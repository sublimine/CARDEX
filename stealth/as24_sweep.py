#!/usr/bin/env python3
"""AS24 harvester — parse __NEXT_DATA__.props.pageProps.listings across 6 TLDs.
One reused Camoufox (warm per TLD). Extracts url/title/price/year/mileage.
Writes per-TLD JSONL to evidence/dumps/autoscout24.<tld>_harvest.jsonl."""
from __future__ import annotations
import json, re, hashlib
from pathlib import Path

STEALTH = Path(__file__).resolve().parent
DUMPS = STEALTH/"evidence"/"dumps"; DUMPS.mkdir(parents=True, exist_ok=True)
TLDS = [("de","DE"),("fr","FR"),("es","ES"),("nl","NL"),("be","BE"),("it","IT")]
PAGES = 2; LIMIT = 40

def uh(u): return hashlib.sha256(u.encode()).hexdigest()[:32]
def digits(s):
    if s is None: return None
    d=re.sub(r"[^\d]","",str(s).split(",")[0]); return int(d) if d else None
def find_year(item):
    v=item.get("vehicle") or {}
    for k in ("firstRegistrationDateFormatted","firstRegistrationDate","firstRegistration"):
        m=re.search(r"(19[7-9]\d|20[0-2]\d)", str(v.get(k) or ""));
        if m: return int(m.group(1))
    # vehicleDetails list of {label/value} or dict
    vd=item.get("vehicleDetails")
    if isinstance(vd,list):
        for d in vd:
            if isinstance(d,dict) and d.get("iconName")=="calendar":
                m=re.search(r"(19[7-9]\d|20[0-2]\d)", str(d.get("data") or ""))
                if m: return int(m.group(1))
    blob=json.dumps(vd,ensure_ascii=False) if vd else ""
    m=re.search(r'"(?:firstRegistration|registration)[^"]*"\s*:\s*"[^"]*?(19[7-9]\d|20[0-2]\d)', blob)
    if m: return int(m.group(1))
    return None

def norm(item, host, country):
    u=item.get("url") or ""
    if u.startswith("/"): u=f"https://www.{host}"+u
    if not u.startswith("http"): return None
    v=item.get("vehicle") or {}
    make=v.get("make") or ""; mv=v.get("modelVersionInput") or v.get("model") or ""
    title=(f"{make} {mv}".strip() or None)
    price=None
    p=item.get("price") or {}
    if isinstance(p,dict): price=digits(p.get("priceFormatted") or p.get("price"))
    elif isinstance(p,(int,float,str)): price=digits(p)
    return {"url_hash":uh(u),"source_url":u,"source_domain":f"autoscout24.{country.lower()}" if False else f"autoscout24.{host.split('.')[-1]}",
            "country":country,"title":(title or "")[:300] or None,
            "price_eur":price,"mileage_km":digits(v.get("mileageInKm")),"year":find_year(item)}

def main():
    from camoufox.sync_api import Camoufox
    summary={}
    with Camoufox(headless=True, humanize=True, geoip=True) as b:
        pg=b.new_page()
        for tld,country in TLDS:
            host=f"autoscout24.{tld}"
            recs={}
            try:
                pg.goto(f"https://www.{host}/", wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(7000)
                for page in range(1,PAGES+1):
                    pg.goto(f"https://www.{host}/lst?sort=age&desc=1&atype=C&page={page}", wait_until="domcontentloaded", timeout=60000)
                    pg.wait_for_timeout(5000)
                    html=pg.content()
                    nd=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
                    if not nd: break
                    try: L=json.loads(nd.group(1))["props"]["pageProps"]["listings"]
                    except Exception: L=[]
                    for it in L:
                        r=norm(it, host, country)
                        if r: recs[r["url_hash"]]=r
                    if len(recs)>=LIMIT: break
            except Exception as e:
                summary[host]={"err":str(e)[:80]}; print(f"[{host}] ERR {str(e)[:80]}",flush=True); continue
            recs=dict(list(recs.items())[:LIMIT])
            if recs:
                (DUMPS/f"{host}_harvest.jsonl").write_text("\n".join(json.dumps(x,ensure_ascii=False) for x in recs.values()),encoding="utf-8")
            withp=sum(1 for r in recs.values() if r["price_eur"])
            summary[host]={"records":len(recs),"with_price":withp}
            print(f"[{host}] records={len(recs)} with_price={withp} sample={list(recs.values())[0] if recs else None}",flush=True)
        pg.close()
    (STEALTH/"evidence"/"sweep"/"as24_summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
    print("AS24_DONE",flush=True)

if __name__=="__main__": main()
