"""Per-language meaning-swap word lists for the corruption engine.

Each entry is (original, replacement).  The engine applies these case-
insensitively and preserves the capitalisation of the original token.
"""
from __future__ import annotations

# Keys are BCP-47 language codes or their two-letter prefixes.
SUBSTITUTIONS: dict[str, list[tuple[str, str]]] = {
    "en": [
        ("always",    "never"),
        ("never",     "always"),
        ("love",      "hate"),
        ("hate",      "love"),
        ("friend",    "enemy"),
        ("enemy",     "friend"),
        ("begin",     "end"),
        ("end",       "begin"),
        ("open",      "close"),
        ("close",     "open"),
        ("right",     "wrong"),
        ("wrong",     "right"),
        ("safe",      "dangerous"),
        ("remember",  "forget"),
        ("forget",    "remember"),
        ("trust",     "distrust"),
        ("win",       "lose"),
        ("lose",      "win"),
        ("save",      "destroy"),
        ("protect",   "abandon"),
    ],
    "fr": [
        ("toujours",    "jamais"),
        ("jamais",      "toujours"),
        ("ami",         "ennemi"),
        ("ennemi",      "ami"),
        ("ouvrir",      "fermer"),
        ("fermer",      "ouvrir"),
        ("commencer",   "terminer"),
        ("terminer",    "commencer"),
        ("souvenir",    "oublier"),
        ("oublier",     "souvenir"),
        ("aimer",       "détester"),
        ("protéger",    "abandonner"),
        ("gagner",      "perdre"),
        ("perdre",      "gagner"),
        ("sauver",      "détruire"),
    ],
    "de": [
        ("immer",       "niemals"),
        ("niemals",     "immer"),
        ("Freund",      "Feind"),
        ("Feind",       "Freund"),
        ("öffnen",      "schließen"),
        ("schließen",   "öffnen"),
        ("beginnen",    "beenden"),
        ("beenden",     "beginnen"),
        ("erinnern",    "vergessen"),
        ("vergessen",   "erinnern"),
        ("lieben",      "hassen"),
        ("hassen",      "lieben"),
        ("gewinnen",    "verlieren"),
        ("verlieren",   "gewinnen"),
        ("schützen",    "verraten"),
    ],
}


def get_substitutions(language: str) -> list[tuple[str, str]]:
    """Return the substitution list for a language code.

    Falls back to English if the language is not found.
    Tries the two-letter prefix (e.g. 'en-US' → 'en').
    """
    if language in SUBSTITUTIONS:
        return SUBSTITUTIONS[language]
    prefix = language.split("-")[0].split("_")[0].lower()
    return SUBSTITUTIONS.get(prefix, SUBSTITUTIONS["en"])
