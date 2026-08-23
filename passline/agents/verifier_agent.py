"""VerifierAgent — deterministic repair verifier (LoopAgent exit controller).

Re-runs the full rule engine on the current subtitle state after each repair
pass.  When zero findings remain, yields an event with ``actions.escalate=True``
to signal the :class:`~google.adk.agents.LoopAgent` to exit.

This agent contains no LLM; it is pure deterministic Python.
"""
from __future__ import annotations

import dataclasses
import logging
from typing import AsyncGenerator

from pydantic import ConfigDict

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions

from passline.agents.event_utils import emit_station_ready, emit_station_working
from passline.events.bus import DeliveryEvent, EventBus, EventType
from passline.models.subtitle import SubtitleFile
from passline.qc.rules import check_file

log = logging.getLogger(__name__)

# Session state keys
STATE_SUBTITLE_FILE = "subtitle_file"
STATE_DELIVERY_ID = "delivery_id"
STATE_LANGUAGE = "language"
STATE_ALL_FINDINGS = "all_findings"

_STATION_ID = "verifier"
_STATION_NAME = "Verifier"


class VerifierAgent(BaseAgent):
    """ADK BaseAgent that re-runs the rule engine and controls loop exit.

    When no findings remain, it sets ``event.actions.escalate = True`` so the
    parent :class:`~google.adk.agents.LoopAgent` terminates cleanly.

    Language findings (rule refs MT01–MT06) are preserved: after re-running
    the deterministic rule engine, any existing language findings whose
    ``cue_index`` is not covered by a deterministic finding are merged back
    into ``all_findings`` so they are not silently lost.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    bus: EventBus

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        delivery_id: str = ctx.session.state.get(STATE_DELIVERY_ID, "")
        language: str = ctx.session.state.get(STATE_LANGUAGE, "und")
        subtitle_file_dict = ctx.session.state.get(STATE_SUBTITLE_FILE)

        emit_station_working(self.bus, _STATION_ID, _STATION_NAME, delivery_id, language)

        if subtitle_file_dict is None:
            log.warning("VerifierAgent: no subtitle_file in state — escalating")
            emit_station_ready(
                self.bus, _STATION_ID, _STATION_NAME, delivery_id, language,
                findings=0, verdict="no_file",
            )
            yield Event(
                author=self.name,
                actions=EventActions(escalate=True, state_delta={STATE_ALL_FINDINGS: []}),
            )
            return

        subtitle_file = SubtitleFile.model_validate(subtitle_file_dict)
        det_findings = check_file(subtitle_file)
        det_dicts = [dataclasses.asdict(f) for f in det_findings]

        # Preserve language findings not superseded by a deterministic finding
        # on the same cue. Language rules use refs MT01–MT06.
        existing_all: list[dict] = ctx.session.state.get(STATE_ALL_FINDINGS, []) or []
        det_cue_rules = {(d["cue_index"], d["rule"]) for d in det_dicts}
        surviving_language = [
            f for f in existing_all
            if f.get("rule", "").startswith("MT")
            and (f.get("cue_index"), f.get("rule")) not in det_cue_rules
        ]

        combined = det_dicts + surviving_language
        verdict = "clean" if not combined else "violations_remain"

        emit_station_ready(
            self.bus, _STATION_ID, _STATION_NAME, delivery_id, language,
            findings=len(combined), verdict=verdict,
        )

        log.debug(
            "VerifierAgent: %d det + %d lang = %d total — verdict=%s",
            len(det_dicts), len(surviving_language), len(combined), verdict,
        )

        if not combined:
            # Zero violations — signal the LoopAgent to exit
            yield Event(
                author=self.name,
                actions=EventActions(
                    escalate=True,
                    state_delta={STATE_ALL_FINDINGS: combined},
                ),
            )
        else:
            # Still violations — update state and let the loop continue
            yield Event(
                author=self.name,
                actions=EventActions(state_delta={STATE_ALL_FINDINGS: combined}),
            )
