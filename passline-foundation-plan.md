# Passline Foundation Plan

## Overview

Bootstrap the Passline codebase: a multi-agent subtitle QC and repair system on Google ADK 2.7.1 + Gemini on Vertex AI. This plan covers the five deliverables requested — package layout, subtitle data model, SRT parser/writer, delivery event system, and pytest golden-file test suite.

**Constraints:**
- Google-only AI: `google-adk` and `google-genai` are the only AI dependencies
- Rule engine is pure deterministic Python — no LLM decides math
- Byte-identical SRT round-trip is a hard requirement
- All tests pass with a single `python -m pytest` command from the project root

---

## Architecture Diagram

```
passline/
├── __init__.py
├── __main__.py           ← entry point: imports + calls both Google libs at startup
├── models/
│   ├── __init__.py
│   └── subtitle.py       ← SubtitleCue, SubtitleFile data models
├── io/
│   ├── __init__.py
│   └── srt.py            ← SRT parser + writer (byte-identical round-trip)
├── events/
│   ├── __init__.py
│   └── bus.py            ← DeliveryEvent, EventBus (JSONL log)
└── agents/
    ├── __init__.py
    └── qc_agent.py       ← ADK LlmAgent stub (wired in __main__)
tests/
├── conftest.py
├── fixtures/
│   └── sample.srt        ← hand-crafted golden SRT file
├── test_srt.py
├── test_models.py
└── test_events.py
pyproject.toml
```

---

## Sub-Tasks

---

### Sub-Task 1: Package Layout + pyproject.toml + Entry Point

**Intent:**
Create the `passline/` Python package and `pyproject.toml` with pinned dependencies. The entry point (`__main__.py`) must visibly import and invoke both `google.adk` and `google.genai` at module top-level, so an automated screener sees them immediately.

**Expected Outcomes:**
- `python -m passline` runs without error
- `pyproject.toml` pins `google-adk==2.7.1` and `google-genai` (>=2.19,<3)
- Imports of `google.adk.Agent`, `google.adk.Runner`, `google.genai.Client` appear in the first ~20 lines of `__main__.py`
- A minimal `LlmAgent` is constructed (no model call made — no API key needed at startup check)
- `agents/qc_agent.py` defines the `QcAgent` as an `LlmAgent` stub

**Todo List:**
1. Create `pyproject.toml` with `[project]` metadata, `requires-python = ">=3.12"`, and dependencies list including `google-adk==2.7.1`, `google-genai>=2.19,<3`, `pydantic>=2.12,<3`, `python-dotenv>=1,<2`
2. Create `passline/__init__.py` (package version constant `__version__ = "0.1.0"`)
3. Create `passline/agents/__init__.py` and `passline/agents/qc_agent.py` defining `QcAgent = LlmAgent(name="qc_agent", model="gemini-2.0-flash", instruction="...")`
4. Create `passline/__main__.py` that: (a) imports `google.adk.Agent`, `google.adk.Runner`, `google.genai.Client` at the top; (b) loads `.env` with `python-dotenv`; (c) constructs a `Runner` with `InMemorySessionService`; (d) prints a startup banner; (e) wraps everything so `if __name__ == "__main__": main()`
5. Create all other `__init__.py` files to make sub-packages importable

**Relevant Context:**
- ADK `LlmAgent` lives at `google.adk.agents.LlmAgent`; `from google.adk import Agent` is the public alias
- `Runner` requires `agent`, `app_name`, and `session_service=InMemorySessionService()`
- `from google.adk.sessions import InMemorySessionService`
- `google.genai.Client` constructor accepts `api_key` or `project`+`location` for Vertex AI
- No actual API call should be made at startup (just construction)

**Status:** [ ] pending

---

### Sub-Task 2: Subtitle Cue Data Model

**Intent:**
Define `SubtitleCue` and `SubtitleFile` as Pydantic v2 models with millisecond-precision timing and computed properties for QC use. All math is deterministic Python — no LLM involvement.

**Expected Outcomes:**
- `SubtitleCue` holds `index: int`, `start_ms: int`, `end_ms: int`, `lines: list[str]`
- Computed properties: `duration_ms`, `char_counts` (per line), `total_chars`, `cps` (characters per second, float, two-decimal precision)
- `SubtitleFile` holds `cues: list[SubtitleCue]`, `language: str`, `source_path: str | None`
- Models are importable from `passline.models`

**Todo List:**
1. Create `passline/models/__init__.py` exporting `SubtitleCue`, `SubtitleFile`
2. Create `passline/models/subtitle.py`:
   - `SubtitleCue(BaseModel)` with fields `index`, `start_ms`, `end_ms`, `lines`
   - `@computed_field` or `@property` for `duration_ms = end_ms - start_ms`
   - `@computed_field` for `char_counts: list[int]` — len of each line (strip trailing whitespace)
   - `@computed_field` for `total_chars: int` — sum of char_counts
   - `@computed_field` for `cps: float` — `total_chars / (duration_ms / 1000)`, guard against zero duration
   - `SubtitleFile(BaseModel)` with `cues`, `language = "und"`, `source_path = None`
3. Use Pydantic v2 `model_config = ConfigDict(frozen=True)` so cues are immutable after parse

**Relevant Context:**
- Pydantic v2: `from pydantic import BaseModel, computed_field, ConfigDict`
- CPS formula: `total_chars / duration_seconds`. For zero-duration cues, return `0.0` not raise
- `char_counts` counts characters per line (not bytes), stripping only trailing whitespace not leading

**Status:** [ ] pending

---

### Sub-Task 3: SRT Parser and Writer

**Intent:**
Implement a parser that reads SRT bytes → `SubtitleFile`, and a writer that serialises `SubtitleFile` → bytes, guaranteeing byte-identical output when round-tripping a valid SRT file.

**Expected Outcomes:**
- `parse_srt(data: bytes, language: str, source_path: str | None) -> SubtitleFile` handles UTF-8 BOM, CRLF, LF
- `write_srt(file: SubtitleFile) -> bytes` produces the exact same bytes as the input
- Round-trip guarantee: `write_srt(parse_srt(raw)) == raw` for any valid SRT
- Parser emits a `subtitle.submitted` event via `EventBus` on successful parse
- Multi-line cues are fully supported

**Todo List:**
1. Create `passline/io/__init__.py` exporting `parse_srt`, `write_srt`
2. Create `passline/io/srt.py`:
   - Detect and strip UTF-8 BOM (`b"\xef\xbb\xbf"`) before parsing; record it
   - Normalise line endings: detect whether source uses CRLF or LF; record the detected style
   - Split on blank-line cue boundaries (double newline in normalised form)
   - Parse each cue block: first line is index, second is timecode `HH:MM:SS,mmm --> HH:MM:SS,mmm`, remaining lines are text
   - Parse timecodes into milliseconds: `H*3600000 + M*60000 + S*1000 + ms`
   - `write_srt` reconstructs exactly: BOM if present, original line-ending style, timecodes zero-padded to `HH:MM:SS,mmm`, trailing newline matching original
   - Emit `subtitle.submitted` event via `EventBus` inside `parse_srt` (accept an optional `EventBus` parameter; default `None` skips emission so tests can isolate)
3. Timecode formatting helper: `_ms_to_timecode(ms: int) -> str` → `"HH:MM:SS,mmm"`
4. Timecode parsing helper: `_timecode_to_ms(tc: str) -> int`

**Relevant Context:**
- SRT timecode separator is `,` not `.` — this is the most common gotcha
- The blank-line cue splitter must handle both `\r\n\r\n` and `\n\n` after normalisation
- To guarantee byte-identical output: do NOT modify the original line-ending style, do NOT add or remove the trailing newline if the original had/lacked it
- The `EventBus` is defined in Sub-Task 4; import it lazily or accept as parameter to avoid circular import

**Status:** [ ] pending

---

### Sub-Task 4: Delivery Event System

**Intent:**
Implement a lightweight event bus that appends structured `DeliveryEvent` records to a local JSONL log file. The schema is versioned and clean enough to later feed a live dashboard and a Kafka topic.

**Expected Outcomes:**
- `EventType` enum: `SUBTITLE_SUBMITTED = "subtitle.submitted"`, `QC_VIOLATION = "qc.violation"`, `QC_REPAIRED = "qc.repaired"`, `DELIVERY_PASSED = "delivery.passed"`
- `DeliveryEvent` Pydantic v2 model: `schema_version: str = "1.0"`, `event_type: EventType`, `timestamp: datetime` (UTC ISO-8601), `delivery_id: str`, `language: str`, `details: dict[str, Any]`
- `EventBus` class: constructed with a `log_path: Path`; `emit(event)` appends one JSON line; `read_all() -> list[DeliveryEvent]` for test assertions
- JSONL format: one JSON object per line, `\n` terminated, UTF-8

**Todo List:**
1. Create `passline/events/__init__.py` exporting `EventType`, `DeliveryEvent`, `EventBus`
2. Create `passline/events/bus.py`:
   - `EventType(str, Enum)` with the four values
   - `DeliveryEvent(BaseModel)` with `schema_version = "1.0"`, `event_type`, `timestamp = Field(default_factory=lambda: datetime.now(timezone.utc))`, `delivery_id`, `language`, `details: dict[str, Any] = Field(default_factory=dict)`
   - `EventBus.__init__(self, log_path: Path)` — creates parent dirs, opens in append mode
   - `EventBus.emit(self, event: DeliveryEvent) -> None` — appends `event.model_dump_json() + "\n"` to file
   - `EventBus.read_all(self) -> list[DeliveryEvent]` — reads the JSONL file and parses each line
3. `DeliveryEvent.model_dump_json()` must serialise `datetime` as ISO-8601 with `Z` suffix (use `model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat().replace("+00:00", "Z")})`)

**Relevant Context:**
- Pydantic v2 serialisation: `model_dump_json()` is the correct method (not `.json()`)
- `datetime` timezone: always store and serialise as UTC. Use `datetime.now(timezone.utc)` not `datetime.utcnow()`
- JSONL is newline-delimited; each line must be a self-contained JSON object with no trailing comma

**Status:** [ ] pending

---

### Sub-Task 5: Pytest Golden-File Test Suite

**Intent:**
Write a thorough, focused test suite using a hand-crafted SRT fixture. Tests verify the byte-identical round-trip, the CPS/line-length math (values computed by hand here in the plan), and correct event emission.

**Expected Outcomes:**
- All tests pass with `python -m pytest` from the project root
- No external network calls or API keys required
- Golden SRT fixture is stored as a file in `tests/fixtures/`

**Golden Fixture — `tests/fixtures/sample.srt`:**

```
1
00:00:01,000 --> 00:00:03,500
Hello, world!

2
00:00:05,000 --> 00:00:08,000
This is a subtitle.
With two lines.

```

Hand-computed expected values:
- Cue 1: `start_ms=1000`, `end_ms=3500`, `duration_ms=2500`, `lines=["Hello, world!"]`, `total_chars=13`, `cps=13/2.5=5.2`
- Cue 2: `start_ms=5000`, `end_ms=8000`, `duration_ms=3000`, `lines=["This is a subtitle.", "With two lines."]`, `char_counts=[19, 15]`, `total_chars=34`, `cps=34/3.0≈11.333...`

**Todo List:**
1. Create `tests/fixtures/sample.srt` with LF line endings, no BOM, trailing newline after last blank line (as shown above)
2. Create a CRLF variant `tests/fixtures/sample_crlf.srt` (same content, CRLF endings, no BOM)
3. Create a BOM variant `tests/fixtures/sample_bom.srt` (LF endings, UTF-8 BOM prepended)
4. Create `tests/conftest.py` with fixtures: `sample_srt_bytes`, `sample_crlf_bytes`, `sample_bom_bytes`, `tmp_event_log` (tmp_path-based EventBus)
5. Create `tests/test_srt.py`:
   - `test_parse_cue_count` — parsed file has 2 cues
   - `test_parse_cue1_times` — start_ms=1000, end_ms=3500
   - `test_parse_cue2_lines` — lines == ["This is a subtitle.", "With two lines."]
   - `test_round_trip_lf` — `write_srt(parse_srt(raw)) == raw`
   - `test_round_trip_crlf` — same for CRLF variant
   - `test_round_trip_bom` — same for BOM variant
6. Create `tests/test_models.py`:
   - `test_cue1_duration` — duration_ms == 2500
   - `test_cue1_cps` — cps == 5.2
   - `test_cue1_char_counts` — char_counts == [13]
   - `test_cue2_char_counts` — char_counts == [19, 15]
   - `test_cue2_total_chars` — total_chars == 34
   - `test_cue2_cps` — abs(cps - 11.333) < 0.001
   - `test_zero_duration_cps` — cps == 0.0 for a cue with start_ms == end_ms
7. Create `tests/test_events.py`:
   - `test_subtitle_submitted_emitted` — parse_srt with an EventBus emits exactly one SUBTITLE_SUBMITTED event
   - `test_event_delivery_id` — event delivery_id matches what was passed
   - `test_event_language` — event language matches
   - `test_event_schema_version` — schema_version == "1.0"
   - `test_event_timestamp_utc` — timestamp has UTC timezone
   - `test_jsonl_append` — two emitted events → two lines in the log file
   - `test_read_all_roundtrip` — emit then read_all returns equivalent events

**Relevant Context:**
- `parse_srt` should accept `delivery_id: str` and `bus: EventBus | None = None` to enable event testing
- Use `tmp_path` pytest fixture for the EventBus log path in tests — never write to a fixed path
- `pytest.approx` for float comparisons in CPS tests
- Fixture files must be committed as binary (LF/CRLF must be preserved by git) — add `tests/fixtures/*.srt` to `.gitattributes` with `binary` attribute

**Status:** [ ] pending
