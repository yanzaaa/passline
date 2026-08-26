import json
from passline.origination.cue_builder import TranscriptSegment
from google.genai import Client, types

class TranscriptionError(Exception):
    pass

async def transcribe_media(media_bytes: bytes, mime_type: str, client: Client) -> list[TranscriptSegment]:
    if len(media_bytes) > 20 * 1024 * 1024:
        raise TranscriptionError("File exceeds the 20MB limit for inline processing.")
        
    prompt = "Please transcribe this media file. Return ONLY a JSON array of segment objects. Each object must have exactly three keys: 'word' (a string), 'start_s' (a float), and 'end_s' (a float)."
    
    response = await client.aio.models.generate_content(
        model="gemini-3-flash-preview",
        contents=[
            types.Part.from_bytes(data=media_bytes, mime_type=mime_type),
            prompt
        ],
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
        
    data = json.loads(text.strip())
    
    segments = []
    for d in data:
        segments.append(TranscriptSegment(
            word=d["word"],
            start_s=float(d["start_s"]),
            end_s=float(d["end_s"])
        ))
    return segments
