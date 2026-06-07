#!/usr/bin/env python3
"""Find mobile.de svc/s/ pagination cap + the make/model id fields in items +
the makes reference list (for the faceting make axis)."""
from __future__ import annotations
import json, sys, time
from pathlib import Path
EVID = Path(__file__).resolve().parent / "evidence"
BASE = "https://m.mobile.de/svc/s/?vc=Car"
JS = """
async (url) => { try {
  const r = await fetch(url,{headers:{'accept':'application/json'},credentials:'include'});
  const t = await r.text(); let j=null; try{j=JSON.parse(t)}catch(e){}
  return JSON.stringify({status:r.status, len:t.length, total:j&&j.numResultsTotal, items:j&&(j.items||[]).length,
    first:j&&j.items&&j.items[0]});
} catch(e){ return JSON.stringify({error:String(e)}); } }
"""
MAKES_JS = """
async () => { for (const u of [
  'https://m.mobile.de/consumer/api/search/reference-data/makes?vehicleClass=Car',
  'https://m.mobile.de/svc/r/makes/Car',
  'https://services.mobile.de/refdata/classes/Car/makes' ]) {
  try { const r=await fetch(u,{headers:{'accept':'application/json'},credentials:'include'});
    const t=await r.text(); if(r.status===200 && t.length>50) return JSON.stringify({url:u,status:r.status,head:t.slice(0,400)});
  } catch(e){} } return JSON.stringify({none:true}); }
"""

def main() -> int:
    from camoufox.sync_api import Camoufox
    out = {}
    with Camoufox(headless=True, humanize=True, geoip=True) as browser:
        page = browser.new_page()
        page.goto("https://www.mobile.de/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(16000)
        # one full item (find make/model id fields)
        rec = json.loads(page.evaluate(JS, BASE + "&p=1"))
        out["first_item"] = rec.get("first")
        print("FIRST ITEM keys:", list((rec.get("first") or {}).keys()), flush=True)
        print("FIRST ITEM:", json.dumps(rec.get("first"), ensure_ascii=False)[:700], flush=True)
        # pagination cap
        print("--- cap ---", flush=True)
        for pg in (50, 100, 200, 300, 400, 500, 1000):
            r = json.loads(page.evaluate(JS, BASE + f"&p={pg}"))
            out[f"p{pg}"] = {"status": r.get("status"), "items": r.get("items")}
            print(f"  p={pg}: status={r.get('status')} items={r.get('items')}", flush=True)
            time.sleep(0.6)
            if r.get("items") in (0, None):
                print(f"  >>> CAP near p={pg}", flush=True); break
        # makes refdata
        mk = json.loads(page.evaluate(MAKES_JS))
        out["makes"] = mk
        print("MAKES:", json.dumps(mk, ensure_ascii=False)[:300], flush=True)
        page.close()
    (EVID / "mobilede_probe3.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
