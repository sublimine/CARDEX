"""T2 dealer inventory harvester — cage discovered dealer inventory as LIVE API pointers.

For dealers the P2 probe flagged ``inventory_tier='T2'`` (real inventory, no deep defense),
this enumerates their vehicle DETAIL URLs (sitemap-first via the existing
``discover_detail_urls``), enriches a bounded sample with JSON-LD (``parse_listing``), and
writes them to ``vehicle_index`` as rich pointers under a ``kind='dealer'`` source_entity —
so each dealer shows up LIVE in ``/v1/entities/{ulid}/inventory`` with real price/year.

HTTP-only (curl_cffi, no browser), RAM-light (per-domain session reused then dropped). The
fetch path is SSRF-guarded: ``discover_detail_urls`` runs same-site through ``net_guard``,
and we re-check the dealer host before touching it.

Validate-and-purge: the fetched HTML is parsed then dropped (the fetcher/session is closed
and GC'd per dealer); the lightweight pointers stay in ``vehicle_index``.
"""
from __future__ import annotations

import gc
import hashlib
import logging
import re
import time

from scrapers.common.indexer import _ENRICH_STREAM, _hash_urls, country_currency
from scrapers.dealer_scraping.discovery import discover_detail_urls
from scrapers.dealer_scraping.harvester import make_dealer_fetcher
from scrapers.pipeline.parse import parse_listing
from scrapers.portals import config as portal_config
from scrapers.portals.config import DriftBaseline, Endpoints, ExtractionConfig

log = logging.getLogger(__name__)

DISCOVERY_CAP = 200          # detail URLs caged per dealer (the inventory pointers)
ENRICH_SAMPLE = 20           # detail pages fetched + JSON-LD-parsed for rich fields


def _digits(v) -> int | None:
    if v is None:
        return None
    m = re.search(r"\d[\d.\s']*", str(v))
    if not m:
        return None
    try:
        return int(re.sub(r"[.\s']", "", m.group(0)))
    except ValueError:
        return None


def _year(v) -> int | None:
    n = _digits(v)
    return n if n and 1950 <= n <= 2027 else None


def _price(v) -> int | None:
    n = _digits(v)
    return n if n and 100 <= n <= 5_000_000 else None


def _entity_ulid(domain: str) -> str:
    return "se_" + hashlib.md5(domain.encode("utf-8")).hexdigest()


async def _ensure_dealer_entity(conn, domain: str, country: str, config_ref: str | None) -> None:
    await conn.execute(
        "INSERT INTO source_entities(entity_ulid,source_key,kind,domain,country,defense_tier,waf,config_ref) "
        "VALUES($1,$2,'dealer',$2,$3,'T2','none',$4) "
        "ON CONFLICT(source_key) DO UPDATE SET kind='dealer', "
        "  defense_tier=COALESCE(source_entities.defense_tier,'T2'), "
        "  config_ref=COALESCE(EXCLUDED.config_ref,source_entities.config_ref), updated_at=now()",
        _entity_ulid(domain), domain, (country or "")[:2], config_ref,
    )


async def cage_inventory(pg, rdb, domain: str, country: str, listings: list[dict], *,
                         config_ref: str | None = None) -> dict:
    """Write rich pointers to vehicle_index under a kind='dealer' entity. Idempotent.

    listings = [{"url", "title"?, "price"?, "year"?, "km"?}]. Returns {discovered, new}.
    """
    urls = [li["url"] for li in listings]
    hash_to_url = _hash_urls(urls)              # drops root URLs, dedups by hash
    if not hash_to_url:
        return {"discovered": 0, "new": 0}
    rich = {li["url"]: li for li in listings}
    moneda = country_currency(country)
    ent = _entity_ulid(domain)
    cc = (country or "")[:2]

    hashes, us, titles, prices, years, kms = [], [], [], [], [], []
    for h, u in hash_to_url.items():
        r = rich.get(u, {})
        hashes.append(h); us.append(u)
        titles.append(r.get("title")); prices.append(r.get("price"))
        years.append(r.get("year")); kms.append(r.get("km"))

    async with pg.acquire() as conn:
        await _ensure_dealer_entity(conn, domain, cc, config_ref)
        rows = await conn.fetch(
            "INSERT INTO vehicle_index "
            "(url_hash,url_original,source_domain,country,moneda,titulo_modelo,precio,anio,kilometraje,last_seen,entity_ulid) "
            "SELECT h,u,$3,$4,$5,NULLIF(t,''),p,y,k,NOW(),$6 "
            "FROM unnest($1::text[],$2::text[],$7::text[],$8::numeric[],$9::int[],$10::int[]) AS x(h,u,t,p,y,k) "
            "ON CONFLICT (url_hash) DO NOTHING RETURNING url_hash",
            hashes, us, domain, cc, moneda, ent, titles, prices, years, kms,
        )
        new_hashes = [r["url_hash"] for r in rows]
        if new_hashes:
            new_urls = [hash_to_url[h] for h in new_hashes]
            await conn.execute(
                "INSERT INTO vehicle_events (url_hash,url_original,source_domain,country,event_type) "
                "SELECT h,u,$3,$4,'SEEN' FROM unnest($1::text[],$2::text[]) AS t(h,u)",
                new_hashes, new_urls, domain, cc,
            )
    if new_hashes:
        pipe = rdb.pipeline(transaction=False)
        for h in new_hashes:
            pipe.xadd(_ENRICH_STREAM, {"h": h, "u": hash_to_url[h], "s": domain, "c": cc}, maxlen=5_000_000)
        await pipe.execute()
    return {"discovered": len(hash_to_url), "new": len(new_hashes)}


def _strategy_for(method: str) -> str:
    if method == "sitemap":
        return "sitemap_listing"
    if method in ("wp_rest",):
        return "wp_rest"
    return "jsonld_detail"   # catalog / catalog_follow / homepage links → JSON-LD on detail


async def harvest_t2_dealer(pg, rdb, domain: str, country: str, *,
                            sample_limit: int = ENRICH_SAMPLE, cap: int = DISCOVERY_CAP) -> dict:
    """Detect→discover→enrich-sample→cage→save-config for one T2 dealer. Never raises."""
    fetcher = make_dealer_fetcher()
    t0 = time.monotonic()
    try:
        details, method, _home, _catalog = await discover_detail_urls(
            domain, static_fetcher=fetcher, e07_fetcher=None, cap=cap)
        if not details:
            return {"domain": domain, "country": country, "method": method or "none",
                    "discovered": 0, "new": 0, "enriched": 0, "yields": False,
                    "ms": round((time.monotonic() - t0) * 1000)}

        listings = [{"url": u} for u in details]
        by_url = {li["url"]: li for li in listings}
        enriched = 0
        for u in details[:sample_limit]:
            try:
                fr = await fetcher(u)
                if fr.status_code == 200 and fr.body:
                    rec = parse_listing(fr.body.decode("utf-8", "ignore"))
                    title = (f"{rec.get('make') or ''} {rec.get('model') or ''}").strip() or None
                    li = by_url[u]
                    li["title"], li["price"] = title, _price(rec.get("price"))
                    li["year"], li["km"] = _year(rec.get("year")), _digits(rec.get("mileage"))
                    if li["price"] or li["year"]:
                        enriched += 1
            except Exception:  # noqa: BLE001 — one bad page never aborts the dealer
                pass

        cfg = ExtractionConfig(
            source_key=domain, country=(country or "")[:2], strategy=_strategy_for(method),
            version=1, endpoints=Endpoints(host="www." + domain),
            drift_baseline=DriftBaseline(expected_min_volume=max(1, len(details))))
        portal_config.save(cfg, kind="dealer")
        config_ref = f"configs/dealers/{domain}.json"

        caged = await cage_inventory(pg, rdb, domain, country, listings, config_ref=config_ref)
        return {"domain": domain, "country": country, "method": method,
                "discovered": caged["discovered"], "new": caged["new"], "enriched": enriched,
                "yields": caged["discovered"] > 0, "ms": round((time.monotonic() - t0) * 1000)}
    except Exception as exc:  # noqa: BLE001
        log.exception("harvest_t2_dealer failed domain=%s", domain)
        return {"domain": domain, "country": country, "error": f"{type(exc).__name__}: {exc}",
                "discovered": 0, "new": 0, "enriched": 0, "yields": False}
    finally:
        aclose = getattr(fetcher, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except Exception:  # noqa: BLE001
                pass
        gc.collect()   # validate-and-purge: drop HTML/session, keep only the pointers
