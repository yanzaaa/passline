"""FixerAgent — repair agent for subtitle violations.

Applies fixes to the current subtitle state based on findings collected by
the parallel checker stage.  There are two classes of fix:

Deterministic fixes (timing / format)
    Applied inline by pure Python logic.  No LLM call.
    - ``line_too_long`` → split line at the nearest space before char 42
    - ``three_line_cue`` → join lines 2+3 (if ≤ 42 visible chars) else truncate
    - ``cps_exceeded`` → extend ``end_ms`` to bring CPS just below 20.0
    - ``sub_one_second`` → extend ``end_ms`` to MIN_DURATION_MS
    - ``overlapping_cues`` → retract ``end_ms`` of cue[i] to cue[i+1].start_ms − 1

Language-level fixes (from language checker output)
    The fixer agent invokes the LLM to propose a rewording.  If the proposed
    text is meaningfully different from the original (i.e. meaning-changing),
    the edit is enqueued in the :class:`~passline.pipeline.approval.ApprovalQueue`
    and the loop suspends via ``await queue.await_decision(item_id)``.

State contract
--------------
Reads:
  - ``subtitle_file`` : serialised SubtitleFile dict
  - ``all_findings``  : list[dict] merged from timing + format + language checkers
  - ``delivery_id``   : str
  - ``language``      : str

Writes:
  - ``subtitle_file`` : updated SubtitleFile dict after repairs
  - ``repair_log``    : list[dict] of applied repairs
"""
from __future__ import annotations

import dataclasses
import logging
import os
import asyncio
from typing import Any, AsyncGenerator

from pydantic import ConfigDict

from google.adk import Agent  # LlmAgent public alias
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions

from passline.agents.callbacks import install_retry_on_model
from passline.agents.event_utils import emit_station_ready, emit_station_working
from passline.events.bus import DeliveryEvent, EventBus, EventType
from passline.models.subtitle import SubtitleCue, SubtitleFile
from passline.pipeline.approval import ApprovalQueue
from passline.qc.thresholds import CPS_VIOLATION, CPS_WARNING_LOW, LINE_CHAR_MAX, MIN_DURATION_MS

log = logging.getLogger(__name__)

_DEFAULT_FIXER_MODEL = "gemini-3-flash-preview"
_FALLBACK_MODEL = "gemini-2.5-flash"

# Session state keys
STATE_SUBTITLE_FILE = "subtitle_file"
STATE_DELIVERY_ID = "delivery_id"
STATE_LANGUAGE = "language"
STATE_ALL_FINDINGS = "all_findings"
STATE_REPAIR_LOG = "repair_log"

_STATION_ID = "fixer"
_STATION_NAME = "Fixer"

# Rules handled deterministically (no LLM)
_DETERMINISTIC_RULES = frozenset({
    "line_too_long",
    "three_line_cue",
    "cps_exceeded",
    "cps_warning",
    "sub_one_second",
    "overlapping_cues",
    "malformed_timecode",
})

_FIXER_INSTRUCTION = """
You are a subtitle repair specialist for streaming delivery workflows.

You will receive a subtitle cue that has been flagged for a language-quality
issue.  Your task is to propose a minimal rewording that fixes the issue
while preserving the intended meaning and tone.

Return ONLY the corrected subtitle text for the cue — no explanation, no JSON,
no markup, just the plain corrected text exactly as it should appear in the
subtitle file.  If the cue has multiple lines, preserve the line breaks
using a newline character.

Important constraints:
- Keep every line to at most 42 visible characters
- Preserve the language of the original text (do not translate)
- Keep the same register and tone as surrounding cues
- If you cannot improve the cue without changing its meaning, return the
  original text unchanged
""".strip()


# ── Deterministic repair helpers ──────────────────────────────────────────────

def _split_long_line(line: str, max_chars: int = LINE_CHAR_MAX) -> list[str]:
    """Split *line* at the nearest space at or before *max_chars*."""
    if len(line.rstrip()) <= max_chars:
        return [line]
    split_at = line.rfind(" ", 0, max_chars + 1)
    if split_at == -1:
        # No space — hard split
        return [line[:max_chars], line[max_chars:]]
    return [line[:split_at], line[split_at + 1:]]


def _apply_deterministic_fix(
    cues: list[SubtitleCue],
    finding: dict,
) -> list[SubtitleCue]:
    """Return a new cues list with the deterministic fix applied for *finding*."""
    rule = finding["rule"]
    cue_index = finding["cue_index"]  # 1-based

    # Build mutable dict copy of cues for easy replacement
    cue_list = list(cues)
    idx = next((i for i, c in enumerate(cue_list) if c.index == cue_index), None)
    if idx is None:
        return cues

    cue = cue_list[idx]

    if rule == "line_too_long":
        new_lines: list[str] = []
        for line in cue.lines:
            new_lines.extend(_split_long_line(line))
        # Do not truncate text. If reflowing creates > 2 lines, leave it unfixable
        # if it can't fit in 3 lines either, we don't truncate text.
        # Actually, standard is max 2 lines, but 3 lines is flagged. If we just created >3 lines, we cannot fix it easily.
        # Let's just update if it fits in 2 or 3 lines. If it's > 3 lines, leave unchanged.
        if len(new_lines) <= 3:
            cue_list[idx] = cue.model_copy(update={"lines": new_lines})

    elif rule == "three_line_cue":
        if len(cue.lines) > 2:
            # Join last two lines if combined visible length <= LINE_CHAR_MAX
            from passline.models.subtitle import _strip_markup
            combined = cue.lines[-2].rstrip() + " " + cue.lines[-1].lstrip()
            if len(_strip_markup(combined).rstrip()) <= LINE_CHAR_MAX:
                new_lines = list(cue.lines[:-2]) + [combined]
                cue_list[idx] = cue.model_copy(update={"lines": new_lines})
            # else: do not discard the third line; leave unchanged as unfixable.

    elif rule in ("cps_exceeded", "cps_warning"):
        # Extend end_ms so CPS drops to just below CPS_WARNING_LOW (clean state)
        chars = cue.total_chars
        if chars > 0:
            new_duration_ms = int(chars / CPS_WARNING_LOW * 1000) + 1
            new_end_ms = cue.start_ms + new_duration_ms
            # Don't extend into the next cue (leave 50ms gap)
            if idx + 1 < len(cue_list):
                next_start = cue_list[idx + 1].start_ms
                new_end_ms = min(new_end_ms, next_start - 50)
            cue_list[idx] = cue.model_copy(update={"end_ms": max(new_end_ms, cue.start_ms + 1)})

    elif rule == "sub_one_second":
        new_end_ms = cue.start_ms + MIN_DURATION_MS
        if idx + 1 < len(cue_list):
            next_start = cue_list[idx + 1].start_ms
            new_end_ms = min(new_end_ms, next_start - 50)
        cue_list[idx] = cue.model_copy(update={"end_ms": max(new_end_ms, cue.start_ms + 1)})

    elif rule == "overlapping_cues":
        if idx + 1 < len(cue_list):
            next_start = cue_list[idx + 1].start_ms
            new_end_ms = next_start - 1
            if new_end_ms > cue.start_ms:
                cue_list[idx] = cue.model_copy(update={"end_ms": new_end_ms})

    elif rule == "malformed_timecode":
        # Swap start/end if end < start; if equal, add 1s
        if cue.end_ms <= cue.start_ms:
            cue_list[idx] = cue.model_copy(update={"end_ms": cue.start_ms + MIN_DURATION_MS})

    return cue_list


# ── FixerAgent ────────────────────────────────────────────────────────────────

class FixerAgent(LlmAgent):
    """ADK LlmAgent that applies repairs to subtitle violations.

    Deterministic fixes are applied inline (no LLM).  Language-level fixes
    are proposed by the LLM and routed through the human approval queue if
    meaning-changing.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    bus: EventBus
    approval_queue: ApprovalQueue

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        delivery_id: str = ctx.session.state.get(STATE_DELIVERY_ID, "")
        language: str = ctx.session.state.get(STATE_LANGUAGE, "und")
        subtitle_file_dict = ctx.session.state.get(STATE_SUBTITLE_FILE)
        all_findings_dicts: list[dict] = ctx.session.state.get(STATE_ALL_FINDINGS, [])
        existing_repair_log: list[dict] = ctx.session.state.get(STATE_REPAIR_LOG, [])

        emit_station_working(self.bus, _STATION_ID, _STATION_NAME, delivery_id, language)

        if not subtitle_file_dict or not all_findings_dicts:
            emit_station_ready(
                self.bus, _STATION_ID, _STATION_NAME, delivery_id, language,
                repairs=0,
            )
            yield Event(
                author=self.name,
                actions=EventActions(state_delta={}),
            )
            return

        subtitle_file = SubtitleFile.model_validate(subtitle_file_dict)
        cues = list(subtitle_file.cues)
        repair_log: list[dict] = list(existing_repair_log)
        
        resolved_language_findings: list[dict] = []
        unresolved_findings: list[dict] = []

        attempted_language_fixes = {(r.get("cue_index"), r.get("rule_ref") or r.get("rule")) for r in repair_log if r.get("type") == "language"}

        language_tasks = []
        for finding in all_findings_dicts:
            rule = finding.get("rule", "")
            if rule in _DETERMINISTIC_RULES:
                # ── Deterministic repair ──────────────────────────────────
                cue_index = finding["cue_index"]
                orig_cue = next((c for c in cues if c.index == cue_index), None)
                original_text = "\n".join(orig_cue.lines) if orig_cue else ""
                new_cues = _apply_deterministic_fix(cues, finding)
                if new_cues is not cues:
                    repaired_cue = next((c for c in new_cues if c.index == cue_index), None)
                    repaired_text = "\n".join(repaired_cue.lines) if repaired_cue else ""
                    repair_log.append({
                        "rule": rule,
                        "cue_index": cue_index,
                        "type": "deterministic",
                        "approved": True,
                    })
                    cues = new_cues
                    self.bus.emit(DeliveryEvent(
                        event_type=EventType.QC_REPAIRED,
                        delivery_id=delivery_id,
                        language=language,
                        details={
                            "rule":     rule,
                            "rule_ref": rule,
                            "cue":      cue_index,
                            "original": original_text,
                            "repaired": repaired_text,
                        },
                    ))
                unresolved_findings.append(finding)
            else:
                # ── Language-level repair via LLM ─────────────────────────
                cue_index = finding.get("cue_index", 0)
                rule_ref = finding.get("rule_ref") or finding.get("rule", "Unknown")
                
                # Do not re-propose if already attempted
                if (cue_index, rule_ref) in attempted_language_fixes:
                    unresolved_findings.append(finding)
                    continue

                cue = next((c for c in cues if c.index == cue_index), None)
                if cue is None:
                    unresolved_findings.append(finding)
                    continue

                original_text = "\n".join(cue.lines)
                explanation = finding.get("explanation", "Language quality issue")
                
                async def _get_proposal(f, o_text, expl, r_ref):
                    prop = f.get("suggested_text")
                    if not prop or not prop.strip() or prop.strip() == o_text.strip():
                        prop = await self._propose_language_fix(o_text, expl, language)
                    return (f, o_text, prop, expl, r_ref)

                language_tasks.append(_get_proposal(finding, original_text, explanation, rule_ref))

        # Wait for all language proposals concurrently
        proposals = []
        if language_tasks:
            proposals = await asyncio.gather(*language_tasks)

        # Enqueue all valid meaning-changing edits
        pending_items = []
        for finding, original_text, proposed_text, explanation, rule_ref in proposals:
            cue_index = finding.get("cue_index", 0)
            if proposed_text and proposed_text.strip() != original_text.strip():
                item = self.approval_queue.make_item(
                    delivery_id=delivery_id,
                    cue_index=cue_index,
                    original_text=original_text,
                    proposed_text=proposed_text,
                    reason=explanation,
                    rule_ref=rule_ref,
                    confidence=finding.get("confidence", 0.0),
                    explanation=explanation,
                )
                self.approval_queue.enqueue(item)
                pending_items.append((item, finding, original_text, proposed_text, rule_ref))
            else:
                rule = finding.get("rule", "")
                repair_log.append({
                    "rule": rule,
                    "rule_ref": rule_ref,
                    "cue_index": cue_index,
                    "type": "language",
                    "approved": False,
                    "status": "unfixable",
                    "original": original_text,
                    "proposed": None,
                })
                self.bus.emit(DeliveryEvent(
                    event_type=EventType.QC_UNFIXABLE,
                    delivery_id=delivery_id,
                    language=language,
                    details={
                        "rule": rule,
                        "rule_ref": rule_ref,
                        "cue": cue_index,
                        "reason": "No replacement could be generated"
                    }
                ))
                unresolved_findings.append(finding)

        # Await decisions sequentially (human responds one by one)
        for item, finding, original_text, proposed_text, rule_ref in pending_items:
            cue_index = finding.get("cue_index", 0)
            rule = finding.get("rule", "")
            try:
                decision = await asyncio.wait_for(
                    self.approval_queue.await_decision(item.item_id),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                decision = "timeout"
                self.approval_queue.reject(item.item_id)
                self.bus.emit(DeliveryEvent(
                    event_type=EventType.APPROVAL_TIMEOUT,
                    delivery_id=delivery_id,
                    language=language,
                    details={"reason": "No human decision was made"}
                ))

            if decision == "approved":
                new_lines = proposed_text.split("\n")
                idx = next((i for i, c in enumerate(cues) if c.index == cue_index), None)
                if idx is not None:
                    cues[idx] = cues[idx].model_copy(update={"lines": new_lines})
                repair_entry = {
                    "rule": rule,
                    "rule_ref": rule_ref,
                    "cue": cue_index,
                    "cue_index": cue_index,
                    "type": "language",
                    "approved": True,
                    "original": original_text,
                    "repaired": proposed_text,
                }
                repair_log.append(repair_entry)
                self.bus.emit(DeliveryEvent(
                    event_type=EventType.QC_REPAIRED,
                    delivery_id=delivery_id,
                    language=language,
                    details=repair_entry,
                ))
                resolved_language_findings.append(finding)
            else:
                repair_log.append({
                    "rule": rule,
                    "rule_ref": rule_ref,
                    "cue_index": cue_index,
                    "type": "language",
                    "approved": False,
                    "status": decision,
                    "original": original_text,
                    "proposed": proposed_text,
                })
                unresolved_findings.append(finding)

        # Rebuild the SubtitleFile with repaired cues
        repaired_file = subtitle_file.model_copy(update={"cues": cues})
        
        state_delta = {
            STATE_SUBTITLE_FILE: repaired_file.model_dump(),
            STATE_REPAIR_LOG: repair_log,
            STATE_ALL_FINDINGS: unresolved_findings,
        }
        
        if resolved_language_findings:
            existing_lang = ctx.session.state.get("language_findings", [])
            if existing_lang:
                resolved_keys = {(f.get("cue_index"), f.get("rule_ref") or f.get("rule")) for f in resolved_language_findings}
                new_lang = [f for f in existing_lang if (f.get("cue_index"), f.get("rule_ref") or f.get("rule")) not in resolved_keys]
                state_delta["language_findings"] = new_lang

        emit_station_ready(
            self.bus, _STATION_ID, _STATION_NAME, delivery_id, language,
            repairs=len(repair_log),
        )

        yield Event(
            author=self.name,
            actions=EventActions(state_delta=state_delta),
        )

    async def _propose_language_fix(
        self,
        original_text: str,
        explanation: str,
        language: str,
    ) -> str | None:
        """Ask the LLM for a minimal repair of *original_text*.

        Returns the proposed text string, or None on failure.
        """
        try:
            from google.adk.runners import Runner
            from google.adk.sessions.in_memory_session_service import InMemorySessionService
            from google.genai import types

            prompt = (
                f"Language: {language}\n"
                f"Issue: {explanation}\n"
                f"Original subtitle text:\n{original_text}\n\n"
                "Provide the corrected subtitle text only:"
            )

            # Use a lightweight single-turn LLM call via a temp runner
            fix_agent = Agent(
                name="_lang_fix_helper",
                model=os.getenv("PASSLINE_FIXER_MODEL", _DEFAULT_FIXER_MODEL),
                instruction=_FIXER_INSTRUCTION,
                description="Temporary one-shot language fix helper",
            )
            install_retry_on_model(fix_agent, max_attempts=4, base_delay_s=1.0)

            svc = InMemorySessionService()
            runner = Runner(
                agent=fix_agent,
                app_name="passline_fixer",
                session_service=svc,
                auto_create_session=True,
            )
            response_text = ""
            async for ev in runner.run_async(
                user_id="fixer",
                session_id=f"fix_{id(original_text)}",
                new_message=types.Content(
                    role="user",
                    parts=[types.Part(text=prompt)],
                ),
            ):
                if ev.content and ev.content.parts:
                    for part in ev.content.parts:
                        if hasattr(part, "text") and part.text:
                            response_text += part.text

            return response_text.strip() or None

        except Exception as exc:
            log.warning("FixerAgent: LLM fix proposal failed — %s", exc)
            return None


def build_fixer_agent(bus: EventBus, approval_queue: ApprovalQueue) -> FixerAgent:
    """Build the fixer agent and install retry on its model."""
    model = os.getenv("PASSLINE_FIXER_MODEL", _DEFAULT_FIXER_MODEL)

    agent = FixerAgent(
        name="fixer",
        model=model,
        instruction=_FIXER_INSTRUCTION,
        description=(
            "Repairs subtitle violations. Applies deterministic fixes inline "
            "and proposes language-level rewording via the LLM."
        ),
        bus=bus,
        approval_queue=approval_queue,
    )
    install_retry_on_model(agent, max_attempts=4, base_delay_s=1.0)
    return agent
