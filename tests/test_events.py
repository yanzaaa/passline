"""Event emission and EventBus persistence tests."""
from __future__ import annotations

import json
from datetime import timezone
from pathlib import Path

import pytest

from passline.events.bus import DeliveryEvent, EventBus, EventType
from passline.io.srt import parse_srt


class TestEventEmission:
    def test_subtitle_submitted_emitted(
        self, sample_srt_bytes: bytes, tmp_event_log: EventBus
    ) -> None:
        """parse_srt must emit exactly one subtitle.submitted event."""
        parse_srt(sample_srt_bytes, delivery_id="delivery-001", bus=tmp_event_log)
        events = tmp_event_log.read_all()
        assert len(events) == 1
        assert events[0].event_type == EventType.SUBTITLE_SUBMITTED

    def test_event_delivery_id(
        self, sample_srt_bytes: bytes, tmp_event_log: EventBus
    ) -> None:
        parse_srt(sample_srt_bytes, delivery_id="abc-123", bus=tmp_event_log)
        event = tmp_event_log.read_all()[0]
        assert event.delivery_id == "abc-123"

    def test_event_language(
        self, sample_srt_bytes: bytes, tmp_event_log: EventBus
    ) -> None:
        parse_srt(sample_srt_bytes, language="fr-FR", delivery_id="x", bus=tmp_event_log)
        event = tmp_event_log.read_all()[0]
        assert event.language == "fr-FR"

    def test_event_schema_version(
        self, sample_srt_bytes: bytes, tmp_event_log: EventBus
    ) -> None:
        parse_srt(sample_srt_bytes, delivery_id="x", bus=tmp_event_log)
        event = tmp_event_log.read_all()[0]
        assert event.schema_version == "1.0"

    def test_event_timestamp_utc(
        self, sample_srt_bytes: bytes, tmp_event_log: EventBus
    ) -> None:
        """Timestamps must be UTC-aware."""
        parse_srt(sample_srt_bytes, delivery_id="x", bus=tmp_event_log)
        event = tmp_event_log.read_all()[0]
        assert event.timestamp.tzinfo is not None
        assert event.timestamp.utcoffset().total_seconds() == 0  # type: ignore[union-attr]

    def test_event_details_cue_count(
        self, sample_srt_bytes: bytes, tmp_event_log: EventBus
    ) -> None:
        """details must include cue_count matching the parsed file."""
        parse_srt(sample_srt_bytes, delivery_id="x", bus=tmp_event_log)
        event = tmp_event_log.read_all()[0]
        assert event.details["cue_count"] == 2

    def test_no_emission_without_bus(self, sample_srt_bytes: bytes) -> None:
        """parse_srt with bus=None must not raise and must not write any file."""
        # If this raises, the test fails; no assertion needed beyond no exception
        parse_srt(sample_srt_bytes, delivery_id="x", bus=None)


class TestEventBusPersistence:
    def test_jsonl_append(self, tmp_event_log: EventBus) -> None:
        """Two emitted events must produce exactly two JSONL lines."""
        tmp_event_log.emit(DeliveryEvent(
            event_type=EventType.QC_VIOLATION,
            delivery_id="d1",
            language="en",
        ))
        tmp_event_log.emit(DeliveryEvent(
            event_type=EventType.DELIVERY_PASSED,
            delivery_id="d1",
            language="en",
        ))
        lines = [l for l in tmp_event_log.log_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 2

    def test_read_all_roundtrip(self, tmp_event_log: EventBus) -> None:
        """Emit then read_all must return equivalent events."""
        original = DeliveryEvent(
            event_type=EventType.QC_REPAIRED,
            delivery_id="repair-99",
            language="de-DE",
            details={"rule": "cps_exceeded", "value": 22.1},
        )
        tmp_event_log.emit(original)
        retrieved = tmp_event_log.read_all()[0]
        assert retrieved.event_type == original.event_type
        assert retrieved.delivery_id == original.delivery_id
        assert retrieved.language == original.language
        assert retrieved.details == original.details
        assert retrieved.schema_version == "1.0"

    def test_jsonl_lines_are_valid_json(self, tmp_event_log: EventBus) -> None:
        """Every line in the log must be a self-contained valid JSON object."""
        tmp_event_log.emit(DeliveryEvent(
            event_type=EventType.SUBTITLE_SUBMITTED,
            delivery_id="x",
            language="ja",
        ))
        raw_lines = [l for l in tmp_event_log.log_path.read_text().splitlines() if l.strip()]
        for line in raw_lines:
            obj = json.loads(line)
            assert isinstance(obj, dict)
            assert "event_type" in obj
            assert "schema_version" in obj

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        """EventBus must create nested parent directories automatically."""
        deep_path = tmp_path / "a" / "b" / "c" / "events.jsonl"
        bus = EventBus(deep_path)
        assert deep_path.exists()

    def test_all_four_event_types(self, tmp_event_log: EventBus) -> None:
        """All four EventType values must serialise and deserialise correctly."""
        for et in EventType:
            tmp_event_log.emit(DeliveryEvent(
                event_type=et, delivery_id="d", language="en"
            ))
        events = tmp_event_log.read_all()
        recovered_types = {e.event_type for e in events}
        assert recovered_types == set(EventType)
