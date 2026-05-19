"""
Intent Engine — buyer personas + navigation plans para sesiones humanas.

Cada sesión de scraping NO empieza directamente en la URL de búsqueda.
Sigue un plan de navegación que imita un comprador real de coches.

20 buyer personas por país (100 total EU).
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

import random
from dataclasses import dataclass, field
from typing import Callable


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


# 20 personas per country — defined at implementation time
PERSONAS: dict[str, list[BuyerPersona]] = {
    "DE": [],
    "ES": [],
    "FR": [],
    "NL": [],
    "BE": [],
    "CH": [],
}


def pick_persona(country: str) -> BuyerPersona:
    """Pick a random persona for the country."""
    personas = PERSONAS.get(country, [])
    if not personas:
        raise ValueError(f"No personas defined for country={country}")
    return random.choice(personas)


def build_plan(persona: BuyerPersona, portal_domain: str) -> SessionPlan:
    """
    Build a full navigation plan for one scraping session.
    Steps follow the ENTRY→LANDING→SEARCH→BROWSE→EXTRACT→EXIT flow.
    Dwell times and click patterns derived from persona profile.
    """
    raise NotImplementedError
