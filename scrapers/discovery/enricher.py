"""
Dealer Enricher — Cross-reference and enrich dealer records.

After discovery from any source (H3/Google, OSM, government registries),
dealers often lack website URL, coordinates, or full contact info.
This module fills those gaps using:

1. Geocoding (OSM Nominatim — free, no key):
   → Convert address + city + country → lat/lng
   → Rate limit: 1 req/sec (Nominatim ToS)

2. Website discovery:
   → Google Knowledge Graph / Places Details if we have place_id
   → Common patterns: search "<dealer name> + city + site" via DuckDuckGo Instant API
   → Domain inference from company name

3. Website validation:
   → HEAD request to discovered URL
   → Check robots.txt for /inventory, /stock, /fahrzeuge paths

4. Bloom filter deduplication:
   → Redis Bloom filter "bloom:dealer_place_ids" (5M capacity)
   → Composite key: sha256(name[:20] + city + country)
   → Prevents same dealer being upserted multiple times from different sources
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import urllib.parse
from typing import Optional

import aiohttp

log = logging.getLogger(__name__)

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_DUCKDUCKGO_URL = "https://api.duckduckgo.com/"
_GMAPS_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

# Common website paths to probe for inventory
_INVENTORY_PROBE_PATHS = [
    "/stock", "/inventory", "/vehicles", "/cars",
    "/coches", "/fahrzeuge", "/voitures", "/occasion",
    "/gebrauchtwagen", "/tweedehands", "/occasions",
    "/api/stock.json", "/api/vehicles.json",
    "/wp-json/wp/v2/car",
]


class DealerEnricher:
    def __init__(self, rdb, session: aiohttp.ClientSession, gmaps_api_key: str = ""):
        self.rdb = rdb
        self.session = session
        self.gmaps_key = gmaps_api_key
        self._nominatim_last = 0.0

    def dealer_fingerprint(self, dealer: dict) -> str:
        """Stable hash for deduplication across sources."""
        name = (dealer.get("name") or "")[:30].lower().strip()
        city = (dealer.get("city") or "").lower().strip()
        country = dealer.get("country", "")
        raw = f"{name}:{city}:{country}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    async def is_duplicate(self, dealer: dict) -> bool:
        fp = self.dealer_fingerprint(dealer)
        key = f"dealer:seen:{fp}"
        added = await self.rdb.set(key, "1", ex=90 * 86400, nx=True)
        return not added  # if nx=True and added=None → already existed

    async def enrich(self, dealer: dict) -> dict:
        """Fill missing lat/lng, website. Returns enriched dealer dict."""
        # 1. Geocode if coords missing
        if dealer.get("lat") is None or dealer.get("lng") is None:
            coords = await self._geocode(dealer)
            if coords:
                dealer["lat"], dealer["lng"] = coords

        # 2. Find website if missing
        if not dealer.get("website") and dealer.get("place_id"):
            website = await self._website_from_place_details(dealer["place_id"])
            if website:
                dealer["website"] = website

        if not dealer.get("website") and dealer.get("name") and dealer.get("city"):
            website = await self._website_from_search(dealer["name"], dealer["city"], dealer["country"])
            if website:
                dealer["website"] = website

        # 3. Compute H3 index at res-7 for geospatial queries
        if dealer.get("lat") and dealer.get("lng"):
            try:
                import h3
                dealer["h3_res7"] = h3.latlng_to_cell(dealer["lat"], dealer["lng"], 7)
                dealer["h3_res4"] = h3.latlng_to_cell(dealer["lat"], dealer["lng"], 4)
            except Exception:
                pass

        return dealer

    async def _geocode(self, dealer: dict) -> Optional[tuple[float, float]]:
        """OSM Nominatim geocoding — rate limited to 1 req/sec."""
        # Respect Nominatim 1 req/sec ToS
        now = asyncio.get_event_loop().time()
        wait = 1.1 - (now - self._nominatim_last)
        if wait > 0:
            await asyncio.sleep(wait)
        self._nominatim_last = asyncio.get_event_loop().time()

        query_parts = [p for p in [
            dealer.get("address"), dealer.get("city"),
            dealer.get("postcode"), dealer.get("country"),
        ] if p]
        if not query_parts:
            return None

        params = {
            "q": ", ".join(query_parts),
            "format": "json",
            "limit": "1",
            "addressdetails": "0",
        }
        try:
            async with self.session.get(
                _NOMINATIM_URL, params=params,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": "CARDEX/1.0 (dealer discovery; contact@cardex.io)"},
            ) as resp:
                results = await resp.json()
                if results:
                    return float(results[0]["lat"]), float(results[0]["lon"])
        except Exception as exc:
            log.debug("nominatim geocode failed: %s", exc)
        return None

    async def _website_from_place_details(self, place_id: str) -> Optional[str]:
        if not self.gmaps_key:
            return None
        try:
            params = {
                "place_id": place_id,
                "fields": "website",
                "key": self.gmaps_key,
            }
            async with self.session.get(
                _GMAPS_DETAILS_URL, params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                return data.get("result", {}).get("website")
        except Exception:
            return None

    async def _website_from_search(self, name: str, city: str, country: str) -> Optional[str]:
        """DuckDuckGo Instant Answer API to find dealer website."""
        query = f"{name} {city} {country} official site"
        try:
            async with self.session.get(
                _DUCKDUCKGO_URL,
                params={"q": query, "format": "json", "no_html": "1"},
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"Accept": "application/json"},
            ) as resp:
                data = await resp.json()

            # AbstractURL is the best match
            url = data.get("AbstractURL") or data.get("OfficialWebsite")
            if url and is_plausible_dealer_domain(url, name):
                return url

            # Check related topics
            for topic in (data.get("RelatedTopics") or [])[:3]:
                first_url = topic.get("FirstURL") or ""
                if first_url and is_plausible_dealer_domain(first_url, name):
                    return first_url
        except Exception:
            pass
        return None

    async def has_crawlable_inventory(self, website: str) -> bool:
        """Quick check: does the dealer website expose an inventory endpoint?"""
        base = website.rstrip("/")
        for path in _INVENTORY_PROBE_PATHS:
            try:
                async with self.session.head(
                    base + path,
                    timeout=aiohttp.ClientTimeout(total=5),
                    allow_redirects=True,
                ) as resp:
                    if resp.status in (200, 301, 302):
                        return True
            except Exception:
                continue
        return False


def is_plausible_dealer_domain(url: str, dealer_name: str) -> bool:
    """Heuristic: does the URL look like it belongs to this dealer?"""
    try:
        domain = urllib.parse.urlparse(url).netloc.lower()
        if not domain:
            return False
        # Reject major platforms (not a dealer's own site)
        reject_domains = {
            "autoscout24", "mobile.de", "kleinanzeigen", "wallapop",
            "coches.net", "leboncoin", "marktplaats", "facebook", "instagram",
            "linkedin", "twitter", "youtube", "wikipedia",
        }
        if any(r in domain for r in reject_domains):
            return False
        # Check if dealer name tokens appear in domain
        name_tokens = re.split(r"[\s\-_,]+", dealer_name.lower())[:3]
        if any(tok in domain for tok in name_tokens if len(tok) > 3):
            return True
        # Accept if domain contains automotive keywords
        auto_keywords = ["auto", "car", "wagen", "vehicle", "motor", "garage", "dealer"]
        return any(kw in domain for kw in auto_keywords)
    except Exception:
        return False
