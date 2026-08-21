# Passline

[![CI](https://github.com/luisyanza/passline/actions/workflows/ci.yml/badge.svg)](https://github.com/luisyanza/passline/actions/workflows/ci.yml)

**Multi-agent subtitle quality control and repair system for streaming delivery workflows**

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
Every line of source code, tests, and configuration is planned and written by
**IBM Bob** inside this repository.

- 📓 [Build Journal](docs/BUILD_JOURNAL.md) — mission-by-mission log of what was built
- 📐 [Foundation Plan](passline-foundation-plan.md) — the Mission 01 architecture plan

---

## Quickstart

**Requirements:** Python 3.12, the `.venv` virtual environment included in this repo.

```bash
# 1 — Activate the virtual environment
source .venv/bin/activate

# 2 — Install the package in editable mode
pip install -e .

# 3 — Run the test suite
python -m pytest

# 4 — Run the entry-point smoke-test (confirms both Google libraries initialise)
python -m passline
```

**Credentials (optional for the smoke-test):**
Copy `.env.example` to `.env` and fill in your Google Cloud project or Gemini API key.
The smoke-test runs without credentials; live agent calls require them.

---

## Project structure

```
passline/
├── agents/         Google ADK agents (QC, repair, …)
├── events/         Delivery event bus (JSONL log → Kafka)
├── io/             SRT parser and writer
└── models/         Subtitle cue and file data models
tests/
├── fixtures/       Golden SRT files for round-trip tests
└── test_*.py       Pytest test suite
docs/
└── BUILD_JOURNAL.md  Mission-by-mission build log
```

---

## License

MIT — see [LICENSE](LICENSE).
