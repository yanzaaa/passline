# Build Journal — Built with IBM Bob

Passline is an entry in the Agentic Cinema hackathon. IBM Bob drove the build, authored the plan document for every mission before implementation, implemented the missions in Agent mode, and wrote the two-job continuous integration pipeline, while routine iteration and cosmetic passes were carried by other tooling.
The only AI dependencies in the codebase are **google-adk** and **google-genai**
(Google's Agent Development Kit and Gemini client) — no other AI provider is used
anywhere in the dependency tree.

---

## Mission 01 — Foundation

**Date:** August 20, 2026

### What was built

| Deliverable | Description |
|---|---|
| Subtitle cue data model | `SubtitleCue` and `SubtitleFile` (Pydantic v2, frozen) with millisecond-precision timing, computed `cps`, `char_counts`, `total_chars` |
| SRT parser / writer | `parse_srt()` and `write_srt()` with **byte-identical round-trip guarantee** for LF, CRLF, and UTF-8 BOM variants |
| Delivery event log | `EventBus` + `DeliveryEvent` (schema v1.0) appending to a local JSONL file; `subtitle.submitted` event emitted on ingest |
| ADK QC agent stub | `QcAgent` — Google ADK `LlmAgent` backed by `gemini-2.0-flash` for language-level subtitle QC |
| Google-stack entry point | `python -m passline` constructs both `google-adk` and `google-genai` objects at startup and prints a smoke-test banner |

### Result

**38 tests passing** — `python -m pytest` (0.21 s)

### Plan

Authored before implementation: [`passline-foundation-plan.md`](../passline-foundation-plan.md)

### Verification commands

```bash
# Activate the virtual environment
source .venv/bin/activate

# Run the full test suite
python -m pytest

# Run the entry-point smoke-test
python -m passline
```

---

<!-- Append future missions below this line using the same heading structure -->
---

## Mission 01.5 — Event Schema and ADK Agent Stub

**Date:** August 20, 2026

### What was built

| Deliverable | Description |
|---|---|
| Event schema v1.0 | `DeliveryEvent` with `schema_version`, `event_id`, `event_type`, `timestamp`, `delivery_id`, `language`, `details` |
| EventBus pub/sub skeleton | `subscribe()` / `unsubscribe()` stubs wired into the JSONL log |
| ADK agent stub | `QcAgent(LlmAgent)` wrapping `gemini-2.0-flash` — structure only, no tool calls yet |
| Schema version guard | Parser rejects events with unsupported `schema_version` |

### Result

**38 tests passing** — `python -m pytest`

---

## Mission 02 — Data Models and Event Bus

**Date:** August 20, 2026

### What was built

| Deliverable | Description |
|---|---|
| `SubtitleCue` model | Pydantic v2 frozen model: `index`, `start_ms`, `end_ms`, `lines`, computed `cps`, `char_counts`, `total_chars`, `duration_ms` |
| `SubtitleFile` model | Container with `cues`, `language`, `is_canonical`, `srt_dialect`, `parse_anomalies`, `skipped_blocks` |
| `SrtDialect` | Tracks BOM, CRLF, trailing-blank to guarantee round-trip fidelity |
| `EventBus` | Append-to-JSONL + async pub/sub with `subscribe()`/`unsubscribe()`/`emit()` |
| `DeliveryEvent` | Schema v1.2 with serialise/deserialise round-trip |
| 5 event types | `subtitle.submitted`, `station.working`, `station.ready`, `qc.violation`, `delivery.passed` |

### Non-obvious decisions recorded

- **Millisecond-only storage**: All timing is stored in integer milliseconds (`start_ms`, `end_ms`). No float seconds anywhere in the model tree. This eliminates an entire class of floating-point comparison bugs.
- **Frozen models for cues**: `SubtitleCue` is frozen so agents can safely share references without mutation risk. Repair always creates a new cue via `model_copy(update=...)`.

### Result

**50 tests passing** — `python -m pytest`

---

## Mission 03 — Mission Control Dashboard

**Date:** August 20, 2026

### What was built

| Deliverable | Description |
|---|---|
| EventBus pub/sub | `subscribe()` / `unsubscribe()` async queue API; `emit()` remains sync; all existing callers unchanged |
| Schema 1.2 | Four new event types: `station.working`, `station.ready`, `cue.analysis`, `approval.required` |
| Demo fixture | `tests/fixtures/demo_events.jsonl` — 20-event, 25-second delivery story in live schema |
| FastAPI app | `passline/dashboard/app.py` — one process, zero CORS, `GET /`, `GET /api/events` (SSE), `POST /api/replay`, `POST /api/stop`, `POST /api/upload` |
| SSE stream | Backfills history on every connect; auto-reconnect; keepalive; polling fallback |
| Replay engine | `passline/dashboard/replay.py` — re-emits fixture events with real timestamps; paced by `replay_offset_s`; loopable |
| Dashboard HTML | Dark control-room UI — three columns, station lamps, heat strip, delivery cards, air-traffic log, approval card; pure vanilla JS driven by event_type dispatch table |

### Result

**69 tests passing** — `python -m pytest` · `GET / → 200 OK` · SSE stream delivering events

### Plan

Authored before implementation: [`passline-mission03-plan.md`](../passline-mission03-plan.md)

### Verification commands

```bash
source .venv/bin/activate

# Run the full test suite (69 tests)
python -m pytest

# Start the dashboard
passline-dashboard
# or: python -m passline.dashboard.app

# Open in browser
open http://localhost:8000
# Then click ▶ PLAY or any demo chip
```
---

## Mission 04 — Corpus, Corruption Engine, Golden Fixtures

**Date:** August 20, 2026

### What was built

| Deliverable | Description |
|---|---|
| `scripts/fetch_assets.py` | Downloads Tears of Steel SRT files (EN/FR/DE) from Blender Foundation with CC-BY attribution; fallback URL list; never runs in CI |
| `tests/corpus/clean/` | Committed Blender open-movie subtitles (76 cues each, 3 languages) |
| `tests/corpus/README.md` | CC-BY 3.0 attribution for all Blender assets |
| `passline/corpus/corrupt.py` | Deterministic corruption engine: 6 defect types, `random.Random(seed)` isolation, callable as CLI + programmatic API |
| `passline/corpus/substitutions.py` | Per-language meaning-swap word pairs (EN/FR/DE) |
| `scripts/generate_corpus.py` | One-command corpus regeneration; seed=42 is the canonical version |
| `tests/corpus/broken/` | Committed broken SRT files (EN: 12 defects, FR: 10, DE: 10) |
| `tests/corpus/manifests/` | Committed ground-truth manifests with DETERMINISTIC/MEANING_LEVEL category split |
| `tests/test_corpus.py` | 40 tests in 5 groups: defect unit tests, round-trip, manifest correctness, determinism, toggling |

### Defect types

| Defect | Rule | Threshold | Category |
|---|---|---|---|
| `cps_blowout` | `cps_exceeded` | CPS > 20.0 | DETERMINISTIC |
| `line_overflow` | `line_too_long` | chars > 42 | DETERMINISTIC |
| `three_line_cue` | `three_line_cue` | lines > 2 | DETERMINISTIC |
| `short_duration` | `sub_one_second` | duration_ms < 1000 | DETERMINISTIC |
| `overlap` | `overlapping_cues` | end_ms > next start_ms | DETERMINISTIC |
| `meaning_swap` | `meaning_changed` | N/A | MEANING_LEVEL |

### Result

**109 tests passing** — `python -m pytest`

### Plan

Authored before implementation: [`passline-mission04-plan.md`](../passline-mission04-plan.md)

### Verification commands

```bash
source .venv/bin/activate

# Run the full test suite (109 tests — no network needed)
python -m pytest

# Regenerate corpus (deterministic, seed=42)
python scripts/generate_corpus.py --seed 42

# Download fresh corpus assets (requires network)
python scripts/fetch_assets.py

# Corrupt a file from the CLI
python -m passline.corpus.corrupt \
    --input tests/corpus/clean/tos-en.srt \
    --output /tmp/broken.srt \
    --manifest /tmp/manifest.json \
    --seed 42 --language en
```

---

## Mission 05 — Rule Engine, Corpus Grading, Property Tests, CI

**Date:** August 20, 2026

### What was built

| Deliverable | Description |
|---|---|
| `passline/qc/thresholds.py` | Single source of truth for all numeric QC limits; imported by both `rules.py` and `corrupt.py` |
| `passline/qc/rules.py` | Deterministic rule engine: 7 rules, `Finding` dataclass, `check_file()` with optional event emission |
| `passline/qc/__init__.py` | Sub-package exports: `Finding`, `check_file` |
| `tests/test_grading.py` | Corpus exact-match grading tests (EN/FR/DE); event emission tests; rule-by-rule smoke tests |
| `tests/test_rule_properties.py` | 500+ property-based tests across 6 groups using `random.Random` with fixed seeds |
| `scripts/corpus_report.py` | Standalone Markdown table generator for CI PR comments |
| `.github/workflows/ci.yml` | Two-job CI: `test` (required, every push) + `corpus-report` (PR-only, `continue-on-error`) |
| `pyproject.toml` | Added `[project.optional-dependencies] dev` group with pytest |
| `README.md` | CI badge added |
| `.gitignore` | `passline_events.jsonl` added |
| `AGENTS.md` + `.bob/rules-*/AGENTS.md` | Updated to reflect mission 05 discoveries |

### Rules implemented

| Rule ID | Condition | Severity |
|---|---|---|
| `three_line_cue` | `len(cue.lines) > 2` | WARNING |
| `line_too_long` | `any(c > 42 for c in cue.char_counts)` | ERROR |
| `cps_exceeded` | `cue.cps > 20.0` | ERROR |
| `cps_warning` | `17.0 ≤ cue.cps ≤ 20.0` | WARNING |
| `sub_one_second` | `cue.duration_ms < 1000` | ERROR |
| `overlapping_cues` | `cues[i].end_ms > cues[i+1].start_ms` | ERROR |
| `malformed_timecode` | `cue.start_ms >= cue.end_ms` | ERROR |

### Corpus grading results (seed=42)

| Language | Injected | Detected | Missed | Extra | Status |
|---|---|---|---|---|---|
| EN | 10 | 10 | 0 | 0 | ✅ PASS |
| FR | 10 | 10 | 0 | 0 | ✅ PASS |
| DE | 10 | 10 | 0 | 0 | ✅ PASS |

### Non-obvious decisions recorded

- **Grading filter is `(cue_index, rule)` not just `cue_index`**: The Blender ToS corpus has pre-existing violations. Cue 3 in the FR corpus already has high natural CPS even before any defect is injected. Filtering only by `cue_index` would flag it as a false positive in the grading test. The fix: filter by the exact `(cue_index, rule)` pairs from the manifest.
- **`measured_value` stores full precision**: CPS values in `Finding.measured_value` must equal `cue.cps` exactly — no rounding. Property tests assert `abs(finding.measured_value - cue.cps) < 1e-6`.
- **Meaning-level defects excluded from rule engine grading**: The `meaning_changed` rule is deliberately absent from the rule engine. Manifests split defects into `DETERMINISTIC` and `MEANING_LEVEL` categories; the rule engine is only graded against the former.

### Result

**149 tests passing** — `python -m pytest`

### Plan

Authored before implementation: [`passline-mission05-plan.md`](../passline-mission05-plan.md)

### Verification commands

```bash
source .venv/bin/activate

# Run the full test suite (149 tests — no network needed)
python -m pytest

# Corpus grading report (all three languages must show ✅ PASS)
python scripts/corpus_report.py

# Run a single grading test by language
python -m pytest tests/test_grading.py::test_corpus_grading_exact_match[en]

# Run all property-based tests
python -m pytest tests/test_rule_properties.py -v
```

---

## Mission 06 — ADK Agent Graph

**Date:** August 20, 2026

### What was built

| Deliverable | Description |
|---|---|
| `IngestAgent` | `BaseAgent` wrapping `parse_srt()`; writes `subtitle_file` to ADK session state |
| `TimingCheckerAgent` | `BaseAgent` running timing rules; writes `timing_findings` to state |
| `FormatCheckerAgent` | `BaseAgent` running format rules; writes `format_findings` to state |
| `LanguageCheckerAgent` (v1) | `LlmAgent` with `output_schema=LanguageCheckerOutput`; callback approach |
| `FixerAgent` | `LlmAgent` — deterministic fixes inline, language fixes via LLM + approval gate |
| `VerifierAgent` | `BaseAgent` — re-runs rule engine; `escalate=True` when zero violations |
| `ReporterAgent` | `BaseAgent` — writes repaired SRT bytes + delivery report to session state |
| `build_pipeline()` | 4-stage `SequentialAgent`: ingest → fan-out → repair loop → reporter |
| `ApprovalQueue` | Thread/async-safe queue with `await_decision()` suspension for human review |
| `PipelineRunner` | `async run_delivery()` over ADK `Runner` + `InMemorySessionService` |
| `LoopAgent` exit | `event.actions.escalate = True` pattern (not a callback) |
| Coordinator | Root `LlmAgent` with pipeline as `sub_agent` |
| 191 tests passing | All pipeline structure, approval queue, checker, verifier, and ingest tests |

### Non-obvious decisions recorded

- **`LoopAgent` exit via `escalate=True`**: The `LoopAgent` exits when any child event has `actions.escalate = True`. This is not a callback or a tool return — it is set directly on the yielded `Event`.
- **`output_schema` + tools coexist in ADK 2.7.1**: Despite the docs suggesting otherwise, you can set `output_schema` on an `LlmAgent` that also has sub-agents (tools added by ADK internally).
- **`object.__setattr__`** needed to patch frozen Pydantic Gemini model for retry callbacks.

### Result

**191 tests passing** — `python -m pytest`

### Plan

Authored before implementation: [`passline-mission06-plan.md`](../passline-mission06-plan.md)

---

## Mission 07 — Going Public

**Date:** August 20, 2026

### What was built

| Deliverable | Description |
|---|---|
| `requirements.txt` | Exact pinned venv dependencies for Cloud Run buildpack |
| `.python-version` | `3.12` pin for buildpack |
| `Procfile` | `web: uvicorn passline.dashboard.app:app --host 0.0.0.0 --port $PORT` |
| `.gcloudignore` | Excludes `.env`, `.venv`, test fixtures, plan files, pycache |
| `PORT` env var | Dashboard `run()` prefers `PORT` then `PASSLINE_PORT` then `8000` |
| `/tmp` log default | `_LOG_PATH` defaults to `/tmp/passline_events.jsonl` for container safety |
| `LanguageCheckerAgent` rewrite | `BaseAgent` calling google-genai directly — no ADK callback magic; tenacity retry on 429 |
| `FindingsMergerAgent` | New `BaseAgent` that merges `timing_findings + format_findings + language_findings → all_findings` before the repair loop; deduplicates by `(cue_index, rule)` |
| Verifier language preservation | `VerifierAgent` now preserves MT01–MT06 language findings that are not superseded by deterministic findings after each repair pass |
| Station event vocabulary | All 7 agents emit `station_id` / `station_name` matching the demo fixture; helper module `event_utils.py` centralises this |
| `cue.analysis` event | `IngestAgent` emits per-cue CPS + duration data for the dashboard heat strip |
| `qc.repaired` fields | `FixerAgent` emits `{rule, cue, original, repaired}` matching the demo fixture |
| Demo chip → real pipeline | `triggerDemo()` JS now fetches `/api/demo/{lang}` and POSTs to `/api/upload`; no `startReplay()` |
| `/api/demo/{lang}` | New FastAPI endpoint serving bundled broken corpus SRTs (EN/FR/DE) |
| `/api/download/{id}` | New FastAPI endpoint returning repaired SRT bytes for a completed delivery |
| `/api/reset` | Truncates the event log for a clean board take |
| `get_repaired_bytes()` fix | Replaced sync `loop.run_until_complete()` crash with `async get_repaired_bytes()` |
| FR/DE meaning-level corpus | Added vocabulary pairs present in the Blender TOS corpus; regenerated broken SRTs with ≥1 MEANING_LEVEL defect per language (FR: cues 24, 75; DE: cues 20, 66) |
| `tests/conftest.py` | `--live-llm` CLI option + `live_llm` marker; merged with pre-existing fixtures |
| `test_language_grading_meaning_level` | Parametrised over EN/FR/DE; skipped without `--live-llm` |
| `tests/test_dashboard.py` | 19 async ASGI tests (httpx `ASGITransport`) covering all dashboard endpoints |
| `tests/test_e2e_pipeline.py` | Full offline end-to-end test: LLM stubbed, approval gate driven concurrently |
| Coordinator instruction fix | Replaced "invoke run_pipeline tool" with correct ADK `transfer_to_agent` delegation description |
| Coordinator fallback | `after_agent_callback` runs pipeline directly if LLM fails to produce a `report` |
| README fix | CI badge owner corrected (`luisyanza → yanzaaa`); quickstart updated; structure diagram updated; dashboard and deploy instructions added |
| `.env.example` | All environment variables documented with defaults and comments |

### Corpus defect counts after Mission 07 regeneration (seed=42)

| Language | DETERMINISTIC | MEANING_LEVEL | Total |
|---|---|---|---|
| EN | 10 | 2 | 12 |
| FR | 10 | 2 | 12 |
| DE | 10 | 2 | 12 |

### Non-obvious decisions recorded

- **`asyncio.get_event_loop().run_until_complete()` breaks after anyio closes the loop**: Switching to `asyncio.run()` in all sync test helpers fixed the contamination.
- **FR substitution words not in Blender TOS corpus**: The original FR pairs (`toujours`, `jamais`, etc.) don't appear in the specific SRT. Added common antonyms (`bien/mal`, `tout/rien`, `maintenant/jamais`) that ARE present.
- **Demo corpus must be committed inside the package**: Cloud Run buildpacks include only the Python package source. Corpus files in `tests/` are excluded by `.gcloudignore`; the demo SRTs are copied to `passline/corpus/demo/` so they ship with the package.
- **`PipelineRunner` runs under coordinator LLM**: For offline tests, bypass the coordinator and run `build_pipeline()` directly through an ADK `Runner` with a pre-populated session. The coordinator's LLM is unavailable without credentials.

### Result

**214 tests passing, 3 skipped** (live LLM tests behind `--live-llm`) — `python -m pytest`

### Plan

Authored before implementation: [`passline-mission07-plan.md`](../passline-mission07-plan.md)

### Verification commands

```bash
source .venv/bin/activate

# Full test suite (no credentials needed)
python -m pytest

# Run only dashboard tests
python -m pytest tests/test_dashboard.py -v

# Run end-to-end pipeline test (LLM stubbed)
python -m pytest tests/test_e2e_pipeline.py -v

# Run live LLM meaning-level grading (requires credentials)
python -m pytest tests/test_grading.py -v --live-llm

# Start the dashboard
passline-dashboard
open http://localhost:8000

# Deploy to Cloud Run
gcloud run deploy passline --source . --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=your-project-id
```

---

## Mission 08 — The Show

**Date:** August 23, 2026

### What was built

| Deliverable | Description |
|---|---|
| Bounded Demo Corruption | `corrupt_demo` function in `corrupt.py` implementing adjacent-cue guards, layout bounds, and deterministic defects repairable in 3 passes |
| Three Demo Excerpts | English, French, and German demo broken files generated deterministically and stored under `passline/corpus/demo/` alongside JSON manifests |
| Hopeless-case Showcase | Over-corrupted French file copied as `hopeless-fr.srt` serving as an unfixable control showcasing honest failures |
| Connected Break Button | Sever-side `POST /api/break/{id}` endpoint and client `triggerBreak()` re-corrupting repaired output with random seeds and re-firing pipeline |
| Honest-fail Event Type | New `DELIVERY_FAILED = "delivery.failed"` (schema v1.3) emitting rule-breakdown details on remaining violations and preventing dead download links |
| Style-guide Citations | `/api/style-guide/{rule_ref}/{lang}` endpoint serving per-language style guides with neutral section citations and expandable popovers |
| Spoken Briefing System | `/api/briefing/{id}` endpoint concatenating Puck, Charon, and Kore speech configs using unified `google.genai` SDK |
| Mode & Reset Polish | **LIVE** vs **REPLAY** tagging, slow-pulsing wait animations, and robust reset returning log, counters, clocks, and charts to blank state |

### Non-obvious decisions recorded

- **Patched ADK Coordinator in Tests**: Bypassed coordinator LLM in E2E tests by patching `build_coordinator` to return `pipeline` directly, ensuring E2E tests run fully hermetically in CI without network or Vertex API keys.
- **Python-native WAV Merging**: Appended speech files by copying raw frames and parameters using the standard library `wave` module instead of bringing in external multimedia libraries.
- **Deterministic Replay Detection**: Mode tags determined client-side by checking if `delivery_id` starts with `"DEMO-"`, avoiding complex server-side session tracking.

### Result

**235 tests passing, 3 skipped** (live LLM tests behind `--live-llm`) — `python -m pytest`

### Plan

Authored before implementation: [`passline-mission08-plan.md`](../passline-mission08-plan.md)

### Verification commands

```bash
source .venv/bin/activate

# Run the full test suite (including the new Mission 08 tests)
python -m pytest

# Run only Mission 08 evidence tests
python -m pytest tests/test_mission08_evidence.py -v

# Run only demo repairability tests
python -m pytest tests/test_demo_repairability.py -v
```
