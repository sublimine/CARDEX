"""Seal the whole Audi DE used inventory — ONE connector, all dealers, PROXY-FREE.

The dead Audi microsites centralize their used stock in the Stock Car Service (SCS):
  GET scs.audi.de/api/v2/search/filter/deuc/de?from=K&size=100&filter=dealer.<id>
  header  Token: FJ54W6H   (public apiKey from the page bundle; no cookie/captcha).
The dealer facet (items[] {id:'dealer.<id>', count}) is the registry + availability oracle.

Per dealer (count>0): fetch every car (paginate to totalCount), cage to vehicle_index
keyed by the dealer's microsite (dealer.pageUrl), reconcile to that availability set
(GONE+purge stale). One curl_cffi AsyncSession = coherent JA3. S-HOST RAM gate. Zero cost.

    python -m scripts.seal_audi_oem_central [--conc 5] [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import time

import asyncpg
import redis.asyncio as aioredis
from curl_cffi.requests import AsyncSession

from scrapers.common import host_budget
from scrapers.dealer_scraping.inventory_harvester import (_entity_ulid, _hash_urls,
                                                          cage_inventory)

DSN = "postgresql://cardex:cardex_dev_only@localhost:5432/cardex"
REDIS = "redis://localhost:6379"
TOKEN = "FJ54W6H"
BASE = "https://scs.audi.de/api/v2/search/filter/deuc/de"
CONFIG_REF = "configs/families/audi_oem_central.json"


async def _get(sess, url):
    r = await sess.get(url, headers={"Token": TOKEN}, timeout=30)
    return r.json()


def _to_listing(v: dict) -> dict:
    price = next((tp.get("amount") for tp in (v.get("typedPrices") or [])
                  if tp.get("type") == "retail"), None)
    return {"url": v.get("weblink") or "",
            "title": (v.get("model") or {}).get("description"),
            "price": price, "year": v.get("modelYear"), "km": v.get("mileage")}


async def _seal_dealer(sess, pool, rdb, did, sem):
    async with sem:
        if not await host_budget.wait_until_healthy(max_s=120):
            return {"id": did, "skipped": "host_pressure"}
        cars: list[dict] = []
        frm, total = 0, 0
        try:
            while True:
                d = await _get(sess, f"{BASE}?size=100&from={frm}&filter=dealer.{did}")
                total = d.get("totalCount", 0)
                vb = d.get("vehicleBasic") or []
                cars.extend(vb)
                frm += 100
                await asyncio.sleep(0.4)            # polite, single source
                if frm >= total or not vb:
                    break
        except Exception as exc:
            return {"id": did, "error": f"{type(exc).__name__}: {exc}"}
        listings = [_to_listing(v) for v in cars if v.get("weblink")]
        if not listings:
            return {"id": did, "served": 0}
        dealer = cars[0].get("dealer") or {}
        dom = (dealer.get("pageUrl") or f"audi-oem-{did}.de").replace(
            "https://", "").replace("http://", "").strip("/").lower()
        try:
            await cage_inventory(pool, rdb, dom, "DE", listings, config_ref=CONFIG_REF)
        except Exception as exc:
            return {"id": did, "dom": dom, "error": f"cage:{type(exc).__name__}: {exc}"}
        ent = _entity_ulid(dom)
        keep = list(_hash_urls([li["url"] for li in listings]).keys())
        async with pool.acquire() as c:
            async with c.transaction():
                stale = await c.fetch(
                    "SELECT url_hash,url_original FROM vehicle_index "
                    "WHERE entity_ulid=$1 AND NOT (url_hash = ANY($2))", ent, keep)
                if stale:
                    await c.execute(
                        "INSERT INTO vehicle_events (url_hash,url_original,source_domain,country,event_type) "
                        "SELECT h,u,$3,'DE','GONE' FROM unnest($1::text[],$2::text[]) AS t(h,u)",
                        [r["url_hash"] for r in stale], [r["url_original"] for r in stale], dom)
                    await c.execute(
                        "DELETE FROM vehicle_index WHERE entity_ulid=$1 AND NOT (url_hash = ANY($2))",
                        ent, keep)
            served = await c.fetchval("SELECT count(*) FROM vehicle_index WHERE entity_ulid=$1", ent)
        return {"id": did, "dom": dom, "served": served, "total": total}


async def main(conc, limit):
    async with AsyncSession(impersonate="chrome136") as sess:
        facet = await _get(sess, f"{BASE}?size=0")
        global_total = facet.get("totalCount")
        dealers = [g["id"].split(".", 1)[1] for g in (facet.get("items") or [])
                   if str(g.get("id", "")).startswith("dealer.")
                   and str(g.get("id")).split(".", 1)[1].isdigit()
                   and (g.get("count") or 0) > 0]
        if limit:
            dealers = dealers[:limit]
        print(f"AUDI OEM-CENTRAL: {len(dealers)} dealers count>0 | global_total={global_total} | "
              f"conc={conc} | RAM={host_budget.available_mb()}MB", flush=True)
        pool = await asyncpg.create_pool(DSN, min_size=2, max_size=conc + 3)
        rdb = aioredis.from_url(REDIS)
        try:
            sem = asyncio.Semaphore(conc)
            t0 = time.monotonic()
            res = await asyncio.gather(*(_seal_dealer(sess, pool, rdb, d, sem) for d in dealers))
            served = [r for r in res if r.get("served")]
            cars_total = sum(r.get("served", 0) for r in served)
            errs = [r for r in res if r.get("error")]
            print(f"DONE {int(time.monotonic()-t0)}s: dealers_served={len(served)}/{len(dealers)} "
                  f"cars_served={cars_total} (target~{global_total}) errors={len(errs)}", flush=True)
            for r in sorted(served, key=lambda r: -r["served"])[:15]:
                print(f"  {r['dom']}: {r['served']}", flush=True)
            if errs:
                for r in errs[:8]:
                    print(f"  ERR {r['id']}: {r['error']}", flush=True)
        finally:
            await rdb.aclose()
            await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--conc", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    asyncio.run(main(a.conc, a.limit))
