"""Ad-hoc per-country funnel report + 3 sample dealers with cars from the live store."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys

import asyncpg

PG_DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")


async def main(countries: list[str]) -> None:
    pg = await asyncpg.connect(PG_DSN)
    try:
        for ctry in countries:
            row = await pg.fetchrow(
                "SELECT "
                " count(*) FILTER (WHERE domain IS NOT NULL AND domain<>'') AS with_web, "
                " count(*) FILTER (WHERE inventory_tier IS NOT NULL) AS classified, "
                " count(*) FILTER (WHERE inventory_tier='T2') AS t2, "
                " count(*) FILTER (WHERE inventory_tier='T1') AS t1, "
                " count(*) FILTER (WHERE domain IS NOT NULL AND domain<>'' "
                "                  AND sitemap_status='pending') AS pending "
                "FROM discovery_candidates WHERE country=$1", ctry)
            caged = await pg.fetchval(
                "SELECT count(*) FROM vehicle_index vi JOIN source_entities se USING(entity_ulid) "
                "WHERE se.kind='dealer' AND se.country=$1", ctry)
            dealers = await pg.fetchval(
                "SELECT count(*) FROM source_entities WHERE kind='dealer' AND country=$1", ctry)
            print(f"\n===== FUNNEL {ctry} =====")
            print(json.dumps({**dict(row), "caged_pointers": caged,
                              "dealer_entities": dealers}, indent=0))

            # top 3 dealers by caged pointer count, with car samples
            top = await pg.fetch(
                "SELECT se.entity_ulid, se.domain, count(vi.*) AS n "
                "FROM source_entities se JOIN vehicle_index vi USING(entity_ulid) "
                "WHERE se.kind='dealer' AND se.country=$1 "
                "GROUP BY se.entity_ulid, se.domain ORDER BY n DESC LIMIT 3", ctry)
            for d in top:
                cars = await pg.fetch(
                    "SELECT titulo_modelo, precio, moneda, anio, kilometraje, url_original "
                    "FROM vehicle_index "
                    "WHERE entity_ulid=$1 AND (precio IS NOT NULL OR anio IS NOT NULL) "
                    "ORDER BY (precio IS NOT NULL) DESC, (anio IS NOT NULL) DESC LIMIT 3",
                    d["entity_ulid"])
                print(f"  DEALER {d['domain']} ulid={d['entity_ulid']} pointers={d['n']}")
                for c in cars:
                    print(f"    - {c['titulo_modelo']} | {c['precio']} {c['moneda']} "
                          f"| year={c['anio']} | {c['kilometraje']} km | {c['url_original']}")
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or ["NL", "CH"]))
