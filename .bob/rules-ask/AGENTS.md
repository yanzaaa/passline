# Project Documentation Rules (Non-Obvious Only)

- **`passline/qc/thresholds.py`** is the canonical reference for all numeric QC limits — not inline comments in rules.py or corrupt.py.
- **Corpus manifests** in `tests/corpus/manifests/` have a `category` field: `"DETERMINISTIC"` (detectable by rule engine) vs `"MEANING_LEVEL"` (LLM-only). The rule engine is only graded against DETERMINISTIC entries.
- **Blender ToS corpus** in `tests/corpus/clean/` already has pre-existing violations (EN: max CPS 43.0, DE: max line 63 chars). This is expected — the grading test ignores non-manifest cues.
- **Two subtitle SRT systems**: `tests/fixtures/` holds golden parse/round-trip fixtures (marked binary); `tests/corpus/` holds Blender open-movie files for QC grading.
- **`passline_events.jsonl`** is a runtime output file, gitignored. Appears at repo root when tests or dashboard emit events.
- **Build Journal**: `docs/BUILD_JOURNAL.md` — mission-by-mission log. Update after each completed mission.
- **Plan files** (`passline-mission0N-plan.md`) live at the repo root — authored before implementation, kept for reference.
- **`passline.egg-info/`** is gitignored (`*.egg-info/` pattern).
- **ADK deprecation warnings** for `SequentialAgent`, `ParallelAgent`, `LoopAgent` are expected. These classes still work in ADK 2.7.1; the graph workflow API cannot yet be used as an LlmAgent sub-agent.
- **`passline/agents/schemas.py`** contains `QcAssessment`, `LanguageFlag`, `LanguageCheckerOutput` — the three Pydantic output schemas. The language checker's `output_schema` is enforced by ADK at runtime.
- **`passline/pipeline/approval.py`** contains the `ApprovalQueue` singleton and `ApprovalItem` dataclass. The module-level `approval_queue` singleton is imported by `app.py`.
- Blender corpus license: CC-BY 3.0 — attribution in `tests/corpus/README.md`.
