"""SubtitleCue model computed-property tests.

All expected values are hand-computed from the golden fixture:

  Cue 1: "Hello, world!"
    start_ms=1000, end_ms=3500
    duration_ms = 3500 - 1000 = 2500
    total_chars = len("Hello, world!") = 13
    cps = 13 / (2500 / 1000) = 13 / 2.5 = 5.2

  Cue 2: "This is a subtitle." / "With two lines."
    start_ms=5000, end_ms=8000
    duration_ms = 8000 - 5000 = 3000
    char_counts = [len("This is a subtitle."), len("With two lines.")] = [19, 15]
    total_chars = 19 + 15 = 34
    cps = 34 / (3000 / 1000) = 34 / 3.0 ≈ 11.3333...
"""
from __future__ import annotations

import pytest

from passline.io.srt import parse_srt
from passline.models.subtitle import SubtitleCue


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def cue1(sample_srt_bytes: bytes) -> SubtitleCue:
    return parse_srt(sample_srt_bytes).cues[0]


@pytest.fixture
def cue2(sample_srt_bytes: bytes) -> SubtitleCue:
    return parse_srt(sample_srt_bytes).cues[1]


# ── Cue 1 ─────────────────────────────────────────────────────────────────────

class TestCue1:
    def test_duration_ms(self, cue1: SubtitleCue) -> None:
        assert cue1.duration_ms == 2_500

    def test_char_counts(self, cue1: SubtitleCue) -> None:
        assert cue1.char_counts == [13]

    def test_total_chars(self, cue1: SubtitleCue) -> None:
        assert cue1.total_chars == 13

    def test_cps(self, cue1: SubtitleCue) -> None:
        assert cue1.cps == pytest.approx(5.2)


# ── Cue 2 ─────────────────────────────────────────────────────────────────────

class TestCue2:
    def test_duration_ms(self, cue2: SubtitleCue) -> None:
        assert cue2.duration_ms == 3_000

    def test_char_counts(self, cue2: SubtitleCue) -> None:
        assert cue2.char_counts == [19, 15]

    def test_total_chars(self, cue2: SubtitleCue) -> None:
        assert cue2.total_chars == 34

    def test_cps(self, cue2: SubtitleCue) -> None:
        assert cue2.cps == pytest.approx(34 / 3.0)


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_zero_duration_cps(self) -> None:
        """A zero-duration cue must return 0.0, not raise ZeroDivisionError."""
        cue = SubtitleCue(index=1, start_ms=1000, end_ms=1000, lines=["text"])
        assert cue.cps == 0.0

    def test_negative_duration_cps(self) -> None:
        """A cue with end < start (malformed) must also return 0.0."""
        cue = SubtitleCue(index=1, start_ms=2000, end_ms=1000, lines=["text"])
        assert cue.cps == 0.0

    def test_char_counts_strips_trailing_whitespace(self) -> None:
        """Trailing whitespace on a line is not counted."""
        cue = SubtitleCue(index=1, start_ms=0, end_ms=1000, lines=["hi   "])
        assert cue.char_counts == [2]

    def test_char_counts_preserves_leading_whitespace(self) -> None:
        """Leading whitespace IS counted (it is visible to the viewer)."""
        cue = SubtitleCue(index=1, start_ms=0, end_ms=1000, lines=["  hi"])
        assert cue.char_counts == [4]

    def test_multiline_total_chars(self) -> None:
        cue = SubtitleCue(index=1, start_ms=0, end_ms=2000, lines=["abc", "de"])
        assert cue.total_chars == 5

    def test_immutability(self) -> None:
        """SubtitleCue is frozen — field assignment must raise."""
        cue = SubtitleCue(index=1, start_ms=0, end_ms=1000, lines=["x"])
        with pytest.raises(Exception):
            cue.index = 2  # type: ignore[misc]
