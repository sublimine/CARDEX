---
name: project_p0_execution_state
description: Estado real tras ejecutar Bloque 0 + P0 del blueprint (rama feature/p0-rewiring); qué quedó cableado y qué diferido
metadata: 
  node_type: memory
  type: project
  originSessionId: 3580463c-4ae4-408a-9d01-af8872ba2a62
---

Bloque 0 + P0 del [[project_blueprint_target_arch]] ejecutados en rama `feature/p0-rewiring` (commits `527086b` corrida previa A6/A7 + `4ad40cb` esta sesión P0-1/P0-2/P0-4). `main` intacto en `6e084a5`. Suite **1232 passed**.

**El seam L1→L2 está cableado en PYTHON, no Go.** El A7 Go (`services/pipeline`) es código MUERTO: sin `go.mod`, fuera de `go.work`, importa `pkg/{fx,h3,bloom}` borrados en `5a4d59a`. El A7 real es `scrapers/rich_consumer.py` (consume `stream:ingestion_raw` grupo `cg_pipeline` → `vehicles`); A6 es `scrapers/enrich_worker.py` (`enrich_pending`→fetch engine→`ingestion_raw`); FX en `scrapers/pipeline/fx_eur.py` (reemplaza el pkg/fx borrado). Compose: `enrich-worker`→`scrapers.enrich_worker`, `pipeline`→`scrapers.rich_consumer`.

**E2E del seam:** `python -m scripts.verify_seam_redis --domain autotrack.nl --country NL --limit 3` con redis throwaway en :56390 (`docker run -d --rm -p 56390:6379 --name cardex-redis-throwaway redis:7-alpine`). Probado: vehicles 30→33, purga exacta→30. **gaspedaal.nl NO sirve** para el seam (meta-agregador, `missing_critical:make,model,images`); usar autotrack/viabovag. Para producción falta el backfill §6.1 (re-encolar 508K de `vehicle_index` sin fila en `vehicles`).

**P0-1:** nuevo `RunStatus.EMPTY_SUSPECT` en `base.py` — harvest-0 de ciclo completo ya no es `done` ni hace finalize (evita wipe del índice). 12 portales done@0 reseteados a pending (`last_error='reeval_empty_harvest_p0-1'`).

**P0-2:** cardex-api requirió rebuild de imagen (binario stale trataba redis como fatal) + `secrets/jwt_private.pem` dev (gitignored). Healthy, /healthz 200, /api/v1/market-price 200.

**P0-4 PARCIAL:** `scrapers/entity_resolver.py` hace solo la capa VIN cross-source (V12) → `entity_matches`. Diferido a P1: fuzzy V21 (embeddings, `discovery_candidates` ya es exact-unique → dedup determinista da 0) y tabla `entities` (acoplada a `vault_dek_id`/KYC).

**Hazard del entorno:** hay branch-flipping + auto-commit hook que me movió entre `feature/p0-rewire`↔`feature/p0-rewiring` a mitad de sesión y committeó solo. Verificar rama antes de cada commit.
