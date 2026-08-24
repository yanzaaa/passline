"""Corruption engine for the Passline golden corpus.

Produces structurally valid, parseable SRT files with deliberate content-level
defects for QC pipeline testing.  All mutations flow through the existing
``SubtitleCue`` model and ``write_srt`` writer so the round-trip guarantee is
maintained.  Defects are never syntax-level.

API
---
``corrupt_file(source, seed, defects, language)`` is the single entry point
and is callable both programmatically and from the CLI.

Determinism
-----------
Uses ``random.Random(seed)`` — NOT the global ``random`` module — so identical
(source, seed) inputs always produce byte-identical outputs regardless of other
randomness in the process.

Defect thresholds (single source of truth)
------------------------------------------
These match the rule engine's enforcement thresholds exactly:

  cps_blowout    CPS > 20.0      (measured via SubtitleCue.cps)
  line_overflow  chars > 42      (measured via SubtitleCue.char_counts[i])
  three_line_cue len(lines) > 2  (structural)
  short_duration duration_ms < 1000  (measured via SubtitleCue.duration_ms)
  overlap        cue[i].end_ms > cue[i+1].start_ms
  meaning_swap   text changed    (MEANING_LEVEL — not catchable by rule engine)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import NamedTuple

from passline.models.subtitle import SrtDialect, SubtitleCue, SubtitleFile
from passline.io.srt import parse_srt, write_srt
from passline.corpus.substitutions import get_substitutions
from passline.qc.thresholds import (
    CPS_VIOLATION,
    CPS_VIOLATION_CJK,
    LINE_CHAR_MAX,
    LINE_CHAR_MAX_CJK,
    MIN_DURATION_MS,
)
CPS_THRESHOLD = CPS_VIOLATION
LINE_CHAR_THRESHOLD = LINE_CHAR_MAX
ALL_DEFECT_TYPES: frozenset[str] = frozenset({
    "cps_blowout",
    "line_overflow",
    "three_line_cue",
    "short_duration",
    "overlap",
    "meaning_swap",
})

# ── Data structures ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DefectSpec:
    """Ground-truth record for one injected defect."""
    cue_index: int
    """1-based cue index matching ``SubtitleCue.index``."""
    defect_type: str
    """One of the ALL_DEFECT_TYPES values."""
    rule: str
    """The rule name the QC engine must check."""
    threshold: float
    """The limit that must not be exceeded (or the structural constraint)."""
    measured_value: float
    """Actual measured value after injection (verified via model property)."""
    severity: str
    """'ERROR' or 'WARNING'."""
    category: str
    """'DETERMINISTIC' (rule engine) or 'MEANING_LEVEL' (language checker)."""
    detail: str
    """Human-readable description for the manifest."""


@dataclass
class CorpusManifest:
    schema_version: str = "1.0"
    corpus_version: str = "1"
    language: str = "und"
    source_file: str = ""
    seed: int = 42
    defects: list[DefectSpec] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "corpus_version": self.corpus_version,
            "language": self.language,
            "source_file": self.source_file,
            "seed": self.seed,
            "defects": [asdict(d) for d in self.defects],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "CorpusManifest":
        m = cls(
            schema_version=d.get("schema_version", "1.0"),
            corpus_version=d.get("corpus_version", "1"),
            language=d.get("language", "und"),
            source_file=d.get("source_file", ""),
            seed=d.get("seed", 42),
        )
        for dd in d.get("defects", []):
            m.defects.append(DefectSpec(**dd))
        return m


@dataclass(frozen=True)
class CorruptionResult:
    broken_file: SubtitleFile
    broken_bytes: bytes
    manifest: CorpusManifest


# ── Case-preserving text substitution ────────────────────────────────────────

def _apply_sub_case(original: str, replacement: str) -> str:
    """Replace *original* with *replacement*, preserving capitalisation."""
    if original[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def _substitute_text(
    text: str,
    pairs: list[tuple[str, str]],
    rng,
) -> tuple[str, str | None, str | None]:
    """Apply one matching substitution to *text*.

    Returns (new_text, original_word, replacement_word).
    If no substitution matched, returns (text, None, None).
    """
    for orig, repl in rng.sample(pairs, k=len(pairs)):
        pattern = re.compile(rf"\b{re.escape(orig)}\b", re.IGNORECASE)
        if pattern.search(text):
            matched = pattern.search(text)
            if matched is None:
                continue
            orig_token = matched.group(0)
            new_token = _apply_sub_case(orig_token, repl)
            new_text = pattern.sub(new_token, text, count=1)
            if len(new_text) / max(len(text), 1) < 0.8 or len(new_text) / max(len(text), 1) > 1.2:
                continue  # skip if char-count change is too extreme
            return new_text, orig_token, new_token
    return text, None, None


# ── Per-defect applicators ────────────────────────────────────────────────────

def _apply_cps_blowout(cue: SubtitleCue, cps_threshold: float, is_cjk: bool) -> SubtitleCue | None:
    """Shrink display time so CPS > cps_threshold.

    Returns None if the cue is ineligible (already over threshold or too short).
    """
    cue_cps = cue.cps_display if is_cjk else cue.cps
    if cue_cps >= cps_threshold:
        return None  # already violating — skip (keeps manifest unambiguous)
    
    total_chars = cue.total_display_chars if is_cjk else cue.total_chars
    if total_chars < 10:
        return None  # too few chars to produce a meaningful CPS blowout
    if cue.duration_ms < 500:
        return None  # already very short

    # New duration: total_chars / (cps_threshold + 2.0) * 1000 ms -> CPS > cps_threshold
    new_duration_ms = int(total_chars / (cps_threshold + 2.0) * 1000)
    # Guard: must actually exceed threshold
    if new_duration_ms <= 0:
        return None
    new_end_ms = cue.start_ms + new_duration_ms
    mutated = SubtitleCue(
        index=cue.index,
        start_ms=cue.start_ms,
        end_ms=new_end_ms,
        lines=cue.lines,
    )
    mutated_cps = mutated.cps_display if is_cjk else mutated.cps
    if mutated_cps <= cps_threshold:
        return None  # rounding didn't push it over — skip
    return mutated


def _apply_line_overflow(cue: SubtitleCue, line_char_threshold: int, is_cjk: bool) -> SubtitleCue | None:
    """Join lines into one line longer than line_char_threshold chars.

    Only eligible if the joined result exceeds the threshold.
    """
    total_chars = cue.total_display_chars if is_cjk else cue.total_chars
    if total_chars > 80:
        return None
    if len(cue.lines) < 2:
        return None
    char_counts = cue.display_char_counts if is_cjk else cue.char_counts
    if any(c > line_char_threshold for c in char_counts):
        return None  # already violating
    joined_visible = " ".join(
        re.sub(r"</?(?:i|b|u|font)(?:\s[^>]*)?>", "", ln, flags=re.IGNORECASE).rstrip()
        for ln in cue.lines
    )
    # wait, if CJK, length of joined visible might be shorter/longer but roughly similar.
    # to be safe, just join the lines and measure.
    new_line = " ".join(ln for ln in cue.lines)
    mutated = SubtitleCue(
        index=cue.index,
        start_ms=cue.start_ms,
        end_ms=cue.end_ms,
        lines=[new_line],
    )
    mutated_char_counts = mutated.display_char_counts if is_cjk else mutated.char_counts
    if not any(c > line_char_threshold for c in mutated_char_counts):
        return None
    return mutated


def _apply_three_line_cue(cue: SubtitleCue) -> SubtitleCue | None:
    """Split the longest line at a word boundary to produce a third line."""
    if cue.total_chars > 80:
        return None
    if len(cue.lines) > 2:
        return None  # already 3+ lines
    # Find the longest line
    longest_idx = max(range(len(cue.lines)), key=lambda i: len(cue.lines[i]))
    longest = cue.lines[longest_idx]
    words = longest.split()
    if len(words) < 3:
        return None  # not enough words to split meaningfully
    mid = len(words) // 2
    part_a = " ".join(words[:mid])
    part_b = " ".join(words[mid:])
    new_lines = list(cue.lines)
    new_lines[longest_idx:longest_idx + 1] = [part_a, part_b]
    if len(new_lines) <= 2:
        return None  # split didn't produce 3 lines
    mutated = SubtitleCue(
        index=cue.index,
        start_ms=cue.start_ms,
        end_ms=cue.end_ms,
        lines=new_lines,
    )
    if len(mutated.lines) <= 2:
        return None
    return mutated


def _apply_short_duration(cue: SubtitleCue) -> SubtitleCue | None:
    """Shrink duration to well below MIN_DURATION_MS (target: 400 ms)."""
    if cue.duration_ms < MIN_DURATION_MS:
        return None  # already short
    if cue.duration_ms < 1500:
        return None  # too close to threshold — injection would be marginal
    new_end_ms = cue.start_ms + 400
    mutated = SubtitleCue(
        index=cue.index,
        start_ms=cue.start_ms,
        end_ms=new_end_ms,
        lines=cue.lines,
    )
    assert mutated.duration_ms < MIN_DURATION_MS
    return mutated


def _apply_overlap(cue_i: SubtitleCue, cue_j: SubtitleCue) -> SubtitleCue | None:
    """Extend cue_i's end_ms past cue_j's start_ms by 500 ms."""
    if cue_i.end_ms >= cue_j.start_ms:
        return None  # already overlapping
    gap_ms = cue_j.start_ms - cue_i.end_ms
    if gap_ms < 100:
        return None  # gap too small to inject cleanly
    new_end_ms = cue_j.start_ms + 500
    mutated = SubtitleCue(
        index=cue_i.index,
        start_ms=cue_i.start_ms,
        end_ms=new_end_ms,
        lines=cue_i.lines,
    )
    assert mutated.end_ms > cue_j.start_ms
    return mutated


# ── Main corruption function ──────────────────────────────────────────────────

def corrupt_file(
    source: SubtitleFile,
    seed: int = 42,
    defects: set[str] | None = None,
    language: str = "und",
    source_filename: str = "",
) -> CorruptionResult:
    """Produce a broken copy of *source* plus a manifest of every defect.

    Parameters
    ----------
    source:
        Clean parsed subtitle file.
    seed:
        Random seed for deterministic candidate selection.
    defects:
        Set of defect type names to inject.  ``None`` means all types.
    language:
        BCP-47 language code used for meaning-swap substitutions.
    source_filename:
        Original filename recorded in the manifest.
    """
    if defects is None:
        defects = set(ALL_DEFECT_TYPES)
    rng = __import__("random").Random(seed)  # local seed, never touches global state

    # ── Resolve thresholds based on language ──────────────────────────────────
    is_cjk = language.lower() in ("zh", "ja", "ko", "zh-tw", "zh-cn", "zh-hk", "zh-hant", "zh-hans")
    cps_threshold = CPS_VIOLATION_CJK if is_cjk else CPS_VIOLATION
    line_char_threshold = LINE_CHAR_MAX_CJK if is_cjk else LINE_CHAR_MAX

    cues: list[SubtitleCue] = list(source.cues)
    injected_defects: list[DefectSpec] = []
    used_cue_indices: set[int] = set()  # never apply two defects to the same cue

    def reserve(idx: int) -> bool:
        if idx in used_cue_indices:
            return False
        used_cue_indices.add(idx)
        return True

    # ── 1. CPS blowout ───────────────────────────────────────────────────────
    if "cps_blowout" in defects:
        candidates = [i for i, c in enumerate(cues)
                      if _apply_cps_blowout(c, cps_threshold, is_cjk) is not None]
        picks = rng.sample(candidates, k=min(2, len(candidates)))
        for i in sorted(picks):
            if not reserve(i):
                continue
            mutated = _apply_cps_blowout(cues[i], cps_threshold, is_cjk)
            if mutated is None:
                continue
            cues[i] = mutated
            mutated_cps = mutated.cps_display if is_cjk else mutated.cps
            total_chars = mutated.total_display_chars if is_cjk else mutated.total_chars
            injected_defects.append(DefectSpec(
                cue_index=mutated.index,
                defect_type="cps_blowout",
                rule="cps_exceeded",
                threshold=cps_threshold,
                measured_value=round(mutated_cps, 2),
                severity="ERROR",
                category="DETERMINISTIC",
                detail=(
                    f"Cue {mutated.index}: CPS={mutated_cps:.2f} > {cps_threshold} "
                    f"(dur={mutated.duration_ms}ms, chars={total_chars})"
                ),
            ))

    # ── 2. Line overflow ─────────────────────────────────────────────────────
    if "line_overflow" in defects:
        candidates = [i for i, c in enumerate(cues)
                      if _apply_line_overflow(c, line_char_threshold, is_cjk) is not None and i not in used_cue_indices]
        picks = rng.sample(candidates, k=min(2, len(candidates)))
        for i in sorted(picks):
            if not reserve(i):
                continue
            mutated = _apply_line_overflow(cues[i], line_char_threshold, is_cjk)
            if mutated is None:
                continue
            cues[i] = mutated
            char_counts = mutated.display_char_counts if is_cjk else mutated.char_counts
            max_line = max(char_counts)
            injected_defects.append(DefectSpec(
                cue_index=mutated.index,
                defect_type="line_overflow",
                rule="line_too_long",
                threshold=line_char_threshold,
                measured_value=float(max_line),
                severity="ERROR",
                category="DETERMINISTIC",
                detail=(
                    f"Cue {mutated.index}: longest line={max_line} chars > {line_char_threshold}"
                ),
            ))

    # ── 3. Three-line cue ────────────────────────────────────────────────────
    if "three_line_cue" in defects:
        candidates = [i for i, c in enumerate(cues)
                      if _apply_three_line_cue(c) is not None and i not in used_cue_indices]
        picks = rng.sample(candidates, k=min(2, len(candidates)))
        for i in sorted(picks):
            if not reserve(i):
                continue
            mutated = _apply_three_line_cue(cues[i])
            if mutated is None:
                continue
            cues[i] = mutated
            injected_defects.append(DefectSpec(
                cue_index=mutated.index,
                defect_type="three_line_cue",
                rule="three_line_cue",
                threshold=2.0,
                measured_value=float(len(mutated.lines)),
                severity="WARNING",
                category="DETERMINISTIC",
                detail=f"Cue {mutated.index}: {len(mutated.lines)} lines (max is 2)",
            ))

    # ── 4. Short duration ────────────────────────────────────────────────────
    if "short_duration" in defects:
        candidates = [i for i, c in enumerate(cues)
                      if _apply_short_duration(c) is not None and i not in used_cue_indices]
        picks = rng.sample(candidates, k=min(2, len(candidates)))
        for i in sorted(picks):
            if not reserve(i):
                continue
            mutated = _apply_short_duration(cues[i])
            if mutated is None:
                continue
            cues[i] = mutated
            injected_defects.append(DefectSpec(
                cue_index=mutated.index,
                defect_type="short_duration",
                rule="sub_one_second",
                threshold=float(MIN_DURATION_MS),
                measured_value=float(mutated.duration_ms),
                severity="ERROR",
                category="DETERMINISTIC",
                detail=(
                    f"Cue {mutated.index}: duration={mutated.duration_ms}ms < {MIN_DURATION_MS}ms"
                ),
            ))

    # ── 5. Overlap ───────────────────────────────────────────────────────────
    if "overlap" in defects:
        pair_candidates = [
            i for i in range(len(cues) - 1)
            if (_apply_overlap(cues[i], cues[i + 1]) is not None
                and i not in used_cue_indices
                and (i + 1) not in used_cue_indices)
        ]
        picks = rng.sample(pair_candidates, k=min(2, len(pair_candidates)))
        for i in sorted(picks):
            if not reserve(i):
                continue
            # Reserve i+1 too to keep manifest unambiguous
            if not reserve(i + 1):
                continue
            mutated = _apply_overlap(cues[i], cues[i + 1])
            if mutated is None:
                continue
            overlap_ms = mutated.end_ms - cues[i + 1].start_ms
            cues[i] = mutated
            injected_defects.append(DefectSpec(
                cue_index=mutated.index,
                defect_type="overlap",
                rule="overlapping_cues",
                threshold=0.0,
                measured_value=float(overlap_ms),
                severity="ERROR",
                category="DETERMINISTIC",
                detail=(
                    f"Cue {mutated.index} end={mutated.end_ms}ms overlaps "
                    f"cue {cues[i+1].index} start={cues[i+1].start_ms}ms "
                    f"by {overlap_ms}ms"
                ),
            ))

    # ── 6. Meaning swap ──────────────────────────────────────────────────────
    if "meaning_swap" in defects:
        pairs = get_substitutions(language)
        candidates = []
        for i, c in enumerate(cues):
            if i in used_cue_indices:
                continue
            for line in c.lines:
                test_text, orig_w, new_w = _substitute_text(line, pairs, rng)
                if orig_w is not None:
                    candidates.append((i, line, test_text, orig_w, new_w))
                    break  # one substitution per cue for unambiguous grading
        picks = rng.sample(candidates, k=min(2, len(candidates))) if len(candidates) >= 2 else candidates
        for i, orig_line, new_text, orig_w, new_w in picks:
            if not reserve(i):
                continue
            old_cue = cues[i]
            new_lines = [
                new_text if ln == orig_line else ln
                for ln in old_cue.lines
            ]
            mutated = SubtitleCue(
                index=old_cue.index,
                start_ms=old_cue.start_ms,
                end_ms=old_cue.end_ms,
                lines=new_lines,
            )
            cues[i] = mutated
            injected_defects.append(DefectSpec(
                cue_index=mutated.index,
                defect_type="meaning_swap",
                rule="meaning_changed",
                threshold=0.0,
                measured_value=0.0,
                severity="WARNING",
                category="MEANING_LEVEL",
                detail=f"Cue {mutated.index}: '{orig_w}' → '{new_w}'",
            ))

    # ── Sort defects by cue_index for deterministic manifest ordering ────────
    injected_defects.sort(key=lambda d: d.cue_index)

    # ── Build broken SubtitleFile and serialise ──────────────────────────────
    broken_file = SubtitleFile(
        cues=cues,
        language=language,
        source_path=None,
        srt_dialect=SrtDialect(trailing_blank=True),
    )
    broken_bytes = write_srt(broken_file)

    manifest = CorpusManifest(
        language=language,
        source_file=source_filename,
        seed=seed,
        defects=injected_defects,
    )

    return CorruptionResult(
        broken_file=broken_file,
        broken_bytes=broken_bytes,
        manifest=manifest,
    )


def corrupt_demo(
    source: SubtitleFile,
    seed: int,
    language: str = "und",
    excerpt_cues: int = 14,
    defects: set[str] | None = None,
) -> CorruptionResult:
    """Produce a broken copy of *source* using the demo recipe constraints.

    Parameters
    ----------
    source:
        Clean parsed subtitle file.
    seed:
        Random seed for deterministic candidate selection.
    language:
        BCP-47 language code used for meaning-swap substitutions.
    excerpt_cues:
        Number of cues to slice from the beginning of the file (default: 14).
    defects:
        Set of defect type names to inject. None means {"cps_blowout", "line_overflow", "short_duration", "meaning_swap"}.
    """
    if defects is None:
        defects = {"cps_blowout", "line_overflow", "short_duration", "meaning_swap"}

    # ── Resolve thresholds based on language ──────────────────────────────────
    is_cjk = language.lower() in ("zh", "ja", "ko", "zh-tw", "zh-cn", "zh-hk", "zh-hant", "zh-hans")
    cps_threshold = CPS_VIOLATION_CJK if is_cjk else CPS_VIOLATION
    line_char_threshold = LINE_CHAR_MAX_CJK if is_cjk else LINE_CHAR_MAX

    rng = __import__("random").Random(seed)

    # Slice N cues and copy them, spacing them out to ensure they are clean and have ample timing room
    # We must skip cues that are natively > line_char_threshold * 2 characters, as they can never be safely reflowed within 
    # the 2-line limit and would permanently hold the delivery.
    def can_be_reflowed_to_two_lines(cue: SubtitleCue) -> bool:
        from passline.agents.fixer_agent import _split_long_line
        full_text = " ".join(ln.strip() for ln in cue.lines)
        res = _split_long_line(full_text, max_chars=line_char_threshold, is_cjk=is_cjk)
        return len(res) <= 2

    eligible_raw_cues = [c for c in source.cues if can_be_reflowed_to_two_lines(c)]
    raw_cues = eligible_raw_cues[:excerpt_cues]
    cues = []
    current_time = 10000
    for i, c in enumerate(raw_cues):
        total_chars = sum(len(ln) for ln in c.lines)
        # Safely space them so they start fully clean below 12.0 CPS
        dur = max(3000, int(total_chars / 12.0 * 1000))
        cues.append(
            SubtitleCue(
                index=i + 1,
                start_ms=current_time,
                end_ms=current_time + dur,
                lines=list(c.lines)
            )
        )
        current_time += dur + 2500  # 2500ms of open air / gap

    injected_defects: list[DefectSpec] = []
    used_cue_indices: set[int] = set()

    def reserve(idx: int) -> bool:
        if idx in used_cue_indices:
            return False
        used_cue_indices.add(idx)
        if idx - 1 >= 0:
            used_cue_indices.add(idx - 1)
        if idx + 1 < len(cues):
            used_cue_indices.add(idx + 1)
        return True

    def is_timing_safe(idx: int) -> bool:
        if idx > 0:
            if cues[idx].start_ms - cues[idx - 1].end_ms < 2000:
                return False
        if idx < len(cues) - 1:
            if cues[idx + 1].start_ms - cues[idx].end_ms < 2000:
                return False
        return True

    def is_repairable_timing(idx: int, target_cps: float = 16.0) -> bool:
        cue = cues[idx]
        total_chars = cue.total_display_chars if is_cjk else cue.total_chars
        if total_chars == 0:
            return True
        # Milliseconds required to sit strictly below target_cps
        req_ms = int(total_chars / target_cps * 1000) + 1
        # Own duration plus gap before the following cue
        available_ms = cue.duration_ms
        if idx + 1 < len(cues):
            available_ms += (cues[idx + 1].start_ms - cue.end_ms) - 50
        else:
            available_ms += 10000
        
        return available_ms >= req_ms

    # ── 1. Meaning swap ──────────────────────────────────────────────────────
    if "meaning_swap" in defects:
        pairs = get_substitutions(language)
        candidates = []
        for i, c in enumerate(cues):
            for line in c.lines:
                test_text, orig_w, new_w = _substitute_text(line, pairs, rng)
                if orig_w is not None:
                    candidates.append((i, line, test_text, orig_w, new_w))
                    break  # one substitution per cue
        if candidates:
            pick_item = rng.choice(candidates)
            i, orig_line, new_text, orig_w, new_w = pick_item
            if reserve(i):
                old_cue = cues[i]
                new_lines = [
                    new_text if ln == orig_line else ln
                    for ln in old_cue.lines
                ]
                mutated = SubtitleCue(
                    index=old_cue.index,
                    start_ms=old_cue.start_ms,
                    end_ms=old_cue.end_ms,
                    lines=new_lines,
                )
                cues[i] = mutated
                injected_defects.append(DefectSpec(
                    cue_index=mutated.index,
                    defect_type="meaning_swap",
                    rule="meaning_changed",
                    threshold=0.0,
                    measured_value=0.0,
                    severity="WARNING",
                    category="MEANING_LEVEL",
                    detail=f"Cue {mutated.index}: '{orig_w}' → '{new_w}'",
                ))

    # ── 2. Other timing/layout defects (loop until target count of 6) ────────
    other_defect_types = [d for d in defects if d != "meaning_swap"]
    if other_defect_types:
        attempts = 0
        while len(injected_defects) < 6 and attempts < 100:
            attempts += 1
            valid_candidates = []
            for d_type in other_defect_types:
                if d_type == "cps_blowout":
                    valid_candidates.extend([
                        (i, d_type) for i, c in enumerate(cues)
                        if i not in used_cue_indices
                        and _apply_cps_blowout(c, cps_threshold, is_cjk) is not None
                        and can_be_reflowed_to_two_lines(c)
                        and is_timing_safe(i)
                        and is_repairable_timing(i)
                    ])
                elif d_type == "line_overflow":
                    valid_candidates.extend([
                        (i, d_type) for i, c in enumerate(cues)
                        if i not in used_cue_indices
                        and _apply_line_overflow(c, line_char_threshold, is_cjk) is not None
                        and can_be_reflowed_to_two_lines(c)
                    ])
                elif d_type == "short_duration":
                    valid_candidates.extend([
                        (i, d_type) for i, c in enumerate(cues)
                        if i not in used_cue_indices
                        and _apply_short_duration(c) is not None
                        and is_timing_safe(i)
                        and is_repairable_timing(i)
                    ])
            
            if not valid_candidates:
                break
                
            pick_i, pick_dtype = rng.choice(valid_candidates)
            if reserve(pick_i):
                if pick_dtype == "cps_blowout":
                    mutated = _apply_cps_blowout(cues[pick_i], cps_threshold, is_cjk)
                    if mutated is not None:
                        cues[pick_i] = mutated
                        mutated_cps = mutated.cps_display if is_cjk else mutated.cps
                        total_chars = mutated.total_display_chars if is_cjk else mutated.total_chars
                        injected_defects.append(DefectSpec(
                            cue_index=mutated.index,
                            defect_type="cps_blowout",
                            rule="cps_exceeded",
                            threshold=cps_threshold,
                            measured_value=round(mutated_cps, 2),
                            severity="ERROR",
                            category="DETERMINISTIC",
                            detail=(
                                f"Cue {mutated.index}: CPS={mutated_cps:.2f} > {cps_threshold} "
                                f"(dur={mutated.duration_ms}ms, chars={total_chars})"
                            ),
                        ))
                elif pick_dtype == "line_overflow":
                    mutated = _apply_line_overflow(cues[pick_i], line_char_threshold, is_cjk)
                    if mutated is not None:
                        cues[pick_i] = mutated
                        char_counts = mutated.display_char_counts if is_cjk else mutated.char_counts
                        max_line = max(char_counts)
                        injected_defects.append(DefectSpec(
                            cue_index=mutated.index,
                            defect_type="line_overflow",
                            rule="line_too_long",
                            threshold=line_char_threshold,
                            measured_value=float(max_line),
                            severity="ERROR",
                            category="DETERMINISTIC",
                            detail=(
                                f"Cue {mutated.index}: longest line={max_line} chars > {line_char_threshold}"
                            ),
                        ))
                elif pick_dtype == "short_duration":
                    mutated = _apply_short_duration(cues[pick_i])
                    if mutated is not None:
                        cues[pick_i] = mutated
                        injected_defects.append(DefectSpec(
                            cue_index=mutated.index,
                            defect_type="short_duration",
                            rule="sub_one_second",
                            threshold=float(MIN_DURATION_MS),
                            measured_value=float(mutated.duration_ms),
                            severity="ERROR",
                            category="DETERMINISTIC",
                            detail=(
                                f"Cue {mutated.index}: duration={mutated.duration_ms}ms < {MIN_DURATION_MS}ms"
                            ),
                        ))

    # ── Sort defects by cue_index for deterministic manifest ordering ────────
    injected_defects.sort(key=lambda d: d.cue_index)

    # ── Build broken SubtitleFile and serialise ──────────────────────────────
    broken_file = SubtitleFile(
        cues=cues,
        language=language,
        source_path=None,
        srt_dialect=SrtDialect(trailing_blank=True),
    )
    broken_bytes = write_srt(broken_file)

    manifest = CorpusManifest(
        language=language,
        source_file=source.source_path or "clean_source.srt",
        seed=seed,
        defects=injected_defects,
    )

    return CorruptionResult(
        broken_file=broken_file,
        broken_bytes=broken_bytes,
        manifest=manifest,
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m passline.corpus.corrupt",
        description="Inject deterministic defects into a subtitle file.",
    )
    p.add_argument("--input",    required=True, help="Clean SRT file path")
    p.add_argument("--output",   required=True, help="Broken SRT output path")
    p.add_argument("--manifest", required=True, help="Manifest JSON output path")
    p.add_argument("--seed",     type=int, default=42, help="Random seed (default: 42)")
    p.add_argument("--language", default="und", help="BCP-47 language code")
    p.add_argument(
        "--defects",
        nargs="*",
        choices=sorted(ALL_DEFECT_TYPES),
        help="Defect types to inject (default: all)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    in_path = Path(args.input)
    out_path = Path(args.output)
    manifest_path = Path(args.manifest)

    if not in_path.exists():
        print(f"ERROR: input file not found: {in_path}", file=sys.stderr)
        return 1

    data = in_path.read_bytes()
    source = parse_srt(data, language=args.language, source_path=str(in_path))

    defect_set = set(args.defects) if args.defects else None
    result = corrupt_file(
        source,
        seed=args.seed,
        defects=defect_set,
        language=args.language,
        source_filename=in_path.name,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(result.broken_bytes)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(result.manifest.to_json(), encoding="utf-8")

    print(f"Corrupted: {out_path}  ({len(result.manifest.defects)} defects)")
    print(f"Manifest:  {manifest_path}")
    for d in result.manifest.defects:
        print(f"  [{d.category:<14}] cue {d.cue_index:>3}  {d.defect_type:<16}  {d.detail}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
