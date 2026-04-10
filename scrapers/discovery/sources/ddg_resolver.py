"""
DuckDuckGo HTML resolver — name + city + country → dealer domain.

Uses the HTML endpoint (html.duckduckgo.com/html/) which returns organic
results as server-rendered HTML. No API key, no rate limits beyond normal
politeness, no tracking.

This is pure function — caller provides a query, the resolver returns a
validated domain or None. No Redis, no DB, no streams.

Usage:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resolver = DDGResolver(client)
        website = await resolver.resolve(
            name="Autohaus Müller",
            city="München",
            country="DE",
        )
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
import urllib.parse

import httpx

log = logging.getLogger(__name__)

_DDG_HTML_URL = "https://html.duckduckgo.com/html/"

_USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
)

_ACCEPT_LANGUAGES = {
    "DE": "de-DE,de;q=0.9,en;q=0.5",
    "ES": "es-ES,es;q=0.9,en;q=0.5",
    "FR": "fr-FR,fr;q=0.9,en;q=0.5",
    "NL": "nl-NL,nl;q=0.9,en;q=0.5",
    "BE": "nl-BE,nl;q=0.8,fr-BE;q=0.7,en;q=0.5",
    "CH": "de-CH,de;q=0.9,fr;q=0.7,en;q=0.5",
}

_COUNTRY_NAMES = {
    "DE": "Deutschland", "ES": "España", "FR": "France",
    "NL": "Nederland",   "BE": "België",  "CH": "Schweiz",
}

_COUNTRY_AUTO_KEYWORDS = {
    "DE": "autohaus",
    "ES": "concesionario coches",
    "FR": "concessionnaire automobile",
    "NL": "autobedrijf",
    "BE": "autobedrijf garage",
    "CH": "autohaus garage",
}

# Domains that are never a dealer's own site.
_PORTAL_DOMAINS = frozenset({
    "autoscout24.", "mobile.de", "kleinanzeigen.de", "heycar.",
    "coches.net", "wallapop.com", "milanuncios.com", "autocasion.com",
    "leboncoin.fr", "lacentrale.fr", "paruvendu.com",
    "marktplaats.nl", "autotrack.nl", "gaspedaal.nl",
    "2dehands.be", "gocar.be",
    "tutti.ch", "comparis.ch", "ricardo.ch",
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com", "x.com",
    "youtube.com", "google.com", "yelp.", "tripadvisor.",
    "pagesjaunes.fr", "gelbeseiten.de", "goudengids.",
    "paginasamarillas.es", "local.ch", "search.ch",
    "wikipedia.org", "wikidata.org",
})

# Regex for DDG organic result anchors.
_RE_RESULT_A = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"')
_RE_UDDG     = re.compile(r'<a[^>]+href="//duckduckgo\.com/l/\?uddg=([^&"]+)')

_JITTER_MIN = 2.0
_JITTER_MAX = 6.0


class DDGResolver:
    """
    Resolves a dealer identity to its canonical website via DuckDuckGo HTML.
    """

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def resolve(
        self,
        *,
        name: str,
        city: str | None,
        country: str,
    ) -> str | None:
        if not name:
            return None

        # Jitter — avoid DDG rate-limit patterns.
        await asyncio.sleep(_JITTER_MIN + random.random() * (_JITTER_MAX - _JITTER_MIN))

        query = self._build_query(name, city or "", country)
        headers = self._build_headers(country)

        try:
            resp = await self._client.post(
                _DDG_HTML_URL,
                data={"q": query, "b": ""},
                headers=headers,
            )
        except Exception as exc:
            log.debug("ddg: request failed name=%s err=%s", name[:40], exc)
            return None

        if resp.status_code != 200:
            return None

        for candidate_url in self._extract_result_urls(resp.text):
            if _is_portal(candidate_url):
                continue
            normalized = _normalize_website(candidate_url)
            if not normalized:
                continue
            if await self._verify_alive(normalized):
                return normalized

        return None

    @staticmethod
    def _build_query(name: str, city: str, country: str) -> str:
        country_name = _COUNTRY_NAMES.get(country, country)
        kw = _COUNTRY_AUTO_KEYWORDS.get(country, "car dealer")
        return f"{name} {city} {country_name} {kw}".strip()

    @staticmethod
    def _build_headers(country: str) -> dict[str, str]:
        return {
            "User-Agent": random.choice(_USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": _ACCEPT_LANGUAGES.get(country, "en-US,en;q=0.9"),
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://html.duckduckgo.com/",
        }

    @staticmethod
    def _extract_result_urls(html: str) -> list[str]:
        urls = _RE_RESULT_A.findall(html)
        if urls:
            return urls[:10]
        # Fallback: DDG's uddg redirect format
        urls = [urllib.parse.unquote(u) for u in _RE_UDDG.findall(html)]
        return urls[:10]

    async def _verify_alive(self, url: str) -> bool:
        try:
            r = await self._client.head(url, timeout=8.0)
            if r.status_code < 400:
                return True
        except Exception:
            pass
        try:
            r = await self._client.get(url, timeout=8.0)
            return r.status_code < 400
        except Exception:
            return False


def _is_portal(url: str) -> bool:
    u = url.lower()
    return any(p in u for p in _PORTAL_DOMAINS)


def _normalize_website(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")
