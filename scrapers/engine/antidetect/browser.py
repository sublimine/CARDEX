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
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from scrapers.engine.identity.profile import Identity

log = logging.getLogger(__name__)


def proxy_dict_from_url(url: str | None) -> dict | None:
    """
    Translate an identity proxy URL into a Playwright/Camoufox proxy dict.

    "http://user:pass@host:port" → {"server": "http://host:port",
                                     "username": "user", "password": "pass"}
    Returns None for an empty/unparseable URL (direct connection).
    """
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.hostname:
        return None
    scheme = parsed.scheme or "http"
    server = f"{scheme}://{parsed.hostname}"
    if parsed.port:
        server = f"{server}:{parsed.port}"
    out: dict = {"server": server}
    if parsed.username:
        out["username"] = parsed.username
    if parsed.password:
        out["password"] = parsed.password
    return out


@dataclass
class BrowserSlot:
    identity: Identity
    browser: Any           # camoufox.AsyncCamoufox entered browser
    page: Any | None       # active page or None if idle
    domain: str = ""
    in_use: bool = False
    cm: Any = None         # the AsyncCamoufox context manager (for __aexit__)


class CamoufoxPool:
    """
    Pool de instancias Camoufox para uso concurrente por el coordinator.
    Máximo pool_size instancias activas simultáneamente.

    A slot is bound to an identity (= one Firefox fingerprint) and reused across
    sessions for that identity. When the pool is full of in-use slots, acquire()
    blocks on a Condition until a slot is released. An idle slot of a *different*
    identity is evicted (closed) to make room before launching a new one.
    """

    def __init__(self, pool_size: int = 8) -> None:
        self.pool_size = pool_size
        self._slots: list[BrowserSlot] = []
        self._cond = asyncio.Condition()

    async def _launch(self, identity: Identity, domain: str) -> BrowserSlot:
        """
        Real Camoufox launch (integration seam — monkeypatched in unit tests).
        Camoufox applies the Firefox fingerprint natively; geoip aligns
        locale/timezone/WebRTC with the proxy IP when a proxy is set.
        """
        from camoufox.async_api import AsyncCamoufox

        proxy = proxy_dict_from_url(identity.proxy_ip)
        cm = AsyncCamoufox(headless=True, geoip=proxy is not None, proxy=proxy)
        browser = await cm.__aenter__()
        page = await browser.new_page()
        log.debug("launched camoufox slot identity=%s domain=%s", identity.id, domain)
        return BrowserSlot(
            identity=identity, browser=browser, page=page,
            domain=domain, in_use=True, cm=cm,
        )

    async def _shutdown(self, slot: BrowserSlot) -> None:
        """Close one slot's browser (integration seam). Never raises."""
        if slot.cm is None:
            return
        try:
            await slot.cm.__aexit__(None, None, None)
        except Exception as exc:  # browser teardown is best-effort
            log.warning("error closing slot identity=%s: %s", slot.identity.id, exc)

    async def acquire(self, identity: Identity, domain: str) -> BrowserSlot:
        """
        Get an idle slot for this identity+domain, or create a new one.
        Blocks if pool is full and all slots are in use.
        Injects identity.fingerprint into Camoufox at launch.
        """
        async with self._cond:
            while True:
                for slot in self._slots:
                    if not slot.in_use and slot.identity.id == identity.id:
                        slot.in_use = True
                        slot.domain = domain
                        return slot
                if len(self._slots) < self.pool_size:
                    slot = await self._launch(identity, domain)
                    self._slots.append(slot)
                    return slot
                idle = next((s for s in self._slots if not s.in_use), None)
                if idle is not None:
                    self._slots.remove(idle)
                    await self._shutdown(idle)
                    slot = await self._launch(identity, domain)
                    self._slots.append(slot)
                    return slot
                await self._cond.wait()

    async def release(self, slot: BrowserSlot) -> None:
        """Mark slot as idle. Does not close the browser — reuse next session."""
        async with self._cond:
            slot.in_use = False
            slot.domain = ""
            self._cond.notify()

    async def close_all(self) -> None:
        """Graceful shutdown. Close all browser instances."""
        async with self._cond:
            slots = list(self._slots)
            self._slots.clear()
        for slot in slots:
            await self._shutdown(slot)
        async with self._cond:
            self._cond.notify_all()
