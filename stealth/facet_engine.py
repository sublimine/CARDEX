#!/usr/bin/env python3
"""Generic recursive FACETING engine for total per-portal coverage.

Idea (config-driven, portal-agnostic):
  - count(filters)            -> declared result total for a facet node
  - children(filters, axis)   -> partition a node along one axis (make/year/...)
  - recurse: if count<=CAP it's a LEAF; else subdivide on the next axis.
  - COVERAGE PROOF: sum(leaf counts) ≈ root count (report both; if short, subdivide
    more / inspect the gap). Union of leaf IDs = full catalog.
  - ENUMERATE leaves by paginating the internal API (validate-with-limit locally).
  - DELTA: ID set vs snapshot -> SEEN/GONE.

Anti-bot: ONE Camoufox session warms past Akamai; every count/enumerate is an
IN-PAGE fetch (page.evaluate) so it carries the valid cookie/TLS. No browser per
ad. RAM-safe. Meant to run DETACHED as a persistent worker.

This file ships the mobile.de config (svc/s/ API). Other portals plug in the same
shape. Usage:
    python facet_engine.py mobilede --mode coverage      # prove sum≈total
    python facet_engine.py mobilede --mode enumerate --limit 500
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EVID = Path(__file__).resolve().parent / "evidence"
OUT = EVID / "facet"
OUT.mkdir(parents=True, exist_ok=True)

FETCH_JS = """
async (url) => { try {
  const r = await fetch(url, {headers:{'accept':'application/json'}, credentials:'include'});
  const t = await r.text(); let j=null; try{j=JSON.parse(t)}catch(e){}
  return JSON.stringify({status:r.status, total: j&&j.numResultsTotal,
    items: j&&(j.items||[]).map(x=>({id:x.id, makeId:x.makeId, modelId:x.modelId,
      make:x.make, model:x.model, title:x.title, price:x.price, url:x.url, attr:x.attr})) });
} catch(e){ return JSON.stringify({error:String(e)}); } }
"""
REF_JS = "async (url)=>{try{const r=await fetch(url,{headers:{'accept':'application/json'},credentials:'include'});return await r.text();}catch(e){return JSON.stringify({error:String(e)})}}"


# --- mobile.de config ------------------------------------------------------------
def mobilede_search_url(filters: dict, page: int) -> str:
    q = "https://m.mobile.de/svc/s/?vc=Car"
    for k, v in filters.items():
        q += f"&{k}={v}"
    return q + f"&p={page}"


CONFIGS_DIR = REPO / "configs" / "portals"


def load_config(portal: str) -> dict:
    """Build the engine runtime config from the versioned per-portal JSON
    (configs/portals/<portal>.json). Single source of truth, reusable."""
    raw = json.loads((CONFIGS_DIR / f"{portal}.json").read_text(encoding="utf-8"))
    count_tpl = raw["endpoints"]["api_url"]   # unified schema: count goes via endpoints.api_url

    def search_url(filters: dict, page: int = 1) -> str:
        frag = "".join(f"&{k}={v}" for k, v in filters.items())
        return count_tpl.replace("{filters}", frag)

    axes = {a["axis"]: a for a in raw.get("facet_axes", [])}
    mk = axes.get("make", {})
    yr = axes.get("year", {})
    return {
        "name": raw["source_key"],
        "country": raw.get("country", ""),
        "warm": raw["access"]["warm"],
        "search_url": search_url,
        "total_path": raw.get("count", {}).get("total_path", "numResultsTotal"),
        "makes_ref": mk.get("values_ref") or raw["endpoints"].get("makes_ref"),
        "makes_path": mk.get("values_path", "makes"),
        "make_id_key": mk.get("id_key", "i"),
        "make_param": mk.get("param", "ms"),
        "make_format": mk.get("format", "{makeId}"),
        "year_param": yr.get("param", "fr"),
        "year_values": [f"{y}%3A{y}" for y in range(1990, 2027)],
        "page_size": raw.get("enumerate", {}).get("page_size", 20),
        "leaf_cap": raw.get("leaf_cap", 2000),
        "raw": raw,
    }


COUNT_SLEEP = 0.25


class Session:
    """One warmed Camoufox page; all queries go in-page."""
    def __init__(self, cfg):
        self.cfg = cfg
        self._cm = None
        self.page = None

    def __enter__(self):
        from camoufox.sync_api import Camoufox
        self._cm = Camoufox(headless=True, humanize=True, geoip=True)
        self.browser = self._cm.__enter__()
        self.page = self.browser.new_page()
        for w in self.cfg["warm"]:
            self.page.goto(w, wait_until="domcontentloaded", timeout=60000)
            self.page.wait_for_timeout(16000)
        return self

    def __exit__(self, *a):
        try:
            self._cm.__exit__(*a)
        except Exception:
            pass

    def query(self, filters: dict, page: int = 1) -> dict:
        url = self.cfg["search_url"](filters, page)
        for _ in range(2):
            try:
                rec = json.loads(self.page.evaluate(FETCH_JS, url))
                if rec.get("status") == 200:
                    return rec
            except Exception:
                pass
            self.page.wait_for_timeout(1500)
        return {"status": None, "total": None, "items": []}

    def count(self, filters: dict) -> int | None:
        time.sleep(COUNT_SLEEP)
        return self.query(filters, 1).get("total")

    def makes(self) -> list[dict]:
        try:
            txt = self.page.evaluate(REF_JS, self.cfg["makes_ref"])
            return json.loads(txt).get(self.cfg.get("makes_path", "makes"), [])
        except Exception:
            return []


def uhash(u: str) -> str:
    return hashlib.sha256(u.encode("utf-8")).hexdigest()[:32]


def mode_coverage(s: Session, cfg) -> dict:
    """Prove sum(make counts) ≈ root; then deep-dive the biggest make by year."""
    root = s.count({})
    print(f"ROOT total (vc=Car) = {root:,}", flush=True)
    makes = s.makes()
    print(f"makes in refdata: {len(makes)}", flush=True)
    idk, mp, mfmt, yp, cap = (cfg["make_id_key"], cfg["make_param"], cfg["make_format"],
                              cfg["year_param"], cfg["leaf_cap"])

    def mk_filter(mid):
        return {mp: mfmt.replace("{makeId}", str(mid))}

    per_make = []
    acc = 0
    for m in makes:
        c = s.count(mk_filter(m[idk]))
        if c is None:
            continue
        acc += c
        per_make.append({"make": m.get("n") or m.get(cfg.get("make_name_key", "n")), "id": m[idk], "count": c})
        if len(per_make) % 20 == 0:
            print(f"  ...{len(per_make)}/{len(makes)} makes counted, running sum={acc:,}", flush=True)
    per_make.sort(key=lambda x: -x["count"])
    print(f"\nMAKE PARTITION: sum_of_makes={acc:,}  root={root:,}  coverage={100*acc/root:.1f}%", flush=True)
    print("top makes:", flush=True)
    for x in per_make[:8]:
        over = "  (>CAP -> needs subdivision)" if x["count"] > cap else ""
        print(f"  {str(x['make']):18} {x['count']:>8,}{over}", flush=True)

    # deep-dive the biggest make by YEAR to prove recursion reconciles
    big = per_make[0]
    print(f"\nDEEP-DIVE {big['make']} (id={big['id']}, count={big['count']:,}) by year:", flush=True)
    yr_sum = 0
    yr_rows = []
    for yr in cfg["year_values"]:
        c = s.count({**mk_filter(big["id"]), yp: yr})
        if c is None:
            continue
        yr_sum += c
        if c:
            yr_rows.append({"year": yr.replace("%3A", ":"), "count": c})
    print(f"  {big['make']}: sum_over_years={yr_sum:,}  make_count={big['count']:,}  reconcile={100*yr_sum/max(1,big['count']):.1f}%", flush=True)

    report = {"portal": cfg["name"], "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
              "root": root, "sum_of_makes": acc, "coverage_pct": round(100 * acc / root, 2),
              "n_makes": len(per_make), "per_make": per_make,
              "deepdive": {"make": big["make"], "make_count": big["count"],
                           "sum_over_years": yr_sum, "years": yr_rows}}
    (OUT / f"{cfg['name']}_coverage.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWROTE {OUT / (cfg['name']+'_coverage.json')}", flush=True)
    return report


def desktop_page_url(filters: dict, page: int) -> str:
    """Enumeration route. svc/s/ is COUNT+PREVIEW only (top-20, does NOT paginate
    via any param). Full leaf enumeration uses the desktop SSR search, which DOES
    paginate via pageNumber; listings are in __INITIAL_STATE__.search.srp.data.
    searchResults.items. Faceting keeps each leaf under the desktop pagination cap
    (~50 pages) so a leaf is fully enumerable. [VERIFIED probe_pageparam.py]"""
    q = "https://suchen.mobile.de/fahrzeuge/search.html?isSearchRequest=true&s=Car&vc=Car"
    for k, v in filters.items():
        q += f"&{k}={v}"
    return q + f"&pageNumber={page}"


def mode_enumerate(s: Session, cfg, limit: int) -> dict:
    """Enumerate small leaves (validate-with-limit), normalise, dedup, DELTA.

    NOTE: enumeration must use the desktop SSR route (desktop_page_url +
    __INITIAL_STATE__), not svc/s/ which only previews the first 20. Count/coverage
    still use svc/s/ (exact). This demo records the svc preview page per leaf; the
    VPS full-dump paginates the desktop route under each sub-cap leaf."""
    idk, mp, mfmt, cap = cfg["make_id_key"], cfg["make_param"], cfg["make_format"], cfg["leaf_cap"]

    def mk_filter(mid):
        return {mp: mfmt.replace("{makeId}", str(mid))}

    makes = s.makes()
    # pick small makes (count <= cap) to fully enumerate cheaply
    leaves = []
    for m in makes:
        c = s.count(mk_filter(m[idk]))
        if c and c <= cap:
            leaves.append((m, c))
        if sum(x[1] for x in leaves) >= limit:
            break
    print(f"enumerating {len(leaves)} small leaves (cap {cap})", flush=True)
    records = {}
    for m, c in leaves:
        got = 0
        for pg in range(1, (c // cfg["page_size"]) + 3):
            r = s.query(mk_filter(m[idk]), pg)
            items = r.get("items") or []
            if not items:
                break
            for it in items:
                u = it.get("url") or f"https://suchen.mobile.de/fahrzeuge/details.html?id={it.get('id')}"
                rec = {"source_url": u, "url_hash": uhash(u), "source_domain": "mobile.de",
                       "country": "DE", "ext_id": it.get("id"),
                       "make": it.get("make"), "model": it.get("model"),
                       "title": it.get("title") or it.get("shortTitle"),
                       "price_eur": (it.get("price") if isinstance(it.get("price"), (int, float)) else None)}
                records[rec["url_hash"]] = rec
                got += 1
            if len(records) >= limit:
                break
            time.sleep(0.2)
        print(f"  {m.get('n', m[idk])}: declared={c} enumerated={got}", flush=True)
        if len(records) >= limit:
            break

    # DELTA
    snap = OUT / f"{cfg['name']}_enum_snapshot.json"
    prev = set(json.loads(snap.read_text(encoding="utf-8"))) if snap.exists() else set()
    cur = set(records.keys())
    delta = {"current": len(cur), "prev": len(prev),
             "seen_new": len(cur - prev), "gone": len(prev - cur)}
    print(f"ENUMERATE: unique={len(cur)}  DELTA seen_new={delta['seen_new']} gone={delta['gone']}", flush=True)
    (OUT / f"{cfg['name']}_enum_sample.json").write_text(
        json.dumps(list(records.values())[:8], indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / f"{cfg['name']}_enum_delta.json").write_text(json.dumps(delta, indent=2), encoding="utf-8")
    snap.write_text(json.dumps(sorted(cur)), encoding="utf-8")
    return {"unique": len(cur), "delta": delta}


def available_portals() -> list[str]:
    return sorted(p.stem for p in CONFIGS_DIR.glob("*.json") if not p.stem.startswith("_"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("portal", help="portal key matching configs/portals/<portal>.json (e.g. mobile.de)")
    ap.add_argument("--mode", choices=["coverage", "enumerate"], default="coverage")
    ap.add_argument("--limit", type=int, default=500)
    args = ap.parse_args()
    if args.portal not in available_portals():
        print(f"no config for '{args.portal}'. available: {available_portals()}")
        return 2
    cfg = load_config(args.portal)
    with Session(cfg) as s:
        if args.mode == "coverage":
            mode_coverage(s, cfg)
        else:
            mode_enumerate(s, cfg, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
