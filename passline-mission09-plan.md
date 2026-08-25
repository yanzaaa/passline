# Mission 09 — Speech and Video Origination Plan

**Status:** Planning  
**Scope:** Speech/video ingest → Gemini transcription → cue assembly → multi-language translation → existing QC pipeline handoff  
**Constraint:** All runtime AI must be Google-only throughout the entire dependency tree. Whisper, any OpenAI technology, and any non-Google transcription service are permanently excluded.

---

## Table of Contents

1. [Overview and Goals](#1-overview-and-goals)
2. [Critical Assumption Validation (Riskiest First)](#2-critical-assumption-validation)
3. [Module Boundaries and Directory Layout](#3-module-boundaries-and-directory-layout)
4. [API Contract](#4-api-contract)
5. [Dashboard Changes](#5-dashboard-changes)
6. [Cue Builder Module Specification](#6-cue-builder-module-specification)
7. [Translation and Pipeline Handoff](#7-translation-and-pipeline-handoff)
8. [Test Strategy](#8-test-strategy)
9. [Sub-Task Dependency Order](#9-sub-task-dependency-order)
10. [Risk Register](#10-risk-register)

---

## 1. Overview and Goals

Mission 09 adds a speech and video origination path to Passline. Today, the system accepts already-authored SRT files and runs them through QC and repair. After this mission, it can also accept raw audio or video, produce a first-pass subtitle cue set in the source language, translate it into eight target languages, and submit each translated file into the existing pipeline as though a human had uploaded it.

### Inputs accepted

| Input type | Browser capture | File upload |
|---|---|---|
| Audio (WAV, MP3, WebM/Opus) | ✓ microphone via MediaRecorder | ✓ `/api/originate` |
| Video (MP4, WebM/VP8) | — | ✓ `/api/originate` |

### Eight target languages

English (`en`), French (`fr`), German (`de`), Spanish (`es`), Portuguese (`pt`), Russian (`ru`), Farsi (`fa`), Mandarin Chinese (`zh`).

These correspond exactly to the language codes already present in `passline/dashboard/app.py`'s `_DEMO_FILES` mapping (lines 67–92), confirming the downstream pipeline already handles all eight.

### Invariants that must not change

- The deterministic rule engine in `passline/qc/rules.py` and `passline/qc/thresholds.py` is the single source of truth for all numeric limits. The cue builder imports from `thresholds.py` — never defines its own constants.
- `PipelineRunner.run_delivery(srt_bytes, language, ...)` is the only permitted handoff into the QC pipeline. No new agent or bypass path is added.
- No non-Google AI dependency may appear anywhere in the dependency tree.

---

## 2. Critical Assumption Validation

### 2.1 The Single Riskiest Assumption

> **Does the Gemini Speech API on Vertex AI accept browser-recorded WebM/Opus and WebM/VP8 audio directly, without requiring server-side format conversion to a supported format such as WAV or FLAC?**

This assumption blocks the entire origination path. If it is false, every other implementation decision — particularly the microphone capture flow, the server-side ingest handler, and the storage format for uploaded files — must be redesigned before any other work can begin. A wrong answer discovered after cue builder implementation would require tearing out the ingest layer.

### 2.2 Why this assumption is risky

The browser's native `MediaRecorder` API produces `audio/webm;codecs=opus` (on Chrome/Edge/Firefox) or `audio/webm;codecs=vp8` (for video tracks). These are Matroska container formats. The Gemini `generateContent` API accepts audio inline as base64 `inlineData` with a MIME type field. The Vertex AI documentation lists supported MIME types that include `audio/wav`, `audio/flac`, `audio/mp3`, `audio/ogg`, and `audio/webm` — but the exact codec support within `audio/webm` and the maximum file size limits for inline audio are not definitively documented as of the planning date.

If the API requires WAV or FLAC, the server must transcode every browser-recorded file before sending it to Gemini. That would add a dependency on `ffmpeg` (a non-Python system binary), introduce latency, and require Cloud Run container configuration changes. It would also change the security profile of the upload endpoint.

### 2.3 Concrete validation experiment

Before any other implementation work begins, run the following experiment in isolation. This requires only `google-genai` (already installed) and access to Vertex AI credentials.

```python
# scripts/validate_webm_transcription.py
"""
Validation experiment: confirm Gemini on Vertex AI accepts browser-native
WebM/Opus audio for transcription without server-side conversion.

Run with:
    GOOGLE_CLOUD_PROJECT=<project> python scripts/validate_webm_transcription.py

Pass/fail criteria are printed explicitly.
"""
import base64
import sys
from pathlib import Path

from google import genai
from google.genai import types

# A real WebM/Opus file captured by MediaRecorder in Chrome.
# Capture one in DevTools: navigator.mediaDevices.getUserMedia({audio:true})
# → new MediaRecorder(stream, {mimeType:'audio/webm;codecs=opus'})
# → record 5 seconds → save the Blob to a file.
WEBM_FILE = Path("scripts/fixtures/test_clip.webm")
VIDEO_WEBM_FILE = Path("scripts/fixtures/test_clip_video.webm")  # video+audio

def test_audio_webm(client: genai.Client, file_bytes: bytes, mime: str) -> bool:
    """Returns True if Gemini returns a non-empty transcription."""
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=types.Content(parts=[
                types.Part(inline_data=types.Blob(
                    mime_type=mime,
                    data=base64.b64encode(file_bytes).decode(),
                )),
                types.Part(text=(
                    "Transcribe this audio with word-level timestamps. "
                    "Return JSON: [{word, start_s, end_s}, ...]"
                )),
            ]),
        )
        text = response.text or ""
        print(f"  MIME={mime!r}  response_length={len(text)}  preview={text[:120]!r}")
        return len(text) > 10
    except Exception as exc:
        print(f"  MIME={mime!r}  ERROR: {exc}")
        return False

def main() -> None:
    import os
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        sys.exit("Set GOOGLE_CLOUD_PROJECT")

    client = genai.Client(vertexai=True, project=project, location="us-central1")

    results: dict[str, bool] = {}

    for path, mime in [
        (WEBM_FILE,       "audio/webm"),
        (WEBM_FILE,       "audio/webm;codecs=opus"),
        (VIDEO_WEBM_FILE, "video/webm"),
        (VIDEO_WEBM_FILE, "video/webm;codecs=vp8"),
    ]:
        if not path.exists():
            print(f"SKIP: {path} not found")
            continue
        data = path.read_bytes()
        print(f"\nTesting {path.name} as {mime!r}  ({len(data)} bytes)")
        results[mime] = test_audio_webm(client, data, mime)

    print("\n--- RESULTS ---")
    for mime, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  {status}  {mime}")

    if all(results.values()):
        print("\nCONCLUSION: Direct WebM ingest is supported. No transcoding needed.")
    else:
        print("\nCONCLUSION: At least one MIME type failed.")
        print("ACTION REQUIRED: Add server-side transcoding via ffmpeg before proceeding.")

if __name__ == "__main__":
    main()
```

**Pass criteria:** Both `audio/webm` and `audio/webm;codecs=opus` return non-empty transcriptions containing recognisable words.

**Fail path:** If either fails, add `passline/origination/transcoder.py` using `subprocess` to invoke `ffmpeg -i input.webm -ar 16000 -ac 1 output.wav` before the Gemini call. Document the `ffmpeg` system dependency in `AGENTS.md` and `README.md`. Update `Dockerfile` (if any) and Cloud Run deployment instructions. This adds Sub-Task 0.5 to the dependency chain in Section 9.

**Decision gate:** This experiment must be completed and its result recorded in a new `docs/BUILD_JOURNAL.md` Mission 09 entry before any Sub-Task 1 code is written.

---

## 3. Module Boundaries and Directory Layout

### 3.1 New top-level module: `passline/origination/`

All new code for this mission lives under `passline/origination/`. Nothing in the existing `passline/` tree is restructured. New code integrates only through the existing public interfaces: `PipelineRunner.run_delivery()` and `parse_srt()`.

```
passline/
├── origination/
│   ├── __init__.py              # exports: originate_file, OriginationResult
│   ├── transcriber.py           # Gemini speech-to-text, returns TranscriptSegment list
│   ├── cue_builder.py           # pure Python: transcript → SubtitleFile (no LLM)
│   ├── translator.py            # Gemini translation: SubtitleFile → {lang: SubtitleFile}
│   ├── orchestrator.py          # assembles transcriber → cue_builder → translator → pipeline
│   └── transcoder.py            # CONDITIONAL: ffmpeg subprocess wrapper (only if §2.3 fails)
│
tests/
├── test_cue_builder.py          # golden-file suite for the cue builder
├── test_transcriber.py          # integration test for Vertex AI call (--live flag)
├── test_origination_e2e.py      # end-to-end: audio bytes → pipeline reports
└── fixtures/
    └── origination/
        ├── en_segment_transcript.json    # golden input: timestamped segments
        ├── en_expected_cues.srt          # golden output: expected SRT
        ├── zh_segment_transcript.json    # Mandarin golden input
        └── zh_expected_cues.srt          # Mandarin golden output
```

### 3.2 Files modified (not created)

| File | Change |
|---|---|
| `passline/dashboard/app.py` | Add `POST /api/originate` endpoint and `GET /api/originate/status/{job_id}` |
| `passline/dashboard/html.py` | Add microphone capture button and origination progress section (CSS + minimal HTML class additions) |
| `pyproject.toml` | Add `passline.origination` to package scan; add `tests/fixtures/origination/` to package data |
| `AGENTS.md` | Add new env vars; document `ffmpeg` dependency if §2.3 fails |
| `docs/BUILD_JOURNAL.md` | Add Mission 09 entry |
| `README.md` | Add origination feature description |

### 3.3 Files not modified

`passline/qc/`, `passline/agents/`, `passline/pipeline/`, `passline/events/`, `passline/io/`, `passline/corpus/`, `passline/models/`. All downstream systems receive `(srt_bytes, language)` tuples and are unaware of the origination path.

---

## 4. API Contract

### 4.1 `POST /api/originate`

Accepts an audio or video file upload and starts an asynchronous origination job.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | `UploadFile` | Yes | Audio or video file |
| `source_language` | `str` | Yes | BCP-47 code of the spoken language, e.g. `"en-US"` |
| `target_languages` | `str` | No | Comma-separated BCP-47 codes. Defaults to all eight supported languages |
| `max_cps` | `float` | No | Reading speed override. Defaults to language-specific threshold from `thresholds.py` |

**Accepted MIME types:** `audio/webm`, `audio/webm;codecs=opus`, `audio/wav`, `audio/flac`, `audio/mp3`, `audio/ogg`, `video/webm`, `video/mp4`.

**Response `202 Accepted`:**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "accepted",
  "source_language": "en-US",
  "target_languages": ["en", "fr", "de", "es", "pt", "ru", "fa", "zh"],
  "filename": "recording.webm",
  "bytes": 184320
}
```

**Response `415 Unsupported Media Type`:** when the uploaded content type is not in the accepted list.

**Response `400 Bad Request`:** when `source_language` is missing or not a valid BCP-47 prefix.

### 4.2 `GET /api/originate/status/{job_id}`

Polls the progress of an origination job.

**Response `200 OK`:**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "translating",
  "stage": "translate_fr",
  "deliveries_started": 3,
  "deliveries_total": 8,
  "error": null
}
```

**`status` values:** `"accepted"` | `"transcribing"` | `"building_cues"` | `"translating"` | `"submitting"` | `"done"` | `"error"`

**Response `404 Not Found`:** when `job_id` is unknown.

### 4.3 Microphone capture flow (browser → server)

No new server endpoint is needed. The browser captures audio using `MediaRecorder`, accumulates chunks into a `Blob`, constructs a `File` object from the blob, and POSTs it to the existing `/api/originate` endpoint using `FormData` — the same pattern used by the existing file drop zone (see `passline/dashboard/html.py` `handleFile()`).

```
browser MediaRecorder
  → ondataavailable chunks → Blob('audio/webm;codecs=opus')
  → File(blob, 'mic-recording.webm', {type: 'audio/webm;codecs=opus'})
  → FormData.append('file', file)
  → POST /api/originate  (+ source_language from UI selector)
```

This requires no new server endpoint and adds no new JavaScript libraries. The existing `fetch` + `FormData` pattern suffices.

### 4.4 Server-side origination job lifecycle

```
POST /api/originate
  → validate inputs
  → create OriginationJob(job_id, status="accepted") in _origination_jobs dict
  → schedule background_task: _run_origination_job(job_id, file_bytes, mime, source_lang, target_langs)
  → return 202

_run_origination_job():
  1. job.status = "transcribing"
     → transcriber.transcribe(file_bytes, mime, source_lang) → list[TranscriptSegment]

  2. job.status = "building_cues"
     → cue_builder.build(segments, language=source_lang) → SubtitleFile

  3. job.status = "translating"
     → for each target_lang:
         job.stage = f"translate_{target_lang}"
         translated_file = translator.translate(source_file, target_lang)
         srt_bytes = write_srt(translated_file)
         delivery_id = str(uuid4())
         runner = PipelineRunner(bus=bus, approval_queue=_approval_queue)
         asyncio.create_task(runner.run_delivery(srt_bytes, target_lang, delivery_id))
         job.deliveries_started += 1

  4. job.status = "done"
```

---

## 5. Dashboard Changes

### 5.1 New HTML elements

All new elements are inserted into the existing left column (`#col-left`) below the existing demo-chips card and above the delivery-cards container. No existing elements are reordered or removed.

```html
<!-- Origination panel -->
<div class="card origination-card" id="origination-card" style="padding:10px 14px">
  <div class="origination-header">
    <span class="origination-label">Originate from Speech</span>
    <select id="origination-lang" class="origination-lang-select">
      <option value="en-US">English</option>
      <option value="fr-FR">French</option>
      <option value="de-DE">German</option>
      <option value="es-ES">Spanish</option>
      <option value="pt-BR">Portuguese</option>
      <option value="ru-RU">Russian</option>
      <option value="fa-IR">Farsi</option>
      <option value="zh-CN">Mandarin</option>
    </select>
  </div>
  <div class="origination-controls">
    <button class="ctrl-btn origination-mic-btn" id="mic-btn" onclick="toggleMic()">
      🎙 RECORD
    </button>
    <span class="origination-status" id="origination-status">Ready</span>
  </div>
  <div class="origination-progress" id="origination-progress" style="display:none">
    <div class="progress-bar">
      <div class="progress-fill" id="origination-progress-fill"></div>
    </div>
    <span class="origination-stage" id="origination-stage"></span>
  </div>
</div>
```

### 5.2 New CSS class hooks

The following CSS classes are added to the stylesheet in `html.py`. All other styling is handled entirely by these classes; no inline styles beyond `display:none` guards are used.

| Class | Purpose |
|---|---|
| `.origination-card` | Container card for the origination panel |
| `.origination-header` | Flex row holding label and language selector |
| `.origination-label` | Section label (matches `.col-header` visual weight) |
| `.origination-lang-select` | Language picker; styled to match the existing dark card surface |
| `.origination-controls` | Flex row holding the record button and status text |
| `.origination-mic-btn` | The microphone record button; extends `.ctrl-btn` |
| `.origination-mic-btn.recording` | Active recording state: red border pulse, `STOP` label |
| `.origination-status` | Small status text beside the button |
| `.origination-progress` | Container for the progress bar and stage label |
| `.origination-stage` | Muted monospace text showing current pipeline stage |

### 5.3 JavaScript additions (no new libraries)

The following functions are added to the existing `<script>` block in `html.py`. They use only the browser's native `MediaRecorder` API, `fetch`, and `FormData`. No import statements, no CDN links, no `npm` packages.

```javascript
// ── Microphone origination ────────────────────────────────────────────
let _mediaRecorder = null;
let _audioChunks   = [];
let _originJobId   = null;
let _originPollTimer = null;

async function toggleMic() {
  if (_mediaRecorder && _mediaRecorder.state === 'recording') {
    _mediaRecorder.stop();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio: true});
    _audioChunks = [];
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus' : 'audio/webm';
    _mediaRecorder = new MediaRecorder(stream, {mimeType});
    _mediaRecorder.ondataavailable = e => { if (e.data.size) _audioChunks.push(e.data); };
    _mediaRecorder.onstop = () => {
      stream.getTracks().forEach(t => t.stop());
      const blob = new Blob(_audioChunks, {type: mimeType});
      _submitOrigination(new File([blob], 'mic-recording.webm', {type: mimeType}));
    };
    _mediaRecorder.start(1000);  // 1-second chunks
    setMicState('recording');
  } catch (err) {
    setOriginationStatus('Microphone access denied: ' + err.message);
  }
}

function setMicState(state) {
  const btn = document.getElementById('mic-btn');
  btn.classList.toggle('recording', state === 'recording');
  btn.textContent = state === 'recording' ? '⏹ STOP' : '🎙 RECORD';
}

async function _submitOrigination(file) {
  setOriginationStatus('Uploading…');
  const lang = document.getElementById('origination-lang').value;
  const fd = new FormData();
  fd.append('file', file);
  fd.append('source_language', lang);
  try {
    const r = await fetch('/api/originate', {method: 'POST', body: fd});
    if (!r.ok) { setOriginationStatus('Upload failed: ' + r.status); return; }
    const data = await r.json();
    _originJobId = data.job_id;
    document.getElementById('origination-progress').style.display = '';
    _startOriginPoll();
  } catch (e) { setOriginationStatus('Error: ' + e.message); }
  setMicState('idle');
}

function _startOriginPoll() {
  if (_originPollTimer) clearInterval(_originPollTimer);
  _originPollTimer = setInterval(async () => {
    if (!_originJobId) return;
    try {
      const r = await fetch('/api/originate/status/' + _originJobId);
      const d = await r.json();
      setOriginationStatus(d.status + (d.stage ? ' · ' + d.stage : ''));
      const pct = d.deliveries_total
        ? Math.round((d.deliveries_started / d.deliveries_total) * 100) : 0;
      document.getElementById('origination-progress-fill').style.width = pct + '%';
      if (d.status === 'done' || d.status === 'error') {
        clearInterval(_originPollTimer);
        _originPollTimer = null;
        setOriginationStatus(d.status === 'done' ? 'All deliveries submitted.' : 'Error: ' + d.error);
      }
    } catch (_) {}
  }, 2000);
}

function setOriginationStatus(msg) {
  document.getElementById('origination-status').textContent = msg;
  document.getElementById('origination-stage').textContent = msg;
}
```

### 5.4 Reset integration

The existing `startReset()` function must also clear origination state:
- Set `_originJobId = null`, clear `_originPollTimer`.
- Reset `#origination-progress` to `display:none`.
- Reset `#origination-status` to `"Ready"`.
- Reset `#mic-btn` to idle state.

These additions are pure appends to the existing `startReset()` body; no existing lines change.

---

## 6. Cue Builder Module Specification

### 6.1 Inputs and outputs

```python
# passline/origination/cue_builder.py

from dataclasses import dataclass
from passline.models.subtitle import SubtitleCue, SubtitleFile

@dataclass(frozen=True)
class TranscriptSegment:
    """One time-aligned unit from the transcription API.

    Either word-level (word="Hello", start_s=1.2, end_s=1.6) or
    phrase-level (word="Hello world", start_s=1.2, end_s=2.0).
    The cue builder handles both granularities identically.
    """
    word: str
    start_s: float
    end_s: float


def build_cues(
    segments: list[TranscriptSegment],
    language: str = "und",
    max_cps: float | None = None,
    max_line_chars: int | None = None,
    max_display_cols: int | None = None,
    min_duration_ms: int | None = None,
) -> SubtitleFile:
    """Assemble a SubtitleFile from time-aligned transcript segments.

    All numeric defaults are read from passline.qc.thresholds — never
    defined inside this function.  Caller overrides are validated against
    threshold bounds and clamped if out of range.

    Returns a SubtitleFile whose cues are guaranteed to pass check_file()
    with zero findings for the rules: sub_one_second, overlapping_cues,
    malformed_timecode.  line_too_long and cps_exceeded are also
    guaranteed clean because the builder enforces them during assembly.
    """
    ...
```

### 6.2 Algorithm

The cue builder is a single-pass greedy algorithm. No LLM is involved at any stage.

**Step 1 — Resolve limits from thresholds**

```python
from passline.qc.thresholds import (
    CPS_VIOLATION, CPS_VIOLATION_CJK,
    LINE_CHAR_MAX, LINE_CHAR_MAX_CJK,
    MIN_DURATION_MS,
)
is_cjk = language.lower() in {"zh", "ja", "ko", "zh-cn", "zh-tw", "zh-hant", "zh-hans"}
cps_limit    = max_cps           or (CPS_VIOLATION_CJK   if is_cjk else CPS_VIOLATION)
line_limit   = max_line_chars    or (LINE_CHAR_MAX_CJK    if is_cjk else LINE_CHAR_MAX)
dur_min_ms   = min_duration_ms   or MIN_DURATION_MS
```

**Step 2 — Display-width counting for CJK**

```python
import unicodedata

def display_width(text: str) -> int:
    """Return the display column count of *text* using East Asian width."""
    total = 0
    for ch in text:
        w = unicodedata.east_asian_width(ch)
        total += 2 if w in ("W", "F") else 1
    return total
```

This mirrors `SubtitleCue.display_char_counts` exactly. The cue builder uses the same function so the assembled cues are consistent with what the rule engine will later measure.

**Step 3 — Greedy line packing**

For each segment, the builder attempts to append the segment's text to the current line of the current cue. If appending would exceed `line_limit`, it wraps to the next line. If the cue already has `MAX_LINES_PER_CUE` (2) lines, it closes the current cue and opens a new one.

```
for segment in segments:
    word = segment.word.strip()
    if word is empty: continue

    candidate = current_line + (" " if current_line else "") + word
    candidate_width = display_width(candidate) if is_cjk else len(candidate)

    if candidate_width <= line_limit:
        # Append to current line
        current_line = candidate
        current_end_s = segment.end_s
    elif len(current_cue_lines) < MAX_LINES_PER_CUE:
        # Wrap to next line in same cue
        flush current_line into current_cue_lines
        current_line = word
        current_end_s = segment.end_s
    else:
        # Close current cue, start new one
        close_cue(current_cue_lines, cue_start_s, current_end_s)
        current_cue_lines = []
        current_line = word
        cue_start_s = segment.start_s
        current_end_s = segment.end_s

# Flush final cue
if current_line or current_cue_lines:
    close_cue(...)
```

**Step 4 — Minimum duration enforcement**

When `close_cue()` is called, if `(end_s - start_s) * 1000 < MIN_DURATION_MS`, the cue's end time is extended to `start_s + MIN_DURATION_MS / 1000`. The extension is capped at the start time of the next segment to prevent overlap.

```python
def close_cue(lines, start_s, end_s, next_start_s=None):
    end_ms = int(end_s * 1000)
    start_ms = int(start_s * 1000)
    if end_ms - start_ms < MIN_DURATION_MS:
        end_ms = start_ms + MIN_DURATION_MS
        if next_start_s is not None:
            end_ms = min(end_ms, int(next_start_s * 1000) - 1)
```

**Step 5 — Overlap prevention**

After all cues are assembled, a final pass ensures no cue's `end_ms` exceeds the next cue's `start_ms`. Any overlap is resolved by trimming `end_ms` of the earlier cue to `next_start_ms - 1`. This pass runs in O(n) and is the last mutation before the `SubtitleFile` is constructed.

**Step 6 — CPS enforcement (reflow)**

After cue assembly, a reflow pass checks every cue's CPS. If a cue exceeds `cps_limit`, it is split at the midpoint of its word list into two cues. The split cues are guaranteed not to exceed the line limit (since the original was already packed to `line_limit`). Each half-cue receives half the original duration. If the split produces a cue below `MIN_DURATION_MS`, the segment boundary is adjusted to the nearest transcript segment boundary with adequate duration. If no valid split exists (e.g. a single word with high CPS), the cue is left as-is and a warning is attached to the `SubtitleFile.parse_anomalies` field rather than silently discarding content.

### 6.3 Interface invariants (enforced by the golden-file tests)

| Invariant | Enforcement point |
|---|---|
| No cue has `start_ms >= end_ms` | Step 4 |
| No cue has `duration_ms < MIN_DURATION_MS` (except single-word fallback) | Step 4 |
| No two adjacent cues overlap | Step 5 |
| No line exceeds `line_limit` display columns | Step 3 |
| No cue has more than `MAX_LINES_PER_CUE` lines | Step 3 |
| `cue.cps` ≤ `cps_limit` (except single-word fallback) | Step 6 |
| Cue indices are 1-based and contiguous | Final assembly |
| All limits imported from `passline.qc.thresholds` | Step 1 |

---

## 7. Translation and Pipeline Handoff

### 7.1 Transcription: `passline/origination/transcriber.py`

```python
from google import genai
from google.genai import types

async def transcribe(
    audio_bytes: bytes,
    mime_type: str,
    source_language: str,
    model: str = "gemini-2.0-flash",
) -> list[TranscriptSegment]:
    """Send audio to Gemini on Vertex AI and return time-aligned segments.

    The prompt requests word-level or sentence-level timestamps in JSON.
    The response is parsed into TranscriptSegment objects.
    Falls back to sentence-level if word-level timestamps are not returned.
    Raises TranscriptionError on API failure after tenacity retry.
    """
```

**Prompt template:**

```
Transcribe the following audio in {source_language}.
Return ONLY valid JSON: [{"word": "...", "start_s": 0.0, "end_s": 0.5}, ...]
Use word-level timestamps if available, otherwise sentence-level segments.
Do not include any text outside the JSON array.
```

**Retry policy:** `tenacity` `retry_if_exception_type(google.api_core.exceptions.ResourceExhausted)`, exponential backoff, max 4 attempts. Reuses the same retry pattern as `passline/agents/language_checker.py`.

**Size limit guard:** If `len(audio_bytes) > 20 * 1024 * 1024` (20 MB), raise `TranscriptionError("Audio file exceeds 20 MB inline limit")`. This matches the documented Gemini inline data limit. Files above this limit require the File API; that path is out of scope for Mission 09 and flagged in the risk register.

### 7.2 Translation: `passline/origination/translator.py`

```python
async def translate_cues(
    source_file: SubtitleFile,
    target_language: str,
    model: str = "gemini-2.0-flash",
) -> SubtitleFile:
    """Translate cue text from source_file into target_language.

    Sends cue text as a structured JSON list to Gemini. Returns a new
    SubtitleFile with identical timing but translated text lines.
    Timing is never modified by the translator — only text changes.

    The returned file's language field is set to target_language.
    """
```

**Prompt template:**

```
Translate the following subtitle cues from {source_language} to {target_language}.
Preserve line breaks. Keep translations concise — these are subtitle cues.
Return ONLY valid JSON: [{"index": 1, "lines": ["translated line 1", "line 2"]}, ...]
Input cues: {json_cues}
```

**Constraint:** The translator must never alter `start_ms` or `end_ms`. Only `lines` is replaced. `SubtitleCue` is frozen (Pydantic `model_config = ConfigDict(frozen=True)`) so replacement is done by constructing new `SubtitleCue` objects with original timing.

### 7.3 Pipeline handoff

After translation, each language's `SubtitleFile` is serialised to bytes and submitted exactly as a human upload:

```python
from passline.io.srt import write_srt
from passline.pipeline.runner import PipelineRunner

for lang, translated_file in translations.items():
    srt_bytes = write_srt(translated_file)
    delivery_id = str(uuid4())
    runner = PipelineRunner(bus=bus, approval_queue=approval_queue)
    # Non-blocking: create_task ensures the origination orchestrator
    # does not block waiting for each pipeline run to complete.
    asyncio.create_task(
        runner.run_delivery(
            srt_bytes=srt_bytes,
            language=lang,
            delivery_id=delivery_id,
            parent_id=job_id,   # links all translated deliveries to the origination job
        )
    )
```

The `parent_id` field is already supported by `PipelineRunner.run_delivery()` (present in `passline/pipeline/runner.py` line 68). The dashboard already renders a `parent:` line on cards when `ev.details.parent_id` is set (Mission 07 sub-task 8).

---

## 8. Test Strategy

### 8.1 Cue builder golden-file tests (`tests/test_cue_builder.py`)

These tests are fully offline — no API calls, no LLM, no network. All test inputs are committed JSON files in `tests/fixtures/origination/`. Each test calls `build_cues()` and asserts the output either matches a golden SRT file or passes `check_file()` with zero findings.

| Test name | Input | Assert |
|---|---|---|
| `test_en_multiline_split` | 20 English words, each ~0.3s, total ~6s | Every cue ≤ 2 lines; every line ≤ 42 chars; `check_file()` returns `[]` |
| `test_zh_cjk_column_budget` | 30 Mandarin characters, each ~0.2s | Every line ≤ 16 display columns (CJK); `check_file(language="zh")` returns `[]` |
| `test_cps_rejection_and_reflow` | 5 words crammed into 0.3s | CPS would exceed 20.0 before reflow; after reflow each cue ≤ 20.0 CPS; `check_file()` returns `[]` |
| `test_minimum_duration_enforcement` | Single word lasting 0.2s | Cue duration extended to ≥ 1000ms; no overlap with next cue |
| `test_overlap_prevention` | Two consecutive segments with identical end/start times | Output has no overlapping cues; `check_file()` rule `overlapping_cues` returns `[]` |
| `test_golden_file_en` | `en_segment_transcript.json` | Output bytes match `en_expected_cues.srt` exactly |
| `test_golden_file_zh` | `zh_segment_transcript.json` | Output bytes match `zh_expected_cues.srt` exactly |
| `test_single_word_fallback` | One word lasting 0.1s with 50 chars | Raises no exception; `parse_anomalies` contains a reflow-warning entry |
| `test_determinism` | Same input, different call order | Two calls with identical arguments return identical bytes |

**Golden file generation:** Run `python scripts/generate_origination_fixtures.py` once to produce the `.srt` golden files from the `.json` inputs. Commit both. Future changes to the cue builder that intentionally alter output must regenerate and recommit the golden files. This follows the same pattern as `scripts/generate_corpus.py`.

### 8.2 Transcriber integration tests (`tests/test_transcriber.py`)

These tests make real Vertex AI calls and are gated behind `--live-llm`. They do not run in CI.

| Test name | What it tests |
|---|---|
| `test_transcribe_webm_opus` | 5-second WebM/Opus clip; asserts ≥ 3 `TranscriptSegment` objects returned |
| `test_transcribe_returns_timestamps` | Same clip; asserts all `start_s < end_s` |
| `test_transcribe_oversized_raises` | 21 MB dummy bytes; asserts `TranscriptionError` before API call |
| `test_transcribe_retry_on_429` | Mock 429 twice then success; asserts `tenacity` retry fired exactly twice |

### 8.3 End-to-end origination tests (`tests/test_origination_e2e.py`)

These tests use the ASGI test client pattern from `tests/test_dashboard.py`. The Gemini calls are stubbed.

| Test name | What it tests |
|---|---|
| `test_originate_endpoint_accepts_webm` | POST to `/api/originate` with a small WebM blob; asserts `202` and a `job_id` |
| `test_originate_status_lifecycle` | Poll `/api/originate/status/{id}` through all status values with mocked orchestrator |
| `test_originate_submits_all_target_languages` | Mock transcriber + translator; assert `PipelineRunner.run_delivery` called 8 times |
| `test_originate_pipeline_handoff_language` | Assert each `run_delivery` call receives the correct BCP-47 language code |
| `test_originate_rejects_unsupported_mime` | POST with `text/plain`; asserts `415` |
| `test_originate_missing_source_language` | POST without `source_language`; asserts `400` |

### 8.4 Reset integration test

Extend `tests/test_dashboard.py` with:

| Test name | What it tests |
|---|---|
| `test_reset_clears_origination_state` | Start an origination job, POST `/api/reset`, assert job state is cleared and no further `run_delivery` calls occur |

---

## 9. Sub-Task Dependency Order

The dependency chain is linear at the top (blocked by the validation experiment) and fans out once the cue builder is proven.

```
Sub-Task 0 — Run §2.3 validation experiment
  BLOCKS ALL OTHERS.
  Output: "direct" (no transcoding needed) or "transcode" (add ffmpeg wrapper).

Sub-Task 0.5 — [CONDITIONAL] Add passline/origination/transcoder.py
  Only if Sub-Task 0 result is "transcode".
  BLOCKS Sub-Task 1.

Sub-Task 1 — Implement passline/origination/cue_builder.py
  Depends on: Sub-Task 0 (interface decisions finalised)
  Does NOT depend on any LLM. Pure Python.

Sub-Task 2 — Write golden-file tests for cue_builder (§8.1)
  Depends on: Sub-Task 1
  No new code — only tests and fixtures.

Sub-Task 3 — Implement passline/origination/transcriber.py
  Depends on: Sub-Task 0 (MIME type handling confirmed)
  Parallel with Sub-Tasks 1 and 2.

Sub-Task 4 — Implement passline/origination/translator.py
  Depends on: Sub-Task 1 (SubtitleFile interface used)
  Parallel with Sub-Task 3.

Sub-Task 5 — Implement passline/origination/orchestrator.py
  Depends on: Sub-Tasks 1, 3, 4.

Sub-Task 6 — Add POST /api/originate and GET /api/originate/status/{id} to app.py
  Depends on: Sub-Task 5.

Sub-Task 7 — Dashboard changes (§5): microphone button, CSS, JS, reset integration
  Depends on: Sub-Task 6 (endpoint contract finalised).

Sub-Task 8 — Write integration and e2e tests (§8.2, §8.3, §8.4)
  Depends on: Sub-Tasks 6, 7.

Sub-Task 9 — README, BUILD_JOURNAL, AGENTS.md updates
  Depends on: Sub-Task 8 (test count finalised).
```

**Parallel opportunities:**
- Sub-Tasks 1 and 2 can run in parallel with Sub-Task 3.
- Sub-Task 4 can run in parallel with Sub-Task 3.
- Sub-Tasks 7 and 8 can overlap once Sub-Task 6 is stable.

**Critical path:** 0 → 1 → 5 → 6 → 7 → 8 → 9 (with 0.5 inserted if transcoding is required).

---

## 10. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **R1** | Gemini does not accept `audio/webm;codecs=opus` inline and requires WAV/FLAC | Medium | High | Validation experiment (§2.3) gates all other work. If FAIL: add `transcoder.py` using `ffmpeg` subprocess, document system dependency, update Cloud Run container config. Cost: +1 sub-task, +3–5 days. |
| **R2** | Word-level timestamps are not returned by Gemini for all languages (especially CJK) | Medium | Medium | The cue builder handles phrase-level segments equally well (algorithm is granularity-agnostic). CJK transcription often returns character-level or phrase-level anyway. Fallback: accept any segment granularity ≥ sentence-level. Golden-file tests must cover phrase-level inputs. |
| **R3** | Translated cue text causes downstream QC violations at a rate that exhausts the repair budget | Medium | Medium | The cue builder's timing is already within spec. Translated text may be longer or shorter than the source. Mitigation: after translation, run `check_file()` on the translated file and emit a pre-submission warning event if ≥ 5 violations are found. The pipeline still runs; the warning is informational. |
| **R4** | Audio files from `MediaRecorder` exceed the 20 MB Gemini inline data limit | Low | High | The `transcriber.py` size guard (§7.1) raises `TranscriptionError` before calling the API. The dashboard UI shows an error and prompts the user to upload a shorter clip. Long-form support via the Gemini File API is explicitly out of scope and documented as a known limitation. |
| **R5** | Farsi (`fa`) and Mandarin (`zh`) script handling in the cue builder produces invisible characters or incorrect display widths due to RTL or ideographic edge cases | Low | Medium | Mandarin: `unicodedata.east_asian_width` is the established standard; the `SubtitleCue.display_char_counts` property (already shipping in `passline/models/subtitle.py`) uses the same function, so parity is guaranteed. Farsi/RTL: SRT files are logically stored in visual order; the cue builder produces logical Unicode order and leaves rendering to the player. Golden-file tests for CJK (§8.1 `test_zh_cjk_column_budget`) will catch regressions. A Farsi golden-file test is added to the test suite. |
| **R6** | Eight simultaneous `PipelineRunner` background tasks (one per translation) saturate the Gemini quota during the language-checker stage | Low | Medium | The pipeline already uses `tenacity` retry on 429 in `LanguageCheckerAgent`. The orchestrator submits all eight deliveries as `asyncio.create_task` with no artificial throttle; the existing retry logic handles quota pressure. If needed, the orchestrator can be changed to submit deliveries in batches of 2–3 with a configurable concurrency cap (`PASSLINE_ORIGINATION_CONCURRENCY` env var, default 8). |
