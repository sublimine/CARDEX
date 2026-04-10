"""
Sitemap-first resolver worker.

Consumes `discovery_candidates` rows where a domain is known but its
sitemap status is still `pending`. For each domain:

    1. GET https://{domain}/robots.txt  — extract Sitemap: directives
    2. If no robots.txt sitemap, probe the standard fallback paths:
       /sitemap.xml, /sitemap_index.xml, /sitemap-index.xml, /sitemap.xml.gz
    3. Validate each candidate sitemap URL by fetching the first 64 KiB and
       checking for <urlset> or <sitemapindex> root elements. Handles gzip.
    4. First match wins; the row is stamped with `sitemap_status='found'`
       and `sitemap_url=<winning url>`. Otherwise `sitemap_status='none'`.
       Network/HTTP failures land the row in `sitemap_status='error'` with
       a short reason in `sitemap_error`.

Claim protocol
--------------
To run N workers in parallel without collisions, the resolver uses an
atomic CTE claim:

    WITH claimed AS (
        SELECT id FROM discovery_candidates
        WHERE sitemap_status = 'pending' AND domain IS NOT NULL
        ORDER BY first_seen
        LIMIT $1
        FOR UPDATE SKIP LOCKED
    )
    UPDATE discovery_candidates
        SET sitemap_status = 'probing', sitemap_probed_at = NOW()
    FROM claimed
    WHERE discovery_candidates.id = claimed.id
    RETURNING discovery_candidates.id, discovery_candidates.domain;

`probing` is a short-lived state; rows stuck in it for > 15 min are
reclaimed on worker startup (crash recovery).

Usage
-----
    python -m scrapers.discovery.sitemap_resolver

Environment
-----------
    DATABASE_URL                postgresql://...
    SITEMAP_RESOLVER_BATCH      rows per claim (default 50)
    SITEMAP_RESOLVER_CONCURRENCY in-flight probes per batch (default 20)
    SITEMAP_RESOLVER_IDLE_SLEEP  seconds to sleep when queue empty (default 30)
    SITEMAP_RESOLVER_ONESHOT     if '1', exit when queue is empty
"""
from __future__ import annotations

import asyncio
import gzip
import logging
import os
import re
from typing import Awaitable

import asyncpg
import httpx

log = logging.getLogger(__name__)

_DEFAULT_DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://cardex:cardex@localhost:5432/cardex",
)

_BATCH_SIZE = int(os.environ.get("SITEMAP_RESOLVER_BATCH", "50"))
_CONCURRENCY = int(os.environ.get("SITEMAP_RESOLVER_CONCURRENCY", "20"))
_IDLE_SLEEP = float(os.environ.get("SITEMAP_RESOLVER_IDLE_SLEEP", "30"))
_ONESHOT = os.environ.get("SITEMAP_RESOLVER_ONESHOT", "0") == "1"

_PROBE_TIMEOUT = 10.0
_STALE_CLAIM_INTERVAL = "15 minutes"

_FALLBACK_PATHS: tuple[str, ...] = (
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/sitemap.xml.gz",
)

_HEADERS = {
    "User-Agent": "CARDEX-DiscoveryResolver/1.0 (+ops@cardex.io)",
    "Accept": "text/xml, application/xml, text/plain, */*;q=0.5",
    "Accept-Encoding": "gzip, deflate",
}

_VALIDATE_BYTES = 65_536
_RE_ROBOTS_SITEMAP = re.compile(r"(?im)^\s*sitemap\s*:\s*(\S+)\s*$")

# ── SQL ──────────────────────────────────────────────────────────────────────

_RECLAIM_STALE_SQL = f"""
UPDATE discovery_candidates
SET sitemap_status = 'pending'
WHERE sitemap_status = 'probing'
  AND sitemap_probed_at < NOW() - INTERVAL '{_STALE_CLAIM_INTERVAL}'
"""

_CLAIM_BATCH_SQL = """
WITH claimed AS (
    SELECT id
    FROM discovery_candidates
    WHERE sitemap_status = 'pending' AND domain IS NOT NULL
    ORDER BY first_seen
    LIMIT $1
    FOR UPDATE SKIP LOCKED
)
UPDATE discovery_candidates
    SET sitemap_status = 'probing', sitemap_probed_at = NOW()
FROM claimed
WHERE discovery_candidates.id = claimed.id
RETURNING discovery_candidates.id, discovery_candidates.domain
"""

_FINALIZE_SQL = """
UPDATE discovery_candidates
SET sitemap_status = $2,
    sitemap_url    = $3,
    sitemap_error  = $4,
    sitemap_probed_at = NOW()
WHERE id = $1
"""


# ── Probing ──────────────────────────────────────────────────────────────────

async def _probe(
    client: httpx.AsyncClient,
    domain: str,
) -> tuple[str, str | None, str | None]:
    """
    Probe one domain. Returns (status, sitemap_url, error).

    status ∈ {'found', 'none', 'error'}
    """
    robots_url = f"https://{domain}/robots.txt"
    robots_text: str | None = None
    transient_error: str | None = None

    try:
        r = await client.get(robots_url, headers=_HEADERS, timeout=_PROBE_TIMEOUT)
        if r.status_code == 200:
            robots_text = r.text
        elif r.status_code in (301, 302, 303, 307, 308):
            # follow_redirects should handle this; defensive fallback
            robots_text = None
        elif 500 <= r.status_code < 600:
            transient_error = f"robots_http_{r.status_code}"
    except httpx.TimeoutException:
        transient_error = "robots_timeout"
    except httpx.ConnectError:
        transient_error = "robots_conn_refused"
    except httpx.HTTPError as exc:
        transient_error = f"robots_http_err:{type(exc).__name__}"

    # Collect sitemap URLs declared in robots.txt, then add fallbacks.
    candidates: list[str] = []
    if robots_text:
        for m in _RE_ROBOTS_SITEMAP.finditer(robots_text):
            url = m.group(1).strip()
            if url and url not in candidates:
                candidates.append(url)
    for path in _FALLBACK_PATHS:
        url = f"https://{domain}{path}"
        if url not in candidates:
            candidates.append(url)

    any_probe_attempted = False
    first_network_error: str | None = None

    for sm_url in candidates:
        try:
            ok = await _validate_sitemap(client, sm_url)
            any_probe_attempted = True
            if ok:
                return "found", sm_url, None
        except _NetworkError as exc:
            if first_network_error is None:
                first_network_error = str(exc)
            continue

    if any_probe_attempted:
        return "none", None, None

    # Nothing was reachable.
    err = transient_error or first_network_error or "no_sitemap_reachable"
    return "error", None, err[:200]


class _NetworkError(Exception):
    pass


async def _validate_sitemap(client: httpx.AsyncClient, url: str) -> bool:
    """Fetch up to 64 KiB and confirm root tag looks like a sitemap."""
    try:
        async with client.stream(
            "GET",
            url,
            headers=_HEADERS,
            timeout=_PROBE_TIMEOUT,
        ) as resp:
            if resp.status_code != 200:
                return False

            ctype = (resp.headers.get("content-type") or "").lower()
            buf = bytearray()
            async for chunk in resp.aiter_bytes():
                buf.extend(chunk)
                if len(buf) >= _VALIDATE_BYTES:
                    break
    except httpx.TimeoutException as exc:
        raise _NetworkError(f"timeout:{url.split('/', 3)[-1][:60]}") from exc
    except httpx.ConnectError as exc:
        raise _NetworkError("conn_refused") from exc
    except httpx.HTTPError as exc:
        raise _NetworkError(f"http_err:{type(exc).__name__}") from exc

    data = bytes(buf[:_VALIDATE_BYTES])

    # Try gzip if URL hints or content-type suggests it.
    if url.endswith(".gz") or "gzip" in ctype:
        try:
            data = gzip.decompress(data + b"\x00" * 0)[:_VALIDATE_BYTES]
        except Exception:
            # Fall through; maybe it's plain XML despite extension.
            pass

    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return False

    return ("<urlset" in text) or ("<sitemapindex" in text)


# ── Worker loop ──────────────────────────────────────────────────────────────

async def _finalize(pool: asyncpg.Pool, row_id: int, status: str,
                    sm_url: str | None, err: str | None) -> None:
    await pool.execute(_FINALIZE_SQL, row_id, status, sm_url, err)


async def _process_batch(
    pool: asyncpg.Pool,
    client: httpx.AsyncClient,
    batch: list[asyncpg.Record],
) -> dict[str, int]:
    sem = asyncio.Semaphore(_CONCURRENCY)
    counts = {"found": 0, "none": 0, "error": 0}

    async def _one(row: asyncpg.Record) -> None:
        async with sem:
            try:
                status, sm_url, err = await _probe(client, row["domain"])
            except Exception as exc:
                status, sm_url, err = "error", None, f"probe_exc:{type(exc).__name__}"[:200]
            counts[status] = counts.get(status, 0) + 1
            await _finalize(pool, row["id"], status, sm_url, err)

    await asyncio.gather(*(_one(r) for r in batch))
    return counts


async def _claim_batch(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    return await pool.fetch(_CLAIM_BATCH_SQL, _BATCH_SIZE)


async def run() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    pool = await asyncpg.create_pool(
        _DEFAULT_DSN, min_size=2, max_size=6, command_timeout=60,
    )
    log.info(
        "sitemap_resolver: starting — batch=%d concurrency=%d oneshot=%s",
        _BATCH_SIZE, _CONCURRENCY, _ONESHOT,
    )

    # Crash recovery: unwedge stale 'probing' rows from a previous crashed run.
    reclaimed = await pool.execute(_RECLAIM_STALE_SQL)
    if reclaimed:
        log.info("sitemap_resolver: reclaimed stale 'probing' rows: %s", reclaimed)

    totals = {"found": 0, "none": 0, "error": 0}

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=_PROBE_TIMEOUT,
            limits=httpx.Limits(
                max_keepalive_connections=_CONCURRENCY,
                max_connections=_CONCURRENCY * 2,
            ),
        ) as client:
            while True:
                batch = await _claim_batch(pool)
                if not batch:
                    if _ONESHOT:
                        log.info("sitemap_resolver: queue empty, oneshot exit")
                        break
                    log.debug("sitemap_resolver: queue empty, sleeping %.0fs", _IDLE_SLEEP)
                    await asyncio.sleep(_IDLE_SLEEP)
                    continue

                counts = await _process_batch(pool, client, batch)
                for k, v in counts.items():
                    totals[k] = totals.get(k, 0) + v
                log.info(
                    "sitemap_resolver: batch=%d  found=%d none=%d error=%d  totals=%d/%d/%d",
                    len(batch), counts["found"], counts["none"], counts["error"],
                    totals["found"], totals["none"], totals["error"],
                )
    finally:
        await pool.close()

    log.info(
        "sitemap_resolver: stopped — totals found=%d none=%d error=%d",
        totals["found"], totals["none"], totals["error"],
    )


if __name__ == "__main__":
    asyncio.run(run())
