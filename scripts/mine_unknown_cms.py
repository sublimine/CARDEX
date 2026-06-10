"""Mine the UNKNOWN cluster — which platforms hide behind unfingerprinted dealers?

Reads the probed-but-unfingerprinted dealers (``inventory_signals->>'cms'`` empty) from
``discovery_candidates``, fetches each homepage once, extracts platform markers
(``marker_mining``), and writes the ranked aggregation to JSON — the shortlist for new
``cms_fingerprint`` signatures + family recipes.

Signatures EVOLVE while stored verdicts do not (the 420-dealer NL run predated the
datamotive markers, leaving pouw.nl & co. unfingerprinted in DB), so the same network
pass also RE-FINGERPRINTS: when the CURRENT ``fingerprint_cms`` fires on a fetched
homepage, the fresh verdict is merged into ``inventory_signals`` (``--no-update-db``
to disable). Classification-state update of an already-probed row — the same contract
``inventory_probe.write_results`` established.

    DATABASE_URL=postgresql://cardex:cardex_dev_only@localhost:5432/cardex \
    python scripts/mine_unknown_cms.py --country NL --tiers T2,T3 --conc 10 \
        --out reports/unknown_cms_nl.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

import aiohttp
import asyncpg

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scrapers.dealer_scraping.cms_fingerprint import fingerprint_cms       # noqa: E402
from scrapers.dealer_scraping.inventory_probe import IN_SCOPE_SQL          # noqa: E402
from scrapers.dealer_scraping.marker_mining import (aggregate_markers,     # noqa: E402
                                                    extract_markers)

log = logging.getLogger("mine_unknown")
PG_DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36")
_MAX_HTML = 800_000   # bytes of homepage read per site — markers live early


async def _fetch_home(session: aiohttp.ClientSession, domain: str, timeout: int) -> str:
    for scheme in ("https", "http"):
        try:
            async with session.get(f"{scheme}://{domain}/",
                                   timeout=aiohttp.ClientTimeout(total=timeout),
                                   allow_redirects=True) as resp:
                if resp.status != 200:
                    continue
                raw = await resp.content.read(_MAX_HTML)
                return raw.decode("utf-8", "ignore")
        except Exception:  # noqa: BLE001 — a dead site is data, not an error
            continue
    return ""


async def run(*, country: str | None, tiers: list[str], conc: int, timeout: int,
              limit: int, out: str, update_db: bool) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    pg = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=4)
    q = ("SELECT domain, country, inventory_tier FROM discovery_candidates "
         "WHERE domain IS NOT NULL AND domain<>'' "
         "AND COALESCE(inventory_signals->>'cms','') = '' "
         "AND inventory_tier = ANY($1::text[]) "
         f"AND {IN_SCOPE_SQL} "
         "AND ($2::text IS NULL OR country=$2) "
         "ORDER BY country, md5(domain)")
    if limit:
        q += f" LIMIT {limit}"
    rows = await pg.fetch(q, tiers, country)
    log.info("mining %d unknown dealers (tiers=%s country=%s conc=%d update_db=%s)",
             len(rows), ",".join(tiers), country or "ALL", conc, update_db)

    connector = aiohttp.TCPConnector(limit=conc + 5, ssl=False, ttl_dns_cache=300)
    per_domain: dict[str, frozenset] = {}
    refingerprinted: list[tuple[str, str, str]] = []
    fetched = 0
    t0 = time.monotonic()
    sem = asyncio.Semaphore(conc)
    async with aiohttp.ClientSession(connector=connector, headers={"User-Agent": _UA}) as session:
        async def one(domain: str, cc: str) -> None:
            nonlocal fetched
            async with sem:
                html = await _fetch_home(session, domain, timeout)
            fetched += 1
            if html:
                per_domain[domain] = extract_markers(html, site_host=domain)
                verdict = fingerprint_cms(html)
                if verdict.cms != "unknown":
                    refingerprinted.append((domain, cc, verdict.cms))
                    if update_db:
                        await pg.execute(
                            "UPDATE discovery_candidates SET inventory_signals = "
                            "COALESCE(inventory_signals,'{}'::jsonb) || jsonb_build_object("
                            "'cms', $3::text, 'cms_confidence', $4::text, "
                            "'cms_signals', $5::jsonb) "
                            "WHERE domain=$1 AND country=$2",
                            domain, cc, verdict.cms, verdict.confidence,
                            json.dumps(list(verdict.signals)))
            if fetched % 50 == 0:
                log.info("…%d/%d fetched (%ds)", fetched, len(rows), int(time.monotonic() - t0))

        await asyncio.gather(*(one(r["domain"], r["country"]) for r in rows))
    await pg.close()

    ranked = aggregate_markers(per_domain, min_domains=2)
    refp_by_cms: dict[str, int] = {}
    for _, _, c in refingerprinted:
        refp_by_cms[c] = refp_by_cms.get(c, 0) + 1
    report = {
        "scope": {"country": country or "ALL", "tiers": tiers, "selected": len(rows),
                  "fetched_ok": len(per_domain), "min_domains": 2},
        "refingerprinted": {"total": len(refingerprinted), "by_cms": refp_by_cms,
                            "db_updated": update_db,
                            "domains": [{"domain": d, "country": c, "cms": m}
                                        for d, c, m in sorted(refingerprinted)]},
        "markers": ranked,
    }
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n===== UNKNOWN-CMS MINING =====")
    print(f"selected={len(rows)} fetched_ok={len(per_domain)} markers_ranked={len(ranked)}")
    print(f"refingerprinted={len(refingerprinted)} by_cms={json.dumps(refp_by_cms)} "
          f"db_updated={update_db}")
    print(f"report={out_path}")
    for m in ranked[:25]:
        print(f"  {m['domains']:>4}x  {m['kind']:<10} {m['value']}")


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default=None)
    ap.add_argument("--tiers", default="T2,T3", help="comma list of inventory tiers to mine")
    ap.add_argument("--conc", type=int, default=10)
    ap.add_argument("--timeout", type=int, default=15)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="reports/unknown_cms.json")
    ap.add_argument("--no-update-db", action="store_true",
                    help="report only — do not merge fresh CMS verdicts into inventory_signals")
    a = ap.parse_args()
    asyncio.run(run(country=a.country, tiers=[t.strip().upper() for t in a.tiers.split(",") if t.strip()],
                    conc=a.conc, timeout=a.timeout, limit=a.limit, out=a.out,
                    update_db=not a.no_update_db))
