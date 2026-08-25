# Passline

[![CI](https://github.com/yanzaaa/passline/actions/workflows/ci.yml/badge.svg)](https://github.com/yanzaaa/passline/actions/workflows/ci.yml)

**Multi-agent subtitle quality control and repair system for streaming delivery workflows**

**🌟 LIVE DEMO: [https://passline-x24264ca3q-ue.a.run.app](https://passline-x24264ca3q-ue.a.run.app)** — Click the "English" chip under Demo controls to watch the live pipeline catch and repair defects!

**Compliance Statement:** The only AI dependencies are the two Google libraries (`google-adk` and `google-genai`), both called at runtime, and the project was built using IBM Bob.

Built on [Google's Agent Development Kit](https://google.github.io/adk-docs/) with
Gemini on Vertex AI.

---

## What it is

Passline automates the subtitle QC pipeline for streaming delivery: it ingests SRT
files, runs a deterministic rule engine to check timing, reading speed, and line
length, flags violations, and invokes a Gemini-powered agent to assess and suggest
repairs at the language level.

**Core design principle:**
> The deterministic rule engine does all arithmetic — timing, characters per second,
> line lengths. The LLM makes only language-level judgments: is this text readable?
> Is it natural? Does it need rephrasing? No LLM ever decides math.

---

## Built with IBM Bob — Agentic Cinema Hackathon (IBM Track)

Passline is an entry in the **Agentic Cinema hackathon**, IBM track.
IBM Bob drove the build, authored the plan document for every mission before implementation, implemented the missions in Agent mode, and wrote the two-job continuous integration pipeline, while routine iteration and cosmetic passes were carried by other tooling.

- 📓 [Build Journal](docs/BUILD_JOURNAL.md) — mission-by-mission log of what was built
- 📐 [Foundation Plan](passline-foundation-plan.md) — the Mission 01 architecture plan

---

## Quickstart

**Requirements:** Python 3.12 or 3.13 for local development and continuous integration. The deployed container on Cloud Run explicitly runs Python 3.13.

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
- **▶ PLAY** — replay a pre-recorded demo delivery run (shows the orange **REPLAY** tag; replay cards offer no dead download links)
- **Demo chips** (English / French / German / Hopeless Case) — upload the newly generated demo-grade broken excerpt files or the hopeless control, running the real E2E pipeline (shows the green **LIVE** tag)
- **⚡ BREAK THIS FILE** — takes the repaired output of the last cleared delivery, corrupts it server-side, and feeds it straight back through the pipeline as a new child delivery.
- **▶ Briefing** — after a delivery clears or fails, click to listen to a 25-second spoken E2E summary generated with three distinct prebuilt Google GenAI voices.
- **Drop zone** — drop any `.srt` file to run it through the pipeline
- **RESET** — clear the board for a clean take (cards, logs, station meters, charts, countdown all return to initial slate)
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
├── events/         Delivery event bus (JSONL log)
├── io/             SRT parser and writer
├── models/         Subtitle cue and file data models
├── pipeline/       PipelineRunner, ApprovalQueue
└── qc/             Deterministic rule engine + thresholds
tests/
├── corpus/         Clean SRTs, broken SRTs, ground-truth manifests
├── fixtures/       Golden SRT files + demo event fixture
├── conftest.py     Shared fixtures, --live-llm CLI option
├── test_pipeline.py     ADK agent structure + approval queue + checker tests
├── test_dashboard.py    Dashboard endpoint tests (httpx ASGI)
├── test_e2e_pipeline.py End-to-end offline pipeline test (LLM stubbed)
├── test_grading.py      Corpus grading + live LLM meaning-level test
└── test_*.py            Unit tests for parsers, models, rules, corpus
docs/
└── BUILD_JOURNAL.md  Mission-by-mission build log
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

# Run tests for one module
python -m pytest tests/test_pipeline.py -v

# Run corpus grading tests
python -m pytest tests/test_grading.py -v

# Run dashboard endpoint tests
python -m pytest tests/test_dashboard.py -v

# Run end-to-end pipeline test (LLM stubbed, no credentials needed)
python -m pytest tests/test_e2e_pipeline.py -v

# Run live LLM grading test (requires GOOGLE_API_KEY or GOOGLE_CLOUD_PROJECT)
python -m pytest tests/test_grading.py -v --live-llm
```

---

## Acknowledgments & Licenses

### Style Guide
The style guide citation table ships with the project as a neutral illustrative house guide with no affiliation to any distributor's specification. A real deployment would swap in its own proprietary style guide definitions.

### Tears of Steel (Corpus Assets)
© Blender Foundation | [mango.blender.org](https://mango.blender.org)
The subtitle assets used for demonstration and testing are licensed under [Creative Commons Attribution 3.0 (CC-BY 3.0)](https://creativecommons.org/licenses/by/3.0/).

## License

MIT — see [LICENSE](LICENSE).

## Origination System (Mission 09)
Passline now supports speech-to-delivery origination via microphone recording.
