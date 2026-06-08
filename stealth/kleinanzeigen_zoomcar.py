#!/usr/bin/env python3
"""Precise price/year extraction for kleinanzeigen (Akamai) + zoomcar via ouestfrance.
ONE camoufox. Prints a verification block so the selector can be checked."""
from __future__ import annotations
import json, re, hashlib
from pathlib import Path
from camoufox.sync_api import Camoufox

DUMPS=Path(__file__).resolve().parent/"evidence"/"dumps"
def uh(u): return hashlib.sha256(u.encode()).hexdigest()[:32]
def pint(s):
    if s is None: return None
    d=re.sub(r"\.","",str(s)).split(",")[0]; d=re.sub(r"[^\d]","",d); return int(d) if d else None
def y4(s):
    m=re.search(r"\b(19[7-9]\d|20[0-2]\d)\b",str(s or "")); return int(m.group(1)) if m else None

def kleinanzeigen(pg):
    pg.goto("https://www.kleinanzeigen.de/", wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(8000)
    pg.goto("https://www.kleinanzeigen.de/s-autos/c216", wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(6000)
    h=pg.content()
    arts=re.split(r'<article', h)[1:]
    print(f"[kln] articles={len(arts)}", flush=True)
    if arts: print("[kln] VERIFY block0 (price area):", re.sub(r'\s+',' ',arts[0])[:700], flush=True)
    recs={}
    for blk in arts:
        m=re.search(r'href="(/s-anzeige/[a-z0-9-]+/\d[\d-]*)"', blk)
        if not m: continue
        u="https://www.kleinanzeigen.de"+m.group(1)
        pm=re.search(r'aditem-main--middle--price-shipping--price[^>]*>\s*([\d.]+)\s*€', blk)
        price=pint(pm.group(1)) if pm else None
        tags=re.findall(r'simpletag[^>]*>([^<]+)<', blk)
        yr=next((y4(t) for t in tags if y4(t)),None)
        km=next((pint(t) for t in tags if "km" in t.lower()),None)
        tm=re.search(r'class="text-module-begin"[^>]*>.*?<a[^>]*>(.*?)</a>', blk, re.DOTALL) or re.search(r'<a[^>]*ellipsis[^>]*>(.*?)</a>', blk, re.DOTALL)
        title=re.sub(r'<[^>]+>','',tm.group(1)).strip() if tm else None
        recs[uh(u)]={"url_hash":uh(u),"source_url":u,"source_domain":"kleinanzeigen.de","country":"DE",
                     "title":(title or "")[:300] or None,"price_eur":price,"year":yr,"mileage_km":km}
        if len(recs)>=40: break
    if recs: (DUMPS/"kleinanzeigen.de_harvest.jsonl").write_text("\n".join(json.dumps(x,ensure_ascii=False) for x in recs.values()),encoding="utf-8")
    print(f"[kln] records={len(recs)} with_price={sum(1 for r in recs.values() if r['price_eur'])} with_year={sum(1 for r in recs.values() if r['year'])}",flush=True)
    for r in list(recs.values())[:4]: print("   ",(r['title'] or '')[:34],"|",r['price_eur'],"|",r['year'],"|",r['mileage_km'],flush=True)

def zoomcar(pg):
    pg.goto("https://www.ouestfrance-auto.com/voiture-occasion/", wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(10000)
    h=pg.content()
    nd=re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.DOTALL)
    print(f"[zoom] NEXT_DATA={bool(nd)}",flush=True)
    recs={}
    if nd:
        j=json.loads(nd.group(1))
        # walk for listings array with price + url
        best=None; st=[(j,"")]
        while st:
            o,p=st.pop()
            if isinstance(o,dict):
                for k,v in o.items():
                    if isinstance(v,list) and len(v)>=3 and isinstance(v[0],dict):
                        ks=set(v[0].keys())
                        if (ks&{"price","prix","priceFormatted"}) and (ks&{"url","id","slug","reference"}):
                            if best is None or len(v)>len(best[1]): best=(p+"."+k,v)
                    st.append((v,p+"."+k))
        if best:
            path,L=best; print(f"[zoom] listings at {path}: {len(L)} keys={list(L[0].keys())[:12]}",flush=True)
            for it in L:
                slug=it.get("url") or it.get("slug")
                u=("https://www.zoomcar.fr"+slug if isinstance(slug,str) and slug.startswith("/") else slug) or f"https://www.zoomcar.fr/ad/{it.get('id') or it.get('reference')}"
                if not isinstance(u,str) or not u.startswith("http"): continue
                recs[uh(u)]={"url_hash":uh(u),"source_url":u,"source_domain":"zoomcar.fr","country":"FR",
                             "title":(it.get("title") or it.get("label") or "")[:300] or None,
                             "price_eur":pint(it.get("price") or it.get("prix")),"year":y4(it.get("year") or it.get("annee") or it.get("registration")),
                             "mileage_km":pint(it.get("mileage") or it.get("kilometrage") or it.get("km"))}
        else:
            print("[zoom] no listings array in NEXT_DATA",flush=True)
    if recs: (DUMPS/"zoomcar.fr_harvest.jsonl").write_text("\n".join(json.dumps(x,ensure_ascii=False) for x in recs.values()),encoding="utf-8")
    print(f"[zoom] records={len(recs)} with_price={sum(1 for r in recs.values() if r['price_eur'])}",flush=True)
    for r in list(recs.values())[:3]: print("   ",(r['title'] or '')[:30],"|",r['price_eur'],"|",r['year'],"|",r['mileage_km'],flush=True)

def main():
    with Camoufox(headless=True, humanize=True, geoip=True) as b:
        pg=b.new_page()
        for fn in (kleinanzeigen, zoomcar):
            try: fn(pg)
            except Exception as e: print(f"[{fn.__name__}] EXC {str(e)[:80]}",flush=True)
        pg.close()
    print("DONE",flush=True)

if __name__=="__main__": main()
