"""
Session conditioning — homepage → search → browse ANTES de extraer.

Sin conditioning, Akamai detecta sesión de extracción directa en 2-3 páginas.
Con conditioning, el primer request llega con cookies reales + historial de navegación.

Protocolo por sesión (derivado del Intent Engine):
  1. Cargar storageState del dominio (cookies previas si existen)
  2. Navegar a homepage con Referer de Google
  3. Dwell + scroll orgánico (3-8s)
  4. Aplicar filtros de búsqueda (persona params)
  5. Navegar página 1 de resultados (dwell 5-15s)
  6. Click en 1-2 listings al azar (dwell 15-40s, back button)
  7. → AHORA empezar extracción (intercept_paginate / dom_paginate)

Conexión con pw_base.py: conditioning opera sobre el mismo browser/page
  que luego usará intercept_paginate. No cierres el browser entre conditioning y extracción.
"""
from __future__ import annotations

import logging
from typing import Any

from scrapers.engine.session.intent import BuyerPersona, build_plan

log = logging.getLogger(__name__)


async def condition_session(
    page: Any,             # Camoufox page (ya con storageState cargado)
    domain: str,
    persona: BuyerPersona,
    portal_base_url: str,
) -> None:
    """
    Run the conditioning flow on the given page before extraction starts.
    Page must already have storageState injected (session/state.py).
    On return: page is at the search results page, ready for intercept_paginate.
    """
    raise NotImplementedError
