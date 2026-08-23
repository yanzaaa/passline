# Demo Assets Relocation Plan

## Overview

The Cloud Run container crashes on demo playback because one runtime asset lives in the `tests/` directory, which `.gcloudignore` explicitly excludes from deployment.

**Single root cause:** `passline/dashboard/replay.py` reads `tests/fixtures/demo_events.jsonl` at module-level import time and again at each `/api/replay` invocation. That file is absent in the deployed image.

**Secondary concern:** `passline/corpus/demo/*.srt` (served by `/api/demo/{lang}`) lives inside the package and is correctly included — but it is not declared in `package_data`, so it may be silently omitted when the package is installed as a wheel rather than copied as source.

### Scope

| Asset | Current location | Problem |
|---|---|---|
| `demo_events.jsonl` | `tests/fixtures/` | Excluded from container — crashes `/api/replay` |
| `tos-{en,fr,de}.srt` (demo) | `passline/corpus/demo/` | Path resolution is correct but file is not declared in `package_data` |

All other runtime reads are safe (event log via env var to `/tmp/`, demo SRT reads from `passline/corpus/demo/`).

### Non-goals

- Do not modify `.gcloudignore`.
- Do not move test-only fixtures (`tests/fixtures/sample*.srt`, `tests/corpus/`).
- Do not change the pipeline, agents, or any non-dashboard logic.

---

## Sub-Task 1 — Move `demo_events.jsonl` into the package

**Status:** `[ ] pending`

### Intent

The demo replay fixture must live inside the deployed package, not under `tests/`. Moving it to `passline/corpus/demo/` groups it with the existing demo SRT assets, keeps the semantic structure clear ("all demo assets live in `passline/corpus/demo/`"), and avoids introducing a new directory.

### Expected Outcomes

- `tests/fixtures/demo_events.jsonl` is deleted (or left only as a symlink/alias if needed, but deletion is preferred).
- `passline/corpus/demo/demo_events.jsonl` exists and contains the original content.
- `passline/dashboard/replay.py` resolves `_FIXTURE` using `Path(__file__).parent` traversal that targets `passline/corpus/demo/demo_events.jsonl` — never `tests/`.
- The path works identically in: a local `python -m passline` run, a `pip install -e .` development install, and a Cloud Run container.

### Todo List

1. Copy `tests/fixtures/demo_events.jsonl` → `passline/corpus/demo/demo_events.jsonl`.
2. In `passline/dashboard/replay.py`, update `_FIXTURE` to use `Path(__file__).parent.parent / "corpus" / "demo" / "demo_events.jsonl"`.
3. Delete `tests/fixtures/demo_events.jsonl` (the file is no longer test-only).

### Relevant Context

- `passline/dashboard/replay.py` line 27: `_FIXTURE = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "demo_events.jsonl"`
- `Path(__file__).parent` inside `passline/dashboard/replay.py` resolves to `passline/dashboard/`
- `passline/dashboard/app.py` line 51: already uses `Path(__file__).parent.parent / "corpus" / "demo"` — the new fixture path should follow the identical pattern.

---

## Sub-Task 2 — Declare demo assets in `package_data`

**Status:** `[ ] pending`

### Intent

`pyproject.toml` has no `package_data` directive. Setuptools auto-discovery includes Python modules but does not guarantee `.jsonl` or `.srt` files are bundled in a wheel. Explicitly declaring the `passline/corpus/demo/` directory ensures these assets are present whether the package is installed from source, as an editable install, or as a built wheel inside a container.

### Expected Outcomes

- `pyproject.toml` includes a `[tool.setuptools.package-data]` section that declares `passline/corpus/demo/` assets (`*.srt`, `*.jsonl`).
- Running `pip install -e .` in a fresh virtual environment still includes the demo files.
- The `passline/corpus/demo/` directory contains an `__init__.py`-free layout (data directory, not a Python package — this is correct; `package_data` covers non-Python files in package directories).

### Todo List

1. Add to `pyproject.toml`:
   ```toml
   [tool.setuptools.package-data]
   "passline.corpus" = ["demo/*.srt", "demo/*.jsonl"]
   ```
2. Confirm `passline/corpus/demo/` is under a directory that setuptools recognises as part of the `passline` package tree (it already is, since `include = ["passline*"]`).

### Relevant Context

- `pyproject.toml` `[tool.setuptools.packages.find]` section uses `include = ["passline*"]`.
- No existing `package_data` directive exists — this is a pure addition.
- `passline/corpus/` already contains `__init__.py` (verified: it is a Python package namespace).

---

## Sub-Task 3 — Update test references

**Status:** `[ ] pending`

### Intent

Any test that previously referenced `tests/fixtures/demo_events.jsonl` must be updated to reference the new canonical location at `passline/corpus/demo/demo_events.jsonl`. No file must be duplicated; tests must import the single copy inside the package.

### Expected Outcomes

- `grep -r "demo_events.jsonl" tests/` returns zero results.
- All test assertions about fixture content remain valid (content is unchanged; only the path changes).
- `python -m pytest` passes with zero failures, zero new errors.

### Todo List

1. Search the entire `tests/` directory tree for any reference to `demo_events.jsonl` or `tests/fixtures/demo_events`.
2. For each reference found, update the path to resolve via `Path(__file__).parent.parent / "passline" / "corpus" / "demo" / "demo_events.jsonl"` or import using `importlib.resources` pointing at `passline.corpus.demo`.
3. If a test patches `passline.dashboard.replay._FIXTURE`, update the patch target to point at the new path (no change to patch mechanics needed — just the path value if it is asserted).

### Relevant Context

- Tests that test the replay route in `tests/test_dashboard.py` may mock or reference the fixture path.
- `grep -r "demo_events" tests/` will reveal every affected test file.
- Test files must not import from `tests/` — they should import from the package or use relative-to-repo-root paths for fixture discovery.

---

## Sub-Task 4 — Verify full deployment correctness

**Status:** `[ ] pending`

### Intent

After the asset move and packaging fix, perform a final verification pass: confirm that no non-test code reads a file from any `.gcloudignore`-excluded directory, and that the full test suite is green.

### Expected Outcomes

- `grep -rn "tests/" passline/` returns zero file-read call-sites (path constructions targeting `tests/`).
- `python -m pytest` exits 0 with the same pass count as before (214 passing, 3 skipped).
- No new warnings, deprecation notices, or import errors.

### Todo List

1. Run `grep -rn '"tests/' passline/` and `grep -rn "'tests/" passline/` and confirm zero matches that involve file I/O.
2. Run the full test suite: `python -m pytest`.
3. If any test failures appear, trace them to the asset relocation (not to unrelated changes) and fix path references only.
4. Verify `passline/corpus/demo/` now contains `demo_events.jsonl` alongside the three SRT files.

### Relevant Context

- `.gcloudignore` excludes: `tests/`, `docs/`, `scripts/`, `.venv/`, `*.egg-info/`, `__pycache__/`, build artifacts.
- The only identified violation was `passline/dashboard/replay.py` line 27.
- `scripts/` references to `tests/corpus/` are development-only tools (also excluded from deployment) — they are not a problem and must not be changed.
