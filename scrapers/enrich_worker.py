"""
CARDEX Enrich Worker — INSERT inmutable a event log + CH columnar.

Consume stream:enrich_pending. Extrae JSON-LD/OG de HTML estático.
PG: INSERT evento ENRICHED (append-only, cero mutación).
CH: INSERT fila con metadatos + is_active=1 (ReplacingMergeTree colapsa
    con la fila SEEN previa en merge background — O(1) amortizado).
Cero UPDATE. Cero DELETE. Cero dead tuples.

Uso: python -m scrapers.enrich_worker
"""
from __future__ import annotations
import asyncio, json, logging, os, re, time
import asyncpg, httpx, redis.asyncio as aioredis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [enrich] %(message)s")
log = logging.getLogger("enrich")

_DB = os.environ.get("DATABASE_URL","postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_RD = os.environ.get("REDIS_URL","redis://localhost:6379")
_CH = os.environ.get("CLICKHOUSE_URL","http://localhost:8123")
_CH_U = os.environ.get("CLICKHOUSE_USER","default")
_CH_P = os.environ.get("CLICKHOUSE_PASSWORD","")
_STREAM = "stream:enrich_pending"
_GROUP = "cg_enrich"
_CONS = os.environ.get("ENRICH_CONSUMER_NAME",f"w-{os.getpid()}")
_BATCH = int(os.environ.get("ENRICH_BATCH_SIZE","50"))
_CONC = int(os.environ.get("ENRICH_CONCURRENCY","20"))
_UA = "CardexBot/1.0 (+https://cardex.eu/bot; enricher)"

_YR = re.compile(r"\b(19|20)\d{2}\b")
_KM = re.compile(r"([\d.,]+)\s*(?:km|KM|Km|kilo)", re.IGNORECASE)

def _mc(h,n):
    for p in [rf'<meta\s+(?:name|property)\s*=\s*["\']'+re.escape(n)+r'["\']\s+content\s*=\s*["\']([^"\']*)["\']',
              rf'<meta\s+content\s*=\s*["\']([^"\']*)["\'][\s]+(?:name|property)\s*=\s*["\']'+re.escape(n)+r'["\']']:
        m = re.search(p,h,re.IGNORECASE)
        if m: return m.group(1).strip()
    return ""

def _ext(html):
    r = {}
    for b in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',html,re.DOTALL|re.IGNORECASE):
        try:
            d = json.loads(b)
            for it in (d if isinstance(d,list) else [d]):
                if not isinstance(it,dict): continue
                t = it.get("@type",""); ts = t if isinstance(t,list) else [t]
                if not any(x in ("Car","Vehicle","Product","Offer","IndividualProduct") for x in ts): continue
                r["t"] = it.get("name","") or it.get("model","") or it.get("vehicleConfiguration","")
                o = it.get("offers",it)
                if isinstance(o,list): o = o[0] if o else {}
                if isinstance(o,dict):
                    p = o.get("price") or o.get("lowPrice")
                    if p:
                        try: r["p"] = float(str(p).replace(",","").replace(" ",""))
                        except: pass
                    r["m"] = o.get("priceCurrency","EUR")
                km = it.get("mileageFromOdometer")
                if isinstance(km,dict): km = km.get("value")
                if km:
                    try: r["k"] = int(float(str(km).replace(",","").replace(".","")))
                    except: pass
                y = it.get("modelDate") or it.get("vehicleModelDate") or it.get("productionDate") or it.get("dateVehicleFirstRegistered")
                if y:
                    ym = _YR.search(str(y))
                    if ym: r["y"] = int(ym.group())
                img = it.get("image")
                if isinstance(img,list): img = img[0] if img else ""
                if isinstance(img,dict): img = img.get("url",img.get("contentUrl",""))
                if img and isinstance(img,str): r["i"] = img
                if r.get("t"): return r
        except: continue
    ot=_mc(html,"og:title"); oi=_mc(html,"og:image"); od=_mc(html,"og:description")
    if ot and not r.get("t"): r["t"]=ot
    if oi and not r.get("i"): r["i"]=oi
    if not r.get("t"):
        m=re.search(r"<title[^>]*>([^<]+)</title>",html,re.IGNORECASE)
        if m: r["t"]=m.group(1).strip()
    if not r.get("p"):
        v=_mc(html,"product:price:amount") or _mc(html,"og:price:amount")
        if v:
            try: r["p"]=float(v.replace(",","").replace(" ",""))
            except: pass
    if not r.get("k") and od:
        m=_KM.search(od)
        if m:
            try: r["k"]=int(m.group(1).replace(".","").replace(",",""))
            except: pass
    if not r.get("y"):
        m=_YR.search(r.get("t","")+" "+(od or ""))
        if m:
            v=int(m.group())
            if 1990<=v<=2027: r["y"]=v
    return r

def _esc(s): return (s or "").replace("\t"," ").replace("\n"," ")

async def _do(http_cl, ch_cl, pg, sem, h, u, s, c):
    async with sem:
        try: resp = await http_cl.get(u)
        except: return False
        meta = _ext(resp.text) if resp.status_code==200 else {}
        if not meta.get("t"): return False

        # PG: append ENRICHED event (blind, immutable)
        await pg.execute(
            "INSERT INTO vehicle_events (url_hash,url_original,source_domain,country,event_type,titulo_modelo,precio,moneda,kilometraje,anio,thumbnail_url) VALUES ($1,$2,'',$3,'ENRICHED',$4,$5,$6,$7,$8,$9)",
            h, u, c, meta.get("t"), meta.get("p"), meta.get("m","EUR"), meta.get("k"), meta.get("y"), meta.get("i"),
        )

        # CH: INSERT enriched row — ReplacingMergeTree collapses with SEEN row on merge
        tsv = "url_hash\turl_original\tsource_domain\tcountry\ttitulo_modelo\tprecio\tmoneda\tkilometraje\tanio\tthumbnail_url\tis_active\n"
        tsv += f"{h}\t{_esc(u)}\t\t{c}\t{_esc(meta.get('t',''))}\t{meta.get('p',0)}\t{meta.get('m','EUR')}\t{meta.get('k',0)}\t{meta.get('y',0)}\t{_esc(meta.get('i',''))}\t1"
        await ch_cl.post(_CH, content=tsv,
            headers={"Content-Type":"text/tab-separated-values"},
            params={"user":_CH_U,"password":_CH_P,"query":"INSERT INTO cardex.vehicle_pointers FORMAT TabSeparatedWithNames"})
        return True

async def run():
    pg = await asyncpg.create_pool(_DB, min_size=2, max_size=10)
    rdb = aioredis.from_url(_RD, decode_responses=True)
    http_cl = httpx.AsyncClient(timeout=12, follow_redirects=True, http2=True,
        headers={"User-Agent":_UA,"Accept":"text/html,*/*;q=0.8","Accept-Encoding":"gzip,deflate,br"},
        limits=httpx.Limits(max_keepalive_connections=30, max_connections=60))
    ch_cl = httpx.AsyncClient(timeout=15)

    try: await rdb.xgroup_create(_STREAM,_GROUP,id="0",mkstream=True)
    except: pass
    sem = asyncio.Semaphore(_CONC)
    log.info("started consumer=%s batch=%d",_CONS,_BATCH)
    try:
        while True:
            ent = await rdb.xreadgroup(_GROUP,_CONS,{_STREAM:">"},count=_BATCH,block=5000)
            if not ent: continue
            t0=time.monotonic(); tasks=[]; ids=[]
            for _,msgs in ent:
                for mid,f in msgs:
                    if f.get("h") and f.get("u"):
                        tasks.append(_do(http_cl,ch_cl,pg,sem,f["h"],f["u"],f.get("s",""),f.get("c","")))
                        ids.append(mid)
            if tasks:
                rs = await asyncio.gather(*tasks, return_exceptions=True)
                if ids: await rdb.xack(_STREAM,_GROUP,*ids)
                log.info("%d done %d enriched %.1fs",len(tasks),sum(1 for r in rs if r is True),time.monotonic()-t0)
    finally:
        await http_cl.aclose(); await ch_cl.aclose(); await rdb.aclose(); await pg.close()

def main(): asyncio.run(run())
if __name__=="__main__": main()
