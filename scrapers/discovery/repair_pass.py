"""
Repair pass — rescue incomplete Meili docs instead of deleting them.

Doctrine: every listing is somebody's ideal car. Don't delete an incomplete
doc — re-fetch it with a stronger client (curl_cffi Chrome impersonation),
re-extract the missing fields, and upsert only the new data. The only docs
that get deleted are:
  • URL returns 404 / 410 / DNS NXDOMAIN
  • Content markers: "vendido", "verkauft", "vendu", "sold", "out of stock"
  • Price impossibly low (< 500€) or impossibly high (> 2_000_000€) → scam

Everything else stays. Partial data is better than no data.
"""
from __future__ import annotations

import asyncio
import gzip
import logging
import os
import re
from typing import Any

import asyncpg
import httpx
from curl_cffi.requests import AsyncSession

from scrapers.discovery.meili_enricher import (  # reuse extractors
    _extract_jsonld,
    _extract_next_data,
    _extract_nuxt_data,
    _extract_microdata,
    _extract_dealerk_meta,
    _extract_all_vehicle_images,
    _extract_description,
    _clean_title,
    _RE_PRICE,
    _RE_KM,
    _RE_YEAR,
    _RE_TITLE,
)

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [repair] %(message)s",
)
log = logging.getLogger("repair")

_DSN = os.environ.get(
    "DATABASE_URL",
    "postgres://cardex:cardex_dev_only@localhost:5432/cardex",
)
_MEILI_URL = os.environ.get("MEILI_URL", "http://localhost:7700")
_MEILI_KEY = os.environ.get("MEILI_MASTER_KEY", "cardex_meili_dev_only")
_INDEX = "vehicles"
_BATCH = int(os.environ.get("REPAIR_BATCH", "500"))
_CONC = int(os.environ.get("REPAIR_CONC", "20"))
_SHARD = int(os.environ.get("REPAIR_SHARD", "0"))
_SHARDS = int(os.environ.get("REPAIR_SHARDS", "1"))

_HDR_MEILI = {
    "Authorization": f"Bearer {_MEILI_KEY}",
    "Content-Type": "application/json",
}

_SOLD_MARKERS = (
    "vendido", "verkauft", "vendu", "sold out", "verkocht",
    "out of stock", "non disponible", "no disponible", "niet beschikbaar",
    "reserviert", "reservado", "réservé", "gereserveerd",
)


def _looks_sold(html: str) -> bool:
    low = html.lower()
    return any(m in low for m in _SOLD_MARKERS)


async def _fetch_html(sess: AsyncSession, url: str) -> tuple[int, str | None]:
    try:
        r = await sess.get(url, impersonate="chrome124", timeout=15, allow_redirects=True)
    except Exception as exc:
        log.debug("fetch %s: %s", url, exc)
        return 0, None
    if r.status_code in (404, 410):
        return r.status_code, None
    if r.status_code != 200:
        return r.status_code, None
    return 200, r.text


def _merge_extracted(existing: dict, html: str, url: str) -> dict:
    """Return only NEW fields to update (preserve existing data)."""
    from urllib.parse import urljoin
    update: dict[str, Any] = {}

    jsonld = _extract_jsonld(html)
    dealerk = _extract_dealerk_meta(html)
    nextd = _extract_next_data(html)
    nuxt = _extract_nuxt_data(html)
    micro = _extract_microdata(html)

    merged: dict = {}
    for src in (dealerk, jsonld, nextd, nuxt, micro):
        for k, v in (src or {}).items():
            if v and not merged.get(k):
                merged[k] = v

    # Fill ONLY missing fields in existing doc
    for field in ("make", "model", "variant", "fuel_type", "transmission",
                  "year", "mileage_km", "price_eur", "power_kw", "power_hp"):
        if not existing.get(field) and merged.get(field):
            update[field] = merged[field]

    # Thumbnail / gallery
    if not existing.get("thumbnail_url"):
        imgs = _extract_all_vehicle_images(html, url)
        if imgs:
            update["thumbnail_url"] = imgs[0]
            update["thumb_url"] = imgs[0]
            update["gallery_urls"] = imgs[:30]

    # Description
    if not existing.get("description"):
        jsonld_desc = (merged.get("description") or "") if isinstance(merged, dict) else ""
        desc = _extract_description(html, jsonld_desc, "")
        if desc:
            update["description"] = desc[:1500]

    # Title → variant fallback
    if not existing.get("variant"):
        m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
        if m:
            t = _clean_title(m.group(1))
            if t:
                update["variant"] = t[:240]

    if not existing.get("price_eur") and "price_eur" not in update:
        for m in _RE_PRICE.finditer(html):
            raw = m.group(1) or m.group(2) or ""
            if not raw:
                continue
            try:
                p = int(re.sub(r"[\s.,\u00a0]", "", raw))
                if 1000 <= p <= 500_000:
                    update["price_eur"] = float(p)
                    break
            except (ValueError, IndexError):
                pass

    if not existing.get("mileage_km") and "mileage_km" not in update:
        for m in _RE_KM.finditer(html):
            raw = m.group(1) or ""
            if not raw:
                continue
            try:
                k = int(re.sub(r"[\s.,\u00a0]", "", raw))
                if 0 < k < 500_000:
                    update["mileage_km"] = k
                    break
            except (ValueError, IndexError):
                pass

    if not existing.get("year") and "year" not in update:
        m = _RE_YEAR.search(html)
        if m:
            y = int(m.group(1))
            if 1990 <= y <= 2027:
                update["year"] = y

    return update


def _is_scam(doc: dict) -> bool:
    p = doc.get("price_eur")
    if p and (p < 500 or p > 2_000_000):
        return True
    return False


async def run() -> None:
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    meili = httpx.AsyncClient(timeout=120.0)
    sess = AsyncSession()

    sem = asyncio.Semaphore(_CONC)
    totals = {"scanned": 0, "fetched": 0, "repaired": 0,
              "dead": 0, "sold": 0, "scam": 0, "unchanged": 0}
    pending_updates: list[dict] = []
    pending_deletes: list[str] = []

    # Meili pagination
    offset = 0
    while True:
        r = None
        for attempt in range(8):
            try:
                r = await meili.get(
                    f"{_MEILI_URL}/indexes/{_INDEX}/documents",
                    headers=_HDR_MEILI,
                    params={"limit": _BATCH, "offset": offset,
                            "fields": "vehicle_ulid,source_url,make,model,variant,"
                                      "year,mileage_km,price_eur,thumbnail_url,"
                                      "description,fuel_type,transmission,power_kw,"
                                      "power_hp,listing_status"},
                )
                if r.status_code == 200:
                    break
                log.warning("meili GET %d attempt %d", r.status_code, attempt)
            except Exception as exc:
                log.warning("meili GET err attempt %d: %s", attempt, exc)
            await asyncio.sleep(3 + attempt * 2)
        if not r or r.status_code != 200:
            log.error("meili GET failed after retries, sleeping 60s and retrying offset")
            await asyncio.sleep(60)
            continue
        docs = r.json().get("results", [])
        if not docs:
            break

        # Skip docs not in this shard
        def in_shard(ulid: str) -> bool:
            if _SHARDS <= 1:
                return True
            h = ulid[2:] if ulid.startswith("vi") else ulid
            try:
                return int(h[:8], 16) % _SHARDS == _SHARD
            except ValueError:
                return False

        async def _process(doc: dict) -> None:
            async with sem:
                totals["scanned"] += 1
                ulid = doc.get("vehicle_ulid") or ""
                if not in_shard(ulid):
                    return

                missing = [f for f in ("make", "model", "price_eur",
                                       "year", "mileage_km", "thumbnail_url",
                                       "description") if not doc.get(f)]
                if not missing:
                    totals["unchanged"] += 1
                    return

                if _is_scam(doc):
                    totals["scam"] += 1
                    pending_deletes.append(ulid)
                    return

                url = doc.get("source_url")
                if not url:
                    return

                status, html = await _fetch_html(sess, url)
                totals["fetched"] += 1
                if status in (404, 410):
                    totals["dead"] += 1
                    pending_deletes.append(ulid)
                    return
                if not html:
                    return

                if _looks_sold(html):
                    totals["sold"] += 1
                    pending_deletes.append(ulid)
                    return

                update = _merge_extracted(doc, html, url)
                if update:
                    update["vehicle_ulid"] = ulid
                    pending_updates.append(update)
                    totals["repaired"] += 1

        await asyncio.gather(*[_process(d) for d in docs])

        # Flush
        if len(pending_updates) >= 200:
            await _flush_updates(meili, pending_updates)
            pending_updates.clear()
        if len(pending_deletes) >= 500:
            await _flush_deletes(meili, pool, pending_deletes)
            pending_deletes.clear()

        offset += len(docs)
        if offset % 5000 == 0:
            log.info("scanned=%d repaired=%d dead=%d sold=%d scam=%d unchanged=%d",
                     totals["scanned"], totals["repaired"], totals["dead"],
                     totals["sold"], totals["scam"], totals["unchanged"])
        if len(docs) < _BATCH:
            break

    if pending_updates:
        await _flush_updates(meili, pending_updates)
    if pending_deletes:
        await _flush_deletes(meili, pool, pending_deletes)

    log.info("DONE totals=%s", totals)
    await sess.close()
    await meili.aclose()
    await pool.close()


async def _flush_updates(meili: httpx.AsyncClient, updates: list[dict]) -> None:
    if not updates:
        return
    r = await meili.put(
        f"{_MEILI_URL}/indexes/{_INDEX}/documents?primaryKey=vehicle_ulid",
        headers=_HDR_MEILI,
        json=updates,
    )
    if r.status_code not in (200, 201, 202):
        log.warning("meili PUT %d: %s", r.status_code, r.text[:200])
    else:
        log.info("flushed %d updates", len(updates))


async def _flush_deletes(meili: httpx.AsyncClient, pool: asyncpg.Pool, ulids: list[str]) -> None:
    if not ulids:
        return
    r = await meili.post(
        f"{_MEILI_URL}/indexes/{_INDEX}/documents/delete-batch",
        headers=_HDR_MEILI,
        json=ulids,
    )
    if r.status_code not in (200, 202):
        log.warning("meili delete %d: %s", r.status_code, r.text[:200])
    hashes = [u[2:] for u in ulids if u.startswith("vi")]
    if hashes:
        await pool.execute(
            "DELETE FROM vehicle_index WHERE url_hash = ANY($1::text[])",
            hashes,
        )
    log.info("deleted %d dead/sold/scam", len(ulids))


if __name__ == "__main__":
    asyncio.run(run())
