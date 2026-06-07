---
name: project_e07_playwright
description: E07 extractor con navegador (Playwright) — desbloquea inventario JS/SPA; rama feature/e07-playwright-xhr
metadata: 
  node_type: memory
  type: project
  originSessionId: 3580463c-4ae4-408a-9d01-af8872ba2a62
---

E07 construido en rama `feature/e07-playwright-xhr` (commit `7e16152`, desde main `a980b3f`; NO pusheado). Suite **1273 verde**. Ver `E07_REPORT.md`. Desbloquea la brecha SPA documentada en [[project_nl_vertical]] / [[project_fanout_5countries]].

**Hallazgo central:** los SPAs (autolina/autohero/gowago) NO traen JSON-LD ni state-blob (`__NEXT_DATA__`) ni XHR de datos limpio — renderizan al DOM. PERO todos pueblan **SEO meta** (`og:title` + `meta description`) con la ficha completa (lo necesitan para previews). autolina description: "...Kilometer: 10'600 km, Preis: CHF 29'500, Erstzulassung: 01.09.2025, Farbe: Silber". → E07 parsea el meta tras render = vector GENÉRICO (sin selectores CSS por-portal).

**Implementación:** `scrapers/pipeline/playwright_extractor.py` — `parse_rendered_meta`+`record_from_rendered` (PUROS, multilingüe DE/FR/ES/NL/IT/EN, ambas órdenes de moneda "CHF 29'500"/"14 990 EUR", separadores '/.,) + `PlaywrightFetcher` (headless Chromium reusado, `domcontentloaded`+settle no `networkidle`). Merge **meta-gana** (el estático da ruido heurístico en SPA: cogía 600 para 10'600km). Núcleo unit-testeable sin navegador.

**Config-driven (una estrategia más, sin reescribir seam):** `portals/config.py` añade `playwright_meta`/`playwright_xhr` + `PLAYWRIGHT_STRATEGIES`. `enrich_worker.enrich_one` rutea a E07 sii `configs/portals/<s>.json` lo dice Y hay `e07_fetcher` inyectado; si no, estático. Mismo `VehicleRecord`→`ingestion_raw`→A7→vehicles. `e07_fetcher` threaded por process_message/reclaim_pending/run. `configs/portals/autolina.ch.json` = referencia.

**E2E [VERIFICADO]:** autolina.ch (0 estático → 3 E07): AUDI Q5/SKODA Kamiq/VW Polo, CHF→EUR (FX_RATE_CHF×1.05), purgado. `scripts/verify_seam_e07.py`. Drift strategy-agnostic toma baseline de la config E07.

**Coordinación git:** main avanzó a `6e0be32` (orquestador FF-mergeó fanout) mientras yo trabajaba. e07 parte de a980b3f → e07↔main divergen (1/1) pero **solapamiento de archivos = 0** → merge e07→main SIN conflictos (rebase o 3-way, NO FF directo). e07 toca config.py+enrich_worker.py (nuevos: playwright_extractor, autolina.json); fanout tocó discovery/sources (disjunto).

**Pendiente:** configs playwright_meta para más portales SPA (autohero/gowago/ocasionplus/clicars/simplicicar/vroom); implementar `playwright_xhr` (intercepción) para SPAs sin meta útil; pool de páginas para escala; wire del e07_fetcher en el contenedor enrich-worker; tier-1 anti-bot (Akamai/DataDome) = proxies P3.

**GUARDIAN audit verdict (2026-06-07, `GUARDIAN_REPORT_E07_2026-06-07.md`):** los 5 ítems verificados (re-run E2E independiente autolina 0→3 CHF→EUR exacto; A6 diff aditivo+opt-in con **reclaim P1 preservado**; meta-gana refutado→correcto; drift strategy-agnostic; 1273 verde). **Merge 3-way LIMPIO** confirmado por `git merge-tree main e07` → exit 0, 0 conflictos (archivos disjuntos del fanout). **Recomendación: GO vía merge 3-way/rebase** (NO es FF); suite post-merge esperada ~1284 (1274+10). **Brecha única (P2, pre-producción, NO bloquea merge): el pool headless es FOOTGUN** — `PlaywrightFetcher` sin semáforo propio hereda `ENRICH_CONCURRENCY=20` → hasta 20 páginas Chromium ~1-2GB en VPS que ya OOMea ([[project_coordinator_oom_supervisor]]); acotar a 2-4 antes de cablear e07_fetcher en producción. Ciclo de vida del browser correcto (página nueva+close en finally, sin leak). Mecánica: el working tree principal está en e07 y existe worktree `cardex-discovery-scale` (sesión de barrido activa) → mergear en worktree temporal sobre main.
