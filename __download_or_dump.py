"""
Download OffeneRegister SQLite dump, gunzip, then query with sqlite3 for DE dealers.
Runs entirely RAM-safe: streams download, decompresses in chunks, queries from disk.

Steps:
  1. Download openregister.db.gz -> SCRATCH/openregister.db.gz  (stream, ~737MB)
  2. Gunzip -> SCRATCH/openregister.db                          (stream, ~3-4 GB)
  3. sqlite3 FTS or LIKE query for dealer name terms
  4. INSERT INTO discovery_candidates (identity rows, no domain)

Usage:
    python __download_or_dump.py [--skip-download] [--skip-gunzip]
"""
from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

import asyncpg
import httpx

logging.basicConfig(
    level="INFO", format="%(asctime)s %(levelname)s [de_or_dump] %(message)s"
)
log = logging.getLogger("de_or_dump")

_SCRATCH = Path(os.environ.get("SCRATCH_DIR", r"C:\Users\elias\AUDIT_SCRATCH\mega"))
_GZ = _SCRATCH / "openregister.db.gz"
_DB = _SCRATCH / "openregister.db"
_URL = "https://daten.offeneregister.de/openregister.db.gz"
_DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
_SOURCE = "offeneregister"
_SOURCE_LAYER = 3
_COUNTRY = "DE"
_BATCH = 500

# DE dealer name terms (from dealer_terms.py)
_TERMS = ("autohaus", "kfz", "automobile", "automobil", "autozentrum",
          "autohandel", "gebrauchtwagen", "fahrzeuge", "motors")

_UPSERT = """
INSERT INTO discovery_candidates
  (domain, country, source_layer, source, url, name, address, city, postcode,
   phone, email, lat, lng, registry_id, external_refs)
VALUES (NULL,$1,$2,$3,NULL,$4,$5,$6,$7,NULL,NULL,NULL,NULL,$8,$9::jsonb)
ON CONFLICT (source, registry_id, country) WHERE domain IS NULL AND registry_id IS NOT NULL
DO UPDATE SET last_seen = NOW()
WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'
"""


def download_dump(skip: bool = False) -> bool:
    """Stream-download the gz dump. Returns True if file ready."""
    if _GZ.exists() and _GZ.stat().st_size > 100_000_000:
        log.info("GZ already present (%d MB) — skip download", _GZ.stat().st_size // 1024 // 1024)
        return True
    if _DB.exists() and _DB.stat().st_size > 500_000_000:
        log.info("DB already present (%d MB) — skip download+gunzip", _DB.stat().st_size // 1024 // 1024)
        return True
    if skip:
        log.warning("--skip-download set but no local file found")
        return False
    log.info("Downloading %s -> %s", _URL, _GZ)
    _SCRATCH.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with httpx.stream("GET", _URL, timeout=3600, follow_redirects=True) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        log.info("Content-Length: %d MB", total // 1024 // 1024)
        downloaded = 0
        with _GZ.open("wb") as f:
            for chunk in r.iter_bytes(chunk_size=1024 * 1024):  # 1MB chunks
                f.write(chunk)
                downloaded += len(chunk)
                if downloaded % (50 * 1024 * 1024) < 1024 * 1024:
                    pct = downloaded * 100 // total if total else 0
                    log.info("  downloaded %d MB / %d MB (%d%%)", downloaded // 1024 // 1024,
                             total // 1024 // 1024, pct)
    elapsed = time.time() - t0
    log.info("Download complete: %d MB in %.0fs", _GZ.stat().st_size // 1024 // 1024, elapsed)
    return True


def gunzip_dump(skip: bool = False) -> bool:
    """Decompress gz -> sqlite db. Returns True if db ready."""
    if _DB.exists() and _DB.stat().st_size > 500_000_000:
        log.info("DB already present (%d MB) — skip gunzip", _DB.stat().st_size // 1024 // 1024)
        return True
    if skip or not _GZ.exists():
        log.warning("Cannot gunzip: gz not present or --skip-gunzip")
        return False
    log.info("Decompressing %s -> %s", _GZ, _DB)
    t0 = time.time()
    with gzip.open(str(_GZ), "rb") as f_in, _DB.open("wb") as f_out:
        shutil.copyfileobj(f_in, f_out, length=4 * 1024 * 1024)
    elapsed = time.time() - t0
    log.info("Gunzip done: %d MB in %.0fs", _DB.stat().st_size // 1024 // 1024, elapsed)
    return True


def iter_dealer_rows():
    """Yield rows from the SQLite db matching dealer name terms. RAM-safe cursor iteration."""
    con = sqlite3.connect(str(_DB))
    con.row_factory = sqlite3.Row
    # First, discover what tables/columns exist
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    log.info("SQLite tables: %s", tables)
    # OffeneRegister documented schema: table 'company', cols company_number/name/registered_office
    # But verify:
    if "company" not in tables:
        log.error("Table 'company' not found; tables=%s", tables)
        con.close()
        return

    cols = [r[1] for r in con.execute("PRAGMA table_info(company)").fetchall()]
    log.info("company cols: %s", cols)

    # Build LIKE conditions for all terms (name col)
    name_col = "name" if "name" in cols else cols[1] if len(cols) > 1 else None
    num_col = "company_number" if "company_number" in cols else cols[0]
    addr_col = "registered_office" if "registered_office" in cols else None
    log.info("Using: num=%s name=%s addr=%s", num_col, name_col, addr_col)

    conditions = " OR ".join(f"lower({name_col}) LIKE ?" for _ in _TERMS)
    params = tuple(f"%{t}%" for t in _TERMS)
    q = f"SELECT {num_col}, {name_col}" + (f", {addr_col}" if addr_col else "") + \
        f" FROM company WHERE {conditions}"
    log.info("Running query: %s (params=%d)", q[:120], len(params))

    cur = con.cursor()
    cur.execute(q, params)
    count = 0
    while True:
        batch = cur.fetchmany(1000)
        if not batch:
            break
        for row in batch:
            count += 1
            yield dict(row)
    log.info("SQLite query yielded %d rows", count)
    con.close()


async def load_to_db() -> int:
    """Load dealer rows from SQLite dump into discovery_candidates."""
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    inserted = 0
    batch: list[dict] = []

    async def flush(rows: list[dict]) -> int:
        n = 0
        for row in rows:
            num_col = next((k for k in row if "number" in k.lower() or "nr" in k.lower()), None)
            name_col = next((k for k in row if "name" in k.lower()), None)
            addr_col = next((k for k in row if "office" in k.lower() or "address" in k.lower() or "city" in k.lower()), None)
            registry_id = str(row.get(num_col or "company_number") or "").strip() or None
            name = str(row.get(name_col or "name") or "").strip() or None
            city = str(row.get(addr_col or "registered_office") or "").strip() or None
            if not registry_id:
                continue
            await pool.execute(
                _UPSERT,
                _COUNTRY, _SOURCE_LAYER, _SOURCE,
                name, None, city, None,
                registry_id, json.dumps({"register": "handelsregister"}),
            )
            n += 1
        return n

    try:
        for row in iter_dealer_rows():
            batch.append(row)
            if len(batch) >= _BATCH:
                inserted += await flush(batch)
                batch.clear()
                if inserted % 5000 == 0:
                    log.info("  upserted so far: %d", inserted)
        if batch:
            inserted += await flush(batch)
        log.info("DONE de_or_dump upserted=%d", inserted)
    finally:
        await pool.close()
    return inserted


async def main():
    skip_download = "--skip-download" in sys.argv
    skip_gunzip = "--skip-gunzip" in sys.argv

    if not download_dump(skip=skip_download):
        log.error("Download failed; aborting")
        return 0
    if not gunzip_dump(skip=skip_gunzip):
        log.error("Gunzip failed; aborting")
        return 0
    n = await load_to_db()
    print(f"FINAL: de_or_dump inserted={n}")
    return n


if __name__ == "__main__":
    asyncio.run(main())
