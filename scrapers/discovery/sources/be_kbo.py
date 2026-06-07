"""
BE discovery — KBO/BCE (Crossroads Bank for Enterprises) open data, NACEBEL auto.

Belgium's company register is KBO/BCE. The web-service API is paid; the free path
is the monthly "KBO Open Data" CSV bundle — but it requires an email-registered
account to download (SOURCING_STRATEGY §4). So this connector parses the documented
KBO CSV structure and is transform-tested, but its LIVE LOAD IS BLOCKED here
(no account → no download). It loads from a local CSV bundle when one is provided
(``KBO_DATA_DIR``); otherwise ``run()`` returns 0 with a logged BLOCKED reason —
never invented data. BE already holds ~4k candidates from other sources.

KBO bundle = several CSVs joined on EntityNumber:
  enterprise.csv (EnterpriseNumber, Status) · denomination.csv (EntityNumber, Denomination)
  · address.csv (EntityNumber, Zipcode, MunicipalityNL/FR, StreetNL/FR, HouseNumber)
  · activity.csv (EntityNumber, NaceCode)  → filter NACEBEL 45.11/45.19/45.20.

Identity rows: registry_id = EnterpriseNumber.

Usage:
    KBO_DATA_DIR=/path/to/kbo_open_data python -m scrapers.discovery.sources.be_kbo
"""
from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
from pathlib import Path

import asyncpg

log = logging.getLogger("be_kbo")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [be_kbo] %(message)s",
)

_DSN = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_SOURCE = "kbo"
_SOURCE_LAYER = 3
_COUNTRY = "BE"
# NACEBEL automotive prefixes: 4511* (sale of cars), 4519* (other vehicles), 4520* (maint/repair).
_NACE_PREFIXES = ("4511", "4519", "4520")


def is_auto_nace(code: str) -> bool:
    """True when a NACEBEL code is an automotive sale/repair class."""
    c = (code or "").replace(".", "").strip()
    return any(c.startswith(p) for p in _NACE_PREFIXES)


def to_candidate(joined: dict) -> dict:
    """Map one joined KBO enterprise row to a discovery candidate (pure)."""
    street = (joined.get("StreetNL") or joined.get("StreetFR") or "").strip()
    house = (joined.get("HouseNumber") or "").strip()
    address = f"{street} {house}".strip() or None
    return {
        "domain": None,
        "country": _COUNTRY,
        "source_layer": _SOURCE_LAYER,
        "source": _SOURCE,
        "name": (joined.get("Denomination") or "").strip() or None,
        "address": address,
        "city": (joined.get("MunicipalityNL") or joined.get("MunicipalityFR") or "").strip() or None,
        "postcode": (joined.get("Zipcode") or "").strip() or None,
        "registry_id": (joined.get("EnterpriseNumber") or "").strip() or None,
        "external_refs": {"nace": joined.get("NaceCode")},
    }


def _index_csv(path: Path, key: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            k = row.get(key)
            if k:
                out[k] = row
    return out


def join_kbo(data_dir: Path) -> list[dict]:
    """Join the KBO CSV bundle into automotive enterprise rows (pure-ish, file IO)."""
    acts = {}
    with (data_dir / "activity.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if is_auto_nace(row.get("NaceCode", "")):
                acts[row["EntityNumber"]] = row.get("NaceCode")
    denom = _index_csv(data_dir / "denomination.csv", "EntityNumber")
    addr = _index_csv(data_dir / "address.csv", "EntityNumber")
    joined: list[dict] = []
    for ent, nace in acts.items():
        j = {"EnterpriseNumber": ent, "NaceCode": nace}
        j.update({k: v for k, v in denom.get(ent, {}).items() if k != "EntityNumber"})
        j.update({k: v for k, v in addr.get(ent, {}).items() if k != "EntityNumber"})
        joined.append(j)
    return joined


async def run(*, data_dir: str | None = None) -> int:
    raw = data_dir or os.environ.get("KBO_DATA_DIR", "").strip()
    if not raw or not Path(raw).is_dir():
        log.warning("BLOCKED: KBO Open Data CSV bundle requires an email-registered "
                    "account to download (no KBO_DATA_DIR provided). Register at "
                    "economie.fgov.be, place the CSVs in KBO_DATA_DIR, then re-run. "
                    "BE already has ~4k candidates from other sources.")
        return 0
    joined = join_kbo(Path(raw))
    inserted = 0
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    try:
        for row in joined:
            cand = to_candidate(row)
            if not cand["registry_id"]:
                continue
            await pool.execute(
                "INSERT INTO discovery_candidates (domain,country,source_layer,source,url,"
                "name,address,city,postcode,phone,email,lat,lng,registry_id,external_refs) "
                "VALUES (NULL,$1,$2,$3,NULL,$4,$5,$6,$7,NULL,NULL,NULL,NULL,$8,$9::jsonb) "
                "ON CONFLICT (source, registry_id, country) WHERE domain IS NULL AND registry_id IS NOT NULL "
                "DO UPDATE SET last_seen = NOW() WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'",
                cand["country"], cand["source_layer"], cand["source"], cand["name"],
                cand["address"], cand["city"], cand["postcode"], cand["registry_id"],
                json.dumps(cand["external_refs"]),
            )
            inserted += 1
        log.info("DONE be_kbo upserted=%d", inserted)
    finally:
        await pool.close()
    return inserted


if __name__ == "__main__":
    asyncio.run(run())
