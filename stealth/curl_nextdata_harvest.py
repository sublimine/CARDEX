#!/usr/bin/env python3
"""Generic curl_cffi __NEXT_DATA__ harvester (RAM-free, no browser) for portals
whose WAF serves the Next.js SSR to a chrome-impersonated TLS (leboncoin, coches,
autoboerse...). Walks __NEXT_DATA__ for the largest listings array, maps fields
defensively. Usage: python curl_nextdata_harvest.py <domain> <url> <host> <country> <lang>"""
from __future__ import annotations
import re, json, hashlib, sys
from pathlib import Path
from curl_cffi import requests

DUMPS = Path(__file__).resolve().parent/"evidence"/"dumps"; DUMPS.mkdir(parents=True,exist_ok=True)

def uh(u): return hashlib.sha256(u.encode()).hexdigest()[:32]
def nm(v): return v.get("name","") if isinstance(v,dict) else (str(v) if v else "")
def pint(v):
    if isinstance(v,dict): v=v.get("amount") or v.get("value") or v.get("gross") or v.get("priceFormatted")
    if isinstance(v,list) and v: v=v[0]
    if isinstance(v,(int,float)): return int(v) if v>0 else None
    if isinstance(v,str):
        d=re.sub(r"[^\d]","",v.split(",")[0].split(".")[0]); return int(d) if d else None
    return None
def yr(*vals):
    for v in vals:
        m=re.search(r"(19[7-9]\d|20[0-2]\d)", str(v or ""))
        if m: return int(m.group(1))
    return None
def best_list(j):
    best=None; stack=[(j,"")]
    while stack:
        o,p=stack.pop()
        if isinstance(o,dict):
            for k,v in o.items():
                if isinstance(v,list) and len(v)>=3 and isinstance(v[0],dict):
                    keys=set(v[0].keys())
                    if (keys & {"price","precio","priceFormatted"}) and (keys & {"id","url","make","marca","model","subject","title","visibleId"}):
                        if best is None or len(v)>len(best[1]): best=(p+"."+k,v)
                stack.append((v,p+"."+k))
        elif isinstance(o,list):
            for it in o[:3]:
                if isinstance(it,(dict,list)): stack.append((it,p+"[]"))
    return best

def main():
    domain,url,host,country,lang = sys.argv[1:6]
    r=requests.get(url, impersonate="chrome", timeout=30, headers={"accept":"text/html","accept-language":lang})
    print(f"status={r.status_code} len={len(r.text)}",flush=True)
    nd=re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
    if not nd: print("no __NEXT_DATA__"); return 1
    bl=best_list(json.loads(nd.group(1)))
    if not bl: print("no listings array"); return 1
    path,L=bl; print(f"listings at {path}: {len(L)}",flush=True)
    recs={}
    for it in L:
        slug=it.get("url") or it.get("slug") or it.get("seoUrl") or it.get("detailUrl")
        u=("https://"+host+slug if isinstance(slug,str) and slug.startswith("/") else slug) or f"https://{host}/ad/{it.get('id') or it.get('visibleId')}"
        if not isinstance(u,str) or not u.startswith("http"): continue
        title=it.get("title") or it.get("subject") or f"{nm(it.get('make') or it.get('marca'))} {nm(it.get('model') or it.get('modelo'))} {nm(it.get('version'))}".strip()
        recs[uh(u)]={"url_hash":uh(u),"source_url":u,"source_domain":domain,"country":country,
                     "title":(title or "")[:300] or None,
                     "price_eur":pint(it.get("price") or it.get("precio") or it.get("priceFormatted")),
                     "year":yr(it.get("registration"),it.get("regdate"),it.get("year"),it.get("firstRegistration"),it.get("ez")),
                     "mileage_km":pint(it.get("mileage") or it.get("mileageInKm") or it.get("km") or it.get("kilometraje"))}
    recs=dict(list(recs.items())[:40])
    (DUMPS/f"{domain}_harvest.jsonl").write_text("\n".join(json.dumps(x,ensure_ascii=False) for x in recs.values()),encoding="utf-8")
    print(f"records={len(recs)} with_price={sum(1 for x in recs.values() if x['price_eur'])} with_year={sum(1 for x in recs.values() if x['year'])}",flush=True)

if __name__=="__main__": raise SystemExit(main())
