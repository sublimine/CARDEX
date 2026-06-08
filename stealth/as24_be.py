#!/usr/bin/env python3
"""autoscout24.be — find the working /lst path variant and harvest via __NEXT_DATA__."""
from __future__ import annotations
import json, re, hashlib
from pathlib import Path
from camoufox.sync_api import Camoufox

DUMPS = Path(__file__).resolve().parent/"evidence"/"dumps"
OUT = DUMPS/"autoscout24.be_harvest.jsonl"

def uh(u): return hashlib.sha256(u.encode()).hexdigest()[:32]
def digits(s):
    if s is None: return None
    d=re.sub(r"[^\d]","",str(s).split(",")[0]); return int(d) if d else None
def listings(html):
    nd=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not nd: return []
    try: return json.loads(nd.group(1))["props"]["pageProps"]["listings"] or []
    except Exception: return []
def norm(it):
    u=it.get("url") or ""
    if u.startswith("/"): u="https://www.autoscout24.be"+u
    if not u.startswith("http"): return None
    v=it.get("vehicle") or {}; p=it.get("price") or {}
    return {"url_hash":uh(u),"source_url":u,"source_domain":"autoscout24.be","country":"BE",
            "title":(f"{v.get('make','')} {v.get('modelVersionInput') or v.get('model') or ''}".strip())[:300] or None,
            "price_eur":digits(p.get("priceFormatted") if isinstance(p,dict) else p),
            "mileage_km":digits(v.get("mileageInKm")),"year":None}

VARIANTS=["/lst?atype=C&sort=age&desc=1","/nl/lst?atype=C&sort=age&desc=1",
          "/fr/lst?atype=C&sort=age&desc=1","/en/lst?atype=C&sort=age&desc=1"]

def main():
    recs={}; chosen=None
    with Camoufox(headless=True, humanize=True, geoip=True) as b:
        pg=b.new_page()
        pg.goto("https://www.autoscout24.be/", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(8000)
        print("landed:", pg.url, flush=True)
        for path in VARIANTS:
            try:
                pg.goto("https://www.autoscout24.be"+path, wait_until="domcontentloaded", timeout=60000)
                pg.wait_for_timeout(6000)
                L=listings(pg.content())
            except Exception as e:
                print(f"  {path} ERR {str(e)[:50]}", flush=True); continue
            print(f"  {path} -> listings={len(L)} url={pg.url[:55]}", flush=True)
            if len(L)>=5:
                chosen=path
                break
        if chosen:
            for page in range(1,3):
                try:
                    pg.goto(f"https://www.autoscout24.be{chosen}&page={page}", wait_until="domcontentloaded", timeout=60000)
                    pg.wait_for_timeout(4500)
                except Exception:
                    break
                for it in listings(pg.content()):
                    r=norm(it)
                    if r: recs[r["url_hash"]]=r
                if len(recs)>=40: break
        pg.close()
    recs=dict(list(recs.items())[:40])
    if recs:
        OUT.write_text("\n".join(json.dumps(x,ensure_ascii=False) for x in recs.values()),encoding="utf-8")
        wp=sum(1 for r in recs.values() if r["price_eur"])
        print(f"CHOSEN={chosen} records={len(recs)} with_price={wp} sample={list(recs.values())[0]}",flush=True)
    else:
        print(f"NO_LISTINGS chosen={chosen}",flush=True)

if __name__=="__main__": main()
