"""Passline QC rule engine.

``check_file`` grades a ``SubtitleFile`` and returns a list of ``Finding``
objects.  Every numeric measurement comes exclusively from ``SubtitleCue``
computed properties — the engine never re-implements math.

Rules implemented
-----------------
three_line_cue   len(cue.lines) > MAX_LINES_PER_CUE                       WARNING
line_too_long    any(c > LINE_CHAR_MAX for c in cue.char_counts)           ERROR
cps_exceeded     cue.cps > CPS_VIOLATION                                   ERROR
cps_warning      CPS_WARNING_LOW <= cue.cps <= CPS_VIOLATION               WARNING
sub_one_second   cue.duration_ms < MIN_DURATION_MS                        ERROR
overlapping_cues cues[i].end_ms > cues[i+1].start_ms                      ERROR
malformed_timecode cue.start_ms >= cue.end_ms                              ERROR
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from passline.models.subtitle import SubtitleFile
from passline.qc.thresholds import (
    CPS_VIOLATION,
    CPS_WARNING_LOW,
    CPS_VIOLATION_CJK,
    CPS_WARNING_LOW_CJK,
    LINE_CHAR_MAX,
    LINE_CHAR_MAX_CJK,
    MAX_LINES_PER_CUE,
    MIN_DURATION_MS,
)

if TYPE_CHECKING:
    from passline.events.bus import EventBus


@dataclass(frozen=True)
class Finding:
    """One rule-engine finding for a single cue."""

    rule: str
    """Rule identifier (matches manifest 'rule' field exactly)."""

    cue_index: int
    """1-based cue sequence number (matches SubtitleCue.index)."""

    measured_value: float
    """The measured value that triggered this finding."""

    threshold: float
    """The limit that was exceeded (or the structural constraint)."""

    severity: str
    """'ERROR' or 'WARNING'."""

    explanation: str
    """One-line human-readable description."""


def check_file(
    subtitle_file: SubtitleFile,
    delivery_id: str = "",
    language: str = "und",
    bus: "EventBus | None" = None,
) -> list[Finding]:
    """Grade *subtitle_file* and return a list of :class:`Finding` objects.

    Findings are produced in cue order.  All measurements use
    ``SubtitleCue`` computed properties — no math is re-implemented here.

    Parameters
    ----------
    subtitle_file:
        Parsed subtitle file to grade.
    delivery_id:
        Identifier attached to emitted events.
    language:
        Language code attached to emitted events. Used as a fallback if the file has no language.
    bus:
        Optional :class:`~passline.events.bus.EventBus`; when provided, one
        ``qc.violation`` event is emitted per finding.
    """
    findings: list[Finding] = []
    cues = subtitle_file.cues
    
    resolved_language = language if language != "und" else (subtitle_file.language if subtitle_file.language else "und")
    is_cjk = resolved_language.lower() in ("zh", "ja", "ko", "zh-tw", "zh-cn", "zh-hk", "zh-hant", "zh-hans")

    limit_cps_violation = CPS_VIOLATION_CJK if is_cjk else CPS_VIOLATION
    limit_cps_warning = CPS_WARNING_LOW_CJK if is_cjk else CPS_WARNING_LOW
    limit_line_char = LINE_CHAR_MAX_CJK if is_cjk else LINE_CHAR_MAX

    for i, cue in enumerate(cues):

        # ── Rule: malformed_timecode (start >= end) ───────────────────────
        if cue.start_ms >= cue.end_ms:
            findings.append(Finding(
                rule="malformed_timecode",
                cue_index=cue.index,
                measured_value=float(cue.end_ms - cue.start_ms),
                threshold=0.0,
                severity="ERROR",
                explanation=(
                    f"Cue {cue.index}: start_ms={cue.start_ms} >= end_ms={cue.end_ms} "
                    f"(duration={cue.duration_ms}ms)"
                ),
            ))
            # Don't run CPS or duration rules on malformed cues
            continue

        # ── Rule: sub_one_second ──────────────────────────────────────────
        if cue.duration_ms < MIN_DURATION_MS:
            findings.append(Finding(
                rule="sub_one_second",
                cue_index=cue.index,
                measured_value=float(cue.duration_ms),
                threshold=float(MIN_DURATION_MS),
                severity="ERROR",
                explanation=(
                    f"Cue {cue.index}: duration={cue.duration_ms}ms "
                    f"< {MIN_DURATION_MS}ms minimum"
                ),
            ))

        # ── Rule: three_line_cue ──────────────────────────────────────────
        if len(cue.lines) > MAX_LINES_PER_CUE:
            findings.append(Finding(
                rule="three_line_cue",
                cue_index=cue.index,
                measured_value=float(len(cue.lines)),
                threshold=float(MAX_LINES_PER_CUE),
                severity="WARNING",
                explanation=(
                    f"Cue {cue.index}: {len(cue.lines)} lines "
                    f"(max {MAX_LINES_PER_CUE})"
                ),
            ))

        # ── Rule: line_too_long ───────────────────────────────────────────
        char_counts = cue.display_char_counts if is_cjk else cue.char_counts
        if any(c > limit_line_char for c in char_counts):
            worst = max(char_counts)
            findings.append(Finding(
                rule="line_too_long",
                cue_index=cue.index,
                measured_value=float(worst),
                threshold=float(limit_line_char),
                severity="ERROR",
                explanation=(
                    f"Cue {cue.index}: longest visible line={worst} chars "
                    f"> {limit_line_char} limit"
                ),
            ))

        # ── Rules: cps_exceeded / cps_warning ────────────────────────────
        # Use cue.cps or cue.cps_display — the model's computed property.
        cue_cps = cue.cps_display if is_cjk else cue.cps
        if cue_cps > limit_cps_violation:
            findings.append(Finding(
                rule="cps_exceeded",
                cue_index=cue.index,
                measured_value=cue_cps,
                threshold=limit_cps_violation,
                severity="ERROR",
                explanation=(
                    f"Cue {cue.index}: {cue_cps:.2f} CPS > {limit_cps_violation} limit "
                    f"({cue.total_display_chars if is_cjk else cue.total_chars} chars / {cue.duration_ms}ms)"
                ),
            ))
        elif limit_cps_warning <= cue_cps <= limit_cps_violation:
            findings.append(Finding(
                rule="cps_warning",
                cue_index=cue.index,
                measured_value=cue_cps,
                threshold=limit_cps_warning,
                severity="WARNING",
                explanation=(
                    f"Cue {cue.index}: {cue_cps:.2f} CPS in warning band "
                    f"[{limit_cps_warning}–{limit_cps_violation}]"
                ),
            ))

    # ── Rule: overlapping_cues (pairwise) ─────────────────────────────────
    for i in range(len(cues) - 1):
        a, b = cues[i], cues[i + 1]
        if a.end_ms > b.start_ms:
            overlap_ms = a.end_ms - b.start_ms
            findings.append(Finding(
                rule="overlapping_cues",
                cue_index=a.index,
                measured_value=float(overlap_ms),
                threshold=0.0,
                severity="ERROR",
                explanation=(
                    f"Cue {a.index} end={a.end_ms}ms overlaps "
                    f"cue {b.index} start={b.start_ms}ms by {overlap_ms}ms"
                ),
            ))

    # Sort findings by cue_index for deterministic ordering
    findings.sort(key=lambda f: (f.cue_index, f.rule))

    # ── Event emission ────────────────────────────────────────────────────
    if bus is not None and findings:
        from passline.events.bus import DeliveryEvent, EventType
        for finding in findings:
            bus.emit(DeliveryEvent(
                event_type=EventType.QC_VIOLATION,
                delivery_id=delivery_id,
                language=resolved_language,
                details={
                    "rule":        finding.rule,
                    "cue":         finding.cue_index,
                    "value":       finding.measured_value,
                    "threshold":   finding.threshold,
                    "severity":    finding.severity,
                    "explanation": finding.explanation,
                },
            ))

    return findings
