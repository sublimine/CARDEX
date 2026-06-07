"""
Domain-resolution — keyless web-search providers.

DuckDuckGo's HTML endpoint is primary: queried with curl_cffi ``impersonate`` it
returns clean results from this host and ranks the dealer's own site first
(verified live: "Ungeheuer Automobile Bruchsal" → ungeheuer-bmw.de). Mojeek is the
fallback when DDG yields nothing. Each provider just returns the results HTML;
``candidate.py`` extracts + ranks the domains.

The fetcher (a curl_cffi AsyncSession) is injected so the resolver owns one polite,
reused session; tests pass an in-memory map.
"""
from __future__ import annotations

import logging
import urllib.parse

from scrapers.discovery.domain_resolution.candidate import clean_name

log = logging.getLogger(__name__)

PROVIDERS: dict[str, str] = {
    "ddg": "https://html.duckduckgo.com/html/?q={q}",
    "mojeek": "https://www.mojeek.com/search?q={q}",
}
PROVIDER_ORDER = ("ddg", "mojeek")
_PROVIDER_ORDER = PROVIDER_ORDER  # backwards-compatible alias


def build_query(name: str, city: str) -> str:
    """
    Search query for a dealer — cleaned name + city (city disambiguates namesakes).

    OEM-locator boilerplate ("(Zaragoza …) - Exposición y Taller") is stripped first
    so the engine searches the dealer, not the generic suffix (which surfaced random
    "taller" workshops live).
    """
    return " ".join(p for p in (clean_name(name), city or "") if p).strip()


async def fetch_search_html(session, name: str, city: str, provider: str = "ddg") -> str:
    """
    Fetch one provider's results HTML for "name city", or "" on failure.

    ``session`` is a curl_cffi AsyncSession (``await session.get(url)``). Never
    raises — a provider error returns "" so the resolver falls back / moves on.
    """
    q = urllib.parse.quote(build_query(name, city))
    url = PROVIDERS[provider].format(q=q)
    try:
        resp = await session.get(url, timeout=20)
    except Exception as exc:  # noqa: BLE001
        log.debug("search %s failed: %s", provider, type(exc).__name__)
        return ""
    if int(getattr(resp, "status_code", 0) or 0) != 200:
        return ""
    return resp.text or ""


async def search_all(session, name: str, city: str) -> tuple[str, str]:
    """Try providers in order; return (provider, html) for the first non-empty page."""
    for provider in _PROVIDER_ORDER:
        html = await fetch_search_html(session, name, city, provider)
        if html and len(html) > 1000:
            return provider, html
    return "", ""
