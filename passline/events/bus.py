"""Delivery event bus for Passline.

Events are appended to a local JSONL log file. The schema is versioned and
designed to feed a live dashboard and a Kafka topic.

Schema version 1.2
-------------------
Changes from 1.1:
- Four new event types for dashboard station state and per-cue analysis:
  ``station.working``, ``station.ready``, ``cue.analysis``, ``approval.required``
- ``EventBus`` now supports in-process async pub/sub via ``subscribe()`` /
  ``unsubscribe()``.  ``emit()`` remains fully synchronous; all existing callers
  are unaffected.  The JSONL file remains the durable source of truth.
"""
from __future__ import annotations

import asyncio
import json
import uuid
import warnings
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventType(str, Enum):
    """Delivery pipeline event types.

    The original four (1.0) are never modified.  New types added in minor bumps.
    """

    # ── Schema 1.0 — original pipeline events ────────────────────────────────
    SUBTITLE_SUBMITTED = "subtitle.submitted"
    QC_VIOLATION = "qc.violation"
    QC_REPAIRED = "qc.repaired"
    DELIVERY_PASSED = "delivery.passed"

    # ── Schema 1.2 — dashboard station + analysis events ─────────────────────
    STATION_WORKING = "station.working"
    STATION_READY = "station.ready"
    CUE_ANALYSIS = "cue.analysis"
    APPROVAL_REQUIRED = "approval.required"

    # ── Schema 1.3 — honest-fail events ──────────────────────────────────────
    DELIVERY_FAILED = "delivery.failed"


class DeliveryEvent(BaseModel):
    """A single versioned delivery pipeline event.

    Designed to be serialised as one JSONL line and forwarded to a Kafka topic
    or live dashboard without schema changes.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.3"
    """Schema version for forward-compatibility with consumers."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    """Globally unique event identifier (UUID4), generated at creation."""

    event_type: EventType
    """One of the delivery pipeline event types."""

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    """UTC timestamp of when the event was created."""

    delivery_id: str
    """Caller-supplied delivery identifier (e.g. UUID or file stem)."""

    language: str
    """BCP-47 language code of the subtitle file being processed."""

    details: dict[str, Any] = Field(default_factory=dict)
    """Arbitrary event-specific payload. Keep keys snake_case for Kafka compatibility."""

    def serialise(self) -> str:
        """Return a single JSON line (no trailing newline) for JSONL output.

        ``timestamp`` is always converted to UTC before formatting so the ``Z``
        suffix is accurate even when the event was created with a non-UTC datetime.
        """
        data = self.model_dump()
        ts_utc = self.timestamp.astimezone(timezone.utc)
        data["timestamp"] = ts_utc.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        data["event_type"] = self.event_type.value
        return json.dumps(data, ensure_ascii=False)


class UnknownDeliveryEvent(BaseModel):
    """Placeholder for events that cannot be deserialised by this schema version.

    Returned by :meth:`EventBus.read_all` when a log line contains an unknown
    ``event_type`` or a ``schema_version`` this code does not recognise.
    """

    model_config = ConfigDict(frozen=True)

    raw: dict[str, Any]
    """The raw parsed JSON object."""


class EventBus:
    """Appends :class:`DeliveryEvent` records to a JSONL log file and notifies
    in-process async subscribers.

    **JSONL file** is the durable source of truth — every ``emit()`` call
    appends one line regardless of subscriber state.

    **Pub/sub** is in-process only.  Call :meth:`subscribe` to obtain an
    ``asyncio.Queue``; the queue receives every future event the moment it is
    emitted.  Call :meth:`unsubscribe` when the consumer is done (e.g. on SSE
    disconnect) to release the queue.

    ``emit()`` is deliberately synchronous so all existing callers are
    unaffected.  It calls ``put_nowait()`` on each subscriber queue — this is
    safe to call from synchronous code when an event loop is running.  When no
    loop is running (CLI, tests), ``_subscribers`` is always empty so the
    ``put_nowait`` path is never reached.
    """

    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.touch()
        self._subscribers: list[asyncio.Queue[DeliveryEvent]] = []

    # ── JSONL persistence ─────────────────────────────────────────────────────

    def emit(self, event: DeliveryEvent) -> None:
        """Append one event to the JSONL log and notify all async subscribers."""
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(event.serialise() + "\n")
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except Exception:
                pass  # slow consumer or no event loop — drop; JSONL is durable

    def read_all(self) -> list[DeliveryEvent | UnknownDeliveryEvent]:
        """Read and parse all events from the log file.

        Forward-compatible: unknown ``event_type`` values or parse errors produce
        :class:`UnknownDeliveryEvent` objects with a warning instead of raising.
        """
        events: list[DeliveryEvent | UnknownDeliveryEvent] = []
        with self.log_path.open("r", encoding="utf-8") as fh:
            for lineno, raw_line in enumerate(fh, start=1):
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                obj: dict | None = None
                try:
                    obj = json.loads(raw_line)
                    events.append(DeliveryEvent.model_validate(obj))
                except Exception as exc:
                    schema_v = obj.get("schema_version") if isinstance(obj, dict) else "?"
                    event_t = obj.get("event_type") if isinstance(obj, dict) else "?"
                    warnings.warn(
                        f"Skipping unrecognised event at line {lineno}: "
                        f"schema_version={schema_v!r} event_type={event_t!r} ({exc})",
                        stacklevel=2,
                    )
                    if isinstance(obj, dict):
                        events.append(UnknownDeliveryEvent(raw=obj))
        return events

    # ── In-process pub/sub ────────────────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue[DeliveryEvent]:
        """Register a new async subscriber and return its queue.

        Call :meth:`unsubscribe` with the returned queue when done to avoid
        a memory leak in long-running server processes.
        """
        q: asyncio.Queue[DeliveryEvent] = asyncio.Queue(maxsize=512)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[DeliveryEvent]) -> None:
        """Remove a previously registered subscriber queue."""
        self._subscribers = [s for s in self._subscribers if s is not q]
