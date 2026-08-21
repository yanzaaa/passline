"""QC Agent — Google ADK LlmAgent stub for subtitle quality control.

Uses Gemini via Google ADK exclusively; no other AI provider is used.
"""
from __future__ import annotations

from google.adk import Agent  # google-adk 2.7.1 — LlmAgent public alias


_INSTRUCTION = """
You are a subtitle quality-control specialist for streaming delivery workflows.

Your role is to review subtitle cues flagged by the deterministic rule engine and
provide language-level judgments on:
- Readability and naturalness of the text
- Appropriate reading speed for the target audience
- Consistency with surrounding cues

You do NOT perform arithmetic or timing calculations — those are handled by the
deterministic rule engine. You provide only language-level assessments.

When asked to evaluate a cue, respond with a structured JSON object containing:
  "assessment": "pass" | "flag" | "repair_needed"
  "reason": str
  "suggested_text": str | null  (only when assessment is "repair_needed")
""".strip()


def build_qc_agent() -> Agent:
    """Construct the Passline QC agent (no model call at construction time)."""
    return Agent(
        name="qc_agent",
        model="gemini-2.0-flash",
        instruction=_INSTRUCTION,
        description="Subtitle quality-control agent for Passline streaming delivery workflows.",
    )
