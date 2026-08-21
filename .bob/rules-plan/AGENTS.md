# Project Architecture Rules (Non-Obvious Only)

- **Deterministic rule engine is pure Python** — no LLM ever decides math. The ADK agent layer (language judgment) is architecturally separate from the rule engine layer.
- **`passline/qc/thresholds.py` is a hard dependency contract** between `rules.py` (rule engine), `corrupt.py` (corpus generator), and `fixer_agent.py` (deterministic repairs). Any threshold change must be considered for all three simultaneously.
- **Corruption engine only targets clean cues** — ensures every injected defect is unambiguous for grading. If thresholds change, corpus must be regenerated.
- **Corpus is committed golden data** (`seed=42`). To change corpus: update `generate_corpus.py` + re-run + commit all three broken SRTs + three manifests atomically.
- **Event bus is append-only JSONL** — `passline_events.jsonl` accumulates across runs. Tests use `tmp_path` fixtures for isolated event logs.
- **CI has two separate jobs**: `test` (required, every push) and `corpus-report` (PR-only, `continue-on-error: true`). Corpus reporting must never block CI.
- **Google ADK is the only permitted agent framework** — no other AI providers.
- **Schema versioning** is forward-only: `1.0` → `1.1` → `1.2`. If a new field is added, bump schema version and update all `test_events.py` assertions.
- **Classic template workflow agents are required**: The spec requires `SequentialAgent`, `ParallelAgent`, `LoopAgent` by name. ADK 2.7.1 deprecates them in favour of the graph workflow API but they still work. The deprecation is intentional.
- **Fixer agent deterministic repairs never call LLM**: Only language-level findings (MT01–MT06) go to the LLM. All timing/format fixes are pure Python math applied inline.
- **Approval queue gates are per-item**: The repair loop enqueues ALL meaning-change edits before suspending. Each item has its own `asyncio.Event` gate. The loop waits for ALL gates to resolve before continuing to the verifier.
- **`install_retry_on_model` wraps `generate_content_async` on the Gemini model object**. Must be called after agent construction. Uses `object.__setattr__` to bypass Pydantic frozen model restriction.
- **`PipelineRunner` creates one session per delivery** via `InMemorySessionService`. Session state is not shared between deliveries.
- **`LanguageCheckerAgent` reads `lang_check_input` from session state** (injected by the pipeline) — it does not receive the subtitle bytes directly. The ingest stage must write `subtitle_file` to state first.
