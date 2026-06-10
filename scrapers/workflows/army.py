"""El Director — orquesta los 6 Generales + la Inquisición, en cascada por país.

Cada país: el General despliega soldados (cierra dealers 5/5), LUEGO la Inquisición
re-certifica una muestra por vía ortogonal. Países en SECUENCIA (la lección
2026-06-10: corridas de red solapadas saturan el NAT/resolver local; en VPS esto no
aplica). Dentro de un país, los soldados van en paralelo.

Emite un cuadro de cobertura por país + tasa de confianza de la Inquisición, y lo
persiste en state/ARMY.json.

    DATABASE_URL=... REDIS_URL=... python -m scrapers.workflows.army \
        --countries ES,FR,NL,BE,CH,DE --limit 200 --concurrency 6 --sample 20 --persist
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from scrapers.workflows.general import run_general  # noqa: E402
from scrapers.workflows.inquisition import run_inquisition  # noqa: E402

log = logging.getLogger("army")


async def run_army(countries: list[str], *, limit: int, concurrency: int, cap: int,
                   sample: int, persist: bool) -> dict:
    board: dict[str, dict] = {}
    for cc in countries:
        log.info("════ GENERAL %s ════", cc)
        g = await run_general(cc, limit=limit, concurrency=concurrency, cap=cap, persist=persist)
        # Inquisition re-certifies the dealers the General just closed (orthogonal path).
        closed = [r.domain for r in g.results if r.all_pasa][:sample]
        inq = await run_inquisition(cc, only=closed, record=True) if closed \
            else await run_inquisition(cc, sample=sample, record=True)
        board[cc] = {
            "claimed": g.claimed, "closed_5of5": g.closed_5of5,
            "closure_rate": g.closure_rate, "blocked": g.blocked,
            "served_total": g.served_total, "worst_gate": g.worst_gate,
            "inquisition_sampled": inq.sampled, "inquisition_trust_rate": inq.trust_rate,
            "inquisition_refuted": [v.domain for v in inq.refuted],
        }

    totals = {
        "closed_5of5": sum(b["closed_5of5"] for b in board.values()),
        "served_total": sum(b["served_total"] for b in board.values()),
        "blocked": sum(b["blocked"] for b in board.values()),
    }
    out = {"by_country": board, "totals": totals}
    if persist:
        (REPO / "state").mkdir(exist_ok=True)
        (REPO / "state" / "ARMY.json").write_text(
            json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n═══════════ CUADRO DE COBERTURA (EJÉRCITO) ═══════════")
    print(f"{'PAÍS':<6}{'cerrados':>10}{'tasa':>8}{'bloq':>6}{'served':>9}{'peor':>6}{'inq.fiar':>10}")
    for cc, b in board.items():
        print(f"{cc:<6}{b['closed_5of5']:>10}{b['closure_rate']:>8.1%}{b['blocked']:>6}"
              f"{b['served_total']:>9}{(b['worst_gate'] or '-'):>6}{b['inquisition_trust_rate']:>10.1%}")
    print(f"{'TOTAL':<6}{totals['closed_5of5']:>10}{'':>8}{totals['blocked']:>6}{totals['served_total']:>9}")
    return out


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default="ES,FR,NL,BE,CH,DE")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--cap", type=int, default=5000)
    ap.add_argument("--sample", type=int, default=20)
    ap.add_argument("--persist", action="store_true")
    a = ap.parse_args()
    countries = [c.strip().upper() for c in a.countries.split(",") if c.strip()]
    asyncio.run(run_army(countries, limit=a.limit, concurrency=a.concurrency, cap=a.cap,
                         sample=a.sample, persist=a.persist))


if __name__ == "__main__":
    main()
