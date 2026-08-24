#!/usr/bin/env python3
"""Download Blender open-movie subtitle files for the Passline corpus.

Run once before working with the corpus. Never called by tests or CI.

Usage:
    python scripts/fetch_assets.py

Downloads to tests/corpus/clean/ and writes attribution README.

Source: https://download.blender.org/demo/movies/ToS/subtitles/
License: Creative Commons Attribution 3.0 (CC-BY 3.0)
"""
from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
OUT_DIR = REPO_ROOT / "tests" / "corpus" / "clean"

BASE = "https://download.blender.org/demo/movies/ToS/subtitles/"

# Candidate lists per language — tried in order; first 200 OK wins.
URL_CANDIDATES: dict[str, list[str]] = {
    "en": [
        f"{BASE}TOS-en.srt",
        "https://download.blender.org/movies/tears_of_steel/tears_of_steel-en.srt",
        "https://download.blender.org/movies/ToS/subtitles/TOS-en.srt",
    ],
    "fr": [
        f"{BASE}TOS-fr-orig.srt",   # canonical original French
        f"{BASE}TOS-fr-OMenor.srt",
        f"{BASE}TOS-fr-Goofy.srt",
        "https://download.blender.org/movies/tears_of_steel/tears_of_steel-fr.srt",
    ],
    "de": [
        f"{BASE}TOS-de.srt",
        "https://download.blender.org/movies/tears_of_steel/tears_of_steel-de.srt",
        "https://download.blender.org/movies/ToS/subtitles/TOS-de.srt",
    ],
    "es": [f"{BASE}TOS-es.srt"],
    "ru": [f"{BASE}TOS-ru.srt"],
    "pt": [f"{BASE}TOS-PT-BR.srt"],
    "zh": [f"{BASE}TOS-CH.srt"],
    "fa": [f"{BASE}TOS-Persian.srt"],
}

OUTPUT_FILENAMES = {
    "en": "tos-en.srt", 
    "fr": "tos-fr.srt", 
    "de": "tos-de.srt",
    "es": "tos-es.srt",
    "ru": "tos-ru.srt",
    "pt": "tos-pt.srt",
    "zh": "tos-zh.srt",
    "fa": "tos-fa.srt",
}

ATTRIBUTION = """# Corpus Assets — CC-BY Attribution

## Tears of Steel

© Blender Foundation | mango.blender.org
Licensed under Creative Commons Attribution 3.0 (CC-BY 3.0)
https://creativecommons.org/licenses/by/3.0/

### Subtitle files

| Language | Filename | Source URL |
|---|---|---|
| English | tos-en.srt | https://download.blender.org/demo/movies/ToS/subtitles/TOS-en.srt |
| French | tos-fr.srt | https://download.blender.org/demo/movies/ToS/subtitles/TOS-fr-orig.srt |
| German | tos-de.srt | https://download.blender.org/demo/movies/ToS/subtitles/TOS-de.srt |
| Spanish | tos-es.srt | https://download.blender.org/demo/movies/ToS/subtitles/TOS-es.srt |
| Russian | tos-ru.srt | https://download.blender.org/demo/movies/ToS/subtitles/TOS-ru.srt |
| Portuguese | tos-pt.srt | https://download.blender.org/demo/movies/ToS/subtitles/TOS-PT-BR.srt |
| Chinese | tos-zh.srt | https://download.blender.org/demo/movies/ToS/subtitles/TOS-CH.srt |
| Persian | tos-fa.srt | https://download.blender.org/demo/movies/ToS/subtitles/TOS-Persian.srt |

These files are used as test fixtures for the Passline QC engine.
They are committed to this repository under the terms of the CC-BY 3.0 license.
Modifications are tracked in tests/corpus/broken/ alongside their manifests.
"""


def fetch_one(lang: str) -> tuple[str, bytes]:
    """Try each URL candidate in order. Return (url, content) for the first success."""
    candidates = URL_CANDIDATES[lang]
    last_err: Exception | None = None
    for url in candidates:
        print(f"  [{lang}] trying {url} …", end=" ", flush=True)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "passline-corpus/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                print(f"✓  {len(data):,} bytes")
                return url, data
        except urllib.error.HTTPError as e:
            print(f"HTTP {e.code}")
            last_err = e
        except Exception as e:
            print(f"error: {e}")
            last_err = e
    raise RuntimeError(f"All URLs for '{lang}' failed. Last error: {last_err}")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Passline corpus asset fetch")
    print(f"Output directory: {OUT_DIR}\n")

    successes: list[tuple[str, str, int]] = []
    failures: list[str] = []

    for lang in ("en", "fr", "de", "es", "ru", "pt", "zh", "fa"):
        try:
            url, data = fetch_one(lang)
            out_path = OUT_DIR / OUTPUT_FILENAMES[lang]
            out_path.write_bytes(data)
            successes.append((lang, url, len(data)))
        except RuntimeError as e:
            print(f"  [{lang}] FAILED: {e}")
            failures.append(lang)

    # Write attribution README alongside clean/
    readme_path = OUT_DIR.parent / "README.md"
    readme_path.write_text(ATTRIBUTION, encoding="utf-8")
    print(f"\nAttribution written: {readme_path}")

    if successes:
        print(f"\n{'Lang':<6} {'Bytes':>8}  URL")
        for lang, url, size in successes:
            print(f"  {lang:<4} {size:>8,}  {url}")

    if failures:
        print(f"\nFailed languages: {', '.join(failures)}")
        return 1

    print(f"\nAll {len(successes)} languages downloaded successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
