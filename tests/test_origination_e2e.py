import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from passline.dashboard.app import app
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

@pytest.mark.anyio
@patch("passline.origination.orchestrator.Client")
@patch("passline.origination.orchestrator.translate_cues", new_callable=AsyncMock)
@patch("passline.origination.orchestrator.transcribe_media", new_callable=AsyncMock)
@patch("passline.origination.orchestrator.PipelineRunner.run_delivery", new_callable=AsyncMock)
async def test_originate_submits_and_handoff_language(mock_run, mock_transcribe, mock_translate, mock_client, tmp_path, monkeypatch):
    monkeypatch.setenv("PASSLINE_PIPELINE_TIMEOUT", "0.01")
    
    mock_transcribe.return_value = []
    from passline.models.subtitle import SubtitleFile
    mock_translate.return_value = SubtitleFile(cues=tuple(), language="en", parse_anomalies=tuple())
    
    async def mock_run_delivery(*args, **kwargs):
        await asyncio.sleep(999)
        
    mock_run.side_effect = mock_run_delivery
    
    from passline.origination.orchestrator import OriginationJob
    from passline.events.bus import EventBus
    
    bus = EventBus(log_path=tmp_path / "events.jsonl")
    
    emitted_events = []
    original_emit = bus.emit
    def intercept_emit(event):
        emitted_events.append(event)
        original_emit(event)
    bus.emit = intercept_emit
    
    job = OriginationJob("test-job", bus)
    
    # We await the job run. It should complete, because it awaits the 8 language tasks, which will time out!
    await job.run(b"fake audio", "audio/webm", "en")
    
    assert job.status == "completed"
    
    # Check that 8 DELIVERY_FAILED events were emitted with reason="timeout"
    failures = [e for e in emitted_events if e.event_type == "delivery.failed" and e.details.get("reason") == "timeout"]
    assert len(failures) == 8

@patch("passline.origination.orchestrator.asyncio.sleep", new_callable=AsyncMock)
@patch("passline.origination.orchestrator.PipelineRunner.run_delivery", new_callable=AsyncMock)
def test_reset_clears_origination_state(mock_run, mock_sleep, client):
    response = client.post("/api/originate", data={"source_language": "en"}, files={"file": ("test.webm", b"hello", "audio/webm")})
    job_id = response.json()["job_id"]
    client.post("/api/reset")
    
    res = client.get(f"/api/originate/status/{job_id}")
    assert res.status_code == 404
