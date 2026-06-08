#!/usr/bin/env python3
"""Discover mobile.de svc/s/ filter param names + page-size + pagination cap.

Baseline count is ~1.58M (vc=Car). Any candidate param that REDUCES the count is
a real filter. Run in-page (past Akamai). Foundation for the faceting axes.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
EVID = Path(__file__).resolve().parent / "evidence"

BASE = "https://m.mobile.de/svc/s/?vc=Car"
# candidate filter fragments to test (price/year/make/pagesize)
CANDIDATES = {
    "baseline": "",
    "price_minmax": "&minPrice=10000&maxPrice=20000",
    "price_pr": "&pr=10000%3A20000",
    "price_p$": "&p%24=10000%3A20000",
    "price_price": "&price=10000%3A20000",
    "year_fr": "&fr=2018%3A2020",
    "year_minmax": "&minFirstRegistrationDate=2018&maxFirstRegistrationDate=2020",
    "year_yor": "&yor=2018%3A2020",
    "make_ms_audi": "&ms=1900%3B%3B%3B",
    "make_make": "&make=AUDI",
    "mileage_ml": "&ml=0%3A50000",
    "pagesize_ps": "&ps=100",
    "pagesize_ipp": "&ipp=100",
    "pagesize_pageSize": "&pageSize=100",
}
JS = """
async (url) => {
  try {
    const r = await fetch(url, {headers:{'accept':'application/json'}, credentials:'include'});
    const t = await r.text();
    let n=null, items=null;
    try { const j=JSON.parse(t); n=j.numResultsTotal; items=(j.items||[]).length; } catch(e){}
    return JSON.stringify({status:r.status, len:t.length, numResultsTotal:n, items:items, head:t.slice(0,120)});
  } catch(e){ return JSON.stringify({error:String(e)}); }
}
"""

def main() -> int:
    from camoufox.sync_api import Camoufox
    out = {}
    with Camoufox(headless=True, humanize=True, geoip=True) as browser:
        page = browser.new_page()
        page.goto("https://www.mobile.de/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(16000)
        try:
            page.goto("https://suchen.mobile.de/fahrzeuge/search.html?isSearchRequest=true&s=Car&vc=Car",
                      wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(8000)
        except Exception:
            pass
        for name, frag in CANDIDATES.items():
            url = BASE + frag + "&p=1"
            try:
                rec = json.loads(page.evaluate(JS, url))
            except Exception as e:
                rec = {"error": str(e)}
            out[name] = {"frag": frag, **rec}
            print(f"[{name:18}] status={rec.get('status')} total={rec.get('numResultsTotal')} items={rec.get('items')}", flush=True)
            time.sleep(0.8)
        # pagination cap: walk p=1,20,50,80,120
        print("--- pagination cap (price 10-20k bucket) ---", flush=True)
        for pg in (1, 20, 50, 60, 80, 120):
            url = f"{BASE}&minPrice=10000&maxPrice=20000&p={pg}"
            try:
                rec = json.loads(page.evaluate(JS, url))
            except Exception as e:
                rec = {"error": str(e)}
            out[f"page_{pg}"] = rec
            print(f"  p={pg}: status={rec.get('status')} items={rec.get('items')} total={rec.get('numResultsTotal')}", flush=True)
            time.sleep(0.8)
        page.close()
    (EVID / "mobilede_probe2.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
