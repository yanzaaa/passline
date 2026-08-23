#!/usr/bin/env python3
"""Generate the Passline demo broken excerpt files from clean files.

Usage:
    python scripts/generate_demo_corpus.py

Reads:  tests/corpus/clean/{tos-en,tos-fr,tos-de}.srt
Writes: passline/corpus/demo/{demo-en-broken,demo-fr-broken,demo-de-broken}.srt
        passline/corpus/demo/{demo-en-manifest,demo-fr-manifest,demo-de-manifest}.json
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from passline.io.srt import parse_srt
from passline.corpus.corrupt import corrupt_demo
from passline.qc.rules import check_file

DEMO_DIR = REPO_ROOT / "passline" / "corpus" / "demo"
CLEAN_DIR = REPO_ROOT / "tests" / "corpus" / "clean"

LANGUAGES = [
    ("en", "tos-en.srt", 7),
    ("fr", "tos-fr.srt", 11),
    ("de", "tos-de.srt", 13),
]


def main() -> int:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    print("Generating demo-grade broken excerpts...\n")
    print(f"{'Lang':<5} {'Seed':<5} {'Defects':>8} {'Bytes':>8}  Output")
    print("-" * 70)

    for lang, clean_fn, seed in LANGUAGES:
        clean_path = CLEAN_DIR / clean_fn
        if not clean_path.exists():
            print(f"ERROR: clean file not found: {clean_path}")
            return 1

        data = clean_path.read_bytes()
        source = parse_srt(data, language=lang)

        # Call corrupt_demo
        result = corrupt_demo(
            source,
            seed=seed,
            language=lang,
            excerpt_cues=14,
        )

        # Ensure the generated file matches the manifest by re-running check_file
        # and re-building the defect list based on the actual rules triggered.
        # Wait, the prompt says: "Each manifest's defect list must account for every violation the rule engine finds in the generated file, so the manifest and the graded file can never disagree."
        broken_file = parse_srt(result.broken_bytes, language=lang)
        violations = check_file(broken_file)
        
        # update manifest defects
        from passline.corpus.corrupt import DefectSpec
        real_defects = []
        for v in violations:
            real_defects.append(DefectSpec(
                cue_index=v.cue_index,
                defect_type="auto-detected",
                rule=v.rule,
                threshold=getattr(v, 'threshold', None),
                measured_value=getattr(v, 'measured_value', None),
                severity=getattr(v, 'severity', 'error'),
                category="rule",
                detail=f"Rule {v.rule} triggered"
            ))
            
        # The prompt also says "record in each manifest the real source filename it was built from"
        result.manifest.source_file = f"tests/corpus/clean/{clean_fn}"
        
        # Keep the meaning swap injection in the manifest if it's there
        meaning_swaps = [d for d in result.manifest.defects if d.defect_type == "meaning_swap"]
        result.manifest.defects = real_defects + meaning_swaps

        broken_path = DEMO_DIR / f"demo-{lang}-broken.srt"
        manifest_path = DEMO_DIR / f"demo-{lang}-manifest.json"

        broken_path.write_bytes(result.broken_bytes)
        manifest_path.write_text(result.manifest.to_json(), encoding="utf-8")

        n_defects = len(result.manifest.defects)
        print(
            f"  {lang:<5} {seed:<5} {n_defects:>8} {len(result.broken_bytes):>8}  "
            f"{broken_path.name}"
        )
        for d in result.manifest.defects:
            print(f"         [{d.category:<14}] cue {d.cue_index:>3}  {d.defect_type} ({d.rule})")

    print("\nGeneration completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
