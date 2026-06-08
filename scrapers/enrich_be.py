"""enrich_be — upgrade Belgium dealer *pointers* to COMPLETE *rich* rows.

Each BE dealer's ``vehicle_index`` rows are pointers: a listing URL with almost
no attributes (≈3% have a price, ≈2% a title). This reads every BE dealer
pointer, fetches its ``url_original`` over HTTP (curl_cffi with browser
impersonation, SSRF-guarded), and runs the **already-verified** extraction seam —
``generic_extractor.extract_listing`` (schema.org / Open Graph / heuristics →
quality gate) → ``rich_consumer.persist_one`` (fingerprint + FX + the exact
``vehicles`` INSERT contract). The rich row is caged to its dealer entity
(``vehicles.entity_ulid``) and the now-redundant pointer is deleted, so the
``entity_inventory`` view surfaces the car as ``detail_level='rich'`` instead of
``'pointer'`` — without double-counting (the view UNIONs both arms).

HONEST by construction: a dealer detail page that carries no structured data
(SPA / no schema.org / missing make·model·year·price·image) fails the verified
``CRITICAL_FIELDS`` gate and is *counted as rejected*, never faked. The per-dealer
report says exactly how many listings each dealer yielded and why the rest didn't.

Operationally safe: low concurrency + a ctypes RAM guard that stops launching new
fetches before it can starve a sibling service (the host OOM-kills under memory
pressure). HTTP-only — no browser — so the footprint is small.

    DATABASE_URL=postgresql://cardex:cardex_dev_only@localhost:5432/cardex \
    python -m scrapers.enrich_be [--country BE] [--conc 4] [--limit 0]
"""
from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import logging
import os
import time
from collections import defaultdict

import asyncpg
from curl_cffi.requests import AsyncSession

from scrapers.common.net_guard import is_safe_public_url
from scrapers.enrich_worker import enrich_one
from scrapers.pipeline import fx_eur
from scrapers.pipeline.generic_extractor import FetchResult
from scrapers.rich_consumer import persist_one

log = logging.getLogger("enrich_be")
PG_DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
# Below this many MB free: stop launching new fetches (protect the API / sibling
# services — the host OOM-kills under pressure). HTTP-only, so this rarely trips.
RAM_ABORT_MB = int(os.environ.get("ENRICH_RAM_ABORT_MB", "520"))


def _avail_mb() -> int:
    class M(ctypes.Structure):
        _fields_ = [("l", ctypes.c_ulong), ("ld", ctypes.c_ulong), ("a", ctypes.c_ulonglong),
                    ("ap", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong), ("c", ctypes.c_ulonglong),
                    ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong), ("f", ctypes.c_ulonglong)]
    m = M(); m.l = ctypes.sizeof(M)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return int(m.ap // 1024 // 1024)


def make_curl_fetcher(session: AsyncSession, timeout: float = 20.0):
    """An async ``Fetcher`` over curl_cffi: SSRF-guarded, browser-impersonated.

    Honors the ``Fetcher`` contract — returns a ``FetchResult`` for ordinary HTTP
    responses (carrying the status), and raises only for a transport fault or an
    SSRF-unsafe URL so the upstream cascade records it as ``fetch_error`` and
    leaves the pointer untouched.
    """
    async def fetch(url: str) -> FetchResult:
        # SSRF: source_url derives from an external-registry domain column. resolve=True
        # closes DNS-rebinding; run getaddrinfo in a thread so it never blocks the loop.
        if not await asyncio.to_thread(is_safe_public_url, url, resolve=True):
            raise RuntimeError(f"unsafe_url:{url}")
        resp = await session.get(url, impersonate="chrome", timeout=timeout, allow_redirects=True)
        return FetchResult(
            url=str(getattr(resp, "url", url)),
            status_code=int(resp.status_code),
            body=resp.content or b"",
        )
    return fetch


async def _cage_and_supersede(pool, *, entity_ulid: str, vehicle_ulid: str, url_hash: str) -> None:
    """Attach the rich row to its dealer, then drop the redundant pointer (one txn).

    The view UNIONs the pointer arm (vehicle_index) and the rich arm (vehicles);
    leaving the pointer in place would double-count the same car. Deleting it only
    after the rich row is confirmed persisted means the listing is preserved with
    strictly more information, never lost.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE vehicles SET entity_ulid=$1 WHERE vehicle_ulid=$2",
                entity_ulid, vehicle_ulid,
            )
            await conn.execute("DELETE FROM vehicle_index WHERE url_hash=$1", url_hash)


async def run(*, country: str, conc: int, limit: int, timeout: float = 20.0) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    pool = await asyncpg.create_pool(PG_DSN, min_size=2, max_size=6)
    rates = fx_eur.load_rates_from_env()
    session = AsyncSession()
    fetch = make_curl_fetcher(session, timeout=timeout)
    sem = asyncio.Semaphore(conc)

    by_dealer: dict[str, dict] = defaultdict(
        lambda: {"domain": "", "attempted": 0, "enriched": 0, "rejected": 0,
                 "reasons": defaultdict(int)})
    tot = {"attempted": 0, "enriched": 0, "rejected": 0, "skipped_ram": 0, "errors": 0}
    t0 = time.monotonic()

    try:
        rows = await pool.fetch(
            "SELECT vi.url_hash, vi.url_original, se.domain, se.entity_ulid "
            "FROM vehicle_index vi JOIN source_entities se USING(entity_ulid) "
            "WHERE se.country=$1 AND se.kind='dealer' "
            "ORDER BY md5(vi.url_hash)", country)
        if limit:
            rows = rows[:limit]
        log.info("enriching %d %s dealer pointers (conc=%d, cap=%s) -- COMPLETE inventory",
                 len(rows), country, conc, limit or "all")

        async def one(r) -> None:
            d = by_dealer[r["entity_ulid"]]
            d["domain"] = r["domain"]
            if _avail_mb() < RAM_ABORT_MB:
                tot["skipped_ram"] += 1
                return
            async with sem:
                tot["attempted"] += 1
                d["attempted"] += 1
                fields = {"h": r["url_hash"], "u": r["url_original"], "s": r["domain"], "c": country}
                try:
                    payload, reason = await enrich_one(fields, fetch, default_country=country)
                except Exception as exc:  # noqa: BLE001 — one bad page must not kill the run
                    tot["errors"] += 1
                    d["rejected"] += 1
                    d["reasons"][f"exc:{type(exc).__name__}"] += 1
                    return
                if payload is None:
                    tot["rejected"] += 1
                    d["rejected"] += 1
                    d["reasons"][reason.split(":")[0]] += 1
                    return
                result, preason = await persist_one(
                    pool, payload, source=r["domain"], channel="SCRAPER", rates=rates)
                if result is None:
                    tot["rejected"] += 1
                    d["rejected"] += 1
                    d["reasons"][f"persist:{preason}"] += 1
                    return
                await _cage_and_supersede(
                    pool, entity_ulid=r["entity_ulid"],
                    vehicle_ulid=result.ulid, url_hash=r["url_hash"])
                tot["enriched"] += 1
                d["enriched"] += 1
                if tot["attempted"] % 50 == 0:
                    log.info("progress attempted=%d enriched=%d rejected=%d err=%d RAM=%dMB",
                             tot["attempted"], tot["enriched"], tot["rejected"], tot["errors"],
                             _avail_mb())

        await asyncio.gather(*(one(r) for r in rows))
    finally:
        await session.close()
        await pool.close()

    elapsed = time.monotonic() - t0
    dealers_yielding = sum(1 for v in by_dealer.values() if v["enriched"] > 0)
    print("\n===== BE ENRICH (pointer -> rich) =====")
    print(f"pointers_attempted={tot['attempted']} enriched={tot['enriched']} "
          f"rejected={tot['rejected']} errors={tot['errors']} skipped_ram={tot['skipped_ram']} "
          f"| {elapsed:.0f}s")
    print(f"dealers_total={len(by_dealer)} dealers_yielding_rich={dealers_yielding}")
    top = sorted(by_dealer.values(), key=lambda v: v["enriched"], reverse=True)[:15]
    print("top_by_enriched:", json.dumps(
        [{"d": v["domain"], "att": v["attempted"], "rich": v["enriched"],
          "rej": v["rejected"]} for v in top], ensure_ascii=False))
    # aggregate reject reasons (why the long tail didn't enrich)
    agg: dict[str, int] = defaultdict(int)
    for v in by_dealer.values():
        for k, n in v["reasons"].items():
            agg[k] += n
    print("reject_reasons:", json.dumps(dict(sorted(agg.items(), key=lambda x: -x[1])),
                                        ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="BE")
    ap.add_argument("--conc", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="cap pointers (0 = all)")
    ap.add_argument("--timeout", type=float, default=20.0)
    a = ap.parse_args()
    asyncio.run(run(country=a.country, conc=a.conc, limit=a.limit, timeout=a.timeout))
