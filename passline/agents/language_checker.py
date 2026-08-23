"""LanguageCheckerAgent — LLM-powered language quality checker.

Reimplemented as a :class:`~google.adk.agents.base_agent.BaseAgent` that calls
the Gemini API directly via ``google-genai`` (not through ADK's LlmAgent),
giving full control over structured output and session state writes.

The agent:
1. Emits ``station.working`` with the correct fixture vocabulary
2. Reads the current ``subtitle_file`` from ADK session state
3. Sends all cue text to Gemini with ``response_schema=LanguageCheckerOutput``
4. Writes the parsed flags to ``language_findings`` in session state
5. Emits one ``qc.violation`` per flag
6. Emits ``station.ready``
7. Yields one ADK :class:`~google.adk.events.event.Event` with the state delta

Retry on HTTP 429 / quota exceeded is implemented via ``tenacity`` around the
async Gemini API call.

Built-in rule reference (MT01–MT06)
-------------------------------------
MT01  Mistranslation — the translated text conveys a different meaning from the
      source (e.g. antonym substitution: "love" rendered as "hate").
MT02  Register violation — the tone/formality level does not match the
      surrounding cues or the target audience.
MT03  False cognate — a word that looks similar to a source-language word but
      means something different (false friend).
MT04  Omission — meaningful information present in the source is absent from
      the translation.
MT05  Addition — information not present in the source has been added,
      changing the intent.
MT06  Style deviation — the subtitle does not follow the target-language
      streaming style guide (e.g. segmentation, punctuation, or number
      formatting rule violation).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncGenerator, Optional

from pydantic import ConfigDict

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions

from passline.agents.schemas import LanguageCheckerOutput, LanguageFlag
from passline.events.bus import DeliveryEvent, EventBus, EventType
from passline.models.subtitle import SubtitleFile

log = logging.getLogger(__name__)

_DEFAULT_LANG_MODEL = "gemini-3.1-pro-preview"

# Session state keys
STATE_SUBTITLE_FILE = "subtitle_file"
STATE_LANGUAGE = "language"
STATE_DELIVERY_ID = "delivery_id"
STATE_LANGUAGE_FINDINGS = "language_findings"

_STATION_ID = "language"
_STATION_NAME = "Language"

_SYSTEM_PROMPT = """You are a subtitle language-quality specialist for streaming delivery workflows.

Your role is to review subtitle cues and flag language-level problems such as
mistranslation, register violations, false cognates, omissions, additions, and
style deviations.

You do NOT perform arithmetic or timing calculations — those are handled by a
separate deterministic rule engine. You provide only language-level assessments.

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

You will receive a JSON array of subtitle cues under the key "cues".
Each cue has:
  - "index": 1-based cue number
  - "lines": list of text lines

Return a JSON object matching this schema:
  {
    "flags": [
      {
        "cue_index": <int>,
        "confidence": <float 0.0-1.0>,
        "rule_ref": "<MT01|MT02|MT03|MT04|MT05|MT06>",
        "explanation": "<one-sentence description>",
        "suggested_text": "<optional repair or null>"
      }
    ],
    "language": "<ISO language code>",
    "checked_cues": <int>
  }

Flag only genuine language errors. Do not flag timing or formatting issues."""


def _build_prompt(subtitle_file: SubtitleFile) -> str:
    cues_payload = [
        {"index": c.index, "lines": c.lines}
        for c in subtitle_file.cues
    ]
    return json.dumps({"cues": cues_payload}, ensure_ascii=False)


async def _call_genai_with_retry(
    client: Any,
    model: str,
    prompt: str,
    language: str,
) -> LanguageCheckerOutput:
    """Call the Gemini API with retry on 429. Returns parsed LanguageCheckerOutput."""
    from google.genai import types
    from google.genai.errors import ClientError

    try:
        from tenacity import (
            retry, stop_after_attempt, wait_exponential, retry_if_exception,
        )
        def _is_rate_limit(exc: BaseException) -> bool:
            return isinstance(exc, ClientError) and getattr(exc, "code", 0) == 429

        @retry(
            retry=retry_if_exception(_is_rate_limit),
            wait=wait_exponential(multiplier=1, min=1, max=30),
            stop=stop_after_attempt(4),
            reraise=True,
        )
        async def _call() -> LanguageCheckerOutput:
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=LanguageCheckerOutput,
                system_instruction=_SYSTEM_PROMPT,
            )
            response = await client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
            raw = json.loads(response.text)
            return LanguageCheckerOutput.model_validate(raw)

        return await _call()

    except Exception:
        # If tenacity not available or other error, try once without retry
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=LanguageCheckerOutput,
            system_instruction=_SYSTEM_PROMPT,
        )
        response = await client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
        raw = json.loads(response.text)
        return LanguageCheckerOutput.model_validate(raw)


class LanguageCheckerAgent(BaseAgent):
    """ADK BaseAgent that calls Gemini directly for language-quality checking.

    Constructor parameters
    ----------------------
    bus:
        Shared event bus for lifecycle events.
    genai_client:
        Optional pre-built ``google.genai.Client``.  If None, a client is
        built lazily from environment variables (``GOOGLE_API_KEY`` or
        ``GOOGLE_CLOUD_PROJECT`` / ``GOOGLE_CLOUD_LOCATION``).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    bus: EventBus
    genai_client: Optional[Any] = None

    def _get_client(self) -> Any:
        if self.genai_client is not None:
            return self.genai_client
        # Build lazily from environment
        from google import genai
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        api_key = os.getenv("GOOGLE_API_KEY")
        if project:
            return genai.Client(vertexai=True, project=project, location=location)
        elif api_key:
            return genai.Client(api_key=api_key)
        else:
            return genai.Client(api_key="not-set")  # Allows import without crashing

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        delivery_id: str = ctx.session.state.get(STATE_DELIVERY_ID, "")
        language: str = ctx.session.state.get(STATE_LANGUAGE, "und")
        subtitle_file_dict = ctx.session.state.get(STATE_SUBTITLE_FILE)

        self.bus.emit(DeliveryEvent(
            event_type=EventType.STATION_WORKING,
            delivery_id=delivery_id,
            language=language,
            details={"station_id": _STATION_ID, "station_name": _STATION_NAME},
        ))

        if subtitle_file_dict is None:
            log.warning("LanguageCheckerAgent: no subtitle_file in state — skipping")
            self.bus.emit(DeliveryEvent(
                event_type=EventType.STATION_READY,
                delivery_id=delivery_id,
                language=language,
                details={"station_id": _STATION_ID, "station_name": _STATION_NAME, "findings": 0},
            ))
            yield Event(
                author=self.name,
                actions=EventActions(state_delta={STATE_LANGUAGE_FINDINGS: []}),
            )
            return

        subtitle_file = SubtitleFile.model_validate(subtitle_file_dict)
        prompt = _build_prompt(subtitle_file)
        model_name = os.getenv("PASSLINE_LANG_MODEL", _DEFAULT_LANG_MODEL)
        client = self._get_client()

        output: LanguageCheckerOutput | None = None
        try:
            output = await _call_genai_with_retry(client, model_name, prompt, language)
        except Exception as exc:
            log.warning("LanguageCheckerAgent: LLM call failed — %s", exc)
            output = LanguageCheckerOutput(flags=[], language=language, checked_cues=0)

        flags = output.flags if output else []

        # Emit one QC_VIOLATION per flag
        for flag in flags:
            self.bus.emit(DeliveryEvent(
                event_type=EventType.QC_VIOLATION,
                delivery_id=delivery_id,
                language=language,
                details={
                    "rule":        flag.rule_ref,
                    "cue":         flag.cue_index,
                    "value":       flag.confidence,
                    "threshold":   0.0,
                    "severity":    "WARNING",
                    "explanation": flag.explanation,
                    "checker":     "language",
                },
            ))

        self.bus.emit(DeliveryEvent(
            event_type=EventType.STATION_READY,
            delivery_id=delivery_id,
            language=language,
            details={
                "station_id": _STATION_ID,
                "station_name": _STATION_NAME,
                "findings": len(flags),
            },
        ))

        log.debug("LanguageCheckerAgent: %d language findings", len(flags))

        yield Event(
            author=self.name,
            actions=EventActions(state_delta={
                STATE_LANGUAGE_FINDINGS: [f.model_dump() for f in flags],
            }),
        )


def build_language_checker(
    bus: EventBus,
    genai_client: Any = None,
) -> LanguageCheckerAgent:
    """Build the language checker agent.

    Parameters
    ----------
    bus:
        Shared event bus for lifecycle events.
    genai_client:
        Optional pre-built ``google.genai.Client``.  Passed through to
        ``LanguageCheckerAgent``; if None the agent builds one lazily from env.
    """
    return LanguageCheckerAgent(
        name="language_checker",
        bus=bus,
        genai_client=genai_client,
    )
