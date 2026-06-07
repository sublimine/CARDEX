#!/usr/bin/env python3
"""Generate the TIER1_COVERAGE.md governance board from the portal queue + the
per-portal status map. Re-run to refresh as portals advance.

Governance rule: this tool NEVER marks a portal green. The strongest a portal
reaches here is 'pendiente de verificación' — an independent Guardian count
audits it before it is closed.
"""
from __future__ import annotations

import json
from pathlib import Path

EVID = Path(__file__).resolve().parent / "evidence"
BOARD = Path(__file__).resolve().parent.parent / "TIER1_COVERAGE.md"

# Per-portal status: portal -> dict. Only portals with hard evidence get a status
# beyond 'pendiente'. total_oficial: declared/live total; cobertura: proven count.
STATUS = {
    "mobile.de": {"total": "1.586.022 (vivo)", "cob": "1.586.026 (Σ178 marcas)", "pct": "100,0%",
                  "delta": "SEEN/GONE OK (seam)", "estado": "pendiente de verificación",
                  "ev": "facet/mobilede_coverage.json"},
    "leboncoin.fr": {"total": "~900.000 (sitemap)", "cob": "~900.000 URLs + 60 muestra", "pct": "~100% (sitemap)",
                     "delta": "altas/bajas OK (seam demo)", "estado": "pendiente de verificación",
                     "ev": "sitemap_recon.json + seam_writer demo"},
    "coches.net": {"total": "249.949 (vivo)", "cob": "Σ marcas (worker en curso)", "pct": "midiendo",
                   "delta": "—", "estado": "midiendo cobertura (worker vivo)", "ev": "facet/coches_coverage.json"},
    "autoscout24.de": {"total": "pend.", "cob": "SSR 20/pág", "pct": "—", "delta": "—",
                       "estado": "parcial · falta count+faceteo", "ev": "as24_de_listings.json"},
    "autoscout24.fr": {"total": "pend.", "cob": "SSR 20/pág", "pct": "—", "delta": "—",
                       "estado": "parcial · falta count+faceteo", "ev": "as24_fr_listings.json"},
    "autoscout24.es": {"total": "pend.", "cob": "SSR 20/pág", "pct": "—", "delta": "—",
                       "estado": "parcial · falta count+faceteo", "ev": "as24_es_listings.json"},
    "autoscout24.nl": {"total": "pend.", "cob": "SSR 20/pág", "pct": "—", "delta": "—",
                       "estado": "parcial · falta count+faceteo", "ev": "as24_nl_listings.json"},
    "autoscout24.ch": {"total": "pend.", "cob": "DOM 20/pág", "pct": "—", "delta": "—",
                       "estado": "parcial · falta count+faceteo", "ev": "as24_ch_listings.json"},
    "autoscout24.be": {"total": "pend.", "cob": "—", "pct": "—", "delta": "—",
                       "estado": "fix URL (locale /nl//fr/)", "ev": "—"},
    "kleinanzeigen.de": {"total": "pend.", "cob": "DOM 27/pág", "pct": "—", "delta": "—",
                         "estado": "parcial · falta count+faceteo", "ev": "kleinanzeigen_listings.json"},
    "milanuncios.com": {"total": "pend.", "cob": "—", "pct": "—", "delta": "—",
                        "estado": "BLOQUEADO · PerimeterX + geo (proxy ES)", "ev": "batch_results.json"},
    "lacentrale.fr": {"total": "pend.", "cob": "—", "pct": "—", "delta": "—",
                      "estado": "BLOQUEADO · DataDome + geo (proxy FR)", "ev": "batch_results.json"},
}
# extra cracked portal outside the 6-country work_queue
EXTRA = [{"portal": "gumtree.com", "country": "UK", "tier": "T?",
          "st": {"total": "pend.", "cob": "DOM 12/pág", "pct": "—", "delta": "—",
                 "estado": "parcial · falta count+faceteo", "ev": "gumtree_listings.json"}}]


def main() -> int:
    queue = json.loads((EVID / "tier1_queue.json").read_text(encoding="utf-8"))
    rows = []
    for q in queue:
        st = STATUS.get(q["portal"], {"total": "—", "cob": "—", "pct": "—", "delta": "—",
                                      "estado": "pendiente", "ev": "—"})
        rows.append((q["portal"], q["country"], q["tier"], st))
    for e in EXTRA:
        rows.append((e["portal"], e["country"], e["tier"], e["st"]))

    n = len(rows)
    n_done = sum(1 for *_, st in rows if "verificación" in st["estado"])
    n_partial = sum(1 for *_, st in rows if st["estado"].startswith("parcial"))
    n_blocked = sum(1 for *_, st in rows if "BLOQUEADO" in st["estado"])
    n_pend = sum(1 for *_, st in rows if st["estado"] == "pendiente")

    lines = [
        "# TIER1_COVERAGE — Tablero de adquisición (73 portales tier-1)",
        "",
        "> **Gobernanza:** ningún portal se marca verde aquí. El máximo estado es",
        "> **«pendiente de verificación»**; Guardian hace un conteo independiente antes de cerrarlo.",
        "> Generado por `stealth/make_dashboard.py` (re-ejecutable). Evidencia en `stealth/evidence/`.",
        "",
        f"**Resumen:** {n} portales · {n_done} pendiente-de-verificación · {n_partial} parcial · "
        f"{n_blocked} bloqueado · {n_pend} pendiente.",
        "",
        "| Portal | País | Tier | Total oficial | Cobertura | % | Delta | Estado | Evidencia |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    order = {"pendiente de verificación": 0, "parcial": 1, "fix": 2, "BLOQUEADO": 3, "pendiente": 4}
    def rank(st):
        for k, v in order.items():
            if st["estado"].startswith(k) or k in st["estado"]:
                return v
        return 5
    rows.sort(key=lambda r: (rank(r[3]), r[1], r[0]))
    for portal, country, tier, st in rows:
        lines.append(f"| {portal} | {country} | {tier} | {st['total']} | {st['cob']} | {st['pct']} | "
                     f"{st['delta']} | {st['estado']} | {st['ev']} |")
    lines += [
        "",
        "## Notas de método",
        "- **Cobertura = Σ(conteos por faceta) ≈ total oficial** (≥99%; resto justificado). "
        "Conteo vía API interna del portal; enumeración vía estado SSR paginado; faceteo "
        "recursivo `marca→año→km→región` mantiene cada hoja bajo el cap de paginación.",
        "- **Delta** → `vehicle_index` (C3) + `vehicle_events` SEEN/GONE (C4) + `stream:enrich_pending` "
        "`{h,u,s,c}` (C5), idempotente. Probado E2E en leboncoin (60 altas, 10 bajas, purgado).",
        "- **Anti-bot:** IP residencial CH nativa + Camoufox solo para cookies/bypass (no un navegador "
        "por anuncio). Geo-sensibles (ES/FR estrictos) requieren proxy residencial del país.",
        "- **«parcial»** = extracción SSR/DOM ya crackeada con evidencia, pero falta el perfil de "
        "count+faceteo para demostrar Σ-hojas=total. **«pendiente»** = sin reconocimiento aún.",
    ]
    BOARD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {BOARD}  ({n} portales: {n_done} pend-verif, {n_partial} parcial, {n_blocked} bloq, {n_pend} pend)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
