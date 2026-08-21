"""SubtitleCue model computed-property tests.

All expected values are hand-computed from the golden fixture:

  Cue 1: "Hello, world!"
    start_ms=1000, end_ms=3500
    duration_ms = 3500 - 1000 = 2500
    total_chars = len("Hello, world!") = 13  (no markup)
    cps = 13 / (2500 / 1000) = 13 / 2.5 = 5.2

  Cue 2: "This is a subtitle." / "With two lines."
    start_ms=5000, end_ms=8000
    duration_ms = 8000 - 5000 = 3000
    char_counts = [len("This is a subtitle."), len("With two lines.")] = [19, 15]
    total_chars = 19 + 15 = 34
    cps = 34 / (3000 / 1000) = 34 / 3.0 ≈ 11.3333...

Markup-stripping values (computed by hand):
  "<i>Hello</i>"                        → visible "Hello"            → 5 chars
  "<b><i>Hi</i></b>"                    → visible "Hi"               → 2 chars
  '<font color="red">Subtitle here!</font>' → visible "Subtitle here!" → 14 chars
  "<i>" + "x"*43 + "</i>"              → raw 49, visible 43
  '<font color="#ffffff">' + "a"*38 + '</font>' → raw 60, visible 38
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


# ── Markup stripping ──────────────────────────────────────────────────────────

class TestMarkupStripping:
    def test_markup_italic_stripped(self) -> None:
        """<i>...</i> tags are excluded; visible text is counted.
        "<i>Hello</i>" → visible "Hello" → 5 chars
        """
        cue = SubtitleCue(index=1, start_ms=0, end_ms=2000, lines=["<i>Hello</i>"])
        assert cue.char_counts == [5]

    def test_markup_nested_stripped(self) -> None:
        """Nested <b><i>...</i></b> → visible text only.
        "<b><i>Hi</i></b>" → "Hi" → 2 chars
        """
        cue = SubtitleCue(index=1, start_ms=0, end_ms=2000, lines=["<b><i>Hi</i></b>"])
        assert cue.char_counts == [2]

    def test_markup_font_tag_stripped(self) -> None:
        """<font color="..."> tag is stripped; visible text counted.
        '<font color="red">Subtitle here!</font>' → "Subtitle here!" → 14 chars
        """
        cue = SubtitleCue(
            index=1, start_ms=0, end_ms=2000,
            lines=['<font color="red">Subtitle here!</font>']
        )
        assert cue.char_counts == [14]

    def test_markup_raw_over_42_visible_under(self) -> None:
        """Raw length > 42 due to markup; visible length < 42 — char_count is visible.
        '<font color="#ffffff">' (22) + 'a'*18 (18) + '</font>' (7) = raw 47
        visible = 18 chars (under 42)
        """
        line = '<font color="#ffffff">' + "a" * 18 + "</font>"
        assert len(line) == 47  # sanity-check the raw length
        cue = SubtitleCue(index=1, start_ms=0, end_ms=2000, lines=[line])
        assert cue.char_counts == [18]
        assert cue.char_counts[0] < 42

    def test_markup_raw_over_42_visible_also_over(self) -> None:
        """Raw length > 42 AND visible length > 42 after stripping markup.
        '<i>' (3) + 'x'*43 (43) + '</i>' (4) = raw 50, visible 43 (still > 42)
        """
        line = "<i>" + "x" * 43 + "</i>"
        assert len(line) == 50
        cue = SubtitleCue(index=1, start_ms=0, end_ms=2000, lines=[line])
        assert cue.char_counts == [43]
        assert cue.char_counts[0] > 42

    def test_markup_lines_field_intact(self) -> None:
        """The raw lines field with markup is never modified."""
        raw = "<b>Important</b>"
        cue = SubtitleCue(index=1, start_ms=0, end_ms=2000, lines=[raw])
        assert cue.lines[0] == raw  # markup preserved in storage
        assert cue.char_counts == [9]  # only "Important" counted
