"""
Per-dealer enrich seam + scope-by-platform purger — the shared validate-with-a-sample wiring.

Used by the validation harness (``scripts/run_dealer_scraping``) AND the production self-healing
remediator (``remediation_dispatcher.build_real_deps``). Extracted here so both reuse ONE
implementation (DRY) instead of a scripts<-scrapers layering inversion.

Both callers run an ISOLATED, slice-then-purge re-harvest of a small sample (remediate() also
purges — it VALIDATES that a regenerated recipe yields inventory, it does not fill production).
So the seam runs on a THROWAWAY redis (``isolate=True`` wipes its enrich/ingestion streams to
bound RAM and isolate dealers) and persists to the real PG (``db_url``) for the recovered check.
``isolate=False`` is reserved for a future continuous production fill that must NOT delete the
live streams.
"""
from __future__ import annotations

from urllib.parse import urlparse

from scrapers import enrich_worker as a6
from scrapers import rich_consumer as a7
from scrapers.common import indexer
from scrapers.dealer_scraping import harvester as hv


def make_live_seam(rdb, static_fetcher, e07_fetcher, *, redis_url: str, db_url: str, isolate: bool = True):
    """Per-dealer seam: seed enrich_pending → A6 (E07 by config) → A7 → return persisted.

    ``redis_url``/``db_url`` are the throwaway redis and the (real) PG the A6/A7 stages connect
    to; ``rdb`` is the matching live client used to seed/clear the streams. ``isolate=True`` wipes
    the enrich/ingestion streams first (validation/remediation, throwaway redis only — NEVER pass
    a production redis with isolate=True or it deletes live work).
    """
    async def run(domain: str, country: str, urls: list[str], is_e07: bool) -> int:
        if not urls:
            return 0  # nothing discovered → A6/A7 batch_size=0 would crash xreadgroup
        if isolate:
            for s in (a6.ENRICH_STREAM, a6.INGESTION_STREAM):
                await rdb.delete(s)  # bound RAM + isolate dealers (throwaway redis)
        for url in urls:
            await rdb.xadd(a6.ENRICH_STREAM, {
                "h": indexer.url_hash(url), "u": url, "s": domain, "c": country,
            })
        conc = hv.E07_CONCURRENCY if is_e07 else hv.STATIC_CONCURRENCY
        await a6.run(
            redis_url=redis_url, fetcher=static_fetcher,
            e07_fetcher=(e07_fetcher if is_e07 else None),
            limit=len(urls), batch_size=len(urls), block_ms=1500,
            concurrency=conc, default_country=country, reclaim_idle_ms=8_000,
        )
        s7 = await a7.run(
            database_url=db_url, redis_url=redis_url,
            limit=len(urls), batch_size=len(urls), block_ms=1500,
            # Dealer cage path: register the dealer's source_entities row (idempotent)
            # and set vehicles.entity_ulid in the INSERT, so the per-entity inventory
            # API (entity_inventory view) serves the caged rows immediately.
            entity_kind="dealer",
        )
        return s7.persisted
    return run


def make_live_purger(pg):
    """Scope-by-platform purge: delete vehicles by source_platform (stable across redirect/
    re-encoding — the source_url that lands in `vehicles` may differ from the discovered URL
    once the site canonicalizes www/percent-encoding, so an exact-URL purge leaks orphans),
    plus the LISTING vin_history for those VINs. Scoped to the dealer(s) just scraped."""
    def _platform(u: str) -> str:
        host = urlparse(u).netloc.lower().split("@")[-1].split(":")[0]
        return host[4:] if host.startswith("www.") else host

    async def purge(urls: list[str]) -> int:
        platforms = sorted({p for u in urls if u and (p := _platform(u))})
        if not platforms:
            return 0
        async with pg.acquire() as conn:
            vins = await conn.fetch(
                "SELECT DISTINCT vin FROM vehicles "
                "WHERE source_platform = ANY($1::text[]) AND vin IS NOT NULL",
                platforms,
            )
            tag = await conn.execute(
                "DELETE FROM vehicles WHERE source_platform = ANY($1::text[])", platforms
            )
            if vins:
                vinlist = [r["vin"] for r in vins]
                await conn.execute(
                    "DELETE FROM vin_history_cache WHERE vin = ANY($1::text[])", vinlist
                )
        try:
            return int(tag.split()[-1])
        except (ValueError, IndexError):
            return 0
    return purge
