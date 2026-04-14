"""
Async HTTP client for CARDEX — honest indexer approach.

CardexBot identifies itself transparently as an indexer.
Portals benefit from our traffic redirects, so polite crawling
is both legally clean and practically effective.

Features:
- Honest CardexBot/1.0 User-Agent
- Rate limiting per domain (from Redis scraper:rate_limits)
- Exponential backoff on transient errors (429/503)
"""
from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Optional

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

log = structlog.get_logger()

CARDEX_UA = (
    "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu) "
    "httpx/0.27 Python/3.12"
)

DEFAULT_HEADERS = {
    "User-Agent": CARDEX_UA,
    "Accept": "text/html,application/xhtml+xml,application/json,application/xml",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


class RateLimiter:
    """Token bucket per domain — config from Redis `scraper:rate_limits`."""

    def __init__(self, domain: str, default_rps: float = 0.3) -> None:
        self.domain = domain
        self.rps = default_rps
        self._last_call: float = 0.0

    async def load_from_redis(self, redis_client: Any) -> None:
        try:
            val = await redis_client.hget("scraper:rate_limits", self.domain)
            if val:
                self.rps = float(val)
        except Exception:
            pass

    async def wait(self) -> None:
        interval = 1.0 / self.rps
        jitter = interval * 0.2 * (random.random() * 2 - 1)
        target = self._last_call + interval + jitter
        now = time.monotonic()
        if target > now:
            await asyncio.sleep(target - now)
        self._last_call = time.monotonic()


class HTTPClient:
    """
    Polite async HTTP client for public listing indexing.
    One instance per scraper, shared across a crawl session.
    """

    def __init__(
        self,
        domain: str,
        default_rps: float = 0.3,
        country: Optional[str] = None,
    ) -> None:
        self.domain = domain
        self.country = country
        self.rate_limiter = RateLimiter(domain, default_rps)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "HTTPClient":
        self._client = httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, connect=10.0),
            http2=True,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        reraise=True,
    )
    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        assert self._client is not None, "Use as async context manager"
        await self.rate_limiter.wait()
        log.debug("http.get", url=url, domain=self.domain)
        resp = await self._client.get(url, **kwargs)

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "60"))
            log.warning("http.rate_limited", url=url, retry_after=retry_after)
            await asyncio.sleep(retry_after)
            raise httpx.TransportError("Rate limited — retrying")

        if resp.status_code == 503:
            await asyncio.sleep(30)
            raise httpx.TransportError("503 — retrying")

        resp.raise_for_status()
        return resp

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        resp = await self.get(url, **kwargs)
        return resp.json()

    async def get_text(self, url: str, **kwargs: Any) -> str:
        resp = await self.get(url, **kwargs)
        return resp.text
