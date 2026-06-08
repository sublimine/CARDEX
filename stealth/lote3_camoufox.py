#!/usr/bin/env python3
"""Lote-3 camoufox batch: ONE browser, navigate each portal (no relaunch).
- kleinanzeigen.de: price/year from search cards
- autoscout24.de: recon listings[0].vehicleDetails (find year field)
- ouestfrance/zoomcar: rendered JSON-LD price/year
- vlan.be / gocar.be / nederlandmobiel.nl: classify + count listings (exhaust before proxy)
Writes per-portal JSONL + prints recon. Run with services stopped (RAM)."""
from __future__ import annotations
import json, re, hashlib
from pathlib import Path
from camoufox.sync_api import Camoufox

DUMPS=Path(__file__).resolve().parent/"evidence"/"dumps"; DUMPS.mkdir(parents=True,exist_ok=True)
def uh(u): return hashlib.sha256(u.encode()).hexdigest()[:32]
def pint(s):
    if s is None: return None
    d=re.sub(r"[^\d]","",str(s).split(",")[0].split(".")[0] if "." in str(s) and len(str(s).split(".")[-1])==3 else str(s).split(",")[0])
    return int(d) if d else None
def y4(s):
    m=re.search(r"(19[7-9]\d|20[0-2]\d)",str(s or "")); return int(m.group(1)) if m else None
BLK=["datadome","captcha-delivery","perimeterx","pardon our","cf-chl","challenge-platform","just a moment","access denied"]

def kleinanzeigen(pg):
    pg.goto("https://www.kleinanzeigen.de/", wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(8000)
    pg.goto("https://www.kleinanzeigen.de/s-autos/c216", wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(6000)
    h=pg.content(); recs={}
    # split per article block
    for blk in re.split(r'<article', h)[1:]:
        m=re.search(r'href="(/s-anzeige/[a-z0-9-]+/\d[\d-]*)"', blk)
        if not m: continue
        u="https://www.kleinanzeigen.de"+m.group(1)
        pm=re.search(r'([\d.]+)\s*€', blk); price=pint(pm.group(1)) if pm else None
        tm=re.search(r'<h2[^>]*>.*?<a[^>]*>(.*?)</a>', blk, re.DOTALL); title=re.sub(r'<[^>]+>','',tm.group(1)).strip() if tm else None
        yr=y4(title)
        recs[uh(u)]={"url_hash":uh(u),"source_url":u,"source_domain":"kleinanzeigen.de","country":"DE",
                     "title":(title or "")[:300] or None,"price_eur":price,"year":yr,"mileage_km":None}
        if len(recs)>=40: break
    if recs: (DUMPS/"kleinanzeigen.de_harvest.jsonl").write_text("\n".join(json.dumps(x,ensure_ascii=False) for x in recs.values()),encoding="utf-8")
    wp=sum(1 for r in recs.values() if r['price_eur']); wy=sum(1 for r in recs.values() if r['year'])
    print(f"[kleinanzeigen] records={len(recs)} with_price={wp} with_year={wy} sample={list(recs.values())[0] if recs else None}",flush=True)

def as24_year(pg):
    pg.goto("https://www.autoscout24.de/", wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(6000)
    pg.goto("https://www.autoscout24.de/lst?atype=C", wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(6000)
    nd=re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', pg.content(), re.DOTALL)
    if not nd: print("[as24-year] no NEXT_DATA",flush=True); return
    it=json.loads(nd.group(1))["props"]["pageProps"]["listings"][0]
    vd=it.get("vehicleDetails"); v=it.get("vehicle") or {}
    print(f"[as24-year] vehicleDetails={json.dumps(vd,ensure_ascii=False)[:300]}",flush=True)
    print(f"[as24-year] vehicle year-ish keys: "+str({k:v[k] for k in v if 'reg' in k.lower() or 'year' in k.lower() or 'date' in k.lower()}),flush=True)

def zoomcar(pg):
    pg.goto("https://www.ouestfrance-auto.com/voiture-occasion/", wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(9000)
    h=pg.content(); recs={}
    for m in re.finditer(r'application/ld\+json[^>]*>(.*?)</script>', h, re.DOTALL):
        try: data=json.loads(m.group(1).strip())
        except: continue
        st=[data]
        while st:
            o=st.pop()
            if isinstance(o,list): st+=o; continue
            if not isinstance(o,dict): continue
            if str(o.get("@type","")).lower() in ("car","vehicle","product") and (o.get("offers") or o.get("url")):
                u=o.get("url") or ""; off=o.get("offers") or {}
                price=off.get("price") if isinstance(off,dict) else (off[0].get("price") if isinstance(off,list) and off else None)
                if u: recs[uh(u)]={"url_hash":uh(u),"source_url":u,"source_domain":"zoomcar.fr","country":"FR",
                                   "title":(o.get("name") or "")[:300] or None,"price_eur":pint(price),
                                   "year":y4(o.get("vehicleModelDate") or o.get("productionDate") or o.get("dateVehicleFirstRegistered")),
                                   "mileage_km":pint((o.get("mileageFromOdometer") or {}).get("value") if isinstance(o.get("mileageFromOdometer"),dict) else None)}
            st+=list(o.values())
    if recs: (DUMPS/"zoomcar.fr_harvest.jsonl").write_text("\n".join(json.dumps(x,ensure_ascii=False) for x in recs.values()),encoding="utf-8")
    print(f"[zoomcar] records={len(recs)} with_price={sum(1 for r in recs.values() if r['price_eur'])} sample={list(recs.values())[0] if recs else None}",flush=True)

def classify_portal(pg, name, warm, target, detail_re):
    try:
        pg.goto(warm, wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(8000)
        st=pg.goto(target, wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(8000)
        # settle for CF
        for _ in range(2):
            h=pg.content(); low=h.lower()
            if not any(b in low for b in BLK): break
            pg.wait_for_timeout(8000)
            try: pg.reload(wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(6000)
            except: pass
        h=pg.content(); low=h.lower()
        hits=[b for b in BLK if b in low]; dets=len(set(re.findall(detail_re,h)))
        print(f"[{name}] status={st.status if st else None} len={len(h)} detailURLs={dets} blk={hits[:3]}",flush=True)
        return h, dets, hits
    except Exception as e:
        print(f"[{name}] EXC {str(e)[:60]}",flush=True); return "",0,["exc"]

def main():
    with Camoufox(headless=True, humanize=True, geoip=True) as b:
        pg=b.new_page()
        for fn in (kleinanzeigen, as24_year, zoomcar):
            try: fn(pg)
            except Exception as e: print(f"[{fn.__name__}] EXC {str(e)[:70]}",flush=True)
        classify_portal(pg,"vlan.be","https://www.vlan.be/","https://www.vlan.be/fr/voitures-occasions", r'/[a-z0-9-]+-\d{5,}')
        classify_portal(pg,"gocar.be","https://www.gocar.be/","https://www.gocar.be/fr/voitures-occasion", r'/\d{5,}')
        classify_portal(pg,"nederlandmobiel.nl","https://www.nederlandmobiel.nl/","https://www.nederlandmobiel.nl/aanbod", r'/\d{4,}')
        pg.close()
    print("LOTE3_DONE",flush=True)

if __name__=="__main__": main()
