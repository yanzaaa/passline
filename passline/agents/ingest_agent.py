"""IngestAgent — deterministic SRT parser stage.

Reads raw SRT bytes and language code from ADK session state, calls the
existing ``parse_srt`` parser, and writes the parsed ``SubtitleFile`` (as a
dict) back to session state.  Emits ``subtitle.submitted`` via the event bus
(the parser already does this when ``bus=`` is provided) and wraps the work
with ``station.working`` / ``station.ready`` lifecycle events.

Also emits a ``cue.analysis`` event with per-cue CPS and duration data so the
dashboard heat strip can be populated.

No LLM involvement.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

from pydantic import ConfigDict

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions

from passline.agents.event_utils import emit_station_ready, emit_station_working
from passline.events.bus import DeliveryEvent, EventBus, EventType
from passline.io.srt import parse_srt

log = logging.getLogger(__name__)

# Session state keys (shared contract across all agents)
STATE_SRT_BYTES = "srt_bytes"
STATE_LANGUAGE = "language"
STATE_DELIVERY_ID = "delivery_id"
STATE_SUBTITLE_FILE = "subtitle_file"

_STATION_ID = "ingest"
_STATION_NAME = "Ingest"


class IngestAgent(BaseAgent):
    """ADK BaseAgent that wraps the existing SRT parser.

    Constructor parameters
    ----------------------
    bus:
        The shared :class:`~passline.events.bus.EventBus` instance.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    bus: EventBus

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        srt_bytes: bytes = ctx.session.state.get(STATE_SRT_BYTES, b"")
        language: str = ctx.session.state.get(STATE_LANGUAGE, "und")
        delivery_id: str = ctx.session.state.get(STATE_DELIVERY_ID, "")

        emit_station_working(self.bus, _STATION_ID, _STATION_NAME, delivery_id, language)
        log.debug("IngestAgent: parsing %d bytes lang=%s", len(srt_bytes), language)

        subtitle_file = parse_srt(
            srt_bytes,
            language=language,
            delivery_id=delivery_id,
            bus=self.bus,
        )

        # Emit cue.analysis so the dashboard heat strip can be populated
        self.bus.emit(DeliveryEvent(
            event_type=EventType.CUE_ANALYSIS,
            delivery_id=delivery_id,
            language=language,
            details={
                "cues": [
                    {
                        "index": c.index,
                        "cps": round(c.cps, 2),
                        "duration_ms": c.duration_ms,
                        "text": " ".join(c.lines),
                    }
                    for c in subtitle_file.cues
                ]
            },
        ))

        emit_station_ready(
            self.bus, _STATION_ID, _STATION_NAME, delivery_id, language,
            cue_count=len(subtitle_file.cues),
        )

        # Serialise SubtitleFile as a plain dict for session storage
        subtitle_file_dict: dict[str, Any] = subtitle_file.model_dump()

        yield Event(
            author=self.name,
            actions=EventActions(state_delta={STATE_SUBTITLE_FILE: subtitle_file_dict}),
        )
