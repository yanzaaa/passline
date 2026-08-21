#!/usr/bin/env python3
"""Regenerate the Passline golden corpus from clean files.

Usage:
    python scripts/generate_corpus.py --seed 42

Reads:  tests/corpus/clean/{tos-en,tos-fr,tos-de}.srt
Writes: tests/corpus/broken/{tos-en,tos-fr,tos-de}-broken.srt
        tests/corpus/manifests/{tos-en,tos-fr,tos-de}-manifest.json

Same seed → byte-identical output every run.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from passline.io.srt import parse_srt
from passline.corpus.corrupt import corrupt_file

CLEAN_DIR    = REPO_ROOT / "tests" / "corpus" / "clean"
BROKEN_DIR   = REPO_ROOT / "tests" / "corpus" / "broken"
MANIFEST_DIR = REPO_ROOT / "tests" / "corpus" / "manifests"

LANGUAGES = [
    ("en", "tos-en.srt",   "en"),
    ("fr", "tos-fr.srt",   "fr"),
    ("de", "tos-de.srt",   "de"),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate Passline golden corpus")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    args = parser.parse_args(argv)
    seed = args.seed

    BROKEN_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Passline corpus generation  (seed={seed})\n")
    print(f"{'Lang':<5} {'Cues':>5} {'Defects':>8} {'Bytes':>8}  Output")
    print("-" * 70)

    ok = 0
    for lang, clean_fn, lang_code in LANGUAGES:
        clean_path = CLEAN_DIR / clean_fn
        if not clean_path.exists():
            print(f"  {lang:<5} SKIP — clean file not found: {clean_path}")
            print("        Run: python scripts/fetch_assets.py")
            continue

        data = clean_path.read_bytes()
        source = parse_srt(data, language=lang_code, source_path=str(clean_path))

        result = corrupt_file(
            source,
            seed=seed,
            language=lang_code,
            source_filename=clean_fn,
        )

        broken_path   = BROKEN_DIR   / f"tos-{lang}-broken.srt"
        manifest_path = MANIFEST_DIR / f"tos-{lang}-manifest.json"

        broken_path.write_bytes(result.broken_bytes)
        manifest_path.write_text(result.manifest.to_json(), encoding="utf-8")

        n_defects = len(result.manifest.defects)
        print(
            f"  {lang:<5} {len(source.cues):>5} {n_defects:>8} {len(result.broken_bytes):>8}  "
            f"{broken_path.name}"
        )
        for d in result.manifest.defects:
            print(f"         [{d.category:<14}] cue {d.cue_index:>3}  {d.defect_type}")
        ok += 1

    print()
    if ok == len(LANGUAGES):
        print(f"All {ok} corpus sets generated successfully.")
        return 0
    else:
        print(f"{ok}/{len(LANGUAGES)} generated. Check errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
