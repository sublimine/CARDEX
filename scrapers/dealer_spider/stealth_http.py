"""
Stealth HTTP Client — TLS-impersonating async HTTP layer for the Dealer Spider.

Replaces raw aiohttp with curl_cffi for Vectors 1/2/Legacy, providing:
  - Per-country TLS impersonation (Chrome/Firefox/Safari JA3/JA4 fingerprints)
  - Coherent header profiles (Sec-CH-UA, Accept-Language, etc.)
  - Proxy tiering (T0 direct → T1 datacenter → T2 residential)
  - Domain rate-limit isolation via Redis (TTL 120s)
  - WAF challenge detection in response bodies
  - Automatic tier escalation on block

The Spider creates one StealthClient per worker. All methods are async.
"""
from __future__ import annotations

import logging
import os
import random
import time
from typing import NamedTuple
from urllib.parse import urlparse

from curl_cffi.requests import AsyncSession, Response

log = logging.getLogger("spider.stealth")

# ── TLS Impersonation Profiles ────────────────────────────────────────────────
#
# Each profile bundles: curl_cffi impersonate string, coherent headers.
# The impersonate string tells curl_cffi which browser TLS to mimic exactly
# (cipher suites, extensions, ALPN, JA3 fingerprint).

class _BrowserProfile(NamedTuple):
    impersonate: str           # curl_cffi impersonate ID
    user_agent: str
    sec_ch_ua: str
    sec_ch_ua_platform: str
    accept_language: str       # country-specific
    sec_fetch_site: str


# Chrome 124 — DE, NL, BE
_CHROME_DE = _BrowserProfile(
    impersonate="chrome124",
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    sec_ch_ua='"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    sec_ch_ua_platform='"Windows"',
    accept_language="de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    sec_fetch_site="none",
)

# Firefox 125 — FR, ES
_FIREFOX_FR = _BrowserProfile(
    impersonate="firefox120",
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    sec_ch_ua="",   # Firefox no envía Sec-CH-UA
    sec_ch_ua_platform="",
    accept_language="fr-FR,fr;q=0.9,es-ES;q=0.8,es;q=0.7,en;q=0.5",
    sec_fetch_site="none",
)

# Safari 17 — CH
_SAFARI_CH = _BrowserProfile(
    impersonate="safari17_2_ios",
    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    sec_ch_ua="",   # Safari no envía Sec-CH-UA
    sec_ch_ua_platform="",
    accept_language="de-CH,de;q=0.9,fr-CH;q=0.8,fr;q=0.7,en;q=0.5",
    sec_fetch_site="none",
)

_COUNTRY_PROFILES: dict[str, _BrowserProfile] = {
    "DE": _CHROME_DE,
    "NL": _CHROME_DE,
    "BE": _CHROME_DE,
    "FR": _FIREFOX_FR,
    "ES": _FIREFOX_FR,
    "CH": _SAFARI_CH,
}

_DEFAULT_PROFILE = _CHROME_DE

# ── Proxy Configuration ──────────────────────────────────────────────────────

# Read from env — operator configures these, not hardcoded
_PROXY_T0 = os.environ.get("PROXY_T0", "")               # local forward proxy or empty
_PROXY_T1 = os.environ.get("PROXY_T1", "")               # datacenter pool URL
_PROXY_T2 = os.environ.get("PROXY_T2", "")               # residential backconnect URL

# Throttle: forced delay (seconds) between ANY request when operating without proxies.
# Prevents IP burn on T0 direct. Set to 0 when proxies are active.
_THROTTLE_MIN = float(os.environ.get("STEALTH_THROTTLE_MIN", "3.0"))
_THROTTLE_MAX = float(os.environ.get("STEALTH_THROTTLE_MAX", "7.0"))
_HAS_PROXIES = bool(_PROXY_T1 or _PROXY_T2)

# ── WAF Challenge Detection ──────────────────────────────────────────────────

_CHALLENGE_SIGNATURES = [
    b"just a moment",
    b"cf-browser-verification",
    b"challenge-platform",
    b"_cf_chl_opt",
    b"attention required",
    b"access denied",
    b"datadome",
    b"akamai bot manager",
    b"imperva incident",
    b"checking your browser",
    b"please turn javascript on",
    b"enable cookies",
]

_WAF_HEADER_SIGNATURES = {
    "cf-mitigated": "cloudflare",
    "cf-ray": "cloudflare",
    "x-datadome": "datadome",
    "x-akamai-transformed": "akamai",
    "x-iinfo": "imperva",
    "x-cdn": "imperva",
}


def detect_waf_type(headers: dict) -> str:
    """Identify WAF vendor from response headers."""
    for header_key, waf_name in _WAF_HEADER_SIGNATURES.items():
        if header_key in headers:
            return waf_name
    server = headers.get("server", "").lower()
    if "cloudflare" in server:
        return "cloudflare"
    if "akamaighost" in server or "akamai" in server:
        return "akamai"
    return "none"


def is_challenge_page(status_code: int, body: bytes, headers: dict) -> bool:
    """Detect WAF challenge/block even on 200 responses."""
    # Explicit blocks
    if status_code in (403, 503):
        return True
    # 200 but body is a challenge page
    if status_code == 200 and len(body) < 15_000:
        body_lower = body.lower()
        for sig in _CHALLENGE_SIGNATURES:
            if sig in body_lower:
                return True
    # cf-mitigated header
    if "cf-mitigated" in headers:
        return True
    return False


# ── Stealth HTTP Client ──────────────────────────────────────────────────────

class StealthClient:
    """
    Async HTTP client with TLS impersonation, proxy tiering, and WAF handling.

    Usage:
        async with StealthClient(rdb, country="ES") as client:
            resp = await client.get(url, dealer_tier=0)
    """

    def __init__(self, rdb, country: str = "DE"):
        self._rdb = rdb
        self._country = country
        self._profile = _COUNTRY_PROFILES.get(country, _DEFAULT_PROFILE)
        self._sessions: dict[int, AsyncSession] = {}  # tier → session

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        for session in self._sessions.values():
            await session.close()
        self._sessions.clear()

    def _get_proxy(self, tier: int) -> str | None:
        if tier == 0:
            return _PROXY_T0 or None
        elif tier == 1:
            return _PROXY_T1 or None
        elif tier == 2:
            return _PROXY_T2 or None
        return None

    def _get_session(self, tier: int) -> AsyncSession:
        if tier not in self._sessions:
            proxy = self._get_proxy(tier)
            self._sessions[tier] = AsyncSession(
                impersonate=self._profile.impersonate,
                proxy=proxy,
                timeout=20,
                verify=False,   # some dealer certs are self-signed
                max_redirects=5,
            )
        return self._sessions[tier]

    def _build_headers(self, url: str) -> dict:
        """Build browser-coherent headers matching the TLS profile."""
        parsed = urlparse(url)
        headers = {
            "User-Agent": self._profile.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": self._profile.accept_language,
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": self._profile.sec_fetch_site,
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Referer": f"{parsed.scheme}://{parsed.netloc}/",
        }
        # Chrome-specific Client Hints
        if self._profile.sec_ch_ua:
            headers["Sec-CH-UA"] = self._profile.sec_ch_ua
            headers["Sec-CH-UA-Mobile"] = "?0"
            headers["Sec-CH-UA-Platform"] = self._profile.sec_ch_ua_platform
        return headers

    async def _check_domain_rate(self, domain: str, tier: int) -> bool:
        """
        Check if this domain was hit recently from the same proxy tier.
        Returns True if safe to proceed, False if should wait/skip.
        Uses Redis with 120s TTL.
        """
        key = f"stealth:domain:{domain}:t{tier}"
        last = await self._rdb.get(key)
        if last is not None:
            elapsed = time.time() - float(last)
            if elapsed < 2.0:  # min 2s between requests to same domain+tier
                return False
        await self._rdb.set(key, str(time.time()), ex=120)
        return True

    async def get(
        self,
        url: str,
        tier: int = 0,
    ) -> tuple[int, str, dict, str]:
        """
        Fetch a URL with TLS impersonation at the given proxy tier.

        Returns: (status_code, body_text, response_headers, detected_waf_type)
        Raises: StealthBlockError if challenge detected after response.
        """
        domain = urlparse(url).netloc
        session = self._get_session(tier)
        headers = self._build_headers(url)

        # Global throttle when operating without proxies (T0 direct IP)
        if not _HAS_PROXIES and tier == 0 and _THROTTLE_MIN > 0:
            import asyncio
            await asyncio.sleep(random.uniform(_THROTTLE_MIN, _THROTTLE_MAX))

        # Domain rate isolation
        safe = await self._check_domain_rate(domain, tier)
        if not safe:
            import asyncio
            await asyncio.sleep(random.uniform(1.0, 3.0))
            await self._rdb.set(f"stealth:domain:{domain}:t{tier}", str(time.time()), ex=120)

        resp: Response = await session.get(url, headers=headers)

        resp_headers = {k.lower(): v for k, v in resp.headers.items()}
        waf = detect_waf_type(resp_headers)
        body_bytes = resp.content

        if is_challenge_page(resp.status_code, body_bytes, resp_headers):
            raise StealthBlockError(
                status=resp.status_code,
                waf_type=waf,
                url=url,
                tier=tier,
            )

        return (
            resp.status_code,
            resp.text,
            resp_headers,
            waf,
        )

    async def head(self, url: str, tier: int = 0) -> int:
        """HEAD request — returns status code only."""
        session = self._get_session(tier)
        headers = self._build_headers(url)
        resp = await session.head(url, headers=headers, allow_redirects=True)
        return resp.status_code

    async def get_json(self, url: str, tier: int = 0) -> dict | list:
        """Fetch JSON endpoint."""
        session = self._get_session(tier)
        headers = self._build_headers(url)
        headers["Accept"] = "application/json, text/javascript, */*;q=0.01"
        headers["X-Requested-With"] = "XMLHttpRequest"
        resp = await session.get(url, headers=headers)
        return resp.json()


class StealthBlockError(Exception):
    """Raised when WAF challenge/block is detected in the response."""
    def __init__(self, status: int, waf_type: str, url: str, tier: int):
        self.status = status
        self.waf_type = waf_type
        self.url = url
        self.tier = tier
        super().__init__(f"WAF block: {waf_type} HTTP {status} on {url} (tier {tier})")


# ── HTTPHelper adapter (drop-in for spider.py) ──────────────────────────────

class StealthHTTPHelper:
    """
    Drop-in replacement for the old _HTTPHelper(aiohttp.ClientSession).
    Used by DMS extractors that expect .get_text(), .get_json(), .post_json().
    """

    def __init__(self, stealth: StealthClient, tier: int = 0):
        self._stealth = stealth
        self._tier = tier

    async def get_text(self, url: str, **kwargs) -> str:
        _status, text, _headers, _waf = await self._stealth.get(url, tier=self._tier)
        return text

    async def get_json(self, url: str, **kwargs) -> dict | list:
        return await self._stealth.get_json(url, tier=self._tier)

    async def post_json(self, url: str, **kwargs) -> dict | list:
        # curl_cffi post — pass through
        session = self._stealth._get_session(self._tier)
        headers = self._stealth._build_headers(url)
        headers["Accept"] = "application/json"
        headers["Content-Type"] = "application/json"
        resp = await session.post(url, headers=headers, **kwargs)
        return resp.json()

    async def head_ok(self, url: str) -> bool:
        try:
            status = await self._stealth.head(url, tier=self._tier)
            return status < 400
        except Exception:
            return False
