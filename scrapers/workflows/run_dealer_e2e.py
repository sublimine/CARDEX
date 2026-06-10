"""Thin CLI over ``pipeline.run_dealer`` — runs ONE dealer through W1-W5 and prints the
per-gate PASA/NO PASA. The orchestration logic lives in ``pipeline`` (single source of
truth, shared with the General); this file is just the operator entrypoint.

    DATABASE_URL=... REDIS_URL=... python -m scrapers.workflows.run_dealer_e2e \
        --domain dificar.com --country ES [--cap 5000] [--persist]

Exit 0 if all five gates PASA, else 1.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import asyncpg
import redis.asyncio as aioredis

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from scrapers.workflows.pipeline import run_dealer  # noqa: E402

PG_DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:56390")


async def _run(domain: str, country: str, cap: int, persist: bool) -> bool:
    pg = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=4)
    rdb = aioredis.from_url(REDIS_URL, decode_responses=False)
    try:
        r = await run_dealer(pg, rdb, domain, country, cap=cap, persist=persist)
        print(f"\n===== E2E {r.domain} ({r.country}) =====")
        if r.blocked_reason:
            print(f"  BLOQUEADO (aislado, no bloquea la línea): {r.blocked_reason}")
        for g in r.gates:
            print(f"  [{'PASA  ' if g.pasa else 'NO PASA'}] {g.gate}: {g.detail}  «{g.method}»")
        print(f"  VEREDICTO: {'★ 5/5 PASA' if r.all_pasa else str(r.gates_passed)+'/5'} "
              f"({r.elapsed_ms}ms)")
        return r.all_pasa
    finally:
        await rdb.aclose(); await pg.close()


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", required=True)
    ap.add_argument("--country", required=True)
    ap.add_argument("--cap", type=int, default=5000)
    ap.add_argument("--persist", action="store_true")
    a = ap.parse_args()
    sys.exit(0 if asyncio.run(_run(a.domain, a.country, a.cap, a.persist)) else 1)


if __name__ == "__main__":
    main()
