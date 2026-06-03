"""
Intent Engine — buyer personas + navigation plans para sesiones humanas.

Cada sesión de scraping NO empieza directamente en la URL de búsqueda.
Sigue un plan de navegación que imita un comprador real de coches.

20 buyer personas por país (120 total, 6 países).
Cada persona tiene: entry_point, search_params, comportamiento de click/dwell/back.

Plan de navegación por sesión:
  1. ENTRY:   URL con Referer de Google Search real por país
  2. LANDING: homepage del portal + dwell + scroll orgánico
  3. SEARCH:  aplicar filtros del portal o URL con params
  4. BROWSE:  páginas con dwell, click-through, back button, comparación
             → EXTRACT URLs de paso (no secuencial obvio)
  5. EXIT:    navegar fuera del portal antes de cerrar el browser

Sin este protocolo → Akamai detecta sesión de extracción en 2-3 páginas.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from urllib.parse import quote_plus


@dataclass
class BuyerPersona:
    id: str
    country: str
    search_params: dict              # {make?, model?, year_min?, year_max?, budget?, fuel?}
    entry_point: str                 # "google_search"|"direct"|"bookmark"
    max_pages: int = 0               # randint(2,9) at session time
    click_through_rate: float = 0.25
    comparison_rate: float = 0.40
    back_button_rate: float = 0.60
    listing_dwell_s: tuple[int, int] = (15, 90)
    results_dwell_s: tuple[int, int] = (5, 25)
    between_page_s: tuple[int, int] = (3, 12)
    uses_filters: bool = True


@dataclass
class NavigationStep:
    action: str          # "navigate"|"scroll"|"click"|"wait"|"back"|"extract"
    url: str | None = None
    selector: str | None = None
    dwell_s: float = 0.0
    referer: str | None = None


@dataclass
class SessionPlan:
    persona: BuyerPersona
    steps: list[NavigationStep] = field(default_factory=list)
    extract_after_step: int = 0      # Which step index to start extracting URLs


# Per-market vocabulary: top-selling make→models, Google ccTLD, and the
# local-language used-car query suffix. Pools are curated from real European
# market leaders so generated search intent is statistically plausible.
_MARKET: dict[str, dict] = {
    "DE": {
        "tld": "de", "suffix": "gebraucht kaufen",
        "models": {
            "Volkswagen": ["Golf", "Passat", "Polo", "Tiguan"],
            "BMW": ["3er", "5er", "X1"],
            "Mercedes-Benz": ["C-Klasse", "A-Klasse", "E-Klasse"],
            "Audi": ["A3", "A4", "A6"],
            "Opel": ["Astra", "Corsa"],
            "Ford": ["Focus", "Fiesta"],
        },
    },
    "ES": {
        "tld": "es", "suffix": "de segunda mano",
        "models": {
            "SEAT": ["León", "Ibiza", "Ateca"],
            "Renault": ["Clio", "Mégane"],
            "Peugeot": ["208", "308"],
            "Volkswagen": ["Golf", "Polo"],
            "Citroën": ["C3", "C4"],
            "Dacia": ["Sandero", "Duster"],
        },
    },
    "FR": {
        "tld": "fr", "suffix": "occasion",
        "models": {
            "Renault": ["Clio", "Mégane", "Captur"],
            "Peugeot": ["208", "308", "3008"],
            "Citroën": ["C3", "C4"],
            "Dacia": ["Sandero", "Duster"],
            "Volkswagen": ["Golf", "Polo"],
            "Toyota": ["Yaris", "Corolla"],
        },
    },
    "NL": {
        "tld": "nl", "suffix": "occasion kopen",
        "models": {
            "Volkswagen": ["Golf", "Polo", "Up"],
            "Opel": ["Corsa", "Astra"],
            "Renault": ["Clio", "Captur"],
            "Peugeot": ["208", "308"],
            "Toyota": ["Yaris", "Aygo"],
            "Kia": ["Picanto", "Ceed"],
        },
    },
    "BE": {
        "tld": "be", "suffix": "tweedehands",
        "models": {
            "Volkswagen": ["Golf", "Polo"],
            "BMW": ["1er", "3er"],
            "Audi": ["A1", "A3"],
            "Renault": ["Clio", "Mégane"],
            "Peugeot": ["208", "308"],
            "Škoda": ["Octavia", "Fabia"],
        },
    },
    "CH": {
        "tld": "ch", "suffix": "occasion kaufen",
        "models": {
            "Volkswagen": ["Golf", "Tiguan"],
            "BMW": ["3er", "X3"],
            "Audi": ["A4", "Q5"],
            "Mercedes-Benz": ["C-Klasse", "GLC"],
            "Škoda": ["Octavia", "Superb"],
            "Volvo": ["XC60", "V60"],
        },
    },
}

_FUELS = ["petrol", "diesel", "hybrid", "electric", "lpg"]
_YEAR_MINS = [2014, 2016, 2018, 2020]
_BUDGETS = [8000, 12000, 15000, 20000, 25000, 30000, 40000, 60000]
_PERSONAS_PER_COUNTRY = 20


def _persona_rng(country: str) -> random.Random:
    """Deterministic RNG per country — persona pools are stable across runs."""
    digest = hashlib.sha256(f"cardex-persona-{country}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _pick_entry_point(rng: random.Random) -> str:
    """google_search 70% / direct 20% / bookmark 10%."""
    roll = rng.random()
    if roll < 0.70:
        return "google_search"
    if roll < 0.90:
        return "direct"
    return "bookmark"


def _make_search_params(rng: random.Random, models: dict[str, list[str]]) -> dict:
    """Coherent {make, model?, year_min, year_max?, budget, fuel?} intent."""
    make = rng.choice(list(models))
    params: dict = {"make": make, "year_min": rng.choice(_YEAR_MINS), "budget": rng.choice(_BUDGETS)}
    if rng.random() < 0.70:
        params["model"] = rng.choice(models[make])
    if rng.random() < 0.30:
        params["year_max"] = params["year_min"] + rng.choice([3, 4, 5])
    if rng.random() < 0.60:
        params["fuel"] = rng.choice(_FUELS)
    return params


def _build_personas(country: str) -> list[BuyerPersona]:
    """Generate the deterministic 20-persona pool for one country."""
    rng = _persona_rng(country)
    models = _MARKET[country]["models"]
    personas: list[BuyerPersona] = []
    for i in range(_PERSONAS_PER_COUNTRY):
        personas.append(
            BuyerPersona(
                id=f"{country}-{i:02d}",
                country=country,
                search_params=_make_search_params(rng, models),
                entry_point=_pick_entry_point(rng),
                click_through_rate=round(rng.uniform(0.15, 0.35), 3),
                comparison_rate=round(rng.uniform(0.30, 0.50), 3),
                back_button_rate=round(rng.uniform(0.50, 0.70), 3),
                uses_filters=rng.random() < 0.70,
            )
        )
    return personas


PERSONAS: dict[str, list[BuyerPersona]] = {c: _build_personas(c) for c in _MARKET}


def pick_persona(country: str, rng: random.Random | None = None) -> BuyerPersona:
    """Pick a random persona for the country."""
    personas = PERSONAS.get(country, [])
    if not personas:
        raise ValueError(f"No personas defined for country={country}")
    return (rng or random).choice(personas)


def _google_domain(country: str) -> str:
    return f"www.google.{_MARKET[country]['tld']}"


def _google_referer(persona: BuyerPersona) -> str:
    """Real Google search URL matching the persona's car intent."""
    sp = persona.search_params
    terms = [sp.get("make", ""), sp.get("model", ""), _MARKET[persona.country]["suffix"]]
    query = " ".join(t for t in terms if t)
    return f"https://{_google_domain(persona.country)}/search?q={quote_plus(query)}"


def _sample(rng: random.Random, bounds: tuple[int, int]) -> float:
    lo, hi = bounds
    return round(rng.uniform(lo, hi), 2)


def build_plan(
    persona: BuyerPersona, portal_domain: str, rng: random.Random | None = None
) -> SessionPlan:
    """
    Build a full navigation plan for one scraping session.
    Steps follow the ENTRY→LANDING→SEARCH→BROWSE→EXTRACT→EXIT flow.
    Dwell times and click patterns derived from persona profile.

    Portal-specific URLs (search results, pagination) are NOT fabricated here —
    those steps carry url=None and the executor (conditioning.py) supplies the
    real URL from the portal scraper's search_url_fn. Only intent-derivable URLs
    (homepage, Google referer, exit) are filled in. extract_after_step marks the
    first BROWSE step, where URL extraction begins.
    """
    rng = rng or random
    home = f"https://{portal_domain}/"
    referer = _google_referer(persona) if persona.entry_point == "google_search" else None

    steps: list[NavigationStep] = [
        NavigationStep("navigate", url=home, referer=referer, dwell_s=_sample(rng, persona.results_dwell_s)),
        NavigationStep("scroll", dwell_s=_sample(rng, persona.results_dwell_s)),
        NavigationStep("navigate", url=None, dwell_s=_sample(rng, persona.results_dwell_s)),
    ]
    extract_after_step = len(steps)  # BROWSE starts at the next appended step

    max_pages = rng.randint(2, 9)
    for page in range(max_pages):
        steps.append(NavigationStep("scroll", dwell_s=_sample(rng, persona.results_dwell_s)))
        if rng.random() < persona.click_through_rate:
            steps.append(NavigationStep("click", selector="listing", dwell_s=_sample(rng, persona.listing_dwell_s)))
            if rng.random() < persona.back_button_rate:
                steps.append(NavigationStep("back", dwell_s=_sample(rng, persona.between_page_s)))
        if page < max_pages - 1:
            steps.append(NavigationStep("navigate", url=None, dwell_s=_sample(rng, persona.between_page_s)))

    steps.append(
        NavigationStep("navigate", url=f"https://{_google_domain(persona.country)}/", dwell_s=_sample(rng, persona.between_page_s))
    )
    return SessionPlan(persona=persona, steps=steps, extract_after_step=extract_after_step)
