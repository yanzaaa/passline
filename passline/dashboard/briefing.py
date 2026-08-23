from __future__ import annotations

import io
import os
import wave
import logging
from typing import Any

from google.genai import Client as GenaiClient
from google.genai import types

logger = logging.getLogger(__name__)


class BriefingError(Exception):
    """Raised when TTS briefing generation fails."""
    pass


class BriefingGenerator:
    """Generates a three-voice spoken briefing using Google GenAI TTS."""

    def __init__(self) -> None:
        self.enabled = os.getenv("PASSLINE_TTS_ENABLED", "true").lower() == "true"
        try:
            self.max_generations = int(os.getenv("PASSLINE_TTS_MAX_GENERATIONS", "50"))
        except ValueError:
            self.max_generations = 50
        self.generation_count = 0

    def generate_briefing(self, report: dict[str, Any], language_findings: list[dict[str, Any]]) -> bytes:
        """Generate a concatenated three-voice WAV briefing.

        Voice 1: Puck (Desk Chief)
        Voice 2: Charon (Language Specialist)
        Voice 3: Kore (Verifier)
        """
        if not self.enabled:
            raise BriefingError("TTS is disabled by configuration")
        if self.generation_count >= self.max_generations:
            raise BriefingError(f"TTS generation limit reached ({self.max_generations})")

        delivery_id = report.get("delivery_id", "unknown")
        verdict = report.get("verdict", "unknown")
        language_code = report.get("language", "und")

        lang_map = {
            "en": "English",
            "en-us": "English",
            "fr": "French",
            "fr-fr": "French",
            "de": "German",
            "de-de": "German",
        }
        lang_name = lang_map.get(language_code.lower(), "undetermined language")

        vf = report.get("violations_found", {})
        total_violations = vf.get("timing", 0) + vf.get("format", 0) + vf.get("language", 0)
        repairs_applied = report.get("repairs_applied", 0)
        remaining_violations = vf.get("remaining_after_repair", 0)

        # Voice 1 (desk chief)
        cleared_status = "CLEARED" if verdict == "passed" else "HELD"
        script1 = (
            f"Delivery {delivery_id}, language {lang_name}. "
            f"Result is {cleared_status}. "
            f"{total_violations} violations found, {repairs_applied} repairs applied."
        )

        # Voice 2 (language specialist)
        if language_findings:
            sorted_flags = sorted(language_findings, key=lambda f: f.get("confidence", 0), reverse=True)
            notable = sorted_flags[0]
            rule_ref = notable.get("rule_ref") or notable.get("rule") or "unknown"
            conf = int(notable.get("confidence", 0) * 100)
            explanation = notable.get("explanation") or notable.get("reason") or "No explanation provided"
            script2 = (
                f"Language specialist report. A notable language flag was detected with rule code {rule_ref} "
                f"and confidence {conf} percent. Reason: {explanation}."
            )
        else:
            script2 = "Language specialist report. No language flags detected."

        # Voice 3 (verifier)
        release_status = "authorized for release" if remaining_violations == 0 else "held pending review"
        script3 = (
            f"Verifier sign-off. {remaining_violations} remaining violations. "
            f"Delivery is {release_status}."
        )

        logger.info("Generating spoken briefing for %s (V1: Puck, V2: Charon, V3: Kore)", delivery_id)

        try:
            client = GenaiClient()
        except Exception as exc:
            logger.error("Failed to initialize GenaiClient: %s", exc)
            raise BriefingError(f"GenaiClient init failed: {exc}")

        wavs: list[bytes] = []
        voices = [("Puck", script1), ("Charon", script2), ("Kore", script3)]

        for voice_name, text in voices:
            try:
                speech_config = types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_name
                        )
                    )
                )

                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=text,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=speech_config
                    )
                )

                # Extract audio bytes
                audio_bytes = response.candidates[0].content.parts[0].inline_data.data
                wavs.append(audio_bytes)
            except Exception as exc:
                logger.error("TTS generation failed for voice %s: %s", voice_name, exc)
                raise BriefingError(f"TTS generation failed for voice {voice_name}: {exc}")

        try:
            merged = self._merge_wavs(wavs)
            self.generation_count += 1
            return merged
        except Exception as exc:
            logger.error("Failed to merge WAV files: %s", exc)
            raise BriefingError(f"WAV merge failed: {exc}")

    def _merge_wavs(self, wav_bytes_list: list[bytes]) -> bytes:
        if not wav_bytes_list:
            return b""
        if len(wav_bytes_list) == 1:
            return wav_bytes_list[0]
        
        output = io.BytesIO()
        with wave.open(output, "wb") as out_wav:
            first_wav_io = io.BytesIO(wav_bytes_list[0])
            with wave.open(first_wav_io, "rb") as in_wav:
                params = in_wav.getparams()
                out_wav.setparams(params)
            
            for b in wav_bytes_list:
                in_wav_io = io.BytesIO(b)
                with wave.open(in_wav_io, "rb") as in_wav:
                    out_wav.writeframes(in_wav.readframes(in_wav.getnframes()))
                    
        return output.getvalue()
