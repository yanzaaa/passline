"""Subtitle cue and file data models for Passline.

All math is deterministic Python — no LLM performs any calculations here.
"""
from __future__ import annotations

from pydantic import BaseModel, computed_field, ConfigDict


class SubtitleCue(BaseModel):
    """A single subtitle cue with millisecond-precision timing."""

    model_config = ConfigDict(frozen=True)

    index: int
    """1-based cue sequence number as found in the SRT file."""

    start_ms: int
    """Cue start time in milliseconds from the beginning of the media."""

    end_ms: int
    """Cue end time in milliseconds from the beginning of the media."""

    lines: list[str]
    """One or more text lines that compose the cue."""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_ms(self) -> int:
        """Duration of the cue in milliseconds."""
        return self.end_ms - self.start_ms

    @computed_field  # type: ignore[prop-decorator]
    @property
    def char_counts(self) -> list[int]:
        """Character count for each line (trailing whitespace stripped)."""
        return [len(line.rstrip()) for line in self.lines]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_chars(self) -> int:
        """Total characters across all lines (trailing whitespace stripped)."""
        return sum(self.char_counts)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cps(self) -> float:
        """Characters per second reading speed.

        Returns 0.0 for zero-duration cues to avoid division by zero.
        """
        if self.duration_ms <= 0:
            return 0.0
        return self.total_chars / (self.duration_ms / 1000.0)


class SubtitleFile(BaseModel):
    """A parsed subtitle file containing an ordered sequence of cues."""

    model_config = ConfigDict(frozen=True)

    cues: list[SubtitleCue]
    """Ordered list of subtitle cues."""

    language: str = "und"
    """BCP-47 language code. Defaults to 'und' (undetermined) if not provided."""

    source_path: str | None = None
    """Original file path, if the file was loaded from disk."""
