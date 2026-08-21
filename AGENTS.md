# AGENTS.md

This file provides guidance to agents when working with code in this repository.

> Passline is a multi-agent subtitle QC and repair system for streaming delivery workflows, built on Google's Agent Development Kit with Gemini on Vertex AI. Core principle: the rule engine is pure deterministic Python — no LLM ever decides math. LLMs are used only for language-level judgment. Everything is verified with golden-file tests.

## Project

**passline** — Python 3.12 multi-agent subtitle QC system on Google ADK 2.7.1 + Gemini.

## Environment

- Python 3.12 via `.venv/` — always activate: `source .venv/bin/activate`
- `pip install -e ".[dev]"` — installs the package + pytest in editable mode
- Secrets in `.env` (gitignored), loaded via `python-dotenv`

## Commands

```bash
# Run the full test suite
python -m pytest

# Run a single test file
python -m pytest tests/test_pipeline.py

# Run a single test by name
python -m pytest tests/test_grading.py::test_corpus_grading_exact_match[en]

# Smoke-test entry point (no credentials needed)
python -m passline

# Corpus grading report (runs rule engine against all broken fixtures)
python scripts/corpus_report.py

# Regenerate corpus golden files (seed=42 is canonical)
python scripts/generate_corpus.py --seed 42

# Run the dashboard (requires GOOGLE_API_KEY or GOOGLE_CLOUD_PROJECT)
passline-dashboard
```

## Architecture

| Layer | Module | Purpose |
|---|---|---|
| Models | `passline/models/subtitle.py` | `SubtitleCue`, `SubtitleFile`, `SrtDialect` |
| I/O | `passline/io/srt.py` | `parse_srt`, `write_srt` |
| QC | `passline/qc/` | Rule engine: `thresholds.py` → `rules.py` → `check_file()` |
| Corpus | `passline/corpus/corrupt.py` | Deterministic corruption engine |
| Events | `passline/events/bus.py` | JSONL event bus, schema 1.2 |
| Dashboard | `passline/dashboard/` | FastAPI + SSE mission control |
| **Agents** | `passline/agents/` | Full ADK pipeline (Mission 06) |
| **Pipeline** | `passline/pipeline/` | `ApprovalQueue`, `PipelineRunner` |

## ADK Agent Graph (Mission 06)

```
RootCoordinator (LlmAgent, gemini-3-flash-preview)
└── DeliveryPipeline (SequentialAgent)
    ├── IngestAgent          BaseAgent — parse_srt, no LLM
    ├── CheckerFanout        ParallelAgent
    │   ├── TimingCheckerAgent  BaseAgent — CPS/duration/overlap rules
    │   ├── FormatCheckerAgent  BaseAgent — line_too_long/three_line_cue
    │   └── LanguageCheckerAgent  LlmAgent, gemini-3.1-pro-preview, output_schema
    ├── RepairLoop           LoopAgent, max_iterations=3
    │   ├── FixerAgent       LlmAgent, gemini-3-flash-preview (LLM for text only)
    │   └── VerifierAgent    BaseAgent — escalate=True when findings == 0
    └── ReporterAgent        BaseAgent — write_srt, delivery verdict
```

## Critical non-obvious rules

- **Single threshold source**: `passline/qc/thresholds.py` — both `corrupt.py` and `rules.py` import from it. Never define a threshold elsewhere.
- **Math always from model properties**: `check_file()` uses `cue.cps`, `cue.duration_ms`, `cue.char_counts` — never re-implements math.
- **LoopAgent exit via `escalate`**: Verifier sets exit by yielding `Event(actions=EventActions(escalate=True))` — NOT a callback. Max 3 iterations.
- **`output_schema` + tools coexist in ADK 2.7.1**: No mutual exclusion. `LanguageCheckerAgent` has `output_schema=LanguageCheckerOutput` but no tools.
- **State writes**: Agents write `ctx.session.state` implicitly via `EventActions(state_delta={...})` on yielded events.
- **Retry patch**: `install_retry_on_model()` from `callbacks.py` must use `object.__setattr__` on the Gemini model (Pydantic frozen). Called after agent construction.
- **Approval queue gates**: `ApprovalQueue.await_decision(item_id)` is an async gate (`asyncio.Event`). The repair loop suspends in-place until ALL queued items are resolved.
- **Corpus grading filter uses `(cue_index, rule)` pairs**, not just `cue_index`. Pre-existing Blender violations on the same cue as an injected defect are ignored by design.
- **`write_file` tool redirects `passline/` paths** to workspace root. Always write `passline/` files via shell `cat >` with absolute paths.
- **`asyncio.coroutine` removed in Python 3.12** — already patched in dashboard.
- **Schema version is `"1.2"`** — always has `event_id`, UTC enforcement.
- **Pydantic v2** — `model_validator(mode='after')`, `model_config`, `.model_dump()`.
- **Classic template workflow agents**: `SequentialAgent`, `ParallelAgent`, `LoopAgent` are deprecated in ADK 2.7.1 in favour of the graph workflow API, but they still work and are required by this project's spec. The deprecation warnings are expected and harmless.

## Key environment variables

| Variable | Default | Purpose |
|---|---|---|
| `PASSLINE_QC_MODEL` | `gemini-2.5-flash` | Gemini model for existing QC agent |
| `PASSLINE_COORDINATOR_MODEL` | `gemini-3-flash-preview` | Root coordinator model |
| `PASSLINE_LANG_MODEL` | `gemini-3.1-pro-preview` | Language checker model |
| `PASSLINE_FIXER_MODEL` | `gemini-3-flash-preview` | Fixer agent model |
| `GOOGLE_API_KEY` | — | Gemini Developer API key |
| `GOOGLE_CLOUD_PROJECT` | — | GCP project for Vertex AI |
| `GOOGLE_CLOUD_LOCATION` | `us-central1` | GCP location for Vertex AI |
| `PASSLINE_LOG` | `passline_events.jsonl` | Event log path |

## Testing

- **191 tests passing**: `python -m pytest`
- Pipeline tests in `tests/test_pipeline.py` (42 tests, fully offline — no LLM calls)
- Golden SRT fixtures in `tests/fixtures/` — marked `binary` in `.gitattributes`
- Corpus fixtures in `tests/corpus/` — seed=42, 3 languages, DETERMINISTIC/MEANING_LEVEL split
- Property-based tests in `test_rule_properties.py` use `random.Random` with fixed seeds

## CI

- `.github/workflows/ci.yml` — two jobs:
  1. `test` — runs `pytest` on every push (required to pass)
  2. `corpus-report` — posts grading table as PR comment (`continue-on-error: true`)

## API Routes (dashboard)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Dashboard HTML |
| `GET` | `/api/events` | SSE stream (live + backfill) |
| `GET` | `/api/history` | All events as JSON |
| `POST` | `/api/replay` | Start demo replay |
| `POST` | `/api/stop` | Stop demo replay |
| `POST` | `/api/upload` | Upload SRT → runs real pipeline |
| `GET` | `/api/queue` | List pending approval items |
| `POST` | `/api/queue/{id}/approve` | Approve a pending item |
| `POST` | `/api/queue/{id}/reject` | Reject a pending item |
