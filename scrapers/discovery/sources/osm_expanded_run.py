"""OSM expanded runner — re-runs the expanded query for all 6 countries."""
from __future__ import annotations

import asyncio
import json
import logging
import os

import asyncpg
import httpx

from scrapers.discovery.sources.osm import OSMSource

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [osm_exp] %(message)s",
)
log = logging.getLogger("osm_exp")

_DSN = os.environ.get(
    "DATABASE_URL",
    "postgres://cardex:cardex_dev_only@localhost:5432/cardex",
)


def _countries_to_run() -> tuple[str, ...]:
    """
    Honour OSM_COUNTRIES env var (comma-separated, e.g. 'BE,NL,CH').
    Falls back to all six countries when the var is absent.
    Order is preserved exactly as specified in the env var.
    """
    env = os.environ.get("OSM_COUNTRIES", "").strip()
    if env:
        return tuple(c.strip().upper() for c in env.split(",") if c.strip())
    return ("DE", "FR", "ES", "NL", "BE", "CH")


async def run() -> None:
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    written = 0
    seen = 0
    countries = _countries_to_run()
    log.info("countries to run: %s", countries)
    try:
        async with httpx.AsyncClient(timeout=600.0, follow_redirects=True) as client:
            src = OSMSource(client)
            for country in countries:
                log.info("country=%s", country)
                async for cand in src.discover(country):
                    seen += 1
                    domain = cand.get("domain")
                    registry_id = cand.get("registry_id")
                    if not domain and not registry_id:
                        continue
                    try:
                        if domain:
                            sql = """
                            INSERT INTO discovery_candidates
                              (domain, country, source_layer, source, url, name, address, city, postcode, phone, email, lat, lng, registry_id, external_refs)
                            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb)
                            ON CONFLICT (domain, country) WHERE domain IS NOT NULL DO NOTHING
                            """
                        else:
                            sql = """
                            INSERT INTO discovery_candidates
                              (domain, country, source_layer, source, url, name, address, city, postcode, phone, email, lat, lng, registry_id, external_refs)
                            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb)
                            ON CONFLICT (source, registry_id, country) WHERE domain IS NULL AND registry_id IS NOT NULL DO NOTHING
                            """
                        await pool.execute(
                            sql,
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
                        written += 1
                        if seen % 500 == 0:
                            log.info("%s progress: seen=%d written=%d", country, seen, written)
                    except Exception as exc:
                        log.debug("upsert: %s", exc)
                log.info("%s done: seen_total=%d written=%d", country, seen, written)
        log.info("ALL DONE seen=%d written=%d", seen, written)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(run())
