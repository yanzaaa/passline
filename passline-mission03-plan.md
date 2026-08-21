# Passline Mission 03 — Mission Control Dashboard

## Overview

Build a real-time web dashboard that visualises the delivery event log. One FastAPI
application, same origin, same process. No new Python dependencies — FastAPI and
Uvicorn are already installed.

---

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│  uvicorn passline.dashboard.app:app --port 8000            │
│                                                            │
│  GET /           → inline HTML (HTMLResponse)              │
│  GET /api/events → SSE stream (StreamingResponse)          │
│  GET /api/history→ JSON array of all past events           │
│  POST /api/replay→ start demo replay background task       │
│  POST /api/stop  → stop replay                             │
│  POST /api/upload→ accept file (triggers demo replay)      │
└────────────────────────────────────────────────────────────│
         │ in-process pub/sub (asyncio.Queue per connection)
         ▼
┌─────────────────────────────┐
│  EventBus  (extended)       │
│  emit() → JSONL file        │
│          + notify subscribers│
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  demo_events.jsonl          │
│  (committed fixture, ~25    │
│  events, versioned schema)  │
└─────────────────────────────┘
```

**No CORS configuration needed** — HTML served from same origin as API.
**No build step** — HTML/CSS/JS inlined in a Python string constant.
**No aiofiles** — HTML served via `HTMLResponse`, not `StaticFiles`.

---

## New event types (schema 1.2)

Added alongside existing four, never replacing them:

| event_type | Purpose | Key details fields |
|---|---|---|
| `station.working` | A QC station started processing | `station_id`, `station_name` |
| `station.ready` | A QC station finished and is idle | `station_id`, `station_name` |
| `cue.analysis` | Per-cue CPS/timing data for heat strip | `cues: [{index, cps, duration_ms, text}]` |
| `approval.required` | Human approval needed | `reason`, `violation_count` |

`schema_version` bumps to `"1.2"`. Existing four event types and all their fields are
**unchanged**. The `UnknownDeliveryEvent` fallback in `read_all()` handles 1.1 logs
read by a 1.2 reader gracefully (no change needed — 1.2 events with new types will
just be UnknownDeliveryEvent when read by 1.1 code).

---

## Sub-Tasks

---

### Sub-Task 1 — Extend EventBus with in-process pub/sub

**Intent:**
Add async subscriber support to `EventBus` so SSE connections can receive events
the instant they are emitted, without polling the JSONL file.

**Design:**
```python
class EventBus:
    def __init__(self, log_path):
        ...
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._subscribers = [s for s in self._subscribers if s is not q]

    def emit(self, event):
        # existing JSONL write — unchanged
        ...
        # notify async subscribers (fire-and-forget, safe from sync context)
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow consumer — drop event; JSONL is the durable source
```

**Critical detail:** `emit()` remains synchronous (existing callers unchanged).
`q.put_nowait()` is safe to call from sync code when an event loop is running
(it doesn't require `await`). When no loop is running (tests, CLI), `_subscribers`
is always empty so `put_nowait` is never called — zero behaviour change in tests.

**Todo List:**
1. Add `import asyncio` to `bus.py`
2. Add `self._subscribers: list[asyncio.Queue]` initialised to `[]` in `__init__`
3. Add `subscribe() -> asyncio.Queue` method
4. Add `unsubscribe(q: asyncio.Queue) -> None` method
5. Extend `emit()` to call `q.put_nowait(event)` for each subscriber after the file write
6. Add new EventType values: `STATION_WORKING`, `STATION_READY`, `CUE_ANALYSIS`, `APPROVAL_REQUIRED`
7. Bump `schema_version` default in `DeliveryEvent` to `"1.2"`
8. Update the two tests that assert `schema_version == "1.1"` to `"1.2"`
9. Add `subscribe`/`unsubscribe` to `__all__` in `events/__init__.py`

**Existing test compatibility:** All existing tests pass because they never set up
a running event loop when calling `emit()`, so `_subscribers` is always empty and
`put_nowait` is never reached.

**Status:** [ ] pending

---

### Sub-Task 2 — Demo replay fixture

**Intent:**
Create a committed JSONL fixture that tells a complete 35-second delivery story using
the real event schema. This is the single source of truth for demo mode — replayed
events are identical in schema to real pipeline events.

**Story arc (25 events, ~35 seconds realistic pacing):**

```
t=0.0   subtitle.submitted   delivery_id="DEMO-EN-001"  language="en-US"
                              details: {cue_count:42, is_canonical:true}
t=1.0   station.working      station_id="timing"  station_name="Timing"
t=1.5   station.working      station_id="format"  station_name="Format"
t=2.5   station.ready        station_id="timing"  station_name="Timing"
t=3.0   qc.violation         details:{rule:"cps_exceeded", cue:7, value:22.4, threshold:20.0}
t=3.5   qc.violation         details:{rule:"line_too_long", cue:12, value:48, threshold:42}
t=4.0   station.ready        station_id="format"  station_name="Format"
t=4.5   station.working      station_id="language"  station_name="Language"
t=5.5   cue.analysis         details:{cues:[...42 cues with CPS values...]}
t=6.5   station.ready        station_id="language"  station_name="Language"
t=7.0   station.working      station_id="fixer"   station_name="Fixer"
t=9.0   qc.repaired          details:{rule:"cps_exceeded", cue:7, original:"...", repaired:"..."}
t=11.0  qc.repaired          details:{rule:"line_too_long", cue:12, original:"...", repaired:"..."}
t=12.0  station.ready        station_id="fixer"   station_name="Fixer"
t=13.0  station.working      station_id="verifier" station_name="Verifier"
t=15.0  station.ready        station_id="verifier" station_name="Verifier"
t=16.0  station.working      station_id="vendor_health" station_name="Vendor Health"
t=17.5  approval.required    details:{reason:"2 cues repaired, policy requires review", violation_count:2}
t=18.0  station.ready        station_id="vendor_health" station_name="Vendor Health"
t=25.0  delivery.passed      details:{approved_by:"human", note:"All repairs verified"}
```

The `cue.analysis` event carries 42 fabricated cues with realistic CPS spread
(3–18 CPS range, with 2 outliers above 20 to match the violation events).

**File:** `tests/fixtures/demo_events.jsonl`

**Todo List:**
1. Write a Python script (run once, not committed) to generate the fixture, OR
   write the fixture directly with timestamps relative to a base time
2. The fixture uses real ISO-8601 timestamps (absolute, not relative) — the replay
   endpoint uses the `t=` offsets embedded in `details.replay_offset_s` field on
   each event, OR computes pacing from inter-event timestamp deltas
3. Decision: embed `replay_offset_s` in each event's details (easier, self-documenting)
4. Write `tests/fixtures/demo_events.jsonl` with all 25 events

**Status:** [ ] pending

---

### Sub-Task 3 — FastAPI dashboard application

**Intent:**
Create `passline/dashboard/` sub-package with the FastAPI app, SSE endpoint,
replay engine, and a global `EventBus` singleton.

**File structure:**
```
passline/dashboard/
├── __init__.py
├── app.py          ← FastAPI app, routes, SSE endpoint
├── replay.py       ← demo replay engine (reads fixture, re-emits on timer)
└── html.py         ← DASHBOARD_HTML constant (the full page)
```

**`app.py` design:**
```python
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from passline.dashboard.html import DASHBOARD_HTML
from passline.dashboard.replay import start_replay, stop_replay
from passline.events.bus import EventBus, DeliveryEvent
import asyncio, json
from pathlib import Path

app = FastAPI()
bus = EventBus(Path("passline_events.jsonl"))

@app.get("/")
def index() -> HTMLResponse:
    return HTMLResponse(DASHBOARD_HTML)

@app.get("/api/history")
def history():
    return [json.loads(e.serialise()) for e in bus.read_all()
            if hasattr(e, "serialise")]

@app.get("/api/events")
async def sse_stream(request: Request):
    q = bus.subscribe()
    async def generate():
        # 1. Backfill history
        for event in bus.read_all():
            if hasattr(event, "serialise"):
                yield f"data: {event.serialise()}\n\n"
        # 2. Stream live events
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(q.get(), timeout=15.0)
                yield f"data: {event.serialise()}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"  # SSE comment — keeps connection alive
    async def cleanup():
        bus.unsubscribe(q)
    return StreamingResponse(generate(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache",
                                       "X-Accel-Buffering": "no"})

@app.post("/api/replay")
async def replay(background_tasks: BackgroundTasks):
    background_tasks.add_task(start_replay, bus)
    return {"status": "started"}

@app.post("/api/stop")
async def stop():
    stop_replay()
    return {"status": "stopped"}
```

**`replay.py` design:**
- Reads `tests/fixtures/demo_events.jsonl`
- Reconstructs `DeliveryEvent` objects from each line
- Reads `replay_offset_s` from `details` to pace events
- Each event is re-emitted via `bus.emit()` with a fresh timestamp (so the live log
  shows real wall-clock times) but the original `event_type`, `delivery_id`, `language`,
  and `details` intact
- Replay is cancellable; a `_replay_task` module-level `asyncio.Task` is set/cancelled
- A "loop" flag restarts when complete

**Dashboard startup:**
Add `passline-dashboard` as a new entry point in `pyproject.toml` pointing to
`passline.dashboard.app:run` where `run()` calls `uvicorn.run(app, ...)`.

**Status:** [ ] pending

---

### Sub-Task 4 — Dashboard HTML/CSS/JS

**Intent:**
Write the complete single-page dashboard as a Python string constant. Dark control-room
aesthetic. Three-column layout. All UI state driven purely from events.

**Visual design spec:**
- Background: `#0a0c0f` (near-black)
- Column card backgrounds: `#111318`
- Border: `1px solid #1e2229`
- Accent colors: violation red `#ff3b3b`, repair amber `#f5a623`, cleared green `#00d26a`, lifecycle blue `#4a9eff`
- Font: `JetBrains Mono` (loaded from Google Fonts — one CDN call allowed) for monospace log; `Inter` or system-ui for labels
- Station lamps: CSS radial-gradient circle, 12px diameter
- Heat strip: `display:flex`, one `<div>` per cue, `width:8px height:32px`, colour mapped from CPS (green < 12, amber 12-17, red >17)
- Delivery cards: rounded, 1px border, status badge pill
- Delivery window countdown: `setInterval` 1 Hz, counts down from 4:00:00

**JS state machine driven purely by event_type:**
```javascript
const HANDLERS = {
  "subtitle.submitted": (ev) => { addDeliveryCard(ev); },
  "station.working":    (ev) => { setLamp(ev.details.station_id, "working"); addLog(ev, "blue"); },
  "station.ready":      (ev) => { setLamp(ev.details.station_id, "ready"); addLog(ev, "blue"); },
  "qc.violation":       (ev) => { markViolation(ev); addLog(ev, "red"); updateHoldsCount(); },
  "qc.repaired":        (ev) => { markRepaired(ev); addLog(ev, "green"); },
  "cue.analysis":       (ev) => { renderHeatStrip(ev.details.cues); },
  "approval.required":  (ev) => { showApprovalCard(ev); addLog(ev, "amber"); },
  "delivery.passed":    (ev) => { markCleared(ev); addLog(ev, "blue"); updateHoldsCount(); },
};
```

**SSE client:**
```javascript
function connectSSE() {
  const src = new EventSource("/api/events");
  src.onmessage = (e) => {
    const ev = JSON.parse(e.data);
    const handler = HANDLERS[ev.event_type];
    if (handler) handler(ev);
  };
  src.onerror = () => {
    src.close();
    setTimeout(connectSSE, 3000);  // auto-reconnect with backfill
  };
}
```

**Reconnect + backfill:** On reconnect, the SSE endpoint sends full history first
(see `app.py` design above), so the page catches up automatically.

**Polling fallback:** If `EventSource` is not supported or fails 3 times, fall back to
`setInterval` polling `/api/history` every 2 seconds, processing only events with
`event_id` not yet seen.

**Demo controls (left column, below drop zone):**
- `▶ PLAY DEMO` button → `POST /api/replay`
- `■ STOP` button → `POST /api/stop`
- `↺ LOOP` toggle (sends `loop=true` query param)
- Three demo chip buttons: `EN-001`, `FR-002`, `JA-003` → all trigger same demo replay

**File drop zone:** `dragover`/`drop` event listeners on the drop zone div.
On drop: read filename, display it in the UI, then `POST /api/replay` to start demo.
On click: `<input type="file" hidden>` trigger.

**Mobile:** `@media (max-width: 768px)` collapses three columns to single column.

**Status:** [ ] pending

---

### Sub-Task 5 — Integration, pyproject.toml, validation

**Intent:**
Wire everything together: entry point, pyproject update, smoke test that the server
starts and `GET /` returns 200.

**Todo List:**
1. Add `passline-dashboard` script to `pyproject.toml` pointing to
   `passline.dashboard.app:run`
2. Add `uvicorn` to the `dependencies` list in `pyproject.toml` (it's already
   installed but not declared)
3. Add `fastapi` to `dependencies` (same — already installed, not declared)
4. Run `pip install -e .` to pick up the new entry point
5. Manual acceptance test: `passline-dashboard`, open `http://localhost:8000`,
   press PLAY DEMO, watch 35 seconds of the story
6. Update `docs/BUILD_JOURNAL.md` with Mission 03 entry

**Status:** [ ] pending

---

## Acceptance Criteria

- `passline-dashboard` (or `python -m passline.dashboard`) starts uvicorn on port 8000
- `GET http://localhost:8000/` returns the dashboard HTML (status 200)
- `POST http://localhost:8000/api/replay` starts the demo
- `GET http://localhost:8000/api/events` streams SSE (text/event-stream)
- All 69 existing tests continue to pass (`python -m pytest`)
- No new Python dependencies required (fastapi and uvicorn already installed)
- Demo story plays for ≥30 seconds with delivery card HOLD→REPAIRING→CLEARED,
  station lamps amber/green, heat strip filling, approval card, scrolling log
