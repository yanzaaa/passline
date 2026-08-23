"""Passline Mission Control — FastAPI application.

One process serves:
  GET  /                        → Dashboard HTML (same origin as API — zero CORS)
  GET  /api/events              → Server-Sent Events stream (backfills history on connect)
  GET  /api/history             → JSON array of all logged events
  POST /api/replay              → Start demo replay (called directly from async handler)
  POST /api/stop                → Stop demo replay
  POST /api/reset               → Truncate event log and stop replay (clean take)
  POST /api/upload              → Accept file drop (triggers real pipeline run)
  GET  /api/demo/{lang}         → Serve bundled corpus SRT for demo chips
  GET  /api/queue               → List pending human-approval items
  POST /api/queue/{id}/approve  → Approve a pending item
  POST /api/queue/{id}/reject   → Reject a pending item
  GET  /api/download/{id}       → Download repaired SRT bytes

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
from fastapi import FastAPI, HTTPException, Request, Response, UploadFile, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from passline.events.bus import DeliveryEvent, EventBus
from passline.dashboard.replay import start_replay, stop_replay
from passline.dashboard.html import DASHBOARD_HTML
from passline.pipeline.approval import ApprovalQueue, approval_queue as _approval_queue

logger = logging.getLogger(__name__)

# ── Global singletons ────────────────────────────────────────────────────────
_LOG_PATH = Path(os.getenv("PASSLINE_LOG", "/tmp/passline_events.jsonl"))
bus = EventBus(_LOG_PATH)

# Wire the bus into the approval queue singleton so it can emit events
_approval_queue.set_bus(bus)

# In-memory store for repaired SRT bytes keyed by delivery_id.
# Populated by PipelineRunner after each successful run.
_repaired_store: dict[str, bytes] = {}

# Demo corpus directory (bundled inside the package for Cloud Run)
_DEMO_DIR = Path(__file__).parent.parent / "corpus" / "demo"

# Language code → demo SRT filename mapping
_DEMO_FILES: dict[str, str] = {
    "en": "tos-en.srt",
    "en-us": "tos-en.srt",
    "fr": "tos-fr.srt",
    "fr-fr": "tos-fr.srt",
    "de": "tos-de.srt",
    "de-de": "tos-de.srt",
}

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
async def replay(loop: bool = False) -> JSONResponse:
    """Start (or restart) the demo replay.

    Called directly in the async handler — start_replay() uses asyncio.create_task()
    which requires a running event loop (present in FastAPI's async context).
    """
    start_replay(bus, loop)
    return JSONResponse({"status": "started", "loop": loop})


@app.post("/api/stop")
async def stop() -> JSONResponse:
    """Stop the current replay."""
    stop_replay()
    return JSONResponse({"status": "stopped"})


@app.post("/api/reset")
async def reset() -> JSONResponse:
    """Truncate the event log and stop replay for a clean board take."""
    stop_replay()
    try:
        _LOG_PATH.write_text("")
    except OSError as exc:
        logger.warning("reset: could not truncate log — %s", exc)
    return JSONResponse({"status": "reset"})


@app.post("/api/upload")
async def upload(file: UploadFile, background_tasks: BackgroundTasks) -> JSONResponse:
    """Accept a subtitle file drop and run the real QC pipeline.

    The background task calls ``_run_and_store`` which persists repaired bytes
    into ``_repaired_store`` keyed by delivery_id so they can be downloaded.
    """
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

    import uuid
    delivery_id = str(uuid.uuid4())

    async def _run_and_store() -> None:
        from passline.pipeline.runner import PipelineRunner
        runner = PipelineRunner(bus=bus, approval_queue=_approval_queue)
        report = await runner.run_delivery(srt_bytes, language, delivery_id=delivery_id)
        # Retrieve repaired bytes via the async-safe getter
        try:
            rb = await runner.get_repaired_bytes(delivery_id=delivery_id)
            if rb:
                _repaired_store[delivery_id] = rb
                logger.info(
                    "stored repaired bytes for delivery %s (%d bytes)",
                    delivery_id, len(rb),
                )
            else:
                logger.debug("no repaired_bytes for delivery %s (verdict=%s)", delivery_id, report.get("verdict"))
        except Exception as exc:
            logger.warning("could not retrieve repaired_bytes for %s: %s", delivery_id, exc)

    background_tasks.add_task(_run_and_store)
    return JSONResponse({"status": "accepted", "filename": filename, "language": language, "delivery_id": delivery_id})


@app.get("/api/demo/{lang}")
async def demo_file(lang: str) -> Response:
    """Serve the bundled broken corpus SRT for demo chips.

    ``lang`` is a BCP-47 code or two-letter prefix (en / fr / de).
    Returns the raw SRT bytes so the JS demo chip can fetch and POST it to
    ``/api/upload`` without the user needing to have the file locally.
    """
    key = lang.lower()
    filename = _DEMO_FILES.get(key)
    if filename is None:
        raise HTTPException(status_code=404, detail=f"No demo corpus for language {lang!r}")

    path = _DEMO_DIR / filename
    if not path.exists():
        logger.error("demo file not found on disk: %s", path)
        raise HTTPException(status_code=404, detail=f"Demo file missing: {filename}")

    data = path.read_bytes()
    return Response(
        content=data,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/download/{delivery_id}")
async def download_repaired(delivery_id: str) -> Response:
    """Download the repaired SRT bytes for a completed delivery run.

    Returns 404 if no repaired bytes have been stored for *delivery_id*.
    """
    data = _repaired_store.get(delivery_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"No repaired file for delivery {delivery_id!r}")
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="repaired-{delivery_id}.srt"'},
    )


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
    port = int(os.getenv("PORT") or os.getenv("PASSLINE_PORT", "8000"))
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
