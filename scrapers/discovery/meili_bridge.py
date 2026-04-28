"""
Meilisearch bridge — pushes `vehicle_index` rows directly into the
`vehicles` Meili index that the marketplace API + frontend already query.

Architectural context
---------------------
The CARDEX portal architecture:

    PG.vehicles (enriched listings)  →  meili-sync worker  →  Meili index "vehicles"
                                                                        ↑
                                              API marketplace.go reads here

The discovery pipeline produces ephemeral URL pointers in `vehicle_index`
(no make/model/price/etc.) and never touches PG.vehicles or the
`stream:meili_sync`. This bridge cuts the gap by reading vehicle_index
directly and pushing minimal documents straight into Meili.

URL parsing strategy
--------------------
Per-CMS parsers, falling back to a generic brand-segment parser:

    edenauto       /voitures/{occasion|neuves|0km}/{city}/{brand}/{model}/{fuel}/{trim-slug}/{stockId}/
                   used by *.edenauto.com, audi-bordeaux, sipa, groupebarbier,
                   volkswagen-bordeaux, groupe-deluc, groupe-portedauphine, ...
    distinxion     /voitures/{brand}/{model[-suffix]}[/{stockId}]
    debardautomobiles /vehicule-{brand}-{model-trim-slug}/{stockId}
    wp_car_manager (car-automobiles.fr et al.):
                   /{vehicule|stock-neuf}/{model-trim-slug}/
    generic        any URL with a brand token in a path segment

Each parser returns the same shape:
    {make, model, variant, year, mileage_km, fuel_type, transmission, city}

Schema configuration
--------------------
Mirrors services/pipeline/cmd/meili-sync/main.go::ensureIndex.

Usage
-----
    python -m scrapers.discovery.meili_bridge

Environment
-----------
    DATABASE_URL          postgres://...
    MEILI_URL             http://localhost:7700
    MEILI_MASTER_KEY      cardex_meili_dev_only
    MEILI_BRIDGE_BATCH    docs per push  (default 5000)
    MEILI_BRIDGE_LIMIT    cap total rows (default unlimited)
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Any, Callable
from urllib.parse import unquote, urlparse

import asyncpg
import httpx

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [meili_bridge] %(message)s",
)
log = logging.getLogger("meili_bridge")

_DSN = os.environ.get(
    "DATABASE_URL",
    "postgres://cardex:cardex_dev_only@localhost:5432/cardex",
)
_MEILI_URL = os.environ.get("MEILI_URL", "http://localhost:7700")
_MEILI_KEY = os.environ.get("MEILI_MASTER_KEY", "cardex_meili_dev_only")
_BATCH = int(os.environ.get("MEILI_BRIDGE_BATCH", "5000"))
_LIMIT = int(os.environ.get("MEILI_BRIDGE_LIMIT", "0"))
_INDEX = "vehicles"

_HEADERS = {
    "Authorization": f"Bearer {_MEILI_KEY}",
    "Content-Type": "application/json",
}


# ── Brand lexicon ────────────────────────────────────────────────────────────
# Lower-case, hyphen-stripped tokens. Order matters: longer/multi-word first
# so "alfa-romeo" matches before "alfa".

_BRANDS_RAW = (
    "alfa-romeo", "aston-martin", "land-rover", "mercedes-benz",
    "rolls-royce", "fiat-professional",
    "alfa", "audi", "bentley", "bmw", "byd",
    "cadillac", "chevrolet", "chrysler", "citroen", "cupra", "dacia", "daf",
    "ds", "ferrari", "fiat", "ford", "honda", "hyundai", "infiniti", "isuzu",
    "iveco", "jaguar", "jeep", "kia", "lamborghini", "lancia",
    "lexus", "lotus", "maserati", "maybach", "mazda", "mclaren", "mercedes",
    "mg", "mini", "mitsubishi", "nissan", "opel", "peugeot",
    "polestar", "porsche", "ram", "renault", "rover", "saab",
    "seat", "skoda", "smart", "ssangyong", "subaru", "suzuki", "tesla",
    "toyota", "vauxhall", "volkswagen", "vw", "volvo", "dangel",
)

# Pretty display names for brand tokens.
_BRAND_DISPLAY = {
    "alfa-romeo": "Alfa Romeo", "aston-martin": "Aston Martin",
    "land-rover": "Land Rover", "mercedes-benz": "Mercedes-Benz",
    "rolls-royce": "Rolls-Royce", "fiat-professional": "Fiat Professional",
    "vw": "Volkswagen", "ds": "DS", "bmw": "BMW", "kia": "KIA",
    "mg": "MG", "mini": "MINI", "byd": "BYD",
}

_BRANDS = _BRANDS_RAW

_FUEL_TOKENS = {
    "essence": "GASOLINE", "gasoline": "GASOLINE", "petrol": "GASOLINE",
    "diesel": "DIESEL", "gasoil": "DIESEL",
    "hybride": "HYBRID", "hybrid": "HYBRID",
    "electrique": "ELECTRIC", "electric": "ELECTRIC", "ev": "ELECTRIC",
    "gpl": "LPG", "lpg": "LPG", "gnv": "CNG", "cng": "CNG",
    "ethanol": "ETHANOL", "e85": "ETHANOL",
}

_RE_YEAR = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")
_RE_KM = re.compile(r"(\d{2,3}[._]?\d{3})\s*km", re.I)


def _slugify(s: str) -> str:
    s = unquote(s).lower()
    s = re.sub(r"[._]+", "-", s)
    s = re.sub(r"[^a-z0-9-/]+", "-", s)
    return s.strip("-/")


def _brand_display(token: str) -> str:
    if token in _BRAND_DISPLAY:
        return _BRAND_DISPLAY[token]
    return " ".join(w.capitalize() for w in token.split("-"))


def _model_from_tokens(tokens: list[str]) -> str:
    """Pick model name(s) from tokens, stop at year/digit/known fuel."""
    out: list[str] = []
    for tok in tokens:
        if not tok:
            continue
        if _RE_YEAR.fullmatch(tok):
            break
        if tok.isdigit() and len(tok) >= 4:
            break
        if tok in _FUEL_TOKENS:
            break
        if tok.endswith("km") and tok[:-2].isdigit():
            break
        out.append(tok)
        if len(out) >= 2:
            break
    return " ".join(out).title()


def _path_segments(url: str) -> list[str]:
    try:
        path = urlparse(url).path
    except Exception:
        return []
    return [_slugify(s) for s in path.split("/") if s.strip()]


# ── Per-CMS parsers ──────────────────────────────────────────────────────────

def _parse_edenauto(segs: list[str]) -> dict[str, Any] | None:
    """
    Edenauto / sipa / groupe-deluc / audi-bordeaux / groupebarbier /
    volkswagen-bordeaux / groupe-portedauphine pattern:

        /voitures/{occasion|neuves|0km}/{city}/{brand}/{model}/{fuel}/{trim}/{stockId}/

    Also occasionally:
        /vehicules-utilitaires/{brand}/{model}/{trim}/{stockId}/
    """
    if not segs:
        return None
    if segs[0] not in ("voitures", "vehicules-utilitaires", "vehicules"):
        return None

    # Walk segments looking for the brand token.
    brand_idx = -1
    brand = ""
    for i, s in enumerate(segs[1:], start=1):
        if s in _BRANDS:
            brand_idx = i
            brand = s
            break
    if brand_idx < 0:
        return None

    after = segs[brand_idx + 1:]
    model = after[0] if after else ""
    fuel = ""
    trim = ""
    stock_id = ""
    if len(after) >= 2 and after[1] in _FUEL_TOKENS:
        fuel = _FUEL_TOKENS[after[1]]
        if len(after) >= 3:
            trim = after[2]
        if len(after) >= 4 and after[-1].isdigit() and len(after[-1]) >= 5:
            stock_id = after[-1]
    elif len(after) >= 2 and after[-1].isdigit() and len(after[-1]) >= 5:
        stock_id = after[-1]
        trim = after[1] if len(after) >= 3 else ""

    return {
        "make":         _brand_display(brand),
        "model":        model.replace("-", " ").title() if model else "",
        "variant":      trim.replace("-", " ") if trim else None,
        "fuel_type":    fuel or None,
        "stock_id":     stock_id or None,
    }


def _parse_distinxion(segs: list[str]) -> dict[str, Any] | None:
    """
        /voitures/{brand}/{model[-suffix]}[/{stockId}]
    """
    if len(segs) < 3 or segs[0] != "voitures":
        return None
    brand = segs[1]
    if brand not in _BRANDS:
        return None
    model_seg = segs[2]
    model_tokens = model_seg.split("-")
    return {
        "make":      _brand_display(brand),
        "model":     _model_from_tokens(model_tokens),
        "variant":   None,
        "fuel_type": None,
        "stock_id":  segs[3] if len(segs) >= 4 and segs[3].isdigit() else None,
    }


def _parse_debardautomobiles(segs: list[str]) -> dict[str, Any] | None:
    """
        /vehicule-{brand}-{model-trim-slug}/{stockId}
    """
    if not segs:
        return None
    first = segs[0]
    if not first.startswith("vehicule-"):
        return None
    body = first[len("vehicule-"):]
    for brand in _BRANDS:
        if body == brand or body.startswith(brand + "-"):
            rest = body[len(brand):].lstrip("-")
            tokens = rest.split("-") if rest else []
            return {
                "make":      _brand_display(brand),
                "model":     _model_from_tokens(tokens),
                "variant":   rest.replace("-", " ") if rest else None,
                "fuel_type": _detect_fuel(tokens),
                "stock_id":  segs[1] if len(segs) >= 2 and segs[1].isdigit() else None,
            }
    return None


def _parse_wp_car_manager(segs: list[str]) -> dict[str, Any] | None:
    """
    WordPress / Car Manager plugin sites (car-automobiles.fr,
    debardautomobiles fallback, etc.):

        /{vehicule|stock-neuf|annonce|fiche}/{slug}/

    Slug is just a model+trim with no brand. Best-effort: probe slug
    tokens against brand list.
    """
    if not segs:
        return None
    if segs[0] not in ("vehicule", "stock-neuf", "annonce", "fiche"):
        return None
    if len(segs) < 2:
        return None
    slug = segs[1]
    tokens = slug.split("-")
    # Try to find brand in slug
    for i, tok in enumerate(tokens):
        if tok in _BRANDS:
            return {
                "make":      _brand_display(tok),
                "model":     _model_from_tokens(tokens[i + 1:]),
                "variant":   slug.replace("-", " "),
                "fuel_type": _detect_fuel(tokens),
                "stock_id":  None,
            }
    # No brand in slug — return slug as variant only
    return {
        "make":      "",
        "model":     _model_from_tokens(tokens),
        "variant":   slug.replace("-", " "),
        "fuel_type": _detect_fuel(tokens),
        "stock_id":  None,
    }


def _parse_generic(segs: list[str]) -> dict[str, Any] | None:
    """Fallback: scan path for brand token in any segment."""
    for i, seg in enumerate(segs):
        for brand in _BRANDS:
            if seg == brand:
                rest_seg = segs[i + 1] if i + 1 < len(segs) else ""
                tokens = rest_seg.split("-") if rest_seg else []
                return {
                    "make":      _brand_display(brand),
                    "model":     _model_from_tokens(tokens),
                    "variant":   rest_seg.replace("-", " ") if rest_seg else None,
                    "fuel_type": _detect_fuel(tokens),
                    "stock_id":  None,
                }
            if seg.startswith(brand + "-"):
                rest = seg[len(brand):].lstrip("-")
                tokens = rest.split("-")
                return {
                    "make":      _brand_display(brand),
                    "model":     _model_from_tokens(tokens),
                    "variant":   rest.replace("-", " "),
                    "fuel_type": _detect_fuel(tokens),
                    "stock_id":  None,
                }
    return None


def _detect_fuel(tokens: list[str]) -> str | None:
    for tok in tokens:
        if tok in _FUEL_TOKENS:
            return _FUEL_TOKENS[tok]
    return None


# ── Domain → parser routing ──────────────────────────────────────────────────

def _select_parser(domain: str) -> Callable[[list[str]], dict[str, Any] | None]:
    d = domain.lower()
    if d.endswith(".edenauto.com") or d == "edenauto.com" or d == "www.edenauto.com":
        return _parse_edenauto
    if d in (
        "www.audi-bordeaux.fr", "www.sipa-automobiles.fr",
        "www.groupebarbier.fr", "www.volkswagen-bordeaux.fr",
        "www.groupe-deluc.com", "www.groupe-portedauphine.fr",
        "www.automobiles-duhau.fr",
    ):
        return _parse_edenauto
    if d == "www.distinxion.fr":
        return _parse_distinxion
    if d == "debardautomobiles.com":
        return _parse_debardautomobiles
    if d in ("car-automobiles.fr", "www.car-automobiles.fr"):
        return _parse_wp_car_manager
    return _parse_generic


def _extract_year(url: str) -> int | None:
    m = _RE_YEAR.search(url)
    if not m:
        return None
    y = int(m.group(1))
    if 1990 <= y <= 2027:
        return y
    return None


def _extract_mileage(url: str) -> int | None:
    m = _RE_KM.search(url)
    if not m:
        return None
    raw = m.group(1).replace(".", "").replace("_", "")
    try:
        v = int(raw)
        if 0 < v < 1_000_000:
            return v
    except ValueError:
        pass
    return None


def _platform_from_domain(domain: str) -> str:
    parts = domain.split(".")
    if len(parts) >= 2 and parts[0] == "www":
        parts = parts[1:]
    if not parts:
        return domain.upper()
    head = parts[0]
    if "-" in head:
        head = head.split("-", 1)[0]
    return head.upper()


def _row_to_doc(row: asyncpg.Record) -> dict[str, Any] | None:
    url = row["url_original"]
    h = row["url_hash"]
    domain = row["source_domain"]
    segs = _path_segments(url)

    parsed = _select_parser(domain)(segs)
    if parsed is None:
        parsed = _parse_generic(segs) or {}

    make = parsed.get("make") or ""
    model = parsed.get("model") or ""

    # Final fallback: pretty domain name as the make
    if not make:
        d_clean = domain
        if d_clean.startswith("www."):
            d_clean = d_clean[4:]
        make = d_clean.split(".")[0].replace("-", " ").title() or "Vehicle"

    return {
        "vehicle_ulid":     f"vi{h}",
        "make":             make,
        "model":            model,
        "variant":          parsed.get("variant"),
        "year":             _extract_year(url),
        "mileage_km":       _extract_mileage(url),
        "price_eur":        None,
        "fuel_type":        parsed.get("fuel_type"),
        "transmission":     None,
        "color":            None,
        "source_country":   row["country"],
        "source_platform":  _platform_from_domain(domain),
        "source_url":       url,
        "thumbnail_url":    None,
        "thumb_url":        None,
        "h3_res4":          None,
        "listing_status":   "ACTIVE",
    }


# ── Meili setup ──────────────────────────────────────────────────────────────

async def _ensure_index(client: httpx.AsyncClient) -> None:
    log.info("ensuring index '%s' exists with correct schema", _INDEX)
    r = await client.post(
        f"{_MEILI_URL}/indexes",
        headers=_HEADERS,
        json={"uid": _INDEX, "primaryKey": "vehicle_ulid"},
    )
    if r.status_code not in (200, 201, 202):
        body = r.text
        if "already_exists" not in body and "already exists" not in body:
            log.warning("create index returned %d: %s", r.status_code, body[:200])

    await client.put(
        f"{_MEILI_URL}/indexes/{_INDEX}/settings/searchable-attributes",
        headers=_HEADERS,
        json=["make", "model", "variant", "color", "fuel_type", "transmission"],
    )
    await client.put(
        f"{_MEILI_URL}/indexes/{_INDEX}/settings/filterable-attributes",
        headers=_HEADERS,
        json=[
            "make", "model", "year", "mileage_km", "price_eur",
            "source_country", "fuel_type", "transmission",
            "listing_status", "h3_res4",
        ],
    )
    await client.put(
        f"{_MEILI_URL}/indexes/{_INDEX}/settings/sortable-attributes",
        headers=_HEADERS,
        json=["price_eur", "mileage_km", "year"],
    )
    # Lift the default 1000 cap on facet/total counters
    await client.patch(
        f"{_MEILI_URL}/indexes/{_INDEX}/settings/pagination",
        headers=_HEADERS,
        json={"maxTotalHits": 10_000_000},
    )
    log.info("index settings updated (pagination cap = 10M)")


async def _push_batch(client: httpx.AsyncClient, docs: list[dict]) -> None:
    r = await client.post(
        f"{_MEILI_URL}/indexes/{_INDEX}/documents?primaryKey=vehicle_ulid",
        headers=_HEADERS,
        json=docs,
    )
    if r.status_code not in (200, 201, 202):
        log.warning("push %d docs failed: %d %s", len(docs), r.status_code, r.text[:200])


# ── Pipeline ─────────────────────────────────────────────────────────────────

async def run() -> None:
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4, command_timeout=120)
    client = httpx.AsyncClient(timeout=120.0)

    try:
        await _ensure_index(client)

        sql = (
            "SELECT url_hash, url_original, source_domain, country "
            "FROM vehicle_index ORDER BY url_hash"
        )
        if _LIMIT > 0:
            sql += f" LIMIT {_LIMIT}"

        log.info("streaming rows from vehicle_index (batch=%d limit=%d)", _BATCH, _LIMIT or -1)

        t0 = time.monotonic()
        total = 0
        skipped = 0
        batch: list[dict] = []

        async with pool.acquire() as conn:
            async with conn.transaction():
                async for row in conn.cursor(sql, prefetch=_BATCH):
                    doc = _row_to_doc(row)
                    if doc is None:
                        skipped += 1
                        continue
                    batch.append(doc)
                    if len(batch) >= _BATCH:
                        await _push_batch(client, batch)
                        total += len(batch)
                        batch = []
                        if total % (_BATCH * 4) == 0:
                            elapsed = time.monotonic() - t0
                            rate = total / elapsed if elapsed > 0 else 0
                            log.info("pushed %d docs (%.0f/s)", total, rate)

        if batch:
            await _push_batch(client, batch)
            total += len(batch)

        elapsed = time.monotonic() - t0
        log.info(
            "done — %d docs pushed (%d skipped) in %.1fs (%.0f docs/s)",
            total, skipped, elapsed, total / elapsed if elapsed else 0,
        )
    finally:
        await client.aclose()
        await pool.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
