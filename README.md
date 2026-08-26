# Passline

[![CI](https://github.com/yanzaaa/passline/actions/workflows/ci.yml/badge.svg)](https://github.com/yanzaaa/passline/actions/workflows/ci.yml)

**Multi-agent subtitle quality control and origination system for streaming delivery workflows**

**🌟 LIVE DEMO: [https://passline-x24264ca3q-ue.a.run.app](https://passline-x24264ca3q-ue.a.run.app)**

**Compliance Statement:** The only AI dependencies are the two Google libraries (`google-adk` and `google-genai`), both called at runtime. The project was built using IBM Bob.

Built on [Google's Agent Development Kit](https://google.github.io/adk-docs/) with Gemini on Vertex AI.

---

## What it does

Subtitle QC failures are a leading cause of delivery rejection on streaming platforms. Every rejection initiates a multi-day redelivery cycle: QC re-run, asset re-packaging, re-ingest, re-validation across distributor systems. The operational cost is not an abstraction — it is measurable in vendor time, platform SLA penalties, and release schedule slippage.

Passline exists to eliminate that failure mode. It ingests SRT files, runs a deterministic rule engine that checks timing, reading speed, and line length, flags every violation, and invokes a Gemini-powered agent to assess and suggest repairs at the language level. For origination workflows, it accepts raw audio or video, produces cued subtitles in the source language via Gemini transcription, translates into eight target languages, and submits each translation directly into the QC pipeline — the same path a human operator would follow.

**Core design principle:**
> The deterministic rule engine does all arithmetic — timing, characters per second,
> line lengths. The LLM makes only language-level judgments: is this text readable?
> Is it natural? Does it need rephrasing? No LLM ever decides math.

---

## Eight languages, two script families, one rule contract

Passline operates across eight languages: English (`en`), French (`fr`), German (`de`), Spanish (`es`), Portuguese (`pt`), Russian (`ru`), Farsi (`fa`), and Mandarin Chinese (`zh`). These are the exact language codes in `passline/origination/orchestrator.py`.

The rule engine in `passline/qc/rules.py` routes each file to one of two profile families based on the language code. The numeric thresholds live exclusively in `passline/qc/thresholds.py` — they are imported by the rule engine, the corruption engine, and the cue builder. No threshold is defined in two places.

| Threshold | Latin profile | CJK profile (`zh`, `ja`, `ko`) |
|---|---|---|
| CPS error limit | 20.0 | 9.0 |
| CPS warning band | 17.0 – 20.0 | 7.0 – 9.0 |
| Line length limit | 42 chars | 16 display columns |
| Russian override | 39 chars | — |

The profiles are not shared across script boundaries. The Latin profile measures line length in raw visible characters. The CJK profile measures in East Asian display columns — wide (`W`) and fullwidth (`F`) characters count as 2, all others as 1 — using `unicodedata.east_asian_width` in both `SubtitleCue.display_char_counts` and `cue_builder._display_width`. This is not a style preference. It is a physical rendering constraint: a CJK character occupies two monospace columns on every display that matters.

### Why per-script profiles are non-negotiable: the clean Chinese file test

`tests/test_corpus.py` (`TestCJKProfile`) demonstrates the stakes directly. It runs the same pristine Chinese subtitle file through `check_file` twice — once with `language="en"` (Latin profile) and once with `language="zh"` (CJK profile). The test asserts that the Latin profile produces fewer than 10 findings and the CJK profile produces more than 50. The test comment records an observed run of approximately 96 CJK findings on the same file that passes nearly clean under the Latin profile.

The reason is measurement unit. Under the Latin 42-character limit, most Chinese cues look short — their byte-visible character count is well below 42. Under the CJK 16-column limit, those same cues are over the line: each Chinese character occupies 2 display columns, so a 9-character Chinese line is already 18 display columns. The Latin profile literally cannot see the violation. The CJK profile cannot miss it.

This experiment is the clearest proof-of-concept the system has. A QC pipeline that applies a Latin profile to a Chinese subtitle delivery will pass files that are objectively unreadable on the target device. Passline routes by script family. The rule is never applied to the wrong alphabet.

---

## Origination pipeline

Before Mission 09, Passline was a QC and repair system. You gave it an SRT file; it checked and fixed it. Mission 09 added an origination path: give it audio or video, and it produces delivery-ready subtitles in eight languages.

The origination flow is implemented across four modules in `passline/origination/`:

**`transcriber.py` — Gemini speech-to-text**
Sends media bytes inline to `gemini-3-flash-preview` via the `google-genai` async client. Returns a list of `TranscriptSegment` objects (`word`, `start_s`, `end_s`). Enforces a 20 MB size guard before making the API call. The model returns word-level or phrase-level timestamps depending on the language; the cue builder handles both granularities identically.

**`cue_builder.py` — deterministic cue assembly**
Pure Python. No LLM. Takes `TranscriptSegment` objects and assembles a `SubtitleFile` that is guaranteed to pass `check_file` with zero violations on timing, line length, and CPS. All numeric limits are imported from `passline/qc/thresholds.py`. The algorithm: greedy line packing → minimum duration enforcement → overlap prevention → CPS reflow (splits cues that exceed the limit by splitting the word list at segment boundaries). CJK display-width measurement uses the same `unicodedata.east_asian_width` function as the rule engine, so assembled cues are consistent with what QC will later measure.

**`translator.py` — structured translation via Gemini**
Sends the source `SubtitleFile` as a JSON array to `gemini-2.5-flash`. Returns a new `SubtitleFile` with translated `lines` and identical `start_ms`/`end_ms`. `SubtitleCue` is frozen (Pydantic `model_config = ConfigDict(frozen=True)`), so replacement is always via new object construction. Tenacity retry on `APIError`, max 5 attempts with exponential backoff.

**`orchestrator.py` — end-to-end job management**
`start_origination()` creates an `OriginationJob`, schedules the async job, and returns a `job_id`. The job runs: transcribe → build source cues → fan-out across `LANGUAGES = ["en", "fr", "de", "es", "ru", "pt", "zh", "fa"]` (staggered by 2 seconds to avoid quota collisions) → `PipelineRunner.run_delivery()` per language. Each language delivery appears in the dashboard as a normal delivery card. The origination job has no special status path in the QC pipeline; it hands off to the same `PipelineRunner` a human upload would use.

The browser capture path uses the native `MediaRecorder` API with `audio/webm;codecs=opus`. No server-side transcoding is required because the validation experiment in Mission 09 confirmed that Gemini accepts inline WebM audio without a format conversion step.

---

## ADK agent graph

```
RootCoordinator (LlmAgent, gemini-3-flash-preview)
└── DeliveryPipeline (SequentialAgent)
    ├── IngestAgent          BaseAgent — parse_srt, emits cue.analysis
    ├── CheckerFanout        ParallelAgent
    │   ├── TimingCheckerAgent    BaseAgent — CPS/duration/overlap rules
    │   ├── FormatCheckerAgent    BaseAgent — line_too_long/three_line_cue
    │   └── LanguageCheckerAgent  BaseAgent — calls Gemini directly, tenacity retry
    ├── FindingsMergerAgent  BaseAgent — merges all findings → all_findings
    ├── RepairLoop           LoopAgent, max_iterations=3
    │   ├── FixerAgent       LlmAgent, gemini-3-flash-preview (LLM for language text only)
    │   └── VerifierAgent    BaseAgent — escalate=True when combined findings == 0
    └── ReporterAgent        BaseAgent — write_srt, delivery verdict
```

`SequentialAgent`, `ParallelAgent`, and `LoopAgent` are the classic ADK template workflow classes. They are deprecated in ADK 2.7.1 in favour of the graph workflow API but continue to work on the pinned version. They are used here intentionally because they express the exact sequential, parallel, and loop structure the pipeline requires. The deprecation warnings are expected and harmless.

Deterministic repairs (timing corrections, line splits) are applied inside `FixerAgent` without any LLM call. Only language-level findings (MT01–MT06: mistranslation, register, spelling, inconsistency, offensive language, formatting) go to the LLM. The `VerifierAgent` re-runs the deterministic rule engine after each repair pass and escalates the loop when combined findings reach zero. If violations remain after three passes, the pipeline emits a `delivery.failed` event (schema v1.3) with a per-rule breakdown and prevents a dead download link from appearing in the dashboard.

The `ApprovalQueue` gates meaning-changing repairs. Every language-level edit is enqueued before the repair loop suspends. Each item has its own `asyncio.Event` gate. The loop waits for all gates to resolve. Human operators approve or reject via the dashboard UI at `/api/queue/{id}/approve` and `/api/queue/{id}/reject`.

---

## How Bob built this — tooling disclosure

Passline is an entry in the Agentic Cinema hackathon, IBM track. IBM Bob drove the build.

Bob authored the mission plan document before any implementation began for every mission, from the foundation through origination. Nine plan files remain committed at the repository root (`passline-foundation-plan.md` through `passline-mission09-plan.md`). They are not documentation retrofitted after the fact — they are the authorship record of intent, architecture, and decision-making that preceded every line of code.

Gemini CLI — also a Google product, like the Gemini transcription service used in the origination pipeline — served as the iteration engine, carrying out the implementation work defined in those plans. This is a straightforward account of a modern AI-assisted development workflow. Human authorship of intent and architecture is unambiguous; it is documented in the plan files and in the `.bob/` directory.

---

## The `.bob/` directory — Bob's operational fingerprint

The `.bob/` directory contains three rule files that define Bob's three distinct operating modes:

**`.bob/rules-plan/AGENTS.md` — Plan mode**
Encodes architectural constraints that must be respected before implementation begins. Key rules: the deterministic rule engine is pure Python — no LLM ever decides math; `passline/qc/thresholds.py` is a hard dependency contract between the rule engine, the corruption engine, and the fixer agent; the corpus is committed golden data at seed=42; CI has two jobs with defined failure semantics; classic ADK template workflow agents are required by spec. Plan mode is where architecture gets locked before code gets written.

**`.bob/rules-agent/AGENTS.md` — Agent mode**
Encodes coding patterns that must be followed during implementation. Key rules: math always from model properties (`cue.cps`, `cue.duration_ms`, `cue.char_counts`) — never reimplemented inside the rule engine; CPS `measured_value` is full precision (property tests assert `abs(finding.measured_value - cue.cps) < 1e-6`); Pydantic v2 patterns (`model_validator(mode='after')`, `.model_dump()`); `LoopAgent` exits via `event.actions.escalate = True` — not a callback; session state writes go through `EventActions(state_delta={...})`; `ApprovalQueue.await_decision()` is an async gate and must never be called from synchronous code. Agent mode is where the architectural decisions get translated into working code.

**`.bob/rules-ask/AGENTS.md` — Ask mode**
Encodes documentation canonicity rules. Key rules: `passline/qc/thresholds.py` is the canonical reference for all numeric limits — not inline comments; corpus manifests split defects into `DETERMINISTIC` and `MEANING_LEVEL` categories; the rule engine is graded only against DETERMINISTIC entries; `passline_events.jsonl` is a runtime output file, gitignored; plan files live at the repo root. Ask mode is what keeps documentation honest when someone asks a question about the system.

This directory is Bob's operational fingerprint. It encodes how Bob plans, how Bob executes autonomously, and how Bob responds to direct questions. Any judge or auditor examining provenance will find in these files a complete and specific account of the decision framework that governed every implementation choice in this codebase.

---

## Built with IBM Bob — Agentic Cinema Hackathon (IBM Track)

- 📓 [Build Journal](docs/BUILD_JOURNAL.md) — mission-by-mission construction record
- 📐 [Foundation Plan](passline-foundation-plan.md) — Mission 01 architecture plan

---

## Quickstart

**Requirements:** Python 3.12 or 3.13. The deployed container on Cloud Run runs Python 3.13.

```bash
# 1 — Clone and enter the repo
git clone https://github.com/yanzaaa/passline.git
cd passline

# 2 — Create a virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# 3 — Install the package and dev dependencies
pip install -e ".[dev]"

# 4 — Set up credentials (copy the example env file, then fill it in)
cp .env.example .env
# Edit .env: add GOOGLE_CLOUD_PROJECT or GOOGLE_API_KEY

# 5 — Run the test suite (no credentials needed)
python -m pytest

# 6 — Run the entry-point smoke-test
python -m passline
```

---

## Run the dashboard

```bash
# Start the Mission Control dashboard on http://localhost:8000
source .venv/bin/activate
passline-dashboard
# or: python -m passline.dashboard.app

# Open in browser
open http://localhost:8000
```

The dashboard supports:
- **▶ PLAY** — replay a pre-recorded demo delivery run (shows the orange **REPLAY** tag; replay cards expose no download links)
- **Demo chips** (English / French / German / Hopeless Case) — run the real end-to-end pipeline on a deterministically broken excerpt file (shows the green **LIVE** tag)
- **⚡ BREAK THIS FILE** — takes the repaired output of the last cleared delivery, corrupts it server-side, and feeds it back through the pipeline as a new child delivery
- **▶ Briefing** — after a delivery clears or fails, generates a 25-second spoken summary using three distinct Puck, Charon, and Kore GenAI voices
- **Drop zone** — drop any `.srt` file to run it through the pipeline
- **🎙 RECORD** — record microphone audio directly in the browser and submit it to the origination pipeline
- **RESET** — return cards, logs, station meters, charts, and countdown to initial state
- **Approval queue** — approve or reject language-level repairs via the UI

---

## Deploy to Cloud Run

```bash
# Build and deploy (uses Google Cloud Buildpacks — no Dockerfile needed)
gcloud run deploy passline \
  --source . \
  --region us-east1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=your-project-id,GOOGLE_CLOUD_LOCATION=global
```

---

## Project structure

```
passline/
├── agents/         Google ADK agent graph
│   ├── pipeline.py         Full SequentialAgent pipeline
│   ├── coordinator.py      Root LlmAgent coordinator
│   ├── ingest_agent.py     Stage 1: SRT parse
│   ├── timing_checker.py   Stage 2a: timing rules
│   ├── format_checker.py   Stage 2b: format rules
│   ├── language_checker.py Stage 2c: LLM language check (BaseAgent)
│   ├── findings_merger.py  Stage 2d: merge all findings
│   ├── fixer_agent.py      Stage 3a: deterministic + LLM repair
│   ├── verifier_agent.py   Stage 3b: loop exit controller
│   └── reporter_agent.py   Stage 4: delivery report
├── corpus/         Corruption engine + substitution pairs + demo SRTs
├── dashboard/      FastAPI app, SSE stream, replay engine, HTML UI
├── events/         Delivery event bus (JSONL log, schema v1.3)
├── io/             SRT parser and writer
├── models/         SubtitleCue, SubtitleFile, SrtDialect
├── origination/    Speech-to-delivery pipeline
│   ├── transcriber.py      Gemini speech-to-text → TranscriptSegment list
│   ├── cue_builder.py      Pure Python: segments → SubtitleFile
│   ├── translator.py       Gemini translation: SubtitleFile → SubtitleFile
│   └── orchestrator.py     Job management + 8-language fan-out
├── pipeline/       PipelineRunner, ApprovalQueue
└── qc/             Deterministic rule engine + thresholds
    ├── thresholds.py       Single source of truth for all numeric limits
    └── rules.py            check_file() → list[Finding]
tests/
├── corpus/         Clean SRTs, broken SRTs, ground-truth manifests (8 languages)
├── fixtures/       Golden SRT files
├── conftest.py     Shared fixtures, --live-llm CLI option
├── test_pipeline.py     ADK agent structure + approval queue + checker tests
├── test_dashboard.py    Dashboard endpoint tests (httpx ASGI)
├── test_e2e_pipeline.py End-to-end offline pipeline test (LLM stubbed)
├── test_grading.py      Corpus grading + live LLM meaning-level test
├── test_corpus.py       CJK profile test + defect unit tests
├── test_cue_builder.py  Golden-file suite for the origination cue builder
└── test_*.py            Unit tests for parsers, models, rules, origination
docs/
└── BUILD_JOURNAL.md  Mission-by-mission construction record
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | — | GCP project ID (for Vertex AI) |
| `GOOGLE_CLOUD_LOCATION` | `us-east1` | Vertex AI region |
| `GOOGLE_API_KEY` | — | Gemini API key (alternative to Vertex AI) |
| `PASSLINE_LANG_MODEL` | `gemini-3.1-pro-preview` | Model for language checker |
| `PASSLINE_FIXER_MODEL` | `gemini-3-flash-preview` | Model for fixer agent |
| `PASSLINE_COORDINATOR_MODEL` | `gemini-3-flash-preview` | Model for coordinator |
| `PORT` | `8000` | Dashboard server port (Cloud Run sets this) |
| `PASSLINE_PORT` | `8000` | Dashboard server port (alternative) |
| `PASSLINE_LOG` | `/tmp/passline_events.jsonl` | Event log path |
| `PASSLINE_TTS_ENABLED` | `true` | Enable speech briefing audio generation |
| `PASSLINE_TTS_MAX_GENERATIONS` | `50` | Maximum speech briefing generations per server process |

See `.env.example` for a ready-to-copy template.

---

## Run a single test

```bash
# Run one specific test
python -m pytest tests/test_pipeline.py::TestPipelineStructure::test_pipeline_name -v

# Run corpus grading tests
python -m pytest tests/test_grading.py -v

# Run the CJK profile test
python -m pytest tests/test_corpus.py::TestCJKProfile -v

# Run dashboard endpoint tests
python -m pytest tests/test_dashboard.py -v

# Run end-to-end pipeline test (LLM stubbed, no credentials needed)
python -m pytest tests/test_e2e_pipeline.py -v

# Run cue builder golden-file tests (no credentials needed)
python -m pytest tests/test_cue_builder.py -v

# Run live LLM grading test (requires GOOGLE_API_KEY or GOOGLE_CLOUD_PROJECT)
python -m pytest tests/test_grading.py -v --live-llm
```

---

## API routes (dashboard)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Dashboard HTML |
| `GET` | `/api/events` | SSE stream (live + backfill) |
| `GET` | `/api/history` | All events as JSON |
| `POST` | `/api/replay` | Start demo replay |
| `POST` | `/api/stop` | Stop demo replay |
| `POST` | `/api/upload` | Upload SRT → runs real pipeline |
| `POST` | `/api/reset` | Truncate event log, stop replay |
| `GET` | `/api/demo/{lang}` | Serve bundled broken corpus SRT (`en`/`fr`/`de`) |
| `GET` | `/api/download/{id}` | Download repaired SRT bytes |
| `GET` | `/api/style-guide/{rule_ref}/{lang}` | Per-language style guide citation |
| `GET` | `/api/briefing/{id}` | Spoken delivery summary (WAV) |
| `POST` | `/api/break/{id}` | Re-corrupt a repaired delivery and re-run pipeline |
| `GET` | `/api/queue` | List pending approval items |
| `POST` | `/api/queue/{id}/approve` | Approve a pending repair |
| `POST` | `/api/queue/{id}/reject` | Reject a pending repair |
| `POST` | `/api/originate` | Start origination job from audio/video file |
| `GET` | `/api/originate/status/{job_id}` | Poll origination job progress |

---

## Acknowledgments & Licenses

### Style Guide
The style guide citation table ships as a neutral illustrative house guide with no affiliation to any distributor's specification. A real deployment would replace the bundled citations with its own proprietary style guide definitions.

### Tears of Steel (Corpus Assets)
© Blender Foundation | [mango.blender.org](https://mango.blender.org)
Subtitle assets used for demonstration and testing are licensed under [Creative Commons Attribution 3.0 (CC-BY 3.0)](https://creativecommons.org/licenses/by/3.0/).

## License

MIT — see [LICENSE](LICENSE).
