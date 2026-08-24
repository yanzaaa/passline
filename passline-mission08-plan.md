# Mission 08 — The Show: Implementation Plan

## Overview

Transform the working Passline subtitle QC product into a flawless live demonstration. Every item is a real product behavior, provable by automated tests, and verifiable end-to-end in a browser at the public URL with zero faking.

### Architecture constraints (carry-forward from AGENTS.md)
- Rule engine is pure deterministic Python — no LLM decides math
- All new event types are forward-only schema additions (bump to 1.3)
- `passline/qc/thresholds.py` remains the single threshold source of truth
- Classic ADK template agents (`SequentialAgent`, `ParallelAgent`, `LoopAgent`) remain in use
- No new AI providers; only `google-adk` + `google-genai`

### What the current state reveals
- `passline/corpus/demo/tos-{en,fr,de}.srt` are the **clean** source files — the demo chips currently send clean files through the pipeline, which produces no violations. This must be fixed.
- The demo chip row has a non-existent "JA-003" chip with no corresponding corpus file.
- `ReporterAgent` emits `QC_VIOLATION` (not a new event type) when verdict is `failed` — the honest-fail path needs its own `delivery.failed` event type.
- The `markCleared` handler unconditionally appends a download link for every `delivery.passed` event, including replayed ones.
- The BREAK THIS FILE button is an `alert()` placeholder.
- No TTS, no confidence chips, no style-guide citations, no REPLAY indicator exist yet.

---

## Sub-Task 1 — Demo recipe: "repairability-proven" corruption mode

**Status:** `[ ] pending`

### Intent

Add a `corrupt_demo` function to `passline/corpus/corrupt.py` that produces a short (~12-cue) excerpt with exactly the defect profile the demo requires: a small, guaranteed-repairable defect set with exactly one meaning-level swap, no adjacent or same-cue collisions, and enough temporal air between timing defects to allow safe retiming. The excerpt is a slice of the existing clean corpus, not a new source.

The key constraints that differ from the existing `corrupt_file`:
1. **One meaning-level swap only** (not up to two as in the current engine).
2. **No adjacent cue defects** — spacing rule: defected cues must be separated by at least one clean cue index.
3. **Bounded excerpt size** — slice the first N cues where N is configurable (default 14), so demo runs are fast.
4. **Timing defects guaranteed safe** — short_duration and overlap defects are only injected when there is ≥ 2000 ms of gap to the nearest neighbor, ensuring retiming cannot collide.
5. **Defect count bounded** — one CPS blowout, one line overflow, one short duration, one meaning swap = four defects total, guaranteed repairable within three passes.

The function signature:
```python
def corrupt_demo(
    source: SubtitleFile,
    seed: int,
    language: str = "und",
    excerpt_cues: int = 14,
) -> CorruptionResult:
```

### Expected Outcomes
- `corrupt_demo` is importable from `passline.corpus.corrupt`.
- Given the same `(source, seed, language)` inputs, it produces byte-identical outputs every time.
- The resulting broken file, when run through the pipeline with the meaning-level decision approved, produces verdict `"passed"` and zero remaining violations.
- The manifest records exactly the injected defects.

### Todo List
1. Add `corrupt_demo()` to `passline/corpus/corrupt.py` — slice first `excerpt_cues` cues, apply the adjacent-spacing guard, inject at most: one CPS blowout (skip if no safe candidate), one line overflow (skip if none), one short duration only if ≥ 2000 ms gap exists to neighbors, one meaning swap (exactly one, not two).
2. The adjacent-spacing guard: after reserving cue `i`, also pre-reserve `i-1` and `i+1` in `used_cue_indices` so no neighbor can be selected.
3. Use `seed=7` for English, `seed=11` for French, `seed=13` for German (values chosen to produce well-distributed defects on the first 14 cues of each language file — verify during implementation).
4. Write one unit test in `tests/test_corpus.py` confirming `corrupt_demo` is deterministic and produces ≥1 and ≤4 defects on the EN corpus.

### Relevant Context
- `passline/corpus/corrupt.py`: `corrupt_file()` at line 281. The new function reuses `_apply_cps_blowout`, `_apply_line_overflow`, `_apply_short_duration`, `_apply_overlap`, `_substitute_text` helpers.
- `passline/corpus/substitutions.py`: substitution tables for en/fr/de all exist.
- `passline/qc/thresholds.py`: `CPS_VIOLATION`, `LINE_CHAR_MAX`, `MIN_DURATION_MS`.
- Adjacent-spacing: the `reserve()` helper inside `corrupt_file` uses `used_cue_indices: set[int]`. The new function extends this by also calling `reserve(i-1)` and `reserve(i+1)` as sentinel reservations (but only if those indices exist — guard against index 0).

---

## Sub-Task 2 — Generate and bundle three demo-grade broken excerpt files

**Status:** `[ ] pending`

### Intent

Use `corrupt_demo` to produce `demo-en-broken.srt`, `demo-fr-broken.srt`, and `demo-de-broken.srt` and commit them into `passline/corpus/demo/`, alongside their manifests. These replace the current clean-source demo files as the targets for demo chip clicks. The current clean files stay in place (needed by `scripts/fetch_assets.py` and the test corpus).

A new script `scripts/generate_demo_corpus.py` produces the three files deterministically. It is committed but not run at container startup — the output files are committed golden data, identical to the test golden corpus pattern.

### Expected Outcomes
- `passline/corpus/demo/demo-en-broken.srt`, `demo-fr-broken.srt`, `demo-de-broken.srt` exist and are committed.
- `passline/corpus/demo/demo-en-manifest.json`, `demo-fr-manifest.json`, `demo-de-manifest.json` exist and are committed.
- Three repairability tests (one per language) in `tests/test_demo_repairability.py`:
  - Load the broken excerpt from its package path.
  - Stub `LanguageCheckerAgent._call_genai_with_retry` to return a single MT01 flag at the meaning-swapped cue, and set the meaning-level approval to auto-approved.
  - Run the full `PipelineRunner` with the auto-approval gate driver from `test_e2e_pipeline.py`.
  - Assert `report["verdict"] == "passed"`.
  - Assert re-parsed repaired SRT grades clean via `check_file()`.

### Todo List
1. Write `scripts/generate_demo_corpus.py`: for each (lang, seed), load `passline/corpus/demo/tos-{lang}.srt`, call `corrupt_demo`, write broken SRT and manifest JSON to `passline/corpus/demo/`.
2. Run the script once locally to produce the three broken files and three manifests.
3. Commit all six generated files.
4. Add them to `pyproject.toml` `[tool.setuptools.package-data]` under `passline.corpus`: `"demo/*.json"` alongside existing `*.srt` and `*.jsonl`.
5. Write `tests/test_demo_repairability.py` with the three parametrised tests as described.
6. Verify all three tests pass (`python -m pytest tests/test_demo_repairability.py`).

### Relevant Context
- `tests/test_e2e_pipeline.py` lines 79–105: pattern for stubbing the language checker and running the gate driver — reuse verbatim.
- `passline/pipeline/runner.py` `run_delivery()` and `get_repaired_bytes()`.
- `passline/qc/rules.py` `check_file()` — used for the re-grade assertion.

---

## Sub-Task 3 — Hopeless-case control file and fourth demo chip

**Status:** `[ ] pending`

### Intent

The current French demo file (`passline/corpus/demo/tos-fr.srt`) is the clean source. The **existing** `tests/corpus/broken/tos-fr-broken.srt` — which has 12 injected defects from the full `corrupt_file` — already has more violations than three repair passes can clear: cue-overlap pairs, multiple CPS blowouts, multiple line overflows, plus meaning swaps. This is the hopeless-case control. Rename/copy it to `passline/corpus/demo/hopeless-fr.srt` and label it clearly.

The hopeless case must end in the new honest-fail state (Item 7 / Sub-Task 7). The board must show it as a feature, not an error, with copy stating the system never fakes a green.

### Expected Outcomes
- `passline/corpus/demo/hopeless-fr.srt` exists with the over-corrupted French content.
- The dashboard demo chip row shows: English, French, German (the demo-grade excerpts), plus a clearly labeled "Hopeless Case" chip.
- Clicking "Hopeless Case" triggers the pipeline; the pipeline ends in `delivery.failed` honest-fail state (not `delivery.passed`).
- No CLEARED styling appears on that card.

### Todo List
1. Copy `tests/corpus/broken/tos-fr-broken.srt` to `passline/corpus/demo/hopeless-fr.srt`.
2. Add `hopeless-fr.srt` to `pyproject.toml` package-data.
3. Update `app.py` `_DEMO_FILES` to add `"hopeless": "hopeless-fr.srt"` and `"demo-en"`, `"demo-fr"`, `"demo-de"` pointing to the new broken excerpts.
4. Update the `triggerDemo` language-detection logic in `html.py` to derive language from the chip key (not just from the filename prefix), since `hopeless` maps to `fr-FR` for the pipeline.
5. Update the demo chip HTML row: remove JA-003, add English / French / German chips (wired to the demo-grade excerpts), add Hopeless Case chip.

### Relevant Context
- `passline/dashboard/app.py` lines 51–61: `_DEMO_DIR`, `_DEMO_FILES`, `/api/demo/{lang}` route.
- `passline/dashboard/html.py` lines 370–377: demo chip HTML.
- `passline/dashboard/html.py` lines 841–859: `triggerDemo()` JS function.

---

## Sub-Task 4 — Event schema: `delivery.failed` honest-fail event type

**Status:** `[ ] pending`

### Intent

Add a new `DELIVERY_FAILED = "delivery.failed"` event type to `EventType` enum in `passline/events/bus.py`. Bump schema version to `"1.3"`. Update `ReporterAgent` to emit `delivery.failed` (instead of re-using `qc.violation`) when verdict is `"failed"`. The `delivery.failed` event's details must carry:
- `remaining_violations: int`
- `per_rule_breakdown: dict[str, int]` — rule name → count
- `repaired_file_exists: bool`
- `verdict: "failed"`

Also add `DELIVERY_FAILED` to the `LOG_TYPES` and `HANDLERS` dispatch tables in the dashboard JS, and to `tests/test_events.py` schema assertions.

### Expected Outcomes
- `EventType.DELIVERY_FAILED` exists and serialises as `"delivery.failed"`.
- `ReporterAgent` emits `delivery.failed` on failed verdict with the per-rule breakdown.
- The event log schema version is `"1.3"` on all new events.
- `tests/test_events.py` passes with updated schema version assertions.
- The `delivery.passed` event gains an explicit `repaired_file_exists: True` field in details, so the download gating logic in the UI can trust it.

### Todo List
1. Add `DELIVERY_FAILED = "delivery.failed"` to `EventType` in `bus.py`.
2. Bump `schema_version` default in `DeliveryEvent` from `"1.2"` to `"1.3"`.
3. Update `ReporterAgent`: on failed verdict, build `per_rule_breakdown` dict from `all_findings` (group by `rule` key), emit `DeliveryEvent(event_type=EventType.DELIVERY_FAILED, ...)` with the required detail fields. Set `repaired_file_exists = len(repaired_bytes) > 0`.
4. On passed verdict, add `repaired_file_exists: True` to the `delivery.passed` details.
5. Update `tests/test_events.py`: change schema version assertions from `"1.2"` to `"1.3"`, add assertion for `DELIVERY_FAILED` value string.
6. Update dashboard `HANDLERS` and `LOG_TYPES` to handle `"delivery.failed"` events.

### Relevant Context
- `passline/events/bus.py` lines 29–45: `EventType` enum, line 57: schema_version default.
- `passline/agents/reporter_agent.py` lines 86–124: verdict branching logic.
- `tests/test_events.py`: schema version assertions that will need updating.
- `passline/dashboard/html.py` lines 550–559: HANDLERS dispatch table, lines 740–749: LOG_TYPES.

---

## Sub-Task 5 — Honest-fail card state in the dashboard

**Status:** `[ ] pending`

### Intent

When the dashboard receives a `delivery.failed` event, the delivery card must enter a visually distinct honest-fail state. Requirements:
- CSS class `failed` on the card (never `cleared`).
- Badge text: `HELD — N violations remain` in amber/red.
- A per-rule violation breakdown rendered in a small table inside the card.
- If `repaired_file_exists` is true in the event details, show a download link labeled `⬇ Download best-effort (not cleared)` in amber, clearly NOT the green cleared-file style.
- The `markCleared` function must only fire on `delivery.passed` events — it must never fire on `delivery.failed`.

A new function `markFailed(ev)` handles `delivery.failed` events.

### Expected Outcomes
- A `delivery.failed` event received via SSE produces a card with `HELD` badge, per-rule breakdown, and (if applicable) an amber download link.
- No green `CLEARED FOR DELIVERY` badge ever appears for a failed delivery.
- The honest-fail card is visually distinct from both HOLD (waiting for repair) and CLEARED.

### Todo List
1. Add CSS for `.delivery-card.failed` and `.badge-failed` in `html.py` (amber border, amber badge).
2. Add `markFailed(ev)` JS function: set card class to `failed`, badge to `HELD — N violations remain`, render per-rule breakdown as a small inline list, conditionally append an amber download link if `ev.details.repaired_file_exists`.
3. Register `'delivery.failed': (ev) => { markFailed(ev); addLog(ev, 'lifecycle'); updateHolds(); }` in `HANDLERS`.
4. Add `'delivery.failed': ['lifecycle', 'HELD      ']` to `LOG_TYPES`.
5. Update `buildLogDetail` for `delivery.failed`: show `remaining_violations` and the delivery_id.
6. Add a `startReset` cleanup for `failed`-status deliveries in the board-clear logic.

### Relevant Context
- `passline/dashboard/html.py` lines 652–674: `markCleared()` — model the new `markFailed()` on this.
- `passline/dashboard/html.py` lines 676–683: `updateHolds()` — failed cards should not count as HOLDs.
- CSS tokens: `--amber`, `--amber-dim`, `--red`, `--red-dim`.

---

## Sub-Task 6 — Download gating: replay cards must never show download links

**Status:** `[ ] pending`

### Intent

The current `markCleared()` unconditionally appends a download link to every card that receives a `delivery.passed` event, including replayed demo events. Replayed events are theater — the repaired bytes do not exist server-side for those deliveries — so the download link would return 404.

Fix: the `delivery.passed` event now carries `repaired_file_exists: bool` in its details (added in Sub-Task 4). The `markCleared()` function must only append the download link when `ev.details.repaired_file_exists === true`.

Replayed events from `replay.py` do not go through `ReporterAgent`, so they will not carry `repaired_file_exists` in their details. The UI trusts the absence of this field as `false`.

Additionally: replay-mode cards must carry a visual `REPLAY` label (Sub-Task 11 handles the REPLAY/LIVE indicator), but the download-gating fix is self-contained here.

### Expected Outcomes
- A `delivery.passed` event emitted by a real pipeline run (with `repaired_file_exists: True`) shows a green download link.
- A `delivery.passed` event from the canned replay (no `repaired_file_exists` field) shows no download link.
- `GET /api/download/{id}` is never reachable from a link rendered during normal operation except for real pipeline runs that cleared.

### Todo List
1. In `markCleared()` in `html.py`, change the download-link append to be conditional: `if (ev.details && ev.details.repaired_file_exists === true)`.
2. Verify `ReporterAgent` sets `repaired_file_exists: True` in `delivery.passed` details (done in Sub-Task 4).
3. Verify `demo_events.jsonl` (replay fixture) events do not carry `repaired_file_exists` — they do not, since they were recorded before this field existed. No change needed to the fixture.
4. Write a test in `tests/test_dashboard.py`: post a `delivery.passed` event without `repaired_file_exists` and assert the card HTML contains no download link. Post one with `repaired_file_exists: True` and assert the link appears.

### Relevant Context
- `passline/dashboard/html.py` lines 662–673: download link append in `markCleared()`.
- `passline/corpus/demo/demo_events.jsonl`: replay fixture events — none carry `repaired_file_exists`.
- `tests/test_dashboard.py`: SSE-triggered card rendering tests.

---

## Sub-Task 7 — Wire demo chips to the new broken excerpt files

**Status:** `[ ] pending`

### Intent

The demo chip row must show exactly four controls: English, French, German, and Hopeless Case. Each chip calls `triggerDemo(key, lang)` which fetches `/api/demo/{key}` and POSTs the bytes to `/api/upload`. The language sent to the pipeline must be the BCP-47 code for the language being processed, not derived from the chip key.

Update `app.py` to map the new keys to the new broken file names. Update the chip HTML labels and onclick handlers.

### Expected Outcomes
- Four chips render on the board: English, French, German, Hopeless Case.
- No Japanese chip is present.
- Clicking English fetches `demo-en-broken.srt` via `/api/demo/demo-en` and uploads it with `language=en-US`.
- Clicking French fetches `demo-fr-broken.srt` via `/api/demo/demo-fr` and uploads with `language=fr-FR`.
- Clicking German fetches `demo-de-broken.srt` via `/api/demo/demo-de` and uploads with `language=de-DE`.
- Clicking Hopeless Case fetches `hopeless-fr.srt` via `/api/demo/hopeless` and uploads with `language=fr-FR`.

### Todo List
1. Update `_DEMO_FILES` in `app.py` to add `"demo-en"`, `"demo-fr"`, `"demo-de"`, `"hopeless"` entries. Keep the existing `"en"`, `"fr"`, `"de"` entries for backward compatibility.
2. Update `triggerDemo(key, lang)` in `html.py` so the `lang` parameter is passed explicitly from the chip and used as-is for the upload (not re-derived from the key).
3. Replace the three chip HTML elements with four new ones: `triggerDemo('demo-en','en-US')` → English, `triggerDemo('demo-fr','fr-FR')` → French, `triggerDemo('demo-de','de-DE')` → German, `triggerDemo('hopeless','fr-FR')` → Hopeless Case (styled distinctively, e.g. amber border).
4. Label the Demo Files section header copy to reference the chips as "English / French / German / Hopeless Case".

### Relevant Context
- `passline/dashboard/app.py` lines 51–61: `_DEMO_FILES`, `/api/demo/{lang}` route at line 195.
- `passline/dashboard/html.py` lines 370–377: chip HTML, lines 841–859: `triggerDemo()`.
- The `/api/upload` handler derives language from the uploaded filename using a regex; the new `triggerDemo` must construct the filename as `tos-{lang_prefix}-demo.srt` to avoid that regex breaking.

---

## Sub-Task 8 — BREAK THIS FILE button (real implementation)

**Status:** `[ ] pending`

### Intent

Replace the `alert()` placeholder on the BREAK THIS FILE button with a real implementation. On click:
1. Find the most recently cleared delivery on the board (highest card with status `cleared`).
2. POST to a new `/api/break/{delivery_id}` endpoint.
3. Server-side: retrieve the repaired SRT bytes from `_repaired_store[delivery_id]`, run them through `corrupt_demo` with a fresh random seed (using `secrets.randbelow` or `random.randrange`) with the meaning-level swap omitted (`defects` excluding `meaning_swap`), and feed the corrupted bytes into a new pipeline run via `PipelineRunner`.
4. The new delivery must carry a `parent_id` in its `subtitle.submitted` details so the board can visually link it to its parent.
5. The break button is disabled (with a tooltip) while no cleared delivery exists.

The `/api/break/{delivery_id}` endpoint is non-blocking (same pattern as `/api/upload`): it starts the pipeline in a background task and returns `{"status": "accepted", "child_delivery_id": "..."}` immediately.

### Expected Outcomes
- Clicking the button on a cleared delivery starts a new pipeline run that produces violations and then repairs them without any user input (no meaning-level swap, so no approval gate).
- The new delivery card appears with a `parent:` label showing the parent delivery ID.
- The button is visually disabled with a tooltip when no cleared delivery exists.
- No file upload dialog, no alert, no page reload.

### Todo List
1. Add `POST /api/break/{delivery_id}` route to `app.py`: fetch repaired bytes from `_repaired_store`, parse the SRT, run `corrupt_demo` with `secrets.randbelow(10000)` as seed and without meaning_swap, start a new `PipelineRunner.run_delivery` call as a background task with a new delivery_id and `parent_id=delivery_id` in the `subtitle.submitted` details.
2. The new delivery's `subtitle.submitted` event must include `parent_id` in its details — update `PipelineRunner.run_delivery` to accept an optional `parent_id: str | None = None` and pass it through to the start event.
3. Update `addDeliveryCard()` in `html.py` to render a `parent:` line when `ev.details.parent_id` is set.
4. Update the break button: remove the `onclick="alert(...)"`, add `id="break-btn"`, add `onclick="triggerBreak()"`.
5. Add `triggerBreak()` JS: find the first card with class `cleared` in `#delivery-cards`, read its delivery_id from the element id, POST to `/api/break/{id}`, disable the button during the request.
6. Add JS logic to enable/disable the break button based on whether any card in `deliveries` has `status === 'cleared'` — update this check in `markCleared()` and `startReset()`.
7. Write a test in `tests/test_dashboard.py`: mock `PipelineRunner.run_delivery`, POST `/api/break/{id}` with a delivery_id that has repaired bytes in `_repaired_store`, assert a 200 response and a new accepted delivery_id.

### Relevant Context
- `passline/dashboard/app.py` lines 152–192: `/api/upload` pattern to copy.
- `passline/dashboard/html.py` line 394: BREAK THIS FILE button placeholder.
- `passline/corpus/corrupt.py`: `corrupt_demo()` added in Sub-Task 1.
- `passline/pipeline/runner.py`: `run_delivery()` signature.

---

## Sub-Task 9 — Confidence chips and style-guide citations

**Status:** `[ ] pending`

### Intent

Language flags already carry `confidence: float` and `rule_ref: str` (MT01–MT06). Surface them in the dashboard:
1. Every `qc.violation` event that carries a `rule_ref` starting with `MT` gets a compact confidence chip in the log line and on the card's flag detail.
2. Each flag is expandable to an inline panel showing: rule code, per-language style-guide citation, and the checker's explanation.
3. Citations come from a single server-side reference table in a new `passline/agents/style_guide.py` module, keyed by `(rule_ref, language_prefix)`. The UI fetches `/api/style-guide/{rule_ref}/{lang}` to get the citation text.

The rule table is server-side so log and card always agree.

### Expected Outcomes
- A `qc.violation` event with `rule_ref=MT01` and `confidence=0.87` renders a chip showing `MT01 · 87%` in the log and on the card.
- Clicking the chip expands a panel with: rule name, style-guide citation (e.g. "Timed-Text Style Guide (FR), section 3.1"), and the explanation field from the event.
- `GET /api/style-guide/MT01/fr` returns `{"rule_ref":"MT01","language":"fr","citation":"Timed-Text Style Guide (FR), section 3.1","rule_name":"Mistranslation"}`.
- No streaming platform names appear anywhere in citation text.

### Todo List
1. Create `passline/agents/style_guide.py` with a `STYLE_GUIDE_CITATIONS` dict keyed by `(rule_ref, lang_prefix)` for all six MT rules × three languages (en, fr, de), using invented neutral section numbers. Add a `get_citation(rule_ref, language)` function with fallback to `"en"`.
2. Add `GET /api/style-guide/{rule_ref}/{lang}` route to `app.py` that returns the citation as JSON.
3. Update `qc.violation` emission in `LanguageCheckerAgent` to include `confidence`, `rule_ref`, and `explanation` in the event details (they may already be there — verify). If not, add them.
4. In `html.py`, update `markViolation(ev)` and `addLog(ev, 'violation')` to detect MT-rule violations (check `ev.details.rule_ref`): render a confidence chip `<span class="conf-chip">MT01 · 87%</span>` and make it clickable to expand a details panel fetching from `/api/style-guide/{rule_ref}/{lang}`.
5. Add CSS for `.conf-chip` (small badge, blue tint) and `.flag-popover` (inline expand panel).

### Relevant Context
- `passline/agents/language_checker.py` lines 245–265: QC_VIOLATION emission in language checker — check if `rule_ref` and `confidence` are already in details.
- `passline/agents/schemas.py` lines 36–61: `LanguageFlag` fields (`confidence`, `rule_ref`, `explanation`).
- `passline/dashboard/html.py` lines 624–633: `markViolation()` — where to add chip rendering.

---

## Sub-Task 10 — Text-to-speech delivery briefing

**Status:** `[ ] pending`

### Intent

After a delivery reaches a final state (passed or failed), its card offers a ▶ Briefing play control. On first click, the server generates ~25 seconds of spoken audio in three voices using the Google Generative AI TTS API. The audio is cached per delivery. Subsequent clicks play the cached audio without generating again.

**Three-voice script structure:**
- Voice 1 (desk chief): "Delivery {id}, {language}. Result: {CLEARED / HELD}. {N} violations found, {M} repairs applied."
- Voice 2 (language specialist): describes the most notable language flag (highest confidence), or states "No language flags detected."
- Voice 3 (verifier): "Verifier sign-off: {N} remaining violations. Delivery is {authorized for release / held pending review}."

**API used:** `google.genai` `generate_content` with `speech_config` for named prebuilt voices. Three separate generation calls, results concatenated as WAV/PCM.

**Guards:**
- `PASSLINE_TTS_ENABLED` env var (default `"true"`); set to `"false"` to disable entirely.
- `PASSLINE_TTS_MAX_GENERATIONS` env var (default `"50"`); cap total per server process.
- Cache: `_briefing_cache: dict[str, bytes]` module-level in `app.py`.
- Lazy: generated only on first `GET /api/briefing/{delivery_id}`.
- Degrade gracefully: if generation fails, return 503 with `{"error": "unavailable"}`.

**Frontend:** the play control is added to the delivery card only when it reaches a final state (`markCleared` or `markFailed`). Clicking it fetches `/api/briefing/{delivery_id}` and plays the returned audio via `new Audio(url)` or a Blob URL.

### Expected Outcomes
- After a delivery clears or fails, the card shows a `▶ Briefing` button.
- Clicking it plays ~25 s of spoken audio in three distinct voices.
- A second click plays the cached audio without making a new generation call.
- Setting `PASSLINE_TTS_ENABLED=false` causes the button to not appear.
- A generation error causes the button to show "Briefing unavailable".

### Todo List
1. Create `passline/dashboard/briefing.py` with:
   - `BriefingGenerator` class holding the TTS config, generation count, and cache.
   - `generate_briefing(report, language_flags)` method: builds three-voice script, calls `google.genai` TTS three times with named voices (e.g. Puck, Charon, Kore), concatenates audio bytes, returns bytes. Raises `BriefingError` on failure or if disabled/capped.
   - `VOICES = ("Puck", "Charon", "Kore")` — three named prebuilt voices from the google-genai library.
2. Add `_briefing_cache: dict[str, bytes] = {}` and `_briefing_generator: BriefingGenerator` to `app.py`.
3. Wire the pipeline's delivery report and language findings to the briefing generator by storing `language_findings` in `_repaired_store` alongside bytes — or add a `_delivery_metadata` dict keyed by delivery_id.
4. Add `GET /api/briefing/{delivery_id}` route: look up cache, generate if needed, return `Response(content=audio_bytes, media_type="audio/wav")`.
5. In `html.py`, add a briefing play button to `markCleared()` and `markFailed()`: `<button class="briefing-btn" onclick="playBriefing('{id}')">▶ Briefing</button>`.
6. Add `playBriefing(id)` JS: fetch `/api/briefing/{id}`, on success create a blob URL and call `new Audio(url).play()`, on 503 mark button "Unavailable".
7. Write a test in `tests/test_dashboard.py` for briefing caching: mock the generator, call `/api/briefing/{id}` twice, assert the mock was called exactly once.

### Relevant Context
- `google.genai` TTS API: `client.models.generate_content(model="gemini-2.5-flash-preview-tts", config=types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")))))`.
- Store `language_findings` alongside repaired bytes: update `app.py`'s `_run_and_store` closure to also save the report's language_findings.
- `PASSLINE_TTS_ENABLED` and `PASSLINE_TTS_MAX_GENERATIONS` must be documented in `AGENTS.md` environment variable table.

---

## Sub-Task 11 — Human-wait visibility and approval card polish

**Status:** `[ ] pending`

### Intent

When the pipeline is waiting for a human decision, the delivery card must enter a visually distinct `waiting` state (animated amber pulse), and the approval card must draw the eye prominently. After a decision, the next pending item must surface within ~2 seconds.

The approval card already shows `item_id` from the `approval.required` event. The two-second surfacing is guaranteed by the ApprovalQueue's `emit_station_working` → `emit approval.required` sequence — verify the timing in the existing flow and confirm there is no artificial delay.

### Expected Outcomes
- A delivery card enters a `waiting` CSS state when it receives `approval.required` and exits it when `qc.repaired` follows.
- The approval card has a more prominent visual treatment: animated border, larger text, high contrast.
- After submitting a decision, the next `approval.required` event (if any) arrives within the SSE latency + asyncio task scheduling latency, typically < 1 second.

### Todo List
1. Add CSS `.delivery-card.waiting` — amber dashed border, pulsing amber glow.
2. Update `showApproval(ev)` in `html.py` to also call `setCardWaiting(ev.delivery_id)`.
3. Add `setCardWaiting(id)` JS: set card class to `waiting`, update badge to `AWAITING HUMAN`.
4. Update `markRepaired(ev)` to clear the `waiting` class when a repair event fires on the same delivery.
5. Update the approval card CSS: increase border width, add `animation: approvalPulse 1.5s ease infinite` border glow.
6. Confirm `ApprovalQueue.enqueue()` emits `APPROVAL_REQUIRED` synchronously on `bus.emit()` — it does (line 78 in approval.py). No artificial delay to fix.

### Relevant Context
- `passline/dashboard/html.py` lines 791–798: `showApproval()`.
- `passline/pipeline/approval.py` lines 65–97: `enqueue()` emits the event.
- CSS tokens: `--amber`, `--amber-dim`.

---

## Sub-Task 12 — LIVE vs REPLAY mode indicator

**Status:** `[ ] pending`

### Intent

Add a small REPLAY/LIVE mode indicator separate from the SSE status dot. While `start_replay()` is active, the board shows a `REPLAY` tag and every delivery card created during the replay carries a `REPLAY` label. When no replay is running and real pipeline activity is occurring, the board shows `LIVE`. These two states must never appear simultaneously.

Implementation: The server-side replay tracks its own active state. Expose `GET /api/replay/status` returning `{"active": bool}`. The client polls this every 5 seconds (not SSE) to update the mode indicator. Alternatively, the `POST /api/replay` response can include a `mode: "replay"` field and `POST /api/stop` / `POST /api/reset` responses include `mode: "live"` — the client updates on response.

Cards created during replay: the `addDeliveryCard()` function can detect replay mode by checking a JS module-level `isReplayMode` flag.

### Expected Outcomes
- While replay is playing, a `REPLAY` tag appears in the topbar.
- During real pipeline runs, a `LIVE` indicator appears instead.
- Each card created during replay shows a `REPLAY` chip inside the card header.
- After clicking stop/reset, the board returns to `LIVE` mode.
- Cards created before the mode switch do not change their label retroactively.

### Todo List
1. Add `isReplayMode` boolean JS state variable in `html.py`.
2. Update `startReplay()` JS: set `isReplayMode = true`, update mode indicator.
3. Update `stopReplay()` and `startReset()` JS: set `isReplayMode = false`, update mode indicator.
4. Add `updateModeIndicator()` JS function: toggle a `#mode-indicator` element between `REPLAY` (amber) and `LIVE` (green).
5. Add the `#mode-indicator` element to the topbar HTML, adjacent to the SSE dot.
6. Update `addDeliveryCard()`: if `isReplayMode`, append a small `REPLAY` chip to the card header.
7. Add CSS for `.replay-chip` (small amber badge) and `#mode-indicator` states.

### Relevant Context
- `passline/dashboard/html.py` lines 45–81: topbar HTML.
- `passline/dashboard/html.py` lines 817–838: `startReplay()`, `stopReplay()`, `startReset()` JS functions.
- `passline/dashboard/html.py` lines 602–618: `addDeliveryCard()` — where to inject the REPLAY chip.

---

## Sub-Task 13 — True clean-slate reset

**Status:** `[ ] pending`

### Intent

The current `startReset()` clears delivery cards, log, and holds count. It misses: station job counters, station lamps, reading-speed chart, before/after panel, approval card, drop-zone caption, delivery-window countdown, and `isReplayMode` flag. A cold-visitor must be able to click reset and have every UI element return to exact initial state.

### Expected Outcomes
- Clicking reset resets: delivery cards, log, holds pill, all six station job counters, all six station lamps, heat strip, before/after panel, approval card, drop-zone caption, countdown to 14400, `isReplayMode` to false, `deliveries` dict, `holdsCount`, `stationCounters`, `progressTimers`.
- The `seen` dedup set is cleared so backfill on the next reconnect starts fresh.
- The LIVE indicator replaces REPLAY.
- The next run after reset counts from zero.

### Todo List
1. Expand `startReset()` in `html.py` to also:
   - Reset all `cnt-{id}` station counter spans to `0`.
   - Reset all lamp elements to `lamp-ready` and station tiles to base class.
   - Clear `#heat-strip` innerHTML and `#heat-cue-count` to `0 cues`.
   - Reset `#diff-before` and `#diff-after` to `—`.
   - Reset approval card: remove `active` class, reset sub text.
   - Reset drop-zone label to `Drop subtitle file here`.
   - Reset `countdownS` to `14400`.
   - Clear `deliveries`, `holdsCount = 0`, `stationCounters = {}`, `progressTimers = {}`.
   - Set `isReplayMode = false`, call `updateModeIndicator()`.
2. Ensure `Object.keys(stationCounters).forEach(...)` covers all six stations.
3. No server-side state change needed beyond the existing `POST /api/reset` (truncates log, stops replay).

### Relevant Context
- `passline/dashboard/html.py` lines 826–833: current `startReset()` body.
- `passline/dashboard/html.py` lines 686–706: `setLamp()` and `stationCounters`.
- Element IDs: `cnt-timing`, `cnt-format`, `cnt-language`, `cnt-fixer`, `cnt-verifier`, `cnt-vendor_health`, `lamp-timing`, etc., `heat-strip`, `heat-cue-count`, `diff-before`, `diff-after`, `approval-card`, `approval-sub`, `.dropzone-label`.

---

## Sub-Task 14 — Required automated tests (Items 14 and 2)

**Status:** `[ ] pending`

### Intent

Write all behavior tests not covered by existing sub-tasks. Tests from Sub-Tasks 1, 2, 6, 8, 10 are written in those sub-tasks. This sub-task adds the remaining tests:

1. **Break-action test**: POST `/api/break/{delivery_id}` creates a new delivery linked to its parent.
2. **Download gating test**: replay cards expose no download data; a 404 is only reachable by manually typing a URL.
3. **Honest-fail event test**: `delivery.failed` event is emitted correctly by `ReporterAgent` on failed verdict, with per-rule breakdown.
4. **Briefing caching test**: second play request performs no second generation call.

### Expected Outcomes
- `python -m pytest` passes with 214+ passing, 3 skipped (same baseline skips).
- No new skips introduced.
- Each new test uses the same patterns as existing tests (tmp_bus, offline pipeline, mock LLM).

### Todo List
1. In `tests/test_dashboard.py`:
   - `test_break_creates_linked_delivery`: add repaired bytes to `_repaired_store`, POST `/api/break/{id}`, assert 200 and response contains `child_delivery_id`.
   - `test_download_gating_replay_no_link`: inject a `delivery.passed` event without `repaired_file_exists`, render via SSE, assert no download link in card HTML (requires ASGI test client inspection or checking the JS logic via server-side state).
   - `test_briefing_caching`: mock `BriefingGenerator.generate_briefing`, call `/api/briefing/{id}` twice, assert mock called once.
2. In `tests/test_pipeline.py` or a new `tests/test_reporter.py`:
   - `test_reporter_emits_delivery_failed`: build a session state with `all_findings = [{"rule":"line_too_long",...}]`, run `ReporterAgent`, collect emitted events, assert one event with `event_type == "delivery.failed"` and `details["per_rule_breakdown"] == {"line_too_long": 1}`.
3. In `tests/test_demo_repairability.py` (created in Sub-Task 2): three language repairability tests.

### Relevant Context
- `tests/test_e2e_pipeline.py` lines 79–105: gate driver pattern to reuse.
- `tests/test_pipeline.py` lines 87–100: `_run_agent_with_state()` helper pattern.
- `tests/test_dashboard.py` lines 38–71: `fresh_app` and `client` fixtures.

---

## Sub-Task 15 — README and build journal update

**Status:** `[ ] pending`

### Intent

Update `README.md` and `docs/BUILD_JOURNAL.md` to document all new behaviors from this mission.

### Expected Outcomes
- README describes: three-language demo cast, hopeless-case showcase, BREAK THIS FILE, delivery briefing voices, confidence chips, style-guide citations, LIVE/REPLAY indicator.
- `docs/BUILD_JOURNAL.md` has a dated Mission 07 entry in the same format as earlier missions, listing all deliverables.

### Todo List
1. Add a Mission 07 section to `docs/BUILD_JOURNAL.md` with date `August 23, 2026`, deliverables table, result line (test count), and plan reference.
2. Update `README.md` Feature Overview section to list the new capabilities.
3. Add `PASSLINE_TTS_ENABLED` and `PASSLINE_TTS_MAX_GENERATIONS` to the environment variable table in `AGENTS.md`.

### Relevant Context
- `docs/BUILD_JOURNAL.md` Mission 01–06 entries for formatting reference.
- `README.md` Feature Overview section.
- `AGENTS.md` environment variable table.

---

## Implementation Order and Dependencies

```
Sub-Task 1  (corrupt_demo)
    ↓
Sub-Task 2  (demo broken files + repairability tests)
    ↓
Sub-Task 3  (hopeless case file)
    ↓
Sub-Task 4  (delivery.failed event schema)
    ↓
Sub-Task 5  (honest-fail card state)
Sub-Task 6  (download gating)          ← depends on Sub-Task 4
Sub-Task 7  (wire demo chips)          ← depends on Sub-Tasks 2 and 3
Sub-Task 8  (BREAK THIS FILE)          ← depends on Sub-Tasks 1 and 7
Sub-Task 9  (confidence chips)
Sub-Task 10 (TTS briefing)             ← depends on Sub-Task 4/5
Sub-Task 11 (human-wait visibility)
Sub-Task 12 (LIVE/REPLAY indicator)
Sub-Task 13 (clean-slate reset)        ← depends on Sub-Task 12
Sub-Task 14 (remaining tests)          ← depends on all above
Sub-Task 15 (README/journal)           ← last
```

Sub-Tasks 5, 6, 7, 9, 11, 12 can proceed in parallel after their prerequisites complete.

---

## Acceptance Checklist

After all sub-tasks complete, the following must all be true:

- [ ] `python -m pytest` passes with zero new failures
- [ ] `grep -rn 'tests/' passline/ --include="*.py"` returns zero matches
- [ ] `grep -rn 'alert(' passline/dashboard/html.py` returns zero matches
- [ ] `grep -rn 'JA-003\|ja-JP\|ja_JP' passline/` returns zero matches
- [ ] Four demo chips visible in browser, no Japanese chip
- [ ] Clicking French demo chip: pipeline runs end-to-end under 90 seconds, CLEARED appears, download link appears
- [ ] Clicking Hopeless Case chip: HELD badge with per-rule breakdown, no CLEARED styling, no dead links
- [ ] BREAK THIS FILE works on a cleared delivery: new linked card appears, repairs without user input
- [ ] Confidence chip (MT01 · 87%) and style-guide citation visible on language flags
- [ ] Briefing plays ~25 seconds in three distinct voices
- [ ] REPLAY tag visible during replay; LIVE tag visible during real runs
- [ ] Reset restores complete clean slate
