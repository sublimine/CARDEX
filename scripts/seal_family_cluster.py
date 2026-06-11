"""Seal a whole CMS-family cluster to AVAILABILITY TRUTH — the multiplier at scale.

Per dealer (bounded concurrency + S-HOST RAM gate so the laptop never saturates):

  AVAILABILITY-FIRST GATE — walk the live paginated listing via the family's candidate
  roots. ONLY a dealer whose listing yields the real on-sale set is a true platform
  member; cage it (rich, via harvest_t2_dealer) and reconcile to that set (GONE + purge
  the sold/stale an old sitemap cage left behind — the H6 fix).

  A dealer that FAILS the gate is a fingerprint false-positive or an unmapped variant.
  We do NOT cage it from the sitemap (that serves SOLD cars). We SKIP it and PURGE any
  inflated inventory a prior run cached — so the cluster converges to "only real members
  serve, and they serve the availability truth". Skipped dealers are reported for triage.

Idempotent / resumable. One network run only (never overlap probe/harvest runs).

    python -m scripts.seal_family_cluster --cms dealerk --conc 3 [--limit N] [--sample 80]
"""
from __future__ import annotations

import argparse
import asyncio
import time

import asyncpg
import redis.asyncio as aioredis

from scrapers.common import host_budget
from scrapers.dealer_scraping import harvester
from scrapers.dealer_scraping.discovery import walk_listing_pagination
from scrapers.dealer_scraping.family_autosociaal import harvest_autosociaal
from scrapers.dealer_scraping.inventory_harvester import (_entity_ulid, _hash_urls,
                                                          cage_inventory, harvest_t2_dealer)
from scrapers.portals import config

# Families whose stock is HTML-listing only (no JSON-LD / no API) → a dedicated module
# returns the full available set in one cumulative page; the generic JSON-LD walk path
# below does not apply. cms -> harvester(host, fetcher) -> {"ok","listings",...}.
_HTML_FAMILIES = {"autosociaal": harvest_autosociaal}

DSN = "postgresql://cardex:cardex_dev_only@localhost:5432/cardex"
REDIS = "redis://localhost:6379"


async def _purge_entity(pool, ent, domain, country, *, keep: list[str] | None = None) -> int:
    """GONE + delete this entity's pointers (all, or all NOT in ``keep``). Returns purged count."""
    cc = (country or "")[:2]
    async with pool.acquire() as c:
        if keep:
            stale = await c.fetch(
                "SELECT url_hash,url_original FROM vehicle_index "
                "WHERE entity_ulid=$1 AND NOT (url_hash = ANY($2))", ent, keep)
        else:
            stale = await c.fetch(
                "SELECT url_hash,url_original FROM vehicle_index WHERE entity_ulid=$1", ent)
        if not stale:
            return 0
        async with c.transaction():
            await c.execute(
                "INSERT INTO vehicle_events (url_hash,url_original,source_domain,country,event_type) "
                "SELECT h,u,$3,$4,'GONE' FROM unnest($1::text[],$2::text[]) AS t(h,u)",
                [r["url_hash"] for r in stale], [r["url_original"] for r in stale], domain, cc)
            if keep:
                await c.execute(
                    "DELETE FROM vehicle_index WHERE entity_ulid=$1 AND NOT (url_hash = ANY($2))",
                    ent, keep)
            else:
                await c.execute("DELETE FROM vehicle_index WHERE entity_ulid=$1", ent)
        return len(stale)


async def _seal_one(pool, rdb, recipe, fetcher, cms, domain, country, sample, sem):
    async with sem:
        if not await host_budget.wait_until_healthy(max_s=120):           # S-HOST gate
            return {"domain": domain, "skipped": "host_pressure"}
        ent = _entity_ulid(domain)

        # HTML-listing families (no JSON-LD/API): a dedicated module returns the full
        # available set (cumulative page); cage it + reconcile to that availability truth.
        if cms in _HTML_FAMILIES:
            try:
                r = await _HTML_FAMILIES[cms](domain, fetcher)
            except Exception as exc:
                return {"domain": domain, "error": f"{type(exc).__name__}: {exc}"}
            if not r.get("ok") or not r.get("listings"):
                purged = await _purge_entity(pool, ent, domain, country)
                return {"domain": domain, "skipped": "no_stock_or_pattern", "purged": purged}
            listings = r["listings"]
            await cage_inventory(pool, rdb, domain, country, listings,
                                 config_ref=f"configs/families/{cms}.json")
            keep = list(_hash_urls([li["url"] for li in listings]).keys())
            purged = await _purge_entity(pool, ent, domain, country, keep=keep)
            async with pool.acquire() as c:
                served = await c.fetchval("SELECT count(*) FROM vehicle_index WHERE entity_ulid=$1", ent)
            return {"domain": domain, "available": len(keep), "served": served, "purged": purged}

        cfg = config.instantiate_family(recipe, domain, country=country)
        rx = cfg.endpoints.detail_url_re or ""

        # AVAILABILITY-FIRST GATE: the live listing must paginate real stock, no sitemap fallback.
        avail: list[str] = []
        for root in (cfg.endpoints.listing_url_candidates or ()):
            try:
                got = await walk_listing_pagination(fetcher, root, detail_url_re=rx, cap=400)
            except Exception:
                got = []
            if got:
                avail = got
                break

        if not avail:
            # FP / unmapped variant: never serve sold cars — purge any prior inflated cache.
            purged = await _purge_entity(pool, ent, domain, country)
            return {"domain": domain, "skipped": "no_availability_pattern", "purged": purged}

        # True platform member: cage rich (harvest enriches the same listing) + reconcile to truth.
        try:
            await harvest_t2_dealer(pool, rdb, domain, country, cms=cms,
                                    cms_confidence="medium", sample_limit=sample)
        except Exception as exc:
            return {"domain": domain, "error": f"{type(exc).__name__}: {exc}"}
        avail_hashes = list(_hash_urls(avail).keys())
        purged = await _purge_entity(pool, ent, domain, country, keep=avail_hashes)
        async with pool.acquire() as c:
            served = await c.fetchval("SELECT count(*) FROM vehicle_index WHERE entity_ulid=$1", ent)
        return {"domain": domain, "available": len(avail_hashes), "served": served, "purged": purged}


async def main(cms, conc, limit, sample):
    recipe = config.load_family(cms)
    if recipe is None:
        raise SystemExit(f"no family recipe for cms={cms!r}")
    pool = await asyncpg.create_pool(DSN, min_size=2, max_size=conc + 3)
    rdb = aioredis.from_url(REDIS)
    fetcher = harvester.make_dealer_fetcher()
    try:
        async with pool.acquire() as c:
            rows = await c.fetch(
                "SELECT domain, coalesce(country,'') country FROM discovery_candidates "
                "WHERE inventory_signals->>'cms'=$1 AND domain IS NOT NULL AND domain<>'' ORDER BY domain",
                cms)
        if limit:
            rows = rows[:limit]
        print(f"CLUSTER {cms}: {len(rows)} dealers | conc={conc} sample={sample} | "
              f"RAM avail={host_budget.available_mb()}MB", flush=True)
        sem = asyncio.Semaphore(conc)
        t0 = time.monotonic()
        results = await asyncio.gather(*(
            _seal_one(pool, rdb, recipe, fetcher, cms, r["domain"], r["country"], sample, sem)
            for r in rows))
        members = [r for r in results if r.get("served")]
        skipped = [r for r in results if r.get("skipped") == "no_availability_pattern"]
        errs = [r for r in results if r.get("error")]
        served_total = sum(r.get("served", 0) for r in members)
        purged_total = sum(r.get("purged", 0) for r in results)
        print(f"DONE {int(time.monotonic()-t0)}s: real_members={len(members)}/{len(rows)} "
              f"served_total={served_total} (availability-truth) | not_member(FP/variant)={len(skipped)} | "
              f"purged_inflated={purged_total} | errors={len(errs)}", flush=True)
        for r in sorted(members, key=lambda r: -r["served"])[:25]:
            print(f"  MEMBER {r['domain']}: served={r['served']} purged={r['purged']}", flush=True)
        if skipped:
            print("NOT-MEMBER (triage — FP or unmapped variant):", flush=True)
            for r in skipped[:20]:
                print(f"  {r['domain']} (purged_inflated={r['purged']})", flush=True)
        if errs:
            print("ERRORS:", flush=True)
            for r in errs[:8]:
                print(f"  {r['domain']}: {r['error']}", flush=True)
    finally:
        await rdb.aclose()
        await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cms", default="dealerk")
    ap.add_argument("--conc", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sample", type=int, default=80)
    a = ap.parse_args()
    asyncio.run(main(a.cms, a.conc, a.limit, a.sample))
