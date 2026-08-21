"""SRT round-trip and parsing tests."""
from __future__ import annotations

import pytest

from passline.io.srt import parse_srt, write_srt


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
