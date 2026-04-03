"""
ProxyManager — rotating proxy pool for anti-ban scraping.

Pool stored in Redis SET `proxy:pool` as pipe-separated strings:
    host:port:user:pass:country:protocol
    e.g. "gate.proxy.io:7000:user123:pass456:ES:http"

Dead proxies are moved to `proxy:dead` (ZSET, score = ban timestamp).
They are re-tried after DEAD_TTL_SECS. Geographic affinity is best-effort:
scraper requests a country code and the manager prefers proxies from
that country, falling back to any available proxy.

Usage:
    pm = ProxyManager(redis_client)
    await pm.load()
    proxy_url = await pm.get(country="ES")   # e.g. "http://user:pass@host:port"
    await pm.mark_dead(proxy_url)
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Optional

import structlog

log = structlog.get_logger()

DEAD_TTL_SECS = 1800  # re-try dead proxies after 30 min


@dataclass
class Proxy:
    host: str
    port: str
    user: str
    password: str
    country: str        # ISO 2-letter, lowercase
    protocol: str = "http"

    @classmethod
    def parse(cls, raw: str) -> Optional["Proxy"]:
        """Parse 'host:port:user:pass:country[:protocol]'."""
        try:
            parts = raw.strip().split(":")
            if len(parts) < 5:
                return None
            protocol = parts[5] if len(parts) > 5 else "http"
            return cls(
                host=parts[0],
                port=parts[1],
                user=parts[2],
                password=parts[3],
                country=parts[4].lower(),
                protocol=protocol,
            )
        except Exception:
            return None

    def as_url(self) -> str:
        if self.user and self.password:
            return f"{self.protocol}://{self.user}:{self.password}@{self.host}:{self.port}"
        return f"{self.protocol}://{self.host}:{self.port}"

    def raw(self) -> str:
        return f"{self.host}:{self.port}:{self.user}:{self.password}:{self.country}:{self.protocol}"


class ProxyManager:
    """
    Rotating proxy pool backed by Redis.
    Thread-safe via asyncio (single-threaded event loop per scraper process).
    """

    def __init__(self, redis_client: any) -> None:
        self._redis = redis_client
        self._proxies: list[Proxy] = []
        self._by_country: dict[str, list[Proxy]] = {}

    async def load(self) -> None:
        """Load proxy pool from Redis. Call once at scraper startup."""
        raw_entries = await self._redis.smembers("proxy:pool")
        # Filter out proxies currently marked dead
        now = time.time()
        dead_raw = await self._redis.zrangebyscore("proxy:dead", now - DEAD_TTL_SECS, "+inf")
        dead_set = set(dead_raw)

        self._proxies = []
        self._by_country = {}

        for raw in raw_entries:
            if raw in dead_set:
                continue
            proxy = Proxy.parse(raw)
            if not proxy:
                continue
            self._proxies.append(proxy)
            self._by_country.setdefault(proxy.country, []).append(proxy)

        log.info(
            "proxy_manager.loaded",
            total=len(self._proxies),
            countries=list(self._by_country.keys()),
        )

    def available(self) -> bool:
        return len(self._proxies) > 0

    async def get(self, country: str | None = None) -> str | None:
        """
        Return a proxy URL with geographic affinity.
        Returns None if no proxies are configured (direct connection).
        """
        if not self._proxies:
            return None

        # Try country-specific pool first
        if country:
            pool = self._by_country.get(country.lower(), [])
            if not pool:
                # Fallback: EU proxies (any European country)
                eu = ["de", "fr", "es", "nl", "be", "ch", "at", "pl", "se", "it", "pt"]
                pool = [p for c in eu for p in self._by_country.get(c, [])]
            if pool:
                return random.choice(pool).as_url()

        # Final fallback: any proxy
        return random.choice(self._proxies).as_url()

    async def mark_dead(self, proxy_url: str) -> None:
        """
        Mark a proxy as dead. It will be excluded for DEAD_TTL_SECS.
        Identifies proxy by host:port prefix in the URL.
        """
        # Extract host:port from URL for matching
        try:
            # "http://user:pass@host:port" → "host:port"
            hostport = proxy_url.split("@")[-1].rstrip("/")
        except Exception:
            return

        # Find matching proxy in pool
        for proxy in self._proxies:
            if f"{proxy.host}:{proxy.port}" == hostport:
                raw = proxy.raw()
                await self._redis.zadd("proxy:dead", {raw: time.time()})
                # Remove from in-memory pool
                self._proxies = [p for p in self._proxies if p.raw() != raw]
                country = proxy.country
                if country in self._by_country:
                    self._by_country[country] = [
                        p for p in self._by_country[country] if p.raw() != raw
                    ]
                log.warning(
                    "proxy_manager.marked_dead",
                    proxy=f"{proxy.host}:{proxy.port}",
                    country=proxy.country,
                    remaining=len(self._proxies),
                )
                return

    async def reload(self) -> None:
        """Reload pool from Redis (e.g. after adding new proxies at runtime)."""
        await self.load()
