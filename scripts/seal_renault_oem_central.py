"""Seal Renault/Dacia FR used inventory — ONE catalog sweep, PROXY-FREE, no auth.

renew.auto (occasion.renault.fr redirects here) exposes all used cars on a clean REST
API, no token/cookie/captcha, no pagination-window limit:
  GET https://fr.renew.auto/wired/commerce/v1/products
      ?locale=fr-FR&channel=main&pageSize=500&page=N&q=productType==vehicle_uci
totalElements ~52k (vehicle_uci = the used filter; without it the count includes services).
Single sweep enumerates everything; per-dealer attribution (dealer.dealerId / dwsShortName)
comes inline, so we group and cage per dealer + reconcile. price = prices[0].priceWithTaxes
(NOT the monthly financing). Dedup by productId (in the url) collapses ~4.6% index dupes.

    python -m scripts.seal_renault_oem_central [--conc 5] [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import time
from collections import defaultdict

import asyncpg
import redis.asyncio as aioredis
from curl_cffi.requests import AsyncSession

from scrapers.common import host_budget
from scrapers.dealer_scraping.inventory_harvester import (_entity_ulid, _hash_urls,
                                                          cage_inventory)

DSN = "postgresql://cardex:cardex_dev_only@localhost:5432/cardex"
REDIS = "redis://localhost:6379"
BASE = "https://fr.renew.auto/wired/commerce/v1/products"
CONFIG_REF = "configs/families/renault_oem_central.json"


def _to_listing(v: dict) -> dict:
    pid = v.get("productId") or ""
    url = (f"https://fr.renew.auto/achat-vehicules-occasions/details.html?productId={pid}"
           if pid else "")
    parts = [(v.get("brand") or {}).get("label"), (v.get("model") or {}).get("label"),
             (v.get("version") or {}).get("label")]
    title = " ".join(p for p in parts if p).strip() or None
    prices = v.get("prices") or []
    price = prices[0].get("priceWithTaxes") if prices else None
    dealer = v.get("dealer") or {}
    did = dealer.get("dealerId")
    short = ((dealer.get("renault") or {}).get("dwsShortName")
             or (f"renault-{did}" if did else "renault-unknown")).strip().lower()
    return {"url": url, "title": title, "price": price, "year": v.get("modelYear"),
            "km": v.get("mileage"), "dom": short}


async def main(conc, limit):
    async with AsyncSession(impersonate="chrome136") as sess:
        cars: list[dict] = []
        page, total, tpages = 0, None, 1
        while True:
            url = (f"{BASE}?locale=fr-FR&channel=main&pageSize=500&page={page}"
                   "&q=productType==vehicle_uci")
            r = await sess.get(url, headers={"Accept": "application/json"}, timeout=40)
            d = r.json()
            total = d.get("totalElements")
            tpages = d.get("totalPages") or 0
            data = d.get("data") or []
            cars.extend(_to_listing(v) for v in data)
            page += 1
            await asyncio.sleep(1.0)
            if not data or page >= tpages:
                break
            if limit and len(cars) >= limit:
                break
        by_dealer: dict[str, list[dict]] = defaultdict(list)
        for c in cars:
            if c["url"] and c["dom"]:
                by_dealer[c["dom"]].append(c)
        print(f"RENAULT sweep: {len(cars)} cars (declared {total}) | {len(by_dealer)} dealers",
              flush=True)
        pool = await asyncpg.create_pool(DSN, min_size=2, max_size=conc + 3)
        rdb = aioredis.from_url(REDIS)
        try:
            sem = asyncio.Semaphore(conc)

            async def _seal(dom, items):
                async with sem:
                    await host_budget.wait_until_healthy(max_s=60)
                    await cage_inventory(pool, rdb, dom, "FR", items, config_ref=CONFIG_REF)
                    ent = _entity_ulid(dom)
                    keep = list(_hash_urls([i["url"] for i in items]).keys())
                    async with pool.acquire() as c:
                        async with c.transaction():
                            stale = await c.fetch(
                                "SELECT url_hash,url_original FROM vehicle_index "
                                "WHERE entity_ulid=$1 AND NOT (url_hash = ANY($2))", ent, keep)
                            if stale:
                                await c.execute(
                                    "INSERT INTO vehicle_events (url_hash,url_original,source_domain,country,event_type) "
                                    "SELECT h,u,$3,'FR','GONE' FROM unnest($1::text[],$2::text[]) AS t(h,u)",
                                    [r["url_hash"] for r in stale],
                                    [r["url_original"] for r in stale], dom)
                                await c.execute(
                                    "DELETE FROM vehicle_index WHERE entity_ulid=$1 AND NOT (url_hash = ANY($2))",
                                    ent, keep)
                        return await c.fetchval(
                            "SELECT count(*) FROM vehicle_index WHERE entity_ulid=$1", ent)

            t0 = time.monotonic()
            res = await asyncio.gather(*(_seal(dom, items) for dom, items in by_dealer.items()))
            print(f"DONE {int(time.monotonic()-t0)}s: dealers_served={sum(1 for r in res if r)} "
                  f"cars_served={sum(res)}", flush=True)
        finally:
            await rdb.aclose()
            await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--conc", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    asyncio.run(main(a.conc, a.limit))
