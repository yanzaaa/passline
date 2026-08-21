"""Passline Mission Control — FastAPI application.

One process serves:
  GET  /                        → Dashboard HTML (same origin as API — zero CORS)
  GET  /api/events              → Server-Sent Events stream (backfills history on connect)
  GET  /api/history             → JSON array of all logged events
  POST /api/replay              → Start demo replay
  POST /api/stop                → Stop demo replay
  POST /api/upload              → Accept file drop (triggers real pipeline run)
  GET  /api/queue               → List pending human-approval items
  POST /api/queue/{id}/approve  → Approve a pending item
  POST /api/queue/{id}/reject   → Reject a pending item

All endpoints share the same in-process EventBus and ApprovalQueue singletons.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import AsyncGenerator

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from passline.events.bus import DeliveryEvent, EventBus
from passline.dashboard.replay import start_replay, stop_replay
from passline.dashboard.html import DASHBOARD_HTML
from passline.pipeline.approval import ApprovalQueue, approval_queue as _approval_queue

logger = logging.getLogger(__name__)

# ── Global singletons ────────────────────────────────────────────────────────
_LOG_PATH = Path(os.getenv("PASSLINE_LOG", "passline_events.jsonl"))
bus = EventBus(_LOG_PATH)

# Wire the bus into the approval queue singleton so it can emit events
_approval_queue.set_bus(bus)

# ── FastAPI application ───────────────────────────────────────────────────────
app = FastAPI(title="Passline Mission Control", version="0.1.0")


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Serve the dashboard single-page application."""
    return HTMLResponse(DASHBOARD_HTML)


@app.get("/api/history")
async def history() -> JSONResponse:
    """Return all logged events as a JSON array (for polling fallback)."""
    events = []
    for ev in bus.read_all():
        if hasattr(ev, "serialise"):
            events.append(json.loads(ev.serialise()))  # type: ignore[union-attr]
    return JSONResponse(events)


@app.get("/api/events")
async def sse_stream(request: Request) -> StreamingResponse:
    """Server-Sent Events stream.

    On connect, all historical events are sent first (backfill), then live events
    are streamed as they are emitted.  On disconnect, the subscriber is cleaned up.
    A keepalive comment is sent every 15 seconds to prevent proxy timeouts.
    """
    q = bus.subscribe()

    async def generate() -> AsyncGenerator[str, None]:
        try:
            # 1. Backfill — send all historical events so reconnect = catchup
            for ev in bus.read_all():
                if hasattr(ev, "serialise"):
                    yield f"data: {ev.serialise()}\n\n"  # type: ignore[union-attr]

            # 2. Live stream
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event: DeliveryEvent = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {event.serialise()}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/replay")
async def replay(
    background_tasks: BackgroundTasks,
    loop: bool = False,
) -> JSONResponse:
    """Start (or restart) the demo replay."""
    background_tasks.add_task(start_replay, bus, loop)
    return JSONResponse({"status": "started", "loop": loop})


@app.post("/api/stop")
async def stop() -> JSONResponse:
    """Stop the current replay."""
    stop_replay()
    return JSONResponse({"status": "stopped"})


@app.post("/api/upload")
async def upload(file: UploadFile, background_tasks: BackgroundTasks) -> JSONResponse:
    """Accept a subtitle file drop and run the real QC pipeline."""
    filename = file.filename or "unknown"
    logger.info("file uploaded: %s — starting pipeline run", filename)
    srt_bytes = await file.read()
    # Detect language from filename (e.g. tos-fr-broken.srt → fr)
    language = "und"
    lower = filename.lower()
    for lang in ("en", "fr", "de"):
        if f"-{lang}" in lower or f"_{lang}" in lower:
            language = lang
            break

    from passline.pipeline.runner import PipelineRunner
    runner = PipelineRunner(bus=bus, approval_queue=_approval_queue)
    background_tasks.add_task(runner.run_delivery, srt_bytes, language)
    return JSONResponse({"status": "accepted", "filename": filename, "language": language})


# ── Human approval queue API ──────────────────────────────────────────────────

@app.get("/api/queue")
async def queue_list() -> JSONResponse:
    """Return all pending human-approval items as a JSON array."""
    return JSONResponse([item.to_dict() for item in _approval_queue.pending()])


@app.post("/api/queue/{item_id}/approve")
async def queue_approve(item_id: str) -> JSONResponse:
    """Approve a pending approval item."""
    ok = _approval_queue.approve(item_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Item {item_id!r} not found or already resolved")
    return JSONResponse({"status": "approved", "item_id": item_id})


@app.post("/api/queue/{item_id}/reject")
async def queue_reject(item_id: str) -> JSONResponse:
    """Reject a pending approval item."""
    ok = _approval_queue.reject(item_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Item {item_id!r} not found or already resolved")
    return JSONResponse({"status": "rejected", "item_id": item_id})


# ── Entry point ───────────────────────────────────────────────────────────────

def run() -> None:
    """Start the Passline Mission Control dashboard server."""
    port = int(os.getenv("PASSLINE_PORT", "8000"))
    host = os.getenv("PASSLINE_HOST", "0.0.0.0")
    print(f"✓ Passline Mission Control starting on http://localhost:{port}")
    print(f"  Event log: {_LOG_PATH.resolve()}")
    uvicorn.run(
        "passline.dashboard.app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    run()
