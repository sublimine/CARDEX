"""
Consolidated dealer-term dictionary — one source of truth, correct dialect per country.

Registries that carry no reliable activity code (DE Handelsregister / OffeneRegister,
CH Zefix) can only isolate car dealers by NAME. The terms differ by the country's
language(s): German for DE, French for FR, Spanish for ES, Dutch for NL, Dutch+French
for BE, and German+French+Italian for CH. Before, these lived fragmented across
sources (blueprint P1-2 flagged the anti-DRY duplication + the missing CH Italian);
this is the single ``{country: {lang: [terms]}}`` table.

Registries that DO carry an activity code (FR NAF, ES CNAE, NL RDW recognition)
filter on the code instead and do not need these terms — but the table covers all
six so a name-fallback is available everywhere.

Matching is accent- and case-insensitive (a German Umlaut or a French accent must
not make a term miss).
"""
from __future__ import annotations

import unicodedata

# Per-country, per-language dealer/garage terms. Lowercase, unaccented at match time.
# NOTE: the bare token "auto" is deliberately EXCLUDED — it over-matches
# "Automation", "automatique", "automatización" (false positives observed live on
# CH Zefix). Only specific compounds (autohaus, automobile(s), autobedrijf,
# autofficina…) and unambiguous words (garage, concessionnaire, carrozzeria) are
# used, mirroring name_to_domain's _GENERIC exclusion.
DEALER_TERMS: dict[str, dict[str, tuple[str, ...]]] = {
    "DE": {"de": ("autohaus", "kfz", "automobile", "automobil", "autozentrum",
                  "autohandel", "gebrauchtwagen", "autohändler", "autosalon",
                  "fahrzeuge", "fahrzeughandel", "motors")},
    "FR": {"fr": ("garage", "automobiles", "automobile", "concessionnaire",
                  "vehicules", "carrosserie", "occasion", "concessionnaire")},
    "ES": {"es": ("concesionario", "automoviles", "automocion", "taller",
                  "vehiculos", "ocasion", "automotor", "autocentro",
                  "coches de ocasion", "coches usados")},
    "NL": {"nl": ("autobedrijf", "garage", "occasion", "garagebedrijf",
                  "automobielbedrijf", "autohandel", "autodealer",
                  "tweedehands auto", "occasions")},
    "BE": {
        "nl": ("autobedrijf", "garage", "occasion", "tweedehands", "autohandel",
               "garagebedrijf", "autodealer"),
        "fr": ("garage", "automobiles", "concessionnaire", "vehicules",
               "carrosserie", "occasion"),
    },
    "CH": {
        "de": ("autohaus", "garage", "automobile", "automobil", "autohandel",
               "autohändler", "gebrauchtwagen", "autosalon"),
        "fr": ("garage", "automobiles", "concessionnaire", "carrosserie",
               "occasion", "vehicules"),
        "it": ("autofficina", "carrozzeria", "concessionaria", "autosalone",
               "automobili", "garage"),
    },
}


def _norm(s: str) -> str:
    """Lowercase + strip accents for robust substring matching."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", (s or "").lower())
        if not unicodedata.combining(c)
    )


def terms_for(country: str) -> tuple[str, ...]:
    """All dealer terms for a country, flattened across its languages (deduped)."""
    langs = DEALER_TERMS.get((country or "").strip().upper(), {})
    seen: dict[str, None] = {}
    for terms in langs.values():
        for t in terms:
            seen[t] = None
    return tuple(seen)


def name_matches(name: str, country: str) -> bool:
    """True when a business name carries any of the country's dealer terms."""
    norm = _norm(name)
    if not norm:
        return False
    return any(_norm(t) in norm for t in terms_for(country))
