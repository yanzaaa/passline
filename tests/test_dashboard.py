"""Dashboard endpoint tests.

All tests run in-process using httpx.ASGITransport with the FastAPI app.
No real network calls, no LLM calls.  Each test gets a fresh temporary
event log and approval queue to avoid state leakage between tests.

Covered endpoints:
  GET  /api/history
  GET  /api/events  (SSE backfill)
  POST /api/replay
  POST /api/stop
  POST /api/reset
  GET  /api/demo/{lang}
  GET  /api/download/{delivery_id}
  GET  /api/queue
  POST /api/queue/{id}/approve
  POST /api/queue/{id}/reject
  POST /api/upload (pipeline mocked)
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import httpx

from passline.events.bus import DeliveryEvent, EventBus, EventType
from passline.pipeline.approval import ApprovalQueue


# ─────────────────────────────────────────────────────────────────────────────
# App fixture — fresh state per test
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_log(tmp_path: Path) -> Path:
    return tmp_path / "events.jsonl"


@pytest.fixture
def fresh_app(tmp_log: Path):
    """Patch the app module's bus and log path for test isolation."""
    import passline.dashboard.app as app_module

    old_bus = app_module.bus
    old_log = app_module._LOG_PATH
    old_store = dict(app_module._repaired_store)

    new_bus = EventBus(tmp_log)
    app_module.bus = new_bus
    app_module._LOG_PATH = tmp_log
    app_module._repaired_store.clear()
    app_module._approval_queue.set_bus(new_bus)

    yield app_module.app

    # Restore originals
    app_module.bus = old_bus
    app_module._LOG_PATH = old_log
    app_module._repaired_store.clear()
    app_module._repaired_store.update(old_store)


@pytest.fixture
async def client(fresh_app):
    transport = httpx.ASGITransport(app=fresh_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ─────────────────────────────────────────────────────────────────────────────
# /api/history
# ─────────────────────────────────────────────────────────────────────────────

class TestHistory:
    @pytest.mark.anyio
    async def test_history_empty_initially(self, client):
        r = await client.get("/api/history")
        assert r.status_code == 200
        assert r.json() == []

    @pytest.mark.anyio
    async def test_history_returns_emitted_events(self, client):
        import passline.dashboard.app as app_module
        app_module.bus.emit(DeliveryEvent(
            event_type=EventType.SUBTITLE_SUBMITTED,
            delivery_id="d1",
            language="en",
            details={"test": True},
        ))
        r = await client.get("/api/history")
        assert r.status_code == 200
        events = r.json()
        assert len(events) >= 1
        assert any(e.get("delivery_id") == "d1" for e in events)


# ─────────────────────────────────────────────────────────────────────────────
# /api/replay + /api/stop + /api/reset
# ─────────────────────────────────────────────────────────────────────────────

class TestReplay:
    @pytest.mark.anyio
    async def test_replay_starts(self, client):
        r = await client.post("/api/replay")
        assert r.status_code == 200
        assert r.json()["status"] == "started"
        await client.post("/api/stop")

    @pytest.mark.anyio
    async def test_stop_returns_stopped(self, client):
        await client.post("/api/replay")
        r = await client.post("/api/stop")
        assert r.status_code == 200
        assert r.json()["status"] == "stopped"

    @pytest.mark.anyio
    async def test_reset_clears_log(self, client, tmp_log: Path):
        import passline.dashboard.app as app_module
        app_module.bus.emit(DeliveryEvent(
            event_type=EventType.SUBTITLE_SUBMITTED,
            delivery_id="x",
            language="en",
            details={},
        ))
        r = await client.get("/api/history")
        assert len(r.json()) >= 1

        r = await client.post("/api/reset")
        assert r.status_code == 200
        assert r.json()["status"] == "reset"
        assert tmp_log.read_text() == ""


# ─────────────────────────────────────────────────────────────────────────────
# /api/demo/{lang}
# ─────────────────────────────────────────────────────────────────────────────

class TestDemoEndpoint:
    @pytest.mark.anyio
    async def test_demo_en_returns_srt(self, client):
        r = await client.get("/api/demo/en")
        assert r.status_code == 200
        assert len(r.content) > 100

    @pytest.mark.anyio
    async def test_demo_fr_returns_srt(self, client):
        r = await client.get("/api/demo/fr")
        assert r.status_code == 200
        assert len(r.content) > 100

    @pytest.mark.anyio
    async def test_demo_de_returns_srt(self, client):
        r = await client.get("/api/demo/de")
        assert r.status_code == 200
        assert len(r.content) > 100

    @pytest.mark.anyio
    async def test_demo_unknown_lang_404(self, client):
        r = await client.get("/api/demo/xx")
        assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# /api/download/{delivery_id}
# ─────────────────────────────────────────────────────────────────────────────

class TestDownloadEndpoint:
    @pytest.mark.anyio
    async def test_download_missing_404(self, client):
        r = await client.get("/api/download/nonexistent-id")
        assert r.status_code == 404

    @pytest.mark.anyio
    async def test_download_stored_bytes(self, client):
        import passline.dashboard.app as app_module
        app_module._repaired_store["test-del-1"] = (
            b"1\n00:00:01,000 --> 00:00:03,000\nRepaired cue.\n\n"
        )
        r = await client.get("/api/download/test-del-1")
        assert r.status_code == 200
        assert b"Repaired cue" in r.content
        assert "attachment" in r.headers.get("content-disposition", "")


# ─────────────────────────────────────────────────────────────────────────────
# /api/queue
# ─────────────────────────────────────────────────────────────────────────────

class TestQueueEndpoints:
    @pytest.fixture(autouse=True)
    def _clean_queue(self):
        from passline.pipeline.approval import approval_queue as aq
        aq._items.clear()
        yield
        aq._items.clear()

    @pytest.mark.anyio
    async def test_queue_list_empty(self, client):
        r = await client.get("/api/queue")
        assert r.status_code == 200
        assert r.json() == []

    @pytest.mark.anyio
    async def test_queue_approve(self, client):
        from passline.pipeline.approval import approval_queue as aq
        item = aq.make_item(
            delivery_id="d1", cue_index=1,
            original_text="Hello", proposed_text="Hi",
            reason="test",
        )
        aq.enqueue(item)
        r = await client.post(f"/api/queue/{item.item_id}/approve")
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

    @pytest.mark.anyio
    async def test_queue_reject(self, client):
        from passline.pipeline.approval import approval_queue as aq
        item = aq.make_item(
            delivery_id="d1", cue_index=2,
            original_text="A", proposed_text="B",
            reason="test",
        )
        aq.enqueue(item)
        r = await client.post(f"/api/queue/{item.item_id}/reject")
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

    @pytest.mark.anyio
    async def test_queue_approve_nonexistent_404(self, client):
        r = await client.post("/api/queue/does-not-exist/approve")
        assert r.status_code == 404

    @pytest.mark.anyio
    async def test_queue_reject_nonexistent_404(self, client):
        r = await client.post("/api/queue/does-not-exist/reject")
        assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# /api/upload (pipeline mocked)
# ─────────────────────────────────────────────────────────────────────────────

class TestUploadEndpoint:
    @pytest.mark.anyio
    async def test_upload_accepted(self, client):
        srt_bytes = b"1\n00:00:01,000 --> 00:00:03,000\nHello world.\n\n"
        with patch(
            "passline.pipeline.runner.PipelineRunner.run_delivery",
            new_callable=AsyncMock,
            return_value={"delivery_id": "mock-id", "verdict": "passed"},
        ):
            with patch(
                "passline.pipeline.runner.PipelineRunner.get_repaired_bytes",
                new_callable=AsyncMock,
                return_value=srt_bytes,
            ):
                r = await client.post(
                    "/api/upload",
                    files={"file": ("test.srt", srt_bytes, "text/plain")},
                )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "accepted"
        assert "delivery_id" in body

    @pytest.mark.anyio
    async def test_upload_detects_language_fr(self, client):
        srt_bytes = b"1\n00:00:01,000 --> 00:00:03,000\nBonjour.\n\n"
        with patch("passline.pipeline.runner.PipelineRunner.run_delivery",
                   new_callable=AsyncMock, return_value={"verdict": "passed"}):
            with patch("passline.pipeline.runner.PipelineRunner.get_repaired_bytes",
                       new_callable=AsyncMock, return_value=b""):
                r = await client.post(
                    "/api/upload",
                    files={"file": ("tos-fr-broken.srt", srt_bytes, "text/plain")},
                )
        assert r.status_code == 200
        assert r.json()["language"] == "fr"
