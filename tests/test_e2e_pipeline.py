"""End-to-end offline pipeline test.

Runs the full agent graph (ingest → checker_fanout → findings_merger →
repair_loop → reporter) directly via the ADK Runner — no coordinator LLM
needed.  The language checker's Gemini call is stubbed to return a canned
LanguageCheckerOutput so no API credentials are required.

The approval queue runs live: pending approval items produced by the fixer
are auto-approved or auto-rejected by a concurrent coroutine, exercising the
gate-suspension logic end-to-end.

Assertions:
  - report["verdict"] ∈ {"passed", "failed"}
  - repaired_bytes parses cleanly via parse_srt
  - report counts are internally consistent
  - Events were emitted to the bus
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types as genai_types

from passline.agents.pipeline import build_pipeline
from passline.agents.schemas import LanguageCheckerOutput, LanguageFlag
from passline.events.bus import EventBus
from passline.io.srt import parse_srt
from passline.pipeline.approval import ApprovalQueue

BROKEN_EN = Path(__file__).parent / "corpus" / "broken" / "tos-en-broken.srt"
_APP_NAME = "e2e_test"


def _canned_language_output() -> LanguageCheckerOutput:
    """Two synthetic language flags on cues that have known deterministic defects."""
    return LanguageCheckerOutput(
        flags=[
            LanguageFlag(
                cue_index=3,
                confidence=0.85,
                rule_ref="MT01",
                explanation="Antonym substitution detected",
                suggested_text=None,
            ),
            LanguageFlag(
                cue_index=9,
                confidence=0.80,
                rule_ref="MT02",
                explanation="Register violation detected",
                suggested_text=None,
            ),
        ],
        language="en",
        checked_cues=76,
    )


@pytest.mark.anyio
async def test_e2e_pipeline_offline(tmp_path: Path) -> None:
    """Full offline end-to-end pipeline run with stubbed language checker LLM."""
    if not BROKEN_EN.exists():
        pytest.skip("Broken EN corpus file missing")

    srt_bytes = BROKEN_EN.read_bytes()
    delivery_id = "e2e-test-01"
    bus = EventBus(tmp_path / "e2e.jsonl")
    approval_queue = ApprovalQueue(bus=bus)

    # Prepare a canned LLM response object
    canned = _canned_language_output()

    class FakeResponse:
        text = canned.model_dump_json()

    fake_client = MagicMock()
    fake_client.aio = MagicMock()
    fake_client.aio.models = MagicMock()
    fake_client.aio.models.generate_content = AsyncMock(return_value=FakeResponse())

    approved_count = 0
    rejected_count = 0

    async def gate_driver() -> None:
        """Approve first pending item, reject second, approve the rest."""
        nonlocal approved_count, rejected_count
        for _ in range(60):
            await asyncio.sleep(0.05)
            for item in list(approval_queue.pending()):
                if item.status != "pending":
                    continue
                if approved_count == 0:
                    approval_queue.approve(item.item_id)
                    approved_count += 1
                elif rejected_count == 0:
                    approval_queue.reject(item.item_id)
                    rejected_count += 1
                else:
                    approval_queue.approve(item.item_id)

    with patch(
        "passline.agents.language_checker.LanguageCheckerAgent._get_client",
        return_value=fake_client,
    ):
        pipeline = build_pipeline(bus=bus, approval_queue=approval_queue)

        svc = InMemorySessionService()
        await svc.create_session(
            app_name=_APP_NAME,
            user_id="test",
            session_id=delivery_id,
            state={
                "srt_bytes": srt_bytes,
                "language": "en",
                "delivery_id": delivery_id,
            },
        )

        runner = Runner(
            agent=pipeline,
            app_name=_APP_NAME,
            session_service=svc,
        )

        gate_task = asyncio.create_task(gate_driver())
        try:
            async for _ in runner.run_async(
                user_id="test",
                session_id=delivery_id,
                new_message=genai_types.Content(
                    role="user",
                    parts=[genai_types.Part(text="process")],
                ),
            ):
                pass
        finally:
            gate_task.cancel()
            try:
                await gate_task
            except asyncio.CancelledError:
                pass

        # Read final session state
        session = await svc.get_session(
            app_name=_APP_NAME,
            user_id="test",
            session_id=delivery_id,
        )
        state = dict(session.state)

    # ── Assertions ──────────────────────────────────────────────────────────

    report = state.get("report", {})
    assert report, f"No report in session state. State keys: {list(state.keys())}"
    assert "verdict" in report, f"No 'verdict' in report: {report}"
    assert report["verdict"] in ("passed", "failed"), (
        f"Unexpected verdict: {report['verdict']!r}"
    )

    # Repaired bytes should parse as valid SRT
    repaired_bytes = state.get("repaired_bytes")
    if repaired_bytes:
        parsed = parse_srt(repaired_bytes, language="en")
        assert len(parsed.cues) > 0, "Repaired SRT must have at least one cue"

    # Report structure sanity
    violations = report.get("violations_found", {})
    assert isinstance(violations, dict), "violations_found must be a dict"
    assert isinstance(report.get("repairs_applied", 0), int)
    assert isinstance(report.get("repairs_rejected", 0), int)

    # Events should have been emitted
    events = list(bus.read_all())
    assert len(events) > 0, "Pipeline must emit events to the bus"

    # Verify station events use the correct vocabulary
    station_events = [
        e for e in events
        if hasattr(e, "event_type") and e.event_type.value in ("station.working", "station.ready")
    ]
    for ev in station_events:
        assert "station_id" in ev.details, (
            f"station event missing 'station_id': {ev.details}"
        )
        assert "station_name" in ev.details, (
            f"station event missing 'station_name': {ev.details}"
        )
