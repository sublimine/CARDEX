"""
Nominatim geocoding — free, open data, no API key.

Respects Nominatim's Usage Policy: 1 request per second max, identifying
User-Agent required. The module is a thin async wrapper around the public
endpoint; caller supplies its own httpx.AsyncClient.

https://operations.osmfoundation.org/policies/nominatim/
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

log = logging.getLogger(__name__)

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "CARDEX/1.0 (dealer discovery; ops@cardex.io)"
_MIN_INTERVAL = 1.1  # seconds between requests (ToS: ≤1 req/sec)


class Nominatim:
    """Thin async wrapper with built-in 1 req/sec throttle."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def geocode(
        self,
        *,
        address: str | None = None,
        city: str | None = None,
        postcode: str | None = None,
        country: str | None = None,
    ) -> Optional[tuple[float, float]]:
        """
        Geocode a postal address to (lat, lng). Returns None on miss or error.
        """
        parts = [p for p in (address, postcode, city, country) if p]
        if not parts:
            return None

        await self._throttle()

        try:
            resp = await self._client.get(
                _NOMINATIM_URL,
                params={
                    "q": ", ".join(parts),
                    "format": "json",
                    "limit": "1",
                    "addressdetails": "0",
                },
                headers={"User-Agent": _USER_AGENT},
                timeout=10.0,
            )
            if resp.status_code != 200:
                return None
            results = resp.json()
        except Exception as exc:
            log.debug("nominatim: geocode failed: %s", exc)
            return None

        if not results:
            return None
        try:
            return float(results[0]["lat"]), float(results[0]["lon"])
        except (KeyError, TypeError, ValueError):
            return None

    async def _throttle(self) -> None:
        async with self._lock:
            loop = asyncio.get_event_loop()
            now = loop.time()
            wait = _MIN_INTERVAL - (now - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = loop.time()
