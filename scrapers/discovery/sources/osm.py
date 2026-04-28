"""
OpenStreetMap Overpass dealer discovery.

OSM is a free public geographic database. Every car dealer that has been
mapped by a volunteer is discoverable via the Overpass API without auth or
rate limits (beyond normal politeness). We query by country boundary with
a single Overpass QL statement that collects all nodes/ways/relations
tagged as motor trade:

    shop=car, shop=car_dealer, trade=cars, shop=second_hand + car context

Output dict shape matches discovery_candidates. Identity is keyed by the
OSM element id (e.g. "node/123456789") so repeat sweeps dedupe naturally.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

import httpx

log = logging.getLogger(__name__)

_OVERPASS_ENDPOINTS: tuple[str, ...] = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)

# Overpass area id = 3_600_000_000 + OSM relation id for the country boundary.
_COUNTRY_AREA_IDS: dict[str, int] = {
    "ES": 3_600_000_000 + 1_311_341,  # Spain
    "FR": 3_600_000_000 + 2_202_162,  # France (metropolitan)
    "DE": 3_600_000_000 + 51_477,     # Germany
    "NL": 3_600_000_000 + 47_796,     # Netherlands
    "BE": 3_600_000_000 + 52_411,     # Belgium
    "CH": 3_600_000_000 + 51_701,     # Switzerland
}

_QUERY_TEMPLATE = """
[out:json][timeout:300];
area({area_id})->.searchArea;
(
  node["shop"="car"](area.searchArea);
  node["shop"="car_dealer"](area.searchArea);
  node["trade"="cars"](area.searchArea);
  node["shop"="second_hand"]["car"](area.searchArea);
  way["shop"="car"](area.searchArea);
  way["shop"="car_dealer"](area.searchArea);
  way["trade"="cars"](area.searchArea);
  relation["shop"="car"](area.searchArea);
  relation["shop"="car_dealer"](area.searchArea);
);
out body center qt;
""".strip()


class OSMSource:
    """
    Yields motor-trade candidates from OpenStreetMap for a given country.
    """

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def discover(self, country: str) -> AsyncIterator[dict]:
        area_id = _COUNTRY_AREA_IDS.get(country)
        if not area_id:
            log.warning("osm: no area id for country %s", country)
            return

        query = _QUERY_TEMPLATE.format(area_id=area_id)
        data: dict | None = None

        for endpoint in _OVERPASS_ENDPOINTS:
            try:
                resp = await self._client.post(
                    endpoint,
                    data={"data": query},
                    headers={"Accept": "application/json"},
                    timeout=360.0,
                )
                if resp.status_code != 200:
                    log.debug("osm: %s HTTP %d", endpoint, resp.status_code)
                    continue
                data = resp.json()
                break
            except Exception as exc:
                log.warning("osm: endpoint %s failed: %s", endpoint, exc)
                continue

        if not data:
            log.error("osm: all endpoints failed for %s", country)
            return

        elements = data.get("elements") or []
        log.info("osm: %s — %d elements", country, len(elements))

        for el in elements:
            cand = _to_candidate(el, country)
            if cand:
                yield cand


def _to_candidate(el: dict, country: str) -> dict | None:
    tags = el.get("tags") or {}
    name = (tags.get("name") or tags.get("brand") or tags.get("operator") or "").strip()
    if not name:
        return None

    if el.get("type") == "node":
        lat = el.get("lat")
        lng = el.get("lon")
    else:
        center = el.get("center") or {}
        lat = center.get("lat")
        lng = center.get("lon")

    if lat is None or lng is None:
        return None

    website = _normalize(
        tags.get("website")
        or tags.get("url")
        or tags.get("contact:website")
    )
    domain = _domain(website)

    osm_id = f"{el.get('type')}/{el.get('id')}"

    return {
        "domain":       domain,
        "country":      country,
        "source_layer": 4,
        "source":       "osm",
        "url":          website,
        "name":         name,
        "address":      _build_address(tags),
        "city":         tags.get("addr:city"),
        "postcode":     tags.get("addr:postcode"),
        "phone":        (
            tags.get("phone")
            or tags.get("contact:phone")
            or tags.get("contact:mobile")
        ),
        "email":        tags.get("email") or tags.get("contact:email"),
        "lat":          float(lat),
        "lng":          float(lng),
        "registry_id":  osm_id,
        "external_refs": {
            "brand":          tags.get("brand"),
            "operator":       tags.get("operator"),
            "opening_hours":  tags.get("opening_hours"),
        },
    }


def _build_address(tags: dict) -> str | None:
    parts = [
        tags.get("addr:street"),
        tags.get("addr:housenumber"),
        tags.get("addr:postcode"),
        tags.get("addr:city"),
    ]
    parts = [p for p in parts if p]
    return ", ".join(parts) if parts else None


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
