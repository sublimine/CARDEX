"""
Meilisearch enricher v2 — multi-strategy HTML extraction.

Pipeline per URL
----------------
1. HTTP GET. If 404/410/Gone → mark for DELETE.
2. SOLD detection: scan title/og:title for "out of stock", "vendu",
   "vendido", "verkauft", "sold", etc. → mark for DELETE.
3. JSON-LD walker (Car/Vehicle/Product/Offer/AggregateOffer).
4. Open Graph + meta extraction (og:title, og:image, og:description,
   product:price:amount, twitter:image, etc.).
5. **Body text scrape** (key fix): extract price/mileage/year from
   visible HTML even when JSON-LD only contains WebPage/Yoast schema.
   - price: ALL `\d{1,3}[\s.,]\d{3}\s*€` matches → keep ones with
     ≥2 occurrences (filters monthly leasing one-offs) → take MAX in
     range 1k-500k.
   - mileage: ALL `\d[\d\s.,]*\s*km` → keep ≥2 occurrences → median.
   - year: first 4-digit year in og:title, then page title, then body.
6. **Image extraction with logo filter**: og:image is preferred but
   skipped if it points at a known logo path; falls back to first
   `<img>` tag whose src contains a vehicle-photo signature
   (`/uploads/`, `/vehicule`, `/vehicles/`, `/voiture`, `/vo/`,
   `/stock/`, `/medias/`, listing-id digit run).

Outcomes per row
----------------
    enriched   → PUT partial update to Meili (preserves bridge fields)
    sold       → DELETE from Meili index AND from PG vehicle_index
    failed     → leave bridge stub doc in place

Usage
-----
    python -m scrapers.discovery.meili_enricher

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
import collections
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
}


# ── Sold-state markers ───────────────────────────────────────────────────────

_SOLD_MARKERS = (
    "out of stock",
    "out-of-stock",
    "vehicle sold",
    "véhicule vendu",
    "vehicule vendu",
    "occasion vendue",
    "voiture vendue",
    "déjà vendu",
    "deja vendu",
    "indisponible",
    "plus disponible",
    "vendue",
    "vendu",
    "vendido",
    "ya vendido",
    "no disponible",
    "verkauft",
    "nicht verfügbar",
    "nicht verfugbar",
    "sold out",
    "venduto",
    "non disponibile",
    "uitverkocht",
    "verkocht",
)


# ── Regex library ────────────────────────────────────────────────────────────

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
_RE_YEAR = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")

# Price: number with optional thousand separators, followed/preceded by €/EUR.
# Matches "24 590 €", "24,590€", "24.590 €", "€24590", etc.
_RE_PRICE = re.compile(
    r"(\d{1,3}(?:[\s.,\u00a0]\d{3})+|\d{4,6})\s*€"
    r"|€\s*(\d{1,3}(?:[\s.,\u00a0]\d{3})+|\d{4,6})"
)

# Mileage: number followed by km. Allow space/dot/comma thousand separators.
_RE_KM = re.compile(
    r"(\d{1,3}(?:[\s.,\u00a0]\d{3})+|\d{1,6})\s*km\b",
    re.IGNORECASE,
)

# Image extraction
_RE_IMG = re.compile(
    r'<img[^>]+(?:data-(?:src|lazy-src|original)|src)\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# Image src signatures suggesting it's a vehicle photo (not chrome/logo)
_IMG_VEHICLE_HINTS = (
    "/uploads/", "/upload/", "/vehicule", "/vehicles", "/voiture",
    "/vo/", "/stock/", "/medias/", "/inventory/", "/photo",
    "/cars/", "/auto/", "/v/",
)

# Image src signatures that mark it as chrome/UI (logo, icon, banner)
_IMG_NOISE_HINTS = (
    "logo", "icon", "favicon", "header", "footer", "banner", "background",
    "/avatar", "/sprite", "/placeholder", "blank.gif",
)


def _parse_meta(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _RE_META.finditer(html):
        out[m.group(1).lower()] = m.group(2)
    for m in _RE_META_REV.finditer(html):
        out.setdefault(m.group(2).lower(), m.group(1))
    return out


def _parse_int(raw: str) -> int | None:
    s = re.sub(r"[\s.,\u00a0]", "", raw)
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def _parse_float(raw: str) -> float | None:
    s = str(raw).strip().replace("\u00a0", "")
    s = re.sub(r"[\s]", "", s)
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


# ── JSON-LD walker ───────────────────────────────────────────────────────────

def _extract_jsonld(html: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for block in _RE_LD_BLOCK.findall(html):
        block = block.strip()
        if not block:
            continue
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            try:
                data = json.loads("[" + block.replace("}{", "},{") + "]")
            except Exception:
                continue
        for item in (data if isinstance(data, list) else [data]):
            _walk_ld(result, item)
    return result


def _walk_ld(out: dict, item: Any) -> None:
    if not isinstance(item, dict):
        if isinstance(item, list):
            for x in item:
                _walk_ld(out, x)
        return

    # Recurse into @graph
    if "@graph" in item:
        for sub in item.get("@graph") or []:
            _walk_ld(out, sub)

    types = item.get("@type") or ""
    if isinstance(types, list):
        types_set = {str(t).lower() for t in types}
    else:
        types_set = {str(types).lower()}

    interesting = bool(types_set & {
        "car", "vehicle", "product", "individualproduct",
        "offer", "aggregateoffer",
    })

    if interesting:
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
            v = _parse_int(str(km))
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
                    pv = _parse_float(p)
                    if pv and pv > 0:
                        out["price_eur"] = pv

        if not out.get("price_eur"):
            p = item.get("price")
            if p:
                pv = _parse_float(p)
                if pv and pv > 0:
                    out["price_eur"] = pv

    # Always recurse into nested objects
    for v in item.values():
        if isinstance(v, (dict, list)):
            _walk_ld(out, v)


# ── Body text scrape ─────────────────────────────────────────────────────────

def _strip_tags(html: str) -> str:
    """Remove script/style blocks then strip tags. Cheap, not bulletproof."""
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.I)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _scrape_price(text: str) -> int | None:
    """
    Find all price-like matches. Pick the price that appears most often
    (most likely the headline price shown multiple times) within a sane
    vehicle range. Filters monthly-leasing one-offs.

    Range: 1000 — 300_000 €. Anything above is almost certainly a sum of
    multiple prices concatenated by the regex (e.g. "260 000 €" formed
    from "260€/mois" + "00 €" = noise) or a typo. The few legitimate
    >300k cars are exotic and out of scope for first-pass enrichment.
    """
    prices: list[int] = []
    for m in _RE_PRICE.finditer(text):
        raw = m.group(1) or m.group(2) or ""
        v = _parse_int(raw)
        if v is None:
            continue
        if 1000 <= v <= 300_000:
            prices.append(v)
    if not prices:
        return None
    counts = collections.Counter(prices)
    # Most-common wins. On tie, prefer the lower value (avoids inflated
    # 6-digit noise from mid-tier cars whose body has many monthly amounts).
    best, _ = max(counts.items(), key=lambda kv: (kv[1], -kv[0]))
    return best


def _scrape_mileage(text: str) -> int | None:
    mileages: list[int] = []
    for m in _RE_KM.finditer(text):
        v = _parse_int(m.group(1))
        if v is None:
            continue
        if 0 < v < 500_000:
            mileages.append(v)
    if not mileages:
        return None
    counts = collections.Counter(mileages)
    best, _ = max(counts.items(), key=lambda kv: (kv[1], -kv[0]))
    return best


def _scrape_year(html: str, og_title: str, og_desc: str) -> int | None:
    for source in (og_title, og_desc, html[:8000]):
        if not source:
            continue
        m = _RE_YEAR.search(source)
        if not m:
            continue
        y = int(m.group(1))
        if 1990 <= y <= 2027:
            return y
    return None


def _looks_like_logo(src: str) -> bool:
    s = src.lower()
    return any(h in s for h in _IMG_NOISE_HINTS)


def _looks_like_vehicle_photo(src: str) -> bool:
    s = src.lower()
    if _looks_like_logo(s):
        return False
    if any(h in s for h in _IMG_VEHICLE_HINTS):
        return True
    # Has a 5+ digit run in the path (likely listing ID)
    if re.search(r"/\d{5,}", s):
        return True
    return False


def _scrape_image(html: str, og_image: str | None, base_url: str) -> str | None:
    # Prefer og:image when it doesn't look like a logo
    if og_image and not _looks_like_logo(og_image):
        return urljoin(base_url, og_image)
    # Walk all <img> tags, take the first vehicle-like
    for m in _RE_IMG.finditer(html):
        src = m.group(1).strip()
        if not src or src.startswith("data:"):
            continue
        if _looks_like_vehicle_photo(src):
            return urljoin(base_url, src)
    # Last resort: og:image even if it looks like a logo (better than nothing)
    if og_image:
        return urljoin(base_url, og_image)
    return None


def _norm_fuel(s: str) -> str:
    s_low = s.lower()
    table = {
        "essence": "GASOLINE", "gasoline": "GASOLINE", "petrol": "GASOLINE",
        "diesel": "DIESEL", "gasoil": "DIESEL", "blue hdi": "DIESEL", "bluehdi": "DIESEL",
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
    if "auto" in s_low or "bva" in s_low or "dsg" in s_low or "automatic" in s_low or "eat" in s_low:
        return "AUTOMATIC"
    if "manu" in s_low or "bvm" in s_low:
        return "MANUAL"
    return s.upper()[:20]


# ── Main extractor ───────────────────────────────────────────────────────────

def _is_sold(html: str, og_title: str) -> bool:
    title_block = (og_title or "").lower()
    title_match = _RE_TITLE.search(html)
    if title_match:
        title_block += " " + title_match.group(1).lower()
    return any(m in title_block for m in _SOLD_MARKERS)


def extract(html: str, url: str) -> tuple[dict[str, Any] | None, bool]:
    """
    Returns (doc, sold).
        doc=None, sold=True   → mark for DELETE (sold/unavailable)
        doc=None, sold=False  → no extractable data, leave as-is
        doc=dict, sold=False  → enriched fields to PUT into Meili
    """
    meta = _parse_meta(html)
    og_title = meta.get("og:title", "") or meta.get("twitter:title", "")
    og_image = meta.get("og:image", "") or meta.get("twitter:image", "")
    og_desc = meta.get("og:description", "") or meta.get("description", "")

    if _is_sold(html, og_title):
        return None, True

    # JSON-LD pass first
    result = _extract_jsonld(html)

    # Body text scrape — fills holes left by JSON-LD
    text = _strip_tags(html[:120_000])  # cap to first 120 KB

    if not result.get("price_eur"):
        v = _scrape_price(text)
        if v:
            result["price_eur"] = float(v)

    if not result.get("mileage_km"):
        v = _scrape_mileage(text)
        if v:
            result["mileage_km"] = v

    if not result.get("year"):
        y = _scrape_year(text, og_title, og_desc)
        if y:
            result["year"] = y

    if not result.get("image"):
        img = _scrape_image(html, og_image, url)
        if img:
            result["image"] = img

    # Always resolve image against base URL — JSON-LD can return
    # protocol-relative or absolute paths.
    if result.get("image"):
        result["image"] = urljoin(url, result["image"])

    if not result.get("title") and og_title:
        result["title"] = og_title

    if not result:
        return None, False

    # Build the Meili partial-update doc
    doc: dict[str, Any] = {}
    if t := result.get("title"):
        # Clean the title: strip prefixes like "Occasion " and suffixes like " | Site"
        clean = re.sub(r"^(?:occasion|new|nuevo|gebraucht|used)\s+", "", t, flags=re.I)
        clean = re.split(r"\s*[|–—-]\s*[A-Z][^|]*$", clean)[0].strip()
        doc["variant"] = clean[:200]
    if make := result.get("make"):
        doc["make"] = str(make)[:80]
    if model := result.get("model"):
        doc["model"] = str(model)[:80]
    if v := result.get("price_eur"):
        doc["price_eur"] = v
    if v := result.get("year"):
        doc["year"] = v
    if v := result.get("mileage_km"):
        doc["mileage_km"] = v
    if v := result.get("fuel_type"):
        doc["fuel_type"] = v
    if v := result.get("transmission"):
        doc["transmission"] = v
    if v := result.get("color"):
        doc["color"] = v
    if img := result.get("image"):
        doc["thumbnail_url"] = img
        doc["thumb_url"] = img

    return (doc if doc else None), False


# ── Pipeline ─────────────────────────────────────────────────────────────────

class _Counters:
    def __init__(self) -> None:
        self.fetched = 0
        self.enriched = 0
        self.sold = 0
        self.failed = 0


async def _fetch_one(
    client: httpx.AsyncClient, row: asyncpg.Record,
) -> tuple[str, dict[str, Any] | None]:
    """
    Returns ('enriched'|'sold'|'dead'|'failed', doc_or_none).
    """
    url = row["url_original"]
    try:
        resp = await client.get(url, headers=_HEADERS_HTTP, timeout=_TIMEOUT)
    except Exception:
        return "failed", None
    if resp.status_code in (404, 410):
        return "dead", None
    if resp.status_code != 200:
        return "failed", None
    html = resp.text
    if not html or len(html) < 500:
        return "failed", None

    doc, sold = extract(html, url)
    if sold:
        return "sold", None
    if doc is None:
        return "failed", None

    doc["vehicle_ulid"] = f"vi{row['url_hash']}"
    return "enriched", doc


async def _push_meili(meili: httpx.AsyncClient, docs: list[dict]) -> None:
    if not docs:
        return
    r = await meili.put(
        f"{_MEILI_URL}/indexes/{_INDEX}/documents?primaryKey=vehicle_ulid",
        headers=_HEADERS_MEILI,
        json=docs,
    )
    if r.status_code not in (200, 201, 202):
        log.warning("meili PUT %d docs: %d %s", len(docs), r.status_code, r.text[:200])


async def _delete_meili(meili: httpx.AsyncClient, ulids: list[str]) -> None:
    if not ulids:
        return
    r = await meili.post(
        f"{_MEILI_URL}/indexes/{_INDEX}/documents/delete-batch",
        headers=_HEADERS_MEILI,
        json=ulids,
    )
    if r.status_code not in (200, 201, 202):
        log.warning("meili DELETE %d: %d %s", len(ulids), r.status_code, r.text[:200])


async def _delete_pg(pool: asyncpg.Pool, hashes: list[str]) -> None:
    if not hashes:
        return
    await pool.execute(
        "DELETE FROM vehicle_index WHERE url_hash = ANY($1::text[])",
        hashes,
    )


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
        "starting v2 — concurrency=%d batch=%d limit=%d timeout=%.1fs",
        _CONC, _BATCH, _LIMIT or -1, _TIMEOUT,
    )

    sql = (
        "SELECT url_hash, url_original, source_domain, country "
        "FROM vehicle_index ORDER BY url_hash"
    )
    if _LIMIT > 0:
        sql += f" LIMIT {_LIMIT}"

    counters = _Counters()
    pending_docs: list[dict] = []
    pending_dead: list[tuple[str, str]] = []  # (ulid, url_hash)

    async def _drain(done_tasks: list[asyncio.Task]) -> None:
        nonlocal pending_docs, pending_dead
        for t in done_tasks:
            counters.fetched += 1
            try:
                outcome, doc = t.result()
            except Exception:
                outcome, doc = "failed", None
            if outcome == "enriched" and doc:
                pending_docs.append(doc)
                counters.enriched += 1
            elif outcome in ("sold", "dead"):
                counters.sold += 1
                # Build ulid from the row's url_hash; we stored it on the task
                row = t.row  # type: ignore[attr-defined]
                pending_dead.append((f"vi{row['url_hash']}", row["url_hash"]))
            else:
                counters.failed += 1

            if len(pending_docs) >= _BATCH:
                await _push_meili(meili_client, pending_docs)
                pending_docs = []
            if len(pending_dead) >= _BATCH:
                ulids = [u for u, _ in pending_dead]
                hashes = [h for _, h in pending_dead]
                await _delete_meili(meili_client, ulids)
                await _delete_pg(pool, hashes)
                pending_dead = []

            if counters.fetched % 500 == 0:
                rate = counters.fetched / max(time.monotonic() - t0, 0.001)
                log.info(
                    "progress: fetched=%d enriched=%d sold/dead=%d failed=%d (%.0f/s)",
                    counters.fetched, counters.enriched, counters.sold,
                    counters.failed, rate,
                )

    async def _process(row: asyncpg.Record) -> tuple[str, dict | None]:
        async with sem:
            return await _fetch_one(fetch_client, row)

    t0 = time.monotonic()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                tasks: list[asyncio.Task] = []
                async for row in conn.cursor(sql, prefetch=200):
                    task = asyncio.create_task(_process(row))
                    task.row = row  # type: ignore[attr-defined]
                    tasks.append(task)

                    if len(tasks) >= _CONC * 4:
                        done, pending = await asyncio.wait(
                            tasks, return_when=asyncio.FIRST_COMPLETED,
                        )
                        tasks = list(pending)
                        await _drain(list(done))

                if tasks:
                    done, _ = await asyncio.wait(tasks)
                    await _drain(list(done))

        if pending_docs:
            await _push_meili(meili_client, pending_docs)
        if pending_dead:
            ulids = [u for u, _ in pending_dead]
            hashes = [h for _, h in pending_dead]
            await _delete_meili(meili_client, ulids)
            await _delete_pg(pool, hashes)

        elapsed = time.monotonic() - t0
        log.info(
            "done — fetched=%d enriched=%d sold/dead=%d failed=%d in %.1fs (%.0f docs/s)",
            counters.fetched, counters.enriched, counters.sold, counters.failed,
            elapsed, counters.fetched / elapsed if elapsed else 0,
        )
    finally:
        await fetch_client.aclose()
        await meili_client.aclose()
        await pool.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
