# passline-mission06-plan.md

## Mission 06 — Full ADK Agent Graph

### Top-Level Overview

Wire a complete Google ADK agent graph around the existing subtitle QC engine, entirely inside
the existing FastAPI web application. No new services, no MCP tooling.

The graph uses three ADK named orchestration classes exactly as required:
- `SequentialAgent` — the delivery pipeline (ingest → fan-out → repair loop → report)
- `ParallelAgent` — concurrent timing, format, and language checkers
- `LoopAgent` — repair–verify cycle (max 3 passes)

Every piece of arithmetic stays in the existing deterministic Python rule engine.
Every LLM call is isolated to three leaf agents (language checker, fixer, root coordinator).
All state flows through ADK session state and the existing JSONL event bus.
All 149 existing tests must remain green. Corpus grading must stay at 10/10.

---

### Key Architectural Decisions (grounded in code research)

**ADK version:** 2.7.1 (pinned in pyproject.toml). `SequentialAgent`, `ParallelAgent`, and
`LoopAgent` are all confirmed present at `google.adk.agents`.

**output_schema + tools:** ADK 2.7.1 explicitly supports both simultaneously. The spec note
("ADK disables tool use on agents given an output schema") refers to an older ADK version.
In 2.7.1 the flow processor handles both via `SetModelResponseTool`. No mutual exclusion.

**Loop exit:** `LoopAgent` exits when `event.actions.escalate = True` OR `max_iterations` is
reached. The verifier agent sets escalate on a clean verdict.

**Session state exchange:** Tools and orchestrating agents read/write `ctx.state['key']`.
State deltas are tracked automatically via `EventActions.state_delta` and committed to the
session on every event yield.

**Model strings:** ADK accepts plain string model IDs passed to `LlmAgent(model=...)`. The
GenAI client resolves Vertex AI vs Developer API via credentials.

**Exponential backoff:** Implemented as an `on_model_error_callback` on each LLM agent.
The callback catches HTTP 429 / `ResourceExhausted` exceptions, sleeps with jitter, and
returns `None` so ADK retries the model call. Max 4 attempts, base delay 1 s.

**Human approval queue:** Multi-item queue — the fixer enqueues ALL meaning-change edits
up-front before suspending. The loop then awaits ALL pending gates (one per queued item) before
proceeding. Three new FastAPI routes expose the queue. The dashboard card works through items
sequentially; each `POST /api/queue/{item_id}/approve|reject` resolves that item's gate.
The loop does NOT proceed until every gate is resolved.

**Existing dashboard UI:** The `approval.required` event payload gains one new field:
`"item_id"` (the UUID of the pending item). `showApproval()` stores this in
`window.currentApprovalId`. `handleApproval()` is changed to POST to the real API route
using that stored ID. Multiple queued items fire successive `approval.required` events; the
card re-activates for each one in sequence.

**New event types needed:** None. `APPROVAL_REQUIRED` already exists in `EventType`.
The `approval.required` event payload adds `"item_id": str` alongside the existing
`"reason"` and `"violation_count"` fields. This is backward-compatible with the demo fixture.
`STATION_WORKING`, `STATION_READY`, `QC_VIOLATION`, `QC_REPAIRED`, `DELIVERY_PASSED` all
already exist in schema 1.2.

---

### File Map

New files to create:

| File | Purpose |
|---|---|
| `passline/agents/callbacks.py` | Shared exponential-backoff `on_model_error_callback` factory |
| `passline/agents/schemas.py` | Pydantic output schemas: `QcAssessment`, `LanguageFlag`, `LanguageCheckerOutput` |
| `passline/agents/ingest_agent.py` | `IngestAgent(BaseAgent)` — calls parse_srt, emits event, writes SubtitleFile to session state |
| `passline/agents/timing_checker.py` | `TimingCheckerAgent(BaseAgent)` — runs timing rules, writes findings to session state |
| `passline/agents/format_checker.py` | `FormatCheckerAgent(BaseAgent)` — runs format rules, writes findings to session state |
| `passline/agents/language_checker.py` | `LanguageCheckerAgent(LlmAgent)` — gemini-3.1-pro-preview, output_schema=LanguageCheckerOutput |
| `passline/agents/fixer_agent.py` | `FixerAgent(LlmAgent)` — gemini-3-flash-preview, proposes/applies repairs, enqueues meaning changes |
| `passline/agents/verifier_agent.py` | `VerifierAgent(BaseAgent)` — re-runs rule engine, sets escalate if zero violations |
| `passline/agents/reporter_agent.py` | `ReporterAgent(BaseAgent)` — assembles final DeliveryReport, writes repaired bytes via write_srt |
| `passline/agents/pipeline.py` | Builds the full agent graph: `build_pipeline()` → `SequentialAgent` |
| `passline/agents/coordinator.py` | `build_coordinator()` → root `LlmAgent` wrapping the pipeline as a tool |
| `passline/pipeline/session.py` | `DeliverySession` dataclass — owns session_id, delivery_id, and convenience state accessors |
| `passline/pipeline/approval.py` | `ApprovalQueue` — manages pending items, asyncio.Event gates for each item |
| `passline/pipeline/runner.py` | `PipelineRunner` — wraps ADK `Runner`, exposes `run_delivery(srt_bytes, language)` coroutine |

Modified files:

| File | Change |
|---|---|
| `passline/dashboard/app.py` | Add 3 approval API routes; wire PipelineRunner; wire /api/upload to real pipeline |
| `passline/dashboard/html.py` | One-line change: `handleApproval` posts to `/api/queue/{id}/approve` or `/api/queue/{id}/reject` |
| `passline/agents/__init__.py` | Export `build_coordinator`, `build_pipeline` |
| `passline/agents/qc_agent.py` | Keep as-is (backward compat); `build_qc_agent()` remains for existing tests |
| `passline/__main__.py` | Keep as-is; smoke-test still works |

New test file:

| File | Purpose |
|---|---|
| `tests/test_pipeline.py` | Offline pipeline tests using InMemorySessionService and patched LLM calls |

---

### Sub-Tasks

---

#### Sub-Task 1 — Output schemas and shared callback

**Intent**
Define the three Pydantic output schemas and the exponential-backoff callback factory used by
all LLM agents. These are pure data definitions with no side effects, and everything else
depends on them.

**Expected Outcomes**
- `passline/agents/schemas.py` with `QcAssessment`, `LanguageFlag`, `LanguageCheckerOutput`
- `passline/agents/callbacks.py` with `make_retry_callback()` factory
- All schemas validate correctly with Pydantic v2
- No changes to existing tests; 149 still pass

**Todo List**
1. Create `passline/agents/schemas.py`:
   - `QcAssessment`: `assessment: Literal["pass", "flag", "repair-needed"]`, `reason: str`, `suggested_text: str | None`
   - `LanguageFlag`: `cue_index: int`, `confidence: float` (0.0–1.0), `rule_ref: str`, `explanation: str`
   - `LanguageCheckerOutput`: `flags: list[LanguageFlag]`, `language: str`, `checked_cues: int`
2. Create `passline/agents/callbacks.py`:
   - `make_retry_callback(max_attempts=4, base_delay_s=1.0)` → `on_model_error_callback`
   - Catches `google.api_core.exceptions.ResourceExhausted` (HTTP 429)
   - Exponential backoff with jitter: `delay = base * 2^attempt + random(0, 0.5)`
   - Logs attempt number via standard `logging`
   - Returns `None` after max attempts to let ADK propagate the error

**Relevant Context**
- Pydantic v2 is the project standard (`model_validator(mode='after')` pattern)
- `QcAssessment` mirrors the existing `qc_agent.py` instruction's JSON contract
- ADK `on_model_error_callback` signature: `Callable[[CallbackContext, LlmRequest, Exception], Optional[LlmResponse]]`
- `ResourceExhausted` is in `google.api_core.exceptions` (already transitively installed)

**Status** `[ ] pending`

---

#### Sub-Task 2 — Deterministic checker agents (Ingest, Timing, Format)

**Intent**
Wrap the existing deterministic code (parser and rule engine) as `BaseAgent` subclasses.
These agents contain no LLM; they translate between ADK session state and the existing Python
APIs. The parallel fan-out needs all three checkers done before verifier/fixer can proceed.

**Expected Outcomes**
- `passline/agents/ingest_agent.py`: `IngestAgent` parses SRT bytes from session state, writes
  `SubtitleFile` to state, emits `subtitle.submitted`
- `passline/agents/timing_checker.py`: `TimingCheckerAgent` reads `SubtitleFile` from state,
  runs timing rules (cps_exceeded, cps_warning, sub_one_second, overlapping_cues,
  malformed_timecode), writes timing findings list to state
- `passline/agents/format_checker.py`: `FormatCheckerAgent` reads `SubtitleFile` from state,
  runs format rules (line_too_long, three_line_cue), writes format findings list to state
- All findings serialised as `list[dict]` in session state (Finding → dict via dataclasses.asdict)
- One `station.working` / `station.ready` event pair emitted around each agent's work
- 149 tests still pass

**Todo List**
1. Create `passline/agents/ingest_agent.py` — `IngestAgent(BaseAgent)`:
   - `_run_async_impl`: reads `ctx.state["srt_bytes"]` (bytes), `ctx.state["language"]` (str),
     `ctx.state["delivery_id"]` (str)
   - Calls `parse_srt(srt_bytes, language=language, delivery_id=delivery_id, bus=bus)`
   - Writes `ctx.state["subtitle_file"]` (serialised as dict via `.model_dump()`)
   - Emits `STATION_WORKING` then `STATION_READY` events with `station_name="ingest"`
   - Yields a single `Event` with the state delta
2. Create `passline/agents/timing_checker.py` — `TimingCheckerAgent(BaseAgent)`:
   - Reads `SubtitleFile` from `ctx.state["subtitle_file"]`
   - Runs `check_file()` filtered to timing rules: `cps_exceeded`, `cps_warning`,
     `sub_one_second`, `overlapping_cues`, `malformed_timecode`
   - Writes `ctx.state["timing_findings"]` as `list[dict]`
   - Emits `QC_VIOLATION` per finding (using existing bus)
   - Wraps with `STATION_WORKING` / `STATION_READY`
3. Create `passline/agents/format_checker.py` — `FormatCheckerAgent(BaseAgent)`:
   - Same pattern as timing checker, filters to: `line_too_long`, `three_line_cue`
   - Writes `ctx.state["format_findings"]`

**Relevant Context**
- `SubtitleFile` is frozen Pydantic v2 — serialise with `.model_dump()`, deserialise with
  `SubtitleFile.model_validate(d)`
- `check_file()` accepts `bus=` for live event emission
- `Finding` is a frozen dataclass — serialise with `dataclasses.asdict(f)`
- All rule IDs: timing = {cps_exceeded, cps_warning, sub_one_second, overlapping_cues,
  malformed_timecode}; format = {line_too_long, three_line_cue}
- `BaseAgent._run_async_impl` must yield at least one `Event` object; yield
  `Event(author=self.name, content=None, actions=EventActions(state_delta={...}))` with the
  state writes collected into one delta

**Status** `[ ] pending`

---

#### Sub-Task 3 — Language Checker Agent

**Intent**
Build the leaf LLM agent for French/German mistranslation and register detection using
`gemini-3.1-pro-preview`. It must produce structured output validated by `LanguageCheckerOutput`,
include the retry callback, and be graded against `MEANING_LEVEL` entries in the corpus manifests.

**Expected Outcomes**
- `passline/agents/language_checker.py` with `build_language_checker()` → `LlmAgent`
- `output_schema=LanguageCheckerOutput` enforced
- Retry callback attached
- Integration test in `tests/test_pipeline.py` (mocked): language checker correctly flags the
  two meaning-swap cues in the EN golden corpus when called offline with a mock LLM
- All findings written to `ctx.state["language_findings"]` as `list[dict]`

**Todo List**
1. Create `passline/agents/language_checker.py`:
   - `build_language_checker(fallback_model="gemini-2.5-flash")` → `LlmAgent`
   - `model="gemini-3.1-pro-preview"` with fallback via env var `PASSLINE_LANG_MODEL`
   - `output_schema=LanguageCheckerOutput`
   - `on_model_error_callback=make_retry_callback()`
   - Instruction: read cue text from session state; for each cue in
     `ctx.state["subtitle_file"]`, flag likely mistranslations or register violations in FR/DE
     against the built-in style guide; reference rule from the rule table in the instruction
   - Built-in rule reference table in the instruction (6 rules: MT01–MT06 covering mistranslation,
     register, false cognates, omission, addition, style)
   - Agent is a leaf — no tools, only output_schema. Reads cue text injected by the pipeline
     via `ctx.state["lang_check_input"]`
   - After-agent callback writes the structured output into `ctx.state["language_findings"]`
2. Write offline tests in `tests/test_pipeline.py`:
   - Mock the LLM call to return a known `LanguageCheckerOutput`
   - Verify the output schema validation rejects malformed responses
   - Verify confidence range validation (0.0–1.0)

**Relevant Context**
- `LlmAgent` `output_schema` in ADK 2.7.1 fully supports leaf agents (no tools)
- The `after_agent_callback` receives a `CallbackContext` and `LlmResponse`; can write to
  `ctx.state` to persist structured output for the next stage
- Meaning-swap defects in EN corpus are cue indices 22 and 32 (`"love" → "hate"`)
- FR/DE manifests also have meaning-swap entries at known cue indices

**Status** `[ ] pending`

---

#### Sub-Task 4 — Approval Queue

**Intent**
Build the human-approval queue that persists across page refreshes and gates the repair loop.
This is a pure Python module with no ADK dependency — it stores items in a plain dict backed
by ADK session state, and uses `asyncio.Event` objects to suspend and resume the loop.

**Expected Outcomes**
- `passline/pipeline/approval.py`: `ApprovalQueue` class
  - `enqueue(item: ApprovalItem) -> str` — adds item, returns item_id, stores in session state
  - `approve(item_id: str) -> bool` — marks item approved, resolves gate event
  - `reject(item_id: str) -> bool` — marks item rejected, resolves gate event
  - `pending() -> list[ApprovalItem]` — returns pending items
  - `await_decision(item_id: str)` — async coroutine that suspends until gate event fires
- `ApprovalItem` dataclass: `item_id`, `delivery_id`, `cue_index`, `original_text`, `proposed_text`,
  `reason`, `status: Literal["pending", "approved", "rejected"]`
- Three new FastAPI routes in `passline/dashboard/app.py`:
  - `GET /api/queue` → list pending items as JSON
  - `POST /api/queue/{item_id}/approve` → approve item, returns 200
  - `POST /api/queue/{item_id}/reject` → reject item, returns 200
- One-line change to `handleApproval` in `dashboard/html.py` to call the real API

**Todo List**
1. Create `passline/pipeline/__init__.py` (empty package marker)
2. Create `passline/pipeline/approval.py`:
   - `ApprovalItem` dataclass with the fields above
   - `ApprovalQueue` with a module-level singleton (shared across requests)
   - `_gates: dict[str, asyncio.Event]` — one per pending item
   - `enqueue()` also emits `APPROVAL_REQUIRED` event with `reason` and `violation_count`
   - `approve()` / `reject()` set status and fire the gate event
3. Add to `passline/dashboard/app.py`:
   - Import and use the `ApprovalQueue` singleton
   - `GET /api/queue` → `[item.to_dict() for item in queue.pending()]`
   - `POST /api/queue/{item_id}/approve` → `queue.approve(item_id)`
   - `POST /api/queue/{item_id}/reject` → `queue.reject(item_id)`
4. In `passline/dashboard/html.py`, find `handleApproval(action)` and replace the fake
   `addLog` call with a real `fetch('/api/queue/...')` call that reads `currentApprovalId`
   (set when `showApproval` fires)

**Relevant Context**
- `app.py` already has a module-level `bus = EventBus(...)` singleton — same pattern for queue
- The `approval.required` event already exists in `EventType.APPROVAL_REQUIRED` = `"approval.required"`
- Demo event shows payload: `{"reason": str, "violation_count": int}`
- `asyncio.Event` is the correct primitive for async gate; gate must be re-created per item
  (not reused) to prevent spurious wakeups

**Status** `[ ] pending`

---

#### Sub-Task 5 — Fixer Agent and Verifier Agent

**Intent**
Build the two agents inside the `LoopAgent`. The fixer applies deterministic repairs directly
(retime/reflow) and calls the LLM only for text rewording; the verifier re-runs the rule engine
and sets `escalate=True` when findings are zero.

**Expected Outcomes**
- `passline/agents/fixer_agent.py`: `FixerAgent(LlmAgent)` with `gemini-3-flash-preview`
  - Deterministic repairs applied inline (no LLM)
  - Text-level repairs proposed by LLM, written to session state
  - Meaning-changing edits enqueued in approval queue, loop suspends via `await_decision()`
  - Repaired `SubtitleFile` written back to `ctx.state["subtitle_file"]`
  - `STATION_WORKING` / `STATION_READY` / `QC_REPAIRED` events emitted
- `passline/agents/verifier_agent.py`: `VerifierAgent(BaseAgent)`
  - Reads current `SubtitleFile` from state
  - Runs full `check_file()` on it
  - If findings == 0: sets `ctx.actions.escalate = True`
  - If findings > 0 and loop not exhausted: writes updated findings to state
  - Emits one `STATION_WORKING` / `STATION_READY` event pair
- 149 existing tests still pass

**Todo List**
1. Create `passline/agents/verifier_agent.py` — `VerifierAgent(BaseAgent)`:
   - `_run_async_impl`: reads `ctx.state["subtitle_file"]`, deserialises to `SubtitleFile`
   - Runs `check_file()`, collects all findings
   - If `len(findings) == 0`: sets escalate via yielding event with `actions.escalate=True`
   - Else: merges findings back into `ctx.state["all_findings"]`
   - Yield a single Event with the delta
2. Create `passline/agents/fixer_agent.py` — `FixerAgent(LlmAgent)`:
   - Reads `ctx.state["all_findings"]` (merged timing + format + language findings)
   - For each deterministic finding (timing/format): apply a simple rule-based fix:
     - `line_too_long` → split the long line at the nearest space before char 42
     - `three_line_cue` → join lines 2+3 if combined length ≤ 42, else truncate
     - `cps_exceeded` → extend end_ms by the minimum needed to drop CPS below threshold
     - `sub_one_second` → extend end_ms to MIN_DURATION_MS if space permits
     - `overlapping_cues` → retract end_ms of overlapping cue to start_ms of next - 1
   - For each language finding: invoke LLM to propose rewording
   - If proposed text differs meaningfully from original: enqueue in ApprovalQueue,
     `await queue.await_decision(item_id)`, then apply or skip based on decision
   - Write repaired `SubtitleFile` to `ctx.state["subtitle_file"]`
   - Emit `QC_REPAIRED` event for each applied repair

**Relevant Context**
- `SubtitleFile` is frozen — edits produce new objects via `model_copy(update={"cues": [...]})`
- `SubtitleCue` is also frozen — patch individual cues with `cue.model_copy(update={...})`
- `LoopAgent` sets `escalate` = True when any yielded event has `event.actions.escalate = True`
  (loop_agent.py line 116)
- `ctx.actions.escalate` is on the current context's event actions — the verifier must yield an
  Event that carries `actions=EventActions(escalate=True)` to signal the loop
- Deterministic repairs must NEVER call LLM — rule check is pure math
- Await-on-approval pattern: call `await approval_queue.await_decision(item_id)` inside the
  async fixer to suspend the coroutine; the FastAPI route resolves the asyncio.Event

**Status** `[ ] pending`

---

#### Sub-Task 6 — Reporter Agent and Pipeline Assembly

**Intent**
Build the final reporter stage and assemble the complete `SequentialAgent` pipeline plus the
root coordinator `LlmAgent`. Wire the `Runner` and `InMemorySessionService` into a
`PipelineRunner` helper that the dashboard can call.

**Expected Outcomes**
- `passline/agents/reporter_agent.py`: `ReporterAgent(BaseAgent)` — assembles final report
  object, calls `write_srt()` for repaired bytes, emits `DELIVERY_PASSED` / `delivery.failed`
- `passline/agents/pipeline.py`: `build_pipeline()` → `SequentialAgent` with correct child order
- `passline/agents/coordinator.py`: `build_coordinator()` → root `LlmAgent` wrapping pipeline
  via a `run_pipeline` tool
- `passline/pipeline/runner.py`: `PipelineRunner` with `run_delivery(srt_bytes, language)` coroutine
- `passline/agents/__init__.py`: updated exports

**Todo List**
1. Create `passline/agents/reporter_agent.py` — `ReporterAgent(BaseAgent)`:
   - Reads all findings and repair log from session state
   - Reads approval queue outcomes
   - Calls `write_srt(subtitle_file)` to produce final bytes
   - Writes `ctx.state["report"]` (dict) and `ctx.state["repaired_bytes"]` (bytes)
   - Emits `DELIVERY_PASSED` (green) or a `QC_VIOLATION` summary (red) based on findings count
2. Create `passline/agents/pipeline.py`:
   - `build_pipeline(bus, approval_queue)` → `SequentialAgent`:
     ```
     children=[
       IngestAgent,
       ParallelAgent(sub_agents=[TimingChecker, FormatChecker, LanguageChecker]),
       LoopAgent(sub_agents=[FixerAgent, VerifierAgent], max_iterations=3),
       ReporterAgent,
     ]
     ```
3. Create `passline/agents/coordinator.py`:
   - `build_coordinator(bus, approval_queue)` → root `LlmAgent`
   - Model: `gemini-3-flash-preview` (env `PASSLINE_COORDINATOR_MODEL`, fallback `gemini-2.5-flash`)
   - One tool: `run_pipeline_tool` — calls the SequentialAgent as a sub-agent
   - `on_model_error_callback=make_retry_callback()`
   - Holds no output_schema (uses session state for data exchange)
4. Create `passline/pipeline/runner.py` — `PipelineRunner`:
   - Constructor takes `bus: EventBus`, `approval_queue: ApprovalQueue`
   - Builds coordinator, creates `InMemorySessionService`, creates `Runner`
   - `run_delivery(srt_bytes, language, delivery_id)` → dict (report)
   - `get_repaired_bytes(session_id)` → bytes

**Relevant Context**
- `SequentialAgent` constructor: `SequentialAgent(name=..., sub_agents=[...])`
- `LoopAgent(max_iterations=3)` — exits after 3 passes or when verifier escalates
- `ParallelAgent(sub_agents=[...])` — each child gets isolated branch context
- `Runner(agent=coordinator, app_name="passline", session_service=InMemorySessionService())`
- `Runner.run_async(user_id=..., session_id=..., new_message=types.Content(...))`

**Status** `[ ] pending`

---

#### Sub-Task 7 — Dashboard Integration

**Intent**
Wire the real pipeline into the dashboard's `/api/upload` route, expose the approval queue
endpoints, and make the minimal change to `html.py` so the approval card calls the real backend.
All existing routes must still work. The demo replay continues to operate unchanged.

**Expected Outcomes**
- `POST /api/upload` triggers a real pipeline run (in background task), not demo replay
- `GET /api/queue` returns pending approval items as JSON
- `POST /api/queue/{item_id}/approve` and `/reject` resolve approval gates
- `handleApproval` in `html.py` posts to the correct API endpoint
- Existing `/api/replay`, `/api/stop`, `/api/history`, `/api/events` routes unchanged
- Dashboard displays agent-station events live (station.working / station.ready events already
  handled by existing JS event router)

**Todo List**
1. In `passline/dashboard/app.py`:
   - Import `PipelineRunner`, `ApprovalQueue` singleton
   - Add `GET /api/queue`, `POST /api/queue/{item_id}/approve`,
     `POST /api/queue/{item_id}/reject` routes
   - Change `POST /api/upload`: instead of starting demo replay, create a `PipelineRunner`
     and launch `runner.run_delivery(...)` as a `BackgroundTask`
   - Keep `/api/replay` for demo mode (unchanged)
2. In `passline/dashboard/html.py`:
   - In `showApproval(ev)`: store `currentApprovalId = ev.details.item_id` on the window
   - In `handleApproval(action)`: replace fake `addLog` with
     `fetch('/api/queue/' + currentApprovalId + '/' + action, {method:'POST'})`
   - These are the only two changes needed

**Relevant Context**
- `app.py` uses `BackgroundTasks` from FastAPI for the demo replay — same pattern for pipeline
- The `bus` singleton in `app.py` is module-level; `PipelineRunner` must receive the same instance
- `approval.required` event's `details` must include `"item_id"` so JS can read it

**Status** `[ ] pending`

---

#### Sub-Task 8 — Tests

**Intent**
Write offline tests that verify the agent graph structure (correct class types, correct child
order), the schema validation, the approval queue mechanics, and the verifier exit condition —
all without making real LLM calls or network requests.

**Expected Outcomes**
- `tests/test_pipeline.py` with tests for:
  - Pipeline structure: correct ADK class types, correct child count and order
  - Schema: `QcAssessment` and `LanguageCheckerOutput` reject invalid enums / out-of-range floats
  - Approval queue: enqueue → pending → approve → resolved; enqueue → reject → resolved
  - Verifier exit: verifier with zero findings yields an event with `escalate=True`
  - Ingest agent: given SRT bytes in state, produces `subtitle_file` in state
  - Timing + format checkers: given a known SubtitleFile with a violation, find it in state
- 149 + N new tests all passing (`python -m pytest`)
- Corpus grading unchanged: `python scripts/corpus_report.py` shows 10/10 for all three languages

**Todo List**
1. Create `tests/test_pipeline.py`:
   - Use `InMemorySessionService` for session management
   - Patch LLM calls with `unittest.mock.patch` on `LlmAgent._run_async_impl` or use
     `before_model_callback` to inject a canned response
   - One test per agent: ingest, timing, format, verifier (escalate case), verifier (no-escalate case)
   - Schema validation tests for `QcAssessment` and `LanguageCheckerOutput`
   - Approval queue unit tests (no ADK needed)
2. Verify: `python -m pytest` reports all tests passing (149 + new count)
3. Verify: `python scripts/corpus_report.py` still reports 10/10 for EN, FR, DE

**Relevant Context**
- Existing test pattern from `tests/test_agents.py`: use `monkeypatch.setenv` for env vars
- `InMemorySessionService` is in `google.adk.sessions`
- The `Runner` can be used offline with `InMemorySessionService` — no network required for
  deterministic agents; LLM agents need patching

**Status** `[ ] pending`

---

### Constraints Checklist

| Constraint | How Met |
|---|---|
| All code in existing app/container | All new files are under `passline/` or `tests/`; no new services |
| No new services, no MCP tooling | Agent graph wired inside FastAPI process |
| 149 existing tests remain green | Existing files changed minimally; `qc_agent.py` untouched |
| Corpus grading 10/10 | Rule engine unchanged; corpus test unchanged |
| Byte-level round-trip preserved | `write_srt()` called unchanged by reporter; SubtitleFile mutations use model_copy |
| Named ADK orchestration classes | `SequentialAgent`, `ParallelAgent`, `LoopAgent` all used |
| Classic template workflow agents | Using agent classes directly, not graph workflow API |
| Exponential backoff on 429 | `on_model_error_callback` on all three LLM agents |
| No output schema on coordinator | Coordinator uses tools + session state, no output_schema |
| Approval queue persists page refresh | Stored in module-level singleton + session state |
