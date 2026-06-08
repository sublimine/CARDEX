"""Correct the fabricated year on already-persisted BE rich rows.

The full-HTML stage-3 heuristic stamped a noise year (e.g. a whole dealer's stock
read year=2000 from a copyright line). Those rows are REAL cars (make/model/price/
mileage verified) with one bad field. This re-fetches each, re-derives the year
from a RELIABLE source only (schema.org modelDate / scoped SEO title·description),
and UPDATEs it — to the real year where the page exposes one, else NULL (honest
"unknown"). It never fabricates and never deletes a real car.

    DATABASE_URL=... python -m scrapers.fix_be_year [--suspect-year 2000] [--conc 4]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re

import asyncpg
from curl_cffi.requests import AsyncSession

from scrapers.common.net_guard import is_safe_public_url
from scrapers.pipeline.parse import parse_jsonld
from scrapers.pipeline.playwright_extractor import parse_rendered_meta

PG = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")


def _reliable_year(html: str) -> int | None:
    """A registration year from a RELIABLE source only (schema.org or scoped meta)."""
    for raw in (parse_jsonld(html).get("year"), parse_rendered_meta(html).get("year")):
        if not raw:
            continue
        m = _YEAR.search(str(raw))
        if m:
            y = int(m.group(1))
            if 1920 <= y <= 2027:
                return y
    return None


async def run(*, suspect_year: int, conc: int, timeout: float = 20.0) -> None:
    pool = await asyncpg.create_pool(PG, min_size=2, max_size=6)
    s = AsyncSession()
    sem = asyncio.Semaphore(conc)
    fixed = {"reextracted": 0, "nulled": 0, "kept": 0, "errors": 0}

    async def fetch(u: str) -> bytes | None:
        if not await asyncio.to_thread(is_safe_public_url, u, resolve=True):
            return None
        r = await s.get(u, impersonate="chrome", timeout=timeout, allow_redirects=True)
        return r.content if r.status_code == 200 else None

    try:
        rows = await pool.fetch(
            "SELECT v.vehicle_ulid, v.source_url, v.year FROM vehicles v "
            "WHERE v.source_country='BE' AND v.year=$1", suspect_year)
        print(f"correcting {len(rows)} BE rows stamped year={suspect_year}")

        async def one(r) -> None:
            async with sem:
                try:
                    body = await fetch(r["source_url"])
                except Exception:  # noqa: BLE001
                    fixed["errors"] += 1
                    return
                y = _reliable_year(body.decode("utf-8", "replace")) if body else None
                if y == r["year"]:
                    fixed["kept"] += 1                      # reliably confirms the value
                    return
                await pool.execute(
                    "UPDATE vehicles SET year=$1 WHERE vehicle_ulid=$2", y, r["vehicle_ulid"])
                if y is None:
                    fixed["nulled"] += 1
                else:
                    fixed["reextracted"] += 1

        await asyncio.gather(*(one(r) for r in rows))
    finally:
        await s.close()
        await pool.close()
    print(f"DONE reextracted_real_year={fixed['reextracted']} nulled_unknown={fixed['nulled']} "
          f"kept_confirmed={fixed['kept']} errors={fixed['errors']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--suspect-year", type=int, default=2000)
    ap.add_argument("--conc", type=int, default=4)
    a = ap.parse_args()
    asyncio.run(run(suspect_year=a.suspect_year, conc=a.conc))
