"""
RDW Erkende Bedrijven — NL official register of RDW-recognised companies.

The Dutch vehicle authority (RDW) publishes, via Socrata open data (no key), the
census of companies it recognises. Two datasets, joined on ``volgnummer``:

  * 5k74-3jha  Erkende Bedrijven — name + address per company (no website).
  * nmwb-dqkz  Erkenningen       — the recognition TYPE(S) each company holds.

The 30,678 companies in 5k74 include non-automotive holders (photographers,
plate manufacturers). The dealer signal lives in the recognition type: a company
holding **Bedrijfsvoorraad** (business vehicle stock) or **Handelaarskenteken**
(dealer trade plate) is a car dealer/trader. We filter to those and emit them as
identity candidates (``domain`` is NULL — RDW carries no website; the dealer's
domain is resolved downstream by ``name_to_domain`` via crt.sh, then inventory is
harvested from that domain by ``generic_extractor``).

This is the verified coste-cero discovery anchor for NL (SOURCING_STRATEGY §3),
the lever that breaks the FR/SIRENE monoculture.

Usage:
    python -m scrapers.discovery.sources.nl_rdw            # full dealer census
    RDW_LIMIT=500 python -m scrapers.discovery.sources.nl_rdw   # bounded sample
"""
from __future__ import annotations

import asyncio
import logging
import os

import asyncpg
import httpx

log = logging.getLogger("nl_rdw")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [nl_rdw] %(message)s",
)

_DSN = os.environ.get("DATABASE_URL", "postgres://cardex:cardex_dev_only@localhost:5432/cardex")
_ERKENDE = "https://opendata.rdw.nl/resource/5k74-3jha.json"
_ERKENNINGEN = "https://opendata.rdw.nl/resource/nmwb-dqkz.json"
_SOURCE = "rdw_erkende_bedrijven"
_SOURCE_LAYER = 3  # registry layer (orchestrator scheme)
_COUNTRY = "NL"

# Recognition types that identify a car dealer/trader (vs photographer / plate maker).
# Bedrijfsvoorraad = holds vehicle stock; Handelaarskenteken = dealer trade plate.
_DEALER_ERKENNINGEN: tuple[str, ...] = ("Bedrijfsvoorraad", "Handelaarskenteken")

_PAGE = 1000           # Socrata page size
_WHERE_CHUNK = 100     # volgnummers per `$where in(...)` (URL-length safe)
_HDR = {"Accept": "application/json", "User-Agent": "cardex-discovery/1.0 (open-data)"}


def to_candidate(company: dict, erkenningen: list[str]) -> dict:
    """
    Map an RDW Erkende-Bedrijven row to a discovery candidate (pure).

    ``domain`` is None (identity row, resolved later); ``registry_id`` is the RDW
    ``volgnummer`` so re-runs dedup on ``(source, registry_id, country)``.
    """
    huis = (company.get("huisnummer") or "").strip()
    straat = (company.get("straat") or "").strip()
    address = f"{straat} {huis}".strip() or None
    pc_num = (company.get("postcode_numeriek") or "").strip()
    pc_alf = (company.get("postcode_alfanumeriek") or "").strip()
    postcode = (pc_num + pc_alf) or None
    name = (company.get("naam_bedrijf") or company.get("gevelnaam") or "").strip() or None
    return {
        "domain": None,
        "country": _COUNTRY,
        "source_layer": _SOURCE_LAYER,
        "source": _SOURCE,
        "url": None,
        "name": name,
        "address": address,
        "city": (company.get("plaats") or "").strip() or None,
        "postcode": postcode,
        "phone": None,
        "email": None,
        "lat": None,
        "lng": None,
        "registry_id": (company.get("volgnummer") or "").strip() or None,
        "external_refs": {
            "gevelnaam": (company.get("gevelnaam") or "").strip(),
            "erkenningen": erkenningen,
            "rdw_dataset": "5k74-3jha",
        },
    }


async def _get_json(client: httpx.AsyncClient, url: str, params: dict) -> list[dict]:
    r = await client.get(url, params=params, headers=_HDR)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


async def fetch_dealer_volgnummers(client: httpx.AsyncClient, limit: int) -> dict[str, list[str]]:
    """
    Return {volgnummer: [erkenning, ...]} for companies holding a dealer recognition.

    Paginates nmwb-dqkz filtered to the dealer recognition types. ``limit`` (>0)
    caps the number of distinct dealers collected (validate-with-a-limit).
    """
    in_list = ",".join(f"'{e}'" for e in _DEALER_ERKENNINGEN)
    where = f"erkenning in({in_list})"
    out: dict[str, list[str]] = {}
    offset = 0
    while True:
        rows = await _get_json(client, _ERKENNINGEN, {
            "$select": "volgnummer,erkenning", "$where": where,
            "$limit": _PAGE, "$offset": offset, "$order": "volgnummer",
        })
        if not rows:
            break
        for row in rows:
            vn = (row.get("volgnummer") or "").strip()
            if not vn:
                continue
            out.setdefault(vn, []).append(row.get("erkenning") or "")
            if limit and len(out) >= limit:
                return out
        offset += _PAGE
    return out


async def fetch_companies(client: httpx.AsyncClient, volgnummers: list[str]) -> dict[str, dict]:
    """Fetch Erkende-Bedrijven rows for the given volgnummers, keyed by volgnummer."""
    out: dict[str, dict] = {}
    for i in range(0, len(volgnummers), _WHERE_CHUNK):
        chunk = volgnummers[i : i + _WHERE_CHUNK]
        in_list = ",".join(f"'{v}'" for v in chunk)
        rows = await _get_json(client, _ERKENDE, {
            "$where": f"volgnummer in({in_list})", "$limit": _WHERE_CHUNK,
        })
        for row in rows:
            vn = (row.get("volgnummer") or "").strip()
            if vn:
                out[vn] = row
    return out


_UPSERT = """
INSERT INTO discovery_candidates
  (domain, country, source_layer, source, url, name, address, city, postcode,
   phone, email, lat, lng, registry_id, external_refs)
VALUES (NULL,$1,$2,$3,NULL,$4,$5,$6,$7,NULL,NULL,NULL,NULL,$8,$9::jsonb)
ON CONFLICT (source, registry_id, country) WHERE domain IS NULL AND registry_id IS NOT NULL
DO UPDATE SET last_seen = NOW()
WHERE discovery_candidates.last_seen < NOW() - INTERVAL '1 hour'
"""


async def run(limit: int = 0) -> int:
    """
    Discover NL car dealers from RDW and upsert them as identity candidates.

    Returns the number of candidates processed. ``limit`` > 0 bounds the sample
    (local validation); 0 = full dealer census.
    """
    import json

    inserted = 0
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            dealers = await fetch_dealer_volgnummers(client, limit)
            log.info("rdw dealers (Bedrijfsvoorraad/Handelaarskenteken) = %d", len(dealers))
            companies = await fetch_companies(client, list(dealers.keys()))
            log.info("rdw companies resolved = %d", len(companies))
            for vn, erk in dealers.items():
                company = companies.get(vn)
                if not company:
                    continue
                cand = to_candidate(company, erk)
                if not cand["registry_id"]:
                    continue
                await pool.execute(
                    _UPSERT,
                    cand["country"], cand["source_layer"], cand["source"], cand["name"],
                    cand["address"], cand["city"], cand["postcode"], cand["registry_id"],
                    json.dumps(cand["external_refs"]),
                )
                inserted += 1
            log.info("DONE nl_rdw upserted=%d", inserted)
    finally:
        await pool.close()
    return inserted


class NLRDWSource:
    """Orchestrator Source adapter: RDW Erkende Bedrijven → NL dealer identity candidates.

    Reuses the verified ``fetch_dealer_volgnummers``/``fetch_companies``/``to_candidate`` and
    YIELDS candidates (the orchestrator's idempotent sink upserts them) — unlike ``run()`` which
    upserts directly for standalone use. NL-only (RDW is the Dutch register). This wires the
    coste-cero NL anchor into the production discovery sweep (breaks the FR/SIRENE monoculture).
    """

    COUNTRY = "NL"

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def discover(self, country: str):
        if country != self.COUNTRY:
            return
        dealers = await fetch_dealer_volgnummers(self._client, limit=0)
        companies = await fetch_companies(self._client, list(dealers.keys()))
        for vn, erk in dealers.items():
            company = companies.get(vn)
            if company is None:
                continue
            cand = to_candidate(company, erk)
            if cand.get("registry_id"):
                yield cand


if __name__ == "__main__":
    asyncio.run(run(limit=int(os.environ.get("RDW_LIMIT", "0"))))
