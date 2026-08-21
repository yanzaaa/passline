# Passline Mission 02 — Hardening Plan

## Overview

Harden and clean up the Mission 01 foundation across eight requirement areas.
No new pipeline stages are added; every change improves correctness, observability,
configurability, or developer hygiene of existing code.

All 38 existing tests must continue to pass. New tests are added alongside.

---

## Sub-Task 1 — Build Journal, README, AGENTS.md, .gitignore

**Intent:**
Create `docs/BUILD_JOURNAL.md`, update `README.md`, refresh `AGENTS.md`, and fix
`.gitignore` to permanently exclude build artifacts and cache directories from
version control. Untrack the already-committed `passline.egg-info/` directory.

**Expected Outcomes:**
- `docs/BUILD_JOURNAL.md` exists with Mission 01 entry (date, deliverables, 38 tests,
  plan pointer, verification commands). Format uses a per-mission heading so future
  entries append cleanly.
- `README.md` at repo root: project summary, IBM Bob / hackathon attribution,
  links to journal and foundation plan, quickstart (venv, install, test, run),
  core design principle, MIT license notice.
- `AGENTS.md` no longer claims `pyproject.toml` does not exist; reflects current
  project state (package exists, `pip install -e .` works, model env var).
- `.gitignore` gains: `*.egg-info/`, `build/`, `dist/`, `.pytest_cache/`, `*.pyo`
- `passline.egg-info/` is untracked from git index (`git rm -r --cached`) while
  remaining on disk for the editable install.

**Todo List:**
1. Create `docs/BUILD_JOURNAL.md` with "Built with IBM Bob" header and Mission 01 entry
2. Create `README.md` with all required sections
3. Update `AGENTS.md`: remove stale "no pyproject.toml" line, add model env var note,
   add note about `SRT_FORMAT_DIALECT` (from Sub-Task 4), remove "no source files" claim
4. Update `.gitignore` to add build artifact patterns
5. Run `git rm -r --cached passline.egg-info/` to untrack the directory

**Status:** [ ] pending

---

## Sub-Task 2 — Model Currency (env-var configurable model id)

**Intent:**
Make the QC agent model id configurable via environment variable `PASSLINE_QC_MODEL`
with default `gemini-2.5-flash` (safe fallback). Supported values include
`gemini-3-flash-preview` and `gemini-3.1-pro-preview`. The startup banner must print
the effective model id so operators can confirm which model is active.

**Expected Outcomes:**
- `qc_agent.py`: `build_qc_agent()` reads `PASSLINE_QC_MODEL` from environment
  (via `os.getenv`), falls back to `"gemini-2.5-flash"`. The model id is printed
  in the `__main__` startup banner.
- `__main__.py`: startup line shows `model={qc_agent.model!r}` (already does, no change needed)
- `PASSLINE_QC_MODEL` documented in AGENTS.md (covered in Sub-Task 1)

**Design note:** `build_qc_agent()` is called after `load_dotenv()` in `__main__.py`,
so the env var from `.env` files is available at construction time.

**Todo List:**
1. In `passline/agents/qc_agent.py`, replace hardcoded `"gemini-2.0-flash"` with
   `os.getenv("PASSLINE_QC_MODEL", "gemini-2.5-flash")`
2. Confirm `__main__.py` already prints `qc_agent.model` in the banner (it does)
3. Add one test in a new `tests/test_agents.py` that patches the env var and asserts
   the agent gets the patched model id

**Status:** [ ] pending

---

## Sub-Task 3 — SRT Metadata as Dialect Object (remove `_meta_cache`)

**Intent:**
Replace the global `_meta_cache: dict[int, _SrtMeta]` with a first-class `SrtDialect`
dataclass stored as a field on `SubtitleFile`. This makes formatting fidelity travel
with the object, survive copies, work safely in long-running server processes, and
eliminate the identity-keyed cache that can attach metadata to the wrong object.

**Design:**
- New frozen dataclass `SrtDialect(has_bom, crlf, trailing_blank)` in `passline/io/srt.py`
  (or a shared `passline/models/srt_dialect.py` — keep in `srt.py` to avoid extra module).
- `SubtitleFile` gains a new optional field: `srt_dialect: SrtDialect | None = None`.
  Since `SubtitleFile` is frozen, this field is set at construction time by `parse_srt`.
- `write_srt` reads `subtitle_file.srt_dialect` instead of the cache. Falls back to a
  default `SrtDialect()` (LF, no BOM, trailing blank = False) for programmatically
  constructed files.
- `_meta_cache` and all references to it are deleted.

**Pydantic v2 note:** `SrtDialect` must be usable as a Pydantic field. Use a Pydantic
`BaseModel` with `frozen=True`, or a standard `dataclass` — either works as a Pydantic
field type. Using a Pydantic `BaseModel` is cleaner.

**Todo List:**
1. Add `SrtDialect(BaseModel, frozen=True)` with fields `has_bom: bool = False`,
   `crlf: bool = False`, `trailing_blank: bool = False` at the top of `srt.py`
2. Add `srt_dialect: SrtDialect | None = None` to `SubtitleFile` in `subtitle.py`
3. In `parse_srt`, replace `_meta_cache[id(subtitle_file)] = meta` with passing
   `srt_dialect=SrtDialect(...)` to the `SubtitleFile` constructor
4. In `write_srt`, replace `_meta_cache.get(id(...), _SrtMeta())` with
   `subtitle_file.srt_dialect or SrtDialect()`
5. Delete `_meta_cache` dict and `_SrtMeta` dataclass
6. Add test: parse a CRLF+BOM file, use `model_copy(update={"cues": modified_cues})`
   to produce a modified copy, verify `write_srt` on the copy still produces CRLF+BOM bytes

**Relevant Context:**
- All three existing round-trip tests (`test_round_trip_lf`, `test_round_trip_crlf`,
  `test_round_trip_bom`) must continue to pass unchanged.
- `SubtitleFile` is imported in `srt.py` — adding `srt_dialect` field means `srt.py`
  now imports `SrtDialect` but `subtitle.py` also needs to import `SrtDialect`.
  To avoid circular imports: put `SrtDialect` in `subtitle.py` alongside `SubtitleFile`,
  then import it in `srt.py`.

**Status:** [ ] pending

---

## Sub-Task 4 — Round-Trip Honesty (anomaly detection + surfacing)

**Intent:**
"Input we cannot reproduce byte-identically" is a first-class detected condition.
After parsing, verify re-serialising reproduces the original bytes. When it does not,
record the discrepancy on the parse result and include anomaly counts in the
`subtitle.submitted` event details. Every skipped or normalised block is observable.

**Design:**

Add three fields to `SubtitleFile`:
- `is_canonical: bool = True` — False if `write_srt(file) != original_bytes`
- `skipped_blocks: int = 0` — count of blocks that were skipped during parsing
- `parse_anomalies: list[str] = []` — human-readable list of anomaly descriptions

Conditions that set `is_canonical = False` and populate `parse_anomalies`:
1. A block had a non-integer index line (skipped)
2. A block had an invalid timecode line (skipped)
3. A block had fewer than 3 lines (skipped)
4. Extra blank lines between cues (3+ consecutive newlines → normalised to 2)
5. Non-canonical timecode format (e.g. single-digit hours `1:00:00,000` → written
   back as `01:00:00,000`)
6. Extra spaces around `-->` (normalised by the regex to single spaces)
7. Mixed CRLF/LF in the same file (detected; write-back uses the majority ending)
8. Trailing content after timecode on the timecode line (currently silently ignored)

The byte-identical verification happens after the initial serialisation attempt:
```
post_check = write_srt(subtitle_file)
if post_check != original_bytes_sans_bom_normalised:
    subtitle_file = subtitle_file.model_copy(update={"is_canonical": False, ...})
```

**New golden fixtures needed:**
- `tests/fixtures/sample_bad_timecode.srt` — one valid cue + one block with garbage timecode
- `tests/fixtures/sample_single_digit_hours.srt` — timecode `1:00:00,000 --> 1:00:03,500`
- `tests/fixtures/sample_arrow_spaces.srt` — timecode `00:00:01,000  -->  00:00:03,500`
- `tests/fixtures/sample_triple_blank.srt` — three blank lines between cues
- `tests/fixtures/sample_mixed_endings.srt` — some CRLF, some LF lines in same file

**New tests in `tests/test_srt.py`:**
- `test_bad_timecode_block_skipped` — `skipped_blocks == 1`, `is_canonical == False`
- `test_single_digit_hours_normalised` — `is_canonical == False`, anomaly message present
- `test_arrow_extra_spaces_normalised` — `is_canonical == False`, anomaly present
- `test_triple_blank_normalised` — `is_canonical == False`, anomaly present
- `test_mixed_endings_anomaly` — `is_canonical == False`, anomaly present
- `test_submitted_event_includes_skipped_count` — event `details["skipped_blocks"] == 1`

**Implementation note on mixed endings detection:**
Count `\r\n` vs `\n` occurrences in the raw bytes (after BOM strip). If both are
present, record anomaly. Use the majority line-ending for `SrtDialect.crlf`.

**Status:** [ ] pending

---

## Sub-Task 5 — Markup Stripping for CPS and char_counts

**Intent:**
CPS and per-line counts must count visible characters only, excluding SRT markup tags
(`<i>`, `</i>`, `<b>`, `</b>`, `<u>`, `</u>`, `<font ...>`, `</font>`). Stored
`lines` text keeps markup intact so `write_srt` produces byte-identical output.

**Design:**
Add a module-level helper in `subtitle.py`:
```python
_MARKUP_RE = re.compile(r"</?(?:i|b|u|font)(?:\s[^>]*)?>", re.IGNORECASE)

def _strip_markup(text: str) -> str:
    return _MARKUP_RE.sub("", text)
```

`char_counts` becomes: `[len(_strip_markup(line).rstrip()) for line in self.lines]`

Docstring update: document that `lines` preserves raw SRT markup for byte-identical
write-back, while `char_counts`, `total_chars`, and `cps` operate on visible text only.

**Hand-computed test values:**
- `"<i>Hello</i>"` → visible `"Hello"` → 5 chars
- `"<b><i>Hi</i></b>"` → nested → `"Hi"` → 2 chars
- `"<font color=\"red\">Subtitle text here!</font>"` → `"Subtitle text here!"` → 19 chars
- For the markup-pushes-raw-over-42 test:
  `"<i>" + "x" * 43 + "</i>"` → raw = 50 chars, visible = 43 chars (still over 42)
  `"<font color=\"#ffffff\">" + "a" * 38 + "</font>"` → raw = 60, visible = 38 (under 42)

**New tests in `tests/test_models.py`:**
- `test_markup_italic_stripped` — single `<i>...</i>` → char_count == visible length
- `test_markup_nested_stripped` — nested bold+italic → char_count == visible length
- `test_markup_font_tag_stripped` — `<font color="...">` → char_count == visible
- `test_markup_raw_over_42_visible_under` — raw > 42, visible < 42, char_count is visible
- `test_markup_raw_over_42_visible_also_over` — raw > 42, visible also > 42

**Relevant Context:**
- The existing `test_char_counts_strips_trailing_whitespace` and
  `test_char_counts_preserves_leading_whitespace` tests must still pass.
- `_strip_markup` strips tags only, not text content; leading whitespace in visible
  text is still counted.

**Status:** [ ] pending

---

## Sub-Task 6 — Event Schema 1.1 (event_id, UTC enforcement, forward-compat read)

**Intent:**
(a) Every event carries a globally unique `event_id` (UUID4) generated at creation.
(b) `serialise()` always converts `timestamp` to UTC before formatting with Z suffix,
regardless of the caller's timezone — eliminating the assumption that the timestamp is UTC.
(c) `read_all()` is forward-compatible: unknown `event_type` values and newer
`schema_version` strings surface as `UnknownDeliveryEvent` objects or are skipped with
a warning, never raise. A test confirms this.
(d) `delivery_id` cannot be empty when a `bus` is provided to `parse_srt`. If empty
string is passed with a bus, either raise `ValueError` immediately or auto-generate a
UUID and return it. Decision: **auto-generate and return** — callers that need the id
for correlation can capture the return value, and existing tests that pass `"x"` still work.
(e) Schema version bumps from `"1.0"` to `"1.1"`.

**Design decisions:**

`event_id`:
```python
import uuid
event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
```

UTC enforcement in `serialise()`:
```python
ts_utc = self.timestamp.astimezone(timezone.utc)
data["timestamp"] = ts_utc.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
```

Forward-compat `read_all()`:
```python
try:
    events.append(DeliveryEvent.model_validate(obj))
except Exception:
    # Unknown event_type or newer schema — emit a warning, skip the line
    import warnings
    warnings.warn(f"Skipping unrecognised event line: schema_version={obj.get('schema_version')}")
```

Empty `delivery_id` enforcement: in `parse_srt`, before emitting, if `delivery_id == ""`,
set `delivery_id = str(uuid.uuid4())`. The function signature changes to return a
`SubtitleFile` **and** the effective `delivery_id`. But changing the return type breaks
existing callers. Better: parse_srt returns only `SubtitleFile`, and `delivery_id` auto-gen
is transparent. The test asserts `event.delivery_id != ""` after calling with `delivery_id=""`.

**Schema version compatibility:** `read_all()` on a log written by schema 1.0 must still
work. Since 1.1 only adds `event_id`, reading a 1.0 line (which has no `event_id`) must
use a default value for `event_id`. Use `event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))` — when deserialising a 1.0 line, `event_id` gets a fresh UUID. This is
intentional and documented.

**Todo List:**
1. Add `import uuid` to `bus.py`
2. Add `event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))` to `DeliveryEvent`
3. Change `schema_version: str = "1.1"` default
4. Update `serialise()` to call `.astimezone(timezone.utc)` before formatting
5. Update `read_all()` to catch parse errors and warn instead of raising
6. In `parse_srt`, if `bus is not None and delivery_id == ""`, auto-generate UUID
7. Add tests: `test_event_has_unique_id`, `test_event_ids_are_unique_across_two_events`,
   `test_utc_conversion_from_non_utc_timestamp`, `test_forward_compat_unknown_event_type`,
   `test_forward_compat_skip_bad_line`, `test_empty_delivery_id_autogenerated`

**Backward compatibility check:**
- Existing `test_event_schema_version` asserts `== "1.0"` — this will **fail** after bump.
  Update it to assert `== "1.1"`.
- `test_read_all_roundtrip` asserts `schema_version == "1.0"` — update to `"1.1"`.
- All other existing tests are unaffected.

**Status:** [ ] pending

---

## Acceptance Criteria

- `python -m pytest` → all tests green (38 existing + new tests)
- `python -m passline` → prints effective model id, exits 0
- `git ls-files passline.egg-info` → empty (untracked)
- `docs/BUILD_JOURNAL.md`, `README.md` exist
- No `_meta_cache` in `passline/io/srt.py`
- `SubtitleFile` has `srt_dialect`, `is_canonical`, `skipped_blocks`, `parse_anomalies` fields
- `DeliveryEvent` has `event_id`, `schema_version == "1.1"` default
- `char_counts` strips SRT markup tags before counting
