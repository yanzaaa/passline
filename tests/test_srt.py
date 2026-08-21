"""SRT round-trip and parsing tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from passline.events.bus import EventBus
from passline.io.srt import parse_srt, write_srt
from passline.models.subtitle import SrtDialect

FIXTURES = Path(__file__).parent / "fixtures"


# ── Parsing correctness ───────────────────────────────────────────────────────

class TestParsing:
    def test_parse_cue_count(self, sample_srt_bytes: bytes) -> None:
        f = parse_srt(sample_srt_bytes)
        assert len(f.cues) == 2

    def test_parse_cue1_index(self, sample_srt_bytes: bytes) -> None:
        cue = parse_srt(sample_srt_bytes).cues[0]
        assert cue.index == 1

    def test_parse_cue1_times(self, sample_srt_bytes: bytes) -> None:
        cue = parse_srt(sample_srt_bytes).cues[0]
        assert cue.start_ms == 1_000
        assert cue.end_ms == 3_500

    def test_parse_cue2_index(self, sample_srt_bytes: bytes) -> None:
        cue = parse_srt(sample_srt_bytes).cues[1]
        assert cue.index == 2

    def test_parse_cue2_times(self, sample_srt_bytes: bytes) -> None:
        cue = parse_srt(sample_srt_bytes).cues[1]
        assert cue.start_ms == 5_000
        assert cue.end_ms == 8_000

    def test_parse_cue1_lines(self, sample_srt_bytes: bytes) -> None:
        cue = parse_srt(sample_srt_bytes).cues[0]
        assert cue.lines == ["Hello, world!"]

    def test_parse_cue2_lines(self, sample_srt_bytes: bytes) -> None:
        cue = parse_srt(sample_srt_bytes).cues[1]
        assert cue.lines == ["This is a subtitle.", "With two lines."]

    def test_parse_language(self, sample_srt_bytes: bytes) -> None:
        f = parse_srt(sample_srt_bytes, language="en-US")
        assert f.language == "en-US"

    def test_parse_source_path(self, sample_srt_bytes: bytes) -> None:
        f = parse_srt(sample_srt_bytes, source_path="/media/en.srt")
        assert f.source_path == "/media/en.srt"


# ── Byte-identical round-trip ─────────────────────────────────────────────────

class TestRoundTrip:
    def test_round_trip_lf(self, sample_srt_bytes: bytes) -> None:
        """LF line endings — byte-identical round-trip."""
        assert b"\r\n" not in sample_srt_bytes, "fixture must use LF only"
        result = write_srt(parse_srt(sample_srt_bytes))
        assert result == sample_srt_bytes

    def test_round_trip_crlf(self, sample_crlf_bytes: bytes) -> None:
        """CRLF line endings — byte-identical round-trip."""
        assert b"\r\n" in sample_crlf_bytes, "fixture must use CRLF"
        result = write_srt(parse_srt(sample_crlf_bytes))
        assert result == sample_crlf_bytes

    def test_round_trip_bom(self, sample_bom_bytes: bytes) -> None:
        """UTF-8 BOM + LF — byte-identical round-trip."""
        assert sample_bom_bytes[:3] == b"\xef\xbb\xbf", "fixture must have BOM"
        result = write_srt(parse_srt(sample_bom_bytes))
        assert result == sample_bom_bytes

    def test_round_trip_dialect_survives_model_copy(
        self, sample_crlf_bytes: bytes
    ) -> None:
        """A model_copy() of a parsed CRLF+BOM file still writes back in CRLF+BOM dialect."""
        # Build a CRLF+BOM fixture in memory
        bom = b"\xef\xbb\xbf"
        crlf_bom_bytes = bom + sample_crlf_bytes
        original = parse_srt(crlf_bom_bytes)
        assert original.srt_dialect is not None
        assert original.srt_dialect.crlf is True
        assert original.srt_dialect.has_bom is True

        # model_copy to simulate a "repaired" version — dialect must carry through
        modified = original.model_copy(
            update={"cues": original.cues}  # same cues, just a copy
        )
        result = write_srt(modified)
        assert result[:3] == bom, "BOM must be preserved in copy"
        assert b"\r\n" in result, "CRLF must be preserved in copy"


# ── Canonicality: canonical files are flagged as such ────────────────────────

class TestCanonical:
    def test_canonical_lf(self, sample_srt_bytes: bytes) -> None:
        f = parse_srt(sample_srt_bytes)
        assert f.is_canonical is True
        assert f.skipped_blocks == 0
        assert f.parse_anomalies == []

    def test_canonical_crlf(self, sample_crlf_bytes: bytes) -> None:
        f = parse_srt(sample_crlf_bytes)
        assert f.is_canonical is True

    def test_canonical_bom(self, sample_bom_bytes: bytes) -> None:
        f = parse_srt(sample_bom_bytes)
        assert f.is_canonical is True


# ── Anomaly detection ─────────────────────────────────────────────────────────

class TestAnomalyDetection:
    def test_bad_timecode_block_skipped(self) -> None:
        """A block with an invalid timecode is skipped; is_canonical is False."""
        data = (FIXTURES / "sample_bad_timecode.srt").read_bytes()
        f = parse_srt(data)
        assert f.is_canonical is False
        assert f.skipped_blocks == 1
        assert len(f.cues) == 1  # only the valid cue survives
        assert any("invalid timecode" in a.lower() for a in f.parse_anomalies)

    def test_single_digit_hours_normalised(self) -> None:
        """Single-digit hours are normalised; is_canonical is False."""
        data = (FIXTURES / "sample_single_digit_hours.srt").read_bytes()
        f = parse_srt(data)
        assert f.is_canonical is False
        assert f.skipped_blocks == 0
        assert len(f.cues) == 1
        assert any("non-canonical timecode" in a.lower() for a in f.parse_anomalies)

    def test_arrow_extra_spaces_normalised(self) -> None:
        """Extra spaces around --> are normalised; is_canonical is False."""
        data = (FIXTURES / "sample_arrow_spaces.srt").read_bytes()
        f = parse_srt(data)
        assert f.is_canonical is False
        assert f.skipped_blocks == 0
        assert any("non-canonical timecode" in a.lower() for a in f.parse_anomalies)

    def test_triple_blank_normalised(self) -> None:
        """Three blank lines between cues are normalised; is_canonical is False."""
        data = (FIXTURES / "sample_triple_blank.srt").read_bytes()
        f = parse_srt(data)
        assert f.is_canonical is False
        assert any("extra blank lines" in a.lower() for a in f.parse_anomalies)
        # Both cues must still parse
        assert len(f.cues) == 2

    def test_mixed_endings_anomaly(self) -> None:
        """Mixed CRLF/LF in the same file is flagged; is_canonical is False."""
        data = (FIXTURES / "sample_mixed_endings.srt").read_bytes()
        f = parse_srt(data)
        assert f.is_canonical is False
        assert any("mixed line endings" in a.lower() for a in f.parse_anomalies)

    def test_submitted_event_includes_skipped_count(
        self, tmp_event_log: EventBus
    ) -> None:
        """subtitle.submitted event details include skipped_blocks count."""
        data = (FIXTURES / "sample_bad_timecode.srt").read_bytes()
        parse_srt(data, delivery_id="test-skip", bus=tmp_event_log)
        event = tmp_event_log.read_all()[0]
        assert event.details["skipped_blocks"] == 1

    def test_submitted_event_is_canonical_false(
        self, tmp_event_log: EventBus
    ) -> None:
        """subtitle.submitted event details include is_canonical=False for anomalous files."""
        data = (FIXTURES / "sample_bad_timecode.srt").read_bytes()
        parse_srt(data, delivery_id="test-canon", bus=tmp_event_log)
        event = tmp_event_log.read_all()[0]
        assert event.details["is_canonical"] is False
