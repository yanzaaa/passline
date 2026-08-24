from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from passline.agents.schemas import LanguageCheckerOutput, LanguageFlag
from passline.events.bus import EventBus
from passline.pipeline.approval import ApprovalQueue
from passline.pipeline.runner import PipelineRunner
from passline.io.srt import parse_srt
from passline.qc.rules import check_file

DEMO_DIR = Path(__file__).parent.parent / "passline" / "corpus" / "demo"


@pytest.mark.anyio
@pytest.mark.parametrize("lang", ["fr", "es", "pt"])
async def test_no_word_drops_in_repair(tmp_path: Path, lang: str) -> None:
    """Ensure that the non-deterministic LLM language repairs do not drop words unless declared as a condensation."""
    from passline.agents.pipeline import build_pipeline
    
    broken_srt_path = DEMO_DIR / f"demo-{lang}-broken.srt"
    if not broken_srt_path.exists():
        pytest.skip("Broken SRT not found")

    srt_bytes = broken_srt_path.read_bytes()
    
    # We do not mock the LLM here. We want to catch the real LLM output (or let the test use the real one if --live-llm is provided).
    # Since we can't guarantee live LLM in normal suite, we will mock the LLM to drop words, and check that the FixerAgent rejects it and retries, and if it still drops words, it marks it unfixable.
    
    bus = EventBus(tmp_path / f"word_drop_{lang}.jsonl")
    approval_queue = ApprovalQueue(bus=bus)

    # Let's mock the language checker to return a finding with NO suggested text
    canned = LanguageCheckerOutput(
        flags=[
            LanguageFlag(
                cue_index=3,
                confidence=0.9,
                rule_ref="MT01",
                explanation="Demo explanation",
                suggested_text=None,
            )
        ],
        language=lang,
        checked_cues=14,
    )

    class FakeResponse:
        text = canned.model_dump_json()

    fake_client = MagicMock()
    fake_client.aio = MagicMock()
    fake_client.aio.models = MagicMock()
    fake_client.aio.models.generate_content = AsyncMock(return_value=FakeResponse())

    def mock_build_coordinator(bus, approval_queue):
        return build_pipeline(bus=bus, approval_queue=approval_queue)

    approvals_requested = 0

    async def gate_driver() -> None:
        nonlocal approvals_requested
        for _ in range(200):
            await asyncio.sleep(0.05)
            for item in list(approval_queue.pending()):
                if item.status == "pending":
                    approvals_requested += 1
                    approval_queue.approve(item.item_id)

    # We mock _propose_language_fix to return a word-dropping string
    with patch("passline.agents.language_checker.LanguageCheckerAgent._get_client", return_value=fake_client), \
         patch("passline.agents.language_checker._call_genai_with_retry", new_callable=AsyncMock, return_value=canned), \
         patch("passline.agents.coordinator.build_coordinator", side_effect=mock_build_coordinator), \
         patch("passline.agents.fixer_agent.FixerAgent._propose_language_fix", new_callable=AsyncMock, return_value="Short") as mock_propose:
         
        runner = PipelineRunner(bus=bus, approval_queue=approval_queue)
        gate_task = asyncio.create_task(gate_driver())
        try:
            report = await runner.run_delivery(srt_bytes, language=lang, delivery_id=f"demo-{lang}-drop")
        finally:
            gate_task.cancel()
            try:
                await gate_task
            except asyncio.CancelledError:
                pass
                
        # Fixer should have retried once, so _propose_language_fix called twice
        assert mock_propose.call_count == 2
        # Since it still dropped words on retry, it should have enqueued ZERO approvals for it
        assert approvals_requested == 0
        
        # Delivery should be failed with the language finding unresolved
        assert report["verdict"] == "failed"
        
        # Verify QC_UNFIXABLE was emitted
        events = bus.read_all()
        unfixable = [e for e in events if e.event_type == "qc.unfixable"]
        assert len(unfixable) == 1
        assert unfixable[0].details["reason"] == "No replacement could be generated"

@pytest.mark.anyio
@pytest.mark.parametrize(
    "lang,seed,meaning_cue",
    [
        ("en", 7, 8),
        ("fr", 11, 13),
        ("de", 13, 12),
        ("es", 17, 0),
        ("ru", 19, 0),
        ("pt", 23, 0),
        ("zh", 29, 0),
        ("fa", 31, 0),
    ],
)
async def test_demo_repairability(tmp_path: Path, lang: str, seed: int, meaning_cue: int) -> None:
    """Run full pipeline on generated demo-grade broken files with approved meaning swap and check they clear."""
    broken_srt_path = DEMO_DIR / f"demo-{lang}-broken.srt"
    if not broken_srt_path.exists():
        pytest.skip(f"Broken SRT not found: {broken_srt_path}")

    srt_bytes = broken_srt_path.read_bytes()

    bus = EventBus(tmp_path / f"demo_{lang}.jsonl")
    approval_queue = ApprovalQueue(bus=bus)

    flags = []
    if meaning_cue > 0:
        flags.append(LanguageFlag(
            cue_index=meaning_cue,
            confidence=0.87,
            rule_ref="MT01",
            explanation="Demo meaning swap flag",
            suggested_text=None,
        ))

    # 1. Prepare canned LLM response returning only 1 meaning_swap at meaning_cue
    canned = LanguageCheckerOutput(
        flags=flags,
        language=lang,
        checked_cues=14,
    )

    class FakeResponse:
        text = canned.model_dump_json()

    fake_client = MagicMock()
    fake_client.aio = MagicMock()
    fake_client.aio.models = MagicMock()
    fake_client.aio.models.generate_content = AsyncMock(return_value=FakeResponse())

    # 2. Gate driver that auto-approves all items in the queue
    approvals_requested = 0

    async def gate_driver() -> None:
        nonlocal approvals_requested
        for _ in range(200):
            await asyncio.sleep(0.05)
            for item in list(approval_queue.pending()):
                if item.status == "pending":
                    assert item.cue_index == meaning_cue, f"Approval raised for wrong cue: {item.cue_index} != {meaning_cue}"
                    approvals_requested += 1
                    approval_queue.approve(item.item_id)

    from passline.agents.pipeline import build_pipeline

    def mock_build_coordinator(bus, approval_queue):
        return build_pipeline(bus=bus, approval_queue=approval_queue)

    with patch(
        "passline.agents.language_checker.LanguageCheckerAgent._get_client",
        return_value=fake_client,
    ), patch(
        "passline.agents.language_checker._call_genai_with_retry",
        new_callable=AsyncMock,
        return_value=canned,
    ), patch(
        "passline.agents.coordinator.build_coordinator",
        side_effect=mock_build_coordinator,
    ), patch(
        "passline.agents.fixer_agent.FixerAgent._propose_language_fix",
        new_callable=AsyncMock,
        return_value="a b c d e f g h i j k l m n o p q r s t",
    ):
        runner = PipelineRunner(bus=bus, approval_queue=approval_queue)

        gate_task = asyncio.create_task(gate_driver())
        try:
            report = await runner.run_delivery(srt_bytes, language=lang, delivery_id=f"demo-{lang}")
        finally:
            gate_task.cancel()
            try:
                await gate_task
            except asyncio.CancelledError:
                pass

    # 3. Assertions
    if meaning_cue > 0:
        assert approvals_requested == 1, f"Expected 1 approval requested, got {approvals_requested}"
    else:
        assert approvals_requested == 0, f"Expected 0 approvals requested, got {approvals_requested}"
        
    assert report["verdict"] == "passed", f"Failed for {lang}: {report}"

    repaired_bytes = await runner.get_repaired_bytes()
    assert repaired_bytes, "No repaired bytes returned"
    
    if meaning_cue > 0:
        assert b"a b c d e f g h i j k l m n o p q r s t" in repaired_bytes

    # Re-parsed repaired SRT grades clean via check_file()
    repaired_file = parse_srt(repaired_bytes, language=lang)
    violations = check_file(repaired_file)
    assert len(violations) == 0, f"Violations remaining in repaired {lang} file: {violations}"


@pytest.mark.anyio
async def test_fixer_requests_proposal_when_checker_omits_it(tmp_path: Path) -> None:
    """If LanguageChecker omits suggested_text, FixerAgent must explicitly request one and enqueue it."""
    from passline.agents.pipeline import build_pipeline
    
    lang = "en"
    srt_bytes = b"1\n00:00:01,000 --> 00:00:03,000\nHello world.\n\n"
    
    bus = EventBus(tmp_path / "fixer_test.jsonl")
    approval_queue = ApprovalQueue(bus=bus)

    canned = LanguageCheckerOutput(
        flags=[
            LanguageFlag(
                cue_index=1,
                confidence=0.87,
                rule_ref="MT01",
                explanation="Demo explanation",
                suggested_text=None,
            )
        ],
        language=lang,
        checked_cues=1,
    )

    class FakeResponse:
        text = canned.model_dump_json()

    fake_client = MagicMock()
    fake_client.aio = MagicMock()
    fake_client.aio.models = MagicMock()
    fake_client.aio.models.generate_content = AsyncMock(return_value=FakeResponse())

    def mock_build_coordinator(bus, approval_queue):
        return build_pipeline(bus=bus, approval_queue=approval_queue)

    approvals_requested = 0

    async def gate_driver() -> None:
        nonlocal approvals_requested
        for _ in range(200):
            await asyncio.sleep(0.05)
            for item in list(approval_queue.pending()):
                if item.status == "pending":
                    approvals_requested += 1
                    approval_queue.approve(item.item_id)

    with patch("passline.agents.language_checker.LanguageCheckerAgent._get_client", return_value=fake_client), \
         patch("passline.agents.language_checker._call_genai_with_retry", new_callable=AsyncMock, return_value=canned), \
         patch("passline.agents.coordinator.build_coordinator", side_effect=mock_build_coordinator), \
         patch("passline.agents.fixer_agent.FixerAgent._propose_language_fix", new_callable=AsyncMock, return_value="Proposed text different") as mock_propose:
         
        runner = PipelineRunner(bus=bus, approval_queue=approval_queue)
        gate_task = asyncio.create_task(gate_driver())
        try:
            report = await runner.run_delivery(srt_bytes, language=lang, delivery_id="test-fixer")
        finally:
            gate_task.cancel()
            
        mock_propose.assert_called_once()
        assert approvals_requested == 1

@pytest.mark.anyio
@pytest.mark.parametrize("action", ["approve", "reject"])
async def test_language_approval_outcomes(tmp_path: Path, action: str) -> None:
    """Ensure an approved language fix clears and a rejected one holds."""
    lang = "en"
    broken_srt_path = DEMO_DIR / f"demo-{lang}-broken.srt"
    if not broken_srt_path.exists():
        pytest.skip("Broken SRT not found")

    srt_bytes = broken_srt_path.read_bytes()
    bus = EventBus(tmp_path / f"demo_approval_{action}.jsonl")
    approval_queue = ApprovalQueue(bus=bus)

    # Prepare canned LLM response
    canned = LanguageCheckerOutput(
        flags=[
            LanguageFlag(
                cue_index=8,
                confidence=0.87,
                rule_ref="MT01",
                explanation="Demo meaning swap flag",
                suggested_text=None,
            )
        ],
        language=lang,
        checked_cues=14,
    )

    class FakeResponse:
        text = canned.model_dump_json()

    fake_client = MagicMock()
    fake_client.aio.models.generate_content = AsyncMock(return_value=FakeResponse())

    async def gate_driver() -> None:
        for _ in range(200):
            await asyncio.sleep(0.05)
            for item in list(approval_queue.pending()):
                if item.status == "pending":
                    if action == "approve":
                        approval_queue.approve(item.item_id)
                    else:
                        approval_queue.reject(item.item_id)

    from passline.agents.pipeline import build_pipeline

    def mock_build_coordinator(bus, approval_queue):
        return build_pipeline(bus=bus, approval_queue=approval_queue)

    with patch(
        "passline.agents.language_checker.LanguageCheckerAgent._get_client",
        return_value=fake_client,
    ), patch(
        "passline.agents.language_checker._call_genai_with_retry",
        new_callable=AsyncMock,
        return_value=canned,
    ), patch(
        "passline.agents.coordinator.build_coordinator",
        side_effect=mock_build_coordinator,
    ), patch(
        "passline.agents.fixer_agent.FixerAgent._propose_language_fix",
        new_callable=AsyncMock,
        return_value="Proposed text that is definitely different from original",
    ):
        runner = PipelineRunner(bus=bus, approval_queue=approval_queue)
        gate_task = asyncio.create_task(gate_driver())
        try:
            report = await runner.run_delivery(srt_bytes, language=lang, delivery_id=f"demo-{lang}-{action}")
        finally:
            gate_task.cancel()

    if action == "approve":
        assert report["verdict"] == "passed"
    else:
        assert report["verdict"] == "failed"
        assert report["violations_found"]["remaining_after_repair"] == 1


@pytest.mark.parametrize("lang", ["en", "fr", "de", "es", "ru", "pt", "zh", "fa"])
def test_deterministic_repair_preserves_text(lang: str) -> None:
    """Ensure that deterministic fixes (like line_too_long or three_line_cue) do not discard text."""
    broken_srt_path = DEMO_DIR / f"demo-{lang}-broken.srt"
    if not broken_srt_path.exists():
        pytest.skip(f"Broken SRT not found: {broken_srt_path}")

    from passline.qc.rules import check_file
    from passline.agents.fixer_agent import _apply_deterministic_fix
    from passline.models.subtitle import _strip_markup

    file_obj = parse_srt(broken_srt_path.read_bytes(), language=lang)
    
    def get_visible_text(f) -> str:
        return "".join(_strip_markup("".join(c.lines)).replace(" ", "") for c in f.cues)
        
    original_text = get_visible_text(file_obj)

    # Apply all deterministic fixes that would trigger
    import dataclasses
    violations = check_file(file_obj)
    cues = file_obj.cues
    for violation in violations:
        cues = _apply_deterministic_fix(cues, dataclasses.asdict(violation))

    repaired_file = file_obj.model_copy(update={"cues": cues})
    repaired_text = get_visible_text(repaired_file)

    assert original_text == repaired_text, f"Text was discarded in {lang} deterministic repair!"
