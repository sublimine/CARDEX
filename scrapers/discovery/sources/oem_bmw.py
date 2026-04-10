"""
BMW dealer discovery — verified endpoint.

BMW Group exposes its full dealer network for all markets through the
Stocklocator backend (STOLO) at:

    https://stolo-data-service.prod.stolo.eu-central-1.aws.bmw.cloud/dealer/showAll

This is pure HTTP GET, no auth, no cookies, no CSRF — the endpoint is
consumed by the public bmw.XX/sl/gebrauchtwagen pages. Response is a JSON
document with an `includedDealers` array containing every authorized BMW
dealer for the requested country.

Yielded dealers usually expose `name`, `city`, `postalCode`,
`attributes.distributionPartnerId`. Lat/lng and website may also be present
depending on market — we opportunistically copy any field we can recognise.

No website is exposed by this endpoint: BMW franchise dealers don't publish
independent inventory pages, all stock lives on the BMW Stocklocator. For
our discovery pipeline this is still useful as an IDENTITY source — the DDG
resolver can take name+city+country and try to find the dealer's own site
(which many BMW dealers run alongside the corporate stocklocator).

Verified: 2026-04-07
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

import httpx

log = logging.getLogger(__name__)

_BMW_STOLO_BASE = "https://stolo-data-service.prod.stolo.eu-central-1.aws.bmw.cloud"
_BMW_DEALERS_URL = f"{_BMW_STOLO_BASE}/dealer/showAll"

# STOLO language codes per country (lang separator uses underscore, not dash).
_LANG = {
    "DE": "de_DE",
    "ES": "es_ES",
    "FR": "fr_FR",
    "NL": "nl_NL",
    "BE": "fr_BE",
    "CH": "de_CH",
}

# Category "BM" = BMW brand; "MI" = MINI. We query BMW for now; MINI can be
# added by running the same endpoint with category="MI".
_CATEGORY = "BM"

_HEADERS = {
    "Accept": "application/json",
    "Origin": "https://www.bmw.de",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}


class BMWDealerSource:
    """
    Yields BMW authorized dealers per country from the STOLO public endpoint.
    """

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def discover(self, country: str) -> AsyncIterator[dict]:
        lang = _LANG.get(country)
        if not lang:
            return

        try:
            resp = await self._client.get(
                _BMW_DEALERS_URL,
                params={
                    "country": country,
                    "category": _CATEGORY,
                    "clientid": "66_STOCK_DLO",
                    "language": lang,
                    "slg": "true",
                },
                headers=_HEADERS,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            log.warning("oem_bmw: %s request failed: %s", country, exc)
            return

        dealers = data.get("includedDealers") or []
        count = 0
        for d in dealers:
            cand = _parse_dealer(d, country)
            if cand:
                count += 1
                yield cand

        log.info("oem_bmw: %s — %d dealers", country, count)


def _parse_dealer(d: dict, country: str) -> dict | None:
    name = (d.get("name") or "").strip()
    if not name:
        return None

    attrs = d.get("attributes") or {}
    key = d.get("key") or ""
    dist_id = attrs.get("distributionPartnerId") or ""

    lat = _maybe_float(d.get("latitude") or d.get("lat") or attrs.get("latitude"))
    lng = _maybe_float(d.get("longitude") or d.get("lng") or attrs.get("longitude"))

    website = (
        d.get("website")
        or d.get("url")
        or attrs.get("website")
        or attrs.get("url")
    )
    website = _normalize(website)
    domain = _domain(website)

    return {
        "domain": domain,
        "country": country,
        "source": "oem:bmw",
        "url": website,
        "name": name,
        "city": d.get("city") or None,
        "postcode": d.get("postalCode") or None,
        "address": d.get("street") or attrs.get("street") or None,
        "phone": d.get("phone") or attrs.get("phone") or None,
        "lat": lat,
        "lng": lng,
        "oem_key": key or None,
        "oem_partner_id": dist_id or None,
    }


def _maybe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _normalize(url) -> str | None:
    if not url:
        return None
    url = str(url).strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    import urllib.parse
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return None
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or None
