"""
Gateway client — sends normalized listings to the CARDEX ingest endpoint.
Signs each request with HMAC-SHA256 (same scheme as gateway/pkg/hmac/).

Also handles Bloom filter pre-check (bloom:listing_urls) to skip already-seen URLs
before even making the HTTP call to the gateway.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .models import RawListing

log = structlog.get_logger()

# PII fields that must be stripped before sending to gateway
_PII_FIELDS = {"seller_phone", "seller_address"}


class GatewayClient:
    """
    Async client for POST /v1/ingest on the CARDEX gateway.
    Thread-safe: can be shared across async tasks in a single scraper run.
    """

    def __init__(
        self,
        gateway_url: str | None = None,
        hmac_secret: str | None = None,
        redis_client: Any = None,
    ) -> None:
        self.gateway_url = (gateway_url or os.environ["GATEWAY_URL"]).rstrip("/")
        self._secret = (hmac_secret or os.environ["GATEWAY_HMAC_SECRET"]).encode()
        self._redis = redis_client
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            limits=httpx.Limits(max_keepalive_connections=5),
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def _bloom_check(self, url: str) -> bool:
        """Return True if this URL has already been sent (bloom hit = skip)."""
        if not self._redis:
            return False
        try:
            result = await self._redis.execute_command(
                "BF.EXISTS", "bloom:listing_urls", url
            )
            return bool(result)
        except Exception:
            return False  # fail open — send anyway if Redis is down

    async def _bloom_add(self, url: str) -> None:
        if not self._redis:
            return
        try:
            await self._redis.execute_command("BF.ADD", "bloom:listing_urls", url)
        except Exception:
            pass

    def _sign(self, body: bytes, timestamp: int) -> str:
        """HMAC-SHA256 over 'timestamp.body'."""
        message = f"{timestamp}.".encode() + body
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()

    def _serialize(self, listing: RawListing) -> bytes:
        data = listing.model_dump(mode="json")
        # Strip PII before sending
        for field in _PII_FIELDS:
            data.pop(field, None)
        return json.dumps(data, default=str).encode()

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        reraise=True,
    )
    async def ingest(self, listing: RawListing) -> bool:
        """
        Send a single listing to /v1/ingest.
        Returns True if accepted (2xx), False if duplicate (409).
        Raises on other errors.
        """
        if await self._bloom_check(listing.source_url):
            log.debug("gateway.bloom_skip", url=listing.source_url)
            return False

        body = self._serialize(listing)
        ts = int(time.time())
        sig = self._sign(body, ts)

        resp = await self._http.post(
            f"{self.gateway_url}/v1/ingest",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Cardex-Timestamp": str(ts),
                "X-Cardex-Signature": sig,
                "X-Scraper-Source": listing.source_platform,
            },
        )

        if resp.status_code == 409:
            log.debug("gateway.duplicate", url=listing.source_url)
            return False

        resp.raise_for_status()
        await self._bloom_add(listing.source_url)
        log.info("gateway.accepted", url=listing.source_url, platform=listing.source_platform)
        return True

    async def ingest_batch(self, listings: list[RawListing]) -> dict[str, int]:
        """Send multiple listings. Returns {'accepted': n, 'skipped': n, 'errors': n}."""
        stats = {"accepted": 0, "skipped": 0, "errors": 0}
        for listing in listings:
            try:
                accepted = await self.ingest(listing)
                if accepted:
                    stats["accepted"] += 1
                else:
                    stats["skipped"] += 1
            except Exception as e:
                stats["errors"] += 1
                log.error("gateway.ingest_error", url=listing.source_url, error=str(e))
        return stats
