#!/usr/bin/env python3
"""Exhaustive in-page probe of mobile.de internal APIs (count / makes / listings).

Warms past Akamai once, then calls candidate JSON endpoints IN-PAGE via
page.evaluate(fetch) so every request carries the valid _abck cookie, TLS and
same-origin headers. Reports status + body head for each — the foundation for the
recursive faceting engine (need: count(filters), make list, listing enumerate,
page-size, cap).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

EVID = Path(__file__).resolve().parent / "evidence"

# Candidate endpoints (consumer mobile API + desktop). {q} filled per call.
PROBES = [
    ("hitcount_root", "https://m.mobile.de/consumer/api/search/hit-count?dam=false&vc=Car"),
    ("hitcount_audi", "https://m.mobile.de/consumer/api/search/hit-count?dam=false&vc=Car&ms=1900%3B%3B%3B"),
    ("refdata_makes", "https://m.mobile.de/consumer/api/search/reference-data/makes?vc=Car"),
    ("refdata_makes2", "https://services.mobile.de/refdata/classes/Car/makes"),
    ("srp_api", "https://m.mobile.de/consumer/api/search/srp?dam=false&vc=Car&pageNumber=1&pageSize=100"),
    ("srp_api50", "https://m.mobile.de/consumer/api/search/srp?dam=false&vc=Car&pageNumber=1&pageSize=50"),
    ("svc_search", "https://m.mobile.de/svc/s/?vc=Car&p=1"),
]

JS = """
async (url) => {
  try {
    const r = await fetch(url, {headers: {'accept':'application/json'}, credentials:'include'});
    const t = await r.text();
    return JSON.stringify({status: r.status, ct: r.headers.get('content-type'), len: t.length, head: t.slice(0, 600)});
  } catch (e) { return JSON.stringify({error: String(e)}); }
}
"""


def main() -> int:
    from camoufox.sync_api import Camoufox
    out = {}
    with Camoufox(headless=True, humanize=True, geoip=True) as browser:
        page = browser.new_page()
        # warm past Akamai
        page.goto("https://www.mobile.de/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(16000)
        # land on a search page too (sets srp cookies)
        try:
            page.goto("https://suchen.mobile.de/fahrzeuge/search.html?dam=false&isSearchRequest=true&s=Car&vc=Car",
                      wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(9000)
        except Exception:
            pass
        for name, url in PROBES:
            try:
                res = page.evaluate(JS, url)
                rec = json.loads(res)
            except Exception as e:
                rec = {"error": str(e)}
            out[name] = {"url": url, **rec}
            st = rec.get("status"); ln = rec.get("len")
            print(f"[{name}] status={st} len={ln} ct={rec.get('ct')}", flush=True)
            print(f"    head={rec.get('head','')[:200]!r}", flush=True)
            time.sleep(1)
        page.close()
    (EVID / "mobilede_probe.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
