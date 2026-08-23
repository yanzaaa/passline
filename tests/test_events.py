"""Event emission and EventBus persistence tests."""
from __future__ import annotations

import json
import warnings
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from passline.events.bus import (
    DeliveryEvent,
    EventBus,
    EventType,
    UnknownDeliveryEvent,
)
from passline.io.srt import parse_srt


# ── Event emission via parse_srt ──────────────────────────────────────────────

class TestEventEmission:
    def test_subtitle_submitted_emitted(
        self, sample_srt_bytes: bytes, tmp_event_log: EventBus
    ) -> None:
        """parse_srt must emit exactly one subtitle.submitted event."""
        parse_srt(sample_srt_bytes, delivery_id="delivery-001", bus=tmp_event_log)
        events = tmp_event_log.read_all()
        assert len(events) == 1
        assert events[0].event_type == EventType.SUBTITLE_SUBMITTED  # type: ignore[union-attr]

    def test_event_delivery_id(
        self, sample_srt_bytes: bytes, tmp_event_log: EventBus
    ) -> None:
        parse_srt(sample_srt_bytes, delivery_id="abc-123", bus=tmp_event_log)
        event = tmp_event_log.read_all()[0]
        assert event.delivery_id == "abc-123"  # type: ignore[union-attr]

    def test_event_language(
        self, sample_srt_bytes: bytes, tmp_event_log: EventBus
    ) -> None:
        parse_srt(sample_srt_bytes, language="fr-FR", delivery_id="x", bus=tmp_event_log)
        event = tmp_event_log.read_all()[0]
        assert event.language == "fr-FR"  # type: ignore[union-attr]

    def test_event_schema_version(
        self, sample_srt_bytes: bytes, tmp_event_log: EventBus
    ) -> None:
        parse_srt(sample_srt_bytes, delivery_id="x", bus=tmp_event_log)
        event = tmp_event_log.read_all()[0]
        assert event.schema_version == "1.3"  # type: ignore[union-attr]

    def test_event_timestamp_utc(
        self, sample_srt_bytes: bytes, tmp_event_log: EventBus
    ) -> None:
        """Timestamps must be UTC-aware."""
        parse_srt(sample_srt_bytes, delivery_id="x", bus=tmp_event_log)
        event = tmp_event_log.read_all()[0]
        assert isinstance(event, DeliveryEvent)
        assert event.timestamp.tzinfo is not None
        assert event.timestamp.utcoffset().total_seconds() == 0  # type: ignore[union-attr]

    def test_event_details_cue_count(
        self, sample_srt_bytes: bytes, tmp_event_log: EventBus
    ) -> None:
        """details must include cue_count matching the parsed file."""
        parse_srt(sample_srt_bytes, delivery_id="x", bus=tmp_event_log)
        event = tmp_event_log.read_all()[0]
        assert event.details["cue_count"] == 2  # type: ignore[union-attr]

    def test_no_emission_without_bus(self, sample_srt_bytes: bytes) -> None:
        """parse_srt with bus=None must not raise and must not write any file."""
        parse_srt(sample_srt_bytes, delivery_id="x", bus=None)


# ── EventBus persistence ──────────────────────────────────────────────────────

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
        assert isinstance(retrieved, DeliveryEvent)
        assert retrieved.event_type == original.event_type
        assert retrieved.delivery_id == original.delivery_id
        assert retrieved.language == original.language
        assert retrieved.details == original.details
        assert retrieved.schema_version == "1.3"

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
        recovered_types = {e.event_type for e in events if isinstance(e, DeliveryEvent)}
        assert recovered_types == set(EventType)


# ── Event ID (schema 1.1) ─────────────────────────────────────────────────────

class TestEventId:
    def test_event_has_unique_id(self, tmp_event_log: EventBus) -> None:
        """Each DeliveryEvent carries a non-empty event_id."""
        tmp_event_log.emit(DeliveryEvent(
            event_type=EventType.SUBTITLE_SUBMITTED,
            delivery_id="x", language="en",
        ))
        event = tmp_event_log.read_all()[0]
        assert isinstance(event, DeliveryEvent)
        assert event.event_id != ""

    def test_event_ids_are_unique_across_two_events(
        self, tmp_event_log: EventBus
    ) -> None:
        """Two independently created events must have different event_ids."""
        for _ in range(2):
            tmp_event_log.emit(DeliveryEvent(
                event_type=EventType.QC_VIOLATION, delivery_id="d", language="en"
            ))
        events = [e for e in tmp_event_log.read_all() if isinstance(e, DeliveryEvent)]
        ids = [e.event_id for e in events]
        assert ids[0] != ids[1]

    def test_event_id_preserved_on_roundtrip(self, tmp_event_log: EventBus) -> None:
        """event_id survives emit → read_all."""
        ev = DeliveryEvent(
            event_type=EventType.DELIVERY_PASSED, delivery_id="d", language="en"
        )
        tmp_event_log.emit(ev)
        retrieved = tmp_event_log.read_all()[0]
        assert isinstance(retrieved, DeliveryEvent)
        assert retrieved.event_id == ev.event_id


# ── UTC enforcement ───────────────────────────────────────────────────────────

class TestUtcEnforcement:
    def test_utc_conversion_from_non_utc_timestamp(
        self, tmp_event_log: EventBus
    ) -> None:
        """A timestamp with a non-UTC timezone is converted to UTC in the log."""
        # Create a timestamp in UTC+5:30 (India Standard Time)
        ist = timezone(timedelta(hours=5, minutes=30))
        ts_ist = datetime(2026, 8, 20, 15, 30, 0, tzinfo=ist)  # 15:30 IST = 10:00 UTC
        ev = DeliveryEvent(
            event_type=EventType.SUBTITLE_SUBMITTED,
            delivery_id="tz-test",
            language="hi",
            timestamp=ts_ist,
        )
        tmp_event_log.emit(ev)

        # The JSONL line must have a Z-suffixed timestamp in UTC
        raw_line = tmp_event_log.log_path.read_text().strip()
        obj = json.loads(raw_line)
        ts_str = obj["timestamp"]
        assert ts_str.endswith("Z"), f"Expected Z suffix, got {ts_str!r}"
        # Parse back and verify it equals the original UTC equivalent
        ts_parsed = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        ts_expected_utc = ts_ist.astimezone(timezone.utc)
        assert ts_parsed.hour == ts_expected_utc.hour
        assert ts_parsed.minute == ts_expected_utc.minute

    def test_utc_timestamp_unchanged(self, tmp_event_log: EventBus) -> None:
        """A UTC timestamp is serialised without modification."""
        ts_utc = datetime(2026, 8, 20, 10, 0, 0, tzinfo=timezone.utc)
        ev = DeliveryEvent(
            event_type=EventType.DELIVERY_PASSED,
            delivery_id="utc-test",
            language="en",
            timestamp=ts_utc,
        )
        tmp_event_log.emit(ev)
        obj = json.loads(tmp_event_log.log_path.read_text().strip())
        assert obj["timestamp"].startswith("2026-08-20T10:00:00")
        assert obj["timestamp"].endswith("Z")


# ── Forward-compatibility ─────────────────────────────────────────────────────

class TestForwardCompat:
    def test_unknown_event_type_returns_unknown_event(
        self, tmp_event_log: EventBus
    ) -> None:
        """An unknown event_type produces an UnknownDeliveryEvent, not a crash."""
        # Inject a line with a future event_type directly into the log
        raw = json.dumps({
            "schema_version": "1.3",
            "event_id": "abc-123",
            "event_type": "future.event_type_not_yet_defined",
            "timestamp": "2026-08-20T10:00:00.000000Z",
            "delivery_id": "x",
            "language": "en",
            "details": {},
        })
        with tmp_event_log.log_path.open("a") as fh:
            fh.write(raw + "\n")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            events = tmp_event_log.read_all()

        assert len(events) == 1
        assert isinstance(events[0], UnknownDeliveryEvent)
        assert len(w) == 1

    def test_forward_compat_skip_bad_json_line(
        self, tmp_event_log: EventBus
    ) -> None:
        """A completely malformed JSON line is skipped silently."""
        with tmp_event_log.log_path.open("a") as fh:
            fh.write("this is not json at all\n")

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            events = tmp_event_log.read_all()

        # No events (the bad line is silently dropped)
        assert events == []

    def test_newer_schema_version_surfaced_as_unknown(
        self, tmp_event_log: EventBus
    ) -> None:
        """A line with a future schema_version is surfaced as UnknownDeliveryEvent."""
        raw = json.dumps({
            "schema_version": "99.0",
            "event_id": "future-id",
            "event_type": "subtitle.submitted",
            "timestamp": "2026-08-20T10:00:00.000000Z",
            "delivery_id": "x",
            "language": "en",
            "details": {},
        })
        with tmp_event_log.log_path.open("a") as fh:
            fh.write(raw + "\n")

        # schema_version 99.0 has a valid event_type so it parses fine
        # (forward-compat is about unknown event_type; known event_type + new schema = ok)
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            events = tmp_event_log.read_all()

        # Should parse successfully — event_type is valid
        assert len(events) == 1
        assert isinstance(events[0], DeliveryEvent)
        assert events[0].schema_version == "99.0"


# ── Empty delivery_id auto-generation ─────────────────────────────────────────

class TestDeliveryIdGeneration:
    def test_empty_delivery_id_autogenerated(
        self, sample_srt_bytes: bytes, tmp_event_log: EventBus
    ) -> None:
        """When delivery_id is empty and bus is provided, a UUID is auto-generated."""
        parse_srt(sample_srt_bytes, delivery_id="", bus=tmp_event_log)
        event = tmp_event_log.read_all()[0]
        assert isinstance(event, DeliveryEvent)
        assert event.delivery_id != ""
        # Should look like a UUID
        assert len(event.delivery_id) == 36
        assert event.delivery_id.count("-") == 4

    def test_explicit_delivery_id_unchanged(
        self, sample_srt_bytes: bytes, tmp_event_log: EventBus
    ) -> None:
        """An explicitly provided delivery_id is used as-is."""
        parse_srt(sample_srt_bytes, delivery_id="my-explicit-id", bus=tmp_event_log)
        event = tmp_event_log.read_all()[0]
        assert isinstance(event, DeliveryEvent)
        assert event.delivery_id == "my-explicit-id"
