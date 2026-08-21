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

from passline.events.bus import DeliveryEvent, EventBus, EventType
from passline.models.subtitle import SubtitleFile
from passline.qc.rules import check_file

log = logging.getLogger(__name__)

# Session state keys
STATE_SUBTITLE_FILE = "subtitle_file"
STATE_DELIVERY_ID = "delivery_id"
STATE_LANGUAGE = "language"
STATE_ALL_FINDINGS = "all_findings"


class VerifierAgent(BaseAgent):
    """ADK BaseAgent that re-runs the rule engine and controls loop exit.

    When no findings remain, it sets ``event.actions.escalate = True`` so the
    parent :class:`~google.adk.agents.LoopAgent` terminates cleanly.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    bus: EventBus

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        delivery_id: str = ctx.session.state.get(STATE_DELIVERY_ID, "")
        language: str = ctx.session.state.get(STATE_LANGUAGE, "und")
        subtitle_file_dict = ctx.session.state.get(STATE_SUBTITLE_FILE)

        self.bus.emit(DeliveryEvent(
            event_type=EventType.STATION_WORKING,
            delivery_id=delivery_id,
            language=language,
            details={"station": self.name},
        ))

        if subtitle_file_dict is None:
            log.warning("VerifierAgent: no subtitle_file in state — escalating")
            self.bus.emit(DeliveryEvent(
                event_type=EventType.STATION_READY,
                delivery_id=delivery_id,
                language=language,
                details={"station": self.name, "findings": 0, "verdict": "no_file"},
            ))
            yield Event(
                author=self.name,
                actions=EventActions(escalate=True, state_delta={STATE_ALL_FINDINGS: []}),
            )
            return

        subtitle_file = SubtitleFile.model_validate(subtitle_file_dict)
        findings = check_file(subtitle_file)

        findings_dicts = [dataclasses.asdict(f) for f in findings]
        verdict = "clean" if not findings else "violations_remain"

        self.bus.emit(DeliveryEvent(
            event_type=EventType.STATION_READY,
            delivery_id=delivery_id,
            language=language,
            details={
                "station": self.name,
                "findings": len(findings),
                "verdict": verdict,
            },
        ))

        log.debug(
            "VerifierAgent: %d finding(s) remain — verdict=%s",
            len(findings),
            verdict,
        )

        if not findings:
            # Zero violations — signal the LoopAgent to exit
            yield Event(
                author=self.name,
                actions=EventActions(
                    escalate=True,
                    state_delta={STATE_ALL_FINDINGS: findings_dicts},
                ),
            )
        else:
            # Still violations — update state and let the loop continue
            yield Event(
                author=self.name,
                actions=EventActions(state_delta={STATE_ALL_FINDINGS: findings_dicts}),
            )
