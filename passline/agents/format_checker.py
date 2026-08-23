"""FormatCheckerAgent — deterministic format rule checker.

Reads the parsed ``SubtitleFile`` from ADK session state, runs the format
rules from the existing rule engine (line length, line count), and writes
the findings to session state.

Format rules covered:
- ``line_too_long``
- ``three_line_cue``

No LLM involvement.
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
from passline.qc.rules import Finding, check_file

log = logging.getLogger(__name__)

# Session state keys
STATE_SUBTITLE_FILE = "subtitle_file"
STATE_DELIVERY_ID = "delivery_id"
STATE_LANGUAGE = "language"
STATE_FORMAT_FINDINGS = "format_findings"

# The subset of rules this checker owns
_FORMAT_RULES = frozenset({
    "line_too_long",
    "three_line_cue",
})

_STATION_ID = "format"
_STATION_NAME = "Format"


class FormatCheckerAgent(BaseAgent):
    """ADK BaseAgent that runs format rules on the current subtitle file."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    bus: EventBus

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        delivery_id: str = ctx.session.state.get(STATE_DELIVERY_ID, "")
        language: str = ctx.session.state.get(STATE_LANGUAGE, "und")
        subtitle_file_dict = ctx.session.state.get(STATE_SUBTITLE_FILE)

        if subtitle_file_dict is None:
            log.warning("FormatCheckerAgent: no subtitle_file in state — skipping")
            yield Event(
                author=self.name,
                actions=EventActions(state_delta={STATE_FORMAT_FINDINGS: []}),
            )
            return

        emit_station_working(self.bus, _STATION_ID, _STATION_NAME, delivery_id, language)

        subtitle_file = SubtitleFile.model_validate(subtitle_file_dict)

        # Run full rule engine then filter to format rules only
        all_findings: list[Finding] = check_file(subtitle_file)
        format_findings = [f for f in all_findings if f.rule in _FORMAT_RULES]

        # Emit QC_VIOLATION events for each format finding
        for finding in format_findings:
            self.bus.emit(DeliveryEvent(
                event_type=EventType.QC_VIOLATION,
                delivery_id=delivery_id,
                language=language,
                details={
                    "rule":        finding.rule,
                    "cue":         finding.cue_index,
                    "value":       finding.measured_value,
                    "threshold":   finding.threshold,
                    "severity":    finding.severity,
                    "explanation": finding.explanation,
                    "checker":     "format",
                },
            ))

        emit_station_ready(
            self.bus, _STATION_ID, _STATION_NAME, delivery_id, language,
            findings=len(format_findings),
        )

        log.debug("FormatCheckerAgent: %d format findings", len(format_findings))

        yield Event(
            author=self.name,
            actions=EventActions(state_delta={
                STATE_FORMAT_FINDINGS: [dataclasses.asdict(f) for f in format_findings],
            }),
        )
