"""Delivery event bus for Passline.

Events are appended to a local JSONL log file. The schema is versioned and
designed to feed a live dashboard and a Kafka topic.

Schema version 1.0
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventType(str, Enum):
    """Delivery pipeline event types."""

    SUBTITLE_SUBMITTED = "subtitle.submitted"
    QC_VIOLATION = "qc.violation"
    QC_REPAIRED = "qc.repaired"
    DELIVERY_PASSED = "delivery.passed"


class DeliveryEvent(BaseModel):
    """A single versioned delivery pipeline event."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    event_type: EventType
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    delivery_id: str
    language: str
    details: dict[str, Any] = Field(default_factory=dict)

    def serialise(self) -> str:
        """Return a single JSON line (no trailing newline) for JSONL output."""
        # Serialise timestamp as ISO-8601 with Z suffix for Kafka compatibility
        data = self.model_dump()
        data["timestamp"] = self.timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        data["event_type"] = self.event_type.value
        return json.dumps(data, ensure_ascii=False)


class EventBus:
    """Appends DeliveryEvent records to a JSONL log file."""

    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.touch()

    def emit(self, event: DeliveryEvent) -> None:
        """Append one event as a JSON line to the log file."""
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(event.serialise() + "\n")

    def read_all(self) -> list[DeliveryEvent]:
        """Read and parse all events from the log file."""
        events: list[DeliveryEvent] = []
        with self.log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    events.append(DeliveryEvent.model_validate(json.loads(line)))
        return events
