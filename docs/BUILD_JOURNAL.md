# Build Journal — Built with IBM Bob

Every line of Passline source code, tests, and configuration is planned and written
by **IBM Bob** inside this repository. No human authored any source file.
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
