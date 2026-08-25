import pytest
from passline.origination.transcriber import transcribe_media, TranscriptionError
from passline.origination.cue_builder import TranscriptSegment
import asyncio
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.anyio
async def test_transcribe_oversized_raises():
    client = MagicMock()
    with pytest.raises(TranscriptionError):
        await transcribe_media(b'0' * (21 * 1024 * 1024), "audio/webm", client)

@pytest.mark.anyio
async def test_transcribe_returns_timestamps():
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.text = '[{"word": "Hello", "start_s": 0.5, "end_s": 0.8}]'
    client.aio.models.generate_content.return_value = mock_resp
    
    segments = await transcribe_media(b'1234', "audio/webm", client)
    assert len(segments) == 1
    assert segments[0].start_s < segments[0].end_s
