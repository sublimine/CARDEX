"""
Meilisearch enricher — fetches each vehicle URL, parses JSON-LD / Open
Graph, and pushes the enriched document directly into the `vehicles`
Meili index.

Why a dedicated module?
-----------------------
The existing `scrapers/enrich_worker.py` writes to PG `vehicle_events`
(append-only ENRICHED rows) and ClickHouse, but it never touches Meili.
The portal reads from Meili, so even after enrichment the cards still
show null prices/photos. This module short-circuits that gap by:

    1. Streaming from `vehicle_index` directly (no Redis stream needed)
    2. Fetching each URL with bounded concurrency
    3. Parsing JSON-LD `Car`/`Vehicle`/`Product`/`Offer`, falling back
       to Open Graph (`og:title`, `og:image`, `og:description`,
       `product:price:amount`)
    4. Pushing batched documents into Meili using the same primaryKey
       (`vehicle_ulid` = `vi<url_hash>`) so the existing minimal docs
       from `meili_bridge.py` are UPDATED in place

The enricher is idempotent and safe to re-run. It does not delete docs;
URLs that fail enrichment keep whatever they had after meili_bridge.

Fields populated when extractable
---------------------------------
    title (model + variant)
    price_eur
    year
    mileage_km
    fuel_type / transmission (when in JSON-LD)
    color
    thumbnail_url + thumb_url

Usage
-----
    python -m scrapers.discovery.meili_enricher
    MEILI_ENRICHER_LIMIT=500 python -m scrapers.discovery.meili_enricher

Environment
-----------
    DATABASE_URL              postgres://...
    MEILI_URL                 http://localhost:7700
    MEILI_MASTER_KEY          cardex_meili_dev_only
    MEILI_ENRICHER_BATCH      docs per Meili push (default 200)
    MEILI_ENRICHER_CONC       parallel HTTP fetches (default 30)
    MEILI_ENRICHER_LIMIT      cap total rows (default unlimited)
    MEILI_ENRICHER_TIMEOUT    per-fetch timeout in seconds (default 10)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import asyncpg
import httpx

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [meili_enricher] %(message)s",
)
log = logging.getLogger("meili_enricher")

_DSN = os.environ.get(
    "DATABASE_URL",
    "postgres://cardex:cardex_dev_only@localhost:5432/cardex",
)
_MEILI_URL = os.environ.get("MEILI_URL", "http://localhost:7700")
_MEILI_KEY = os.environ.get("MEILI_MASTER_KEY", "cardex_meili_dev_only")
_BATCH = int(os.environ.get("MEILI_ENRICHER_BATCH", "200"))
_CONC = int(os.environ.get("MEILI_ENRICHER_CONC", "30"))
_LIMIT = int(os.environ.get("MEILI_ENRICHER_LIMIT", "0"))
_TIMEOUT = float(os.environ.get("MEILI_ENRICHER_TIMEOUT", "10"))
_INDEX = "vehicles"

_HEADERS_MEILI = {
    "Authorization": f"Bearer {_MEILI_KEY}",
    "Content-Type": "application/json",
}

_HEADERS_HTTP = {
    "User-Agent": "CardexBot/1.0 (+https://cardex.eu/bot; enricher)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
}


# ── Parsers ──────────────────────────────────────────────────────────────────

_RE_LD_BLOCK = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
_RE_META = re.compile(
    r'<meta[^>]+(?:name|property)\s*=\s*["\']([^"\']+)["\'][^>]+content\s*=\s*["\']([^"\']*)["\']',
    re.IGNORECASE,
)
_RE_META_REV = re.compile(
    r'<meta[^>]+content\s*=\s*["\']([^"\']*)["\'][^>]+(?:name|property)\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_RE_TITLE = re.compile(r"<title[^>]*>([^<]+)</title>", re.IGNORECASE)
_RE_PRICE = re.compile(r"(?:€|EUR)\s*([\d.,\s]{3,12})|([\d.,\s]{3,12})\s*(?:€|EUR)", re.IGNORECASE)
_RE_YEAR = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")
_RE_KM = re.compile(r"(\d{1,3}[.,\s]?\d{3})\s*km", re.IGNORECASE)
_RE_KW_TYPE = re.compile(r"@type", re.IGNORECASE)


def _parse_meta(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _RE_META.finditer(html):
        out[m.group(1).lower()] = m.group(2)
    for m in _RE_META_REV.finditer(html):
        out.setdefault(m.group(2).lower(), m.group(1))
    return out


def _coerce_float(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    s = s.replace("\u00a0", "").replace(" ", "")
    # Heuristic: if it looks European with comma decimal, swap
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _coerce_int(v: Any) -> int | None:
    f = _coerce_float(v)
    return int(f) if f is not None else None


def _extract_jsonld_vehicle(html: str) -> dict[str, Any]:
    """Walk JSON-LD blocks looking for Car/Vehicle/Product."""
    result: dict[str, Any] = {}
    for block in _RE_LD_BLOCK.findall(html):
        block = block.strip()
        if not block:
            continue
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            # Try to repair common multi-doc concatenations
            try:
                data = json.loads("[" + block.replace("}{", "},{") + "]")
            except Exception:
                continue
        for item in (data if isinstance(data, list) else [data]):
            if isinstance(item, dict) and "@graph" in item:
                for sub in item.get("@graph") or []:
                    _merge_ld(result, sub)
            else:
                _merge_ld(result, item)
        if result.get("title") and result.get("price_eur"):
            return result
    return result


def _merge_ld(out: dict, item: Any) -> None:
    if not isinstance(item, dict):
        return
    types = item.get("@type") or ""
    if isinstance(types, list):
        types_set = {t.lower() for t in types if isinstance(t, str)}
    else:
        types_set = {str(types).lower()}
    if not types_set & {"car", "vehicle", "product", "individualproduct", "offer", "aggregateoffer"}:
        # Walk children
        for v in item.values():
            if isinstance(v, dict):
                _merge_ld(out, v)
            elif isinstance(v, list):
                for x in v:
                    _merge_ld(out, x)
        return

    name = item.get("name") or item.get("model") or item.get("vehicleConfiguration")
    if name and not out.get("title"):
        out["title"] = str(name).strip()

    brand = item.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    if brand and not out.get("make"):
        out["make"] = str(brand).strip()

    model = item.get("model") or item.get("vehicleConfiguration")
    if model and not out.get("model"):
        out["model"] = str(model).strip()

    color = item.get("color")
    if color and not out.get("color"):
        out["color"] = str(color).strip()[:40]

    fuel = item.get("fuelType") or item.get("vehicleFuelType")
    if fuel and not out.get("fuel_type"):
        out["fuel_type"] = _norm_fuel(str(fuel))

    tx = item.get("vehicleTransmission")
    if tx and not out.get("transmission"):
        out["transmission"] = _norm_tx(str(tx))

    km = item.get("mileageFromOdometer")
    if isinstance(km, dict):
        km = km.get("value")
    if km and not out.get("mileage_km"):
        v = _coerce_int(km)
        if v and 0 < v < 1_000_000:
            out["mileage_km"] = v

    year = (
        item.get("modelDate") or item.get("vehicleModelDate")
        or item.get("productionDate") or item.get("dateVehicleFirstRegistered")
    )
    if year and not out.get("year"):
        m = _RE_YEAR.search(str(year))
        if m:
            out["year"] = int(m.group(1))

    img = item.get("image")
    if isinstance(img, list):
        img = img[0] if img else None
    if isinstance(img, dict):
        img = img.get("url") or img.get("contentUrl")
    if img and not out.get("image"):
        out["image"] = str(img)

    offers = item.get("offers")
    if offers:
        if isinstance(offers, list):
            offers = offers[0] if offers else None
        if isinstance(offers, dict):
            p = offers.get("price") or offers.get("lowPrice")
            if p and not out.get("price_eur"):
                pv = _coerce_float(p)
                if pv and pv > 0:
                    out["price_eur"] = pv
            cur = offers.get("priceCurrency") or "EUR"
            out.setdefault("currency", cur)

    # Some sites place price directly on the Product
    if not out.get("price_eur"):
        p = item.get("price")
        if p:
            pv = _coerce_float(p)
            if pv and pv > 0:
                out["price_eur"] = pv


def _norm_fuel(s: str) -> str:
    s_low = s.lower()
    table = {
        "essence": "GASOLINE", "gasoline": "GASOLINE", "petrol": "GASOLINE",
        "diesel": "DIESEL", "gasoil": "DIESEL",
        "hybride": "HYBRID", "hybrid": "HYBRID",
        "electrique": "ELECTRIC", "electric": "ELECTRIC", "ev": "ELECTRIC",
        "lpg": "LPG", "gpl": "LPG", "cng": "CNG", "gnv": "CNG",
        "ethanol": "ETHANOL", "e85": "ETHANOL",
    }
    for key, val in table.items():
        if key in s_low:
            return val
    return s.upper()[:20]


def _norm_tx(s: str) -> str:
    s_low = s.lower()
    if "auto" in s_low or "bva" in s_low or "dsg" in s_low or "automatic" in s_low:
        return "AUTOMATIC"
    if "manu" in s_low or "bvm" in s_low:
        return "MANUAL"
    return s.upper()[:20]


def _extract_og(html: str) -> dict[str, Any]:
    meta = _parse_meta(html)
    out: dict[str, Any] = {}
    if v := meta.get("og:title"):
        out["title"] = v.strip()
    elif v := meta.get("twitter:title"):
        out["title"] = v.strip()
    if v := meta.get("og:image") or meta.get("twitter:image"):
        out["image"] = v.strip()
    if v := meta.get("og:description"):
        out["description"] = v.strip()
    if v := meta.get("product:price:amount") or meta.get("og:price:amount"):
        pv = _coerce_float(v)
        if pv and pv > 0:
            out["price_eur"] = pv
    return out


def _extract_html_fallback(html: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if m := _RE_TITLE.search(html):
        out["title"] = m.group(1).strip()
    return out


def _extract(html: str) -> dict[str, Any]:
    """Combined extractor: JSON-LD → OG → HTML title."""
    result = _extract_jsonld_vehicle(html)

    og = _extract_og(html)
    for k, v in og.items():
        if v and not result.get(k):
            result[k] = v

    if not result.get("title"):
        fallback = _extract_html_fallback(html)
        if t := fallback.get("title"):
            result["title"] = t

    # Salvage year/mileage from description if present
    if not result.get("year"):
        for source in (result.get("title", ""), result.get("description", "")):
            m = _RE_YEAR.search(source or "")
            if m:
                y = int(m.group(1))
                if 1990 <= y <= 2027:
                    result["year"] = y
                    break

    if not result.get("mileage_km"):
        for source in (result.get("title", ""), result.get("description", "")):
            m = _RE_KM.search(source or "")
            if m:
                v = _coerce_int(m.group(1).replace(" ", ""))
                if v and 0 < v < 1_000_000:
                    result["mileage_km"] = v
                    break

    if not result.get("price_eur"):
        # Last-resort: scan visible HTML for first €-prefixed number
        for source in (result.get("title", ""), result.get("description", "")):
            if not source:
                continue
            m = _RE_PRICE.search(source)
            if m:
                pv = _coerce_float(m.group(1) or m.group(2))
                if pv and 1000 < pv < 1_000_000:
                    result["price_eur"] = pv
                    break

    return result


# ── Pipeline ─────────────────────────────────────────────────────────────────

async def _fetch_one(client: httpx.AsyncClient, row: asyncpg.Record) -> dict[str, Any] | None:
    url = row["url_original"]
    try:
        resp = await client.get(url, headers=_HEADERS_HTTP, timeout=_TIMEOUT)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    html = resp.text
    if not html or len(html) < 500:
        return None

    meta = _extract(html)
    if not meta:
        return None

    img = meta.get("image")
    if img and not img.startswith(("http://", "https://")):
        img = urljoin(url, img)

    doc: dict[str, Any] = {"vehicle_ulid": f"vi{row['url_hash']}"}
    if t := meta.get("title"):
        # Heuristic split of title into make/model when JSON-LD didn't supply
        # both. Title formats vary; we just keep the cleaned-up title under
        # variant if make/model are already populated by the URL parser.
        doc["variant"] = t[:200]
    if make := meta.get("make"):
        doc["make"] = str(make)[:80]
    if model := meta.get("model"):
        doc["model"] = str(model)[:80]
    if v := meta.get("price_eur"):
        doc["price_eur"] = v
    if v := meta.get("year"):
        doc["year"] = v
    if v := meta.get("mileage_km"):
        doc["mileage_km"] = v
    if v := meta.get("fuel_type"):
        doc["fuel_type"] = v
    if v := meta.get("transmission"):
        doc["transmission"] = v
    if v := meta.get("color"):
        doc["color"] = v
    if img:
        doc["thumbnail_url"] = img
        doc["thumb_url"] = img
    return doc if len(doc) > 1 else None


async def _push_batch(meili: httpx.AsyncClient, docs: list[dict]) -> None:
    if not docs:
        return
    # PUT = partial update — merges fields with existing doc, preserves
    # source_url / source_country / listing_status / etc. that the
    # bridge populated. POST would REPLACE the full doc and destroy
    # those critical fields.
    r = await meili.put(
        f"{_MEILI_URL}/indexes/{_INDEX}/documents?primaryKey=vehicle_ulid",
        headers=_HEADERS_MEILI,
        json=docs,
    )
    if r.status_code not in (200, 201, 202):
        log.warning("meili push %d docs: %d %s", len(docs), r.status_code, r.text[:200])


async def run() -> None:
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4, command_timeout=120)
    fetch_client = httpx.AsyncClient(
        timeout=_TIMEOUT,
        follow_redirects=True,
        http2=True,
        limits=httpx.Limits(
            max_keepalive_connections=_CONC * 2,
            max_connections=_CONC * 4,
        ),
    )
    meili_client = httpx.AsyncClient(timeout=60.0)
    sem = asyncio.Semaphore(_CONC)

    log.info(
        "starting — concurrency=%d batch=%d limit=%d timeout=%.1fs",
        _CONC, _BATCH, _LIMIT or -1, _TIMEOUT,
    )

    sql = (
        "SELECT url_hash, url_original, source_domain, country "
        "FROM vehicle_index ORDER BY url_hash"
    )
    if _LIMIT > 0:
        sql += f" LIMIT {_LIMIT}"

    t0 = time.monotonic()
    pending_docs: list[dict] = []
    fetched = 0
    enriched = 0
    failed = 0

    async def _process(row: asyncpg.Record) -> dict | None:
        async with sem:
            return await _fetch_one(fetch_client, row)

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                tasks: list[asyncio.Task] = []
                async for row in conn.cursor(sql, prefetch=200):
                    tasks.append(asyncio.create_task(_process(row)))

                    # Drain completed tasks opportunistically
                    if len(tasks) >= _CONC * 4:
                        done, pending = await asyncio.wait(
                            tasks, return_when=asyncio.FIRST_COMPLETED,
                        )
                        tasks = list(pending)
                        for t in done:
                            fetched += 1
                            try:
                                doc = t.result()
                            except Exception:
                                doc = None
                            if doc:
                                pending_docs.append(doc)
                                enriched += 1
                            else:
                                failed += 1

                            if len(pending_docs) >= _BATCH:
                                await _push_batch(meili_client, pending_docs)
                                pending_docs = []

                            if fetched % 500 == 0:
                                rate = fetched / max(time.monotonic() - t0, 0.001)
                                log.info(
                                    "progress: fetched=%d enriched=%d failed=%d (%.0f/s)",
                                    fetched, enriched, failed, rate,
                                )

                # Drain remaining tasks
                if tasks:
                    for t in await asyncio.gather(*tasks, return_exceptions=True):
                        fetched += 1
                        if isinstance(t, dict):
                            pending_docs.append(t)
                            enriched += 1
                        else:
                            failed += 1
                        if len(pending_docs) >= _BATCH:
                            await _push_batch(meili_client, pending_docs)
                            pending_docs = []

        if pending_docs:
            await _push_batch(meili_client, pending_docs)

        elapsed = time.monotonic() - t0
        log.info(
            "done — fetched=%d enriched=%d failed=%d in %.1fs (%.0f docs/s)",
            fetched, enriched, failed, elapsed, fetched / elapsed if elapsed else 0,
        )
    finally:
        await fetch_client.aclose()
        await meili_client.aclose()
        await pool.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
