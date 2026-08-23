"""Demo replay engine for Passline Mission Control.

Reads passline/corpus/demo/demo_events.jsonl and re-emits every event through
the live EventBus with a fresh timestamp, preserving all other fields.  Pacing
is driven by the ``replay_offset_s`` field in each event's ``details``.

Each replay run uses a fresh delivery_id so repeated runs produce distinct
delivery cards on the dashboard.

Replayed events are written to the live JSONL log and are indistinguishable
from real pipeline events to the dashboard.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from passline.events.bus import EventBus

logger = logging.getLogger(__name__)

_FIXTURE = Path(__file__).parent.parent / "corpus" / "demo" / "demo_events.jsonl"

# Module-level task handle — one replay at a time
_task: asyncio.Task | None = None
_loop_flag: bool = False


def _load_fixture() -> list[dict]:
    """Load and parse the demo fixture JSONL."""
    events = []
    with _FIXTURE.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


async def _run_replay(bus: "EventBus", loop: bool = False) -> None:
    """Async task: re-emit fixture events at realistic pacing, optionally looping."""
    from passline.events.bus import DeliveryEvent, EventType

    while True:
        events = _load_fixture()
        if not events:
            logger.warning("demo_events.jsonl is empty — nothing to replay")
            return

        # Fresh delivery_id per run so repeated plays produce distinct dashboard cards
        delivery_id = f"DEMO-{uuid4().hex[:8].upper()}"

        prev_offset = 0.0
        for raw in events:
            details = dict(raw.get("details", {}))
            offset = float(details.pop("replay_offset_s", 0.0))
            delay = max(0.0, offset - prev_offset)
            if delay > 0:
                await asyncio.sleep(delay)
            prev_offset = offset

            try:
                event = DeliveryEvent(
                    event_type=EventType(raw["event_type"]),
                    delivery_id=delivery_id,
                    language=raw["language"],
                    details=details,
                    # Fresh timestamp so log shows real wall-clock times
                )
                bus.emit(event)
                logger.debug("replayed %s at offset %.1fs", raw["event_type"], offset)
            except Exception as exc:
                logger.warning("skipping event %s: %s", raw.get("event_type"), exc)

        if not loop:
            break
        logger.info("replay loop complete — restarting")
        await asyncio.sleep(2.0)


def start_replay(bus: "EventBus", loop: bool = False) -> None:
    """Start (or restart) the demo replay as an asyncio background task."""
    global _task, _loop_flag
    _loop_flag = loop
    if _task and not _task.done():
        _task.cancel()
    _task = asyncio.create_task(_run_replay(bus, loop=loop))
    logger.info("demo replay started (loop=%s)", loop)


def stop_replay() -> None:
    """Cancel the current replay task if running."""
    global _task
    if _task and not _task.done():
        _task.cancel()
        logger.info("demo replay stopped")
    _task = None
