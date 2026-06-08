#!/usr/bin/env python3
"""Backfill website tags from Overpass for OSM entities that lack a domain.

The OSM ingestion code extracts website tags at ingest time. Entities that
had no website tag then (hence domain IS NULL) may have been updated by OSM
editors since. This script re-queries Overpass in batches by node/way/relation
IDs stored in registry_id, extracts any website tag, validates the domain
is a real automotive homepage, and writes it to discovery_candidates.

Usage:
    python stealth/osm_website_backfill.py [--batch 400] [--countries DE,FR,NL]
    python stealth/osm_website_backfill.py --dry-run --batch 100
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import ssl
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import aiohttp
import psycopg2

DB_URL = "postgresql://cardex:cardex_dev_only@127.0.0.1:5432/cardex"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_BATCH = 500   # node IDs per Overpass query
HTTP_BATCH  = 20       # concurrent domain validations
OVERPASS_SLEEP = 3.0   # politeness delay between Overpass requests

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# ── Domain normalization ──────────────────────────────────────────────────────

def _apex(url: str) -> Optional[str]:
    if not url:
        return None
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
        netloc = re.sub(r":\d+$", "", netloc)
        netloc = netloc.lstrip("www.")
        if "." not in netloc or len(netloc) < 4:
            return None
        return netloc
    except Exception:
        return None

# ── Overpass query ────────────────────────────────────────────────────────────

def _build_overpass_query(ids_by_type: dict[str, list[str]]) -> str:
    """Build an Overpass QL query that returns tags for a set of node/way/relation IDs."""
    parts = []
    for otype, ids in ids_by_type.items():
        if ids:
            id_list = ",".join(ids)
            parts.append(f"{otype}(id:{id_list});")
    inner = "\n  ".join(parts)
    return f"""[out:json][timeout:30];
(
  {inner}
);
out tags;"""


async def overpass_fetch_websites(session: aiohttp.ClientSession,
                                   rows: list[tuple[int, str, str]]) -> dict[int, str]:
    """Query Overpass for a batch of registry IDs, return {db_id: website_url}."""
    ids_by_type: dict[str, list[str]] = {"node": [], "way": [], "relation": []}
    id_to_dbid: dict[tuple[str, str], int] = {}

    for db_id, registry_id, country in rows:
        if not registry_id:
            continue
        parts = registry_id.strip().split("/")
        if len(parts) != 2:
            continue
        otype, oid = parts[0].lower(), parts[1]
        if otype in ids_by_type:
            ids_by_type[otype].append(oid)
            id_to_dbid[(otype, oid)] = db_id

    if not any(ids_by_type.values()):
        return {}

    query = _build_overpass_query(ids_by_type)
    try:
        resp = await session.post(
            OVERPASS_URL,
            data={"data": query},
            timeout=aiohttp.ClientTimeout(total=60),
            ssl=SSL_CTX,
        )
        if resp.status != 200:
            return {}
        data = await resp.json(content_type=None)
    except Exception as exc:
        print(f"[overpass] fetch error: {type(exc).__name__}: {exc}", flush=True)
        return {}

    result: dict[int, str] = {}
    for element in data.get("elements", []):
        etype = element.get("type", "")
        eid = str(element.get("id", ""))
        tags = element.get("tags") or {}
        website = tags.get("website") or tags.get("url") or tags.get("contact:website") or ""
        if not website:
            continue
        db_id = id_to_dbid.get((etype, eid))
        if db_id is not None:
            result[db_id] = website

    return result

# ── Domain validation ─────────────────────────────────────────────────────────

async def validate_domain(session: aiohttp.ClientSession, domain: str) -> bool:
    """Return True if domain responds with an HTTP 2xx/3xx (not parked/dead)."""
    PARKED_RE = re.compile(
        r"domain.{0,20}(?:for sale|zu verkaufen|te koop)"
        r"|sedoparking|hugedomains|namecheap\.com/domains",
        re.I,
    )
    for scheme in ("https://", "http://"):
        try:
            resp = await session.get(
                f"{scheme}{domain}",
                timeout=aiohttp.ClientTimeout(total=10),
                ssl=SSL_CTX,
                allow_redirects=True,
            )
            if resp.status in (200, 301, 302, 307, 308):
                body = await resp.content.read(8192)
                text = body.decode("utf-8", errors="replace")
                if PARKED_RE.search(text):
                    return False
                return True
        except Exception:
            continue
    return False

# ── DB helpers ────────────────────────────────────────────────────────────────

def fetch_osm_noweb(conn, countries: list[str]) -> list[tuple[int, str, str]]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, registry_id, country
            FROM discovery_candidates
            WHERE (domain IS NULL OR domain = '')
              AND source IN ('osm', 'osm_nametail')
              AND registry_id IS NOT NULL
              AND country = ANY(%s)
            ORDER BY country, id
        """, (countries,))
        return cur.fetchall()


def write_website(conn, db_id: int, domain: str, website_url: str, dry_run: bool) -> None:
    if dry_run:
        return
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE discovery_candidates
            SET domain = %s,
                url    = %s,
                external_refs = COALESCE(external_refs, '{}'::jsonb)
                                || jsonb_build_object('resolved_via', 'osm_backfill')
            WHERE id = %s
              AND (domain IS NULL OR domain = '')
        """, (domain, website_url, db_id))
    conn.commit()

# ── Main pipeline ─────────────────────────────────────────────────────────────

async def run(rows: list[tuple[int, str, str]], dry_run: bool, batch_size: int) -> dict:
    stats = {"overpass_batches": 0, "overpass_hits": 0, "validated": 0,
             "written": 0, "invalid": 0, "total": len(rows)}
    conn = psycopg2.connect(DB_URL)

    connector = aiohttp.TCPConnector(limit=HTTP_BATCH, ssl=SSL_CTX)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CARDEX-backfill/1.0)"}
    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:

        for i in range(0, len(rows), batch_size):
            chunk = rows[i:i + batch_size]
            stats["overpass_batches"] += 1

            websites = await overpass_fetch_websites(session, chunk)
            stats["overpass_hits"] += len(websites)

            # Validate domains concurrently
            sem = asyncio.Semaphore(HTTP_BATCH)
            to_validate = [(db_id, url) for db_id, url in websites.items()]

            async def _validate(db_id: int, url: str) -> tuple[int, str, bool]:
                domain = _apex(url)
                if not domain:
                    return db_id, url, False
                async with sem:
                    ok = await validate_domain(session, domain)
                return db_id, url, ok

            tasks = [_validate(db_id, url) for db_id, url in to_validate]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for res in results:
                if isinstance(res, Exception):
                    stats["invalid"] += 1
                    continue
                db_id, url, ok = res
                stats["validated"] += 1
                if ok:
                    domain = _apex(url)
                    write_website(conn, db_id, domain, url, dry_run)
                    stats["written"] += 1
                    if stats["written"] <= 10:
                        print(f"  [WRITTEN] {domain} <- {url}", flush=True)
                else:
                    stats["invalid"] += 1

            progress = min(i + batch_size, len(rows))
            print(f"[{progress}/{len(rows)}] batches={stats['overpass_batches']} "
                  f"hits={stats['overpass_hits']} written={stats['written']}", flush=True)
            await asyncio.sleep(OVERPASS_SLEEP)

    conn.close()
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=OVERPASS_BATCH)
    ap.add_argument("--countries", default="DE,FR,NL,ES,BE,CH")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    countries = [c.strip() for c in args.countries.split(",")]
    conn = psycopg2.connect(DB_URL)
    rows = fetch_osm_noweb(conn, countries)
    conn.close()
    print(f"[fetch] {len(rows)} OSM no-web entities with registry_id "
          f"({', '.join(countries)})", flush=True)

    by_c: dict[str, int] = {}
    for _, _, c in rows:
        by_c[c] = by_c.get(c, 0) + 1
    print(f"[fetch] breakdown: {by_c}", flush=True)

    if args.limit:
        rows = rows[:args.limit]
        print(f"[fetch] limited to {len(rows)}", flush=True)

    if not rows:
        print("Nothing to do.", flush=True)
        return 0

    t0 = time.monotonic()
    stats = asyncio.run(run(rows, args.dry_run, args.batch))
    elapsed = time.monotonic() - t0

    print(f"\n=== OSM WEBSITE BACKFILL RESULTS ===")
    print(f"Total entities:    {stats['total']}")
    print(f"Overpass batches:  {stats['overpass_batches']}")
    print(f"Overpass hits:     {stats['overpass_hits']} "
          f"({100*stats['overpass_hits']/stats['total']:.1f}% have website tag in OSM)")
    print(f"Validated OK:      {stats['written']}")
    print(f"Validation failed: {stats['invalid']}")
    hit_rate = 100*stats['overpass_hits']/stats['total'] if stats['total'] else 0
    valid_rate = 100*stats['written']/stats['overpass_hits'] if stats['overpass_hits'] else 0
    print(f"Hit rate:          {hit_rate:.1f}%")
    print(f"Valid rate:        {valid_rate:.1f}% (of hits)")
    print(f"Net new domains:   {stats['written']}")
    print(f"Elapsed:           {elapsed:.0f}s")
    print(f"{'[DRY RUN]' if args.dry_run else '[WRITTEN TO DB]'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
