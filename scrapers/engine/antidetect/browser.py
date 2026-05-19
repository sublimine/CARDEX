"""
Camoufox instance pool — gestión del pool de browsers T2/T3.

Cada instancia Camoufox = una identidad = un Firefox fingerprint.
El pool mantiene N instancias activas reutilizables entre tareas.

Camoufox recibe el fingerprint de identity.fingerprint y lo aplica a nivel C++.
No necesita JS adicional — las señales browser son nativas de Firefox.

Conexión con pw_base.py:
  pw_base.py es el motor de PAGINACIÓN (intercept_paginate / dom_paginate).
  browser.py es el POOL que proporciona instancias a pw_base.py y al Intent Engine.
  pw_base.py puede operar sin pool (crea su propio browser por sesión).
  El pool es para el coordinator cuando gestiona múltiples sesiones concurrentes.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from scrapers.engine.identity.profile import Identity

log = logging.getLogger(__name__)


@dataclass
class BrowserSlot:
    identity: Identity
    browser: Any           # camoufox.AsyncCamoufox instance
    page: Any | None       # active page or None if idle
    domain: str = ""
    in_use: bool = False


class CamoufoxPool:
    """
    Pool de instancias Camoufox para uso concurrente por el coordinator.
    Máximo pool_size instancias activas simultáneamente.
    """

    def __init__(self, pool_size: int = 8) -> None:
        self.pool_size = pool_size
        self._slots: list[BrowserSlot] = []
        self._lock = asyncio.Lock()

    async def acquire(self, identity: Identity, domain: str) -> BrowserSlot:
        """
        Get an idle slot for this identity+domain, or create a new one.
        Blocks if pool is full and all slots are in use.
        Injects identity.fingerprint into Camoufox at launch.
        """
        raise NotImplementedError

    async def release(self, slot: BrowserSlot) -> None:
        """Mark slot as idle. Does not close the browser — reuse next session."""
        raise NotImplementedError

    async def close_all(self) -> None:
        """Graceful shutdown. Close all browser instances."""
        raise NotImplementedError
