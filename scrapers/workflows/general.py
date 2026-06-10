"""General de país — reclama la cola de su territorio y despliega SOLDADOS en paralelo.

Soldados = ejecuciones concurrentes del pipeline (Python asyncio, masivo y barato).
RAM-aware (el host OOM-killea bajo presión). Agrega % de cobertura, histograma de
gates fallidos (dónde mandar refuerzos) y aísla al dealer bloqueado sin parar la línea.

    DATABASE_URL=... REDIS_URL=... python -m scrapers.workflows.general \
        --country ES --limit 200 --concurrency 6 [--persist]
"""
from __future__ import annotations

import argparse
import asyncio
import ctypes
import gc
import json
import logging
import os
import sys
from pathlib import Path

import asyncpg
import redis.asyncio as aioredis

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from scrapers.dealer_scraping.inventory_probe import IN_SCOPE_SQL  # noqa: E402
from scrapers.workflows.model import GATES, DealerResult, GeneralReport  # noqa: E402
from scrapers.workflows.pipeline import run_dealer  # noqa: E402

log = logging.getLogger("general")
PG_DSN = os.environ.get("DATABASE_URL", "postgresql://cardex:cardex_dev_only@localhost:5432/cardex")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:56390")
RAM_HARD_MB = 550


def _avail_mb() -> int:
    class M(ctypes.Structure):
        _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("tp", ctypes.c_ulonglong),
                    ("ap", ctypes.c_ulonglong), ("tpf", ctypes.c_ulonglong),
                    ("apf", ctypes.c_ulonglong), ("tv", ctypes.c_ulonglong),
                    ("av", ctypes.c_ulonglong), ("ae", ctypes.c_ulonglong)]
    m = M(); m.l = ctypes.sizeof(M)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return int(m.ap // 1024 // 1024)


def aggregate(country: str, claimed: int, results: list[DealerResult]) -> GeneralReport:
    """Pure roll-up — extracted so the General's accounting is unit-testable."""
    closed = [r for r in results if r.all_pasa]
    blocked = [r for r in results if r.blocked_reason is not None]
    gate_fail = {g: 0 for g in GATES}
    for r in results:
        if r.blocked_reason is not None:
            continue
        for g in r.gates:
            if not g.pasa:
                gate_fail[g.gate] = gate_fail.get(g.gate, 0) + 1
    return GeneralReport(
        country=country, claimed=claimed, closed_5of5=len(closed), blocked=len(blocked),
        gate_failures=gate_fail, served_total=sum(r.served for r in closed),
        results=tuple(results))


async def _claim_queue(pg, country: str, limit: int) -> list[str]:
    """Pull the country's pipeline queue: T2/T3 dealers WITH web (md5-spread, stable)."""
    q = ("SELECT domain FROM discovery_candidates "
         "WHERE country=$1 AND domain IS NOT NULL AND domain<>'' "
         "AND inventory_tier IN ('T2','T3') "
         f"AND {IN_SCOPE_SQL} ORDER BY md5(domain)")
    if limit:
        q += f" LIMIT {limit}"
    return [r["domain"] for r in await pg.fetch(q, country)]


async def run_general(country: str, *, limit: int = 200, concurrency: int = 6,
                      cap: int = 5000, persist: bool = False) -> GeneralReport:
    cc = country.upper()[:2]
    pg = await asyncpg.create_pool(PG_DSN, min_size=2, max_size=concurrency + 2)
    rdb = aioredis.from_url(REDIS_URL, decode_responses=False)
    try:
        domains = await _claim_queue(pg, cc, limit)
        log.info("General %s: %d dealers reclamados (conc=%d)", cc, len(domains), concurrency)
        sem = asyncio.Semaphore(concurrency)
        results: list[DealerResult] = []

        async def soldier(domain: str) -> None:
            if _avail_mb() < RAM_HARD_MB:
                gc.collect(); await asyncio.sleep(5)
            async with sem:
                r = await run_dealer(pg, rdb, domain, cc, cap=cap, persist=persist)
                results.append(r)
                tag = "★5/5" if r.all_pasa else (f"BLOQ:{r.blocked_reason[:24]}"
                                                 if r.blocked_reason else f"{r.gates_passed}/5")
                if r.all_pasa or r.blocked_reason or len(results) % 25 == 0:
                    log.info("  [%d/%d] %-28s %s served=%d", len(results), len(domains),
                             domain, tag, r.served)

        await asyncio.gather(*(soldier(d) for d in domains))
        report = aggregate(cc, len(domains), results)
        _write_report(report)
        print(f"\n===== GENERAL {cc} =====")
        print(f"reclamados={report.claimed} cerrados_5/5={report.closed_5of5} "
              f"({report.closure_rate:.1%}) bloqueados={report.blocked} "
              f"served_total={report.served_total}")
        print(f"gate_failures={json.dumps(report.gate_failures)} "
              f"peor_gate={report.worst_gate}")
        return report
    finally:
        await rdb.aclose(); await pg.close()


def _write_report(r: GeneralReport) -> None:
    out = REPO / "state" / "generals"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{r.country}.json").write_text(json.dumps({
        "country": r.country, "claimed": r.claimed, "closed_5of5": r.closed_5of5,
        "closure_rate": r.closure_rate, "blocked": r.blocked,
        "gate_failures": r.gate_failures, "worst_gate": r.worst_gate,
        "served_total": r.served_total,
        "closed_domains": [x.domain for x in r.results if x.all_pasa],
        "blocked_domains": [{"domain": x.domain, "reason": x.blocked_reason}
                            for x in r.results if x.blocked_reason],
    }, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--cap", type=int, default=5000)
    ap.add_argument("--persist", action="store_true")
    a = ap.parse_args()
    asyncio.run(run_general(a.country, limit=a.limit, concurrency=a.concurrency,
                            cap=a.cap, persist=a.persist))


if __name__ == "__main__":
    main()
