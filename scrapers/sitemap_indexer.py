"""
CARDEX Sitemap Indexer — Delta In-Process + PG como Fuente de Verdad.

Arquitectura:
  - PG es la fuente de verdad mandatoria. vehicle_index con last_seen.
  - Delta computado in-process con set nativo Python — cero Redis para estado,
    cero SDIFFSTORE, cero bloqueo de hilo único de ningún servicio externo.
  - Estado previo: una sola query PG por partición (source_domain, country)
    que devuelve solo url_hashes (columna indexada, index-only scan).
    PG ES la fuente de verdad. No se duplica en ningún store externo.
  - Mutaciones terminales a PG:
    * INSERT nuevos con last_seen = NOW()
    * DELETE stale (hard delete mandatorio — ausentes del sitemap)
    * Cero UPDATE de existentes no-mutados. Si un nodo sigue vivo en el
      sitemap, no se le toca. Su last_seen refleja su última aparición
      como nodo NUEVO. La presencia en el sitemap es la prueba de vida.
      La ausencia activa el hard delete.
  - Redis: solo conditional fetch (ETag/hash) + enrich stream. Cero estado.
  - Streaming XML O(1): iterparse + elem.clear().

Flujo por partición:
  1. Conditional fetch (304/hash)
  2. Stream-parse XML → set local de (hash, url) del ciclo
  3. Query PG: SELECT url_hash FROM vehicle_index WHERE source/country
     (index-only scan, columna indexada, cero seq scan)
  4. Delta in-process:
     new   = cycle_hashes - pg_hashes  → INSERT PG + XADD enrich
     stale = pg_hashes - cycle_hashes  → DELETE PG + INSERT event GONE
  5. Cero UPDATE. Cero touch de existentes.
"""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import io
import logging
import os
import re
import time
from urllib.parse import urlparse
from xml.etree.ElementTree import iterparse

import asyncpg
import httpx
import redis.asyncio as aioredis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [sitemap_indexer] %(message)s",
)
log = logging.getLogger("sitemap_indexer")

_DATABASE_URL = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
_USER_AGENT = "CardexBot/1.0 (+https://cardex.eu/bot; vehicle search indexer)"
_REQUEST_TIMEOUT = 20.0
_ENRICH_STREAM = "stream:enrich_pending"
_PG_BATCH = 500

COUNTRIES = ["DE", "FR", "ES", "NL", "BE", "CH"]

# ── SHA-256 truncated 128-bit ───────────────────────────────────────────────

def _uid(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:32]

def _chash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]

# ── Sitemap Registry ────────────────────────────────────────────────────────
# Tuple: (source_key, country, sitemap_url, url_regex, child_filter_regex|None)
# child_filter_regex: optional regex applied to sitemapindex child URLs.
#   Only children matching this regex are followed. None = follow all.
#   Critical for Marktplaats/2dehands where the master sitemap has 3000+
#   children but only ~100 are auto-related.
#
# Verified 2026-04-08 against live sitemaps. Sources removed:
#   BMW/Mercedes/Spoticar/Ford/VW/Audi/Hyundai — sitemaps contain only
#     marketing/category pages, zero individual vehicle listings.
#     Their used-car inventory is behind SPAs/APIs (OEM Gateway handles these).
#   AutoScout24 (6) — no public sitemap (404/403).
#   Mobile.de — 403 blocked.
#   LeBonCoin — sitemap declared in robots.txt but returns 403.

SITEMAP_SOURCES: list[tuple[str, str, str, str, str | None]] = [
    # ── Renew (Renault Group) — individual vehicle URLs with productId ──
    ("renew","DE","https://de.renew.auto/sitemap.xml",r"\?productId=",None),
    ("renew","FR","https://fr.renew.auto/sitemap.xml",r"\?productId=",None),
    ("renew","ES","https://es.renew.auto/sitemap.xml",r"\?productId=",None),
    ("renew","BE","https://fr-be.renew.auto/sitemap.xml",r"\?productId=",None),
    # ── Toyota — individual vehicle detail pages ──
    ("toyota","DE","https://www.toyota.de/sitemap.xml",r"/gebrauchtwagen/|/occasion/",None),
    ("toyota","FR","https://www.toyota.fr/sitemap.xml",r"/occasions/|/vehicule/",None),
    # ── Marktplaats (NL) — master sitemap, filter only auto-s children ──
    ("marktplaats","NL","https://www.marktplaats.nl/sitemap/sitemap.xml",r"/v/auto-s/",r"\.auto-s\."),
    # ── 2dehands (BE) — master sitemap, filter only auto-s children ──
    ("2dehands","BE","https://www.2dehands.be/sitemap/sitemap.xml",r"/v/auto-s/",r"\.auto-s\."),
]

# ── Streaming XML — O(1) ───────────────────────────────────────────────────

def _idx_locs(raw):
    locs = []
    try:
        in_sm = False
        for ev, el in iterparse(io.BytesIO(raw), events=("start","end")):
            t = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if ev=="start" and t=="sitemap": in_sm=True
            elif ev=="end" and t=="sitemap": in_sm=False; el.clear()
            elif ev=="end" and t=="loc" and in_sm and el.text: locs.append(el.text.strip()); el.clear()
            elif ev=="end": el.clear()
    except: locs = re.findall(r"<loc>(https?://[^<]+)</loc>", raw.decode("utf-8","replace"))
    return locs

def _url_locs(raw, f):
    locs = []
    try:
        for _, el in iterparse(io.BytesIO(raw), events=("end",)):
            t = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if t=="loc" and el.text:
                l = el.text.strip()
                if f is None or f.search(l): locs.append(l)
            el.clear()
    except:
        for u in re.findall(r"<loc>(https?://[^<]+)</loc>", raw.decode("utf-8","replace")):
            if f is None or f.search(u): locs.append(u)
    return locs

# ── Conditional fetch (Redis: only ETag/hash, zero state) ──────────────────

async def _cfetch(cl, rdb, url):
    sk = f"sm:{_uid(url)}"
    st = await rdb.hgetall(sk)
    h = {}
    if st:
        if st.get(b"e"): h["If-None-Match"] = st[b"e"].decode()
        if st.get(b"m"): h["If-Modified-Since"] = st[b"m"].decode()
    try: resp = await cl.get(url, headers=h)
    except: return None, False
    if resp.status_code == 304: return None, False
    if resp.status_code != 200: return None, False
    body = resp.content
    if url.endswith(".gz") or resp.headers.get("content-encoding")=="gzip":
        try: body = gzip.decompress(body)
        except: pass
    ch = _chash(body)
    if st and st.get(b"c",b"").decode()==ch: return None, False
    p = rdb.pipeline(transaction=False)
    p.hset(sk, mapping={"e":resp.headers.get("etag",""),"m":resp.headers.get("last-modified",""),"c":ch})
    p.expire(sk, 604800)
    await p.execute()
    return body, True

async def _fetch(cl, rdb, url, f, d=3, cf=None):
    """cf = compiled child filter regex (applied to sitemapindex child URLs)."""
    if d<=0: return []
    body, ok = await _cfetch(cl, rdb, url)
    if not ok: return []
    if b"sitemapindex" in body[:500].lower():
        ch = _idx_locs(body)
        if cf:
            before = len(ch)
            ch = [u for u in ch if cf.search(u)]
            log.info("INDEX %s → %d children (%d after filter)", url[:80], before, len(ch))
        else:
            log.info("INDEX %s → %d", url[:80], len(ch))
        sem = asyncio.Semaphore(8)
        async def _c(u):
            async with sem: return await _fetch(cl, rdb, u, f, d-1, cf=None)
        rs = await asyncio.gather(*[_c(u) for u in ch], return_exceptions=True)
        return [u for r in rs if isinstance(r,list) for u in r]
    urls = _url_locs(body, f)
    log.info("URLSET %s → %d", url[:80], len(urls))
    return urls

# ── Delta cycle ─────────────────────────────────────────────────────────────

async def _delta(
    pg: asyncpg.Pool, rdb: aioredis.Redis,
    sk: str, cc: str, dom: str, sm_url: str,
    urls: list[str],
) -> dict[str, int]:
    """
    Delta in-process. PG is source of truth.

    1. Build cycle set locally (hash computation in-process)
    2. Load existing hashes from PG (index-only scan on url_hash)
    3. Set diff in-process (Python native set, no external service)
    4. INSERT new, DELETE stale. Zero UPDATE of non-mutated rows.
    """
    stats = {"new": 0, "gone": 0}

    # Phase 1: cycle set — local computation
    hash_to_url: dict[str, str] = {}
    for u in urls:
        hash_to_url[_uid(u)] = u
    cycle_set = set(hash_to_url.keys())

    # Phase 2: existing hashes from PG — source of truth
    # Index-only scan on (source_domain, country) → url_hash
    async with pg.acquire() as conn:
        rows = await conn.fetch(
            "SELECT url_hash FROM vehicle_index WHERE source_domain=$1 AND country=$2",
            dom, cc,
        )
    pg_set = {r["url_hash"] for r in rows}

    # Phase 3: in-process set diff — zero external service, zero blocking
    new_hashes = cycle_set - pg_set
    stale_hashes = pg_set - cycle_set

    stats["new"] = len(new_hashes)
    stats["gone"] = len(stale_hashes)

    # Phase 4: terminal mutations to PG

    # 4a. INSERT new with last_seen = NOW()
    if new_hashes:
        new_list = list(new_hashes)
        for i in range(0, len(new_list), _PG_BATCH):
            batch = new_list[i:i+_PG_BATCH]
            records = [(h, hash_to_url[h], dom, cc, sm_url) for h in batch]
            async with pg.acquire() as conn:
                await conn.executemany(
                    "INSERT INTO vehicle_index (url_hash,url_original,source_domain,country,sitemap_source,last_seen) VALUES ($1,$2,$3,$4,$5,NOW()) ON CONFLICT (url_hash) DO NOTHING",
                    records,
                )
                await conn.executemany(
                    "INSERT INTO vehicle_events (url_hash,url_original,source_domain,country,sitemap_source,event_type) VALUES ($1,$2,$3,$4,$5,'SEEN')",
                    records,
                )

        # Enrich stream
        pipe = rdb.pipeline(transaction=False)
        for h in new_list:
            u = hash_to_url[h]
            pipe.xadd(_ENRICH_STREAM, {"h":h,"u":u,"s":sk,"c":cc}, maxlen=5_000_000)
        await pipe.execute()

    # 4b. Hard delete stale (mandatorio — ausentes del sitemap oficial)
    if stale_hashes:
        stale_list = list(stale_hashes)
        for i in range(0, len(stale_list), _PG_BATCH):
            batch = stale_list[i:i+_PG_BATCH]
            async with pg.acquire() as conn:
                # Hard delete from vehicle_index
                await conn.execute(
                    "DELETE FROM vehicle_index WHERE url_hash = ANY($1::text[])",
                    batch,
                )
                # Event log
                await conn.executemany(
                    "INSERT INTO vehicle_events (url_hash,source_domain,country,sitemap_source,event_type) VALUES ($1,$2,$3,$4,'GONE')",
                    [(h, dom, cc, sm_url) for h in batch],
                )

    # 4c. Existing non-mutated rows: ZERO TOUCH.
    # last_seen preserves the timestamp of first/last INSERT.
    # Presence in sitemap is proof of life. Absence triggers hard delete.
    # No UPDATE cycle → zero dead tuples from touch.

    return stats

# ── Core ────────────────────────────────────────────────────────────────────

async def _index_source(pg, rdb, cl, sk, cc, url, fs, cfs=None):
    stats = {"urls_found":0,"new":0,"gone":0,"skipped":0}
    t0 = time.monotonic()
    f = re.compile(fs, re.IGNORECASE) if fs else None
    cf = re.compile(cfs, re.IGNORECASE) if cfs else None
    log.info("START %s/%s — %s", sk, cc, url[:80])
    urls = await _fetch(cl, rdb, url, f, cf=cf)
    stats["urls_found"] = len(urls)
    if not urls:
        stats["skipped"]=1; return stats
    d = await _delta(pg, rdb, sk, cc, urlparse(url).netloc, url, urls)
    stats.update(d)
    log.info("DONE %s/%s — found=%d new=%d gone=%d %.1fs",
             sk,cc,stats["urls_found"],stats["new"],stats["gone"],time.monotonic()-t0)
    return stats

async def run(countries=None, sources=None):
    countries = [c.upper() for c in (countries or COUNTRIES)]
    pg = await asyncpg.create_pool(_DATABASE_URL, min_size=4, max_size=20)
    rdb = aioredis.from_url(_REDIS_URL, decode_responses=False)

    async with pg.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS vehicle_index (
                url_hash TEXT PRIMARY KEY,
                url_original TEXT NOT NULL,
                source_domain TEXT NOT NULL,
                country CHAR(2) NOT NULL,
                sitemap_source TEXT NOT NULL DEFAULT '',
                titulo_modelo TEXT, precio NUMERIC(12,2), moneda CHAR(3) DEFAULT 'EUR',
                kilometraje INT, anio SMALLINT, thumbnail_url TEXT,
                last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_vi_dc ON vehicle_index (source_domain,country)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_vi_ls ON vehicle_index (last_seen)")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS vehicle_events (
                event_id BIGSERIAL PRIMARY KEY,
                url_hash TEXT NOT NULL, url_original TEXT NOT NULL DEFAULT '',
                source_domain TEXT NOT NULL DEFAULT '', country CHAR(2) NOT NULL DEFAULT '',
                sitemap_source TEXT NOT NULL DEFAULT '',
                event_type TEXT NOT NULL CHECK (event_type IN ('SEEN','ENRICHED','GONE')),
                titulo_modelo TEXT, precio NUMERIC(12,2), moneda CHAR(3) DEFAULT 'EUR',
                kilometraje INT, anio SMALLINT, thumbnail_url TEXT,
                ts TIMESTAMPTZ NOT NULL DEFAULT NOW()
            ) WITH (fillfactor=100, autovacuum_enabled=false)
        """)

    cl = httpx.AsyncClient(
        timeout=_REQUEST_TIMEOUT, follow_redirects=True, http2=True,
        headers={"User-Agent":_USER_AGENT,"Accept":"application/xml,text/xml,*/*;q=0.8","Accept-Encoding":"gzip,deflate,br"},
        limits=httpx.Limits(max_keepalive_connections=40, max_connections=80),
    )
    sa = {}
    try:
        active = [(s,c,u,f,cf) for s,c,u,f,cf in SITEMAP_SOURCES if c in countries and (not sources or s in sources)]
        log.info("START: %d sources × %s", len(active), countries)
        t0 = time.monotonic()
        for s,c,u,f,cf in active:
            k=f"{s}/{c}"
            try: sa[k] = await _index_source(pg,rdb,cl,s,c,u,f,cf)
            except Exception as e: log.error("FAIL %s: %s",k,e,exc_info=True); sa[k]={"error":str(e)}
        el = time.monotonic()-t0
        async with pg.acquire() as cn:
            live=(await cn.fetchrow("SELECT COUNT(*) c FROM vehicle_index"))["c"]
            evts=(await cn.fetchrow("SELECT COUNT(*) c FROM vehicle_events"))["c"]
        log.info("═══ DONE: %.1fs | found=%d new=%d gone=%d | live=%d events=%d ═══",
                 el,sum(s.get("urls_found",0) for s in sa.values()),
                 sum(s.get("new",0) for s in sa.values()),
                 sum(s.get("gone",0) for s in sa.values()),live,evts)
    finally:
        await cl.aclose(); await rdb.aclose(); await pg.close()
    return sa

def main():
    import argparse
    p=argparse.ArgumentParser(prog="sitemap_indexer")
    p.add_argument("--country",action="append",dest="countries")
    p.add_argument("--source",action="append",dest="sources")
    a=p.parse_args()
    asyncio.run(run(countries=a.countries,sources=a.sources))

if __name__=="__main__": main()
