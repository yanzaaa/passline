"""SRT subtitle file parser and writer for Passline.

Hard requirement: parsing a valid SRT file and writing it back produces
byte-identical output. This is achieved by recording:
  - Whether the source had a UTF-8 BOM
  - Whether the source used CRLF or LF line endings
  - Whether the source had a trailing blank line after the last cue

Timecode format: ``HH:MM:SS,mmm`` (comma separator, not dot).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from passline.models.subtitle import SubtitleCue, SubtitleFile

if TYPE_CHECKING:
    from passline.events.bus import EventBus

_BOM = b"\xef\xbb\xbf"

_TIMECODE_RE = re.compile(
    r"^(\d{1,2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2}),(\d{3})"
)


def _timecode_to_ms(tc: str) -> int:
    m = _TIMECODE_RE.match(tc)
    if m is None:
        raise ValueError(f"Invalid SRT timecode: {tc!r}")
    h, mi, s, ms = int(m[1]), int(m[2]), int(m[3]), int(m[4])
    return h * 3_600_000 + mi * 60_000 + s * 1_000 + ms


def _ms_to_timecode(ms: int) -> str:
    total_s, millis = divmod(ms, 1000)
    total_m, secs = divmod(total_s, 60)
    hours, mins = divmod(total_m, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def _parse_timecode_line(tc_line: str) -> tuple[int, int]:
    m = _TIMECODE_RE.match(tc_line)
    if m is None:
        raise ValueError(f"Invalid SRT timecode line: {tc_line!r}")
    start = int(m[1]) * 3_600_000 + int(m[2]) * 60_000 + int(m[3]) * 1_000 + int(m[4])
    end   = int(m[5]) * 3_600_000 + int(m[6]) * 60_000 + int(m[7]) * 1_000 + int(m[8])
    return start, end


@dataclass
class _SrtMeta:
    has_bom: bool = False
    crlf: bool = False
    trailing_blank: bool = False


# Metadata keyed by object id to enable byte-identical write-back without
# polluting the frozen Pydantic model.
_meta_cache: dict[int, _SrtMeta] = {}


def parse_srt(
    data: bytes,
    language: str = "und",
    source_path: str | None = None,
    delivery_id: str = "",
    bus: "EventBus | None" = None,
) -> SubtitleFile:
    """Parse raw SRT bytes into a SubtitleFile.

    Parameters
    ----------
    data:        Raw bytes of the SRT file.
    language:    BCP-47 language code.
    source_path: Optional file path stored on the model.
    delivery_id: Identifier emitted with the subtitle.submitted event.
    bus:         Optional EventBus; when provided, emits subtitle.submitted.
    """
    meta = _SrtMeta()

    # 1. Strip BOM
    if data.startswith(_BOM):
        meta.has_bom = True
        data = data[len(_BOM):]

    # 2. Detect line endings
    meta.crlf = b"\r\n" in data

    # Normalise to LF for parsing
    text = data.decode("utf-8")
    if meta.crlf:
        text = text.replace("\r\n", "\n")

    # 3. Detect trailing blank line
    meta.trailing_blank = text.endswith("\n\n")

    # 4. Split into cue blocks on double newline
    blocks = [b.strip("\n") for b in text.split("\n\n")]
    blocks = [b for b in blocks if b.strip()]

    # 5. Parse each cue block
    cues: list[SubtitleCue] = []
    for block in blocks:
        block_lines = block.split("\n")
        if len(block_lines) < 3:
            continue

        try:
            index = int(block_lines[0].strip())
        except ValueError:
            continue

        try:
            start_ms, end_ms = _parse_timecode_line(block_lines[1])
        except ValueError:
            continue

        text_lines = block_lines[2:]
        if not text_lines:
            continue

        cues.append(SubtitleCue(
            index=index,
            start_ms=start_ms,
            end_ms=end_ms,
            lines=text_lines,
        ))

    subtitle_file = SubtitleFile(cues=cues, language=language, source_path=source_path)
    _meta_cache[id(subtitle_file)] = meta

    # 6. Emit subtitle.submitted event
    if bus is not None:
        from passline.events.bus import DeliveryEvent, EventType
        bus.emit(DeliveryEvent(
            event_type=EventType.SUBTITLE_SUBMITTED,
            delivery_id=delivery_id,
            language=language,
            details={"cue_count": len(cues), "source_path": source_path},
        ))

    return subtitle_file


def write_srt(subtitle_file: SubtitleFile) -> bytes:
    """Serialise a SubtitleFile back to SRT bytes.

    If subtitle_file was produced by parse_srt in the same process,
    output is byte-identical to the original input.
    """
    meta = _meta_cache.get(id(subtitle_file), _SrtMeta())
    eol = "\r\n" if meta.crlf else "\n"

    cue_blocks: list[str] = []
    for cue in subtitle_file.cues:
        block_lines = [
            str(cue.index),
            f"{_ms_to_timecode(cue.start_ms)} --> {_ms_to_timecode(cue.end_ms)}",
            *cue.lines,
        ]
        cue_blocks.append(eol.join(block_lines))

    # Join cue blocks with a blank line between them (two eols).
    # Each block ends without a newline; we add eol+eol between blocks,
    # then decide the tail based on whether the original had a trailing blank.
    body = (eol + eol).join(cue_blocks)

    if meta.trailing_blank:
        body += eol + eol   # blank line after last cue
    else:
        body += eol         # single trailing newline after last cue text

    result = body.encode("utf-8")
    if meta.has_bom:
        result = _BOM + result

    return result
