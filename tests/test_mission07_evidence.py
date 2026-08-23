from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from passline.events.bus import DeliveryEvent, EventBus, EventType
from passline.pipeline.approval import ApprovalQueue
from passline.dashboard.briefing import BriefingError


# ─────────────────────────────────────────────────────────────────────────────
# Test isolation fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_log(tmp_path: Path) -> Path:
    return tmp_path / "events.jsonl"


@pytest.fixture
def fresh_app(tmp_log: Path):
    """Patch the app module's singletons for test isolation."""
    import passline.dashboard.app as app_module

    old_bus = app_module.bus
    old_log = app_module._LOG_PATH
    old_store = dict(app_module._repaired_store)
    old_metadata = dict(app_module._delivery_metadata)
    old_briefing_cache = dict(app_module._briefing_cache)

    new_bus = EventBus(tmp_log)
    app_module.bus = new_bus
    app_module._LOG_PATH = tmp_log
    app_module._repaired_store.clear()
    app_module._delivery_metadata.clear()
    app_module._briefing_cache.clear()
    app_module._approval_queue.set_bus(new_bus)

    yield app_module

    # Restore originals
    app_module.bus = old_bus
    app_module._LOG_PATH = old_log
    app_module._repaired_store.clear()
    app_module._repaired_store.update(old_store)
    app_module._delivery_metadata.clear()
    app_module._delivery_metadata.update(old_metadata)
    app_module._briefing_cache.clear()
    app_module._briefing_cache.update(old_briefing_cache)


@pytest.fixture
async def client(fresh_app):
    transport = httpx.ASGITransport(app=fresh_app.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ─────────────────────────────────────────────────────────────────────────────
# Evidence Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMission07Evidence:
    @pytest.mark.anyio
    async def test_break_action_creates_linked_delivery(self, fresh_app, client) -> None:
        """The /api/break/{id} endpoint fetches repaired bytes, corrupts them, and re-fires pipeline."""
        # Setup parent delivery data
        parent_id = "parent-123"
        clean_srt = (
            "1\n00:00:01,000 --> 00:00:03,000\nHello world\n\n"
            "2\n00:00:05,000 --> 00:00:08,000\nThis is a clean file\n\n"
        ).encode("utf-8")

        fresh_app._repaired_store[parent_id] = clean_srt
        fresh_app._delivery_metadata[parent_id] = {
            "delivery_id": parent_id,
            "language": "en",
            "verdict": "passed",
        }

        # Mock E2E PipelineRunner.run_delivery so we don't do real slow pipeline runs
        mock_run = AsyncMock(return_value={"verdict": "passed", "delivery_id": "child-456"})
        mock_get_bytes = AsyncMock(return_value=b"child-repaired-srt")

        with patch("passline.pipeline.runner.PipelineRunner.run_delivery", mock_run), \
             patch("passline.pipeline.runner.PipelineRunner.get_repaired_bytes", mock_get_bytes):
            
            resp = await client.post(f"/api/break/{parent_id}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "accepted"
            assert data["parent_delivery_id"] == parent_id
            
            # Allow background tasks to run briefly
            await asyncio.sleep(0.1)

            # Check that PipelineRunner.run_delivery was called with parent_id as argument
            mock_run.assert_called_once()
            called_args, called_kwargs = mock_run.call_args
            assert called_kwargs["parent_id"] == parent_id
            assert called_kwargs["language"] == "en"
            # verify that the input SRT bytes was corrupted by corrupt_demo
            assert called_args[0] != clean_srt

    @pytest.mark.anyio
    async def test_download_gating(self, fresh_app, client) -> None:
        """A repaired file is retrievable only when exists; not-found triggers 404."""
        # 1. Non-existent delivery returns 404
        r = await client.get("/api/download/nonexistent-999")
        assert r.status_code == 404
        assert "No repaired file" in r.text

        # 2. Existing delivery returns 200 and bytes
        fresh_app._repaired_store["valid-123"] = b"repaired-srt-data"
        r = await client.get("/api/download/valid-123")
        assert r.status_code == 200
        assert r.content == b"repaired-srt-data"

    @pytest.mark.anyio
    async def test_briefing_caching(self, fresh_app, client) -> None:
        """A second play/briefing request performs no second TTS generation."""
        delivery_id = "delivery-briefing-test"
        fresh_app._delivery_metadata[delivery_id] = {
            "delivery_id": delivery_id,
            "language": "en",
            "verdict": "passed",
            "violations_found": {"timing": 0, "format": 0, "language": 0, "remaining_after_repair": 0},
            "repairs_applied": 1,
        }

        # Mock the briefing generator
        dummy_wav = b"RIFF....WAVEfmt....data...."
        mock_gen = MagicMock(return_value=dummy_wav)
        fresh_app._briefing_generator.generate_briefing = mock_gen

        # 1. First request: triggers generation
        r1 = await client.get(f"/api/briefing/{delivery_id}")
        assert r1.status_code == 200
        assert r1.content == dummy_wav
        mock_gen.assert_called_once()

        # 2. Second request: should hits cache and NOT trigger a second generation
        mock_gen.reset_mock()
        r2 = await client.get(f"/api/briefing/{delivery_id}")
        assert r2.status_code == 200
        assert r2.content == dummy_wav
        mock_gen.assert_not_called()

    @pytest.mark.anyio
    async def test_briefing_unavailable_degrades_gracefully(self, fresh_app, client) -> None:
        """If briefing generator raises BriefingError or is disabled, return 503."""
        delivery_id = "delivery-error-test"
        fresh_app._delivery_metadata[delivery_id] = {
            "delivery_id": delivery_id,
            "language": "en",
            "verdict": "passed",
            "violations_found": {"timing": 0, "format": 0, "language": 0, "remaining_after_repair": 0},
        }

        mock_gen = MagicMock(side_effect=BriefingError("TTS limit exceeded"))
        fresh_app._briefing_generator.generate_briefing = mock_gen

        resp = await client.get(f"/api/briefing/{delivery_id}")
        assert resp.status_code == 503
        assert resp.json()["error"] == "unavailable"

    @pytest.mark.anyio
    async def test_honest_fail_final_outcome_event(self, tmp_path: Path) -> None:
        """ReporterAgent emits a delivery.failed event on failed verdict with rule breakdown."""
        from passline.agents.reporter_agent import ReporterAgent
        from passline.events.bus import EventBus
        from unittest.mock import MagicMock

        log_path = tmp_path / "failed_event.jsonl"
        bus = EventBus(log_path)
        agent = ReporterAgent(name="reporter", bus=bus)

        ctx = MagicMock()
        ctx.session.state = {
            "delivery_id": "failed-delivery-001",
            "language": "en",
            "subtitle_file": None,
            "all_findings": [{"rule": "cps_exceeded"}, {"rule": "line_too_long"}],
            "timing_findings": [],
            "format_findings": [{"rule": "line_too_long"}],
            "language_findings": [{"rule": "cps_exceeded"}],
            "repair_log": [],
        }

        # Run reporter agent async generator to trigger E2E emission
        async for _ in agent._run_async_impl(ctx):
            pass

        # Verify that a DELIVERY_FAILED event was emitted to the bus
        events = bus.read_all()
        emitted_event = None
        for ev in events:
            if ev.event_type == EventType.DELIVERY_FAILED:
                emitted_event = ev
                break

        assert emitted_event is not None
        assert emitted_event.delivery_id == "failed-delivery-001"
        assert emitted_event.details["verdict"] == "failed"
        assert emitted_event.details["remaining_violations"] == 2
        assert emitted_event.details["per_rule_breakdown"] == {"cps_exceeded": 1, "line_too_long": 1}
        assert emitted_event.details["repaired_file_exists"] is False
