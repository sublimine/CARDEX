"""
CH discovery — Zefix ALL 26 cantons via the Basel-Stadt open-data mirror.

Switzerland's commercial register (Zefix) is fragmented across 26 cantonal
registers. Basel-Stadt republishes a consolidated daily mirror of every canton
as plain CSV (keyless, open):

    https://data-bs.ch/stata/zefix_handelsregister/all_cantons/companies_<KT>.csv

This supersedes ``ch_zefix_bs`` (Basel-Stadt only, ~19k) and ``ch_zefix``
(PublicREST, credential-gated) for census coverage: it reaches the whole country
without a key. The register carries NO reliable NOGA activity code, so dealers
are isolated by NAME using the trilingual ``dealer_terms`` (de/fr/it) — the same
filter the rest of the CH pipeline uses (Ticino Italian included).

Each CSV row is an identity candidate (no website, no coords): registry_id =
``company_uid`` (CHE-…). Domain resolution happens later (name_to_domain / OEM /
OSM overlap). Verified live from host 2026-06-07 (companies_ZH.csv = 200, 40 MB).

The download is streamed to a temp file and parsed from disk, never held whole in
RAM, so a 40 MB cantonal CSV cannot OOM a memory-constrained host running other
jobs concurrently.

Usage:
    python -m scrapers.discovery.sources.ch_zefix_allcantons
    CH_CANTONS=ZH,BE,GE python -m scrapers.discovery.sources.ch_zefix_allcantons
"""
from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import tempfile

import asyncpg
import httpx

from scrapers.discovery.dealer_terms import name_matches

log = logging.getLogger("ch_zefix_ac")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [ch_zefix_ac] %(message)s",
)

_DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
_MIRROR = "https://data-bs.ch/stata/zefix_handelsregister/all_cantons/companies_{kt}.csv"
_SOURCE = "zefix"
_SOURCE_LAYER = 3
_COUNTRY = "CH"
_HDR = {"Accept": "text/csv", "User-Agent": "cardex-discovery/1.0 (open-data)"}

# 26 cantons — ISO 3166-2:CH codes (mirror filenames use these).
_CANTONS: tuple[str, ...] = (
    "AG", "AI", "AR", "BE", "BL", "BS", "FR", "GE", "GL", "GR",
    "JU", "LU", "NE", "NW", "OW", "SG", "SH", "SO", "SZ", "TG",
    "TI", "UR", "VD", "VS", "ZG", "ZH",
)


def _cantons() -> tuple[str, ...]:
    raw = os.environ.get("CH_CANTONS", "").strip()
    if not raw or raw.lower() == "all":
        return _CANTONS
    return tuple(c.strip().upper() for c in raw.split(",") if c.strip())


def to_candidate(row: dict) -> dict:
    """Map one all-cantons CSV row to a discovery candidate (pure)."""
    return {
        "domain": None,
        "country": _COUNTRY,
        "source_layer": _SOURCE_LAYER,
        "source": _SOURCE,
        "url": None,
        "name": (row.get("company_legal_name") or "").strip() or None,
        "address": (row.get("street") or "").strip() or None,
        "city": (row.get("locality") or row.get("municipality") or "").strip() or None,
        "postcode": (str(row.get("plz")) if row.get("plz") else "").strip() or None,
        "phone": None,
        "email": None,
        "lat": None,
        "lng": None,
        "registry_id": (row.get("company_uid") or "").strip() or None,
        "external_refs": {
            "canton": (row.get("short_name_canton") or "").strip() or None,
            "legal_form": (row.get("company_type_de") or "").strip() or None,
            "register_url": (row.get("url_cantonal_register") or "").strip() or None,
        },
    }


_UPSERT = """
INSERT INTO discovery_candidates
  (domain, country, source_layer, source, url, name, address, city, postcode,
   phone, email, lat, lng, registry_id, external_refs)
VALUES (NULL,$1,$2,$3,NULL,$4,$5,$6,$7,NULL,NULL,NULL,NULL,$8,$9::jsonb)
ON CONFLICT (source, registry_id, country) WHERE domain IS NULL AND registry_id IS NOT NULL
DO UPDATE SET last_seen = NOW()
WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'
"""


async def _download_canton(client: httpx.AsyncClient, kt: str) -> str | None:
    """Stream a cantonal CSV to a temp file (disk, not RAM). Returns path or None."""
    url = _MIRROR.format(kt=kt)
    tmp = tempfile.NamedTemporaryFile("wb", delete=False, suffix=f"_{kt}.csv")
    try:
        async with client.stream("GET", url, headers=_HDR) as resp:
            if resp.status_code != 200:
                log.warning("canton=%s HTTP %d — skipping", kt, resp.status_code)
                tmp.close()
                os.unlink(tmp.name)
                return None
            async for chunk in resp.aiter_bytes():
                tmp.write(chunk)
        tmp.close()
        return tmp.name
    except Exception as exc:  # noqa: BLE001 — one canton failing must not abort the sweep
        log.warning("canton=%s download error: %s", kt, exc)
        tmp.close()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        return None


async def _load_canton(pool: asyncpg.Pool, path: str, kt: str) -> tuple[int, int]:
    """Parse a cantonal CSV from disk, name-filter to dealers, upsert. (scanned, upserted)."""
    scanned = upserted = 0
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            scanned += 1
            name = row.get("company_legal_name") or ""
            if not name_matches(name, _COUNTRY):  # no reliable NOGA → name filter (de/fr/it)
                continue
            cand = to_candidate(row)
            if not cand["registry_id"] or not cand["name"]:
                continue
            try:
                await pool.execute(
                    _UPSERT, cand["country"], cand["source_layer"], cand["source"],
                    cand["name"], cand["address"], cand["city"], cand["postcode"],
                    cand["registry_id"], json.dumps(cand["external_refs"]),
                )
                upserted += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("canton=%s upsert failed name=%r: %s", kt, name[:50], exc)
    return scanned, upserted


async def run(cantons: tuple[str, ...] | None = None) -> int:
    cantons = cantons or _cantons()
    total_scanned = total_upserted = 0
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    try:
        async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
            for kt in cantons:
                path = await _download_canton(client, kt)
                if not path:
                    continue
                try:
                    scanned, upserted = await _load_canton(pool, path, kt)
                finally:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
                total_scanned += scanned
                total_upserted += upserted
                log.info("canton=%s scanned=%d dealer_upserts=%d (cum=%d)", kt, scanned, upserted, total_upserted)
        log.info("DONE ch_zefix_allcantons scanned=%d dealer_upserts=%d cantons=%d",
                 total_scanned, total_upserted, len(cantons))
    finally:
        await pool.close()
    return total_upserted


if __name__ == "__main__":
    asyncio.run(run())
