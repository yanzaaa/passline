# AGENTS.md

This file provides guidance to agents when working with code in this repository. 

> Passline is a multi-agent subtitle QC and repair system for streaming delivery workflows, built on Google's Agent Development Kit with Gemini on Vertex AI. Core principle: the rule engine is pure deterministic Python — no LLM ever decides math. LLMs are used only for language-level judgment. Everything is verified with golden-file tests. USE FULL CAPABILITIES AND MAKE THIS AS GOOD AS IT CAN BE.
>

## Project

**passline** — a Python 3.12 AI agent application built with Google ADK (Agent Development Kit) v2.7.1, FastAPI, and Pydantic v2. No source files exist yet; the venv is pre-populated.

## Environment

- Python 3.12.5 via `.venv/` (managed with `python3 -m venv`)
- Always activate the venv before running anything: `source .venv/bin/activate`
- Secrets go in `.env` (gitignored); loaded via `python-dotenv`

## Commands

```bash
# Run the ADK dev server (once an agent entry point exists)
adk web

# Run the ADK CLI
adk run <agent_module>

# Run all tests
python -m pytest

# Run a single test file
python -m pytest path/to/test_file.py

# Run a single test by name
python -m pytest path/to/test_file.py::test_function_name
```

No `pyproject.toml`, `setup.py`, or `requirements.txt` exist yet — dependencies are only in the venv. Add one before shipping.

## Stack (installed packages)

| Package                     | Version      | Purpose                        |
| --------------------------- | ------------ | ------------------------------ |
| `google-adk`              | 2.7.1        | Agent framework (Google ADK)   |
| `fastapi` / `uvicorn`   | 0.141 / 0.52 | HTTP server for the ADK web UI |
| `pydantic`                | 2.x          | Data validation / models       |
| `google-genai`            | 2.19         | Gemini model client            |
| `aiosqlite` / `aiohttp` | —           | Async DB and HTTP I/O          |
| `tenacity`                | 9.x          | Retry logic                    |
| `pytest`                  | 9.x          | Test runner                    |

## Code Style

- Use **Pydantic v2** models (`BaseModel`, `model_validator`, `field_validator`) — not v1 style (`@validator`).
- Async-first: prefer `async def` handlers in FastAPI routes and ADK agent callbacks.
- Type-annotate all function signatures; use `from __future__ import annotations` for forward refs.
- `.env` variables must be accessed through a settings model or `os.getenv`, never hardcoded.
