"""
Name-to-domain resolver using crt.sh fuzzy matching.

For identity rows (Sirene, BMW, Zefix) that have name+city but no domain,
query crt.sh for certificates whose SAN contains the business name tokens.
If a match is found with the right country TLD, promote the identity row
by UPDATEing its domain field.

Heuristic:
    1. Tokenize the name (lowercase, strip accents, split on whitespace,
       drop stopwords like "SAS", "SARL", "GMBH", "SRL", "SL", "SA", "BV")
    2. Keep the 2 longest tokens as the search key
    3. Query crt.sh for `%token1%token2%.tld`
    4. Pick the shortest apex domain that contains BOTH tokens
    5. UPDATE the row via PG

Limits:
    - crt.sh rate: 2 concurrent queries
    - Only processes rows where source='sirene_v311' OR 'sirene' OR 'oem:bmw'
    - Skips rows already enriched (domain NOT NULL)

Usage:
    python -m scrapers.discovery.name_to_domain
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import unicodedata

import asyncpg

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [name2dom] %(message)s",
)
log = logging.getLogger("name2dom")

_DSN = os.environ.get(
    "DATABASE_URL",
    "postgres://cardex:cardex_dev_only@localhost:5432/cardex",
)
_CRT_DSN = "postgresql://guest@crt.sh:5432/certwatch"

_CONC = int(os.environ.get("N2D_CONC", "2"))
_LIMIT = int(os.environ.get("N2D_LIMIT", "0"))
_COUNTRY_TLD = {
    "FR": "fr", "DE": "de", "ES": "es",
    "NL": "nl", "BE": "be", "CH": "ch",
}

# Legal form stopwords to drop
_STOPWORDS = {
    "sas", "sasu", "sa", "sarl", "eurl", "snc",
    "gmbh", "ag", "kg", "ohg", "ug", "gmbh co", "co",
    "srl", "spa", "sc",
    "sl", "sll",
    "bv", "nv",
    "ag", "ltd", "gbr", "ek",
    "auto", "autos", "automobiles", "automobile",
}

# Words too generic to use as match anchor
_GENERIC = {
    "garage", "autohaus", "concessionnaire", "auto",
    "motor", "motors", "car", "cars", "voiture",
    "coche", "coches", "the",
}


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )


def _tokenize(name: str) -> list[str]:
    n = _strip_accents(name.lower())
    n = re.sub(r"[^a-z0-9\s-]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    tokens = [t for t in n.split() if len(t) >= 3 and t not in _STOPWORDS]
    # Prefer non-generic tokens
    anchors = [t for t in tokens if t not in _GENERIC]
    if anchors:
        tokens = anchors
    # Sort by length descending — longest tokens are most distinctive
    tokens.sort(key=len, reverse=True)
    return tokens[:2]


async def _resolve_one(
    conn: asyncpg.Connection,
    name: str,
    tld: str,
) -> str | None:
    tokens = _tokenize(name)
    if not tokens:
        return None
    # Build ILIKE pattern that matches both tokens in any order
    t0 = tokens[0]
    t1 = tokens[1] if len(tokens) > 1 else ""
    pattern = f"%{t0}%.{tld}"
    try:
        sql = (
            "SELECT DISTINCT lower(ci.NAME_VALUE) AS d "
            "FROM certificate_and_identities ci "
            "WHERE plainto_tsquery('certwatch', '" + t0.replace("'", "''") + "') "
            "      @@ identities(ci.CERTIFICATE) "
            "AND ci.NAME_VALUE ILIKE '" + pattern.replace("'", "''") + "' "
            "LIMIT 1000"
        )
        rows = await asyncio.wait_for(conn.fetch(sql), timeout=90)
    except Exception:
        return None

    # Filter + rank
    apexes: list[str] = []
    for r in rows:
        d = r["d"].strip().lower()
        if d.startswith("*."):
            d = d[2:]
        if " " in d or not d.endswith("." + tld):
            continue
        # Apex only
        parts = d.split(".")
        if len(parts) < 2:
            continue
        apex = ".".join(parts[-2:])
        if t0 not in apex:
            continue
        if t1 and t1 not in apex:
            # Second token required if present
            continue
        apexes.append(apex)

    if not apexes:
        return None
    # Prefer shortest match (tighter to the business name)
    return min(set(apexes), key=len)


async def run() -> None:
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)

    # Fetch identity rows that need resolution
    sql = """
    SELECT id, name, country
    FROM discovery_candidates
    WHERE domain IS NULL
      AND registry_id IS NOT NULL
      AND name IS NOT NULL
      AND source IN ('sirene_v311','sirene','oem:bmw')
    ORDER BY id
    """
    if _LIMIT > 0:
        sql += f" LIMIT {_LIMIT}"
    rows = await pool.fetch(sql)
    log.info("identity rows to resolve: %d", len(rows))

    sem = asyncio.Semaphore(_CONC)
    stats = {"scanned": 0, "resolved": 0, "updated": 0}
    t0 = time.monotonic()

    async def _worker(row):
        async with sem:
            stats["scanned"] += 1
            tld = _COUNTRY_TLD.get(row["country"])
            if not tld:
                return
            try:
                conn = await asyncpg.connect(_CRT_DSN, ssl="prefer", timeout=30, statement_cache_size=0)
                await conn.execute("SET statement_timeout='120s'")
                domain = await _resolve_one(conn, row["name"], tld)
                await conn.close()
            except Exception as exc:
                log.debug("resolve %s: %s", row["name"], exc)
                return
            if not domain:
                return
            stats["resolved"] += 1
            try:
                # Insert a new row with the domain instead of updating the identity
                # (identity row stays as crossref, new row is the domain candidate)
                await pool.execute(
                    """
                    INSERT INTO discovery_candidates
                      (domain, country, source_layer, source, url, name, external_refs)
                    VALUES ($1,$2,5,'name2dom',$3,$4,'{}'::jsonb)
                    ON CONFLICT (domain, country) WHERE domain IS NOT NULL
                    DO NOTHING
                    """,
                    domain, row["country"], f"https://{domain}/", row["name"],
                )
                stats["updated"] += 1
            except Exception as exc:
                log.debug("insert %s: %s", domain, exc)

            if stats["scanned"] % 20 == 0:
                log.info("scanned=%d resolved=%d updated=%d (%.0fs)",
                         stats["scanned"], stats["resolved"], stats["updated"],
                         time.monotonic() - t0)

    await asyncio.gather(*[_worker(r) for r in rows])
    log.info("DONE scanned=%d resolved=%d updated=%d elapsed=%.0fs",
             stats["scanned"], stats["resolved"], stats["updated"],
             time.monotonic() - t0)
    await pool.close()


if __name__ == "__main__":
    asyncio.run(run())
