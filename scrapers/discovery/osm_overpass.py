"""
OpenStreetMap Overpass API Crawler — FREE, no API key, institutionally maintained.

OSM is the world's most complete public geographic database, maintained by
millions of volunteers. Every car dealer in Europe that has ever been tagged
on OSM is discoverable here. This is completely independent of Google.

Relevant OSM tags:
  shop=car               — primary tag for car dealers
  shop=car_dealer        — alias
  trade=cars             — wholesale/trade dealer
  amenity=car_rental     — often also sell
  shop=second_hand       + car/vehicle categories
  landuse=garage         — dealer lots
  building=garage        + dealer context

Overpass query: get ALL nodes, ways, and relations with shop=car* across
the entire country bounding box in a single batch request.
Response: GeoJSON-style OverpassJSON with all OSM tags preserved.

No rate limit issues — Overpass is designed for batch queries.
Single query per country returns tens of thousands of results.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

import aiohttp

log = logging.getLogger(__name__)

_OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",   # mirror 1
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",  # mirror 2
]

_COUNTRY_ISO: dict[str, str] = {
    "ES": "ES", "FR": "FR", "DE": "DE",
    "NL": "NL", "BE": "BE", "CH": "CH",
}

# ISO 3166-1 alpha-2 → Nominatim area ID (3600000000 + OSM relation ID)
# These are stable OSM relation IDs for each country boundary
_COUNTRY_AREA_IDS: dict[str, int] = {
    "ES": 3600001311,   # Spain
    "FR": 3600000000 + 2202162,  # France (metropolitan)
    "DE": 3600000000 + 51477,    # Germany
    "NL": 3600000000 + 47796,    # Netherlands
    "BE": 3600000000 + 52411,    # Belgium
    "CH": 3600000000 + 51701,    # Switzerland
}

# Overpass QL query template — fetches every node/way/relation tagged as car dealer
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
"""


class OSMOverpassCrawler:
    """
    Downloads ALL car dealers from OpenStreetMap for a country in one batch.
    No pagination — Overpass returns everything in a single response.
    Result: list of OSM elements with tags, lat/lon, name, website, phone, etc.
    """

    def __init__(self, rdb, session: aiohttp.ClientSession):
        self.rdb = rdb
        self.session = session

    async def _is_country_done(self, country: str) -> bool:
        key = f"discovery:osm_done:{country}"
        return bool(await self.rdb.exists(key))

    async def _mark_country_done(self, country: str) -> None:
        key = f"discovery:osm_done:{country}"
        # 7-day TTL — OSM data updates weekly
        await self.rdb.set(key, "1", ex=7 * 86400)

    async def crawl_country(self, country: str) -> AsyncGenerator[dict, None]:
        if await self._is_country_done(country):
            log.info("osm: %s already done (within 7 days)", country)
            return

        area_id = _COUNTRY_AREA_IDS.get(country)
        if not area_id:
            log.warning("osm: no area_id for country %s", country)
            return

        query = _QUERY_TEMPLATE.format(area_id=area_id).strip()
        log.info("osm: fetching all car dealers in %s (area=%d)…", country, area_id)

        data = None
        for endpoint in _OVERPASS_ENDPOINTS:
            try:
                async with self.session.post(
                    endpoint,
                    data={"data": query},
                    timeout=aiohttp.ClientTimeout(total=360),
                    headers={"Accept": "application/json"},
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)
                    break
            except Exception as exc:
                log.warning("osm endpoint %s failed: %s — trying next", endpoint, exc)
                await asyncio.sleep(2)
                continue

        if not data:
            log.error("osm: all endpoints failed for %s", country)
            return

        elements = data.get("elements") or []
        log.info("osm: %s — %d elements found", country, len(elements))

        for el in elements:
            dealer = self._parse_element(el, country)
            if dealer:
                yield dealer

        await self._mark_country_done(country)

    @staticmethod
    def _parse_element(el: dict, country: str) -> dict | None:
        """Convert OSM element to dealer dict compatible with our dealers table."""
        tags = el.get("tags") or {}

        name = tags.get("name") or tags.get("brand") or tags.get("operator")
        if not name:
            return None

        # Coordinates: node has lat/lon directly; ways/relations have 'center'
        if el.get("type") == "node":
            lat = el.get("lat")
            lng = el.get("lon")
        else:
            center = el.get("center") or {}
            lat = center.get("lat")
            lng = center.get("lon")

        if lat is None or lng is None:
            return None

        return {
            "source": "osm",
            "osm_id": f"{el.get('type')}/{el.get('id')}",
            "name": name,
            "country": country,
            "lat": float(lat),
            "lng": float(lng),
            "website": (
                tags.get("website")
                or tags.get("url")
                or tags.get("contact:website")
            ),
            "phone": (
                tags.get("phone")
                or tags.get("contact:phone")
                or tags.get("contact:mobile")
            ),
            "email": tags.get("email") or tags.get("contact:email"),
            "address": _build_address(tags),
            "city": tags.get("addr:city"),
            "postcode": tags.get("addr:postcode"),
            "brand": tags.get("brand"),
            "opening_hours": tags.get("opening_hours"),
            "raw_tags": tags,
        }


def _build_address(tags: dict) -> str | None:
    parts = []
    if tags.get("addr:street"):
        parts.append(tags["addr:street"])
    if tags.get("addr:housenumber"):
        parts.append(tags["addr:housenumber"])
    if tags.get("addr:postcode"):
        parts.append(tags["addr:postcode"])
    if tags.get("addr:city"):
        parts.append(tags["addr:city"])
    return ", ".join(parts) if parts else None
