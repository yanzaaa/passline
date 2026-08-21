# Passline Mission 05 — Rule Engine, Corpus Grading, Property Tests, CI

## Overview

Five deliverables in one mission:
1. **Rule engine** — `passline/qc/rules.py` — pure Python, zero AI, all measurements from `SubtitleCue` computed properties
2. **Corpus-grading test** — `tests/test_grading.py` — exact-match against DETERMINISTIC manifest entries
3. **Property-based tests** — `tests/test_rule_properties.py` — random cue generators proving math consistency
4. **Event emission** — findings emit `qc.violation` events into the event bus
5. **GitHub Actions CI** — two jobs: pytest suite + PR corpus table

---

## Architecture

```
passline/qc/
  __init__.py
  rules.py          ← rule engine: check_file() → list[Finding]
  thresholds.py     ← single source of truth, imported by corrupt.py too
```

`thresholds.py` is the canonical module. Both `corrupt.py` and `rules.py` import from it.
**No threshold is defined in two places.**

---

## Rule-to-manifest mapping (exact)

| Rule id in engine   | manifest `rule` field  | Severity          |
|---------------------|------------------------|-------------------|
| `three_line_cue`    | `three_line_cue`       | WARNING           |
| `line_too_long`     | `line_too_long`        | ERROR             |
| `cps_warning`       | `cps_warning`          | WARNING (17–20)   |
| `cps_exceeded`      | `cps_exceeded`         | ERROR (>20)       |
| `sub_one_second`    | `sub_one_second`       | ERROR             |
| `overlapping_cues`  | `overlapping_cues`     | ERROR             |
| `malformed_timecode`| (not in corpus)        | ERROR             |

---

## Sub-Tasks

---

### Sub-Task 1 — Thresholds module (single source of truth)

**Intent:**
Extract all numeric thresholds into `passline/qc/thresholds.py` so the rule engine,
corruption engine, and tests share one definition.  No threshold is duplicated.

**Todo List:**
1. Create `passline/qc/__init__.py`
2. Create `passline/qc/thresholds.py`:
   ```python
   CPS_VIOLATION = 20.0      # strictly above → ERROR
   CPS_WARNING_LOW = 17.0    # at or above → WARNING
   LINE_CHAR_MAX = 42        # strictly above → ERROR
   MAX_LINES_PER_CUE = 2     # strictly above → WARNING
   MIN_DURATION_MS = 1_000   # strictly below → ERROR
   ```
3. Update `passline/corpus/corrupt.py` to import from `passline.qc.thresholds`
   instead of defining constants locally (the four constants `CPS_THRESHOLD`,
   `LINE_CHAR_THRESHOLD`, `MIN_DURATION_MS` become imports).
   `CPS_THRESHOLD` maps to `thresholds.CPS_VIOLATION`.

**Status:** [ ] pending

---

### Sub-Task 2 — Rule engine

**Intent:**
`passline/qc/rules.py` grades a `SubtitleFile` and returns a list of `Finding`
objects.  Every measurement comes from `SubtitleCue` computed properties — the
engine never re-implements math.

**Finding dataclass:**
```python
@dataclass(frozen=True)
class Finding:
    rule: str           # matches manifest "rule" field exactly
    cue_index: int      # 1-based SubtitleCue.index
    measured_value: float
    threshold: float
    severity: str       # "ERROR" | "WARNING"
    explanation: str    # one-line human-readable
```

**`check_file(subtitle_file, delivery_id, language, bus) → list[Finding]`**

Rules implemented in order:

1. **`three_line_cue`** — `len(cue.lines) > MAX_LINES_PER_CUE`
   - severity: WARNING
   - measured: `len(cue.lines)` (float)
   - threshold: `MAX_LINES_PER_CUE` (2.0)
   - explanation: `f"Cue {cue.index}: {len(cue.lines)} lines (max {MAX_LINES_PER_CUE})"`

2. **`line_too_long`** — `any(c > LINE_CHAR_MAX for c in cue.char_counts)`
   - one Finding per cue (worst line reported)
   - severity: ERROR
   - measured: `max(cue.char_counts)`
   - threshold: `LINE_CHAR_MAX`

3. **`cps_exceeded`** / **`cps_warning`** — based on `cue.cps`
   - `cue.cps > CPS_VIOLATION` → ERROR, rule=`cps_exceeded`
   - `CPS_WARNING_LOW <= cue.cps <= CPS_VIOLATION` → WARNING, rule=`cps_warning`
   - (only one of these fires per cue — violation takes priority)

4. **`sub_one_second`** — `cue.duration_ms < MIN_DURATION_MS`
   - severity: ERROR
   - measured: `cue.duration_ms`

5. **`overlapping_cues`** — `cues[i].end_ms > cues[i+1].start_ms`
   - severity: ERROR
   - cue_index: `cues[i].index` (the cue whose end overlaps)
   - measured: overlap amount in ms (`cues[i].end_ms - cues[i+1].start_ms`)

6. **`malformed_timecode`** — `cue.start_ms >= cue.end_ms`
   - severity: ERROR
   - measured: `cue.end_ms - cue.start_ms` (negative or zero)

**Event emission:**
After computing findings, emit one `qc.violation` `DeliveryEvent` per finding:
```python
DeliveryEvent(
    event_type=EventType.QC_VIOLATION,
    delivery_id=delivery_id,
    language=language,
    details={
        "rule": finding.rule,
        "cue": finding.cue_index,
        "value": finding.measured_value,
        "threshold": finding.threshold,
        "severity": finding.severity,
        "explanation": finding.explanation,
    }
)
```
`bus` parameter is optional (`None` → no events emitted).

**Todo List:**
1. Create `passline/qc/rules.py` with `Finding` dataclass and `check_file()` function
2. Add `__all__` to `passline/qc/__init__.py` exporting `Finding`, `check_file`
3. `check_file` must not import `EventBus` at module level (use `TYPE_CHECKING`)

**Status:** [ ] pending

---

### Sub-Task 3 — Corpus-grading test

**Intent:**
`tests/test_grading.py` — automated, stays green forever.  Loads every broken corpus
file, grades it with the rule engine, and checks that the findings match the
DETERMINISTIC entries in the manifest exactly: zero misses, zero false positives,
matched on `(cue_index, rule, severity)`.

**MEANING_LEVEL entries are excluded** — they are the language checker's responsibility.

**Match key:** `(cue_index, rule, severity)` — three-tuple.

**Test structure:**
```python
@pytest.mark.parametrize("lang", ["en", "fr", "de"])
def test_corpus_grading_exact_match(lang):
    # Load broken file
    data = (BROKEN / f"tos-{lang}-broken.srt").read_bytes()
    broken = parse_srt(data, language=lang)

    # Load manifest
    manifest = CorpusManifest.from_dict(...)

    # Run rule engine
    findings = check_file(broken)

    # Build match sets
    expected = {
        (d.cue_index, d.rule, d.severity)
        for d in manifest.defects
        if d.category == "DETERMINISTIC"
    }
    actual = {
        (f.cue_index, f.rule, f.severity)
        for f in findings
    }

    missing = expected - actual
    extra   = actual - expected

    assert not missing, f"Rule engine missed: {missing}"
    assert not extra,   f"Rule engine over-fired: {extra}"
```

**Important nuance:** The `cps_warning` rule (17–20 CPS) fires on real clean cues
that the corruption engine did NOT inject as corpus defects (because the clean file
already had some).  The corpus-grading test must **only** compare against injected
defects.  If the clean file already had a violation, the engine will find it — but
since it's not in the manifest, it would show as a false positive.

**Resolution:** The grading test runs against the **broken file** (not the clean
file), and only checks against DETERMINISTIC manifest entries.  Findings on cues
NOT in the manifest must be allowed — they are pre-existing issues in the Blender
corpus, not injected defects.  The match key strategy is adjusted:

```python
# Only check manifest cues — pre-existing violations on non-manifest cues are OK
manifest_cue_indices = {d.cue_index for d in manifest.defects if d.category == "DETERMINISTIC"}

expected = {(d.cue_index, d.rule, d.severity) for d in manifest.defects if d.category == "DETERMINISTIC"}
actual_on_manifest_cues = {(f.cue_index, f.rule, f.severity) for f in findings if f.cue_index in manifest_cue_indices}

missing = expected - actual_on_manifest_cues
# extra check: for every manifest cue, we must not fire MORE rules than expected
# (which would indicate a double-injection or incorrect threshold)
extra_on_manifest_cues = actual_on_manifest_cues - expected

assert not missing, ...
assert not extra_on_manifest_cues, ...
```

**Todo List:**
1. Create `tests/test_grading.py` with the parametrised corpus-grading test
2. Add a test that proves event emission: `check_file(..., bus=bus)` emits one
   `qc.violation` event per finding
3. Add a test that proves warning/violation distinction: findings with severity
   "WARNING" emit events with `details["severity"] == "WARNING"`

**Status:** [ ] pending

---

### Sub-Task 4 — Property-based tests

**Intent:**
`tests/test_rule_properties.py` — random cue generators, no hypothesis library
needed (use `random.Random` with deterministic seeds for reproducibility).
Prove that the rule math is consistent with the cue model under edge cases.

**Test categories:**

**Category 1 — CPS consistency:**
For any random `(total_chars, duration_ms)`:
- If `total_chars / (duration_ms / 1000) > CPS_VIOLATION`:
  engine must emit `cps_exceeded` ERROR
- If `CPS_WARNING_LOW <= total_chars / (duration_ms / 1000) <= CPS_VIOLATION`:
  engine must emit `cps_warning` WARNING (not ERROR)
- Duration = 0: `cue.cps == 0.0`, no CPS finding

**Category 2 — Line length consistency:**
For any `line_text`:
- `len(_strip_markup(line_text).rstrip()) > LINE_CHAR_MAX` → `line_too_long` ERROR
- Unicode chars count as their character length (not byte length)
- Markup tags (`<i>`, `<b>`, etc.) are stripped before counting

**Category 3 — Duration consistency:**
- `duration_ms < MIN_DURATION_MS` → `sub_one_second` ERROR
- Negative duration (`end_ms < start_ms`) → `malformed_timecode` ERROR

**Category 4 — Empty lines:**
- Cue with `lines=[""]` → `char_counts == [0]`, no `line_too_long`
- No division by zero or crash

**Random generators:**
```python
def make_cue(rng, *, force_cps_violation=False, force_warning=False, ...):
    ...
```

**Todo List:**
1. Create `tests/test_rule_properties.py`
2. Implement `make_random_cue(rng, **overrides) → SubtitleCue`
3. Property test: 500 random cues, every CPS finding correctly classifies
4. Property test: 500 random line lengths, every `line_too_long` correctly fires
5. Property test: unicode in lines — count chars not bytes
6. Property test: zero-duration cue → no CPS finding, `malformed_timecode` fires
7. Property test: 500 random duration values, `sub_one_second` boundary exact

**Status:** [ ] pending

---

### Sub-Task 5 — GitHub Actions CI

**Intent:**
Two jobs in `.github/workflows/ci.yml`.  No cloud credentials, no network in Job 1.

**Job 1 — pytest suite (every push):**
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -e ".[dev]"
      - run: python -m pytest --tb=short
    # Status badge: ![CI](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)
```

**Job 2 — corpus table PR comment (PRs only, explicitly allowed to fail):**
```yaml
  corpus-report:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    continue-on-error: true           # MUST NOT block the PR
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12", cache: pip}
      - run: pip install -e ".[dev]"
      - name: Generate corpus report
        id: report
        run: |
          python scripts/corpus_report.py > /tmp/corpus_report.md 2>&1 || true
          echo "report<<EOF" >> $GITHUB_OUTPUT
          cat /tmp/corpus_report.md >> $GITHUB_OUTPUT
          echo "EOF" >> $GITHUB_OUTPUT
      - uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `## Corpus Grading Report\n\n${process.env.REPORT}`
            })
        env:
          REPORT: ${{ steps.report.outputs.report }}
```

`scripts/corpus_report.py` runs the rule engine over all three broken corpus files,
formats a markdown table, and exits 0 regardless of findings.

**pyproject.toml `[project.optional-dependencies]`:**
```toml
[project.optional-dependencies]
dev = ["pytest>=9"]
```
(fastapi, uvicorn etc are already in `dependencies`)

**README badge line:**
```markdown
![CI](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)
```
Replace OWNER/REPO with the actual GitHub remote (detect from git config).

**Todo List:**
1. Create `.github/workflows/ci.yml` with both jobs
2. Create `scripts/corpus_report.py`
3. Add `[project.optional-dependencies]` dev group to `pyproject.toml`
4. Add badge to `README.md` (detect repo from `git remote get-url origin`)
5. Ensure `passline-events.jsonl` is listed in `.gitignore` (runtime artifact)

**Status:** [ ] pending

---

## Acceptance Criteria

- `python -m pytest` passes all tests (109 existing + new)
- `tests/test_grading.py` parametrised over EN/FR/DE — all green
- `tests/test_rule_properties.py` — all green
- `check_file(broken, delivery_id=..., bus=bus)` emits `qc.violation` events
- Dashboard lights up: grading a broken file fills log with red violations
- `.github/workflows/ci.yml` exists with two jobs as specified
- README contains CI badge pointing to the workflow
- No threshold defined in two places
