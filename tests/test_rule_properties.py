"""Property-based tests for the Passline rule engine.

Random cue generators with deterministic seeds prove that CPS, duration, and
line-length calculations are consistent between the SubtitleCue model and the
rule engine under edge cases including unicode, empty lines, and zero duration.

No external property-testing library is required — we use random.Random with
fixed seeds for reproducibility.
"""
from __future__ import annotations

import math
import random as _random
import unicodedata
from typing import Iterator

import pytest

from passline.models.subtitle import SubtitleCue
from passline.qc.rules import Finding, check_file
from passline.qc.thresholds import (
    CPS_VIOLATION,
    CPS_WARNING_LOW,
    LINE_CHAR_MAX,
    MAX_LINES_PER_CUE,
    MIN_DURATION_MS,
)
from passline.models.subtitle import SubtitleFile, SrtDialect


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_file(cues: list[SubtitleCue]) -> SubtitleFile:
    return SubtitleFile(
        cues=cues,
        language="en",
        srt_dialect=SrtDialect(),
    )


def _file_findings(cues: list[SubtitleCue]) -> list[Finding]:
    return check_file(_make_file(cues))


def _findings_for(cue: SubtitleCue) -> list[Finding]:
    return _file_findings([cue])


def _make_cue(
    *,
    index: int = 1,
    start_ms: int = 0,
    end_ms: int = 3000,
    lines: list[str] | None = None,
) -> SubtitleCue:
    if lines is None:
        lines = ["Sample subtitle text"]
    return SubtitleCue(index=index, start_ms=start_ms, end_ms=end_ms, lines=lines)


def _random_ascii_line(rng: _random.Random, length: int) -> str:
    chars = "abcdefghijklmnopqrstuvwxyz ABCDE,.!?"
    return "".join(rng.choice(chars) for _ in range(length))


def _random_unicode_line(rng: _random.Random, char_count: int) -> str:
    """Build a string with *char_count* Unicode characters (Latin + CJK mix)."""
    pool = (
        list("abcdefghijklmnopqrstuvwxyz ") +
        [chr(0x4E00 + i) for i in range(50)] +   # CJK unified ideographs
        [chr(0x00E0 + i) for i in range(30)] +   # Latin extended
        [chr(0x03B1 + i) for i in range(20)]     # Greek lowercase
    )
    return "".join(rng.choice(pool) for _ in range(char_count))


# ─────────────────────────────────────────────────────────────────────────────
# Group 1 — CPS property tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCPSProperties:
    """Every CPS finding correctly reflects the cue model's computed .cps property."""

    def test_cps_violation_exactly_matches_model(self) -> None:
        """When cue.cps > CPS_VIOLATION, rule engine fires cps_exceeded ERROR."""
        rng = _random.Random(101)
        n_tested = n_correct = 0
        for _ in range(500):
            chars = rng.randint(10, 60)
            # Choose duration to be just below the CPS_VIOLATION threshold
            # target_cps = CPS_VIOLATION + rng.uniform(0.5, 10)
            target_cps = CPS_VIOLATION + rng.uniform(0.5, 15.0)
            duration_ms = int(chars / target_cps * 1000)
            if duration_ms <= 0:
                continue
            cue = _make_cue(start_ms=0, end_ms=duration_ms, lines=["x" * chars])
            # Model's own property
            model_cps = cue.cps
            n_tested += 1

            findings = _findings_for(cue)
            rule_ids = {f.rule for f in findings}

            if model_cps > CPS_VIOLATION:
                assert "cps_exceeded" in rule_ids, (
                    f"cps={model_cps:.4f} > {CPS_VIOLATION} but cps_exceeded not fired"
                )
                assert "cps_warning" not in rule_ids, "both cps rules fired — only one should"
                # Measured value in Finding must equal model CPS
                cps_finding = next(f for f in findings if f.rule == "cps_exceeded")
                assert abs(cps_finding.measured_value - model_cps) < 1e-6
                n_correct += 1
        assert n_tested > 100, f"Too few test cases: {n_tested}"
        assert n_correct == n_tested

    def test_cps_warning_band_exactly_matches_model(self) -> None:
        """CPS in [CPS_WARNING_LOW, CPS_VIOLATION] fires cps_warning WARNING only."""
        rng = _random.Random(102)
        n_in_band = n_correct = 0
        for _ in range(1000):
            chars = rng.randint(10, 80)
            target_cps = rng.uniform(CPS_WARNING_LOW, CPS_VIOLATION)
            duration_ms = int(chars / target_cps * 1000)
            if duration_ms <= 0:
                continue
            cue = _make_cue(start_ms=0, end_ms=duration_ms, lines=["x" * chars])
            model_cps = cue.cps
            if not (CPS_WARNING_LOW <= model_cps <= CPS_VIOLATION):
                continue  # rounding pushed it out of band
            n_in_band += 1
            findings = _findings_for(cue)
            rule_ids = {f.rule for f in findings}
            assert "cps_warning" in rule_ids, (
                f"cps={model_cps:.4f} in warning band but cps_warning not fired"
            )
            assert "cps_exceeded" not in rule_ids, (
                f"cps={model_cps:.4f} is in warning band but ERROR fired"
            )
            n_correct += 1
        assert n_in_band >= 50, f"Too few in-band cases: {n_in_band}"
        assert n_correct == n_in_band

    def test_safe_cps_no_cps_finding(self) -> None:
        """CPS well below WARNING_LOW fires no CPS finding."""
        rng = _random.Random(103)
        for _ in range(300):
            chars = rng.randint(5, 30)
            duration_ms = rng.randint(5000, 15000)  # very long → very low CPS
            cue = _make_cue(start_ms=0, end_ms=duration_ms, lines=["x" * chars])
            assert cue.cps < CPS_WARNING_LOW
            findings = _findings_for(cue)
            cps_rules = {f.rule for f in findings if f.rule.startswith("cps")}
            assert not cps_rules, (
                f"cps={cue.cps:.4f} < {CPS_WARNING_LOW} but CPS finding fired: {cps_rules}"
            )

    def test_zero_duration_no_cps_finding(self) -> None:
        """Zero duration → cue.cps == 0.0 → no CPS finding (malformed_timecode fires instead)."""
        cue = _make_cue(start_ms=1000, end_ms=1000, lines=["Hello world"])
        assert cue.cps == 0.0  # model property guard
        findings = _findings_for(cue)
        cps_rules = [f for f in findings if f.rule.startswith("cps")]
        assert not cps_rules, f"Zero-duration cue fired CPS rule: {cps_rules}"
        timecode_rules = [f for f in findings if f.rule == "malformed_timecode"]
        assert timecode_rules, "Zero-duration cue should fire malformed_timecode"

    def test_negative_duration_no_cps_finding(self) -> None:
        """Negative duration (end < start) → cue.cps == 0.0 → no CPS finding."""
        cue = _make_cue(start_ms=5000, end_ms=3000, lines=["Hello world"])
        assert cue.cps == 0.0
        findings = _findings_for(cue)
        cps_rules = [f for f in findings if f.rule.startswith("cps")]
        assert not cps_rules


# ─────────────────────────────────────────────────────────────────────────────
# Group 2 — Line length property tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLineLengthProperties:
    """line_too_long fires iff SubtitleCue.char_counts has an entry > LINE_CHAR_MAX."""

    def test_line_too_long_boundary(self) -> None:
        """Exactly LINE_CHAR_MAX chars → no finding. LINE_CHAR_MAX+1 → ERROR."""
        at_limit = _make_cue(lines=["x" * LINE_CHAR_MAX])
        over_limit = _make_cue(lines=["x" * (LINE_CHAR_MAX + 1)])

        assert not any(f.rule == "line_too_long" for f in _findings_for(at_limit)), (
            f"Exactly {LINE_CHAR_MAX} chars should not fire line_too_long"
        )
        over_findings = [f for f in _findings_for(over_limit) if f.rule == "line_too_long"]
        assert over_findings, f"{LINE_CHAR_MAX + 1} chars must fire line_too_long"
        assert over_findings[0].severity == "ERROR"
        assert over_findings[0].measured_value == LINE_CHAR_MAX + 1

    def test_random_line_lengths_consistent(self) -> None:
        """For 500 random line lengths, line_too_long fires iff char_count > LINE_CHAR_MAX."""
        rng = _random.Random(201)
        for _ in range(500):
            length = rng.randint(0, 90)
            cue = _make_cue(lines=["a" * length])
            model_count = cue.char_counts[0]
            assert model_count == length  # no markup, no trailing space

            findings = [f for f in _findings_for(cue) if f.rule == "line_too_long"]
            if model_count > LINE_CHAR_MAX:
                assert findings, f"length={length} > {LINE_CHAR_MAX} but line_too_long not fired"
                assert findings[0].measured_value == float(model_count)
            else:
                assert not findings, (
                    f"length={length} <= {LINE_CHAR_MAX} but line_too_long fired"
                )

    def test_unicode_chars_counted_correctly(self) -> None:
        """Unicode characters count as their character count, not byte count."""
        rng = _random.Random(202)
        for _ in range(200):
            char_count = rng.randint(30, 60)
            line = _random_unicode_line(rng, char_count)
            # Sanity: Python len() counts characters, not bytes
            assert len(line) == char_count

            cue = _make_cue(lines=[line])
            # Model uses len() via _strip_markup + .rstrip() — same as len()
            # (no markup, no trailing whitespace in our test lines)
            assert cue.char_counts[0] == char_count

            findings = [f for f in _findings_for(cue) if f.rule == "line_too_long"]
            if char_count > LINE_CHAR_MAX:
                assert findings, (
                    f"unicode line with {char_count} chars should fire line_too_long"
                )
            else:
                assert not findings

    def test_markup_stripped_before_counting(self) -> None:
        """Markup tags are stripped before char counting."""
        from passline.models.subtitle import _strip_markup

        visible = "x" * LINE_CHAR_MAX  # exactly at limit
        tagged = f"<i>{visible}</i>"    # raw length > limit but visible == limit

        cue_tagged = _make_cue(lines=[tagged])
        cue_plain  = _make_cue(lines=[visible])

        # Model uses _strip_markup — tagged and plain must produce same char_count
        assert cue_tagged.char_counts[0] == cue_plain.char_counts[0] == LINE_CHAR_MAX

        # Neither should fire line_too_long
        assert not any(f.rule == "line_too_long" for f in _findings_for(cue_tagged))
        assert not any(f.rule == "line_too_long" for f in _findings_for(cue_plain))

        # One char over: tagged raw length is much more but visible is what counts
        over_visible = "x" * (LINE_CHAR_MAX + 1)
        over_tagged = f"<b>{over_visible}</b>"
        cue_over = _make_cue(lines=[over_tagged])
        assert cue_over.char_counts[0] == LINE_CHAR_MAX + 1
        assert any(f.rule == "line_too_long" for f in _findings_for(cue_over))

    def test_empty_line_no_finding(self) -> None:
        """Empty string line: char_count == 0, no line_too_long."""
        cue = _make_cue(lines=[""])
        assert cue.char_counts == [0]
        assert not any(f.rule == "line_too_long" for f in _findings_for(cue))

    def test_trailing_whitespace_stripped(self) -> None:
        """Trailing whitespace does not inflate line length."""
        # Visible 42 chars + 10 trailing spaces = raw 52 but visible 42
        line = "x" * LINE_CHAR_MAX + "   "
        cue = _make_cue(lines=[line])
        assert cue.char_counts[0] == LINE_CHAR_MAX
        assert not any(f.rule == "line_too_long" for f in _findings_for(cue))


# ─────────────────────────────────────────────────────────────────────────────
# Group 3 — Duration property tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDurationProperties:
    """sub_one_second fires iff SubtitleCue.duration_ms < MIN_DURATION_MS."""

    def test_duration_boundary(self) -> None:
        """Exactly MIN_DURATION_MS → no finding. MIN_DURATION_MS-1 → ERROR."""
        at = _make_cue(start_ms=0, end_ms=MIN_DURATION_MS)
        under = _make_cue(start_ms=0, end_ms=MIN_DURATION_MS - 1)

        assert not any(f.rule == "sub_one_second" for f in _findings_for(at)), (
            f"duration={MIN_DURATION_MS}ms at threshold should not fire"
        )
        under_findings = [f for f in _findings_for(under) if f.rule == "sub_one_second"]
        assert under_findings, f"{MIN_DURATION_MS-1}ms must fire sub_one_second"
        assert under_findings[0].severity == "ERROR"
        assert under_findings[0].measured_value == MIN_DURATION_MS - 1

    def test_random_durations_consistent(self) -> None:
        """For 500 random durations, sub_one_second fires iff duration_ms < MIN_DURATION_MS."""
        rng = _random.Random(301)
        for _ in range(500):
            duration = rng.randint(100, 5000)
            cue = _make_cue(start_ms=0, end_ms=duration)
            model_dur = cue.duration_ms
            assert model_dur == duration

            findings = [f for f in _findings_for(cue) if f.rule == "sub_one_second"]
            if model_dur < MIN_DURATION_MS:
                assert findings, f"duration={duration}ms should fire sub_one_second"
                assert findings[0].measured_value == float(duration)
            else:
                assert not findings, f"duration={duration}ms should not fire sub_one_second"

    def test_malformed_timecode_negative_duration(self) -> None:
        """end_ms < start_ms fires malformed_timecode, not sub_one_second or cps."""
        cue = _make_cue(start_ms=5000, end_ms=3000)
        assert cue.duration_ms < 0
        findings = _findings_for(cue)
        rules = {f.rule for f in findings}
        assert "malformed_timecode" in rules
        assert "sub_one_second" not in rules
        assert "cps_exceeded" not in rules
        assert "cps_warning" not in rules


# ─────────────────────────────────────────────────────────────────────────────
# Group 4 — Three-line cue property tests
# ─────────────────────────────────────────────────────────────────────────────

class TestThreeLineCueProperties:
    """three_line_cue fires iff len(cue.lines) > MAX_LINES_PER_CUE."""

    @pytest.mark.parametrize("n_lines", [1, 2, 3, 4, 5])
    def test_line_count_rule_boundary(self, n_lines: int) -> None:
        lines = [f"Line {i+1}" for i in range(n_lines)]
        cue = _make_cue(lines=lines)
        findings = [f for f in _findings_for(cue) if f.rule == "three_line_cue"]
        if n_lines > MAX_LINES_PER_CUE:
            assert findings, f"{n_lines} lines must fire three_line_cue"
            assert findings[0].severity == "WARNING"
            assert findings[0].measured_value == float(n_lines)
        else:
            assert not findings, f"{n_lines} lines must not fire three_line_cue"


# ─────────────────────────────────────────────────────────────────────────────
# Group 5 — Overlap property tests
# ─────────────────────────────────────────────────────────────────────────────

class TestOverlapProperties:
    def test_non_overlapping_cues_no_finding(self) -> None:
        """Adjacent cues with a gap produce no overlap finding."""
        cue_a = SubtitleCue(index=1, start_ms=0,    end_ms=2000, lines=["A"])
        cue_b = SubtitleCue(index=2, start_ms=2500, end_ms=5000, lines=["B"])
        findings = _file_findings([cue_a, cue_b])
        assert not any(f.rule == "overlapping_cues" for f in findings)

    def test_touching_cues_no_overlap_finding(self) -> None:
        """Cues that touch (end == next start) are not overlapping."""
        cue_a = SubtitleCue(index=1, start_ms=0,    end_ms=2000, lines=["A"])
        cue_b = SubtitleCue(index=2, start_ms=2000, end_ms=4000, lines=["B"])
        findings = _file_findings([cue_a, cue_b])
        assert not any(f.rule == "overlapping_cues" for f in findings)

    def test_overlapping_cues_fire_error(self) -> None:
        """Cue i end_ms > cue i+1 start_ms fires overlapping_cues ERROR."""
        overlap_ms = 300
        cue_a = SubtitleCue(index=1, start_ms=0,    end_ms=2300,  lines=["A"])
        cue_b = SubtitleCue(index=2, start_ms=2000, end_ms=4000,  lines=["B"])
        assert cue_a.end_ms > cue_b.start_ms
        findings = _file_findings([cue_a, cue_b])
        overlap_findings = [f for f in findings if f.rule == "overlapping_cues"]
        assert overlap_findings
        assert overlap_findings[0].severity == "ERROR"
        assert overlap_findings[0].cue_index == 1  # the cue whose end overlaps
        assert overlap_findings[0].measured_value == float(overlap_ms)

    def test_random_timing_pairs_consistent(self) -> None:
        """500 random cue pairs: overlap fires iff end_ms > next start_ms."""
        rng = _random.Random(401)
        for _ in range(500):
            start_a = rng.randint(0, 100_000)
            end_a   = start_a + rng.randint(500, 5000)
            start_b = start_a + rng.randint(0, 6000)  # may be before or after end_a
            end_b   = start_b + rng.randint(500, 5000)
            cue_a = SubtitleCue(index=1, start_ms=start_a, end_ms=end_a, lines=["A"])
            cue_b = SubtitleCue(index=2, start_ms=start_b, end_ms=end_b, lines=["B"])
            findings = _file_findings([cue_a, cue_b])
            overlap_findings = [f for f in findings if f.rule == "overlapping_cues"]
            if end_a > start_b:
                assert overlap_findings, (
                    f"end_a={end_a} > start_b={start_b} must fire overlapping_cues"
                )
            else:
                assert not overlap_findings, (
                    f"end_a={end_a} <= start_b={start_b} must not fire"
                )


# ─────────────────────────────────────────────────────────────────────────────
# Group 6 — No crashes on edge inputs
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_file_no_crash(self) -> None:
        empty = SubtitleFile(cues=[], language="en")
        assert check_file(empty) == []

    def test_single_empty_cue_no_crash(self) -> None:
        cue = _make_cue(lines=[""])
        findings = _findings_for(cue)
        # Empty line: no line_too_long, but may have other findings
        assert isinstance(findings, list)

    def test_very_long_unicode_line(self) -> None:
        """Very long unicode line: fires line_too_long with correct char count."""
        rng = _random.Random(601)
        line = _random_unicode_line(rng, 100)
        cue = _make_cue(lines=[line])
        assert cue.char_counts[0] == 100
        findings = [f for f in _findings_for(cue) if f.rule == "line_too_long"]
        assert findings
        assert findings[0].measured_value == 100.0

    def test_all_rules_fire_on_maximally_broken_cue(self) -> None:
        """A cue violating every rule produces findings for all applicable rules."""
        # 3 lines, each over 42 chars, very short duration
        long_line = "x" * 50
        cue = SubtitleCue(
            index=1,
            start_ms=0,
            end_ms=200,   # < 1000ms
            lines=[long_line, long_line, long_line],  # 3 lines, each too long
        )
        findings = _findings_for(cue)
        rules_fired = {f.rule for f in findings}
        assert "three_line_cue" in rules_fired
        assert "line_too_long" in rules_fired
        assert "sub_one_second" in rules_fired
        # CPS: 150 chars / 0.2s = 750 CPS → cps_exceeded
        assert "cps_exceeded" in rules_fired
