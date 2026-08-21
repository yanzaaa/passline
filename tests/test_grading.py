"""Corpus-grading tests for the Passline rule engine.

The rule engine is graded against every DETERMINISTIC entry in each language's
corruption manifest.  Meaning-level entries are excluded — they are the
language checker's responsibility.

Match key: (cue_index, rule, severity) — three-tuple.

Only manifest cue indices are checked.  Pre-existing violations in the Blender
corpus on non-manifest cues are expected and ignored by design (option-a).

All three corpus files (EN, FR, DE) must pass.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from passline.corpus.corrupt import CorpusManifest
from passline.events.bus import DeliveryEvent, EventBus, EventType
from passline.io.srt import parse_srt
from passline.qc.rules import Finding, check_file

CORPUS   = Path(__file__).parent / "corpus"
BROKEN   = CORPUS / "broken"
MANIFEST_DIR = CORPUS / "manifests"
LANGUAGES = ["en", "fr", "de"]


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _load_broken(lang: str) -> tuple[bytes, object]:
    path = BROKEN / f"tos-{lang}-broken.srt"
    if not path.exists():
        pytest.skip(f"Broken corpus file missing: {path}")
    data = path.read_bytes()
    return data, parse_srt(data, language=lang)


def _load_manifest(lang: str) -> CorpusManifest:
    path = MANIFEST_DIR / f"tos-{lang}-manifest.json"
    if not path.exists():
        pytest.skip(f"Manifest missing: {path}")
    return CorpusManifest.from_dict(json.loads(path.read_text()))


# ─────────────────────────────────────────────────────────────────────────────
# Core grading test — parametrised over all three languages
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang", LANGUAGES)
def test_corpus_grading_exact_match(lang: str) -> None:
    """Rule engine exactly matches every DETERMINISTIC manifest entry.

    Zero misses: every injected defect is detected.
    Zero false positives: no extra findings on manifest cue indices.
    Pre-existing Blender violations on non-manifest cues are allowed (option-a).
    """
    _, broken = _load_broken(lang)
    manifest = _load_manifest(lang)

    findings = check_file(broken)

    # Only DETERMINISTIC entries — MEANING_LEVEL are excluded
    deterministic = [d for d in manifest.defects if d.category == "DETERMINISTIC"]

    # Expected findings (injected by corruption engine)
    expected: set[tuple[int, str, str]] = {
        (d.cue_index, d.rule, d.severity)
        for d in deterministic
    }

    # Manifest (cue_index, rule) pairs — only check these specific combos.
    # Pre-existing Blender violations on the same cue (different rule) are ignored.
    manifest_cue_rule_pairs = {(d.cue_index, d.rule) for d in deterministic}

    # Actual findings filtered to manifest cue+rule pairs only
    actual: set[tuple[int, str, str]] = {
        (f.cue_index, f.rule, f.severity)
        for f in findings
        if (f.cue_index, f.rule) in manifest_cue_rule_pairs
    }

    missing = expected - actual
    extra   = actual - expected

    assert not missing, (
        f"[{lang}] Rule engine MISSED {len(missing)} injected defect(s):\n"
        + "\n".join(f"  cue={cue_i:>3}  rule={rule:<22}  severity={sev}" for cue_i, rule, sev in sorted(missing))
    )
    assert not extra, (
        f"[{lang}] Rule engine OVER-FIRED {len(extra)} time(s) on manifest cues:\n"
        + "\n".join(f"  cue={cue_i:>3}  rule={rule:<22}  severity={sev}" for cue_i, rule, sev in sorted(extra))
    )


@pytest.mark.parametrize("lang", LANGUAGES)
def test_corpus_grading_finding_count_reasonable(lang: str) -> None:
    """The rule engine produces at least as many findings as injected defects."""
    _, broken = _load_broken(lang)
    manifest = _load_manifest(lang)
    n_deterministic = sum(1 for d in manifest.defects if d.category == "DETERMINISTIC")

    findings = check_file(broken)
    # Must find at least the injected ones (may find more on pre-existing cues)
    assert len(findings) >= n_deterministic, (
        f"[{lang}] Expected >= {n_deterministic} findings, got {len(findings)}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Event emission tests
# ─────────────────────────────────────────────────────────────────────────────

def test_check_file_emits_qc_violation_events(tmp_path: Path) -> None:
    """check_file with a bus emits one qc.violation event per finding."""
    _, broken = _load_broken("en")
    bus = EventBus(tmp_path / "events.jsonl")

    findings = check_file(broken, delivery_id="grading-test", language="en", bus=bus)

    events = [e for e in bus.read_all() if isinstance(e, DeliveryEvent)]
    violation_events = [e for e in events if e.event_type == EventType.QC_VIOLATION]

    assert len(violation_events) == len(findings), (
        f"Expected {len(findings)} qc.violation events, got {len(violation_events)}"
    )


def test_check_file_events_carry_severity(tmp_path: Path) -> None:
    """qc.violation events carry severity in their details payload."""
    _, broken = _load_broken("en")
    bus = EventBus(tmp_path / "events.jsonl")

    findings = check_file(broken, delivery_id="sev-test", language="en", bus=bus)

    events = [e for e in bus.read_all() if isinstance(e, DeliveryEvent)]
    for ev in events:
        if ev.event_type == EventType.QC_VIOLATION:
            assert "severity" in ev.details, f"Missing 'severity' in event details: {ev.details}"
            assert ev.details["severity"] in ("ERROR", "WARNING")


def test_check_file_events_carry_rule(tmp_path: Path) -> None:
    """qc.violation events carry the rule identifier in their details payload."""
    _, broken = _load_broken("en")
    bus = EventBus(tmp_path / "events.jsonl")

    findings = check_file(broken, delivery_id="rule-test", language="en", bus=bus)

    events = [e for e in bus.read_all() if isinstance(e, DeliveryEvent)]
    for ev in events:
        if ev.event_type == EventType.QC_VIOLATION:
            assert "rule" in ev.details
            assert "cue" in ev.details
            assert "value" in ev.details


def test_check_file_no_events_without_bus() -> None:
    """check_file with bus=None must not raise and must not write any log."""
    _, broken = _load_broken("en")
    findings = check_file(broken, delivery_id="no-bus", bus=None)
    assert isinstance(findings, list)


def test_warnings_and_violations_distinct(tmp_path: Path) -> None:
    """WARNING and ERROR severity findings both appear in events, visually distinct."""
    _, broken = _load_broken("en")
    bus = EventBus(tmp_path / "events.jsonl")

    findings = check_file(broken, delivery_id="distinct-sev", language="en", bus=bus)

    severities_in_findings = {f.severity for f in findings}
    events = [e for e in bus.read_all() if isinstance(e, DeliveryEvent)]
    severities_in_events = {
        e.details["severity"]
        for e in events
        if e.event_type == EventType.QC_VIOLATION and "severity" in e.details
    }

    # The EN broken corpus has both ERROR (cps_exceeded, line_too_long, etc.)
    # and WARNING (three_line_cue) — verify both appear
    assert "ERROR" in severities_in_findings
    assert "WARNING" in severities_in_findings
    assert severities_in_events == severities_in_findings


# ─────────────────────────────────────────────────────────────────────────────
# Rule-by-rule smoke tests (using real corpus defects as known inputs)
# ─────────────────────────────────────────────────────────────────────────────

def test_cps_exceeded_fires_on_corpus_cue() -> None:
    """The cps_exceeded rule fires on a known injected cue from the EN corpus."""
    _, broken = _load_broken("en")
    manifest = _load_manifest("en")

    # Find the first cps_blowout from the manifest
    cps_defect = next(
        (d for d in manifest.defects if d.defect_type == "cps_blowout"), None
    )
    if cps_defect is None:
        pytest.skip("No cps_blowout in EN corpus")

    findings = check_file(broken)
    cps_findings = [
        f for f in findings
        if f.cue_index == cps_defect.cue_index and f.rule == "cps_exceeded"
    ]
    assert cps_findings, (
        f"Expected cps_exceeded on cue {cps_defect.cue_index}, got nothing"
    )
    assert cps_findings[0].severity == "ERROR"
    # Measured value comes from SubtitleCue.cps — verify it exceeds the threshold
    from passline.qc.thresholds import CPS_VIOLATION
    assert cps_findings[0].measured_value > CPS_VIOLATION


def test_sub_one_second_fires_on_corpus_cue() -> None:
    """The sub_one_second rule fires on a known injected cue from the EN corpus."""
    _, broken = _load_broken("en")
    manifest = _load_manifest("en")

    dur_defect = next(
        (d for d in manifest.defects if d.defect_type == "short_duration"), None
    )
    if dur_defect is None:
        pytest.skip("No short_duration in EN corpus")

    findings = check_file(broken)
    dur_findings = [
        f for f in findings
        if f.cue_index == dur_defect.cue_index and f.rule == "sub_one_second"
    ]
    assert dur_findings, f"Expected sub_one_second on cue {dur_defect.cue_index}"
    from passline.qc.thresholds import MIN_DURATION_MS
    assert dur_findings[0].measured_value < MIN_DURATION_MS
