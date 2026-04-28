"""
SIRENE V3.11 — official INSEE API with authenticated key.

Endpoint: https://api.insee.fr/api-sirene/3.11/siret
Auth: header X-INSEE-Api-Key-Integration: <key>
Rate limit: 30 req/s per key

Query shape:
    q=periode(activitePrincipaleEtablissement:45.11Z)
    nombre=1000 (max per page)
    debut=N (offset, not page)

NAF codes for car dealers:
    45.11Z — Commerce de voitures et véhicules automobiles légers
    45.19Z — Commerce d'autres véhicules automobiles
    45.20A — Entretien et réparation de véhicules automobiles légers
    45.20B — Entretien et réparation d'autres véhicules automobiles

The response yields établissements with uniteLegale.denominationUniteLegale,
adresseEtablissement fields for the street/city/postcode. Website is NOT
exposed by SIRENE — identity rows only, resolved later by name→domain.

Usage:
    INSEE_API_KEY=... python -m scrapers.discovery.sources.fr_sirene_v311
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

import asyncpg
import httpx

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [sirene311] %(message)s",
)
log = logging.getLogger("sirene311")

_DSN = os.environ.get(
    "DATABASE_URL",
    "postgres://cardex:cardex_dev_only@localhost:5432/cardex",
)

_API_BASE = "https://api.insee.fr/api-sirene/3.11/siret"
_API_KEY = os.environ.get("INSEE_API_KEY", "")

_NAF_CODES = ("45.11Z", "45.19Z", "45.20A", "45.20B")
_PAGE_SIZE = 1000
_REQ_DELAY = 0.05  # stay under 30/s

_HDR = {
    "X-INSEE-Api-Key-Integration": _API_KEY,
    "Accept": "application/json",
}


async def _query_page(
    client: httpx.AsyncClient,
    naf: str,
    cursor: str,
) -> tuple[list[dict], int, str | None]:
    q = f"periode(activitePrincipaleEtablissement:{naf} AND etatAdministratifEtablissement:A)"
    params = {"q": q, "nombre": _PAGE_SIZE, "curseur": cursor, "tri": "siret"}
    try:
        r = await client.get(_API_BASE, headers=_HDR, params=params, timeout=60)
    except Exception as exc:
        log.warning("sirene %s cursor=%s: %s", naf, cursor[:20], exc)
        return [], 0, None
    if r.status_code == 404:
        return [], 0, None
    if r.status_code == 429:
        log.warning("sirene %s: 429 rate limit, sleeping", naf)
        await asyncio.sleep(5)
        return await _query_page(client, naf, cursor)
    if r.status_code != 200:
        log.warning("sirene %s: HTTP %d: %s", naf, r.status_code, r.text[:200])
        return [], 0, None
    try:
        data = r.json()
    except Exception:
        return [], 0, None
    hdr = data.get("header", {})
    return (
        data.get("etablissements", []),
        hdr.get("total", 0),
        hdr.get("curseurSuivant"),
    )


def _to_candidate(et: dict, naf: str) -> dict | None:
    siret = et.get("siret")
    if not siret:
        return None
    ul = et.get("uniteLegale") or {}
    name = (
        ul.get("denominationUniteLegale")
        or ul.get("denominationUsuelle1UniteLegale")
        or ul.get("sigleUniteLegale")
        or ""
    ).strip()
    if not name:
        # Fallback: person-run business
        fn = ul.get("prenom1UniteLegale") or ""
        ln = ul.get("nomUniteLegale") or ""
        name = f"{fn} {ln}".strip()
    if not name:
        return None

    adr = et.get("adresseEtablissement") or {}
    street = " ".join(filter(None, (
        str(adr.get("numeroVoieEtablissement") or ""),
        adr.get("typeVoieEtablissement") or "",
        adr.get("libelleVoieEtablissement") or "",
    ))).strip() or None
    city = adr.get("libelleCommuneEtablissement")
    postcode = adr.get("codePostalEtablissement")
    dep = adr.get("codeCommuneEtablissement", "")[:2] if adr.get("codeCommuneEtablissement") else None

    return {
        "domain": None,
        "country": "FR",
        "source_layer": 3,
        "source": "sirene_v311",
        "url": None,
        "name": name[:200],
        "address": street[:200] if street else None,
        "city": city[:100] if city else None,
        "postcode": postcode,
        "phone": None,
        "email": None,
        "lat": None,
        "lng": None,
        "registry_id": siret,
        "external_refs": {
            "naf_code": naf,
            "siren": ul.get("siren"),
            "departement": dep,
        },
    }


async def run() -> None:
    if not _API_KEY:
        log.error("INSEE_API_KEY not set in environment")
        return
    pool = await asyncpg.create_pool(_DSN, min_size=2, max_size=4)
    total_written = 0
    total_seen = 0
    t0 = time.monotonic()

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True, http2=True) as client:
        for naf in _NAF_CODES:
            cursor = "*"
            log.info("starting NAF %s", naf)
            page_count = 0
            naf_written = 0
            seen_cursors: set[str] = set()
            while True:
                rows, grand_total, next_cursor = await _query_page(client, naf, cursor)
                if not rows:
                    log.info("NAF %s done: total=%d written=%d", naf, grand_total, naf_written)
                    break
                for et in rows:
                    cand = _to_candidate(et, naf)
                    if not cand:
                        continue
                    total_seen += 1
                    try:
                        await pool.execute(
                            """
                            INSERT INTO discovery_candidates
                              (domain, country, source_layer, source, url, name, address, city, postcode, phone, email, lat, lng, registry_id, external_refs)
                            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb)
                            ON CONFLICT (source, registry_id, country) WHERE domain IS NULL AND registry_id IS NOT NULL
                            DO NOTHING
                            """,
                            cand.get("domain"),
                            cand.get("country"),
                            cand.get("source_layer"),
                            cand.get("source"),
                            cand.get("url"),
                            cand.get("name"),
                            cand.get("address"),
                            cand.get("city"),
                            cand.get("postcode"),
                            cand.get("phone"),
                            cand.get("email"),
                            cand.get("lat"),
                            cand.get("lng"),
                            cand.get("registry_id"),
                            json.dumps(cand.get("external_refs") or {}),
                        )
                        total_written += 1
                        naf_written += 1
                    except Exception as exc:
                        log.debug("upsert: %s", exc)
                page_count += 1
                if not next_cursor or next_cursor == cursor or next_cursor in seen_cursors:
                    log.info("NAF %s done (cursor exhausted): total=%d written=%d",
                             naf, grand_total, naf_written)
                    break
                seen_cursors.add(cursor)
                cursor = next_cursor
                if page_count % 10 == 0:
                    log.info("NAF %s progress: page=%d/%d written=%d (%.0fs)",
                             naf, page_count, (grand_total // _PAGE_SIZE) + 1,
                             naf_written, time.monotonic() - t0)
                await asyncio.sleep(_REQ_DELAY)
    log.info("DONE seen=%d written=%d elapsed=%.0fs",
             total_seen, total_written, time.monotonic() - t0)
    await pool.close()


if __name__ == "__main__":
    asyncio.run(run())
