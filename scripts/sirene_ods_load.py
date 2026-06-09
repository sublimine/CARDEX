"""
SIRENE via Opendatasoft export stream — bulk FR auto-trade discovery, NO API row cap.

The gov recherche-entreprises API caps at 10k/query and rate-limited our IP. Opendatasoft
hosts the full SIRENE v3 (different host, not penalised) with an /exports/csv endpoint that
STREAMS every matching establishment (no cap). FR auto-trade NAF codes:
  45.11Z car dealers 256.679 · 45.20A garages 234.029 · 45.19Z 6.225 · 45.20B 8.426
  45.40Z motorcycles · = ~500k+ establishments (each a physical entity = a dealer/garage).

Streams the CSV, filters etatadministratifetablissement='Actif', maps to identity candidates
(registry_id=SIRET, address from voie/postcode/commune), and BULK-upserts in batches.

    python -m scripts.sirene_ods_load                  # all auto codes
    SIRENE_CODES=45.11Z python -m scripts.sirene_ods_load
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import os

import asyncpg
import httpx

_DSN = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_BASE = ("https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
         "economicref-france-sirene-v3/exports/csv")
_CODES = [c.strip() for c in os.environ.get(
    "SIRENE_CODES", "45.11Z,45.19Z,45.20A,45.20B,45.40Z").split(",") if c.strip()]
_SELECT = ("siret,denominationusuelleetablissement,enseigne1etablissement,"
           "numerovoieetablissement,typevoieetablissement,libellevoieetablissement,"
           "codepostaletablissement,libellecommuneetablissement,etatadministratifetablissement")
_BATCH = 1000
_HDR = {"User-Agent": "cardex-discovery/1.0", "Accept": "text/csv"}

_UPSERT = """
INSERT INTO discovery_candidates
  (domain, country, source_layer, source, url, name, address, city, postcode,
   phone, email, lat, lng, registry_id, external_refs)
VALUES (NULL,'FR',3,'sirene:etablissement',NULL,$1,$2,$3,$4,NULL,NULL,NULL,NULL,$5,$6::jsonb)
ON CONFLICT (source, registry_id, country) WHERE domain IS NULL AND registry_id IS NOT NULL
DO UPDATE SET last_seen = NOW()
WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'
"""

_ND = {"[ND]", "", None}


def _clean(v):
    v = (v or "").strip()
    return None if v in ("[ND]", "") else v


def _to_row(rec: dict, code: str):
    siret = _clean(rec.get("siret"))
    if not siret:
        return None
    if _clean(rec.get("etatadministratifetablissement")) == "Fermé":
        return None  # only live establishments
    name = _clean(rec.get("enseigne1etablissement")) or _clean(rec.get("denominationusuelleetablissement"))
    num = _clean(rec.get("numerovoieetablissement"))
    typ = _clean(rec.get("typevoieetablissement"))
    lib = _clean(rec.get("libellevoieetablissement"))
    address = " ".join(x for x in (num, typ, lib) if x) or None
    return (
        name, address, _clean(rec.get("libellecommuneetablissement")),
        _clean(rec.get("codepostaletablissement")), siret,
        json.dumps({"naf": code, "siret": siret}),
    )


async def _flush(pool, batch):
    if not batch:
        return 0
    async with pool.acquire() as conn:
        await conn.executemany(_UPSERT, batch)
    return len(batch)


async def load_code(client: httpx.AsyncClient, pool, code: str) -> int:
    # NOTE: do NOT pass delimiter — opendatasoft FR export defaults to ';' and we parse with ';'.
    # Passing delimiter=',' made the export comma-delimited while we split on ';' -> 0 rows.
    params = {"select": _SELECT,
              "where": f'activiteprincipaleetablissement="{code}" and etatadministratifetablissement="Actif"',
              "limit": -1}
    total = 0
    batch = []
    buf = ""
    header = None
    async with client.stream("GET", _BASE, params=params, headers=_HDR, timeout=None) as r:
        r.raise_for_status()
        async for chunk in r.aiter_text():
            buf += chunk
            *lines, buf = buf.split("\n")
            for line in lines:
                if header is None:
                    header = next(csv.reader([line.lstrip("﻿")], delimiter=";"))
                    continue
                if not line.strip():
                    continue
                vals = next(csv.reader([line], delimiter=";"))
                if len(vals) != len(header):
                    continue
                row = _to_row(dict(zip(header, vals)), code)
                if not row:
                    continue
                batch.append(row)
                if len(batch) >= _BATCH:
                    total += await _flush(pool, batch)
                    batch = []
                    if total % 20000 == 0:
                        print(f"  {code}: {total} upserted...", flush=True)
    total += await _flush(pool, batch)
    print(f"DONE {code}: {total} establishments upserted", flush=True)
    return total


async def run() -> int:
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=6)
    grand = 0
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            for code in _CODES:
                try:
                    grand += await load_code(client, pool, code)
                except Exception as exc:  # noqa: BLE001 — one code must not abort the rest
                    print(f"ERR {code}: {type(exc).__name__} {str(exc)[:120]}", flush=True)
    finally:
        await pool.close()
    print(f"GRAND TOTAL FR sirene:etablissement upserted={grand}", flush=True)
    return grand


if __name__ == "__main__":
    asyncio.run(run())
