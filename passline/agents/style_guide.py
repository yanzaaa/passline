from __future__ import annotations

# Passline Bundled Example House Style Guide citations for the dashboard (never mentions any streamer names)
STYLE_GUIDE_CITATIONS: dict[tuple[str, str], dict[str, str]] = {
    # (rule_ref, language_prefix)
    ("MT01", "en"): {
        "rule_ref": "MT01",
        "language": "en",
        "rule_name": "Mistranslation",
        "citation": "Netflix Timed Text Style Guide - General Requirements (https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617)",
    },
    ("MT01", "fr"): {
        "rule_ref": "MT01",
        "language": "fr",
        "rule_name": "Contre-sens",
        "citation": "Netflix French Timed Text Style Guide (https://partnerhelp.netflixstudios.com/hc/en-us/articles/215339368)",
    },
    ("MT01", "de"): {
        "rule_ref": "MT01",
        "language": "de",
        "rule_name": "Sinnfehler",
        "citation": "Netflix German Timed Text Style Guide (https://partnerhelp.netflixstudios.com/hc/en-us/articles/215759167)",
    },
    ("MT02", "en"): {
        "rule_ref": "MT02",
        "language": "en",
        "rule_name": "Tone and Register",
        "citation": "Netflix Timed Text Style Guide - General Requirements (https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617)",
    },
    ("MT02", "fr"): {
        "rule_ref": "MT02",
        "language": "fr",
        "rule_name": "Niveau de langue",
        "citation": "Netflix French Timed Text Style Guide (https://partnerhelp.netflixstudios.com/hc/en-us/articles/215339368)",
    },
    ("MT02", "de"): {
        "rule_ref": "MT02",
        "language": "de",
        "rule_name": "Tonfall",
        "citation": "Netflix German Timed Text Style Guide (https://partnerhelp.netflixstudios.com/hc/en-us/articles/215759167)",
    },
    ("MT03", "en"): {
        "rule_ref": "MT03",
        "language": "en",
        "rule_name": "Spelling and Grammar",
        "citation": "Netflix Timed Text Style Guide - General Requirements (https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617)",
    },
    ("MT03", "fr"): {
        "rule_ref": "MT03",
        "language": "fr",
        "rule_name": "Orthographe et Grammaire",
        "citation": "Netflix French Timed Text Style Guide (https://partnerhelp.netflixstudios.com/hc/en-us/articles/215339368)",
    },
    ("MT03", "de"): {
        "rule_ref": "MT03",
        "language": "de",
        "rule_name": "Rechtschreibung und Grammatik",
        "citation": "Netflix German Timed Text Style Guide (https://partnerhelp.netflixstudios.com/hc/en-us/articles/215759167)",
    },
    ("MT04", "en"): {
        "rule_ref": "MT04",
        "language": "en",
        "rule_name": "Inconsistency",
        "citation": "Netflix Timed Text Style Guide - General Requirements (https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617)",
    },
    ("MT04", "fr"): {
        "rule_ref": "MT04",
        "language": "fr",
        "rule_name": "Incohérence",
        "citation": "Netflix French Timed Text Style Guide (https://partnerhelp.netflixstudios.com/hc/en-us/articles/215339368)",
    },
    ("MT04", "de"): {
        "rule_ref": "MT04",
        "language": "de",
        "rule_name": "Inkonsistenz",
        "citation": "Netflix German Timed Text Style Guide (https://partnerhelp.netflixstudios.com/hc/en-us/articles/215759167)",
    },
    ("MT05", "en"): {
        "rule_ref": "MT05",
        "language": "en",
        "rule_name": "Offensive Language",
        "citation": "Netflix Timed Text Style Guide - General Requirements (https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617)",
    },
    ("MT05", "fr"): {
        "rule_ref": "MT05",
        "language": "fr",
        "rule_name": "Langage offensant",
        "citation": "Netflix French Timed Text Style Guide (https://partnerhelp.netflixstudios.com/hc/en-us/articles/215339368)",
    },
    ("MT05", "de"): {
        "rule_ref": "MT05",
        "language": "de",
        "rule_name": "Anstößige Sprache",
        "citation": "Netflix German Timed Text Style Guide (https://partnerhelp.netflixstudios.com/hc/en-us/articles/215759167)",
    },
    ("MT06", "en"): {
        "rule_ref": "MT06",
        "language": "en",
        "rule_name": "Formatting tags",
        "citation": "Netflix Timed Text Style Guide - General Requirements (https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617)",
    },
    ("MT06", "fr"): {
        "rule_ref": "MT06",
        "language": "fr",
        "rule_name": "Balises de format",
        "citation": "Netflix French Timed Text Style Guide (https://partnerhelp.netflixstudios.com/hc/en-us/articles/215339368)",
    },
    ("MT06", "de"): {
        "rule_ref": "MT06",
        "language": "de",
        "rule_name": "Formatierungs-Tags",
        "citation": "Netflix German Timed Text Style Guide (https://partnerhelp.netflixstudios.com/hc/en-us/articles/215759167)",
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
            "citation": f"Netflix Timed Text Style Guide - General Requirements (https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617)",
        }
    return citation
