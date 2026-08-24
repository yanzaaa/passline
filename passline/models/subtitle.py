"""Subtitle cue and file data models for Passline.

All arithmetic is deterministic Python — no LLM performs any calculations here.

Character counting policy
--------------------------
``char_counts``, ``total_chars``, and ``cps`` operate on **visible text** only.
SRT formatting markup tags (``<i>``, ``</i>``, ``<b>``, ``</b>``, ``<u>``, ``</u>``,
``<font ...>``, ``</font>``) are stripped before counting so that reading-speed
calculations reflect what the viewer actually reads.

The raw ``lines`` field retains all markup intact so that ``write_srt`` can produce
byte-identical output. Never strip markup from ``lines`` directly.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, computed_field, ConfigDict, Field


# ── Markup stripping ──────────────────────────────────────────────────────────

# Matches opening and closing SRT markup tags: <i>, </i>, <b>, </b>, <u>, </u>,
# <font ...>, </font>. Attribute values may contain any characters except '>'.
_MARKUP_RE = re.compile(r"</?(?:i|b|u|font)(?:\s[^>]*)?>", re.IGNORECASE)


def _strip_markup(text: str) -> str:
    """Remove SRT formatting markup tags from *text*, leaving visible characters."""
    return _MARKUP_RE.sub("", text)


# ── SRT dialect ───────────────────────────────────────────────────────────────

class SrtDialect(BaseModel):
    """Formatting facts recorded during SRT parsing for byte-identical write-back.

    Stored on :class:`SubtitleFile` so it travels with the object and survives
    ``model_copy()`` calls — eliminating the need for an identity-keyed cache.
    """

    model_config = ConfigDict(frozen=True)

    has_bom: bool = False
    """True if the source file began with a UTF-8 byte-order mark."""

    crlf: bool = False
    """True if the source file used CRLF line endings."""

    trailing_blank: bool = False
    """True if the source file ended with a blank line after the last cue."""


# ── Subtitle cue ─────────────────────────────────────────────────────────────

class SubtitleCue(BaseModel):
    """A single subtitle cue with millisecond-precision timing.

    ``lines`` stores the raw SRT text including any markup tags.
    ``char_counts``, ``total_chars``, and ``cps`` operate on visible text
    (markup stripped) so they accurately reflect reading speed.
    """

    model_config = ConfigDict(frozen=True)

    index: int
    """1-based cue sequence number as found in the SRT file."""

    start_ms: int
    """Cue start time in milliseconds from the beginning of the media."""

    end_ms: int
    """Cue end time in milliseconds from the beginning of the media."""

    lines: list[str]
    """Raw SRT text lines (markup intact, for byte-identical write-back)."""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_ms(self) -> int:
        """Duration of the cue in milliseconds."""
        return self.end_ms - self.start_ms

    @computed_field  # type: ignore[prop-decorator]
    @property
    def display_char_counts(self) -> list[int]:
        """Visible character count per line, weighted by East Asian display width.

        Wide (W) and Fullwidth (F) characters count as 2.
        All other characters count as 1.
        """
        import unicodedata
        counts = []
        for line in self.lines:
            visible = _strip_markup(line).rstrip()
            count = 0
            for char in visible:
                width = unicodedata.east_asian_width(char)
                count += 2 if width in ("W", "F") else 1
            counts.append(count)
        return counts

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_display_chars(self) -> int:
        """Total visible display characters across all lines."""
        return sum(self.display_char_counts)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cps_display(self) -> float:
        """Characters per second reading speed based on display width.

        Returns ``0.0`` for zero-duration or negative-duration cues.
        """
        if self.duration_ms <= 0:
            return 0.0
        return self.total_display_chars / (self.duration_ms / 1000.0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def char_counts(self) -> list[int]:
        """Visible character count per line.

        Trailing whitespace and SRT markup tags are excluded.
        Leading whitespace (indentation visible to the viewer) is counted.
        """
        return [len(_strip_markup(line).rstrip()) for line in self.lines]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_chars(self) -> int:
        """Total visible characters across all lines."""
        return sum(self.char_counts)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cps(self) -> float:
        """Characters per second reading speed (visible characters only).

        Returns ``0.0`` for zero-duration or negative-duration cues.
        """
        if self.duration_ms <= 0:
            return 0.0
        return self.total_chars / (self.duration_ms / 1000.0)


# ── Subtitle file ─────────────────────────────────────────────────────────────

class SubtitleFile(BaseModel):
    """A parsed subtitle file containing an ordered sequence of cues."""

    model_config = ConfigDict(frozen=True)

    cues: list[SubtitleCue]
    """Ordered list of subtitle cues."""

    language: str = "und"
    """BCP-47 language code. Defaults to ``'und'`` (undetermined)."""

    source_path: str | None = None
    """Original file path, if the file was loaded from disk."""

    srt_dialect: SrtDialect | None = None
    """SRT formatting facts recorded at parse time for byte-identical write-back.

    ``None`` for programmatically constructed files; ``write_srt`` treats ``None``
    as a default LF dialect with no BOM and no trailing blank line.
    """

    is_canonical: bool = True
    """``False`` if ``write_srt`` would not reproduce the original input bytes.

    Set during parsing when any block is skipped, normalised, or when re-serialising
    the result does not equal the original bytes.
    """

    skipped_blocks: int = 0
    """Number of cue blocks that were skipped during parsing (malformed or unparseable)."""

    parse_anomalies: list[str] = Field(default_factory=list)
    """Human-readable descriptions of every normalisation or skip performed during parsing."""
