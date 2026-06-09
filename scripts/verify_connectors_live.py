"""
Live connector rot-check — the anti-lie gate for giants + discovery anchors.

Scraper endpoints and embedded-JSON shapes ROT (wallapop went CloudFront-WAF;
comparis flipped to DataDome; ES OpenMercantil went dark). A connector that
parsed yesterday can silently return zero rows today, and "CARDEX no vende
mentiras" — so before trusting any volume claim we re-verify, live, that:

  * the giant ``__NEXT_DATA__`` connectors still fetch (HTTP 200), still expose a
    declared total (the count_verify anchor), and still parse > 0 rows whose core
    fields (make/price) are populated — i.e. the JSON shape has not moved; and
  * each OEM dealer-locator endpoint still answers and still yields dealers.

Read-only: pure HTTP GET + parse + report. No DB, no persistence, nothing to
purge (slice-then-purge degenerates to slice-only). Bounded: one listing page
per giant, one representative country per OEM brand — enough to detect rot,
polite to the endpoints.

    python -m scripts.verify_connectors_live                 # everything
    python -m scripts.verify_connectors_live --giants        # giants only
    python -m scripts.verify_connectors_live --oem           # OEM only
    python -m scripts.verify_connectors_live --json proof.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any, Awaitable, Callable

import httpx

from scrapers.dealer_scraping.harvester import make_dealer_fetcher
from scrapers.pipeline.generic_extractor import _safe_fetch
from scrapers.portals import as24_listings as a24
from scrapers.portals import leboncoin_listings as lbc
from scrapers.portals import marktplaats_listings as mpl

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


# ── giants (curl_cffi __NEXT_DATA__ connectors) ────────────────────────────────
# Each: a listing URL, the connector module, and the base/currency for parsing.
# The module triplet (extract_next_data, number_of_results, parse_listings) is the
# uniform contract; as24's extract_next_data is shared by all three.
_GIANTS: list[dict[str, Any]] = [
    {"name": "autoscout24.fr", "country": "FR", "currency": "EUR",
     "url": "https://www.autoscout24.fr/lst?page=1",
     "base": "https://www.autoscout24.fr", "mod": a24},
    {"name": "leboncoin.fr", "country": "FR", "currency": "EUR",
     "url": "https://www.leboncoin.fr/recherche?category=2",
     "base": "https://www.leboncoin.fr", "mod": lbc},
    {"name": "marktplaats.nl", "country": "NL", "currency": "EUR",
     "url": "https://www.marktplaats.nl/l/auto-s/",
     "base": "https://www.marktplaats.nl", "mod": mpl},
]


def _sample_row(rows: list[dict]) -> dict | None:
    """First row that carries both a make and a price — proof the shape still maps."""
    for r in rows:
        if r.get("make") and r.get("price_raw"):
            return {k: r.get(k) for k in ("make", "model", "year", "mileage_km",
                                          "price_raw", "currency_raw", "source_url")}
    return rows[0] if rows else None


async def verify_giants(fetcher) -> list[dict]:
    results: list[dict] = []
    for g in _GIANTS:
        rec: dict[str, Any] = {"target": g["name"], "kind": "giant"}
        r = await _safe_fetch(fetcher, g["url"])
        if r is None:
            rec.update(status=None, ok=False, error="transport fault (no response)")
            results.append(rec)
            continue
        nd = g["mod"].extract_next_data(r.text or "")
        total = g["mod"].number_of_results(nd)
        rows = g["mod"].parse_listings(nd, base_url=g["base"], currency=g["currency"])
        sample = _sample_row(rows)
        rec.update(
            status=r.status_code,
            declared_total=total,
            parsed_rows=len(rows),
            sample=sample,
            ok=bool(r.status_code == 200 and total and rows and sample
                    and sample.get("make") and sample.get("price_raw")),
        )
        if not rec["ok"]:
            rec["error"] = _giant_diag(r.status_code, nd, total, rows, sample)
        results.append(rec)
        await asyncio.sleep(1.0)  # polite spacing between distinct giants
    return results


def _giant_diag(status: int, nd: dict, total, rows: list, sample) -> str:
    if status != 200:
        return f"HTTP {status} (blocked/challenged — rot or anti-bot)"
    if not nd:
        return "no __NEXT_DATA__ in body (SSR shape moved or challenge page)"
    if total is None:
        return "declared total missing (count anchor path moved)"
    if not rows:
        return "0 rows parsed (listings path moved)"
    return "rows parsed but core fields empty (field mapping moved)"


# ── OEM dealer-locator endpoints ───────────────────────────────────────────────
# Re-verify each brand against one representative country (DE — every brand serves
# it). Reuses the module's own fetch_* so we test the EXACT production path.
async def verify_oem() -> list[dict]:
    from scrapers.discovery.sources import oem_locators as oem

    brand_country = [("vw", "DE"), ("audi", "DE"), ("skoda", "DE"),
                     ("toyota", "DE"), ("hyundai", "DE"), ("kia", "DE")]
    results: list[dict] = []
    async with httpx.AsyncClient(timeout=45.0, follow_redirects=True,
                                 headers={"User-Agent": _BROWSER_UA}) as client:
        for brand, country in brand_country:
            entry = oem.BRANDS.get(brand)
            rec: dict[str, Any] = {"target": f"oem:{brand}", "country": country, "kind": "oem"}
            if not entry:
                rec.update(ok=False, error="brand not in BRANDS registry")
                results.append(rec)
                continue
            fetch, _ = entry
            try:
                cands = await fetch(client, country)
            except Exception as exc:  # noqa: BLE001 — report, never abort the sweep
                rec.update(ok=False, error=f"{type(exc).__name__}: {str(exc)[:160]}")
                results.append(rec)
                continue
            sample = None
            for c in cands:
                if c.get("name"):
                    sample = {k: c.get(k) for k in ("name", "city", "postcode", "domain")}
                    break
            rec.update(dealers=len(cands), sample=sample, ok=bool(cands))
            if not cands:
                rec["error"] = "0 dealers (endpoint moved / WAF / empty response)"
            results.append(rec)
            await asyncio.sleep(0.5)
    return results


# ── portal directory anchor (AS24-DE is the only reachable one historically) ────
async def verify_portal_anchor(fetcher) -> dict:
    rec: dict[str, Any] = {"target": "portal:autoscout24/DE haendler-dir", "kind": "portal"}
    r = await _safe_fetch(fetcher, "https://www.autoscout24.de/haendler/")
    if r is None:
        rec.update(status=None, ok=False, error="transport fault")
        return rec
    import re
    hrefs = re.findall(r'href="(/haendler/[^"?#]+)"', r.text or "")
    rec.update(status=r.status_code, profile_hrefs=len(set(hrefs)),
               ok=bool(r.status_code == 200 and hrefs))
    if not rec["ok"]:
        rec["error"] = (f"HTTP {r.status_code}" if r.status_code != 200
                        else "0 dealer-profile hrefs (directory markup moved)")
    return rec


# ── report ─────────────────────────────────────────────────────────────────────
def _print_report(giants: list[dict], oem: list[dict], portal: dict | None) -> bool:
    all_recs = giants + oem + ([portal] if portal else [])
    print("\n=== LIVE CONNECTOR ROT-CHECK ===")
    if giants:
        print("\n[GIANTS] __NEXT_DATA__ connectors (status / declared_total / parsed_rows)")
        for r in giants:
            flag = "PASS" if r.get("ok") else "FAIL"
            print(f"  {flag}  {r['target']:<18} status={r.get('status')} "
                  f"total={r.get('declared_total')} rows={r.get('parsed_rows')}")
            if r.get("sample"):
                s = r["sample"]
                print(f"        e.g. {s.get('make')} {s.get('model')} "
                      f"{s.get('year')} {s.get('price_raw')}{s.get('currency_raw') or ''}")
            if r.get("error"):
                print(f"        -> {r['error']}")
    if oem:
        print("\n[OEM] dealer-locator endpoints (dealers found, country=DE)")
        for r in oem:
            flag = "PASS" if r.get("ok") else "FAIL"
            print(f"  {flag}  {r['target']:<14} dealers={r.get('dealers')}")
            if r.get("sample"):
                s = r["sample"]
                print(f"        e.g. {s.get('name')} ({s.get('city')}) dom={s.get('domain')}")
            if r.get("error"):
                print(f"        -> {r['error']}")
    if portal:
        flag = "PASS" if portal.get("ok") else "FAIL"
        print(f"\n[PORTAL] {flag}  {portal['target']} status={portal.get('status')} "
              f"hrefs={portal.get('profile_hrefs')}")
        if portal.get("error"):
            print(f"        -> {portal['error']}")
    passed = sum(1 for r in all_recs if r.get("ok"))
    print(f"\n=== {passed}/{len(all_recs)} connectors live ===\n")
    return passed == len(all_recs)


async def _main() -> None:
    ap = argparse.ArgumentParser(description="Live connector rot-check (anti-lie gate)")
    ap.add_argument("--giants", action="store_true", help="giants only")
    ap.add_argument("--oem", action="store_true", help="OEM locators only")
    ap.add_argument("--portal", action="store_true", help="portal directory anchor only")
    ap.add_argument("--json", default=None, help="write full results JSON to this path")
    args = ap.parse_args()
    run_all = not (args.giants or args.oem or args.portal)

    giants: list[dict] = []
    oem: list[dict] = []
    portal: dict | None = None

    fetcher = make_dealer_fetcher()
    try:
        if run_all or args.giants:
            giants = await verify_giants(fetcher)
        if run_all or args.portal:
            portal = await verify_portal_anchor(fetcher)
    finally:
        aclose = getattr(fetcher, "aclose", None)
        if aclose:
            await aclose()

    if run_all or args.oem:
        oem = await verify_oem()

    all_ok = _print_report(giants, oem, portal)

    if args.json:
        payload = {"giants": giants, "oem": oem, "portal": portal, "all_ok": all_ok}
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        print(f"results written -> {args.json}")


if __name__ == "__main__":
    asyncio.run(_main())
