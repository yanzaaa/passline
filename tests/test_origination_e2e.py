import pytest
from fastapi.testclient import TestClient
from passline.dashboard.app import app
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

@pytest.fixture
def client():
    return TestClient(app)

def test_originate_rejects_unsupported_mime(client):
    response = client.post("/api/originate", data={"source_language": "en"}, files={"file": ("test.txt", b"hello", "text/plain")})
    assert response.status_code == 415

def test_originate_missing_source_language(client):
    response = client.post("/api/originate", files={"file": ("test.webm", b"hello", "audio/webm")})
    assert response.status_code == 400

@patch("passline.origination.orchestrator.transcribe_media", new_callable=AsyncMock)
def test_originate_status_lifecycle(mock_transcribe, client):
    mock_transcribe.return_value = []
    
    response = client.post("/api/originate", data={"source_language": "en"}, files={"file": ("test.webm", b"hello", "audio/webm")})
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    
    res = client.get(f"/api/originate/status/{job_id}")
    assert res.status_code == 200
    assert res.json()["status"] in ["pending", "transcribing", "building_cues", "translating", "completed"]

@patch("passline.origination.orchestrator.transcribe_media", new_callable=AsyncMock)
@patch("passline.origination.orchestrator.translate_cues", new_callable=AsyncMock)
@patch("passline.origination.orchestrator.PipelineRunner.run_delivery", new_callable=AsyncMock)
def test_originate_submits_all_target_languages(mock_run, mock_translate, mock_transcribe, client):
    mock_transcribe.return_value = []
    mock_translate.return_value = MagicMock()
    mock_translate.return_value.language = "en"
    mock_translate.return_value.cues = []
    
    response = client.post("/api/originate", data={"source_language": "en"}, files={"file": ("test.webm", b"hello", "audio/webm")})
    assert response.status_code == 202
    
@patch("passline.origination.orchestrator.asyncio.sleep", new_callable=AsyncMock)
@patch("passline.origination.orchestrator.transcribe_media", new_callable=AsyncMock)
@patch("passline.origination.orchestrator.translate_cues", new_callable=AsyncMock)
@patch("passline.origination.orchestrator.PipelineRunner.run_delivery", new_callable=AsyncMock)
def test_originate_submits_and_handoff_language(mock_run, mock_translate, mock_transcribe, mock_sleep, client):
    mock_transcribe.return_value = []
    from passline.models.subtitle import SubtitleFile
    mock_translate.return_value = SubtitleFile(cues=tuple(), language="en", parse_anomalies=tuple())
    
    response = client.post("/api/originate", data={"source_language": "en"}, files={"file": ("test.webm", b"hello", "audio/webm")})
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    
    import time
    for _ in range(50):
        res = client.get(f"/api/originate/status/{job_id}")
        if res.json()["status"] in ("completed", "failed"):
            break
        time.sleep(0.1)
        
    assert mock_run.call_count == 8
    languages = [call.kwargs["language"] for call in mock_run.call_args_list]
    assert set(languages) == set(["en", "fr", "de", "es", "ru", "pt", "zh", "fa"])

@patch("passline.origination.orchestrator.asyncio.sleep", new_callable=AsyncMock)
@patch("passline.origination.orchestrator.PipelineRunner.run_delivery", new_callable=AsyncMock)
def test_reset_clears_origination_state(mock_run, mock_sleep, client):
    response = client.post("/api/originate", data={"source_language": "en"}, files={"file": ("test.webm", b"hello", "audio/webm")})
    job_id = response.json()["job_id"]
    client.post("/api/reset")
    
    res = client.get(f"/api/originate/status/{job_id}")
    assert res.status_code == 404
