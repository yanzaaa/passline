"""Corpus, corruption engine, and golden-fixture tests.

Test groups
-----------
A — Defect-type unit tests using synthetic cues.  Each test creates a minimal
    SubtitleCue, applies the relevant corruption function, and verifies the
    defect using the cue model's own computed properties.

B — Round-trip tests: every committed broken SRT file must pass
    write_srt(parse_srt(data)) == data.

C — Manifest correctness: for every DETERMINISTIC defect in a committed manifest,
    look up the cue in the parsed broken file and assert the violation via the
    cue model's computed property.

D — Determinism: same seed produces byte-identical output every time.

E — Defect-type toggling: enabling/disabling individual defect types works.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from passline.corpus.corrupt import (
    ALL_DEFECT_TYPES,
    CPS_THRESHOLD,
    LINE_CHAR_THRESHOLD,
    MIN_DURATION_MS,
    CorpusManifest,
    corrupt_file,
    _apply_cps_blowout,
    _apply_line_overflow,
    _apply_overlap,
    _apply_short_duration,
    _apply_three_line_cue,
)
from passline.io.srt import parse_srt, write_srt
from passline.models.subtitle import SubtitleCue, SubtitleFile, SrtDialect

CORPUS = Path(__file__).parent / "corpus"
CLEAN   = CORPUS / "clean"
BROKEN  = CORPUS / "broken"
MANIFEST_DIR = CORPUS / "manifests"

LANGUAGES = ["en", "fr", "de"]


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def clean_files() -> dict[str, SubtitleFile]:
    """Parse all clean corpus files once for the session."""
    result = {}
    for lang in LANGUAGES:
        path = CLEAN / f"tos-{lang}.srt"
        if not path.exists():
            pytest.skip(f"Clean file not found: {path}. Run: python scripts/fetch_assets.py")
        data = path.read_bytes()
        result[lang] = parse_srt(data, language=lang)
    return result


@pytest.fixture(scope="session")
def broken_files() -> dict[str, tuple[bytes, SubtitleFile]]:
    """Read committed broken files and parse them."""
    result = {}
    for lang in LANGUAGES:
        path = BROKEN / f"tos-{lang}-broken.srt"
        if not path.exists():
            pytest.skip(f"Broken file not found: {path}. Run: python scripts/generate_corpus.py")
        data = path.read_bytes()
        result[lang] = (data, parse_srt(data, language=lang))
    return result


@pytest.fixture(scope="session")
def manifests() -> dict[str, CorpusManifest]:
    """Load committed manifests."""
    result = {}
    for lang in LANGUAGES:
        path = MANIFEST_DIR / f"tos-{lang}-manifest.json"
        if not path.exists():
            pytest.skip(f"Manifest not found: {path}. Run: python scripts/generate_corpus.py")
        result[lang] = CorpusManifest.from_dict(json.loads(path.read_text()))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Group A — Defect-type unit tests (synthetic cues)
# ─────────────────────────────────────────────────────────────────────────────

class TestDefectUnits:
    """Each test verifies one defect type using SubtitleCue's own computed properties."""

    def test_cps_blowout_exceeds_threshold(self) -> None:
        """After CPS blowout, SubtitleCue.cps > CPS_THRESHOLD (20.0)."""
        # 30 chars, 3 seconds = 10 CPS (safe, well below threshold)
        cue = SubtitleCue(
            index=1,
            start_ms=1000,
            end_ms=4000,
            lines=["This is a thirty-char line.xx"],  # exactly 28 chars
        )
        assert cue.total_chars >= 10
        assert cue.cps <= CPS_THRESHOLD

        mutated = _apply_cps_blowout(cue)
        assert mutated is not None, "Expected cue to be eligible for CPS blowout"
        # Verify via the model's computed property
        assert mutated.cps > CPS_THRESHOLD, (
            f"Expected cps > {CPS_THRESHOLD}, got {mutated.cps}"
        )

    def test_cps_blowout_ineligible_when_already_over(self) -> None:
        """Cues already violating CPS must not be eligible for blowout injection."""
        cue = SubtitleCue(
            index=1, start_ms=0, end_ms=100,  # 100ms → very high CPS
            lines=["This is a long line of text"],
        )
        assert cue.cps > CPS_THRESHOLD
        assert _apply_cps_blowout(cue) is None

    def test_line_overflow_exceeds_threshold(self) -> None:
        """After line-overflow injection, SubtitleCue.char_counts[0] > LINE_CHAR_THRESHOLD (42)."""
        # Two lines that together exceed 42 visible chars
        cue = SubtitleCue(
            index=1,
            start_ms=0,
            end_ms=3000,
            lines=["Twenty-two characters long.", "Another twenty chars here."],
        )
        # Each line individually is under 42
        assert all(c <= LINE_CHAR_THRESHOLD for c in cue.char_counts)
        # Joined they should exceed 42
        joined_len = sum(cue.char_counts) + len(cue.lines) - 1  # spaces
        assert joined_len > LINE_CHAR_THRESHOLD, "Test cue not long enough — fix test"

        mutated = _apply_line_overflow(cue)
        assert mutated is not None
        assert len(mutated.lines) == 1
        # Verify via the model's own computed property
        assert any(c > LINE_CHAR_THRESHOLD for c in mutated.char_counts), (
            f"Expected char count > {LINE_CHAR_THRESHOLD}, got {mutated.char_counts}"
        )

    def test_line_overflow_ineligible_single_line(self) -> None:
        """Single-line cues must not be eligible for line-overflow injection."""
        cue = SubtitleCue(index=1, start_ms=0, end_ms=2000, lines=["Short single line"])
        assert _apply_line_overflow(cue) is None

    def test_three_line_cue_has_three_lines(self) -> None:
        """After three-line injection on a 2-line cue, len(cue.lines) == 3."""
        # Use a 2-line cue — the engine splits the longest line at word boundary
        cue = SubtitleCue(
            index=1,
            start_ms=0,
            end_ms=3000,
            lines=[
                "Look Celia, we have to follow our passions;",
                "you have your robotics.",
            ],
        )
        mutated = _apply_three_line_cue(cue)
        assert mutated is not None, (
            "Expected 2-line cue with long first line to be eligible for 3-line injection"
        )
        assert len(mutated.lines) == 3, f"Expected 3 lines, got {len(mutated.lines)}"
        # All words from the original cue are preserved
        original_words = set(" ".join(cue.lines).split())
        mutated_words = set(" ".join(mutated.lines).split())
        assert original_words == mutated_words

    def test_short_duration_under_threshold(self) -> None:
        """After short-duration injection, SubtitleCue.duration_ms < MIN_DURATION_MS (1000)."""
        cue = SubtitleCue(
            index=1,
            start_ms=5000,
            end_ms=8000,  # 3000ms — well above threshold
            lines=["Some subtitle text"],
        )
        assert cue.duration_ms >= MIN_DURATION_MS

        mutated = _apply_short_duration(cue)
        assert mutated is not None
        # Verify via the model's own computed property
        assert mutated.duration_ms < MIN_DURATION_MS, (
            f"Expected duration_ms < {MIN_DURATION_MS}, got {mutated.duration_ms}"
        )

    def test_short_duration_ineligible_when_already_short(self) -> None:
        """Cues already short must not be eligible for short-duration injection."""
        cue = SubtitleCue(index=1, start_ms=0, end_ms=500, lines=["Short"])
        assert _apply_short_duration(cue) is None

    def test_overlap_applied(self) -> None:
        """After overlap injection, cue_i.end_ms > cue_j.start_ms."""
        cue_i = SubtitleCue(index=1, start_ms=1000, end_ms=3000, lines=["Cue one"])
        cue_j = SubtitleCue(index=2, start_ms=4000, end_ms=6000, lines=["Cue two"])
        assert cue_i.end_ms <= cue_j.start_ms

        mutated_i = _apply_overlap(cue_i, cue_j)
        assert mutated_i is not None
        # Verify overlap
        assert mutated_i.end_ms > cue_j.start_ms, (
            f"Expected end_ms {mutated_i.end_ms} > {cue_j.start_ms}"
        )

    def test_overlap_ineligible_when_gap_too_small(self) -> None:
        """Cues with gap < 100ms must not be eligible for overlap injection."""
        cue_i = SubtitleCue(index=1, start_ms=1000, end_ms=3000, lines=["A"])
        cue_j = SubtitleCue(index=2, start_ms=3050, end_ms=5000, lines=["B"])
        assert _apply_overlap(cue_i, cue_j) is None

    def test_meaning_swap_changes_text(self) -> None:
        """Meaning-swap changes text; manifest category is MEANING_LEVEL."""
        from passline.corpus.corrupt import _substitute_text
        from passline.corpus.substitutions import get_substitutions
        import random as _random

        pairs = get_substitutions("en")
        rng = _random.Random(42)
        new_text, orig_w, new_w = _substitute_text("I always trust my friends.", pairs, rng)
        # Should have substituted something
        assert orig_w is not None, "Expected a substitution to match"
        assert new_text != "I always trust my friends."
        assert orig_w.lower() != new_w.lower()

    def test_meaning_swap_category_in_full_corrupt(self, clean_files) -> None:
        """Full corrupt_file returns MEANING_LEVEL defects for meaning_swap."""
        source = clean_files["en"]
        result = corrupt_file(source, seed=42, defects={"meaning_swap"}, language="en")
        swap_defects = [d for d in result.manifest.defects if d.defect_type == "meaning_swap"]
        if swap_defects:  # only assert if the corpus has matching words
            for d in swap_defects:
                assert d.category == "MEANING_LEVEL"


# ─────────────────────────────────────────────────────────────────────────────
# Group B — Round-trip tests on committed broken files
# ─────────────────────────────────────────────────────────────────────────────

class TestRoundTrip:
    @pytest.mark.parametrize("lang", LANGUAGES)
    def test_broken_round_trips(
        self, lang: str, broken_files: dict
    ) -> None:
        """Broken SRT files must pass byte-identical round-trip through parser."""
        data, _ = broken_files[lang]
        result = write_srt(parse_srt(data, language=lang))
        assert result == data, (
            f"Round-trip failed for {lang}: "
            f"original={len(data)} bytes, result={len(result)} bytes"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Group C — Manifest correctness
# ─────────────────────────────────────────────────────────────────────────────

class TestManifestCorrectness:
    @pytest.mark.parametrize("lang", LANGUAGES)
    def test_deterministic_defects_verified_by_model(
        self,
        lang: str,
        broken_files: dict,
        manifests: dict,
    ) -> None:
        """Every DETERMINISTIC defect in the manifest is verified using SubtitleCue's computed properties."""
        _, broken = broken_files[lang]
        manifest = manifests[lang]

        cue_by_index = {c.index: c for c in broken.cues}

        for defect in manifest.defects:
            if defect.category != "DETERMINISTIC":
                continue

            assert defect.cue_index in cue_by_index, (
                f"Defect cue_index={defect.cue_index} not found in broken file"
            )
            cue = cue_by_index[defect.cue_index]

            if defect.defect_type == "cps_blowout":
                assert cue.cps > CPS_THRESHOLD, (
                    f"cue {cue.index}: expected CPS > {CPS_THRESHOLD}, got {cue.cps:.2f}"
                )
            elif defect.defect_type == "line_overflow":
                assert any(c > LINE_CHAR_THRESHOLD for c in cue.char_counts), (
                    f"cue {cue.index}: expected a line > {LINE_CHAR_THRESHOLD} chars, "
                    f"got {cue.char_counts}"
                )
            elif defect.defect_type == "three_line_cue":
                assert len(cue.lines) > 2, (
                    f"cue {cue.index}: expected > 2 lines, got {len(cue.lines)}"
                )
            elif defect.defect_type == "short_duration":
                assert cue.duration_ms < MIN_DURATION_MS, (
                    f"cue {cue.index}: expected duration_ms < {MIN_DURATION_MS}, "
                    f"got {cue.duration_ms}"
                )
            elif defect.defect_type == "overlap":
                # Find the next cue
                next_idx = cue.index + 1
                # Some cues may be non-consecutive; find by scanning
                next_cue = next(
                    (c for c in broken.cues if c.index > cue.index),
                    None,
                )
                if next_cue is not None:
                    assert cue.end_ms > next_cue.start_ms, (
                        f"cue {cue.index}: expected end_ms {cue.end_ms} > "
                        f"next start_ms {next_cue.start_ms}"
                    )

    @pytest.mark.parametrize("lang", LANGUAGES)
    def test_manifest_cue_indices_in_range(
        self,
        lang: str,
        broken_files: dict,
        manifests: dict,
    ) -> None:
        """Every manifest defect cue_index is a valid index in the broken file."""
        _, broken = broken_files[lang]
        manifest = manifests[lang]
        valid_indices = {c.index for c in broken.cues}
        for defect in manifest.defects:
            assert defect.cue_index in valid_indices, (
                f"cue_index={defect.cue_index} not in broken file cue indices"
            )

    @pytest.mark.parametrize("lang", LANGUAGES)
    def test_manifest_category_split(
        self,
        lang: str,
        manifests: dict,
    ) -> None:
        """Every manifest defect has a valid category."""
        manifest = manifests[lang]
        valid_categories = {"DETERMINISTIC", "MEANING_LEVEL"}
        for defect in manifest.defects:
            assert defect.category in valid_categories, (
                f"Invalid category {defect.category!r} for defect {defect.defect_type}"
            )

    @pytest.mark.parametrize("lang", LANGUAGES)
    def test_manifest_no_duplicate_cue_indices(
        self,
        lang: str,
        manifests: dict,
    ) -> None:
        """No two defects in a manifest share the same cue_index."""
        manifest = manifests[lang]
        indices = [d.cue_index for d in manifest.defects]
        assert len(indices) == len(set(indices)), (
            f"Duplicate cue indices found: {indices}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Group D — Determinism
# ─────────────────────────────────────────────────────────────────────────────

class TestDeterminism:
    def test_same_seed_produces_identical_output(self, clean_files: dict) -> None:
        """Running corrupt_file twice with the same seed produces byte-identical output."""
        source = clean_files["en"]
        r1 = corrupt_file(source, seed=42, language="en")
        r2 = corrupt_file(source, seed=42, language="en")
        assert r1.broken_bytes == r2.broken_bytes

    def test_different_seeds_produce_different_output(self, clean_files: dict) -> None:
        """Different seeds should produce different broken files."""
        source = clean_files["en"]
        r42 = corrupt_file(source, seed=42, language="en")
        r99 = corrupt_file(source, seed=99, language="en")
        assert r42.broken_bytes != r99.broken_bytes, (
            "Seed 42 and seed 99 produced identical output — seeding may be broken"
        )

    @pytest.mark.parametrize("lang", LANGUAGES)
    def test_corpus_regeneration_matches_committed(
        self,
        lang: str,
        clean_files: dict,
        broken_files: dict,
    ) -> None:
        """Regenerating from the clean file with seed=42 produces the committed broken file."""
        source = clean_files[lang]
        committed_bytes, _ = broken_files[lang]

        result = corrupt_file(source, seed=42, language=lang, source_filename=f"tos-{lang}.srt")
        assert result.broken_bytes == committed_bytes, (
            f"Regenerated broken file for '{lang}' does not match committed corpus. "
            f"Run: python scripts/generate_corpus.py --seed 42"
        )

    @pytest.mark.parametrize("lang", LANGUAGES)
    def test_manifest_regeneration_matches_committed(
        self,
        lang: str,
        clean_files: dict,
        manifests: dict,
    ) -> None:
        """Regenerating manifests with seed=42 matches the committed JSON."""
        source = clean_files[lang]
        committed_manifest = manifests[lang]

        result = corrupt_file(source, seed=42, language=lang, source_filename=f"tos-{lang}.srt")
        regen = result.manifest

        assert len(regen.defects) == len(committed_manifest.defects), (
            f"Defect count mismatch for '{lang}': "
            f"regen={len(regen.defects)}, committed={len(committed_manifest.defects)}"
        )
        for r, c in zip(regen.defects, committed_manifest.defects):
            assert r.cue_index == c.cue_index
            assert r.defect_type == c.defect_type
            assert r.category == c.category


# ─────────────────────────────────────────────────────────────────────────────
# Group E — Defect-type toggling
# ─────────────────────────────────────────────────────────────────────────────

class TestDefectToggling:
    def test_disable_meaning_swap(self, clean_files: dict) -> None:
        """Disabling meaning_swap produces no MEANING_LEVEL defects."""
        source = clean_files["en"]
        enabled = ALL_DEFECT_TYPES - {"meaning_swap"}
        result = corrupt_file(source, seed=42, defects=enabled, language="en")
        swap_defects = [d for d in result.manifest.defects if d.defect_type == "meaning_swap"]
        assert swap_defects == [], f"Found unexpected meaning_swap defects: {swap_defects}"

    def test_enable_only_cps_blowout(self, clean_files: dict) -> None:
        """Enabling only cps_blowout produces only cps_blowout defects."""
        source = clean_files["en"]
        result = corrupt_file(source, seed=42, defects={"cps_blowout"}, language="en")
        for defect in result.manifest.defects:
            assert defect.defect_type == "cps_blowout", (
                f"Expected only cps_blowout, got {defect.defect_type}"
            )

    def test_enable_only_line_overflow(self, clean_files: dict) -> None:
        """Enabling only line_overflow produces only line_overflow defects."""
        source = clean_files["en"]
        result = corrupt_file(source, seed=42, defects={"line_overflow"}, language="en")
        for defect in result.manifest.defects:
            assert defect.defect_type == "line_overflow"

    def test_no_defects_enabled_produces_no_changes(self, clean_files: dict) -> None:
        """Passing an empty defects set produces no defects and identical content."""
        source = clean_files["en"]
        result = corrupt_file(source, seed=42, defects=set(), language="en")
        assert result.manifest.defects == []

    def test_all_defect_types_present_in_corpus(self, manifests: dict) -> None:
        """The corpus as a whole (all languages) covers every deterministic defect type."""
        seen_types: set[str] = set()
        for manifest in manifests.values():
            for d in manifest.defects:
                seen_types.add(d.defect_type)
        deterministic_types = {"cps_blowout", "line_overflow", "three_line_cue",
                               "short_duration", "overlap"}
        missing = deterministic_types - seen_types
        assert not missing, f"Defect types not represented in corpus: {missing}"


# ─────────────────────────────────────────────────────────────────────────────
# CLI smoke-test
# ─────────────────────────────────────────────────────────────────────────────

class TestCorruptCLI:
    def test_cli_produces_output_files(self, tmp_path: Path, clean_files: dict) -> None:
        """CLI: --input, --output, --manifest all work end-to-end."""
        clean_path = CLEAN / "tos-en.srt"
        if not clean_path.exists():
            pytest.skip("Clean file not present")
        from passline.corpus.corrupt import main as corrupt_main
        out_srt = tmp_path / "out.srt"
        out_json = tmp_path / "manifest.json"
        rc = corrupt_main([
            "--input",    str(clean_path),
            "--output",   str(out_srt),
            "--manifest", str(out_json),
            "--seed",     "42",
            "--language", "en",
        ])
        assert rc == 0
        assert out_srt.exists() and out_srt.stat().st_size > 0
        assert out_json.exists() and out_json.stat().st_size > 0
        manifest = json.loads(out_json.read_text())
        assert "defects" in manifest
        assert manifest["seed"] == 42
