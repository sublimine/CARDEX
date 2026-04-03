"""
Async HTTP client with full anti-detection stack:
- curl_cffi: TLS fingerprint identical to Chrome 120+ (defeats Akamai, Cloudflare JA3/JA4 checks)
- Rotating User-Agent pool (real browser UAs — Chrome, Firefox, Edge)
- Complete browser-like headers (sec-fetch-*, Accept-Language, etc.)
- Proxy rotation via ProxyManager (geographic affinity)
- Auto-rotate proxy on 403/429/503 ban signals
- Exponential backoff with jitter
- Rate limiting per domain from Redis
"""
from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Optional

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

try:
    from curl_cffi.requests import AsyncSession, BrowserType
    _CURL_AVAILABLE = True
except ImportError:
    import httpx  # fallback — won't pass TLS fingerprint checks
    _CURL_AVAILABLE = False

from .proxy_manager import ProxyManager

log = structlog.get_logger()

# ─── Real browser User-Agent pool ────────────────────────────────────────────
# Chrome, Firefox, Edge — Windows/Mac/Linux. Updated quarterly.
_USER_AGENTS = [
    # Chrome 120 – Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Chrome 121 – Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    # Chrome 122 – Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Chrome 120 – Windows (alternate build)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.130 Safari/537.36",
    # Edge 120 – Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    # Firefox 121 – Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Firefox 120 – Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.2; rv:120.0) Gecko/20100101 Firefox/120.0",
    # Firefox 121 – Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Chrome 119 – Windows (older — realistic distribution)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Safari 17 – Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    # Chrome 120 – Android (mobile listings)
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    # Chrome 121 – Windows (latest)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 OPR/107.0.0.0",
]

_ACCEPT_LANGUAGES = [
    "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7",
    "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7",
    "en-GB,en;q=0.9",
    "en-US,en;q=0.9",
]


def _browser_headers(ua: str, accept: str = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8") -> dict:
    """Return a complete set of browser-like headers for the given UA."""
    is_firefox = "Firefox" in ua
    return {
        "User-Agent": ua,
        "Accept": accept,
        "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        **({"DNT": "1"} if is_firefox else {}),
        **({"Sec-CH-UA": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"'} if not is_firefox else {}),
    }


def _json_headers(ua: str) -> dict:
    return _browser_headers(
        ua,
        accept="application/json, text/plain, */*",
    ) | {
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }


class RateLimiter:
    """Token bucket per domain — config from Redis `scraper:rate_limits`."""

    def __init__(self, domain: str, default_rps: float = 0.5) -> None:
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
        jitter = interval * 0.25 * (random.random() * 2 - 1)
        target = self._last_call + interval + jitter
        now = time.monotonic()
        if target > now:
            await asyncio.sleep(target - now)
        self._last_call = time.monotonic()


class BanDetectedError(Exception):
    """Raised when a hard ban is detected (403 Access Denied, block page, etc.)."""


class HTTPClient:
    """
    Async HTTP client with Chrome TLS fingerprint + proxy rotation.
    Uses curl_cffi when available; falls back to httpx (no TLS spoofing).
    One instance per scraper, shared across a crawl session.
    """

    def __init__(
        self,
        domain: str,
        default_rps: float = 0.5,
        proxy_manager: Optional[ProxyManager] = None,
        country: Optional[str] = None,
    ) -> None:
        self.domain = domain
        self.country = country
        self.rate_limiter = RateLimiter(domain, default_rps)
        self.proxy_manager = proxy_manager
        self._ua = random.choice(_USER_AGENTS)
        self._session: Any = None

    async def __aenter__(self) -> "HTTPClient":
        proxy = await self._get_proxy()
        if _CURL_AVAILABLE:
            self._session = AsyncSession(
                impersonate=BrowserType.chrome120,
                proxies={"https": proxy, "http": proxy} if proxy else None,
                timeout=30,
                verify=True,
            )
        else:
            log.warning("http_client.curl_cffi_missing", fallback="httpx (no TLS spoofing)")
            import httpx
            self._session = httpx.AsyncClient(
                headers=_browser_headers(self._ua),
                proxies=proxy,
                follow_redirects=True,
                timeout=httpx.Timeout(30.0, connect=10.0),
                http2=True,
            )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._session:
            await self._session.aclose()

    async def _get_proxy(self) -> Optional[str]:
        if self.proxy_manager:
            return await self.proxy_manager.get(country=self.country)
        return None

    async def _rotate_proxy(self, banned_proxy: Optional[str]) -> None:
        """Mark current proxy dead and re-create session with a new one."""
        if self.proxy_manager and banned_proxy:
            await self.proxy_manager.mark_dead(banned_proxy)
        self._ua = random.choice(_USER_AGENTS)
        if self._session:
            await self._session.aclose()
        proxy = await self._get_proxy()
        if _CURL_AVAILABLE:
            self._session = AsyncSession(
                impersonate=BrowserType.chrome120,
                proxies={"https": proxy, "http": proxy} if proxy else None,
                timeout=30,
                verify=True,
            )
        else:
            import httpx
            self._session = httpx.AsyncClient(
                headers=_browser_headers(self._ua),
                proxies=proxy,
                follow_redirects=True,
                timeout=httpx.Timeout(30.0, connect=10.0),
                http2=True,
            )
        log.info("http_client.proxy_rotated", domain=self.domain, new_proxy=bool(proxy))

    def _is_ban(self, status: int, text: str) -> bool:
        if status in (403, 451):
            ban_phrases = [
                "access denied", "blocked", "forbidden", "captcha",
                "bot detected", "unusual traffic", "verify you are human",
                "please enable cookies", "ray id",
            ]
            ltext = text.lower()
            return any(p in ltext for p in ban_phrases)
        return False

    async def get(self, url: str, **kwargs: Any) -> Any:
        """GET with automatic proxy rotation on ban (up to 3 retries)."""
        assert self._session is not None, "Use as async context manager"

        current_proxy = await self._get_proxy() if self.proxy_manager else None
        last_exc: Exception | None = None

        for attempt in range(3):
            await self.rate_limiter.wait()
            log.debug("http.get", url=url, domain=self.domain, attempt=attempt)

            try:
                if _CURL_AVAILABLE:
                    resp = await self._session.get(
                        url,
                        headers=_browser_headers(self._ua),
                        **kwargs,
                    )
                    status, text = resp.status_code, resp.text
                else:
                    resp = await self._session.get(url, **kwargs)
                    status, text = resp.status_code, resp.text

                if status == 429:
                    retry_after = int(resp.headers.get("Retry-After", "60"))
                    log.warning("http.rate_limited", url=url, retry_after=retry_after)
                    await asyncio.sleep(retry_after)
                    continue

                if status == 503:
                    await asyncio.sleep(30 + random.uniform(0, 15))
                    continue

                if self._is_ban(status, text):
                    log.warning("http.ban_detected", url=url, status=status, attempt=attempt)
                    await self._rotate_proxy(current_proxy)
                    current_proxy = await self._get_proxy() if self.proxy_manager else None
                    await asyncio.sleep(random.uniform(5, 15))
                    continue

                if status >= 400:
                    resp.raise_for_status() if hasattr(resp, 'raise_for_status') else None
                    raise Exception(f"HTTP {status}: {url}")

                return resp

            except BanDetectedError:
                raise
            except Exception as e:
                last_exc = e
                wait = (2 ** attempt) + random.uniform(0, 5)
                log.warning("http.error", url=url, error=str(e), retry_in=wait)
                await asyncio.sleep(wait)

        raise last_exc or Exception(f"Max retries exceeded for {url}")

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        """GET JSON with browser JSON Accept headers."""
        if _CURL_AVAILABLE:
            assert self._session is not None
            await self.rate_limiter.wait()
            resp = await self._session.get(
                url,
                headers=_json_headers(self._ua),
                **kwargs,
            )
            return resp.json()
        # httpx fallback
        resp = await self.get(url, **kwargs)
        return resp.json()
