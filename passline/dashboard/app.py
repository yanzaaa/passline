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

from passline.events.bus import DeliveryEvent, EventBus, EventType
from passline.dashboard.replay import start_replay, stop_replay
from passline.dashboard.html import DASHBOARD_HTML
from passline.pipeline.approval import ApprovalQueue, approval_queue as _approval_queue

logger = logging.getLogger(__name__)

# ── Global singletons ────────────────────────────────────────────────────────
_LOG_PATH = Path(os.getenv("PASSLINE_LOG", "/tmp/passline_events.jsonl"))
bus = EventBus(_LOG_PATH)

# Wire the bus into the approval queue singleton so it can emit events
_approval_queue.set_bus(bus)

from passline.dashboard.briefing import BriefingGenerator, BriefingError

# In-memory store for repaired SRT bytes keyed by delivery_id.
# Populated by PipelineRunner after each successful run.
_repaired_store: dict[str, bytes] = {}

# In-memory store for delivery reports and metadata needed by the briefing system.
_delivery_metadata: dict[str, dict] = {}

# Briefing cache and generator
_briefing_cache: dict[str, bytes] = {}
_briefing_generator = BriefingGenerator()

# Running delivery tasks
import asyncio
_active_deliveries: set[asyncio.Task] = set()

# Demo corpus directory (bundled inside the package for Cloud Run)
_DEMO_DIR = Path(__file__).parent.parent / "corpus" / "demo"

# Language code → demo SRT filename mapping
_DEMO_FILES: dict[str, str] = {
    "en": "demo-en-broken.srt",
    "en-us": "demo-en-broken.srt",
    "fr": "demo-fr-broken.srt",
    "fr-fr": "demo-fr-broken.srt",
    "de": "demo-de-broken.srt",
    "de-de": "demo-de-broken.srt",
    "es": "demo-es-broken.srt",
    "es-es": "demo-es-broken.srt",
    "ru": "demo-ru-broken.srt",
    "ru-ru": "demo-ru-broken.srt",
    "pt": "demo-pt-broken.srt",
    "pt-br": "demo-pt-broken.srt",
    "zh": "demo-zh-broken.srt",
    "zh-cn": "demo-zh-broken.srt",
    "fa": "demo-fa-broken.srt",
    "fa-ir": "demo-fa-broken.srt",
    "demo-en": "demo-en-broken.srt",
    "demo-fr": "demo-fr-broken.srt",
    "demo-de": "demo-de-broken.srt",
    "demo-es": "demo-es-broken.srt",
    "demo-ru": "demo-ru-broken.srt",
    "demo-pt": "demo-pt-broken.srt",
    "demo-zh": "demo-zh-broken.srt",
    "demo-fa": "demo-fa-broken.srt",
    "hopeless": "hopeless-fr.srt",
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
    
    # Origination jobs reset
    try:
        from passline.origination.orchestrator import cancel_all_jobs
        cancel_all_jobs()
    except ImportError:
        pass
    
    # Cancel all active delivery tasks
    for task in list(_active_deliveries):
        task.cancel()
    _active_deliveries.clear()
    
    # Reject/Resolve any pending approvals
    for item in list(_approval_queue.pending()):
        if item.status == "pending":
            _approval_queue.reject(item.item_id)
            
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
    for lang in ("en", "fr", "de", "es", "ru", "pt", "zh", "fa"):
        if f"-{lang}" in lower or f"_{lang}" in lower:
            language = lang
            break

    import uuid
    delivery_id = str(uuid.uuid4())

    def _emit_final_event(report: dict, repaired_bytes: bytes, delivery_id: str, language: str) -> None:
        verdict = report.get("verdict", "unknown")
        if verdict == "passed":
            bus.emit(DeliveryEvent(
                event_type=EventType.DELIVERY_PASSED,
                delivery_id=delivery_id,
                language=language,
                details={
                    "repairs_applied": report.get("repairs_applied", 0),
                    "verdict": "passed",
                    "repaired_file_exists": len(repaired_bytes) > 0,
                },
            ))
        else:
            remaining = report.get("violations_found", {}).get("remaining_after_repair", 0)
            per_rule_breakdown = {}
            for f in report.get("all_findings", []):
                rule_name = f.get("rule") or f.get("rule_ref") or "unknown"
                per_rule_breakdown[rule_name] = per_rule_breakdown.get(rule_name, 0) + 1

            bus.emit(DeliveryEvent(
                event_type=EventType.DELIVERY_FAILED,
                delivery_id=delivery_id,
                language=language,
                details={
                    "verdict": "failed",
                    "remaining_violations": remaining,
                    "per_rule_breakdown": per_rule_breakdown,
                    "repaired_file_exists": len(repaired_bytes) > 0,
                    "summary": f"{remaining} violation(s) remain after repair",
                },
            ))

    async def _run_and_store() -> None:
        from passline.pipeline.runner import PipelineRunner
        runner = PipelineRunner(bus=bus, approval_queue=_approval_queue)
        is_demo = filename.lower().startswith("demo-")
        is_hopeless = "hopeless" in filename.lower()
        report = await runner.run_delivery(srt_bytes, language, delivery_id=delivery_id, is_demo=is_demo, is_hopeless=is_hopeless)
        _delivery_metadata[delivery_id] = report
        # Retrieve repaired bytes via the async-safe getter
        rb_final = b""
        try:
            rb = await runner.get_repaired_bytes(delivery_id=delivery_id)
            if rb:
                rb_final = rb
                _repaired_store[delivery_id] = rb
                logger.info(
                    "stored repaired bytes for delivery %s (%d bytes)",
                    delivery_id, len(rb),
                )
            else:
                logger.debug("no repaired_bytes for delivery %s (verdict=%s)", delivery_id, report.get("verdict"))
        except Exception as exc:
            logger.warning("could not retrieve repaired_bytes for %s: %s", delivery_id, exc)

        _emit_final_event(report, rb_final, delivery_id, language)

    task = asyncio.create_task(_run_and_store())
    _active_deliveries.add(task)
    task.add_done_callback(_active_deliveries.discard)
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


@app.post("/api/break/{delivery_id}")
async def break_file(delivery_id: str, background_tasks: BackgroundTasks) -> JSONResponse:
    """Take repaired SRT of cleared delivery, corrupt it server-side, and re-fire pipeline."""
    repaired_bytes = _repaired_store.get(delivery_id)
    if not repaired_bytes:
        raise HTTPException(status_code=404, detail="No repaired file found for this delivery.")

    parent_report = _delivery_metadata.get(delivery_id, {})
    language = parent_report.get("language", "und")

    import secrets
    from passline.io.srt import parse_srt
    from passline.corpus.corrupt import corrupt_demo

    source = parse_srt(repaired_bytes, language=language)
    seed = secrets.randbelow(10000)

    result = corrupt_demo(
        source,
        seed=seed,
        language=language,
        excerpt_cues=14,
        defects={"cps_blowout", "line_overflow", "short_duration"},
    )

    import uuid
    child_id = str(uuid.uuid4())

    async def _run_and_store_child() -> None:
        from passline.pipeline.runner import PipelineRunner
        runner = PipelineRunner(bus=bus, approval_queue=_approval_queue)
        report = await runner.run_delivery(
            result.broken_bytes,
            language=language,
            delivery_id=child_id,
            parent_id=delivery_id,
        )
        _delivery_metadata[child_id] = report
        rb_final = b""
        try:
            rb = await runner.get_repaired_bytes(delivery_id=child_id)
            if rb:
                rb_final = rb
                _repaired_store[child_id] = rb
                logger.info(
                    "stored repaired bytes for broken child delivery %s (%d bytes)",
                    child_id, len(rb),
                )
        except Exception as exc:
            logger.warning("could not retrieve repaired_bytes for child %s: %s", child_id, exc)

        # we can't reuse _emit_final_event easily because it's a closure in another method, 
        # let's just copy the logic or call it if we move it to top level. Wait, I'll define it locally.
        verdict = report.get("verdict", "unknown")
        if verdict == "passed":
            bus.emit(DeliveryEvent(
                event_type=EventType.DELIVERY_PASSED,
                delivery_id=child_id,
                language=language,
                details={
                    "repairs_applied": report.get("repairs_applied", 0),
                    "verdict": "passed",
                    "repaired_file_exists": len(rb_final) > 0,
                    "parent_id": delivery_id,
                },
            ))
        else:
            remaining = report.get("violations_found", {}).get("remaining_after_repair", 0)
            per_rule_breakdown = {}
            for f in report.get("all_findings", []):
                rule_name = f.get("rule") or f.get("rule_ref") or "unknown"
                per_rule_breakdown[rule_name] = per_rule_breakdown.get(rule_name, 0) + 1

            bus.emit(DeliveryEvent(
                event_type=EventType.DELIVERY_FAILED,
                delivery_id=child_id,
                language=language,
                details={
                    "verdict": "failed",
                    "remaining_violations": remaining,
                    "per_rule_breakdown": per_rule_breakdown,
                    "repaired_file_exists": len(rb_final) > 0,
                    "summary": f"{remaining} violation(s) remain after repair",
                    "parent_id": delivery_id,
                },
            ))

    task = asyncio.create_task(_run_and_store_child())
    _active_deliveries.add(task)
    task.add_done_callback(_active_deliveries.discard)

    return JSONResponse({
        "status": "accepted",
        "child_delivery_id": child_id,
        "parent_id": delivery_id,
    })


@app.get("/api/briefing/{delivery_id}")
async def briefing(delivery_id: str) -> Response:
    """Serve concatenated spoken briefing WAV file for a delivery.

    Generates lazily on first access and caches the result.
    """
    if delivery_id in _briefing_cache:
        return Response(content=_briefing_cache[delivery_id], media_type="audio/wav")

    report = _delivery_metadata.get(delivery_id)
    if not report:
        raise HTTPException(status_code=404, detail="No metadata found for this delivery.")

    language_findings = report.get("language_findings", [])

    try:
        audio_bytes = await asyncio.to_thread(
            _briefing_generator.generate_briefing, report, language_findings
        )
        _briefing_cache[delivery_id] = audio_bytes
        return Response(content=audio_bytes, media_type="audio/wav")
    except BriefingError as exc:
        logger.warning("Briefing generation failed: %s", exc)
        return JSONResponse({"error": "unavailable", "detail": str(exc)}, status_code=503)
    except Exception as exc:
        logger.error("Unexpected error in briefing generation: %s", exc)
        return JSONResponse({"error": "unavailable", "detail": str(exc)}, status_code=503)


@app.get("/api/style-guide/{rule_ref}/{lang}")
async def style_guide(rule_ref: str, lang: str) -> JSONResponse:
    """Return Style Guide citation for a language and rule code."""
    from passline.agents.style_guide import get_citation
    return JSONResponse(get_citation(rule_ref, lang))


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


@app.post("/api/originate")
async def api_originate(request: Request):
    from passline.origination.orchestrator import start_origination
    form = await request.form()
    file_obj = form.get("file")
    source_language = form.get("source_language")
    
    if not source_language:
        raise HTTPException(status_code=400, detail="source_language is required")
        
    if not file_obj:
        raise HTTPException(status_code=400, detail="file is required")
        
    media_bytes = await file_obj.read()
    mime_type = file_obj.content_type
    
    if not mime_type or not mime_type.startswith(("audio/", "video/")):
        raise HTTPException(status_code=415, detail="Unsupported media type")
        
    job_id = start_origination(media_bytes, mime_type, source_language, bus)
    return JSONResponse(status_code=202, content={"job_id": job_id})

@app.get("/api/originate/status/{job_id}")
async def api_originate_status(job_id: str):
    from passline.origination.orchestrator import get_job_status
    job_info = get_job_status(job_id)
    if not job_info:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_info
