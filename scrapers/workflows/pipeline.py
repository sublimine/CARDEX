"""W1→W5 pipeline for ONE dealer — returns a structured ``DealerResult``.

Reuses the production atoms (harvester, cdx_code, entity_api view). Each gate is
decided by an INDEPENDENT method recorded on the verdict. The General calls
``run_dealer`` per dealer over a shared pool; a NO PASA isolates the dealer
(``blocked_reason``) and never aborts the line.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from scrapers.intelligence.cdx_code import cdx_code
from scrapers.portals import config as portal_config
from scrapers.workflows.model import DealerResult, GateVerdict

REPO = Path(__file__).resolve().parent.parent.parent
_DRIFT_TOL = 0.01
_DRIFT_FLOOR = 2


async def _independent_sitemap_count(domain: str, detail_url_re: str, sitemap_url: str) -> int:
    """V3 path A — count visible PDPs by walking the sitemap FRESH (independent fetch
    from the harvester). Recipe regex defines "a PDP"; transport/enumeration is ours."""
    from curl_cffi.requests import AsyncSession
    cs = AsyncSession(impersonate="chrome131", verify=False)
    try:
        rx = re.compile(detail_url_re) if detail_url_re else None
        seen: set[str] = set()
        queue = [sitemap_url or f"https://www.{domain}/sitemap.xml"]
        walked = 0
        while queue and walked < 50:
            u = queue.pop(0)
            walked += 1
            try:
                r = await cs.get(u, timeout=15, allow_redirects=True)
            except Exception:  # noqa: BLE001
                continue
            if r.status_code != 200:
                continue
            body = (r.content or b"").decode("utf-8", "ignore")
            locs = re.findall(r"<loc>\s*([^<\s]+)", body)
            if "<sitemapindex" in body.lower():
                queue.extend(locs)
                continue
            for loc in locs:
                if rx is None or rx.search(loc):
                    seen.add(loc)
        return len(seen)
    finally:
        await cs.close()


async def run_dealer(pg, rdb, domain: str, country: str, *,
                     cap: int = 5000, persist: bool = False) -> DealerResult:
    """Run one dealer through W1-W5. Never raises for an ordinary failure — a bad
    dealer becomes a ``blocked_reason`` so the General's batch never aborts."""
    from scrapers.dealer_scraping.inventory_harvester import harvest_t2_dealer
    cc = country.upper()[:2]
    code = cdx_code(cc, domain=domain)
    t0 = time.monotonic()
    gates: list[GateVerdict] = []
    try:
        row = await pg.fetchrow(
            "SELECT city, province, name, url FROM discovery_candidates "
            "WHERE domain=$1 AND country=$2", domain, cc)
        if row is None:
            return DealerResult(domain, cc, code, blocked_reason="not_in_discovery")

        # W1 DESCUBRIR
        city, province = row["city"] or "", row["province"] or ""
        geo_ok = bool(city and province)
        gates.append(GateVerdict("W1", bool(domain and code and geo_ok),
                                 f"cdx={code} geo={cc}/{province}/{city}",
                                 "cdx_code+discovery_candidates"))

        # W2 RECETA
        cfg = portal_config.load(domain)
        recipe_ok = cfg is not None and bool(cfg.endpoints.detail_url_re or cfg.endpoints.sitemap_url)
        gates.append(GateVerdict("W2", recipe_ok,
                                 f"strategy={cfg.strategy if cfg else None} "
                                 f"v{cfg.version if cfg else '-'}",
                                 "portal_config.load"))

        # W3 SCRAPEAR + V3 — DOS vías ortogonales que deben CONCORDAR.
        #   path A = sitemap (enumera TODO, incluidos vendidos cuyo PDP sigue dando 200)
        #   path B = listado paginado (lo que el portal muestra como DISPONIBLE)
        # Lección dificar.com 2026-06-10: el sitemap dio 235, el listado 123 — los 112
        # de más eran coches VENDIDOS/RESERVADOS con la página aún viva. La verdad del
        # stock disponible es el LISTADO, no el sitemap (ver workflows/README §D5). El
        # gate sólo PASA si las dos vías concuerdan; si divergen, el dealer NO PASA y se
        # marca para filtrado-de-disponibilidad (no se vende inventario vendido como vivo).
        from scrapers.workflows.inquisition import count_by_listing_pagination
        hr = await harvest_t2_dealer(pg, rdb, domain, cc, cap=cap)
        extracted = hr.get("discovered", 0)
        detail_re = cfg.endpoints.detail_url_re if cfg else ""
        sitemap = cfg.endpoints.sitemap_url if cfg else ""
        listing = cfg.endpoints.listing_url_template if cfg else ""
        count_sitemap = await _independent_sitemap_count(domain, detail_re, sitemap)
        count_listing = await count_by_listing_pagination(domain, listing, detail_re)
        # the AVAILABLE truth: the listing when we have it, else fall back to sitemap
        independent = count_listing if count_listing >= 0 else count_sitemap
        tol = max(_DRIFT_FLOOR, int(max(independent, 1) * _DRIFT_TOL))
        agree = count_listing < 0 or abs(count_sitemap - count_listing) <= tol
        v3_ok = independent > 0 and abs(extracted - independent) <= tol and agree
        detail = f"sitemap={count_sitemap} listado={count_listing} servido_extraído={extracted}"
        if count_listing >= 0 and not agree:
            detail += " ⚠ DIVERGEN (sitemap incluye vendidos→filtrar disponibilidad)"
        gates.append(GateVerdict("W3", v3_ok, detail,
                                 "sitemap_walk ∧ listing_pagination (deben concordar)"))

        # W4 API + DELTA
        ulid = await pg.fetchval("SELECT entity_ulid FROM source_entities WHERE source_key=$1", domain)
        served = await pg.fetchval(
            "SELECT count(*) FROM entity_inventory WHERE entity_ulid=$1", ulid) if ulid else 0
        gone = await pg.fetchval(
            "SELECT count(*) FROM vehicle_events WHERE source_domain=$1 AND event_type='GONE'",
            domain) or 0
        false_baja = served > 0 and gone > served
        gates.append(GateVerdict("W4", bool(ulid) and served > 0 and not false_baja,
                                 f"servido_API={served} GONE={gone}",
                                 "entity_inventory view + vehicle_events"))

        # W5 GUARDAR (checksum del dato estructurado para reconstrucción en frío)
        inv = await pg.fetch(
            "SELECT source_url, year, price, mileage_km, title FROM entity_inventory "
            "WHERE entity_ulid=$1 ORDER BY source_url", ulid) if ulid else []
        checksum = hashlib.sha256(
            json.dumps([dict(r) for r in inv], sort_keys=True, default=str).encode()).hexdigest()
        if persist and ulid:
            _persist_dealer_record(cc, province, city, code, domain, row, cfg, gates, served,
                                   independent, checksum)
        gates.append(GateVerdict("W5", bool(ulid),
                                 f"checksum={checksum[:12]} {'persist' if persist else 'dry'}",
                                 "structured_checksum"))

        return DealerResult(domain, cc, code, tuple(gates), served, independent,
                            elapsed_ms=int((time.monotonic() - t0) * 1000))
    except Exception as exc:  # noqa: BLE001 — isolate, never block the line
        return DealerResult(domain, cc, code, tuple(gates),
                            blocked_reason=f"{type(exc).__name__}: {exc}",
                            elapsed_ms=int((time.monotonic() - t0) * 1000))


def _persist_dealer_record(cc, province, city, code, domain, row, cfg, gates, served,
                           independent, checksum) -> None:
    prov_slug = re.sub(r"[^a-z0-9]+", "-", province.lower()).strip("-") or "sin-provincia"
    city_slug = re.sub(r"[^a-z0-9]+", "-", city.lower()).strip("-") or "sin-ciudad"
    ddir = REPO / "dealers" / cc / prov_slug / city_slug / code
    ddir.mkdir(parents=True, exist_ok=True)
    (ddir / "ficha.json").write_text(json.dumps({
        "cdx_code": code, "domain": domain, "country": cc, "province": province,
        "city": city, "name": row["name"],
        "stock_url": cfg.endpoints.sitemap_url if cfg else row["url"],
        "config_ref": f"configs/dealers/{domain}.json",
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (ddir / "estado.json").write_text(json.dumps({
        "gates": {g.gate: ("PASA" if g.pasa else "NO_PASA") for g in gates},
        "served": served, "visible_independiente": independent,
        "structured_checksum_sha256": checksum, "verified_date": "2026-06-10",
    }, indent=2, ensure_ascii=False), encoding="utf-8")
