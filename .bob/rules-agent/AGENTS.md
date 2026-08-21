# Project Coding Rules (Non-Obvious Only)

- No `pyproject.toml` / `requirements.txt` yet — when adding dependencies, install with `pip install <pkg>` AND create/update a `requirements.txt` or `pyproject.toml` so the install is reproducible.
- `google-adk` exposes both a CLI (`adk`) and a Python API under `google.adk.*`; prefer the Python API for agent logic, use the CLI only for serving.
- `pydantic` v2 is installed — do NOT use v1 patterns (`@validator`, `class Config`, `.dict()`). Use `model_validator(mode='after')`, `model_config`, `.model_dump()`.
- `tenacity` is available for retry logic; use it rather than writing manual retry loops.
- `aiosqlite` is installed for async SQLite — use it instead of synchronous `sqlite3` in async contexts.
- Tests use `pytest` 9.x; run a single test with `python -m pytest path/to/test.py::test_name` (must have venv active).
- The `.remember/` directory is a session-memory plugin artifact — do not store application data there.
