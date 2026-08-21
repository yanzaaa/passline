"""Offline tests for the Passline ADK agent pipeline.

Tests cover:
- Pipeline structure (correct ADK class types, correct child order)
- Output schema validation (QcAssessment, LanguageCheckerOutput)
- Approval queue mechanics (enqueue → pending → approve/reject → resolved)
- Verifier exit condition (escalate=True when findings == 0)
- Ingest agent (SRT bytes → subtitle_file in state)
- Timing/format checkers (known violations found in state)

All tests run without real LLM calls or network requests.
"""
from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path

import pytest

from google.adk.agents import LoopAgent, ParallelAgent, SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types

from passline.agents.pipeline import build_pipeline
from passline.agents.ingest_agent import IngestAgent
from passline.agents.timing_checker import TimingCheckerAgent
from passline.agents.format_checker import FormatCheckerAgent
from passline.agents.verifier_agent import VerifierAgent
from passline.agents.schemas import (
    LanguageCheckerOutput,
    LanguageFlag,
    QcAssessment,
)
from passline.events.bus import EventBus
from passline.models.subtitle import SubtitleCue, SubtitleFile, SrtDialect
from passline.pipeline.approval import ApprovalQueue


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_bus(tmp_path: Path) -> EventBus:
    return EventBus(tmp_path / "test_events.jsonl")


@pytest.fixture
def approval_queue(tmp_bus: EventBus) -> ApprovalQueue:
    return ApprovalQueue(bus=tmp_bus)


@pytest.fixture
def pipeline(tmp_bus: EventBus, approval_queue: ApprovalQueue) -> SequentialAgent:
    return build_pipeline(tmp_bus, approval_queue)


def _clean_file() -> SubtitleFile:
    """A perfectly clean subtitle file — no violations."""
    cue = SubtitleCue(
        index=1, start_ms=0, end_ms=3000,
        lines=["Hello world", "This is fine"]
    )
    return SubtitleFile(cues=[cue], language="en", srt_dialect=SrtDialect())


def _broken_file() -> SubtitleFile:
    """A subtitle file with a line_too_long violation."""
    cue = SubtitleCue(
        index=1, start_ms=0, end_ms=3000,
        lines=["x" * 50, "This line is fine"]  # first line > 42 chars
    )
    return SubtitleFile(cues=[cue], language="en", srt_dialect=SrtDialect())


def _cps_violated_file() -> SubtitleFile:
    """A subtitle file with a cps_exceeded violation."""
    cue = SubtitleCue(
        index=1, start_ms=0, end_ms=500,  # 500ms for 20 chars → 40 CPS
        lines=["Hello world twelve!"]  # ~19 chars
    )
    return SubtitleFile(cues=[cue], language="en", srt_dialect=SrtDialect())


async def _run_agent_with_state(
    agent,
    initial_state: dict,
    bus: EventBus,
    session_id: str = "s1",
) -> dict:
    """Run *agent* offline with *initial_state*, return final session state."""
    svc = InMemorySessionService()
    await svc.create_session(
        app_name="test", user_id="u1", session_id=session_id,
        state=initial_state,
    )
    runner = Runner(agent=agent, app_name="test", session_service=svc)
    async for _ev in runner.run_async(
        user_id="u1", session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text="go")])
    ):
        pass
    session = await svc.get_session(app_name="test", user_id="u1", session_id=session_id)
    return dict(session.state)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline structure tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineStructure:
    def test_pipeline_is_sequential_agent(self, pipeline: SequentialAgent) -> None:
        assert isinstance(pipeline, SequentialAgent)

    def test_pipeline_name(self, pipeline: SequentialAgent) -> None:
        assert pipeline.name == "delivery_pipeline"

    def test_pipeline_has_four_stages(self, pipeline: SequentialAgent) -> None:
        assert len(pipeline.sub_agents) == 4

    def test_stage_1_is_ingest(self, pipeline: SequentialAgent) -> None:
        ingest = pipeline.sub_agents[0]
        assert isinstance(ingest, IngestAgent)
        assert ingest.name == "ingest"

    def test_stage_2_is_parallel_agent(self, pipeline: SequentialAgent) -> None:
        fanout = pipeline.sub_agents[1]
        assert isinstance(fanout, ParallelAgent)
        assert fanout.name == "checker_fanout"

    def test_fanout_has_three_checkers(self, pipeline: SequentialAgent) -> None:
        fanout = pipeline.sub_agents[1]
        names = [a.name for a in fanout.sub_agents]
        assert "timing_checker" in names
        assert "format_checker" in names
        assert "language_checker" in names

    def test_stage_3_is_loop_agent(self, pipeline: SequentialAgent) -> None:
        loop = pipeline.sub_agents[2]
        assert isinstance(loop, LoopAgent)
        assert loop.name == "repair_loop"

    def test_loop_max_iterations_is_three(self, pipeline: SequentialAgent) -> None:
        loop = pipeline.sub_agents[2]
        assert loop.max_iterations == 3

    def test_loop_has_fixer_and_verifier(self, pipeline: SequentialAgent) -> None:
        loop = pipeline.sub_agents[2]
        names = [a.name for a in loop.sub_agents]
        assert "fixer" in names
        assert "verifier" in names

    def test_stage_4_is_reporter(self, pipeline: SequentialAgent) -> None:
        from passline.agents.reporter_agent import ReporterAgent
        reporter = pipeline.sub_agents[3]
        assert isinstance(reporter, ReporterAgent)
        assert reporter.name == "reporter"

    def test_language_checker_has_output_schema(self, pipeline: SequentialAgent) -> None:
        fanout = pipeline.sub_agents[1]
        lang_checker = next(a for a in fanout.sub_agents if a.name == "language_checker")
        assert lang_checker.output_schema is LanguageCheckerOutput


# ─────────────────────────────────────────────────────────────────────────────
# Schema validation tests
# ─────────────────────────────────────────────────────────────────────────────

class TestQcAssessmentSchema:
    def test_valid_pass(self) -> None:
        q = QcAssessment(assessment="pass", reason="looks good")
        assert q.assessment == "pass"
        assert q.suggested_text is None

    def test_valid_flag(self) -> None:
        q = QcAssessment(assessment="flag", reason="suspicious")
        assert q.assessment == "flag"

    def test_valid_repair_needed_with_text(self) -> None:
        q = QcAssessment(
            assessment="repair-needed",
            reason="word choice",
            suggested_text="Better text here"
        )
        assert q.suggested_text == "Better text here"

    def test_rejects_invalid_assessment(self) -> None:
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            QcAssessment(assessment="invalid-value", reason="test")

    def test_frozen(self) -> None:
        q = QcAssessment(assessment="pass", reason="ok")
        with pytest.raises(Exception):
            q.assessment = "flag"  # type: ignore[misc]


class TestLanguageCheckerOutputSchema:
    def test_empty_flags_valid(self) -> None:
        out = LanguageCheckerOutput(flags=[], language="en", checked_cues=10)
        assert out.flags == []
        assert out.checked_cues == 10

    def test_flag_confidence_boundary_valid(self) -> None:
        f = LanguageFlag(cue_index=1, confidence=0.0, rule_ref="MT01", explanation="test")
        assert f.confidence == 0.0
        f2 = LanguageFlag(cue_index=2, confidence=1.0, rule_ref="MT02", explanation="test")
        assert f2.confidence == 1.0

    def test_flag_confidence_above_one_rejected(self) -> None:
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            LanguageFlag(cue_index=1, confidence=1.01, rule_ref="MT01", explanation="test")

    def test_flag_confidence_below_zero_rejected(self) -> None:
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            LanguageFlag(cue_index=1, confidence=-0.01, rule_ref="MT01", explanation="test")

    def test_negative_checked_cues_rejected(self) -> None:
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            LanguageCheckerOutput(flags=[], language="en", checked_cues=-1)

    def test_full_output_serialises(self) -> None:
        flag = LanguageFlag(
            cue_index=3,
            confidence=0.9,
            rule_ref="MT01",
            explanation="Antonym substitution detected",
            suggested_text="I love you",
        )
        out = LanguageCheckerOutput(flags=[flag], language="fr", checked_cues=5)
        d = out.model_dump()
        assert d["language"] == "fr"
        assert len(d["flags"]) == 1
        assert d["flags"][0]["rule_ref"] == "MT01"


# ─────────────────────────────────────────────────────────────────────────────
# Approval queue tests
# ─────────────────────────────────────────────────────────────────────────────

class TestApprovalQueue:
    def test_enqueue_returns_item_id(self, approval_queue: ApprovalQueue) -> None:
        item = approval_queue.make_item(
            delivery_id="d1", cue_index=5,
            original_text="I love you", proposed_text="I hate you",
            reason="Meaning change"
        )
        item_id = approval_queue.enqueue(item)
        assert item_id == item.item_id

    def test_pending_shows_new_item(self, approval_queue: ApprovalQueue) -> None:
        item = approval_queue.make_item(
            delivery_id="d1", cue_index=5,
            original_text="a", proposed_text="b", reason="test"
        )
        approval_queue.enqueue(item)
        pending = approval_queue.pending()
        assert len(pending) == 1
        assert pending[0].item_id == item.item_id

    def test_approve_resolves_item(self, approval_queue: ApprovalQueue) -> None:
        item = approval_queue.make_item(
            delivery_id="d1", cue_index=1,
            original_text="a", proposed_text="b", reason="test"
        )
        approval_queue.enqueue(item)
        ok = approval_queue.approve(item.item_id)
        assert ok is True
        assert approval_queue.get(item.item_id).status == "approved"
        assert len(approval_queue.pending()) == 0

    def test_reject_resolves_item(self, approval_queue: ApprovalQueue) -> None:
        item = approval_queue.make_item(
            delivery_id="d1", cue_index=1,
            original_text="a", proposed_text="b", reason="test"
        )
        approval_queue.enqueue(item)
        ok = approval_queue.reject(item.item_id)
        assert ok is True
        assert approval_queue.get(item.item_id).status == "rejected"
        assert len(approval_queue.pending()) == 0

    def test_approve_returns_false_for_unknown_id(self, approval_queue: ApprovalQueue) -> None:
        assert approval_queue.approve("does-not-exist") is False

    def test_reject_returns_false_for_unknown_id(self, approval_queue: ApprovalQueue) -> None:
        assert approval_queue.reject("does-not-exist") is False

    def test_approve_returns_false_for_already_resolved(self, approval_queue: ApprovalQueue) -> None:
        item = approval_queue.make_item(
            delivery_id="d1", cue_index=1,
            original_text="a", proposed_text="b", reason="test"
        )
        approval_queue.enqueue(item)
        approval_queue.approve(item.item_id)
        # Second approve on resolved item
        assert approval_queue.approve(item.item_id) is False

    def test_multi_item_queue(self, approval_queue: ApprovalQueue) -> None:
        items = [
            approval_queue.make_item(
                delivery_id="d1", cue_index=i,
                original_text=f"orig {i}", proposed_text=f"prop {i}",
                reason=f"reason {i}"
            )
            for i in range(3)
        ]
        for item in items:
            approval_queue.enqueue(item)
        assert len(approval_queue.pending()) == 3

        approval_queue.approve(items[0].item_id)
        approval_queue.reject(items[1].item_id)
        assert len(approval_queue.pending()) == 1
        assert approval_queue.pending()[0].item_id == items[2].item_id

    def test_await_decision_approve(self, approval_queue: ApprovalQueue) -> None:
        item = approval_queue.make_item(
            delivery_id="d1", cue_index=1,
            original_text="a", proposed_text="b", reason="test"
        )
        approval_queue.enqueue(item)

        async def run():
            async def approve_later():
                await asyncio.sleep(0.01)
                approval_queue.approve(item.item_id)

            asyncio.create_task(approve_later())
            return await approval_queue.await_decision(item.item_id)

        decision = asyncio.get_event_loop().run_until_complete(run())
        assert decision == "approved"

    def test_await_decision_reject(self, approval_queue: ApprovalQueue) -> None:
        item = approval_queue.make_item(
            delivery_id="d1", cue_index=1,
            original_text="a", proposed_text="b", reason="test"
        )
        approval_queue.enqueue(item)

        async def run():
            async def reject_later():
                await asyncio.sleep(0.01)
                approval_queue.reject(item.item_id)

            asyncio.create_task(reject_later())
            return await approval_queue.await_decision(item.item_id)

        decision = asyncio.get_event_loop().run_until_complete(run())
        assert decision == "rejected"

    def test_item_to_dict(self, approval_queue: ApprovalQueue) -> None:
        item = approval_queue.make_item(
            delivery_id="d1", cue_index=7,
            original_text="Hello", proposed_text="Hi",
            reason="Register violation"
        )
        d = item.to_dict()
        assert d["cue_index"] == 7
        assert d["status"] == "pending"
        assert "item_id" in d


# ─────────────────────────────────────────────────────────────────────────────
# Verifier agent: exit condition
# ─────────────────────────────────────────────────────────────────────────────

class TestVerifierExitCondition:
    def test_verifier_escalates_on_clean_file(self, tmp_bus: EventBus) -> None:
        """VerifierAgent sets escalate=True when subtitle_file has no violations."""
        verifier = VerifierAgent(name="verifier", bus=tmp_bus)

        async def run():
            sf = _clean_file()
            state = await _run_agent_with_state(
                verifier,
                {"subtitle_file": sf.model_dump(), "delivery_id": "t1", "language": "en"},
                tmp_bus,
            )
            # Re-run and capture escalate flag directly from events
            svc = InMemorySessionService()
            await svc.create_session(
                app_name="test", user_id="u1", session_id="s_esc",
                state={"subtitle_file": sf.model_dump(), "delivery_id": "t1", "language": "en"},
            )
            runner = Runner(agent=verifier, app_name="test", session_service=svc)
            escalated = False
            async for ev in runner.run_async(
                user_id="u1", session_id="s_esc",
                new_message=types.Content(role="user", parts=[types.Part(text="verify")])
            ):
                if ev.actions and ev.actions.escalate:
                    escalated = True
            return escalated

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result, "Verifier must escalate when subtitle_file is clean"

    def test_verifier_does_not_escalate_on_violations(self, tmp_bus: EventBus) -> None:
        """VerifierAgent does NOT set escalate when violations remain."""
        verifier = VerifierAgent(name="verifier", bus=tmp_bus)

        async def run():
            sf = _broken_file()  # has line_too_long
            svc = InMemorySessionService()
            await svc.create_session(
                app_name="test", user_id="u1", session_id="s_viol",
                state={"subtitle_file": sf.model_dump(), "delivery_id": "t2", "language": "en"},
            )
            runner = Runner(agent=verifier, app_name="test", session_service=svc)
            escalated = False
            async for ev in runner.run_async(
                user_id="u1", session_id="s_viol",
                new_message=types.Content(role="user", parts=[types.Part(text="verify")])
            ):
                if ev.actions and ev.actions.escalate:
                    escalated = True
            return escalated

        result = asyncio.get_event_loop().run_until_complete(run())
        assert not result, "Verifier must NOT escalate when violations remain"

    def test_verifier_writes_findings_to_state(self, tmp_bus: EventBus) -> None:
        """VerifierAgent writes all_findings to session state."""
        verifier = VerifierAgent(name="verifier", bus=tmp_bus)

        async def run():
            sf = _broken_file()
            return await _run_agent_with_state(
                verifier,
                {"subtitle_file": sf.model_dump(), "delivery_id": "t3", "language": "en"},
                tmp_bus,
                session_id="s_findings",
            )

        state = asyncio.get_event_loop().run_until_complete(run())
        findings = state.get("all_findings", [])
        assert isinstance(findings, list)
        assert len(findings) > 0, "Should have line_too_long finding"
        rules = [f["rule"] for f in findings]
        assert "line_too_long" in rules


# ─────────────────────────────────────────────────────────────────────────────
# Ingest agent
# ─────────────────────────────────────────────────────────────────────────────

class TestIngestAgent:
    def test_ingest_writes_subtitle_file_to_state(self, tmp_bus: EventBus) -> None:
        """IngestAgent writes subtitle_file dict to session state."""
        ingest = IngestAgent(name="ingest", bus=tmp_bus)
        srt_bytes = Path("tests/corpus/clean/tos-en.srt").read_bytes()

        async def run():
            return await _run_agent_with_state(
                ingest,
                {"srt_bytes": srt_bytes, "language": "en", "delivery_id": "i1"},
                tmp_bus,
                session_id="s_ingest",
            )

        state = asyncio.get_event_loop().run_until_complete(run())
        sf_dict = state.get("subtitle_file")
        assert sf_dict is not None
        assert "cues" in sf_dict
        assert len(sf_dict["cues"]) == 76  # EN corpus has 76 cues

    def test_ingest_emits_submitted_event(self, tmp_bus: EventBus) -> None:
        """IngestAgent causes a subtitle.submitted event to be logged."""
        ingest = IngestAgent(name="ingest", bus=tmp_bus)
        srt_bytes = Path("tests/corpus/clean/tos-en.srt").read_bytes()

        async def run():
            return await _run_agent_with_state(
                ingest,
                {"srt_bytes": srt_bytes, "language": "en", "delivery_id": "i2"},
                tmp_bus,
                session_id="s_ingest2",
            )

        asyncio.get_event_loop().run_until_complete(run())
        from passline.events.bus import EventType
        events = [e for e in tmp_bus.read_all() if hasattr(e, "event_type")]
        submitted = [e for e in events if e.event_type == EventType.SUBTITLE_SUBMITTED]
        assert len(submitted) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Timing and format checkers
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckers:
    def test_timing_checker_finds_cps_violation(self, tmp_bus: EventBus) -> None:
        """TimingCheckerAgent finds cps_exceeded on a short-duration cue."""
        timing = TimingCheckerAgent(name="timing_checker", bus=tmp_bus)
        sf = _cps_violated_file()

        async def run():
            return await _run_agent_with_state(
                timing,
                {"subtitle_file": sf.model_dump(), "delivery_id": "tc1", "language": "en"},
                tmp_bus,
                session_id="s_timing",
            )

        state = asyncio.get_event_loop().run_until_complete(run())
        findings = state.get("timing_findings", [])
        rules = [f["rule"] for f in findings]
        # 500ms, ~19 chars → ~38 CPS → cps_exceeded
        assert "cps_exceeded" in rules or "sub_one_second" in rules or len(findings) > 0

    def test_format_checker_finds_line_too_long(self, tmp_bus: EventBus) -> None:
        """FormatCheckerAgent finds line_too_long on a 50-char line."""
        fmt = FormatCheckerAgent(name="format_checker", bus=tmp_bus)
        sf = _broken_file()  # has 50-char line

        async def run():
            return await _run_agent_with_state(
                fmt,
                {"subtitle_file": sf.model_dump(), "delivery_id": "fc1", "language": "en"},
                tmp_bus,
                session_id="s_format",
            )

        state = asyncio.get_event_loop().run_until_complete(run())
        findings = state.get("format_findings", [])
        rules = [f["rule"] for f in findings]
        assert "line_too_long" in rules

    def test_format_checker_no_finding_on_clean_file(self, tmp_bus: EventBus) -> None:
        """FormatCheckerAgent finds nothing on a clean subtitle file."""
        fmt = FormatCheckerAgent(name="format_checker", bus=tmp_bus)
        sf = _clean_file()

        async def run():
            return await _run_agent_with_state(
                fmt,
                {"subtitle_file": sf.model_dump(), "delivery_id": "fc2", "language": "en"},
                tmp_bus,
                session_id="s_format2",
            )

        state = asyncio.get_event_loop().run_until_complete(run())
        findings = state.get("format_findings", [])
        assert findings == [], f"Clean file should produce no format findings; got {findings}"

    def test_timing_checker_no_finding_on_clean_file(self, tmp_bus: EventBus) -> None:
        """TimingCheckerAgent finds nothing on a clean subtitle file."""
        timing = TimingCheckerAgent(name="timing_checker", bus=tmp_bus)
        sf = _clean_file()

        async def run():
            return await _run_agent_with_state(
                timing,
                {"subtitle_file": sf.model_dump(), "delivery_id": "tc2", "language": "en"},
                tmp_bus,
                session_id="s_timing2",
            )

        state = asyncio.get_event_loop().run_until_complete(run())
        findings = state.get("timing_findings", [])
        assert findings == [], f"Clean file should produce no timing findings; got {findings}"
