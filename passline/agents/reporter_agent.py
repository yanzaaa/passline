"""ReporterAgent — final stage: assemble delivery report and write repaired SRT.

Reads all findings, repair log, and approval queue outcomes from session state.
Calls ``write_srt()`` on the repaired subtitle file to produce the final bytes.
Emits a ``delivery.passed`` (green) or summary ``qc.violation`` (red) event.

State contract
--------------
Reads:
  - ``subtitle_file``      : repaired SubtitleFile dict
  - ``all_findings``       : list[dict] of remaining violations
  - ``timing_findings``    : list[dict]
  - ``format_findings``    : list[dict]
  - ``language_findings``  : list[dict]
  - ``repair_log``         : list[dict] of applied repairs
  - ``delivery_id``        : str
  - ``language``           : str

Writes:
  - ``report``             : final delivery report dict
  - ``repaired_bytes``     : bytes (SRT output from write_srt)
"""
from __future__ import annotations

import logging
from typing import AsyncGenerator

from pydantic import ConfigDict

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions

from passline.agents.event_utils import emit_station_ready, emit_station_working
from passline.events.bus import DeliveryEvent, EventBus, EventType
from passline.io.srt import write_srt
from passline.models.subtitle import SubtitleFile

log = logging.getLogger(__name__)

STATE_SUBTITLE_FILE = "subtitle_file"
STATE_DELIVERY_ID = "delivery_id"
STATE_LANGUAGE = "language"
STATE_ALL_FINDINGS = "all_findings"
STATE_TIMING_FINDINGS = "timing_findings"
STATE_FORMAT_FINDINGS = "format_findings"
STATE_LANGUAGE_FINDINGS = "language_findings"
STATE_REPAIR_LOG = "repair_log"
STATE_REPORT = "report"
STATE_REPAIRED_BYTES = "repaired_bytes"

_STATION_ID = "reporter"
_STATION_NAME = "Reporter"


class ReporterAgent(BaseAgent):
    """ADK BaseAgent that assembles the final delivery report."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    bus: EventBus

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        delivery_id: str = ctx.session.state.get(STATE_DELIVERY_ID, "")
        language: str = ctx.session.state.get(STATE_LANGUAGE, "und")
        subtitle_file_dict = ctx.session.state.get(STATE_SUBTITLE_FILE)
        all_findings: list[dict] = ctx.session.state.get(STATE_ALL_FINDINGS, [])
        timing_findings: list[dict] = ctx.session.state.get(STATE_TIMING_FINDINGS, [])
        format_findings: list[dict] = ctx.session.state.get(STATE_FORMAT_FINDINGS, [])
        language_findings: list[dict] = ctx.session.state.get(STATE_LANGUAGE_FINDINGS, [])
        repair_log: list[dict] = ctx.session.state.get(STATE_REPAIR_LOG, [])

        emit_station_working(self.bus, _STATION_ID, _STATION_NAME, delivery_id, language)

        # Produce repaired bytes via the existing writer
        repaired_bytes = b""
        cue_count = 0
        if subtitle_file_dict is not None:
            try:
                subtitle_file = SubtitleFile.model_validate(subtitle_file_dict)
                cue_count = len(subtitle_file.cues)
                if cue_count == 0:
                    all_findings.append({
                        "rule": "no_content",
                        "cue_index": 0,
                        "severity": "ERROR",
                        "explanation": "No parseable cues found. Nothing to certify.",
                    })
                repaired_bytes = write_srt(subtitle_file)
                log.debug("ReporterAgent: wrote %d repaired bytes", len(repaired_bytes))
            except Exception as exc:
                log.error("ReporterAgent: write_srt failed — %s", exc)
        else:
            all_findings.append({
                "rule": "no_content",
                "cue_index": 0,
                "severity": "ERROR",
                "explanation": "No parseable cues found. Nothing to certify.",
            })

        # Verdict: green if no remaining errors, red otherwise
        remaining = len(all_findings)
        has_errors = any(f.get("severity", "ERROR").upper() == "ERROR" for f in all_findings)
        verdict = "passed" if not has_errors else "failed"

        report: dict = {
            "delivery_id": delivery_id,
            "language": language,
            "verdict": verdict,
            "cue_count": cue_count,
            "violations_found": {
                "timing": len(timing_findings),
                "format": len(format_findings),
                "language": len(language_findings),
                "remaining_after_repair": remaining,
            },
            "repairs_applied": len([r for r in repair_log if r.get("approved")]),
            "repairs_rejected": len([r for r in repair_log if not r.get("approved")]),
            "repair_log": repair_log,
            "all_findings": all_findings,
        }

        emit_station_ready(
            self.bus, _STATION_ID, _STATION_NAME, delivery_id, language,
            verdict=verdict,
        )

        yield Event(
            author=self.name,
            actions=EventActions(state_delta={
                STATE_REPORT: report,
                STATE_REPAIRED_BYTES: repaired_bytes,
            }),
        )
