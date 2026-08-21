"""Passline ADK output schemas.

Pydantic v2 models used as ADK ``output_schema`` for leaf agents.
All validation follows project conventions (model_validator, model_config,
.model_dump() / .model_validate()).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ── QC Agent assessment schema ────────────────────────────────────────────────

class QcAssessment(BaseModel):
    """Structured output for the existing QC agent leaf.

    Mirrors the JSON contract described in qc_agent.py's instruction string.
    Used as ``output_schema`` on the qc_agent so ADK enforces structure.
    """

    model_config = {"frozen": True}

    assessment: Literal["pass", "flag", "repair-needed"]
    """Overall assessment verdict."""

    reason: str
    """One-sentence explanation of the assessment."""

    suggested_text: Optional[str] = None
    """Proposed replacement text (only when assessment == 'repair-needed')."""


# ── Language checker schemas ──────────────────────────────────────────────────

class LanguageFlag(BaseModel):
    """One language-level flag raised by the language checker agent."""

    model_config = {"frozen": True}

    cue_index: int
    """1-based cue sequence number (matches SubtitleCue.index)."""

    confidence: float = Field(ge=0.0, le=1.0)
    """Confidence score between 0.0 and 1.0."""

    rule_ref: str
    """Reference to the specific rule from the built-in rule table (e.g. 'MT01')."""

    explanation: str
    """One-line human-readable explanation of the flag."""

    suggested_text: Optional[str] = None
    """Proposed replacement text (may be None if no repair is suggested)."""

    @field_validator("confidence")
    @classmethod
    def _confidence_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {v}")
        return v


class LanguageCheckerOutput(BaseModel):
    """Structured output for the language checker leaf agent.

    The ADK ``output_schema`` on the language checker agent enforces this shape.
    """

    model_config = {"frozen": True}

    flags: list[LanguageFlag] = Field(default_factory=list)
    """List of language-level flags found. Empty list means no issues detected."""

    language: str
    """ISO language code of the checked subtitle file (e.g. 'en', 'fr', 'de')."""

    checked_cues: int = Field(ge=0)
    """Number of cues examined by the language checker."""
