"""SRT subtitle file parser and writer for Passline.

Round-trip guarantee
---------------------
For files that parse as *canonical* (``SubtitleFile.is_canonical == True``),
``write_srt(parse_srt(data)) == data`` is guaranteed byte-for-byte.

Non-canonical detection
------------------------
After parsing, the file is immediately re-serialised and compared to the original
bytes.  Any mismatch marks ``is_canonical = False`` and populates
``parse_anomalies`` with human-readable descriptions of every discrepancy.
Skipped blocks increment ``skipped_blocks``.  Nothing is silent.

Formatting fidelity (BOM, CRLF, trailing blank) travels in ``SubtitleFile.srt_dialect``
so it survives ``model_copy()`` and works correctly in long-running server processes.

Timecode format: ``HH:MM:SS,mmm`` (comma separator, not dot).
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from passline.models.subtitle import SrtDialect, SubtitleCue, SubtitleFile

if TYPE_CHECKING:
    from passline.events.bus import EventBus

_BOM = b"\xef\xbb\xbf"

# Timecode pattern.  We capture both halves independently so we can detect
# non-canonical formatting (single-digit hours, extra spaces around -->) later.
_TIMECODE_RE = re.compile(
    r"^(\d{1,2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2}),(\d{3})"
)

# Pattern for a *canonical* timecode line: exactly two-digit hours, single space
# around the arrow, no trailing content.
_CANONICAL_TC_RE = re.compile(
    r"^\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}$"
)


# ── Timecode helpers ──────────────────────────────────────────────────────────

def _ms_to_timecode(ms: int) -> str:
    """Format milliseconds as ``HH:MM:SS,mmm`` (always two-digit hours)."""
    total_s, millis = divmod(ms, 1000)
    total_m, secs = divmod(total_s, 60)
    hours, mins = divmod(total_m, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def _parse_timecode_line(tc_line: str) -> tuple[int, int]:
    """Return ``(start_ms, end_ms)`` from a timecode line, or raise ValueError."""
    m = _TIMECODE_RE.match(tc_line)
    if m is None:
        raise ValueError(f"Invalid SRT timecode line: {tc_line!r}")
    start = int(m[1]) * 3_600_000 + int(m[2]) * 60_000 + int(m[3]) * 1_000 + int(m[4])
    end   = int(m[5]) * 3_600_000 + int(m[6]) * 60_000 + int(m[7]) * 1_000 + int(m[8])
    return start, end


# ── Writer (used standalone and internally for canonicality check) ────────────

def write_srt(subtitle_file: SubtitleFile) -> bytes:
    """Serialise a :class:`~passline.models.subtitle.SubtitleFile` to SRT bytes.

    If *subtitle_file* was produced by :func:`parse_srt` in the same process and
    ``subtitle_file.is_canonical`` is ``True``, the output is byte-identical to the
    original input.

    For programmatically constructed files (``srt_dialect`` is ``None``), output
    uses LF line endings, no BOM, and a trailing newline after the last cue.
    """
    dialect = subtitle_file.srt_dialect or SrtDialect()
    eol = "\r\n" if dialect.crlf else "\n"

    cue_blocks: list[str] = []
    for cue in subtitle_file.cues:
        block_lines = [
            str(cue.index),
            f"{_ms_to_timecode(cue.start_ms)} --> {_ms_to_timecode(cue.end_ms)}",
            *cue.lines,
        ]
        cue_blocks.append(eol.join(block_lines))

    body = (eol + eol).join(cue_blocks)

    if dialect.trailing_blank:
        body += eol + eol
    else:
        body += eol

    result = body.encode("utf-8")
    if dialect.has_bom:
        result = _BOM + result

    return result


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_srt(
    data: bytes,
    language: str = "und",
    source_path: str | None = None,
    delivery_id: str = "",
    bus: "EventBus | None" = None,
) -> SubtitleFile:
    """Parse raw SRT bytes into a :class:`~passline.models.subtitle.SubtitleFile`.

    Parameters
    ----------
    data:
        Raw bytes of the SRT file.
    language:
        BCP-47 language code to attach to the result.
    source_path:
        Optional file path stored on the model (not used for parsing).
    delivery_id:
        Identifier emitted with the ``subtitle.submitted`` event.
        If empty and *bus* is provided, a UUID is auto-generated.
    bus:
        Optional :class:`~passline.events.bus.EventBus`; when provided, emits
        a ``subtitle.submitted`` event after successful parsing.

    Returns
    -------
    SubtitleFile
        Parsed file.  Check ``is_canonical`` and ``parse_anomalies`` for
        normalisation details; ``skipped_blocks`` counts dropped cue blocks.
    """
    original_data = data  # keep for canonicality check
    anomalies: list[str] = []
    skipped = 0

    # ── 1. Strip BOM ──────────────────────────────────────────────────────────
    has_bom = data.startswith(_BOM)
    if has_bom:
        data = data[len(_BOM):]

    # ── 2. Detect line endings ────────────────────────────────────────────────
    crlf_count = data.count(b"\r\n")
    # Count bare \n that are NOT preceded by \r
    lf_only_count = len(re.findall(b"(?<!\r)\n", data))

    if crlf_count > 0 and lf_only_count > 0:
        anomalies.append(
            f"Mixed line endings: {crlf_count} CRLF and {lf_only_count} bare LF — "
            f"normalised to {'CRLF' if crlf_count >= lf_only_count else 'LF'}"
        )
        crlf = crlf_count >= lf_only_count
    else:
        crlf = crlf_count > 0

    # ── 3. Normalise to LF for parsing ────────────────────────────────────────
    text = data.decode("utf-8")
    if "\r\n" in text:
        text = text.replace("\r\n", "\n")

    # ── 4. Detect trailing blank line ─────────────────────────────────────────
    trailing_blank = text.endswith("\n\n")

    # ── 5. Split into cue blocks ──────────────────────────────────────────────
    # More than two consecutive \n means extra blank lines — flag it.
    if "\n\n\n" in text:
        anomalies.append("Extra blank lines between cues — normalised to single blank line")
        # Collapse runs of 3+ \n to \n\n
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Re-check trailing blank after collapse
        trailing_blank = text.endswith("\n\n")

    blocks = [b.strip("\n") for b in text.split("\n\n")]
    blocks = [b for b in blocks if b.strip()]

    dialect = SrtDialect(has_bom=has_bom, crlf=crlf, trailing_blank=trailing_blank)

    # ── 6. Parse each cue block ───────────────────────────────────────────────
    cues: list[SubtitleCue] = []
    for block in blocks:
        block_lines = block.split("\n")

        if len(block_lines) < 3:
            anomalies.append(
                f"Skipped block with fewer than 3 lines: {block_lines[0]!r}"
            )
            skipped += 1
            continue

        # Index line
        try:
            index = int(block_lines[0].strip())
        except ValueError:
            anomalies.append(
                f"Skipped block: non-integer index line {block_lines[0]!r}"
            )
            skipped += 1
            continue

        # Timecode line
        tc_line = block_lines[1]
        try:
            start_ms, end_ms = _parse_timecode_line(tc_line)
        except ValueError:
            anomalies.append(
                f"Skipped cue {index}: invalid timecode {tc_line!r}"
            )
            skipped += 1
            continue

        # Check for non-canonical timecode format
        if not _CANONICAL_TC_RE.match(tc_line):
            anomalies.append(
                f"Cue {index}: non-canonical timecode {tc_line!r} — "
                f"normalised to {_ms_to_timecode(start_ms)} --> {_ms_to_timecode(end_ms)}"
            )

        text_lines = block_lines[2:]
        if not text_lines:
            anomalies.append(f"Skipped cue {index}: no text lines")
            skipped += 1
            continue

        cues.append(SubtitleCue(
            index=index,
            start_ms=start_ms,
            end_ms=end_ms,
            lines=text_lines,
        ))

    # ── 7. Build preliminary SubtitleFile (canonical=True initially) ──────────
    subtitle_file = SubtitleFile(
        cues=cues,
        language=language,
        source_path=source_path,
        srt_dialect=dialect,
        is_canonical=True,
        skipped_blocks=skipped,
        parse_anomalies=anomalies,
    )

    # ── 8. Canonicality check ─────────────────────────────────────────────────
    # Re-serialise and compare to original bytes. Any mismatch = non-canonical.
    if anomalies or skipped:
        # We already know it's non-canonical if we recorded any anomalies or skips.
        subtitle_file = subtitle_file.model_copy(update={"is_canonical": False})
    else:
        reconstructed = write_srt(subtitle_file)
        if reconstructed != original_data:
            subtitle_file = subtitle_file.model_copy(update={
                "is_canonical": False,
                "parse_anomalies": [
                    "Re-serialised bytes differ from original (unclassified difference)"
                ],
            })

    # ── 9. Auto-generate delivery_id if empty and bus is provided ────────────
    if bus is not None and not delivery_id:
        import uuid
        delivery_id = str(uuid.uuid4())

    # ── 10. Emit subtitle.submitted event ─────────────────────────────────────
    if bus is not None:
        from passline.events.bus import DeliveryEvent, EventType
        bus.emit(DeliveryEvent(
            event_type=EventType.SUBTITLE_SUBMITTED,
            delivery_id=delivery_id,
            language=language,
            details={
                "cue_count": len(cues),
                "source_path": source_path,
                "skipped_blocks": skipped,
                "is_canonical": subtitle_file.is_canonical,
            },
        ))

    return subtitle_file
