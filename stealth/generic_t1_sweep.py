#!/usr/bin/env python3
"""Generic T1 sweep — attack every defended platform in the census end-to-end.

ONE Camoufox instance reused across portals (avoids multi-launch crash). Per
portal: warm -> target search page -> classify (blocked vs ok) -> extract via
cascade (JSON-LD schema.org Car/Vehicle/Offer  ->  __NEXT_DATA__/__INITIAL ads
->  portal detail-URL regex) -> normalized records JSONL. Browser closes, THEN
seam phase writes each portal's sample to vehicle_index, captures BEFORE/AFTER +
samples, and PURGES (validate-with-limit-and-purge). Hardware: caller pauses
Meili/Grafana/Prometheus around this; concurrency 1; small batch.

Output: evidence/sweep/t1_marker.json + per-portal JSONL in evidence/dumps/.
"""
from __future__ import annotations
import json, re, time, hashlib, subprocess, sys
from pathlib import Path

STEALTH = Path(__file__).resolve().parent
DUMPS = STEALTH / "evidence" / "dumps"; DUMPS.mkdir(parents=True, exist_ok=True)
SWEEP = STEALTH / "evidence" / "sweep"; SWEEP.mkdir(parents=True, exist_ok=True)
LIMIT = 40
BLOCK = ["datadome","captcha-delivery","geo.captcha","perimeterx","px-captcha","pardon our interruption",
         "_px","incapsula","_incap_","cf-chl","challenge-platform","attention required","access denied",
         "akamai","zugriff verweigert","unusual traffic","human verification","robot"]

# domain, country, warm, target(search), detail-URL regex (portal-specific)
WORK = [
  ("autoscout24.de","DE","https://www.autoscout24.de/","https://www.autoscout24.de/lst/?sort=age&desc=1&atype=C", r'href="(/angebote/[^"#?]+)"'),
  ("autoscout24.fr","FR","https://www.autoscout24.fr/","https://www.autoscout24.fr/lst/?sort=age&desc=1&atype=C", r'href="(/offres/[^"#?]+)"'),
  ("autoscout24.es","ES","https://www.autoscout24.es/","https://www.autoscout24.es/lst/?sort=age&desc=1&atype=C", r'href="(/ofertas/[^"#?]+)"'),
  ("autoscout24.nl","NL","https://www.autoscout24.nl/","https://www.autoscout24.nl/lst/?sort=age&desc=1&atype=C", r'href="(/aanbod/[^"#?]+)"'),
  ("autoscout24.be","BE","https://www.autoscout24.be/","https://www.autoscout24.be/nl/lst/?sort=age&desc=1&atype=C", r'href="(/(?:nl|fr)/aanbod/[^"#?]+|/(?:nl|fr)/offres/[^"#?]+)"'),
  ("autoscout24.it","IT","https://www.autoscout24.it/","https://www.autoscout24.it/lst/?sort=age&desc=1&atype=C", r'href="(/annunci/[^"#?]+)"'),
  ("kleinanzeigen.de","DE","https://www.kleinanzeigen.de/","https://www.kleinanzeigen.de/s-autos/c216", r'(/s-anzeige/[a-z0-9-]+/\d+[\d-]*)'),
  ("autoweek.nl","NL","https://www.autoweek.nl/","https://www.autoweek.nl/occasions/", r'(/occasions/[a-z0-9-]+/\d+/?)'),
  ("vlan.be","BE","https://www.vlan.be/","https://www.vlan.be/fr/voiture-occasion", r'(/[a-z]+/annonce[^"#?]*\d{4,})'),
  ("autoboerse.de","DE","https://www.autoboerse.de/","https://www.autoboerse.de/gebrauchtwagen", r'(/(?:fahrzeug|gebrauchtwagen)/[^"#?]*\d{4,})'),
  ("zoomcar.fr","FR","https://www.zoomcar.fr/","https://www.zoomcar.fr/recherche", r'(/[a-z-]*annonce[^"#?]*\d{4,})'),
  ("gocar.be","BE","https://www.gocar.be/","https://www.gocar.be/fr/occasions", r'(/[a-z/]*occasion[^"#?]*\d{4,})'),
  ("nederlandmobiel.nl","NL","https://www.nederlandmobiel.nl/","https://www.nederlandmobiel.nl/aanbod", r'(/(?:aanbod|occasion)[^"#?]*\d{4,})'),
  ("coches.com","ES","https://www.coches.com/","https://www.coches.com/coches-segunda-mano/", r'(/[^"#?]*-\d{6,}(?:\.aspx)?)'),
  ("ouestfrance-auto.fr","FR","https://www.ouestfrance-auto.com/","https://www.ouestfrance-auto.com/voiture-occasion/", r'(/voiture-occasion/[^"#?]*\d{4,})'),
  ("autowereld.nl","NL","https://www.autowereld.nl/","https://www.autowereld.nl/occasions/", r'(/occasion[^"#?]*\d{4,})'),
  ("promoneuve.fr","FR","https://www.promoneuve.fr/","https://www.promoneuve.fr/voiture-neuve", r'(/voiture[^"#?]*\d{4,})'),
]

def uh(u): return hashlib.sha256(u.encode("utf-8")).hexdigest()[:32]
def pint(v):
    if isinstance(v,(int,float)): return int(v) if v>0 else None
    if isinstance(v,str):
        d=re.sub(r"[^\d]","",v.split(",")[0].split(".")[0]); return int(d) if d else None
    return None
def pyear(v):
    m=re.search(r"\b(19[7-9]\d|20[0-2]\d)\b", str(v or "")); return int(m.group(1)) if m else None

def extract_jsonld(html, domain, country):
    recs={}
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.DOTALL|re.I):
        try: data=json.loads(m.group(1).strip())
        except Exception: continue
        stack=[data]
        while stack:
            o=stack.pop()
            if isinstance(o,list): stack.extend(o); continue
            if not isinstance(o,dict): continue
            t=str(o.get("@type","")).lower()
            if t in ("car","vehicle","product","offer","individualproduct") and (o.get("url") or o.get("@id") or o.get("name")):
                url=o.get("url") or o.get("@id")
                if not url or not isinstance(url,str):
                    stack.extend(o.values()); continue
                if url.startswith("/"): url=f"https://www.{domain}"+url
                offers=o.get("offers") or {}
                price=None
                if isinstance(offers,dict): price=offers.get("price") or offers.get("lowPrice")
                elif isinstance(offers,list) and offers: price=offers[0].get("price")
                h=uh(url)
                recs[h]={"url_hash":h,"source_url":url,"source_domain":domain,"country":country,
                         "title":(str(o.get("name") or "")[:300] or None),
                         "price_eur":pint(price),
                         "year":pyear(o.get("productionDate") or o.get("modelDate") or o.get("name")),
                         "mileage_km":pint((o.get("mileageFromOdometer") or {}).get("value") if isinstance(o.get("mileageFromOdometer"),dict) else None)}
            stack.extend(o.values())
    return recs

def extract_regex(html, rx, domain, country):
    recs={}
    for m in re.findall(rx, html):
        u=m if isinstance(m,str) else m[0]
        if u.startswith("/"): u=f"https://www.{domain}"+u
        if domain not in u: continue
        h=uh(u)
        recs[h]={"url_hash":h,"source_url":u,"source_domain":domain,"country":country,
                 "title":None,"price_eur":None,"year":None,"mileage_km":None}
        if len(recs)>=LIMIT*2: break
    return recs

def classify(status, html):
    low=html.lower(); hits=[s for s in BLOCK if s in low]
    if status and status>=400: return "BLOCKED", hits or [f"http{status}"]
    if hits and len(html)<35000: return "BLOCKED", hits
    return "OK", hits

def main():
    from camoufox.sync_api import Camoufox
    results={}
    with Camoufox(headless=True, humanize=True, geoip=True) as b:
        pg=b.new_page()
        for domain,country,warm,target,rx in WORK:
            r={"domain":domain,"country":country,"status":None,"verdict":None,"hits":[],"records":0,"method":None}
            try:
                pg.goto(warm, wait_until="domcontentloaded", timeout=60000); pg.wait_for_timeout(11000)
                resp=pg.goto(target, wait_until="domcontentloaded", timeout=60000); r["status"]=resp.status if resp else None
                pg.wait_for_timeout(7000)
                html=pg.content()
                v,hits=classify(r["status"], html); r["verdict"]=v; r["hits"]=hits[:4]
                if v=="OK":
                    recs=extract_jsonld(html, domain, country); r["method"]="jsonld" if recs else None
                    if len(recs)<3:
                        rg=extract_regex(html, rx, domain, country)
                        if len(rg)>len(recs): recs=rg; r["method"]="regex"
                    recs=dict(list(recs.items())[:LIMIT])
                    r["records"]=len(recs)
                    if recs:
                        (DUMPS/f"{domain}_harvest.jsonl").write_text(
                            "\n".join(json.dumps(x,ensure_ascii=False) for x in recs.values()),encoding="utf-8")
            except Exception as e:
                r["verdict"]="ERROR"; r["hits"]=[str(e)[:60]]
            results[domain]=r
            (SWEEP/"t1_marker.json").write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding="utf-8")
            print(f"[{domain}] status={r['status']} verdict={r['verdict']} method={r['method']} records={r['records']} hits={r['hits']}", flush=True)
        pg.close()
    (SWEEP/"t1_marker.json").write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding="utf-8")
    print("BROWSER_PHASE_DONE", flush=True)

if __name__=="__main__":
    main()
