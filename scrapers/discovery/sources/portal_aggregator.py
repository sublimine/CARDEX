"""
Portal dealer-directory scraper.

Many European marketplace portals publish a browsable "find a dealer"
directory: AutoScout24 (6 countries), Mobile.de, LeBonCoin, Coches.net,
Marktplaats, 2dehands. Each dealer profile page links to the dealer's OWN
website — which is exactly what we want for sitemap-first indexing.

This module is a read-only HTML scraper with two phases per portal:

    Phase 1 — paginate directory pages, collect profile hrefs
    Phase 2 — fetch each profile, extract external website URL

Output is a stream of candidate dicts:

    {
        "domain":   "autohaus-mueller.de",
        "country":  "DE",
        "source":   "portal:autoscout24",
        "url":      "https://autohaus-mueller.de/",
        "name":     "Autohaus Müller GmbH",
        "city":     "München",
        "postcode": "80331",
        "phone":    "+49 89 123456",
        "lat":      48.1351,
        "lng":      11.5820,
    }

Only candidates that expose an EXTERNAL website (not the portal itself) are
yielded. A dealer without its own site is useless for sitemap indexing.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import urllib.parse
from typing import Any, AsyncIterator

import httpx

log = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_DEFAULT_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8,fr;q=0.7,es;q=0.6,nl;q=0.5",
}

_LIST_INTERVAL = 2.0     # seconds between directory page fetches per portal
_PROFILE_INTERVAL = 0.5  # seconds between profile fetches per portal
_PROFILE_BATCH = 5       # parallel profile fetches per batch

_SKIP_DOMAINS = frozenset({
    "autoscout24.", "mobile.de", "leboncoin.", "coches.net", "marktplaats.",
    "2dehands.", "kleinanzeigen.", "wallapop.", "milanuncios.",
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com", "x.com",
    "youtube.com", "google.", "yelp.", "tripadvisor.", "wikipedia.",
    "pagesjaunes.", "gelbeseiten.", "goudengids.", "paginasamarillas.",
})


# Portal configuration — profile-URL and website-URL regexes per site.
PORTALS: dict[str, dict[str, Any]] = {
    "autoscout24": {
        "directories": {
            "DE": "https://www.autoscout24.de/haendler/",
            "ES": "https://www.autoscout24.es/concesionarios/",
            "FR": "https://www.autoscout24.fr/concessionnaires/",
            "NL": "https://www.autoscout24.nl/dealers/",
            "BE": "https://www.autoscout24.be/fr/concessionnaires/",
            "CH": "https://www.autoscout24.ch/de/haendler/",
        },
        "domain": {
            "DE": "https://www.autoscout24.de",
            "ES": "https://www.autoscout24.es",
            "FR": "https://www.autoscout24.fr",
            "NL": "https://www.autoscout24.nl",
            "BE": "https://www.autoscout24.be",
            "CH": "https://www.autoscout24.ch",
        },
        "max_pages": 500,
        "profile_re": re.compile(
            r'href="((?:/(?:haendler|dealers?|concession[a-z]*|concessionnaire[a-z]*)/)[^"?#]+)"',
            re.I,
        ),
        "website_re": [
            re.compile(
                r'href="(https?://(?!(?:www\.)?autoscout24)[^"]+)"[^>]*>\s*'
                r'(?:Website|Webseite|Sitio\s*web|Site\s*web|Visiter|Besuchen|Bekijken)',
                re.I,
            ),
            re.compile(r'"url"\s*:\s*"(https?://(?!(?:www\.)?autoscout24)[^"]+)"'),
            re.compile(
                r'class="[^"]*(?:dealer-?website|homepage|extern|website-link)[^"]*"[^>]*'
                r'href="(https?://(?!(?:www\.)?autoscout24)[^"]+)"',
                re.I,
            ),
        ],
    },
    "mobile_de": {
        "directories": {"DE": "https://www.mobile.de/haendler/"},
        "domain": {"DE": "https://www.mobile.de"},
        "max_pages": 500,
        "profile_re": re.compile(r'href="(/haendler/[^"?#]+)"', re.I),
        "website_re": [
            re.compile(
                r'href="(https?://(?!(?:www\.)?mobile\.de)[^"]+)"[^>]*>\s*'
                r'(?:Website|Homepage|Webseite)',
                re.I,
            ),
            re.compile(r'"url"\s*:\s*"(https?://(?!(?:www\.)?mobile\.de)[^"]+)"'),
        ],
    },
    "leboncoin": {
        "directories": {"FR": "https://www.leboncoin.fr/boutiques/voitures/"},
        "domain": {"FR": "https://www.leboncoin.fr"},
        "max_pages": 300,
        "profile_re": re.compile(r'href="(/boutique/[^"?#]+)"', re.I),
        "website_re": [
            re.compile(
                r'href="(https?://(?!(?:www\.)?leboncoin)[^"]+)"[^>]*>\s*'
                r'(?:Site\s*web|Visiter|Voir\s*le\s*site)',
                re.I,
            ),
            re.compile(r'"website"\s*:\s*"(https?://[^"]+)"'),
        ],
    },
    "coches_net": {
        "directories": {"ES": "https://www.coches.net/concesionarios/"},
        "domain": {"ES": "https://www.coches.net"},
        "max_pages": 200,
        "profile_re": re.compile(r'href="(/concesionarios?/[^"?#]+\.htm)"', re.I),
        "website_re": [
            re.compile(
                r'href="(https?://(?!(?:www\.)?coches\.net)[^"]+)"[^>]*>\s*'
                r'(?:Web|Sitio|P[áa]gina|Visitar)',
                re.I,
            ),
            re.compile(r'"url"\s*:\s*"(https?://(?!(?:www\.)?coches\.net)[^"]+)"'),
        ],
    },
    "marktplaats": {
        "directories": {"NL": "https://www.marktplaats.nl/verkopers/autos/"},
        "domain": {"NL": "https://www.marktplaats.nl"},
        "max_pages": 200,
        "profile_re": re.compile(r'href="(/verkopers?/[^"?#]+)"', re.I),
        "website_re": [
            re.compile(
                r'href="(https?://(?!(?:www\.)?marktplaats)[^"]+)"[^>]*>\s*'
                r'(?:Website|Bekijk|Bezoek)',
                re.I,
            ),
        ],
    },
    "2dehands": {
        "directories": {"BE": "https://www.2dehands.be/verkopers/autos/"},
        "domain": {"BE": "https://www.2dehands.be"},
        "max_pages": 200,
        "profile_re": re.compile(r'href="(/verkopers?/[^"?#]+)"', re.I),
        "website_re": [
            re.compile(
                r'href="(https?://(?!(?:www\.)?2dehands)[^"]+)"[^>]*>\s*'
                r'(?:Website|Bekijk|Bezoek)',
                re.I,
            ),
        ],
    },
}


class _Throttle:
    def __init__(self, interval: float):
        self._interval = interval
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            wait = self._interval - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


class PortalAggregatorSource:
    """
    Yields dealer candidates from marketplace portal dealer directories.
    """

    def __init__(self, client: httpx.AsyncClient):
        self._client = client
        self._list_throttle = _Throttle(_LIST_INTERVAL)
        self._profile_throttle = _Throttle(_PROFILE_INTERVAL)

    async def discover(self, country: str) -> AsyncIterator[dict]:
        for portal_name, cfg in PORTALS.items():
            dir_url = cfg["directories"].get(country)
            if not dir_url:
                continue
            domain = cfg["domain"][country]
            try:
                async for cand in self._scrape_portal(
                    portal=portal_name,
                    dir_url=dir_url,
                    domain=domain,
                    cfg=cfg,
                    country=country,
                ):
                    yield cand
            except Exception as exc:
                log.warning(
                    "portal_aggregator: %s/%s scrape error: %s",
                    portal_name, country, exc,
                )

    async def _scrape_portal(
        self,
        *,
        portal: str,
        dir_url: str,
        domain: str,
        cfg: dict,
        country: str,
    ) -> AsyncIterator[dict]:
        profile_re: re.Pattern = cfg["profile_re"]
        website_patterns: list[re.Pattern] = cfg["website_re"]
        max_pages: int = cfg.get("max_pages", 200)

        seen_profiles: set[str] = set()
        page = 1

        while page <= max_pages:
            await self._list_throttle.acquire()
            url = dir_url if page == 1 else f"{dir_url}?page={page}"
            try:
                resp = await self._client.get(url, headers=_DEFAULT_HEADERS)
                if resp.status_code in (403, 404, 410):
                    break
                resp.raise_for_status()
            except Exception as exc:
                log.debug("portal %s page %d fail: %s", portal, page, exc)
                break

            html = resp.text
            hrefs = profile_re.findall(html)
            if not hrefs:
                break

            fresh: list[str] = []
            for href in hrefs:
                if href.startswith("/"):
                    full = domain + href
                elif href.startswith("http"):
                    full = href
                else:
                    continue
                canon = full.rstrip("/").lower()
                if canon not in seen_profiles:
                    seen_profiles.add(canon)
                    fresh.append(full)

            if not fresh:
                break  # pagination exhausted — all duplicates

            for i in range(0, len(fresh), _PROFILE_BATCH):
                batch = fresh[i : i + _PROFILE_BATCH]
                results = await asyncio.gather(
                    *[
                        self._parse_profile(p, portal, website_patterns, country)
                        for p in batch
                    ],
                    return_exceptions=True,
                )
                for r in results:
                    if isinstance(r, dict):
                        yield r

            if not _has_next_page(html):
                break
            page += 1

        log.info(
            "portal_aggregator: %s/%s done — %d pages, %d profiles",
            portal, country, page, len(seen_profiles),
        )

    async def _parse_profile(
        self,
        profile_url: str,
        portal: str,
        website_patterns: list[re.Pattern],
        country: str,
    ) -> dict | None:
        await self._profile_throttle.acquire()

        try:
            resp = await self._client.get(profile_url, headers=_DEFAULT_HEADERS)
            if resp.status_code >= 400:
                return None
            html = resp.text
        except Exception:
            return None

        name = _extract_name(html)
        if not name:
            return None

        website = _extract_website(html, website_patterns)
        if not website:
            return None  # no external website = useless for sitemap indexing

        domain = _extract_domain(website)
        if not domain:
            return None

        addr, city, postcode = _extract_address(html)
        phone = _extract_phone(html)
        lat, lng = _extract_coords(html)

        return {
            "domain": domain,
            "country": country,
            "source": f"portal:{portal}",
            "url": website,
            "name": name,
            "address": addr,
            "city": city,
            "postcode": postcode,
            "phone": phone,
            "lat": lat,
            "lng": lng,
        }


# ── Parsing helpers ──────────────────────────────────────────────────────────

def _extract_name(html: str) -> str | None:
    m = re.search(r"<h1[^>]*>([^<]{3,120})</h1>", html)
    if m:
        return re.sub(r"\s+", " ", m.group(1).strip())
    m = re.search(r'"name"\s*:\s*"([^"]{3,120})"', html)
    if m:
        return m.group(1).strip()
    return None


def _extract_website(html: str, patterns: list[re.Pattern]) -> str | None:
    for pat in patterns:
        m = pat.search(html)
        if not m:
            continue
        candidate = m.group(1).strip()
        if _is_skip(candidate):
            continue
        return _normalize(candidate)

    # Fallback: JSON-LD "url" field
    for ld_match in re.finditer(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
        html, re.DOTALL,
    ):
        try:
            ld = json.loads(ld_match.group(1))
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(ld, dict):
            continue
        candidate = ld.get("url") or ""
        if candidate and not _is_skip(candidate):
            return _normalize(candidate)
    return None


def _extract_address(html: str) -> tuple[str | None, str | None, str | None]:
    m = re.search(
        r'"streetAddress"\s*:\s*"([^"]*)".*?'
        r'"addressLocality"\s*:\s*"([^"]*)".*?'
        r'"postalCode"\s*:\s*"([^"]*)"',
        html, re.DOTALL,
    )
    if not m:
        return None, None, None
    return (
        m.group(1).strip() or None,
        m.group(2).strip() or None,
        m.group(3).strip() or None,
    )


def _extract_phone(html: str) -> str | None:
    m = re.search(r'"telephone"\s*:\s*"([^"]+)"', html)
    return m.group(1).strip() if m else None


def _extract_coords(html: str) -> tuple[float | None, float | None]:
    m = re.search(
        r'"latitude"\s*:\s*"?([0-9.]+)"?.*?"longitude"\s*:\s*"?([0-9.]+)"?',
        html, re.DOTALL,
    )
    if not m:
        return None, None
    try:
        return float(m.group(1)), float(m.group(2))
    except (TypeError, ValueError):
        return None, None


def _extract_domain(url: str) -> str:
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return ""
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def _normalize(url: str) -> str | None:
    url = (url or "").strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def _is_skip(url: str) -> bool:
    u = url.lower()
    return any(s in u for s in _SKIP_DOMAINS)


_NEXT_PAGE_PATTERNS = (
    re.compile(r'rel="next"', re.I),
    re.compile(r'class="[^"]*next[^"]*"', re.I),
    re.compile(r'aria-label="[Nn]ext'),
    re.compile(r'data-page="next"'),
    re.compile(r'>\s*(?:Next|Weiter|Suivant|Volgende|Siguiente|Nächste)\s*<'),
    re.compile(r'aria-label="[Pp]age\s+suivante"'),
)


def _has_next_page(html: str) -> bool:
    return any(p.search(html) for p in _NEXT_PAGE_PATTERNS)
