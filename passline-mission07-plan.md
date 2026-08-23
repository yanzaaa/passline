# passline-mission07-plan.md

## Mission 07 — Going Public

### Top-Level Overview

Make Passline deployable to Cloud Run via buildpacks, fix every dead path in the
G1 demo flow, and complete the evidence artifacts (README, BUILD_JOURNAL).

The requirements are grouped into three tracks:

**A. Buildability** — pyproject.toml, requirements.txt, .python-version, Procfile,
.gcloudignore, container-safe event-log path.

**B. Demo path** — fix the PLAY button (wrong thread), wire language checker output
into session state, merge findings before repair loop, regenerate FR/DE meaning-level
corpus entries, align event vocabulary with demo fixture, untangle upload from replay,
add repaired-file download, fix coordinator instruction, add board reset, prove
everything with tests.

**C. Evidence artifacts** — README fixes, BUILD_JOURNAL entries.

---

### Key Facts Discovered

**Bugs confirmed by reading code:**

1. **`start_replay` crash** (`replay.py:86`) — `asyncio.create_task()` is called from inside
   `app.py`'s `/api/replay` endpoint handler, which runs in a FastAPI async request handler.
   This should work. BUT `app.py` line 102 calls `start_replay(bus, loop)` (sync) from an
   `async def replay()` route handler via `background_tasks.add_task(start_replay, bus, loop)`.
   `BackgroundTasks.add_task` schedules the function synchronously on the event loop — but
   `start_replay` calls `asyncio.create_task()` which requires a running loop. When called via
   `BackgroundTasks`, the loop is running (it's an async context), so `create_task` works.
   The actual bug: `background_tasks.add_task(start_replay, bus, loop)` schedules a **sync
   call** to `start_replay`, which calls `asyncio.create_task()`. This must run from within
   the async loop. The fix: change `/api/replay` to call `start_replay` directly (not via
   background_tasks), since it's already inside an `async def` handler.

2. **Language checker output never written to state** — `language_checker.py` is an `LlmAgent`
   with `output_schema=LanguageCheckerOutput`. The promised `after_agent_callback` that would
   read the structured output and write it to `ctx.state["language_findings"]` was never
   implemented. The agent produces output but the downstream fixer never sees it.

3. **Fixer reads only `all_findings`, but nothing merges timing + format + language** — The
   `fixer_agent.py` reads `STATE_ALL_FINDINGS` (`"all_findings"`) but nothing in the pipeline
   merges `timing_findings`, `format_findings`, and `language_findings` into `all_findings`
   before the repair loop starts. So the fixer starts with an empty findings list.

4. **Verifier clobbers unresolved language findings** — `verifier_agent.py` re-runs
   `check_file()` (deterministic rules only) and overwrites `all_findings` with its result.
   Language findings (MT01–MT06) that weren't repaired disappear.

5. **FR/DE manifests have no `MEANING_LEVEL` entries** — the meaning-swap defects were not
   injected into the FR and DE corpus files; only EN has them. Requirement 10 asks for at least
   one meaning swap in FR and DE.

6. **Station events use wrong vocabulary** — agents emit
   `{"station": "ingest"}` / `{"station": "timing_checker"}` in their details dicts, but the
   dashboard JS reads `ev.details.station_id` to control lamps. The fixture uses
   `{"station_id": "timing", "station_name": "Timing"}`. Mismatch = lamps never light.

7. **No `cue.analysis` event emitted** — the ingest agent emits `station.working/ready` but
   never emits `cue.analysis` which populates the heat strip on the dashboard.

8. **`qc.violation` events use `"cue_index"` but fixture/dashboard uses `"cue"`** — the
   checker agents emit `{"cue": finding.cue_index, ...}` — this one is actually correct per
   the fixture. Keep.

9. **`qc.repaired` events need `"cue"`, `"original"`, `"repaired"` fields** — the fixture
   shows `{"rule": "cps_exceeded", "cue": 7, "original": "...", "repaired": "..."}` but the
   fixer emits `{"rule": ..., "cue_index": ..., "type": "deterministic", "approved": True}`.
   Missing `"cue"` (vs `"cue_index"`), missing `"original"`, missing `"repaired"`.

10. **`subtitle.submitted` event needs `"cue_count"`** — the fixture has `{"cue_count": 42}` in
    details; `parse_srt` with `bus=` emits the event but `cue_count` may not be in details.
    Check and add.

11. **`handleFile` calls `startReplay(false)` after upload** — `html.py:846`. This starts the
    canned demo replay on top of the real pipeline run. Must be removed.

12. **Demo chips call `triggerDemo()` which calls `startReplay(false)`** — they should instead
    upload the corresponding real corpus SRT file. The corpus files are at
    `tests/corpus/broken/tos-{lang}-broken.srt`. For Cloud Run these need to be bundled.
    The demo chip should POST the corpus file to `/api/upload`.

13. **Coordinator instruction references `run_pipeline` tool that does not exist** — the
    coordinator has `sub_agents=[pipeline]` (ADK delegation) but the instruction says
    "invoke the run_pipeline tool". When the LLM tries to call that tool it fails silently.
    Fix: rewrite instruction to match the actual sub-agent delegation mechanism, OR add a
    `PipelineRunner`-based `after_agent_callback` / deterministic fallback.

14. **`get_repaired_bytes()` crashes inside running server** — uses `loop.run_until_complete()`
    inside an already-running event loop. Replace with proper async session access.

15. **No `/api/download/{delivery_id}` endpoint** — repaired bytes not downloadable.

16. **No board reset endpoint** — second recording starts with stale events from first.

17. **Event log path is relative** — `"passline_events.jsonl"` at CWD. Cloud Run containers
    have read-only filesystem except `/tmp`. Must default to `/tmp/passline_events.jsonl`
    when running in container.

18. **`pytest-asyncio>=0.24,<1` in dev extras conflicts** — requires pytest <9.x. Cloud Run
    buildpack and local CI fail to resolve dependencies. Remove it entirely (nothing uses it).

19. **PLAY button doesn't transmit `loopMode`** — `onclick="startReplay(false)"` hardcodes
    `false`. Should pass `loopMode` variable.

---

### Sub-Tasks

---

#### Sub-Task 1 — Buildability files

**Intent**
Create the five files Cloud Run's buildpack needs, fix the event-log path for containers,
and fix the dependency conflict.

**Expected Outcomes**
- `pyproject.toml` dev extra has only `pytest>=9,<10` (no pytest-asyncio pin)
- `requirements.txt` at repo root with exact versions from the working venv
- `.python-version` at repo root containing `3.12`
- `Procfile` at repo root: `web: uvicorn passline.dashboard.app:app --host 0.0.0.0 --port $PORT`
- `.gcloudignore` at repo root with the specified include/exclude rules
- `app.py` `run()` prefers `PORT` env var, then `PASSLINE_PORT`, then `8000`
- `_LOG_PATH` in `app.py` defaults to `/tmp/passline_events.jsonl` (via env var default change)
- All 191 existing tests still pass

**Todo List**
1. Edit `pyproject.toml`: remove `pytest-asyncio>=0.24,<1` from `[project.optional-dependencies]` dev
2. Create `requirements.txt` by running `pip freeze | grep -v "^-e "` in the venv and saving to file
3. Create `.python-version` containing `3.12`
4. Create `Procfile` with the uvicorn web process
5. Create `.gcloudignore` with the specified rules
6. Edit `app.py` `run()` function: `port = int(os.getenv("PORT") or os.getenv("PASSLINE_PORT", "8000"))`
7. Edit `app.py` `_LOG_PATH`: `Path(os.getenv("PASSLINE_LOG", "/tmp/passline_events.jsonl"))`
   — but keep the `PASSLINE_LOG` override so local dev can still use the local path
8. Run `python -m pytest -q` — verify 191 passing

**Relevant Context**
- `app.py:33`: `_LOG_PATH = Path(os.getenv("PASSLINE_LOG", "passline_events.jsonl"))`
- `app.py:125-130`: `run()` with `port = int(os.getenv("PASSLINE_PORT", "8000"))`
- The `.gcloudignore` must explicitly list `.env` and `.venv` by name (not just via .gitignore patterns) because an explicit .gcloudignore disables .gitignore fallback

**Status** `[ ] pending`

---

#### Sub-Task 2 — Fix replay endpoint and board reset

**Intent**
Fix `start_replay` so it runs on the correct event loop (called from async handler, not
background thread). Add a `/api/reset` endpoint that truncates the event log so a second
recording starts clean. Add a `fresh_delivery_id` per replay run so every run gets a
distinct delivery ID. Fix the PLAY button to transmit `loopMode`.

**Expected Outcomes**
- `POST /api/replay` no longer raises "no running event loop" errors
- `POST /api/reset` truncates `passline_events.jsonl` and returns 200
- Each replay run gets a fresh delivery ID baked into the replayed events
- `onclick="startReplay(loopMode)"` in PLAY button (passes actual toggle state)
- Test: POST to `/api/replay` then GET `/api/history` returns ≥1 event within 5s

**Todo List**
1. In `app.py` `/api/replay` handler: call `start_replay(bus, loop)` directly (the handler is
   already `async def`), NOT via `background_tasks.add_task`. Remove `BackgroundTasks` param
   from the replay endpoint.
2. Add `POST /api/reset` to `app.py`:
   - Truncate the event log file (`_LOG_PATH.write_text("")`)
   - Call `stop_replay()`
   - Return `{"status": "reset"}`
3. In `replay.py` `_run_replay`: generate a fresh `delivery_id = f"LIVE-{uuid4().hex[:8]}"` at
   the start of each replay run; substitute it into every event's `delivery_id` field
4. In `html.py`: change `onclick="startReplay(false)"` on the PLAY button to
   `onclick="startReplay(loopMode)"`. Add a `startReset()` JS function and a RESET button.
5. Write test in `tests/test_dashboard.py`: use `httpx.AsyncClient` with the FastAPI app,
   POST to `/api/replay`, poll `/api/history` until ≥1 event present (or timeout 5s)

**Relevant Context**
- `app.py:99-103`: `/api/replay` handler currently uses `background_tasks`
- `replay.py:80-87`: `start_replay()` calls `asyncio.create_task()` — works fine from async context
- `html.py:383`: `<button class="ctrl-btn btn-play" onclick="startReplay(false)">▶ PLAY</button>`
- `loopMode` JS variable is already declared and toggled by `toggleLoop()`

**Status** `[ ] pending`

---

#### Sub-Task 3 — Rewrite language checker as BaseAgent calling google-genai directly

**Intent**
Convert `LanguageCheckerAgent` from an `LlmAgent` (whose structured output is difficult to
reliably intercept via callbacks) to a `BaseAgent` subclass that drives the Gemini API
directly via `google-genai`. The agent reads `subtitle_file` from state, calls the Gemini API
with structured-output config, parses the response as `LanguageCheckerOutput`, writes
`language_findings` to state, and emits all lifecycle events with the correct vocabulary.
No ADK callback magic needed.

**Expected Outcomes**
- `language_checker.py` defines `LanguageCheckerAgent(BaseAgent)` instead of wrapping `LlmAgent`
- The agent writes `language_findings` (list of flag dicts) to session state
- `station.working` and `station.ready` events carry `station_id="language"`,
  `station_name="Language"` (matching the demo fixture)
- One `qc.violation` event emitted per flag
- Retry on 429 via `tenacity.retry` around the async genai call
- Offline test: patch `client.aio.models.generate_content`; verify `language_findings` in state

**Todo List**
1. Rewrite `language_checker.py` — define `LanguageCheckerAgent(BaseAgent)`:
   - Fields: `bus: EventBus`, `genai_client` (google-genai `Client` or None to build lazily)
   - In `_run_async_impl`:
     a. Emit `STATION_WORKING` with `station_id="language"`, `station_name="Language"`
     b. Read `subtitle_file` dict from state; deserialise to `SubtitleFile`
     c. Build prompt: JSON list of `{"index": cue.index, "lines": cue.lines}` for each cue
     d. Call `await client.aio.models.generate_content(model=..., contents=..., config=GenerateContentConfig(response_mime_type="application/json", response_schema=LanguageCheckerOutput))`
     e. Parse response as `LanguageCheckerOutput.model_validate(json.loads(response.text))`
     f. Write `ctx.state["language_findings"] = [f.model_dump() for f in output.flags]`
     g. Emit one `QC_VIOLATION` event per flag
     h. Emit `STATION_READY` with `station_id="language"`, `station_name="Language"`, `findings=len(output.flags)`
     i. Yield one `Event` with state delta `{"language_findings": [...]}`
2. Wrap the genai call in `tenacity.retry`:
   `@retry(retry=retry_if_exception(lambda e: isinstance(e, ClientError) and e.code == 429), wait=wait_exponential(min=1, max=30), stop=stop_after_attempt(4))`
3. Update `build_language_checker(bus, genai_client=None)` to return `LanguageCheckerAgent(...)`
4. Update `pipeline.py` to pass `genai_client` to `build_language_checker` (build lazily from env in agent init if None)
5. Add offline test in `tests/test_pipeline.py`: patch genai; verify `language_findings` written to state

**Relevant Context**
- `google.genai` async API: `from google import genai; client = genai.Client(); await client.aio.models.generate_content(...)`
- `GenerateContentConfig` from `google.genai.types`: `response_mime_type="application/json"`, `response_schema=LanguageCheckerOutput`
- `passline/__main__.py`: already initialises `genai.Client` — reuse that pattern for credential handling
- `tenacity` is already installed (confirmed in venv)

**Status** `[ ] pending`

---

#### Sub-Task 4 — Fix findings merge and verifier clobbering

**Intent**
Before the repair loop runs, merge `timing_findings`, `format_findings`, and
`language_findings` into the single `all_findings` key the fixer reads. The verifier
currently clobbers `all_findings` with only deterministic results; fix it to keep
language findings that are not yet repaired.

**Expected Outcomes**
- A `FindingsMergerAgent(BaseAgent)` (or inline merge step) writes `all_findings` to state
  after the `checker_fanout` parallel stage and before the `repair_loop` stage
- The verifier re-runs the deterministic rule engine and merges the result with surviving
  language findings (those not yet approved/rejected), so language findings are not lost
- Offline test: pipeline with three known findings (1 timing, 1 format, 1 language) ends up
  with all three in `all_findings` before the fixer runs

**Todo List**
1. Create `passline/agents/findings_merger.py` — `FindingsMergerAgent(BaseAgent)`:
   - Reads `timing_findings`, `format_findings`, `language_findings` from state
   - Merges into a combined list, deduplicating by `(cue_index, rule)`
   - Writes `all_findings` to state
   - No events emitted (bookkeeping only)
2. Add `FindingsMergerAgent` to the `SequentialAgent` in `pipeline.py` between
   `checker_fanout` and `repair_loop`:
   ```
   [ingest, checker_fanout, findings_merger, repair_loop, reporter]
   ```
3. Fix `verifier_agent.py`: after re-running `check_file()`, read the existing
   `language_findings` from state and re-append any that are not covered by a
   deterministic finding on the same cue. This prevents the verifier from silently
   dropping language flags.
4. Update `pipeline.py` to include `findings_merger`
5. Update tests in `test_pipeline.py` to verify the merge

**Relevant Context**
- `fixer_agent.py:62`: `STATE_ALL_FINDINGS = "all_findings"` — fixer reads this
- `verifier_agent.py:98-106`: writes `{STATE_ALL_FINDINGS: findings_dicts}` — only has deterministic
- Language findings have `rule` in range MT01–MT06, not covered by `check_file()`
- `pipeline.py:47-77`: current 4-stage pipeline

**Status** `[ ] pending`

---

#### Sub-Task 5 — Align station event vocabulary

**Intent**
Every agent currently emits events with `{"station": "ingest"}` (single key) but the
dashboard JavaScript reads `ev.details.station_id` to identify which lamp to light.
The demo fixture uses `{"station_id": "timing", "station_name": "Timing"}`.
Also: the `subtitle.submitted` event needs `"cue_count"` in its details, and a
`cue.analysis` event must be emitted after ingest.

**Expected Outcomes**
- All six agents emit `STATION_WORKING` / `STATION_READY` with `station_id` and
  `station_name` matching the vocabulary in `tests/fixtures/demo_events.jsonl`
- `subtitle.submitted` details include `cue_count: int`
- A `cue.analysis` event is emitted by the ingest agent with
  `details={"cues": [{"index": n, "cps": x, "duration_ms": y, "text": "..."}]}`
- `qc.repaired` events carry `"cue"` (not `"cue_index"`), `"original"`, `"repaired"`
- All 191 tests still pass

**Vocabulary table** (from demo fixture):
| Agent | station_id | station_name |
|---|---|---|
| ingest | `"ingest"` | `"Ingest"` |
| timing_checker | `"timing"` | `"Timing"` |
| format_checker | `"format"` | `"Format"` |
| language_checker | `"language"` | `"Language"` |
| fixer | `"fixer"` | `"Fixer"` |
| verifier | `"verifier"` | `"Verifier"` |
| reporter | `"reporter"` | `"Reporter"` |

**Todo List**
1. Create `passline/agents/event_utils.py` with helpers:
   - `emit_station_working(bus, station_id, station_name, delivery_id, language, **extras)`
   - `emit_station_ready(bus, station_id, station_name, delivery_id, language, **extras)`
2. Update all six agents to use the helpers, replacing the old `{"station": name}` pattern
3. In `ingest_agent.py`: after writing subtitle_file to state, emit `CUE_ANALYSIS` with
   `details={"cues": [{"index": c.index, "cps": round(c.cps, 2), "duration_ms": c.duration_ms, "text": " ".join(c.lines)} for c in subtitle_file.cues]}`
4. Verify `subtitle.submitted` from `parse_srt` includes `cue_count` — check `io/srt.py` and
   add if missing
5. In `fixer_agent.py` `_apply_deterministic_fix` and language repair loop: ensure `qc.repaired`
   events carry `{"rule": ..., "cue": cue_index, "original": original_text, "repaired": new_text}`
6. Run full test suite after changes

**Relevant Context**
- `io/srt.py`: `parse_srt` emits `SUBTITLE_SUBMITTED` with bus; check what's in details
- `ingest_agent.py:73-80`: current STATION_WORKING/READY uses `{"station": self.name}`
- Demo fixture line 1: `"details": {"cue_count": 42, "is_canonical": true, "skipped_blocks": 0, "source_path": null}`
- Demo fixture line 9: `cue.analysis` with `cues` array having `index`, `cps`, `duration_ms`, `text`

**Status** `[ ] pending`

---

#### Sub-Task 6 — Untangle upload from replay, wire demo chips

**Intent**
Remove the `startReplay(false)` call from `handleFile` (upload must not also start a demo).
Wire demo chips to POST the actual corpus SRT file via the upload endpoint instead of calling
`startReplay`. Update the dropzone caption. Bundle corpus files so they're accessible to
Cloud Run (copy to `passline/corpus/demo/`).

**Expected Outcomes**
- Dropping a real SRT file triggers only the pipeline, no replay
- Clicking EN-001 / FR-002 demo chips POSTs the corresponding corpus file to `/api/upload`
- The stale "triggers demo" dropzone caption is replaced with "runs QC pipeline"
- Corpus demo files at `passline/corpus/demo/tos-en.srt`, `tos-fr.srt`, `tos-de.srt`
  (symlinks to `tests/corpus/broken/` or copied)
- A new `/api/demo/{lang}` endpoint serves the corpus file bytes as a download (so the JS
  can fetch and POST it), OR the chips fetch the file from the server-side path

**Todo List**
1. In `html.py` `handleFile()`: remove `.then(() => startReplay(false))` — upload must not
   also replay
2. In `html.py` `triggerDemo(id, lang)`: replace `startReplay(false)` with a call that
   fetches `/api/demo/{lang}` then POSTs it to `/api/upload`
3. Add `GET /api/demo/{lang}` to `app.py` that returns the broken corpus SRT file bytes
   for `lang` ∈ {en, fr, de}
4. Copy or symlink the three broken corpus SRTs to `passline/corpus/demo/`
   (they need to be in the source tree for Cloud Run upload)
5. Update dropzone caption: "or click to browse · runs QC pipeline"
6. Add `lang` parameter to `triggerDemo` call (already in HTML, just needs the JS body)

**Relevant Context**
- `html.py:365`: `<div class="dropzone-sub">or click to browse · triggers demo</div>`
- `html.py:839-848`: `handleFile` function
- `html.py:819-821`: `triggerDemo` function
- `tests/corpus/broken/tos-en-broken.srt` etc. exist in repo

**Status** `[ ] pending`

---

#### Sub-Task 7 — Regenerate FR/DE meaning-level corpus entries

**Intent**
The FR and DE corpus manifests currently have no `MEANING_LEVEL` defects. Requirement 10
asks for at least one meaning swap per language. Regenerate the broken FR and DE corpus files
with one `meaning_swap` each, update their manifests, and add a grading test asserting the
language checker flags every meaning-level manifest entry.

**Expected Outcomes**
- `tests/corpus/manifests/tos-fr-manifest.json` has ≥ 1 `MEANING_LEVEL` entry
- `tests/corpus/manifests/tos-de-manifest.json` has ≥ 1 `MEANING_LEVEL` entry
- `tests/corpus/broken/tos-fr-broken.srt` and `tos-de-broken.srt` regenerated with the swaps
- `tests/test_grading.py` existing corpus tests still pass (DETERMINISTIC grading unchanged)
- New test `test_language_grading_meaning_level[lang]` (marked `@pytest.mark.live_llm`) that:
  - Loads the broken corpus file
  - Runs the language checker with a mocked or real LLM
  - Asserts every MEANING_LEVEL manifest entry is flagged by the checker
  - Skip if `PASSLINE_LANG_MODEL` not set or `--live-llm` not passed

**Todo List**
1. Check `passline/corpus/substitutions.py` for FR and DE word-swap pairs
2. Run `python scripts/generate_corpus.py --seed 42 --language fr` (or edit generate_corpus.py
   to always inject one meaning_swap per language) — regenerate with meaning swaps enabled
3. Commit regenerated `tos-fr-broken.srt`, `tos-de-broken.srt`, updated manifests
4. Add `conftest.py` fixture `live_llm` marker and `--live-llm` CLI option
5. Write `test_language_grading_meaning_level` in `test_grading.py` behind the marker

**Relevant Context**
- `passline/corpus/corrupt.py`: `corrupt_file()` accepts `defects=` set; `"meaning_swap"` is a
  valid defect type for FR and DE if substitution pairs exist
- `passline/corpus/substitutions.py`: check whether FR/DE substitution pairs are defined
- `scripts/generate_corpus.py`: review to see if meaning_swap was excluded for FR/DE

**Status** `[ ] pending`

---

#### Sub-Task 8 — Fix coordinator instruction and pipeline fallback

**Intent**
The coordinator's instruction references a `run_pipeline` tool that does not exist. The LLM
may answer with prose instead of delegating to the pipeline, producing no report. Fix:
- Rewrite the instruction to match the actual sub-agent delegation mechanism (ADK uses
  `transfer_to_agent` internally for `sub_agents=[]` — the LLM should say "transfer to
  delivery_pipeline")
- Add a deterministic `after_agent_callback` on the coordinator that invokes the pipeline
  directly if `session.state.get("report")` is None after the coordinator runs

**Expected Outcomes**
- Coordinator instruction correctly describes ADK delegation
- If the coordinator fails to produce a report, the fallback triggers the pipeline directly
- Offline test: coordinator with mocked LLM (returning prose) still produces a `report`
  in session state via the fallback

**Todo List**
1. In `coordinator.py`, update `_COORDINATOR_INSTRUCTION`: replace "invoke the run_pipeline
   tool" with the correct ADK delegation description — the pipeline is a sub-agent named
   `delivery_pipeline`; the coordinator should say `transfer_to_agent("delivery_pipeline")`
   or just delegate all subtitle processing to the delivery_pipeline sub-agent
2. Add an `after_agent_callback` on the coordinator that checks `ctx.session.state.get("report")`
   and if missing, runs the pipeline directly via `PipelineRunner` as a fallback
3. Write a test that patches the LLM to return prose and verifies the fallback kicks in

**Relevant Context**
- `coordinator.py:29-48`: `_COORDINATOR_INSTRUCTION` references non-existent `run_pipeline` tool
- ADK sub-agents are delegated to via `transfer_to_agent` in the LLM's tool list
- The fallback avoids a broken demo due to LLM hallucination

**Status** `[ ] pending`

---

#### Sub-Task 9 — Repaired-file download endpoint

**Intent**
Persist repaired bytes per delivery ID. Expose `GET /api/download/{delivery_id}` that
returns the repaired SRT as a file download. Fix `get_repaired_bytes()` which uses
`loop.run_until_complete()` inside the already-running server loop (crashes with
"This event loop is already running").

**Expected Outcomes**
- `GET /api/download/{delivery_id}` returns the repaired SRT bytes as
  `Content-Disposition: attachment; filename=repaired.srt`
- Returns 404 if no repaired bytes exist for that delivery ID
- `get_repaired_bytes()` removed from `PipelineRunner` (replaced by the download endpoint)
- The dashboard emits a link/button to download after `delivery.passed` event (minor UI)

**Todo List**
1. Add a module-level `_repaired_store: dict[str, bytes]` dict in `pipeline/runner.py`
   (or `app.py`) keyed by `delivery_id`
2. In `PipelineRunner.run_delivery()`: after extracting the report, also read
   `session.state.get("repaired_bytes")` from the session and store in `_repaired_store`
   (can be done since we're already in the async `run_delivery` coroutine)
3. Remove `get_repaired_bytes()` synchronous method from `PipelineRunner` (crashes in server)
4. Add `GET /api/download/{delivery_id}` to `app.py`:
   - Look up `_repaired_store.get(delivery_id)`
   - If found: `Response(content=bytes, media_type="application/octet-stream",
     headers={"Content-Disposition": f"attachment; filename=repaired-{delivery_id}.srt"})`
   - If not found: 404
5. In `html.py` `markCleared(ev)` (the `delivery.passed` handler): append a download link
   `<a href="/api/download/{delivery_id}">⬇ Download repaired SRT</a>` to the delivery card

**Relevant Context**
- `runner.py:140-162`: `get_repaired_bytes()` uses `loop.run_until_complete()` — remove
- `app.py` already imports `Response` equivalents from FastAPI
- `html.py`: `markCleared()` function marks the delivery card green

**Status** `[ ] pending`

---

#### Sub-Task 10 — Tests that prove the demo

**Intent**
Write the tests required by requirement 16: one offline end-to-end pipeline test with
stubbed language checker, dashboard endpoint tests (replay-produces-events, SSE backfill,
queue approve/reject + 404, upload with mocked pipeline).

**Expected Outcomes**
- `tests/test_dashboard.py` with async HTTPX tests for all listed endpoints
- `tests/test_e2e_pipeline.py` with one offline end-to-end test (language checker stubbed):
  - Runs ingest → timing → format → language (stubbed) → merge → loop → reporter
  - Drives one approval through `approve` AND one through `reject`
  - Asserts `report["verdict"]` ∈ {"passed", "failed"}
  - Asserts repaired bytes re-parse with `parse_srt` without crash
  - Asserts report counts match actual findings
- All 191 + new tests pass

**Todo List**
1. Create `tests/test_dashboard.py`:
   - `test_replay_produces_events`: POST /api/replay, wait, GET /api/history → ≥1 event
   - `test_sse_backfill`: emit 2 events, connect SSE, verify both events in first response chunk
   - `test_queue_approve`: enqueue item, POST /api/queue/{id}/approve → 200
   - `test_queue_reject`: enqueue item, POST /api/queue/{id}/reject → 200
   - `test_queue_approve_404`: POST /api/queue/nonexistent/approve → 404
   - `test_upload_triggers_pipeline`: POST /api/upload with SRT bytes (pipeline mocked) → 200
2. Create `tests/test_e2e_pipeline.py`:
   - Build pipeline with `build_pipeline(bus, approval_queue)`
   - Inject known broken SRT (e.g. `tests/corpus/broken/tos-en-broken.srt`)
   - Stub language checker's LLM with a canned `LanguageCheckerOutput` (2 flags)
   - Run via `PipelineRunner`
   - One approval gate: `.approve(item_id)` in a concurrent task
   - One rejection gate: `.reject(item_id)` in a concurrent task
   - Assert repaired bytes parse clean
   - Assert report counts match
3. Run `python -m pytest -q` and confirm green

**Relevant Context**
- `httpx` is available transitively via FastAPI dev dependencies
- `pytest-anyio` or standard `asyncio` loop for async tests
- Stub pattern: patch `Gemini.generate_content_async` to return a canned response
- `tests/test_pipeline.py` has the pattern for running agents offline

**Status** `[ ] pending`

---

#### Sub-Task 11 — README and BUILD_JOURNAL

**Intent**
Fix the README CI badge owner (luisyanza → yanzaaa), make the quickstart work on a fresh
clone, add `.env.example`, refresh project structure, add dashboard instructions, and add
missing BUILD_JOURNAL entries for Missions 01.5, 02 through 05 post-149-tests work and 06.

**Expected Outcomes**
- README CI badge points to correct repo owner `yanzaaa`
- README quickstart: no reference to bundled `.venv`, uses `pip install -e ".[dev]"`,
  shows how to create `.env` from `.env.example`
- `.env.example` at repo root with all env vars documented
- README project structure diagram updated to show `passline/agents/`, `passline/pipeline/`
- BUILD_JOURNAL has entries for Missions 01.5 (events + ADK stub), 02 (models + bus),
  03 (dashboard), 04 (corpus), 05 (rule engine), 06 (agent graph)
- README has "Run the dashboard" instructions

**Todo List**
1. Create `.env.example` with all variables from AGENTS.md env table
2. Edit `README.md`:
   - Fix badge URL: `github.com/yanzaaa/passline`
   - Remove `.venv` bundled reference from quickstart
   - Add `pip install -e ".[dev]"` step
   - Add `.env.example` → `.env` copy step
   - Update project structure diagram
   - Add dashboard launch section
3. Add missing BUILD_JOURNAL entries (concise, follow existing format)

**Relevant Context**
- `README.md:3`: badge URL has `luisyanza` — fix to `yanzaaa`
- `README.md:51-53`: "Requirements: Python 3.12, the `.venv` virtual environment included" — wrong
- `docs/BUILD_JOURNAL.md`: last entry is Mission 05; need Mission 06 and backfill for Missions 01.5–02

**Status** `[ ] pending`

---

### Constraints Checklist

| Constraint | How Met |
|---|---|
| 191 existing tests green | Test suite run after each sub-task |
| Corpus grading 10/10 | Rule engine unchanged; grading test unchanged |
| Cloud Run buildpack compatible | pyproject.toml fix, requirements.txt, Procfile, .gcloudignore |
| No new services | All code stays in the single FastAPI process |
| Byte-level round-trip preserved | `write_srt()` called unchanged |
| All spec requirements numbered 1–16 covered | Mapped across sub-tasks 1–10 |
