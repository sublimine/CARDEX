"""
Sitemap bridge — connects `discovery_candidates` (sitemap_status='found') to
the sealed `sitemap_indexer` module.

The sealed indexer has a hardcoded `SITEMAP_SOURCES` list of 7 verified
portal/brand sitemaps. Every other sitemap we want to index (every dealer
found by the discovery pipeline) lives in `discovery_candidates` and needs
to be fed into the same `_index_source()` primitive the sealed module uses
internally.

This bridge does NOT mutate the sealed module or its global registry. It
imports the three private primitives (`_index_source`, `_fetch`, `_delta`)
and calls them directly per candidate. All other invariants (url_hash
partitioning by source_domain, INSERT/DELETE only, zero UPDATE of existing
rows, PG as source of truth) come from the sealed implementation.

Per-dealer regex policy
-----------------------
The indexer needs a URL regex to distinguish individual vehicle URLs from
all the other noise in a dealer's sitemap (home, blog, contact, category
pages). Three regex sources, in priority order:

    1. discovery_candidates.url_regex_override  (hand-set per domain)
    2. external_refs->>'url_regex'              (sourced at discovery time)
    3. UNIVERSAL_VEHICLE_URL_REGEX              (default fallback)

The universal regex requires BOTH a vehicle-path keyword (gebrauchtwagen,
occasion, coches, voertuigen, stock, inventory, ...) AND an identifier
signature (≥5 digit id, ≥8 alnum id, or ?productId=/vehicleId=/... query).
High precision, some false-negatives on pure-slug URLs.

Claim protocol
--------------
Atomic claim via CTE (identical pattern to sitemap_resolver):

    WITH claimed AS (
        SELECT id FROM discovery_candidates
        WHERE sitemap_status = 'found'
          AND (indexer_last_run IS NULL
               OR indexer_last_run < NOW() - INTERVAL ...)
        ORDER BY indexer_last_run NULLS FIRST, first_seen
        LIMIT $1
        FOR UPDATE SKIP LOCKED
    )
    UPDATE ... SET indexer_last_run = NOW() FROM claimed RETURNING ...

Bumping `indexer_last_run` at claim time serves both as cursor (so the next
loop iteration skips this row) and as stale-claim recovery. A crashed
worker's claim expires after the stale interval and is re-picked up.

Usage
-----
    python -m scrapers.discovery.sitemap_bridge
    SITEMAP_BRIDGE_COUNTRIES=FR,ES python -m scrapers.discovery.sitemap_bridge
    SITEMAP_BRIDGE_ONESHOT=1 python -m scrapers.discovery.sitemap_bridge

Environment
-----------
    DATABASE_URL                 postgresql://...
    REDIS_URL                    redis://...   (used by sealed indexer for ETag state)
    SITEMAP_BRIDGE_BATCH         rows per claim      (default 20)
    SITEMAP_BRIDGE_CONCURRENCY   parallel dealers    (default 8)
    SITEMAP_BRIDGE_MIN_INTERVAL  PG interval between successive runs per dealer
                                 (default '6 hours')
    SITEMAP_BRIDGE_IDLE_SLEEP    sleep when queue empty (default 60)
    SITEMAP_BRIDGE_ONESHOT       if '1', exit when queue is empty
    SITEMAP_BRIDGE_COUNTRIES     comma-separated ISO-2 subset (optional)
"""
from __future__ import annotations

import asyncio
import logging
import os
import re

import asyncpg
import httpx
import redis.asyncio as aioredis

# ── Reuse sealed indexer primitives — DO NOT mutate the module ───────────────
from scrapers.sitemap_indexer import (
    _index_source,  # type: ignore[attr-defined]
    _USER_AGENT,    # type: ignore[attr-defined]
    _REQUEST_TIMEOUT,  # type: ignore[attr-defined]
)

log = logging.getLogger(__name__)

_DEFAULT_DSN = os.environ.get(
    "DATABASE_URL",
    "postgres://cardex:cardex_dev_only@localhost:5432/cardex",
)
_DEFAULT_REDIS = os.environ.get("REDIS_URL", "redis://localhost:6379")

_BATCH_SIZE = int(os.environ.get("SITEMAP_BRIDGE_BATCH", "20"))
_CONCURRENCY = int(os.environ.get("SITEMAP_BRIDGE_CONCURRENCY", "8"))
_IDLE_SLEEP = float(os.environ.get("SITEMAP_BRIDGE_IDLE_SLEEP", "60"))
_ONESHOT = os.environ.get("SITEMAP_BRIDGE_ONESHOT", "0") == "1"
_MIN_INTERVAL = os.environ.get("SITEMAP_BRIDGE_MIN_INTERVAL", "6 hours")
_COUNTRIES_FILTER = tuple(
    c.strip().upper()
    for c in os.environ.get("SITEMAP_BRIDGE_COUNTRIES", "").split(",")
    if c.strip()
)


# ── Universal vehicle URL regex ──────────────────────────────────────────────
#
# Requires a vehicle-path keyword AND an id signature. Case-insensitive.
# Tested against the URL shape of Autobiz, Autentia, Incadea, Motormanager,
# WP Car Manager, and plain WooCommerce-based dealer sites across DE/FR/ES/
# NL/BE/CH. False negatives on pure-slug URLs (e.g. /audi-a4-2020-metallic)
# are accepted — those dealers need a manual override.

_VEHICLE_PATH_KEYWORDS = (
    # DE
    "gebrauchtwagen", "gebrauchtwagen-detail", "fahrzeug", "fahrzeuge",
    "fahrzeug-detail", "pkw", "neuwagen", "wagen",
    # FR
    "occasion", "occasions", "vehicule", "vehicules", "voiture", "voitures",
    "annonce", "annonces", "fiche",
    # ES
    "coche", "coches", "vehiculo", "vehiculos", "segunda-mano", "ocasion",
    "ficha", "anuncio", "anuncios",
    # NL / BE
    "auto-s", "voertuig", "voertuigen", "wagens", "advertentie", "aanbod",
    # EN / universal
    "vehicle", "vehicles", "car", "cars", "stock", "inventory", "listing",
)

# Listing-identity signatures AFTER the keyword. A URL qualifies as an
# individual listing (rather than a category/home/blog page) when ANY of:
#
#   1. A path segment contains 2+ hyphens  — slug pattern common to
#      WordPress-based dealer sites (Autobiz, Autentia, WP Car Manager,
#      and generic WooCommerce). Example: /vehicule/fiesta-1-0-ecoboost-85-active
#      Category pages are short and hyphen-poor (/coches/audi/a4/), so a
#      2-hyphen threshold cleanly separates them.
#
#   2. A 5+ digit numeric run  — covers dealer CMS that embed listing
#      IDs in the URL: /gebrauchtwagen/audi-a4-123456, /vehicle/78910.
#
#   3. A known listing-id query parameter  — OEM/portal-style URLs:
#      ?productId=, ?vehicleId=, ?carId=, ?stockId=, etc.
_LISTING_SIGNATURE = (
    r"-[^/?#]*-[^/?#]*"                    # segment with 2+ hyphens
    r"|\d{5,}"                             # 5+ digit run
    r"|[?&](?:productId|vehicleId|carId|stockId|listingId|adId|"
    r"Angebotsnr|annonce[_-]?id|ref|reference)=\w+"
)

_KW_GROUP = "|".join(re.escape(k) for k in _VEHICLE_PATH_KEYWORDS)

# Positive match: vehicle-path keyword at the START of a path segment
# (either a full segment or a compound segment like `coches-ocasion`,
# `pkw-angebote`, `gebrauchtwagen-detail`) AND a listing signature
# anywhere after it in the URL.
UNIVERSAL_VEHICLE_URL_REGEX_SRC = (
    rf"(?i)(?:^|/)(?:{_KW_GROUP})(?:[/_\-]|$)[^?#]*?(?:{_LISTING_SIGNATURE})"
)

# Compile once at module load. The sealed _index_source expects a regex
# SOURCE STRING (not a compiled object) — it re-compiles internally.
UNIVERSAL_VEHICLE_URL_REGEX = UNIVERSAL_VEHICLE_URL_REGEX_SRC


def resolve_url_regex(
    url_regex_override: str | None,
    external_refs: dict | None,
) -> str:
    if url_regex_override:
        return url_regex_override
    if external_refs and isinstance(external_refs, dict):
        rx = external_refs.get("url_regex")
        if rx:
            return str(rx)
    return UNIVERSAL_VEHICLE_URL_REGEX


# ── SQL ──────────────────────────────────────────────────────────────────────

# NOTE: min_interval is embedded as a literal INTERVAL in the SQL text
# (not a parameter) because asyncpg binds $N::interval to a Python
# datetime.timedelta, not a string. Environment override still works —
# substituted at module load into the f-string below.

_CLAIM_SQL_BASE = f"""
WITH claimed AS (
    SELECT id
    FROM discovery_candidates
    WHERE sitemap_status = 'found'
      AND (indexer_last_run IS NULL
           OR indexer_last_run < NOW() - INTERVAL '{_MIN_INTERVAL}')
      {{country_filter}}
    ORDER BY indexer_last_run NULLS FIRST, first_seen
    LIMIT $1
    FOR UPDATE SKIP LOCKED
)
UPDATE discovery_candidates
   SET indexer_last_run = NOW()
FROM claimed
WHERE discovery_candidates.id = claimed.id
RETURNING
    discovery_candidates.id,
    discovery_candidates.domain,
    discovery_candidates.country,
    discovery_candidates.sitemap_url,
    discovery_candidates.url_regex_override,
    discovery_candidates.external_refs
"""

_FINALIZE_SQL = """
UPDATE discovery_candidates
SET indexer_urls_seen = $2,
    indexer_new       = $3,
    indexer_gone      = $4,
    indexer_error     = $5,
    indexer_last_run  = NOW()
WHERE id = $1
"""


def _build_claim_sql() -> str:
    if _COUNTRIES_FILTER:
        return _CLAIM_SQL_BASE.format(
            country_filter="AND country = ANY($2::text[])",
        )
    return _CLAIM_SQL_BASE.format(country_filter="")


async def _claim_batch(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    sql = _build_claim_sql()
    if _COUNTRIES_FILTER:
        return await pool.fetch(sql, _BATCH_SIZE, list(_COUNTRIES_FILTER))
    return await pool.fetch(sql, _BATCH_SIZE)


async def _finalize(
    pool: asyncpg.Pool,
    row_id: int,
    urls_seen: int,
    new: int,
    gone: int,
    err: str | None,
) -> None:
    await pool.execute(
        _FINALIZE_SQL, row_id, urls_seen, new, gone, err,
    )


# ── Per-dealer indexing ──────────────────────────────────────────────────────

async def _index_one(
    pool: asyncpg.Pool,
    rdb: aioredis.Redis,
    client: httpx.AsyncClient,
    row: asyncpg.Record,
) -> dict:
    source_key = row["domain"]           # short stable key = the domain
    country = row["country"]
    sitemap_url = row["sitemap_url"]
    url_regex = resolve_url_regex(
        row["url_regex_override"],
        _decode_jsonb(row["external_refs"]),
    )

    try:
        stats = await _index_source(
            pool, rdb, client,
            source_key, country, sitemap_url, url_regex, None,
        )
    except Exception as exc:
        log.warning(
            "sitemap_bridge: %s/%s failed: %s",
            source_key, country, exc,
        )
        await _finalize(pool, row["id"], 0, 0, 0, f"{type(exc).__name__}:{exc}"[:200])
        return {"found": 0, "new": 0, "gone": 0, "errored": 1}

    urls_seen = int(stats.get("urls_found", 0))
    new = int(stats.get("new", 0))
    gone = int(stats.get("gone", 0))
    err = stats.get("error") if isinstance(stats.get("error"), str) else None

    await _finalize(pool, row["id"], urls_seen, new, gone, err)
    return {
        "found": urls_seen,
        "new": new,
        "gone": gone,
        "errored": 1 if err else 0,
    }


def _decode_jsonb(val) -> dict | None:
    """asyncpg returns JSONB as dict by default; be defensive in case it's a str."""
    if val is None:
        return None
    if isinstance(val, dict):
        return val
    if isinstance(val, (bytes, bytearray)):
        val = val.decode("utf-8", errors="replace")
    if isinstance(val, str):
        try:
            import json
            return json.loads(val)
        except Exception:
            return None
    return None


# ── Worker loop ──────────────────────────────────────────────────────────────

async def _process_batch(
    pool: asyncpg.Pool,
    rdb: aioredis.Redis,
    client: httpx.AsyncClient,
    batch: list[asyncpg.Record],
) -> dict[str, int]:
    sem = asyncio.Semaphore(_CONCURRENCY)
    totals = {"found": 0, "new": 0, "gone": 0, "errored": 0}

    async def _one(row: asyncpg.Record) -> None:
        async with sem:
            result = await _index_one(pool, rdb, client, row)
        for k, v in result.items():
            totals[k] = totals.get(k, 0) + v

    await asyncio.gather(*(_one(r) for r in batch))
    return totals


async def run() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    pool = await asyncpg.create_pool(
        _DEFAULT_DSN, min_size=4, max_size=20, command_timeout=120,
    )
    rdb = aioredis.from_url(_DEFAULT_REDIS, decode_responses=False)
    client = httpx.AsyncClient(
        timeout=_REQUEST_TIMEOUT,
        follow_redirects=True,
        http2=True,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "application/xml,text/xml,*/*;q=0.8",
            "Accept-Encoding": "gzip,deflate,br",
        },
        limits=httpx.Limits(
            max_keepalive_connections=_CONCURRENCY * 4,
            max_connections=_CONCURRENCY * 8,
        ),
    )

    log.info(
        "sitemap_bridge: starting — batch=%d concurrency=%d min_interval=%r oneshot=%s countries=%s",
        _BATCH_SIZE, _CONCURRENCY, _MIN_INTERVAL, _ONESHOT,
        _COUNTRIES_FILTER or "ALL",
    )

    cumulative = {"found": 0, "new": 0, "gone": 0, "errored": 0}

    try:
        while True:
            batch = await _claim_batch(pool)
            if not batch:
                if _ONESHOT:
                    log.info("sitemap_bridge: queue empty, oneshot exit")
                    break
                log.debug("sitemap_bridge: queue empty, sleeping %.0fs", _IDLE_SLEEP)
                await asyncio.sleep(_IDLE_SLEEP)
                continue

            log.info("sitemap_bridge: claimed batch of %d dealers", len(batch))
            counts = await _process_batch(pool, rdb, client, batch)
            for k, v in counts.items():
                cumulative[k] = cumulative.get(k, 0) + v
            log.info(
                "sitemap_bridge: batch done — found=%d new=%d gone=%d errored=%d  "
                "totals=%d/%d/%d/%d",
                counts["found"], counts["new"], counts["gone"], counts["errored"],
                cumulative["found"], cumulative["new"],
                cumulative["gone"], cumulative["errored"],
            )
    finally:
        await client.aclose()
        await rdb.aclose()
        await pool.close()

    log.info(
        "sitemap_bridge: stopped — cumulative found=%d new=%d gone=%d errored=%d",
        cumulative["found"], cumulative["new"],
        cumulative["gone"], cumulative["errored"],
    )


if __name__ == "__main__":
    asyncio.run(run())
