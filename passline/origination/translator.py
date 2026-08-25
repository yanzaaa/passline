import os
import json
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from passline.models.subtitle import SubtitleFile, SubtitleCue
from google.genai.errors import APIError
from google.genai import Client

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(APIError)
)
async def translate_cues(sf: SubtitleFile, target_language: str, client: Client) -> SubtitleFile:
    """Translates a SubtitleFile into target_language using Gemini."""
    if sf.language == target_language:
        return sf
        
    prompt = f"Translate the following subtitle cues into the BCP-47 language code '{target_language}'. Maintain the exact same number of cues and preserve the indexing and timecodes. Return ONLY valid JSON as a list of objects with 'index', 'start_ms', 'end_ms', and 'lines' (a list of strings)."
    
    source_json = []
    for cue in sf.cues:
        source_json.append({
            "index": cue.index,
            "start_ms": cue.start_ms,
            "end_ms": cue.end_ms,
            "lines": cue.lines,
        })
        
    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=[prompt, json.dumps(source_json, indent=2)],
        config={
            "response_mime_type": "application/json",
            "temperature": 0.1
        }
    )
    
    text = response.text
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
        
    translated_data = json.loads(text.strip())
    
    new_cues = []
    for td in translated_data:
        new_cues.append(SubtitleCue(
            index=td["index"],
            start_ms=td["start_ms"],
            end_ms=td["end_ms"],
            lines=td["lines"]
        ))
        
    return SubtitleFile(
        cues=tuple(new_cues),
        language=target_language,
        parse_anomalies=sf.parse_anomalies
    )