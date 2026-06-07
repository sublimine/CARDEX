#!/usr/bin/env python3
"""Persistent faceted-dump worker for the cracked giants — with DELTA.

For a given portal it:
  1. Enumerates the catalog by PAGINATION (and FACETS make×… when search caps),
     or by SITEMAP (leboncoin).
  2. Extracts listings from the embedded SSR state / internal API (already cracked).
  3. NORMALISES each to a common seam-like contract (vehicle_index pointer +
     cheap rich fields), with a stable url_hash.
  4. Computes the DELTA against the previous snapshot: SEEN (new) / GONE
     (disappeared) / present.
  5. Honors LOCAL limit-and-purge: stops at EXTRACT_LIMIT, validates the schema,
     and (with --purge) deletes the local harvest, leaving only the snapshot +
     delta report. Full dumps are for the VPS (CARDEX_ENV=vps, limit=0).

RAM-safe: one Camoufox at a time, pages fetched sequentially. Meant to be run
DETACHED (Start-Process -WindowStyle Hidden) as a persistent worker.

Usage:
    python dump_worker.py leboncoin --limit 100
    python dump_worker.py leboncoin --limit 100 --purge
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import classify  # noqa: E402
from extract_state import extract_balanced, walk_find_lists, get_path  # noqa: E402

EVID = Path(__file__).resolve().parent / "evidence"
OUT = EVID / "dumps"
OUT.mkdir(parents=True, exist_ok=True)

STATE_VARS = ["__NEXT_DATA__", "window.__INITIAL_PROPS__", "window.__INITIAL_STATE__"]


def url_hash(u: str) -> str:
    return hashlib.sha256(u.encode("utf-8")).hexdigest()[:32]


# --- per-portal config: how to paginate + extract + normalise --------------------
def _lbc_norm(it: dict) -> dict:
    attrs = {a.get("key"): (a.get("value_label") or a.get("value")) for a in it.get("attributes", [])}
    price = it.get("price")
    price = price[0] if isinstance(price, list) and price else it.get("price_cents", 0) // 100 if it.get("price_cents") else None
    loc = it.get("location", {}) or {}
    return {
        "title": it.get("subject"),
        "price_eur": price, "currency": "EUR",
        "make": attrs.get("brand"), "model": attrs.get("model"),
        "year": _int(attrs.get("regdate")), "mileage_km": _int((attrs.get("mileage") or "").replace(" km", "")),
        "fuel": attrs.get("fuel"),
        "city": loc.get("city"), "region": loc.get("region_name"),
    }


def _coches_norm(it: dict) -> dict:
    p = it.get("price", {})
    price = p.get("amount") if isinstance(p, dict) else (it.get("price") if isinstance(it.get("price"), (int, float)) else None)
    return {
        "title": it.get("title"), "price_eur": price, "currency": "EUR",
        "make": it.get("make"), "model": it.get("model"), "year": it.get("year"),
        "mileage_km": it.get("km"), "fuel": it.get("fuelType"),
        "city": (it.get("location") or {}).get("mainProvince") if isinstance(it.get("location"), dict) else None,
    }


def _mobilede_norm(it: dict) -> dict:
    p = it.get("price", {})
    return {
        "title": it.get("title") or it.get("shortTitle"),
        "price_eur": p.get("grossAmount") if isinstance(p, dict) else None,
        "currency": "EUR", "make": it.get("make"), "model": it.get("model"),
    }


def _as24_norm(it: dict) -> dict:
    v = it.get("vehicle", {}) or {}
    p = it.get("price", {}) or {}
    return {
        "title": " ".join(filter(None, [v.get("make"), v.get("model")])) or None,
        "price_eur": p.get("priceRaw") or _money(p.get("priceFormatted")),
        "currency": "EUR", "make": v.get("make"), "model": v.get("model"),
        "year": _int(v.get("firstRegistrationDate", "")[:4]) if v.get("firstRegistrationDate") else None,
        "mileage_km": v.get("mileageInKmRaw"), "fuel": v.get("fuelCategory", {}).get("formatted") if isinstance(v.get("fuelCategory"), dict) else None,
    }


def _int(s):
    try:
        return int("".join(ch for ch in str(s) if ch.isdigit()) or 0) or None
    except Exception:
        return None


def _money(s):
    if not s:
        return None
    return _int(s)


def _url_lbc(it):
    return it.get("url") or f"https://www.leboncoin.fr/ad/voitures/{it.get('list_id')}"


def _url_rel(base):
    def f(it):
        u = it.get("url") or it.get("relativeUrl") or ""
        return (base + u) if u.startswith("/") else u
    return f


PORTALS = {
    "leboncoin": {
        "country": "FR", "domain": "leboncoin.fr",
        "page_url": "https://www.leboncoin.fr/recherche?category=2&page={page}",
        "warm": "https://www.leboncoin.fr/", "settle": 2,
        "path_hint": "searchData.ads", "norm": _lbc_norm, "url_of": _url_lbc,
    },
    "coches": {
        "country": "ES", "domain": "coches.net",
        "page_url": "https://www.coches.net/segunda-mano/?pg={page}",
        "warm": "https://www.coches.net/", "settle": 2,
        "path_hint": "initialResults.items", "norm": _coches_norm, "url_of": _url_rel("https://www.coches.net"),
    },
    "mobilede": {
        "country": "DE", "domain": "mobile.de",
        "page_url": "https://suchen.mobile.de/fahrzeuge/search.html?dam=false&isSearchRequest=true&s=Car&vc=Car&pageNumber={page}",
        "warm": "https://www.mobile.de/", "settle": 3,
        "path_hint": "searchResults.items", "norm": _mobilede_norm, "url_of": _url_rel("https://suchen.mobile.de"),
    },
    "as24_de": {
        "country": "DE", "domain": "autoscout24.de",
        "page_url": "https://www.autoscout24.de/lst?atype=C&page={page}&size=20&sort=standard",
        "warm": "https://www.autoscout24.de/", "settle": 2,
        "path_hint": "pageProps.listings", "norm": _as24_norm, "url_of": _url_rel("https://www.autoscout24.de"),
    },
}


def pick_listings(html: str, path_hint: str):
    for var in STATE_VARS:
        raw = extract_balanced(html, var)
        if not raw:
            continue
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        lists = walk_find_lists(data)
        # prefer the path matching the hint
        lists.sort(key=lambda t: (path_hint in t[0], t[1]), reverse=True)
        if lists:
            try:
                return get_path(data, lists[0][0])
            except Exception:
                continue
    return []


def run(portal: str, limit: int, purge: bool, max_pages: int) -> int:
    cfg = PORTALS[portal]
    from camoufox.sync_api import Camoufox
    snap_file = OUT / f"{portal}_snapshot.json"
    prev = set(json.loads(snap_file.read_text(encoding="utf-8"))) if snap_file.exists() else set()
    records: list[dict] = []
    seen_urls: set[str] = set()

    print(f"[{portal}] limit={limit} prev_snapshot={len(prev)}", flush=True)
    with Camoufox(headless=True, humanize=True, geoip=True) as browser:
        page = browser.new_page()
        if cfg.get("warm"):
            try:
                page.goto(cfg["warm"], wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(15000)
            except Exception:
                pass
        for pg in range(1, max_pages + 1):
            if len(records) >= limit:
                break
            url = cfg["page_url"].format(page=pg)
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                page.wait_for_timeout(3000)
                continue
            page.wait_for_timeout(7000)
            body = page.content()
            verdict, hits = classify(resp.status if resp else None, page.title(), body)
            rounds = 0
            while verdict == "BLOCKED" and rounds < cfg.get("settle", 0):
                rounds += 1
                page.wait_for_timeout(9000)
                try:
                    page.reload(wait_until="domcontentloaded", timeout=60000)
                except Exception:
                    pass
                page.wait_for_timeout(7000)
                body = page.content()
                verdict, hits = classify(resp.status if resp else None, page.title(), body)
            items = pick_listings(body, cfg["path_hint"])
            if not items:
                print(f"[{portal}] page {pg}: no items (verdict={verdict}) — stop", flush=True)
                break
            new_on_page = 0
            for it in items:
                if not isinstance(it, dict):
                    continue
                u = cfg["url_of"](it)
                if not u or u in seen_urls:
                    continue
                seen_urls.add(u)
                base = {"source_url": u, "url_hash": url_hash(u),
                        "source_domain": cfg["domain"], "country": cfg["country"]}
                base.update(cfg["norm"](it))
                records.append(base)
                new_on_page += 1
                if len(records) >= limit:
                    break
            print(f"[{portal}] page {pg}: items={len(items)} new={new_on_page} total={len(records)} verdict={verdict}", flush=True)
            if new_on_page == 0:
                break
            page.wait_for_timeout(1500)
        page.close()

    # validate schema
    valid = [r for r in records if r.get("source_url") and r.get("title") and r.get("price_eur")]
    print(f"[{portal}] harvested={len(records)} schema_valid={len(valid)}", flush=True)

    # DELTA vs previous snapshot
    cur = {r["url_hash"] for r in records}
    seen_new = cur - prev          # SEEN (new since last run)
    gone = prev - cur              # GONE (disappeared)
    delta = {"portal": portal, "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
             "current": len(cur), "prev": len(prev),
             "seen_new": len(seen_new), "gone": len(gone),
             "seen_new_sample": list(seen_new)[:5], "gone_sample": list(gone)[:5]}
    (OUT / f"{portal}_delta.json").write_text(json.dumps(delta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[{portal}] DELTA: current={len(cur)} prev={len(prev)} SEEN_new={len(seen_new)} GONE={len(gone)}", flush=True)

    # write harvest (JSONL) + sample, update snapshot
    harvest = OUT / f"{portal}_harvest.jsonl"
    with harvest.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    (OUT / f"{portal}_sample.json").write_text(
        json.dumps(records[:5], indent=2, ensure_ascii=False), encoding="utf-8")
    snap_file.write_text(json.dumps(sorted(cur), ensure_ascii=False), encoding="utf-8")

    # local purge (keep snapshot + delta + sample; drop the bulk harvest)
    if purge:
        harvest.unlink(missing_ok=True)
        print(f"[{portal}] PURGED bulk harvest (kept snapshot+delta+sample) — VPS does full dump", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("portal", choices=list(PORTALS.keys()))
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--max-pages", type=int, default=12)
    ap.add_argument("--purge", action="store_true")
    args = ap.parse_args()
    try:
        return run(args.portal, args.limit, args.purge, args.max_pages)
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
