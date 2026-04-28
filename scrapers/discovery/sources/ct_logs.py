"""
Certificate Transparency log miner — crt.sh Postgres direct.

crt.sh publishes a free public Postgres read replica at
    postgresql://guest@crt.sh:5432/certwatch
No authentication, no rate limits worth worrying about at our volumes.
This is 10× more reliable than the HTTP API which serves stale 502/empty
responses under load.

Per-country keyword matrix: see _KEYWORDS_BY_COUNTRY.

Usage:
    python -m scrapers.discovery.sources.ct_logs
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

import asyncpg

log = logging.getLogger("ct_logs")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [ct_logs] %(message)s",
)

_DSN = os.environ.get(
    "DATABASE_URL",
    "postgres://cardex:cardex_dev_only@localhost:5432/cardex",
)

_CRT_DSN = "postgresql://guest@crt.sh:5432/certwatch"

_KEYWORDS_BY_COUNTRY: dict[str, tuple[str, ...]] = {
    "DE": (
        "autohaus", "autohandel", "automobile", "gebrauchtwagen",
        "kfz", "autowelt", "fahrzeug", "autohof",
        "autozentrum", "automobil", "autocenter", "auto-",
    ),
    "FR": (
        "garage", "automobile", "voiture", "occasion",
        "concessionnaire", "vehicule", "auto-", "carrosserie",
        "autocentre",
    ),
    "ES": (
        "coches", "automocion", "concesionario", "vehiculos",
        "autocasion", "autoventa", "automoviles",
        "talleres",
    ),
    "NL": (
        "autobedrijf", "occasion", "autohandel", "automobielen",
        "tweedehands", "autocentrum",
    ),
    "BE": (
        "autobedrijf", "garage", "automobile", "carrosserie",
        "occasion",
    ),
    "CH": (
        "garage", "automobile", "occasion", "autohaus",
        "fahrzeug", "autohof", "autozentrum",
    ),
}

_TLDS_BY_COUNTRY: dict[str, tuple[str, ...]] = {
    "DE": ("de",),
    "FR": ("fr",),
    "ES": ("es",),
    "NL": ("nl",),
    "BE": ("be",),
    "CH": ("ch",),
}

# Concurrency must be conservative to not overload crt.sh guest instance
_CONC = int(os.environ.get("CT_CONC", "2"))
_QUERY_LIMIT = int(os.environ.get("CT_QUERY_LIMIT", "50000"))
_TIMEOUT = float(os.environ.get("CT_TIMEOUT", "180"))


def _apex_domain(name: str, tld: str) -> str | None:
    n = (name or "").strip().lower()
    if not n or n.startswith("*."):
        n = n[2:]
    if n.startswith("*") or " " in n or "\n" in n:
        return None
    parts = n.split(".")
    if len(parts) < 2:
        return None
    if parts[-1] != tld:
        return None
    return ".".join(parts[-2:])


async def _query_crt_pg(
    keyword: str,
    tld: str,
) -> list[str]:
    """Query crt.sh Postgres for keyword+TLD, return apex domains.
    Uses FTS index + ILIKE filter per crt.sh SQL cookbook."""
    pattern = f"%{keyword}%.{tld}"
    try:
        conn = await asyncpg.connect(
            _CRT_DSN, ssl="prefer", timeout=30, statement_cache_size=0,
        )
    except Exception as exc:
        log.warning("crt.sh connect failed %s/%s: %s", keyword, tld, exc)
        return []

    try:
        await conn.execute("SET statement_timeout='300s'")
        sql = (
            "SELECT DISTINCT lower(ci.NAME_VALUE) AS d "
            "FROM certificate_and_identities ci "
            "WHERE plainto_tsquery('certwatch', '" + keyword.replace("'", "''") + "') "
            "      @@ identities(ci.CERTIFICATE) "
            "AND ci.NAME_VALUE ILIKE '" + pattern.replace("'", "''") + "' "
            f"LIMIT {_QUERY_LIMIT}"
        )
        rows = await asyncio.wait_for(conn.fetch(sql), timeout=_TIMEOUT)
    except asyncio.TimeoutError:
        log.warning("crt.sh timeout %s/%s", keyword, tld)
        rows = []
    except Exception as exc:
        log.warning("crt.sh query %s/%s: %s", keyword, tld, str(exc)[:200])
        rows = []
    finally:
        try:
            await conn.close()
        except Exception:
            pass

    apexes: set[str] = set()
    for r in rows:
        apex = _apex_domain(r["d"], tld)
        if apex:
            apexes.add(apex)
    log.info("crt.sh %s/%s → %d raw rows → %d apex domains",
             keyword, tld, len(rows), len(apexes))
    return sorted(apexes)


async def _upsert(pool: asyncpg.Pool, domain: str, country: str, keyword: str) -> bool:
    try:
        result = await pool.execute(
            """
            INSERT INTO discovery_candidates
              (domain, country, source_layer, source, url, name, address, city, postcode, phone, email, lat, lng, registry_id, external_refs)
            VALUES ($1,$2,5,'ct_logs',$3,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,$4::jsonb)
            ON CONFLICT (domain, country) WHERE domain IS NOT NULL
            DO NOTHING
            """,
            domain, country, f"https://{domain}/", json.dumps({"keyword": keyword}),
        )
        return "INSERT 0 1" in result
    except Exception as exc:
        log.debug("upsert %s: %s", domain, exc)
        return False


async def run() -> None:
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=6)
    sem = asyncio.Semaphore(_CONC)
    stats = {"queries": 0, "apexes": 0, "inserted": 0}
    t0 = time.monotonic()

    async def _one(country: str, keyword: str, tld: str) -> None:
        async with sem:
            apexes = await _query_crt_pg(keyword, tld)
            stats["queries"] += 1
            stats["apexes"] += len(apexes)
            inserted_local = 0
            for dom in apexes:
                if await _upsert(pool, dom, country, keyword):
                    inserted_local += 1
            stats["inserted"] += inserted_local
            log.info(
                "%s %s: %d apex, +%d new (tot q=%d apex=%d ins=%d elapsed=%.0fs)",
                country, keyword, len(apexes), inserted_local,
                stats["queries"], stats["apexes"], stats["inserted"],
                time.monotonic() - t0,
            )

    tasks = []
    for country, keywords in _KEYWORDS_BY_COUNTRY.items():
        tlds = _TLDS_BY_COUNTRY[country]
        for keyword in keywords:
            for tld in tlds:
                tasks.append(_one(country, keyword, tld))
    await asyncio.gather(*tasks)

    el = time.monotonic() - t0
    log.info("DONE queries=%d apexes=%d inserted=%d elapsed=%.0fs",
             stats["queries"], stats["apexes"], stats["inserted"], el)
    await pool.close()


if __name__ == "__main__":
    asyncio.run(run())
