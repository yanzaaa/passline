#!/usr/bin/env python3
"""Generate a Markdown corpus-grading report for PR comments.

Runs the rule engine against every broken corpus file and prints a Markdown
table summarising findings vs. manifest expectations.

Usage:
    python scripts/corpus_report.py            # prints to stdout
    python scripts/corpus_report.py > out.md   # capture for CI comment
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure the package is importable when run from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from passline.corpus.corrupt import CorpusManifest
from passline.io.srt import parse_srt
from passline.qc.rules import check_file


CORPUS_DIR = Path(__file__).parent.parent / "tests" / "corpus"
BROKEN_DIR = CORPUS_DIR / "broken"
MANIFEST_DIR = CORPUS_DIR / "manifests"
LANGUAGES = ["en", "fr", "de"]


def grade_language(lang: str) -> dict:
    broken_path = BROKEN_DIR / f"tos-{lang}-broken.srt"
    manifest_path = MANIFEST_DIR / f"tos-{lang}-manifest.json"

    if not broken_path.exists():
        return {"lang": lang.upper(), "error": f"Missing: {broken_path.name}"}
    if not manifest_path.exists():
        return {"lang": lang.upper(), "error": f"Missing: {manifest_path.name}"}

    broken_bytes = broken_path.read_bytes()
    subtitle_file = parse_srt(broken_bytes, language=lang)
    manifest = CorpusManifest.from_dict(json.loads(manifest_path.read_text()))

    findings = check_file(subtitle_file)

    deterministic = [d for d in manifest.defects if d.category == "DETERMINISTIC"]
    expected = {(d.cue_index, d.rule, d.severity) for d in deterministic}
    manifest_cue_rule_pairs = {(d.cue_index, d.rule) for d in deterministic}

    actual = {
        (f.cue_index, f.rule, f.severity)
        for f in findings
        if (f.cue_index, f.rule) in manifest_cue_rule_pairs
    }

    missing = expected - actual
    extra = actual - expected
    matched = expected & actual

    return {
        "lang": lang.upper(),
        "injected": len(deterministic),
        "detected": len(matched),
        "missed": len(missing),
        "extra": len(extra),
        "total_findings": len(findings),
        "missing_detail": sorted(missing),
        "extra_detail": sorted(extra),
        "pass": len(missing) == 0 and len(extra) == 0,
    }


def render_report(results: list[dict]) -> str:
    lines: list[str] = []
    lines.append("## 📊 Corpus Grading Report\n")

    # Summary table
    lines.append("| Language | Injected | Detected | Missed | Extra | Total Findings | Status |")
    lines.append("|----------|----------|----------|--------|-------|----------------|--------|")

    for r in results:
        if "error" in r:
            lines.append(f"| {r['lang']} | — | — | — | — | — | ⚠️ {r['error']} |")
            continue
        status = "✅ PASS" if r["pass"] else "❌ FAIL"
        lines.append(
            f"| {r['lang']} "
            f"| {r['injected']} "
            f"| {r['detected']} "
            f"| {r['missed']} "
            f"| {r['extra']} "
            f"| {r['total_findings']} "
            f"| {status} |"
        )

    lines.append("")

    # Detail sections for failures
    any_failure = False
    for r in results:
        if "error" in r or r.get("pass"):
            continue
        any_failure = True
        lines.append(f"### {r['lang']} failures\n")
        if r["missing_detail"]:
            lines.append("**Missed** (rule engine did not detect injected defect):\n")
            for cue_i, rule, sev in r["missing_detail"]:
                lines.append(f"- cue `{cue_i:>3}` · `{rule}` · `{sev}`")
            lines.append("")
        if r["extra_detail"]:
            lines.append("**Extra** (rule engine over-fired on manifest cue+rule):\n")
            for cue_i, rule, sev in r["extra_detail"]:
                lines.append(f"- cue `{cue_i:>3}` · `{rule}` · `{sev}`")
            lines.append("")

    if not any_failure:
        lines.append("_All corpus languages passed — zero missed defects, zero false positives._")

    return "\n".join(lines)


def main() -> None:
    results = [grade_language(lang) for lang in LANGUAGES]
    print(render_report(results))

    # Exit non-zero if any language failed (useful for local debugging)
    if any(not r.get("pass", False) for r in results if "error" not in r):
        sys.exit(1)


if __name__ == "__main__":
    main()
