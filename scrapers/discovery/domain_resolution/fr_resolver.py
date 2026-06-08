"""
FR domain resolver — break the single-IP block with our OWN free proxy rotation.

France is the big pool (~563K no-web) but PagesJaunes answers 403/DataDome and the
search engines throttle from our single IP. The free fix (no paid proxies): a
self-refreshing pool of public free proxies VALIDATED to return 200 from PagesJaunes
(hard-evidence bypass), used ONLY for the blocked endpoint. The dealer's own homepage
is then validated DIRECT from our IP (small dealer sites are not IP-blocked), so the
anti-false-positive gate (word-boundary name + 6-lang non-dealer + strong auto) is
unchanged.

Data note: FR ``city`` holds the INSEE code, not the city name — the real city is the
token after the postcode in ``address`` (``95500 GONESSE``). ``derive_city`` recovers it
so the PagesJaunes query (name + city) actually matches.

RAM-safe (small batches, gc, bounded pool, low concurrency), idempotent (UPDATE-only,
``WHERE domain IS NULL`` + collision-merge), resumable (the ddg_attempts queue is the
cursor). Runs alongside the REST workers — SKIP LOCKED keeps claims disjoint.

    python -m scrapers.discovery.domain_resolution.fr_resolver --limit 0 --batch 20
"""
from __future__ import annotations

import argparse
import asyncio
import gc
import logging
import os
import re
import time
import urllib.parse
from dataclasses import dataclass, field

import asyncpg

from scrapers.discovery.domain_resolution import worker as W
from scrapers.discovery.domain_resolution.candidate import name_tokens, ranked_candidates
from scrapers.discovery.domain_resolution.directories import _pagesjaunes
from scrapers.discovery.domain_resolution.proxy_pool import RotatingPool
from scrapers.discovery.domain_resolution.validate import validate_domain

log = logging.getLogger("fr_resolver")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(),
                    format="%(asctime)s %(levelname)s [fr_resolver] %(message)s")

_DSN = W._DSN
_MAX_ATTEMPTS = int(os.environ.get("DOMRES_MAX_ATTEMPTS", "5"))
_PROXY_TRIES = int(os.environ.get("FR_PROXY_TRIES", "5"))
_VALIDATE_TOP = 3

_FR_CLAIM = f"""
WITH claimed AS (
    SELECT id FROM discovery_candidates
    WHERE domain IS NULL AND name IS NOT NULL AND country='FR'
      AND address IS NOT NULL AND address <> ''
      AND postcode IS NOT NULL AND postcode <> ''
      AND position(postcode IN address) > 0
      AND ddg_attempts < {_MAX_ATTEMPTS}
      AND (ddg_last_attempt IS NULL OR ddg_last_attempt < NOW() - INTERVAL '24 hours')
    ORDER BY ddg_last_attempt NULLS FIRST, first_seen
    LIMIT $1 FOR UPDATE SKIP LOCKED
)
UPDATE discovery_candidates SET ddg_last_attempt = NOW()
FROM claimed WHERE discovery_candidates.id = claimed.id
RETURNING discovery_candidates.id, discovery_candidates.name, discovery_candidates.city,
          discovery_candidates.address, discovery_candidates.postcode
"""

_CITY_TAIL = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ' \-]{2,40}")


def derive_city(address: str, postcode: str, city_field: str) -> str:
    """
    Real city name for the PagesJaunes query. FR ``city`` is the INSEE code, so prefer
    the token after the postcode in the address (``… 95500 GONESSE`` → ``GONESSE``);
    fall back to ``city`` only if it is non-numeric.
    """
    addr = (address or "").strip()
    pc = (postcode or "").strip()
    if pc and pc in addr:
        tail = addr.split(pc, 1)[1].strip()
        m = _CITY_TAIL.search(tail)   # first letter-run after the postcode (skips ", ")
        if m:
            city = m.group(0).strip(" -'")
            # drop a trailing country word
            for stop in ("ALLEMAGNE", "FRANCE", "BELGIQUE", "SUISSE", "ESPAGNE"):
                city = re.sub(rf"\b{stop}\b.*$", "", city, flags=re.I).strip()
            if len(city) >= 3:
                return city
    cf = (city_field or "").strip()
    return cf if cf and not cf.isdigit() else ""


@dataclass
class FRStats:
    attempted: int = 0
    resolved: int = 0
    collided: int = 0
    failed: int = 0
    no_city: int = 0
    by_via: dict = field(default_factory=dict)

    def bump(self, k: str) -> None:
        self.by_via[k] = self.by_via.get(k, 0) + 1


_SP_URL = "https://www.startpage.com/sp/search?query={q}"


async def _startpage_via(proxy_session, proxy_url: str, name: str, city: str, country: str) -> list[str]:
    """Startpage results via a proxy → ranked candidate apexes (or [])."""
    q = urllib.parse.quote(f"{name} {city}".strip())
    try:
        r = await proxy_session.get(_SP_URL.format(q=q), timeout=18, allow_redirects=True,
                                    proxies={"http": proxy_url, "https": proxy_url})
    except Exception:  # noqa: BLE001
        return []
    html = r.text or ""
    if int(getattr(r, "status_code", 0) or 0) != 200 or len(html) <= 1000:
        return []
    return [h for h, _ in ranked_candidates(html, name, country, top=_VALIDATE_TOP)]


async def _gather_candidates(proxy_session, rot: RotatingPool, name: str, city: str) -> tuple[str, list[str]]:
    """
    (via, candidate apexes) for one FR dealer, rotating over live proxies and trying BOTH
    PagesJaunes (directory) and Startpage (search) per proxy — first that yields wins.
    Free proxies often hand back a DataDome 200-challenge (empty parse), so we rotate
    through several; a transport fault drops that proxy from the pool.
    """
    for _ in range(_PROXY_TRIES):
        p = rot.get()
        if p is None:
            return "", []
        try:
            pj = await _pagesjaunes(proxy_session, name, city, proxy=p.url)
        except Exception:  # noqa: BLE001
            rot.mark_dead(p)
            continue
        if pj:
            return "directory:pagesjaunes", pj[:_VALIDATE_TOP]
        sp = await _startpage_via(proxy_session, p.url, name, city, "FR")
        if sp:
            return "search:startpage", sp
    return "", []


async def _resolve_one(pg, direct_session, proxy_session, rot, row, stats: FRStats) -> None:
    name = row["name"]
    # Require a distinctive name token (≥4 chars, not a brand/generic). A name like
    # "AXO AUTO" or bare "Renault" has none → it can only confirm by city coincidence,
    # which mis-matched a same-town landscaper live. Skip it (precision over recall).
    if not name_tokens(name):
        await pg.execute(W._MARK_FAIL_SQL, row["id"], "no_distinctive_name")
        stats.failed += 1
        stats.bump("fail:no_distinctive_name")
        return
    city = derive_city(row["address"], row["postcode"], row["city"])
    if not city:
        await pg.execute(W._MARK_FAIL_SQL, row["id"], "no_derivable_city")
        stats.failed += 1
        stats.no_city += 1
        return

    async def _fetch(url):  # homepage validation DIRECT (our IP — homes aren't blocked)
        return await direct_session.get(url, timeout=15, allow_redirects=True, verify=False)

    via, cands = await _gather_candidates(proxy_session, rot, name, city)

    resolved_host = None
    rejected = 0
    seen: set[str] = set()
    for host in cands[:_VALIDATE_TOP]:
        if not host or host in seen:
            continue
        seen.add(host)
        ok, _why = await validate_domain(host, name, city, _fetch, require_name=True)
        if ok:
            resolved_host = host
            break
        rejected += 1

    if not resolved_host:
        reason = f"candidates_rejected:{rejected}" if rejected else "no_candidates"
        await pg.execute(W._MARK_FAIL_SQL, row["id"], reason)
        stats.failed += 1
        stats.bump(f"fail:{reason.split(':')[0]}")
        return

    import json
    try:
        await pg.execute(W._PROMOTE_SQL, row["id"], resolved_host,
                         f"https://{resolved_host}/", json.dumps({"resolved_via": via}))
        stats.resolved += 1
        stats.bump(f"{via}:resolved")
        log.info("RESOLVED %s / %s -> %s", name[:36], city[:20], resolved_host)
    except asyncpg.UniqueViolationError:
        try:
            await pg.execute(W._COLLISION_MERGE_SQL, row["id"], resolved_host, "FR")
            stats.collided += 1
        except Exception as exc:  # noqa: BLE001
            await pg.execute(W._MARK_FAIL_SQL, row["id"], f"collision_err:{type(exc).__name__}"[:100])
            stats.failed += 1


async def run(*, limit: int = 0, batch: int = 20, concurrency: int = 3) -> FRStats:
    pg = await asyncpg.create_pool(_DSN, min_size=2, max_size=6)
    direct = W._make_session()
    proxy_session = W._make_session()
    # Pool validated by LIVENESS (a fast neutral 204), kept broad — a status-200 from
    # PagesJaunes can be a DataDome challenge page, so real-content filtering happens
    # per-dealer in _gather_candidates (PJ parse / Startpage rank), rotating proxies.
    rot = RotatingPool(target="https://www.google.com/generate_204",
                       ok_status=(204, 200), floor=20, sample=700)
    stats = FRStats()
    sem = asyncio.Semaphore(concurrency)
    t0 = time.monotonic()
    try:
        n = await rot.ensure(proxy_session)
        log.info("initial proxy pool: %d live proxies", n)
        if n == 0:
            log.warning("no live proxies at start — will retry per batch")
        while limit == 0 or stats.attempted < limit:
            take = batch if limit == 0 else min(batch, limit - stats.attempted)
            rows = await pg.fetch(_FR_CLAIM, take)
            if not rows:
                break
            stats.attempted += len(rows)

            async def _guard(r):
                async with sem:
                    await _resolve_one(pg, direct, proxy_session, rot, dict(r), stats)

            await asyncio.gather(*(_guard(r) for r in rows))
            await rot.ensure(proxy_session)   # keep the pool topped up between batches
            gc.collect()
            log.info("batch: attempted=%d resolved=%d collided=%d failed=%d pool=%d (%.0fs)",
                     stats.attempted, stats.resolved, stats.collided, stats.failed,
                     rot.size, time.monotonic() - t0)
        log.info("DONE attempted=%d resolved=%d collided=%d failed=%d by_via=%s",
                 stats.attempted, stats.resolved, stats.collided, stats.failed, stats.by_via)
        return stats
    finally:
        for s in (direct, proxy_session):
            try:
                await s.close()
            except Exception:  # noqa: BLE001
                pass
        await pg.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--concurrency", type=int, default=3)
    args = ap.parse_args()
    asyncio.run(run(limit=args.limit, batch=args.batch, concurrency=args.concurrency))


if __name__ == "__main__":
    main()
