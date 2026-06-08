#!/usr/bin/env python3
"""Find the real pagination param for m.mobile.de/svc/s/.
Compares the first item id across candidate page params; the one that CHANGES
the first id paginates. Abarth (small leaf) used so pages are stable."""
from __future__ import annotations
import json, time
BASEMS = "https://m.mobile.de/svc/s/?vc=Car&ms=140%3B%3B%3B"
JS = """async (url)=>{try{const r=await fetch(url,{headers:{'accept':'application/json'},credentials:'include'});
const j=await r.json();const its=j.items||[];return JSON.stringify({status:r.status,n:its.length,first:its[0]&&its[0].id,last:its[its.length-1]&&its[its.length-1].id});}catch(e){return JSON.stringify({error:String(e)})}}"""

def main():
    from camoufox.sync_api import Camoufox
    with Camoufox(headless=True, humanize=True, geoip=True) as b:
        pg=b.new_page()
        pg.goto("https://www.mobile.de/",wait_until="domcontentloaded",timeout=60000); pg.wait_for_timeout(16000)
        base=json.loads(pg.evaluate(JS, BASEMS+"&p=1")); print("p=1 baseline:",base,flush=True)
        for name,frag in [("p=2","&p=2"),("pageNumber=2","&pageNumber=2"),("pn=2","&pn=2"),
                          ("page=2","&page=2"),("o=20","&o=20"),("from=20","&from=20"),
                          ("start=20","&start=20"),("offset=20","&offset=20"),("s=20","&s=20")]:
            r=json.loads(pg.evaluate(JS, BASEMS+frag))
            changed = r.get("first") and r.get("first")!=base.get("first")
            print(f"  {name:14} n={r.get('n')} first={r.get('first')} CHANGED={changed}",flush=True)
            time.sleep(0.6)
        pg.close()
    return 0
if __name__=="__main__": raise SystemExit(main())
