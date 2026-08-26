import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

@pytest.mark.anyio
@patch("passline.origination.orchestrator.Client")
@patch("passline.origination.orchestrator.translate_cues", new_callable=AsyncMock)
@patch("passline.origination.orchestrator.transcribe_media", new_callable=AsyncMock)
@patch("passline.origination.orchestrator.PipelineRunner.run_delivery", new_callable=AsyncMock)
async def test_originate_submits_and_handoff_language(mock_run, mock_transcribe, mock_translate, mock_client, tmp_path):
    mock_transcribe.return_value = []
    from passline.models.subtitle import SubtitleFile
    mock_translate.return_value = SubtitleFile(cues=tuple(), language="en", parse_anomalies=tuple())
    
    from passline.origination.orchestrator import OriginationJob
    from passline.events.bus import EventBus
    
    bus = EventBus(log_path=tmp_path / "events.jsonl")
    job = OriginationJob("test-job", bus)
    
    await job.run(b"fake audio", "audio/webm", "en")
    
    assert mock_run.call_count == 8
    languages = [call.kwargs["language"] for call in mock_run.call_args_list]
    assert set(languages) == set(["en", "fr", "de", "es", "ru", "pt", "zh", "fa"])
