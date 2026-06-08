#!/usr/bin/env python3
"""leboncoin.fr harvester — PURE curl_cffi (no browser, RAM-free). DataDome serves
the full Next.js SSR to a chrome-impersonated TLS, so __NEXT_DATA__.props.pageProps
.searchData.ads carries the listings. Paginate ?category=2&page=N. Writes JSONL."""
from __future__ import annotations
import re, json, hashlib, sys
from pathlib import Path
from curl_cffi import requests

DUMPS = Path(__file__).resolve().parent/"evidence"/"dumps"; DUMPS.mkdir(parents=True,exist_ok=True)
OUT = DUMPS/"leboncoin.fr_harvest.jsonl"
PAGES = int(sys.argv[1]) if len(sys.argv)>1 else 2
LIMIT = 80

def uh(u): return hashlib.sha256(u.encode()).hexdigest()[:32]
def attr(ad,key):
    for a in (ad.get("attributes") or []):
        if a.get("key")==key: return a.get("value")
    return None
def pint(v):
    if isinstance(v,list) and v: v=v[0]
    if isinstance(v,(int,float)): return int(v)
    if isinstance(v,str):
        d=re.sub(r"[^\d]","",v); return int(d) if d else None
    return None

def main():
    recs={}
    S=requests.Session()
    for page in range(1,PAGES+1):
        url=f"https://www.leboncoin.fr/recherche?category=2&page={page}"
        r=S.get(url, impersonate="chrome", timeout=30, headers={"accept":"text/html","accept-language":"fr-FR,fr;q=0.9"})
        if r.status_code!=200: print(f"page{page} status={r.status_code} STOP",flush=True); break
        nd=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
        if not nd: print(f"page{page} no NEXT_DATA STOP",flush=True); break
        try: ads=json.loads(nd.group(1))["props"]["pageProps"]["searchData"]["ads"]
        except Exception as e: print(f"page{page} ads parse err {e}",flush=True); break
        new=0
        for ad in ads:
            u=ad.get("url")
            if not u: continue
            if u.startswith("/"): u="https://www.leboncoin.fr"+u
            h=uh(u)
            if h in recs: continue
            recs[h]={"url_hash":h,"source_url":u,"source_domain":"leboncoin.fr","country":"FR",
                     "title":(ad.get("subject") or "")[:300] or None,
                     "price_eur":pint(ad.get("price") or ad.get("price_cents")),
                     "year":pint(attr(ad,"regdate")),
                     "mileage_km":pint(attr(ad,"mileage"))}
            new+=1
        print(f"page{page}: ads={len(ads)} new={new} total={len(recs)}",flush=True)
        if len(recs)>=LIMIT: break
    recs=dict(list(recs.items())[:LIMIT])
    OUT.write_text("\n".join(json.dumps(x,ensure_ascii=False) for x in recs.values()),encoding="utf-8")
    withp=sum(1 for r in recs.values() if r["price_eur"]); withy=sum(1 for r in recs.values() if r["year"])
    print(f"WROTE {len(recs)} -> {OUT} | with_price={withp} with_year={withy}",flush=True)

if __name__=="__main__": main()
