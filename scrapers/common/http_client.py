"""
Async HTTP client with:
- Honest User-Agent (identified as a bot)
- Configurable rate limiting (reads from Redis scraper:rate_limits hash)
- Exponential backoff with jitter on 429/503
- No TLS fingerprint spoofing, no WAF evasion — plain httpx
"""
from __future__ import annotations

import asyncio
import random
import time
from typing import Any

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

log = structlog.get_logger()

# Honest, identifiable bot User-Agent
CARDEX_UA = (
    "CardexBot/1.0 (+https://cardex.eu/bot; scraping@cardex.eu) "
    "httpx/0.27 Python/3.12"
)

DEFAULT_HEADERS = {
    "User-Agent": CARDEX_UA,
    "Accept": "text/html,application/xhtml+xml,application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


class RateLimiter:
    """Token bucket per domain — reads config from Redis, falls back to default."""

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
            pass  # use default

    async def wait(self) -> None:
        """Wait until the next request is allowed, with ±20% jitter."""
        interval = 1.0 / self.rps
        jitter = interval * 0.2 * (random.random() * 2 - 1)
        target = self._last_call + interval + jitter
        now = time.monotonic()
        if target > now:
            await asyncio.sleep(target - now)
        self._last_call = time.monotonic()


class HTTPClient:
    """
    Thin async HTTP client wrapping httpx.AsyncClient.
    One instance per scraper, shared across all pages of a crawl session.
    """

    def __init__(self, domain: str, default_rps: float = 0.3) -> None:
        self.domain = domain
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
        wait=wait_exponential(multiplier=2, min=2, max=30),
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
            raise httpx.TransportError("Rate limited — retrying")  # trigger tenacity retry

        if resp.status_code == 503:
            await asyncio.sleep(30)
            raise httpx.TransportError("503 — retrying")

        resp.raise_for_status()
        return resp

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        reraise=True,
    )
    async def get_json(self, url: str, **kwargs: Any) -> Any:
        resp = await self.get(url, **kwargs)
        return resp.json()
