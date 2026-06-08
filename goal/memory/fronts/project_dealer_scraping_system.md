---
name: project-dealer-scraping-system
description: Per-dealer config-driven scraping system (frente C) — branch feature/dealer-scraping-system; honest cost-zero yield reality
metadata: 
  node_type: memory
  type: project
  originSessionId: 4702af55-ddf6-4bc0-950b-c3028e4f4a63
---

**Frente C** (activar dealers con web). Rama `feature/dealer-scraping-system` desde `main b980f90`, en **worktree aislado** `C:\Users\elias\projects\cardex-dealer-scraping` (committed `72b31d5`, NO pushed, main intacto). Construido sobre el seam y E07 de [[project-p0-execution-state]] / [[project-e07-playwright]] — NO reescribe el seam.

Módulos nuevos en `scrapers/dealer_scraping/`: `detector` (tipo de web sitemap/wp/jsonld/SPA-E07 + clasificación de causa), `detector_helpers` (incl. detección de widget DMS embebido), `discovery` (**catalog-follow** estático + **render-follow**: resuelve "el sitemap apunta al catálogo `/fahrzeuge`, no a las fichas"), `harvester` (RAM-safe: cursor id-paged, E07 conc 2, 1 browser/batch, validate-with-limit-and-purge), `remediation` (drift→re-detect→regenerate→revalidate, funcional). Store versionado por dealer = extensión ADITIVA de `portals/config.py` → `configs/dealers/<domain>.json` (el seam lo resuelve nativo vía `config.load`). Scripts: `run_dealer_scraping.py` (seam+purga), `sweep_dealers.py` (censo). 36 tests, suite 1325 verde.

**Realidad cost-zero medida (no inventar):** yield estático sobre OSM random ~3% — porque OSM (92% de los ~30K con dominio) es ~mitad NO-dealers de coches (talleres/chapa/piezas/motos), ~23% unreachable (bloqueo IP datacenter), ~19% `details_no_fields` (inventario JS/widget que NO se recupera ni con E07-meta → necesita playwright_xhr o feed DMS). **El yield real cost-zero está en concesionarios de marca/grupo** (CMS estándar con sitemap+JSON-LD): probado E2E con dacia-meaux.fr/nissan-epernay.fr/mercedes-benz-compiegne.fr → 24 vehículos reales en `vehicles`, purgados (30→30).

**Why:** futuras sesiones no deben re-derivar que el long-tail OSM rinde poco cost-zero, ni reescribir el seam. El segmento de alto yield = brand/group dealers (1 receta → N dealers, como `.audi` x1354).
**How to apply:** sesiones concurrentes escriben `discovery_candidates` (domain-resolution + discovery-scale en sus worktrees) → SIEMPRE leer-only + usar worktree propio. Backlog: playwright_xhr para SPA-XHR, conector feed DMS (Modix/mobile.de), proxies para unreachable. Ver `DEALER_SCRAPING_REPORT.md`.
