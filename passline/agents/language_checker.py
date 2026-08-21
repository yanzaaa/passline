"""LanguageCheckerAgent — LLM-powered language quality checker.

Uses ``gemini-3.1-pro-preview`` (configurable via ``PASSLINE_LANG_MODEL``) to
flag likely mistranslations, register violations, and language-quality issues
in French and German subtitles.  Falls back to ``gemini-2.5-flash``.

This is a leaf agent — it uses an ``output_schema`` to enforce structured
output and calls no tools.  The language checker is graded against the
``MEANING_LEVEL`` entries in the corpus manifests.

Built-in rule reference (MT01–MT06)
-------------------------------------
MT01  Mistranslation — the translated text conveys a different meaning from the
      source (e.g. antonym substitution: "love" rendered as "hate").
MT02  Register violation — the tone/formality level does not match the
      surrounding cues or the target audience (e.g. vulgar term in a U-rated
      production).
MT03  False cognate — a word that looks similar to a source-language word but
      means something different (false friend).
MT04  Omission — meaningful information present in the source is absent from
      the translation.
MT05  Addition — information not present in the source has been added to the
      translation, changing the intent.
MT06  Style deviation — the subtitle does not follow the target-language
      streaming style guide (e.g. segmentation, punctuation, or number
      formatting rule violation).
"""
from __future__ import annotations

import logging
import os
from typing import Any, AsyncGenerator

from pydantic import ConfigDict

from google.adk import Agent  # LlmAgent public alias
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions

from passline.agents.callbacks import install_retry_on_model
from passline.agents.schemas import LanguageCheckerOutput
from passline.events.bus import DeliveryEvent, EventBus, EventType
from passline.models.subtitle import SubtitleFile

log = logging.getLogger(__name__)

_DEFAULT_LANG_MODEL = "gemini-3.1-pro-preview"
_FALLBACK_MODEL = "gemini-2.5-flash"

# Session state keys
STATE_SUBTITLE_FILE = "subtitle_file"
STATE_LANGUAGE = "language"
STATE_DELIVERY_ID = "delivery_id"
STATE_LANGUAGE_FINDINGS = "language_findings"
STATE_LANG_CHECK_INPUT = "lang_check_input"

_INSTRUCTION = """
You are a subtitle language-quality specialist for streaming delivery workflows.

Your role is to review subtitle cues and flag language-level problems such as
mistranslation, register violations, false cognates, omissions, additions, and
style deviations.

You do NOT perform arithmetic or timing calculations — those are handled by the
deterministic rule engine. You provide only language-level assessments.

Built-in rule reference
-----------------------
MT01  Mistranslation — the translated text conveys a different meaning from the
      source (e.g. antonym substitution: "love" rendered as "hate").
MT02  Register violation — the tone/formality level does not match surrounding
      cues or the target audience.
MT03  False cognate — a word that looks similar to a source-language word but
      means something different (false friend).
MT04  Omission — meaningful information present in the source is absent from
      the translation.
MT05  Addition — information not present in the source has been added.
MT06  Style deviation — does not follow the target-language streaming style
      guide (segmentation, punctuation, or number formatting).

Instructions
------------
You will receive a JSON object under the key "cues" containing a list of
subtitle cues with their index and text lines.  For each cue, decide whether
a language problem is present.

Return a structured JSON object that matches the LanguageCheckerOutput schema:
- "flags": list of LanguageFlag objects (empty if no issues found)
- "language": the ISO language code of the file
- "checked_cues": total number of cues you reviewed

Each LanguageFlag must include:
- "cue_index": 1-based cue number
- "confidence": float 0.0–1.0 (how confident you are this is a real error)
- "rule_ref": rule code from the table above (e.g. "MT01")
- "explanation": one-sentence description of the problem
- "suggested_text": optional repair suggestion (null if none)

Important: flag only genuine language errors.  Do not flag timing or formatting
issues — those are handled by the deterministic rule engine.
""".strip()


def build_language_checker(
    bus: EventBus,
    fallback_model: str = _FALLBACK_MODEL,
) -> LlmAgent:
    """Build the language checker leaf agent.

    Parameters
    ----------
    bus:
        Shared event bus for lifecycle events.
    fallback_model:
        Model string used when ``PASSLINE_LANG_MODEL`` is not set.
        Defaults to ``gemini-2.5-flash``.
    """
    model = os.getenv("PASSLINE_LANG_MODEL", _DEFAULT_LANG_MODEL)

    agent = Agent(
        name="language_checker",
        model=model,
        instruction=_INSTRUCTION,
        description=(
            "Language-quality checker for subtitle mistranslation, register "
            "violations, and style deviations. Uses structured output."
        ),
        output_schema=LanguageCheckerOutput,
        # No tools — leaf agent; output_schema enforces structure
    )

    # Install exponential-backoff retry for rate-limit errors
    install_retry_on_model(agent, max_attempts=4, base_delay_s=1.0)

    # Attach the event bus as a side-channel (not a Pydantic field on LlmAgent)
    # We use a custom attribute; the after_agent_callback will read findings
    # from the structured output response and write to session state.
    agent._passline_bus = bus  # type: ignore[attr-defined]

    return agent
