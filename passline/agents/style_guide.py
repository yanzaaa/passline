from __future__ import annotations

# Timed-Text Style Guide citations for the dashboard (never mentions any streamer names)
STYLE_GUIDE_CITATIONS: dict[tuple[str, str], dict[str, str]] = {
    # (rule_ref, language_prefix)
    ("MT01", "en"): {
        "rule_ref": "MT01",
        "language": "en",
        "rule_name": "Mistranslation",
        "citation": "Timed-Text Style Guide (EN), Section 3.1.2: Meaning and Accuracy",
    },
    ("MT01", "fr"): {
        "rule_ref": "MT01",
        "language": "fr",
        "rule_name": "Contre-sens",
        "citation": "Timed-Text Style Guide (FR), Section 2.4.1: Contre-sens et faux-amis",
    },
    ("MT01", "de"): {
        "rule_ref": "MT01",
        "language": "de",
        "rule_name": "Sinnfehler",
        "citation": "Timed-Text Style Guide (DE), Sektion 4.1.3: Sinnentstellung und Genauigkeit",
    },
    ("MT02", "en"): {
        "rule_ref": "MT02",
        "language": "en",
        "rule_name": "Tone and Register",
        "citation": "Timed-Text Style Guide (EN), Section 3.2.1: Character Voice and Register",
    },
    ("MT02", "fr"): {
        "rule_ref": "MT02",
        "language": "fr",
        "rule_name": "Niveau de langue",
        "citation": "Timed-Text Style Guide (FR), Section 2.5.3: Registre et ton du personnage",
    },
    ("MT02", "de"): {
        "rule_ref": "MT02",
        "language": "de",
        "rule_name": "Tonfall",
        "citation": "Timed-Text Style Guide (DE), Sektion 4.2.1: Tone und Register",
    },
    ("MT03", "en"): {
        "rule_ref": "MT03",
        "language": "en",
        "rule_name": "Spelling and Grammar",
        "citation": "Timed-Text Style Guide (EN), Section 1.1: Standard Orthography",
    },
    ("MT03", "fr"): {
        "rule_ref": "MT03",
        "language": "fr",
        "rule_name": "Orthographe et Grammaire",
        "citation": "Timed-Text Style Guide (FR), Section 1.1: Orthographe d'usage",
    },
    ("MT03", "de"): {
        "rule_ref": "MT03",
        "language": "de",
        "rule_name": "Rechtschreibung und Grammatik",
        "citation": "Timed-Text Style Guide (DE), Sektion 1.1: Orthografie und Grammatik",
    },
    ("MT04", "en"): {
        "rule_ref": "MT04",
        "language": "en",
        "rule_name": "Inconsistency",
        "citation": "Timed-Text Style Guide (EN), Section 3.4.2: Consistency of Terminology",
    },
    ("MT04", "fr"): {
        "rule_ref": "MT04",
        "language": "fr",
        "rule_name": "Incohérence",
        "citation": "Timed-Text Style Guide (FR), Section 2.6.4: Cohérence de la terminologie",
    },
    ("MT04", "de"): {
        "rule_ref": "MT04",
        "language": "de",
        "rule_name": "Inkonsistenz",
        "citation": "Timed-Text Style Guide (DE), Sektion 4.3.1: Konsistenz der Terminologie",
    },
    ("MT05", "en"): {
        "rule_ref": "MT05",
        "language": "en",
        "rule_name": "Offensive Language",
        "citation": "Timed-Text Style Guide (EN), Section 3.5.1: Profanity and Sensitive Content",
    },
    ("MT05", "fr"): {
        "rule_ref": "MT05",
        "language": "fr",
        "rule_name": "Langage offensant",
        "citation": "Timed-Text Style Guide (FR), Section 2.7.1: Vulgarités et termes sensibles",
    },
    ("MT05", "de"): {
        "rule_ref": "MT05",
        "language": "de",
        "rule_name": "Anstößige Sprache",
        "citation": "Timed-Text Style Guide (DE), Sektion 4.4.2: Vulgär- und Fäkalsprache",
    },
    ("MT06", "en"): {
        "rule_ref": "MT06",
        "language": "en",
        "rule_name": "Formatting tags",
        "citation": "Timed-Text Style Guide (EN), Section 1.5.3: Italic and Format Tags",
    },
    ("MT06", "fr"): {
        "rule_ref": "MT06",
        "language": "fr",
        "rule_name": "Balises de format",
        "citation": "Timed-Text Style Guide (FR), Section 1.4.2: Italiques et balises typographiques",
    },
    ("MT06", "de"): {
        "rule_ref": "MT06",
        "language": "de",
        "rule_name": "Formatierungs-Tags",
        "citation": "Timed-Text Style Guide (DE), Sektion 1.5.1: Kursivschrift und Format-Tags",
    },
}


def get_citation(rule_ref: str, language: str) -> dict[str, str]:
    """Get style guide citation for a given rule and language prefix."""
    lang_prefix = language.split("-")[0].split("_")[0].lower()
    citation = STYLE_GUIDE_CITATIONS.get((rule_ref, lang_prefix))
    if citation is None:
        # Fallback to English
        citation = STYLE_GUIDE_CITATIONS.get((rule_ref, "en"))
    if citation is None:
        # Generic fallback
        citation = {
            "rule_ref": rule_ref,
            "language": language,
            "rule_name": "Style Guide Rule",
            "citation": f"Timed-Text Style Guide, Rule {rule_ref}",
        }
    return citation
