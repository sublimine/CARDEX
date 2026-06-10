"""W1 geo — provincia española DETERMINISTA desde el código postal (los 2 primeros
dígitos = una de las 52 provincias). Dato de referencia canónico (no se adivina).

geo_region estaba vacía para ES (migr. 0004), así que la jerarquía provincia no podía
backfillar por join. El postcode ES sí la determina sin ambigüedad. Puro y testeable;
el backfill (``--apply``) actualiza ``discovery_candidates.province`` para ES.

    DATABASE_URL=... python -m scrapers.discovery.geo_es --apply
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

# Prefijo postal (01-52) → provincia oficial. Fuente: plan de codificación postal de Correos.
ES_PROVINCES: dict[str, str] = {
    "01": "Álava", "02": "Albacete", "03": "Alicante", "04": "Almería", "05": "Ávila",
    "06": "Badajoz", "07": "Illes Balears", "08": "Barcelona", "09": "Burgos",
    "10": "Cáceres", "11": "Cádiz", "12": "Castellón", "13": "Ciudad Real", "14": "Córdoba",
    "15": "A Coruña", "16": "Cuenca", "17": "Girona", "18": "Granada", "19": "Guadalajara",
    "20": "Gipuzkoa", "21": "Huelva", "22": "Huesca", "23": "Jaén", "24": "León",
    "25": "Lleida", "26": "La Rioja", "27": "Lugo", "28": "Madrid", "29": "Málaga",
    "30": "Murcia", "31": "Navarra", "32": "Ourense", "33": "Asturias", "34": "Palencia",
    "35": "Las Palmas", "36": "Pontevedra", "37": "Salamanca", "38": "Santa Cruz de Tenerife",
    "39": "Cantabria", "40": "Segovia", "41": "Sevilla", "42": "Soria", "43": "Tarragona",
    "44": "Teruel", "45": "Toledo", "46": "Valencia", "47": "Valladolid", "48": "Bizkaia",
    "49": "Zamora", "50": "Zaragoza", "51": "Ceuta", "52": "Melilla",
}


def province_from_postcode(postcode: str | None) -> str | None:
    """The Spanish province a postcode falls in, or None when undecidable.

    ES postcodes are 5 digits; provinces 01-09 carry a leading zero that integer
    storage drops ("1001" → really 01001 = Álava). So pad to 5 BEFORE taking the
    province prefix, never just slice the raw string."""
    if not postcode:
        return None
    digits = "".join(ch for ch in str(postcode) if ch.isdigit())
    if not (2 <= len(digits) <= 5):
        return None
    return ES_PROVINCES.get(digits.zfill(5)[:2])


async def backfill(apply: bool) -> None:
    import asyncpg
    dsn = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
    pg = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    try:
        # Authoritative: re-derive for every ES row WITH a postcode and correct any
        # stored province that differs (fixes the 4-digit leading-zero mis-maps too).
        rows = await pg.fetch(
            "SELECT id, postcode, province FROM discovery_candidates "
            "WHERE country='ES' AND postcode IS NOT NULL AND postcode<>''")
        updates = [(r["id"], p) for r in rows
                   if (p := province_from_postcode(r["postcode"])) and p != (r["province"] or "")]
        print(f"ES: {len(rows)} con postcode → {len(updates)} a backfillar/corregir")
        if apply and updates:
            await pg.executemany(
                "UPDATE discovery_candidates SET province=$2 WHERE id=$1", updates)
            print(f"APLICADO: {len(updates)} provincias backfilled")
        elif not apply:
            from collections import Counter
            top = Counter(p for _, p in updates).most_common(8)
            print("dry-run; top provincias:", top)
    finally:
        await pg.close()


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    asyncio.run(backfill(a.apply))
