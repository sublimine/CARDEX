"""
Discovery Orchestrator — 7-layer dealer discovery system.

Runs all discovery layers in parallel, deduplicates via Redis bloom filter,
enriches each dealer (coords, website), and upserts into the `dealers` table.
Then publishes each dealer to stream:dealer_discovered for the spider fleet.

Discovery layers (all run concurrently per country):
  Layer 1 — H3 Adaptive Grid (Google Maps, res-7/8, multi-query)
  Layer 2 — OpenStreetMap Overpass API (shop=car*)
  Layer 3 — Government registry per country:
             FR: INSEE SIRENE (NAF 4511Z)
             NL: KVK (SBI 4511)
             BE: BCE (NACE 4511)
             CH: Zefix (NOGA 4511)
             DE: Gelbe Seiten (Autohaus / KFZ Händler, all PLZ prefixes)
             ES: Páginas Amarillas (all 52 provinces)

Layer 4 — Cross-reference enrichment (geocoding + website discovery)
Layer 5 — Deduplication (Redis bloom filter + fingerprint hash)
Layer 6 — DB upsert into `dealers` table (PostgreSQL)
Layer 7 — Publish to stream:dealer_discovered for spider fleet pickup

Expected scale:
  H3 res-7 hexes per country:  ES ~340k, FR ~460k, DE ~590k, NL ~60k, BE ~40k, CH ~55k
  Total hexes: ~1.5M
  Queries per hex: 8 text + 2 nearby = 10
  Pages per query: avg 1.3
  Total Google API calls: ~19.5M (over multiple weeks — not a burst)
  Government registry records: ~200,000 unique dealers
  OSM records: ~80,000 nodes
  Expected total unique dealers: ~400,000–600,000 across 6 countries
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import AsyncGenerator

import aiohttp
from redis.asyncio import Redis

from scrapers.discovery.h3_grid import H3AdaptiveGridCrawler
from scrapers.discovery.osm_overpass import OSMOverpassCrawler
from scrapers.discovery.enricher import DealerEnricher
from scrapers.discovery.registries.fr_sirene import FRSIRENECrawler
from scrapers.discovery.registries.nl_kvk import NLKVKCrawler
from scrapers.discovery.registries.be_bce import BEBCECrawler
from scrapers.discovery.registries.ch_zefix import CHZefixCrawler
from scrapers.discovery.registries.de_handelsregister import DEHandelsregisterCrawler
from scrapers.discovery.registries.es_aeoc import ESAEOCCrawler

log = logging.getLogger(__name__)

_COUNTRIES = ["ES", "FR", "DE", "NL", "BE", "CH"]
_STREAM_DEALER_DISCOVERED = "stream:dealer_discovered"

# Maps country → registry crawler class
_REGISTRY_CRAWLERS = {
    "FR": FRSIRENECrawler,
    "NL": NLKVKCrawler,
    "BE": BEBCECrawler,
    "CH": CHZefixCrawler,
    "DE": DEHandelsregisterCrawler,
    "ES": ESAEOCCrawler,
}

_GMAPS_PLACE_TYPES = {"car_dealer", "car_repair"}


class DiscoveryOrchestrator:
    """
    Runs all 7 discovery layers and upserts every found dealer into
    the database + Redis stream for spider pickup.
    """

    def __init__(self, rdb: Redis, pg_pool, gmaps_api_key: str = ""):
        self.rdb = rdb
        self.pg = pg_pool
        self.gmaps_key = gmaps_api_key

    async def run(self, countries: list[str] | None = None) -> None:
        targets = countries or _COUNTRIES
        log.info("discovery: starting for countries=%s", targets)

        async with aiohttp.ClientSession() as session:
            enricher = DealerEnricher(self.rdb, session, self.gmaps_key)

            # Run all countries concurrently
            await asyncio.gather(*[
                self._run_country(country, session, enricher)
                for country in targets
            ])

        log.info("discovery: all layers complete")

    async def _run_country(
        self, country: str, session: aiohttp.ClientSession, enricher: DealerEnricher
    ) -> None:
        log.info("discovery: starting country=%s", country)

        # All layers run concurrently and feed into a shared queue
        # Bounded queue with backpressure — feeders block when consumer is slow
        queue: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=2000)
        feeder_count = 0

        async def feed_queue(gen) -> None:
            nonlocal feeder_count
            feeder_count += 1
            try:
                async for item in gen:
                    await queue.put(item)
            except Exception as exc:
                log.warning("discovery layer error country=%s: %s", country, exc)
            finally:
                # Each finished feeder sends one sentinel
                await queue.put(None)

        # Spawn all layers as background tasks
        h3_crawler = H3AdaptiveGridCrawler(self.rdb, session)
        osm_crawler = OSMOverpassCrawler(self.rdb, session)
        registry_cls = _REGISTRY_CRAWLERS.get(country)

        asyncio.create_task(feed_queue(
            self._gmaps_to_dealer(h3_crawler.crawl_country(country), country)
        ))
        asyncio.create_task(feed_queue(
            osm_crawler.crawl_country(country)
        ))

        if registry_cls:
            registry = registry_cls(self.rdb, session)
            asyncio.create_task(feed_queue(registry.crawl()))
        else:
            feeder_count -= 1  # one less feeder; pre-decrement before tasks start

        # Process queue until all feeders have sent their sentinel
        processed = 0
        sentinels_received = 0
        # feeder_count was incremented inside feed_queue — wait for all to finish
        expected_sentinels = (3 if registry_cls else 2)

        while sentinels_received < expected_sentinels:
            try:
                dealer = await asyncio.wait_for(queue.get(), timeout=300.0)
            except asyncio.TimeoutError:
                log.warning("discovery: %s — queue timeout, stopping", country)
                break

            if dealer is None:
                sentinels_received += 1
                continue

            # Deduplicate (atomic Redis SET NX)
            if await enricher.is_duplicate(dealer):
                continue

            # Enrich: geocode + website discovery
            try:
                dealer = await enricher.enrich(dealer)
            except Exception as exc:
                log.debug("enrich failed for %s: %s", dealer.get("name"), exc)
                # Upsert anyway — partial data is better than no data

            # Upsert to DB
            try:
                await self._upsert_dealer(dealer)
            except Exception as exc:
                log.warning("dealer upsert failed name=%s: %s", dealer.get("name"), exc)
                continue

            # Publish to spider stream only if website discovered
            if dealer.get("website"):
                try:
                    await self._publish_to_spider(dealer)
                except Exception as exc:
                    log.warning("spider publish failed: %s", exc)

            processed += 1
            if processed % 1000 == 0:
                log.info("discovery: %s — %d dealers processed", country, processed)

        log.info("discovery: %s — DONE — %d total dealers", country, processed)

    @staticmethod
    async def _gmaps_to_dealer(gen: AsyncGenerator, country: str) -> AsyncGenerator[dict, None]:
        """Convert raw Google Maps place dicts to our dealer format."""
        async for place in gen:
            yield {
                "source": "google_maps",
                "place_id": place.get("place_id"),
                "name": place.get("name"),
                "country": country,
                "lat": place.get("geometry", {}).get("location", {}).get("lat"),
                "lng": place.get("geometry", {}).get("location", {}).get("lng"),
                "address": place.get("formatted_address"),
                "city": _extract_city(place),
                "postcode": _extract_postcode(place),
                "website": place.get("website"),
                "phone": place.get("formatted_phone_number") or place.get("international_phone_number"),
                "types": place.get("types", []),
                "rating": place.get("rating"),
                "user_ratings_total": place.get("user_ratings_total"),
                "raw": place,
            }

    async def _upsert_dealer(self, dealer: dict) -> None:
        # Parameters: $1…$15 (place_id, name, country, lat, lng, address, city,
        # postcode, website, phone, email, h3_res7, h3_res4, source, registry_id)
        # discovery_sources initialized as ARRAY[$14] where $14 = source
        await self.pg.execute("""
            INSERT INTO dealers (
                place_id, name, country, lat, lng, address, city, postcode,
                website, phone, email, h3_res7, h3_res4,
                source, registry_id, discovery_sources,
                spider_status, created_at, updated_at
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,
                $14,$15,
                ARRAY[$14]::text[], 'PENDING', now(), now()
            )
            ON CONFLICT ON CONSTRAINT dealers_unique
            DO UPDATE SET
                website           = COALESCE(EXCLUDED.website, dealers.website),
                phone             = COALESCE(EXCLUDED.phone, dealers.phone),
                lat               = COALESCE(EXCLUDED.lat, dealers.lat),
                lng               = COALESCE(EXCLUDED.lng, dealers.lng),
                h3_res7           = COALESCE(EXCLUDED.h3_res7, dealers.h3_res7),
                h3_res4           = COALESCE(EXCLUDED.h3_res4, dealers.h3_res4),
                discovery_sources = (
                    SELECT array_agg(DISTINCT s)
                    FROM unnest(dealers.discovery_sources || ARRAY[EXCLUDED.source]) s
                ),
                updated_at        = now()
        """,
            dealer.get("place_id"),
            dealer.get("name"),
            dealer.get("country"),
            dealer.get("lat"),
            dealer.get("lng"),
            dealer.get("address"),
            dealer.get("city"),
            dealer.get("postcode"),
            dealer.get("website"),
            dealer.get("phone"),
            dealer.get("email"),
            dealer.get("h3_res7"),
            dealer.get("h3_res4"),
            dealer.get("source"),
            dealer.get("registry_id"),
        )

    async def _publish_to_spider(self, dealer: dict) -> None:
        """Publish dealer to stream:dealer_discovered for spider fleet."""
        await self.rdb.xadd(
            _STREAM_DEALER_DISCOVERED,
            {
                "dealer_id":   dealer.get("registry_id") or dealer.get("place_id") or dealer.get("name", ""),
                "name":        dealer.get("name", ""),
                "country":     dealer.get("country", ""),
                "website":     dealer.get("website", ""),
                "lat":         str(dealer.get("lat") or ""),
                "lng":         str(dealer.get("lng") or ""),
                "source":      dealer.get("source", ""),
            },
        )


def _extract_city(place: dict) -> str | None:
    for comp in place.get("address_components") or []:
        if "locality" in comp.get("types", []):
            return comp.get("long_name")
    return None


def _extract_postcode(place: dict) -> str | None:
    for comp in place.get("address_components") or []:
        if "postal_code" in comp.get("types", []):
            return comp.get("long_name")
    return None


async def run() -> None:
    """Entry point for run_scraper.py target 'discovery'."""
    import os
    from redis.asyncio import from_url as redis_from_url
    import asyncpg

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    rdb = redis_from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))
    pg = await asyncpg.create_pool(
        os.environ.get("DATABASE_URL", "postgresql://cardex:cardex@localhost:5432/cardex")
    )

    countries_env = os.environ.get("DISCOVERY_COUNTRIES", "")
    countries = countries_env.split(",") if countries_env else None

    orchestrator = DiscoveryOrchestrator(
        rdb=rdb,
        pg_pool=pg,
        gmaps_api_key=os.environ.get("GOOGLE_MAPS_API_KEY", ""),
    )
    await orchestrator.run(countries=countries)
    await pg.close()
    await rdb.aclose()
