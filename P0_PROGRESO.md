# P0 — PROGRESO (rama feature/p0-rewiring)

> Plan vivo. Estado real por bloque. Doctrina: un bloque, su verificación, el siguiente.

## Estado runtime de partida [VERIFICADO 2026-06-06]
- PG vivo: vehicle_index=508339, vehicle_events=539259, **vehicles=30**, entities=0, vin_history_cache=0.
- cardex-api: **Restarting (crash-loop)** por red docker.
- Redis vivo. Ningún scraper/worker corriendo.

## Checklist
- [x] **Bloque 0** — Git hazard auditado + `BLOCK0_GIT_HAZARD.md` + rama dedicada `feature/p0-rewiring` + bundle de rescate en `AUDIT_SCRATCH/block0_rescue/`.
- [x] **P0-3** — `enrich_worker` (A6) + `rich_consumer` (A7) + `fx_eur`. **VERIFICADO E2E vivo:** seam Redis real `enrich_pending`→A6→`ingestion_raw`→A7→`vehicles` 30→33 (autotrack.nl: Peugeot 2008 €20700, Mazda CX-3 €19395, SEAT Ateca €16950), H1 source_id poblado, meili_sync emitido, purga exacta→30. Hallazgo: A7-Go no compila (sin go.mod/pkg/Dockerfile) → portado a Python honrando contrato C7. Hallazgo 2: gaspedaal.nl es meta-agregador (`missing_critical`) → piloto NL usa autotrack/viabovag. Compose corregido (command `scrapers.enrich_worker` + pipeline→`scrapers.rich_consumer`).
- [x] **P0-2** — `cardex-api` recableado a red `data` + **rebuild desde fuente** (imagen stale: binario viejo trataba redis como fatal) + JWT key dev provisionada. *Hecho:* healthy, /healthz 200, /api/v1/market-price 200 con datos reales.
- [x] **P0-1** — Harvest-0 detector: ciclo completo con `total==0` → nuevo `RunStatus.EMPTY_SUSPECT`, NO `done`, **NO finalize** (protege el índice del wipe). 12 portales done@0 reseteados a pending (causa `reeval_empty_harvest_p0-1`). H2: reset/purga por igualdad EXACTA. *Hecho:* 0 nuevos done@0; 12 re-evaluándose.
- [x] **P0-4** — Entity resolution a PG **(parcial verificado + plan)**: `entity_resolver` (capa VIN cross-source V12, determinista) escribe `entity_matches` real (E2E: 1 match insertado, idempotente, purgado). Capa fuzzy V21 (embeddings) + `entities`/KYC (vault_dek_id) **diferidas a P1** con plan en el reporte.
- [x] Tests: suite Python **1232/1232 verde** (baseline 1188 + nuevos: P0-1 portals/coordinator, P0-4 entity_resolver, A6/A7/fx).
- [x] `P0_EXECUTION_REPORT.md` con evidencia antes/después.

## Principio transversal
validar-con-límite-y-purgar: EXTRACT_LIMIT/ENRICH_LIMIT en local; verificar E2E; purgar. Disco = banco de pruebas.

## Notas de decisión
- Rama in-place (no worktree): worktree perdería engine.db/.env/contexto docker untracked. auto_commit_check.ps1 borra .claude\worktrees\*.
