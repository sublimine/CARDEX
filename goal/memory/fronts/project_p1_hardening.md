---
name: project_p1_hardening
description: Punch-list P1 (GUARDIAN §9) ejecutado en rama feature/p1-hardening; fugas cerradas antes del seam a escala
metadata: 
  node_type: memory
  type: project
  originSessionId: 3580463c-4ae4-408a-9d01-af8872ba2a62
---

GUARDIAN §9 punch-list cerrado en rama `feature/p1-hardening` (commit `a980b3f`, desde main `830bf5d`; NO pusheado, main intacto). Suite **1263 verde**. Ver `P1_HARDENING_REPORT.md`. Continúa [[project_nl_vertical]] / [[project_p0_execution_state]].

**H1 reclaim:** `reclaim_pending()` (XAUTOCLAIM) en `enrich_worker` (A6) y `rich_consumer` (A7), un pase por iteración (idle>`*_RECLAIM_IDLE_MS` 60s) antes del read `>`; tombstones se ACK-ean. Idempotente. E2E real: PEL 1→0.

**Moneda CH:** `fx_eur.country_currency(country)` (CH→CHF, resto EUR); `rich_consumer`/`indexer` usan `currency_raw or country_currency(country)` (nunca default EUR para CH); `FX_RATE_CHF` en compose servicio `pipeline`; 212.524 filas CH `vehicle_index` corregidas EUR→CHF (datos vivos).

**PG salud:** `vehicle_events` tenía `autovacuum_enabled=false` en ensure_schema Y init-pg → planner ciego; corregido + ANALYZE. **Particionada** RANGE-mensual vía `scripts/migrate_vehicle_events_partition.sql` (transaccional, rename-no-drop, verificación de conteo que aborta; 539.259 preservadas, backup `vehicle_events_old` retenido — dueño lo borra). Helper `ensure_month_partition`/`ensure_event_partitions` en indexer + DEFAULT partition. PK ahora (event_id, ts); event_id es GENERATED IDENTITY.

**Drift-gate cableado:** `drift_gate.evaluate_volume` (solo-volumen, sin falsa-alarma por campos) + `coordinator.check_volume_drift` en `_process_item` → WARNING por origen si harvest < baseline de la config. Opt-in por `configs/portals/<domain>.json` (baseline prod=1000 en autotrack/viabovag). Auto-pausa/DLQ = P2.

**Scope camiones:** truckscout24 = 72.225 camiones DE purgados (index+events, igualdad exacta); `portals.NON_CAR_PORTALS` + `is_car_portal()`; coordinator `_process_item` marca done sin harvest si no es car-portal. El scraper SIGUE registrado (tests intactos).

**Estado PG:** vehicle_index=436.114 (tras purga), vehicle_events particionada, CH=CHF, vehicles=30 seed. Las fugas están cerradas → backfill 508K + seam sostenido ya pueden correr.

**GUARDIAN audit verdict (2026-06-07, `GUARDIAN_REPORT_P1_2026-06-07.md`):** los 5 ítems VERIFICADOS empíricamente (conteos exactos, set-diff, E2E, file:line) — sin pérdida de datos ni colateral. Partición: 539.259 preservadas + backup `_old` intacto; déficit 467.034 = exactamente los 72.225 camiones (set-diff: new⊂old, 100% truckscout24), recuperable. CH 212.524 CHF sin fuga a no-CH; `40000 CHF×1.05=42000 EUR` coherente. Drift realmente cableado (bug "0 callers" corregido). Guard = frozenset 1 miembro, match exacto. **Recomendación: GO, FF-merge a main (0/1, 1263 verde, aditivo).** 2 brechas P2 NO bloqueantes: (a) reclaim sin cap max-delivery → entrada permanentemente-transient (dominio sin identidad→fetch_error) hace livelock indefinido + A6 reclaim sin try/except (A7 sí); (b) `migrate_vehicle_events_partition.sql` no embebe BEGIN/COMMIT → atomicidad depende del flag `--single-transaction`. Bonus risk: portales CH no exponen JSON-LD (autolina dlq=2) → el 41,8% del índice no enriquece sin E07.
