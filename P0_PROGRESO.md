# P0 — PROGRESO (rama feature/p0-rewiring)

> Plan vivo. Estado real por bloque. Doctrina: un bloque, su verificación, el siguiente.

## Estado runtime de partida [VERIFICADO 2026-06-06]
- PG vivo: vehicle_index=508339, vehicle_events=539259, **vehicles=30**, entities=0, vin_history_cache=0.
- cardex-api: **Restarting (crash-loop)** por red docker.
- Redis vivo. Ningún scraper/worker corriendo.

## Checklist
- [x] **Bloque 0** — Git hazard auditado + `BLOCK0_GIT_HAZARD.md` + rama dedicada `feature/p0-rewiring`.
- [x] **P0-3** — `enrich_worker` (A6) + `rich_consumer` (A7) + `fx_eur`. **VERIFICADO E2E vivo:** seam Redis real `enrich_pending`→A6→`ingestion_raw`→A7→`vehicles` 30→32 (SEAT Ateca €16950, Peugeot 2008 €20700), H1 source_id poblado, meili_sync emitido, purga exacta→30. Hallazgo: A7-Go no compila (sin go.mod/pkg/Dockerfile) → portado a Python honrando contrato C7. Compose corregido (command `scrapers.enrich_worker` + pipeline→`scrapers.rich_consumer`). +39 tests.
- [ ] **P0-2** — `cardex-api` recableado a red `data`, healthy. *Hecho:* /healthz 200.
- [ ] **P0-1** — Harvest-0 detector: single-segment harvest-0 → `empty_suspect`, no `done`. H2: purga por igualdad EXACTA. *Hecho:* 0 portales done@0.
- [ ] **P0-4** — Entity resolution a PG (entities/entity_matches). *Hecho:* entities>0 (o cableado parcial documentado).
- [ ] Tests: suite Python 1188/1188 verde + nuevos tests del cambio.
- [ ] `P0_EXECUTION_REPORT.md` con evidencia antes/después.

## Principio transversal
validar-con-límite-y-purgar: EXTRACT_LIMIT/ENRICH_LIMIT en local; verificar E2E; purgar. Disco = banco de pruebas.

## Notas de decisión
- Rama in-place (no worktree): worktree perdería engine.db/.env/contexto docker untracked. auto_commit_check.ps1 borra .claude\worktrees\*.
