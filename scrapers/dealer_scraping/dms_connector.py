"""
DMS / inventory-widget connector (frente C, backlog) — harvest the embedded feed.

A large share of dealers (esp. DE) render their stock from a third-party DMS/widget
(Modix, mobile.de Händler, AutoScout24 dealer, PlanetVO, …). The vehicles live on the
provider, embedded via a client-side script that calls the provider's API. Because
Playwright captures EVERY response — including cross-origin XHR — rendering the dealer's
catalog page makes that widget call its API, whose JSON ARRAY is the dealer's whole
inventory. This connector finds that array and normalizes each entry to a record, reusing
the ``playwright_xhr`` normalizer — so it is provider-agnostic: no per-provider reverse
engineering, just "render the catalog, capture the inventory JSON".

The array-finding + per-entry normalization is PURE (JSON in → records out), unit-tested
without a browser; ``harvest_inventory_xhr`` is the thin live wrapper.
"""
from __future__ import annotations

import logging

from scrapers.pipeline.normalize import to_record
from scrapers.pipeline.playwright_xhr import _vehicle_score, vehicle_json_to_raw
from scrapers.pipeline.quality import evaluate
from scrapers.pipeline.schema import VehicleRecord

log = logging.getLogger(__name__)

MAX_INVENTORY = 2000   # bound a single catalog capture


def _find_vehicle_arrays(obj, depth: int = 0, out: list | None = None) -> list:
    """Collect JSON lists whose elements look like vehicles (DFS, bounded)."""
    if out is None:
        out = []
    if depth > 6:
        return out
    if isinstance(obj, list):
        dicts = [e for e in obj if isinstance(e, dict)]
        if dicts and sum(1 for e in dicts if _vehicle_score(e) >= 2) >= max(1, len(dicts) // 2):
            out.append(obj)
        else:
            for e in obj[:200]:
                _find_vehicle_arrays(e, depth + 1, out)
    elif isinstance(obj, dict):
        for v in obj.values():
            _find_vehicle_arrays(v, depth + 1, out)
    return out


def extract_vehicles_from_captured(captured: list) -> list[dict]:
    """
    From captured JSON payloads, return the largest list of normalized vehicle raw dicts.

    Picks the richest vehicle array seen across all payloads (the inventory feed), then
    normalizes each entry; keeps only entries with at least make+model+price.
    """
    best: list[dict] = []
    for payload in captured:
        for arr in _find_vehicle_arrays(payload):
            raws = []
            for el in arr[:MAX_INVENTORY]:
                r = vehicle_json_to_raw(el)
                if r.get("make") and r.get("model") and r.get("price"):
                    raws.append(r)
            if len(raws) > len(best):
                best = raws
    return best


def records_from_raws(raws: list[dict], *, source_domain: str, country: str,
                      base_url: str = "") -> list[VehicleRecord]:
    """
    Turn normalized raw dicts into quality-gated VehicleRecords.

    The DMS feed rarely carries a per-vehicle detail URL in a stable place, so a
    synthetic same-site source_url is derived from the vehicle's id/vin/slug when the raw
    dict lacks one — enough to satisfy the deep-link gate and dedup; the canonical URL is
    refined later if a detail link is found.
    """
    records: list[VehicleRecord] = []
    origin = base_url or f"https://{source_domain}"
    for i, raw in enumerate(raws):
        url = raw.get("source_url") or ""
        if not url:
            ident = raw.get("vin") or "-".join(
                str(raw.get(k, "")) for k in ("make", "model", "year", "mileage")).strip("-")
            url = f"{origin.rstrip('/')}/vehicle/{ident or i}".lower().replace(" ", "-")
        record = to_record(raw, source_url=url, source_domain=source_domain, country=country)
        # DMS feeds carry the full car (make/model/year/price/mileage) but often serve
        # photos from a separate endpoint/relative path, so a missing image must NOT drop
        # otherwise-complete inventory (A7 persists without an image). Require the core
        # commercial fields, then the same coherence/poison gate as every other vector.
        if not (record.make and record.model and record.year is not None and record.price is not None):
            continue
        verdict = evaluate(record, html="")
        if verdict.ok:
            records.append(record)
    return records


# Common inventory/stock paths across DE/FR/ES/NL/CH platforms — tried when the
# detected catalog URL is wrong (the VW Group platform lives at /gebrauchtwagen, etc.).
COMMON_INVENTORY_PATHS: tuple[str, ...] = (
    "/gebrauchtwagen", "/gebrauchtwagen.html", "/fahrzeuge", "/fahrzeugsuche",
    "/occasion", "/occasions", "/stock", "/voorraad", "/aanbod", "/used-cars",
    "/coches-ocasion", "/de/gebrauchtwagen.html", "/neufahrzeuge",
)


async def harvest_inventory_xhr(catalog_url: str, xhr_fetcher, *, country: str,
                                source_domain: str) -> list[VehicleRecord]:
    """
    Render a dealer's catalog, capture the inventory feed XHR, return its vehicles.

    ``xhr_fetcher`` is a ``PlaywrightXHRFetcher`` (its ``capture_json`` is used). Provider-
    agnostic: whatever JSON array the embedded widget fetched becomes records.
    """
    try:
        captured = await xhr_fetcher.capture_json(catalog_url)
    except Exception as exc:  # noqa: BLE001 — render/transport fault → no inventory
        log.debug("dms capture failed %s: %s", catalog_url, type(exc).__name__)
        return []
    raws = extract_vehicles_from_captured(captured)
    return records_from_raws(raws, source_domain=source_domain, country=country, base_url=catalog_url)


async def harvest_inventory_multi(domain: str, xhr_fetcher, *, country: str,
                                  catalog_url: str = "", max_tries: int = 3,
                                  good_enough: int = 3) -> list[VehicleRecord]:
    """
    Try the detected catalog URL plus common inventory paths; return the best capture.

    The catalog-URL detector often lands on a nav page; a dealer whose stock is a widget
    needs the actual inventory route (``/gebrauchtwagen`` for VW Group, etc.). Bounded by
    ``max_tries`` renders (RAM/time); stops early once ``good_enough`` vehicles are found.
    """
    tries: list[str] = []
    if catalog_url:
        tries.append(catalog_url)
    for p in COMMON_INVENTORY_PATHS:
        u = f"https://{domain}{p}"
        if u not in tries:
            tries.append(u)
    best: list[VehicleRecord] = []
    for url in tries[:max_tries]:
        recs = await harvest_inventory_xhr(url, xhr_fetcher, country=country, source_domain=domain)
        if len(recs) > len(best):
            best = recs
        if len(best) >= good_enough:
            break
    return best
