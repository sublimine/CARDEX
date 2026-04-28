"""
Discovery orchestrator — fans out every source per country in parallel and
upserts candidate dicts into the `discovery_candidates` PG table.

Design contract
---------------
* Pure fan-out + sink. No Redis state, no streams, no enrichment, no spider
  publish. Sources are passive producers; the sink is idempotent upsert.
* Two upsert paths selected by the candidate shape:
    - domain-ful  →  ON CONFLICT (domain, country)   where domain IS NOT NULL
    - identity    →  ON CONFLICT (source, registry_id, country)
                     where domain IS NULL and registry_id IS NOT NULL
* On conflict the ONLY mutation is a `last_seen` heartbeat, and only when
  the existing row is stale (> 1 h). This satisfies the MVCC policy: no
  phantom updates of columns that already hold the same value.
* Rows without both domain and registry_id are dropped — they cannot be
  deduped and are useless downstream.

Usage
-----
    python -m scrapers.discovery.orchestrator
    DISCOVERY_COUNTRIES=FR,ES python -m scrapers.discovery.orchestrator

Environment
-----------
    DATABASE_URL          postgresql://... (default: local cardex dev)
    DISCOVERY_COUNTRIES   comma-separated ISO-2 codes (default: all 6)
    CC_INDEX_URL          override Common Crawl index snapshot
    ZEFIX_BASE_URL        override Zefix PublicREST base
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, AsyncIterator, Awaitable, Callable

import asyncpg
import httpx

from scrapers.discovery.sources.ch_zefix import ZefixSource
from scrapers.discovery.sources.common_crawl import CommonCrawlSource
from scrapers.discovery.sources.fr_sirene import SireneSource
from scrapers.discovery.sources.oem_bmw import BMWDealerSource
from scrapers.discovery.sources.osm import OSMSource
from scrapers.discovery.sources.portal_aggregator import PortalAggregatorSource

log = logging.getLogger(__name__)

_DEFAULT_COUNTRIES: tuple[str, ...] = ("DE", "ES", "FR", "NL", "BE", "CH")

_DEFAULT_DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://cardex:cardex@localhost:5432/cardex",
)

_STALE_INTERVAL = "1 hour"  # heartbeat granularity for last_seen updates


# ── SQL ──────────────────────────────────────────────────────────────────────

_INSERT_COLUMNS = (
    "domain, country, source_layer, source, url, "
    "name, address, city, postcode, phone, email, "
    "lat, lng, registry_id, external_refs"
)
_VALUE_PLACEHOLDERS = (
    "$1, $2, $3, $4, $5, "
    "$6, $7, $8, $9, $10, $11, "
    "$12, $13, $14, $15::jsonb"
)

_UPSERT_DOMAIN_SQL = f"""
INSERT INTO discovery_candidates ({_INSERT_COLUMNS})
VALUES ({_VALUE_PLACEHOLDERS})
ON CONFLICT (domain, country) WHERE domain IS NOT NULL
DO UPDATE SET last_seen = NOW()
WHERE discovery_candidates.last_seen < NOW() - INTERVAL '{_STALE_INTERVAL}'
"""

_UPSERT_IDENTITY_SQL = f"""
INSERT INTO discovery_candidates ({_INSERT_COLUMNS})
VALUES ({_VALUE_PLACEHOLDERS})
ON CONFLICT (source, registry_id, country)
    WHERE domain IS NULL AND registry_id IS NOT NULL
DO UPDATE SET last_seen = NOW()
WHERE discovery_candidates.last_seen < NOW() - INTERVAL '{_STALE_INTERVAL}'
"""


# ── Source registry ──────────────────────────────────────────────────────────

SourceFactory = Callable[[httpx.AsyncClient], Any]

# Sources keyed by logical name. Each factory returns a new instance with the
# shared httpx client injected. A source is country-gated by a predicate — if
# the predicate returns False, the source is skipped for that country.
_SOURCES: list[tuple[str, SourceFactory, Callable[[str], bool]]] = [
    # Layer 1 — OEM
    ("oem_bmw",       BMWDealerSource,        lambda c: c in _DEFAULT_COUNTRIES),
    # Layer 2 — Portal aggregators (each portal self-filters by country)
    ("portal",        PortalAggregatorSource, lambda c: True),
    # Layer 3 — Registries
    ("sirene",        SireneSource,           lambda c: c == "FR"),
    ("zefix",         ZefixSource,            lambda c: c == "CH"),
    # Layer 4 — OSM
    ("osm",           OSMSource,              lambda c: True),
    # Layer 5 — Common Crawl
    ("common_crawl",  CommonCrawlSource,      lambda c: True),
]


# ── Sink ─────────────────────────────────────────────────────────────────────

async def _upsert(pool: asyncpg.Pool, cand: dict) -> bool:
    """Route a candidate to the right upsert path. Returns True on INSERT/UPDATE."""
    domain = cand.get("domain")
    registry_id = cand.get("registry_id")
    if not domain and not registry_id:
        return False  # can't dedupe, drop

    params = (
        domain,
        cand.get("country"),
        cand.get("source_layer"),
        cand.get("source"),
        cand.get("url"),
        cand.get("name"),
        cand.get("address"),
        cand.get("city"),
        cand.get("postcode"),
        cand.get("phone"),
        cand.get("email"),
        cand.get("lat"),
        cand.get("lng"),
        registry_id,
        json.dumps(cand.get("external_refs") or {}),
    )

    sql = _UPSERT_DOMAIN_SQL if domain else _UPSERT_IDENTITY_SQL

    try:
        await pool.execute(sql, *params)
        return True
    except Exception as exc:
        log.warning(
            "discovery: upsert failed source=%s name=%r: %s",
            cand.get("source"),
            (cand.get("name") or "")[:60],
            exc,
        )
        return False


# ── Drain loops ──────────────────────────────────────────────────────────────

async def _drain_source(
    name: str,
    source: Any,
    country: str,
    pool: asyncpg.Pool,
    stats: dict[str, int],
) -> None:
    key = f"{country}:{name}"
    seen = 0
    written = 0
    try:
        async for cand in source.discover(country):
            seen += 1
            if await _upsert(pool, cand):
                written += 1
            if seen % 500 == 0:
                log.info(
                    "discovery: %s — progress: %d seen / %d written",
                    key, seen, written,
                )
    except Exception as exc:
        log.warning("discovery: %s — source errored: %s", key, exc)
    stats[key] = written
    log.info("discovery: %s — done: %d seen / %d written", key, seen, written)


async def _run_country(
    country: str,
    client: httpx.AsyncClient,
    pool: asyncpg.Pool,
    stats: dict[str, int],
) -> None:
    tasks = []
    for name, factory, gate in _SOURCES:
        if not gate(country):
            continue
        source = factory(client)
        tasks.append(_drain_source(name, source, country, pool, stats))
    await asyncio.gather(*tasks)


# ── Entry point ──────────────────────────────────────────────────────────────

async def run(countries: list[str] | None = None) -> dict[str, int]:
    countries = countries or list(_DEFAULT_COUNTRIES)
    stats: dict[str, int] = {}

    pool = await asyncpg.create_pool(
        _DEFAULT_DSN,
        min_size=2,
        max_size=8,
        command_timeout=60,
    )
    try:
        async with httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=True,
            limits=httpx.Limits(
                max_keepalive_connections=32,
                max_connections=64,
            ),
        ) as client:
            await asyncio.gather(*[
                _run_country(c, client, pool, stats)
                for c in countries
            ])
    finally:
        await pool.close()

    total = sum(stats.values())
    log.info("discovery: complete — %d candidates written", total)
    for k in sorted(stats):
        log.info("  %-32s %d", k, stats[k])
    return stats


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    raw = os.environ.get("DISCOVERY_COUNTRIES", "").strip()
    countries = [c.strip().upper() for c in raw.split(",") if c.strip()] or None
    asyncio.run(run(countries=countries))


if __name__ == "__main__":
    main()
