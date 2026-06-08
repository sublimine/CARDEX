"""
Domain-resolution — national business-directory providers.

Directories list a business with its website/contact; given a dealer's name+city they
yield candidate domains the homepage-validator then confirms. Only directories that
expose the dealer's own domain in ONE fetch (verified live from this host) are wired:

  * FR — PagesJaunes: the dealer's site appears as a plain external ``href`` in the
    results page.
  * CH — local.ch: the results JSON embeds the dealer's contact ``email`` (and often a
    ``website``); the email's apex is the domain.

DE (gelbeseiten) needs a second detail-page fetch and ES (paginasamarillas) is anti-bot
gated from this IP — both deferred; DDG/Mojeek already cover those countries. Each
provider returns ORDERED candidate apexes (best first) or ``[]``; never raises.

The fetcher is the resolver's shared curl_cffi AsyncSession (polite, impersonating).
"""
from __future__ import annotations

import logging
import re
import urllib.parse

from scrapers.discovery.domain_resolution.candidate import apex, clean_name, email_apex, is_excluded

log = logging.getLogger(__name__)

# Country → directory provider key.
DIRECTORY_BY_COUNTRY: dict[str, str] = {"FR": "pagesjaunes", "CH": "localch", "DE": "gelbeseiten"}

_HREF_RE = re.compile(r'href="(https?://[^"]+)"', re.I)
_EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
_WEBSITE_JSON_RE = re.compile(r'"(?:website|websiteUrl|url|web)"\s*:\s*"(https?://[^"]+)"', re.I)
_GS_DETAIL_RE = re.compile(r'href="(https://www\.gelbeseiten\.de/gsbiz/[a-f0-9\-]+)"', re.I)


def _uniq(hosts: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for h in hosts:
        if h and h not in seen:
            seen.add(h)
            out.append(h)
    return out


async def _get(session, url: str, proxy: str | None = None) -> str:
    kw: dict = {"timeout": 20, "allow_redirects": True}
    if proxy:  # route this fetch through a rotating proxy (IP-block bypass)
        kw["proxies"] = {"http": proxy, "https": proxy}
    try:
        resp = await session.get(url, **kw)
    except Exception as exc:  # noqa: BLE001 — a directory miss must not break resolution
        log.debug("directory get failed %s: %s", url, type(exc).__name__)
        return ""
    if int(getattr(resp, "status_code", 0) or 0) != 200:
        return ""
    return resp.text or ""


async def _pagesjaunes(session, name: str, city: str, proxy: str | None = None) -> list[str]:
    q = urllib.parse.quote(clean_name(name))
    ou = urllib.parse.quote(city or "")
    url = f"https://www.pagesjaunes.fr/annuaire/chercherlespros?quoiqui={q}&ou={ou}&proximite=0"
    html = await _get(session, url, proxy=proxy)
    if not html:
        return []
    cands = []
    for raw in _HREF_RE.findall(html):
        h = apex(raw)
        if h and not is_excluded(h):
            cands.append(h)
    return _uniq(cands)


async def _localch(session, name: str, city: str) -> list[str]:
    what = urllib.parse.quote(clean_name(name))
    where = urllib.parse.quote(city or "")
    url = f"https://www.local.ch/de/q?what={what}&where={where}"
    html = await _get(session, url)
    if not html:
        return []
    cands: list[str] = []
    # explicit website URLs in the results JSON first (strongest), then contact emails
    for raw in _WEBSITE_JSON_RE.findall(html):
        h = apex(raw)
        if h and not is_excluded(h):
            cands.append(h)
    for addr in _EMAIL_RE.findall(html):
        h = email_apex(addr.lower())
        if h:
            cands.append(h)
    return _uniq(cands)


async def _gelbeseiten(session, name: str, city: str) -> list[str]:
    # 2-step: results page only carries the name; the dealer's website lives on the
    # business detail page (gsbiz/<uuid>). Follow the top match, then extract its
    # external site link. Throttle-resistant alternative to DDG for the big DE pool.
    q = urllib.parse.quote(clean_name(name))
    where = urllib.parse.quote(city or "")
    results = await _get(session, f"https://www.gelbeseiten.de/Suche/{q}/{where}")
    if not results:
        return []
    m = _GS_DETAIL_RE.search(results)
    if not m:
        return []
    detail = await _get(session, m.group(1))
    if not detail:
        return []
    cands = []
    for raw in _HREF_RE.findall(detail):
        h = apex(raw)
        if h and not is_excluded(h):
            cands.append(h)
    return _uniq(cands)


_PROVIDERS = {"pagesjaunes": _pagesjaunes, "localch": _localch, "gelbeseiten": _gelbeseiten}


async def directory_candidates(session, name: str, city: str, country: str) -> tuple[str, list[str]]:
    """
    (provider, ordered candidate apexes) from ``country``'s directory, or ("", []).

    The candidates carry name+city provenance (the directory matched them), so the
    resolver validates them leniently (name OR city on the homepage + automotive).
    """
    key = DIRECTORY_BY_COUNTRY.get((country or "").upper())
    if not key or not name:
        return "", []
    provider = _PROVIDERS[key]
    return key, await provider(session, name, city)
