# P1 HARDENING — Execution report (GUARDIAN §9 punch-list)

**Fecha:** 2026-06-07 · **Rama:** `feature/p1-hardening` (desde `main @ 830bf5d`) · NO push · main intacto
**Fuente:** `GUARDIAN_REPORT_2026-06-06.md` §9 (cerrar fugas antes de correr el seam a escala).
**Disciplina:** validate-con-límite-y-purgar en pruebas; suite verde; evidencia por ítem.

> Cada cifra es `[VERIFICADO]` (salida de comando). Lo poblado para validar se purgó.
> No se tocó el segundo checkout ni el Block0 hazard. Suite: **1263 passed, 0 failed**.

---

## Resumen

| # | Ítem (H/P) | Estado | Evidencia clave |
|---|---|---|---|
| 1 | Fuga del PEL Redis (H1) — sin reclaim | ✅ | XAUTOCLAIM en A6+A7; E2E real: PEL 1→0 |
| 2 | Moneda CH mal-etiquetada (41,8% EUR→CHF) | ✅ | 212.524 corregidas; CHF→EUR E2E; FX_RATE_CHF |
| 3a | Autovacuum nunca corrió (planner ciego) | ✅ | ANALYZE; planner pasa de 0/189K a 211.977 real |
| 3b | vehicle_events sin particionar | ✅ | RANGE-mensual; 539.259 preservadas; pruning OK |
| 4 | Drift-gate construido pero desconectado | ✅ | cableado al coordinator (`check_volume_drift`) |
| 5 | 72.225 camiones truckscout24 en DE | ✅ | purgados; scope guard `NON_CAR_PORTALS` |

---

## 1 · Fuga del PEL Redis (H1) — reclaim XAUTOCLAIM

**Problema [VERIFICADO]:** A6 (`enrich_worker`) y A7 (`rich_consumer`) leían solo `>` (mensajes
nuevos). Un mensaje leído y no-ACK (fallo transitorio / crash) quedaba en el PEL del grupo
**para siempre** — `XREADGROUP '>'` nunca lo re-entrega → pérdida silenciosa a escala.

**Fix:** `reclaim_pending()` en ambos consumidores — un `XAUTOCLAIM` por iteración (idle >
`*_RECLAIM_IDLE_MS`, default 60s) reprocesa las entradas varadas antes de leer nuevas;
tombstones (entradas borradas) se ACK-ean para limpiar el PEL. Idempotente (A7 dedup por
fingerprint; A6 por url_hash) → reprocesar nunca duplica.

**Evidencia E2E (Redis 7 real):**
```
PEL before reclaim: 1            # mensaje leído por c1, sin ACK
reclaimed=1 persisted=1 vehicles 30->31
PEL after reclaim: 0            # drenado · purgado → 30
```
Tests: `test_reclaim_pending_reprocesses_stranded_entry`, `test_reclaim_tombstone_is_acked` (A6+A7).

---

## 2 · Moneda CH (41,8%) — CHF + FX_RATE_CHF

**Problema [VERIFICADO]:** 212.524 filas CH en `vehicle_index` con `moneda='EUR'` (el default de
columna) cuando el mercado CH cotiza en **CHF**; `fx_eur` sin `FX_RATE_CHF` → precio EUR NULL.

**Fix:**
- `fx_eur.country_currency(country)` → CHF para CH, EUR para el resto del fleet.
- `rich_consumer` (donde se escribe el precio L2): `currency = currency_raw or country_currency(country)`
  — nunca el default EUR para CH (el fix del 41,8% en el punto de escritura).
- `indexer` (L1): `moneda` country-correcta en el INSERT (defensa).
- `docker-compose.yml`: `FX_RATE_CHF=${FX_RATE_CHF:-1.05}` en el servicio `pipeline`.
- **Datos existentes:** `UPDATE vehicle_index SET moneda='CHF' WHERE country='CH'` → 212.524 filas
  (DE/NL siguen EUR; VACUUM tras el churn).

**Evidencia E2E (PG vivo, `persist_one` + FX_RATE_CHF=1.05):**
```
ROW: make=BMW model=X3 currency_raw=CHF price_raw=40000.00
     gross_physical_cost_eur=42000.00 source_country=CH      # 40000 CHF × 1.05 → purgado
```
Tests: `test_country_currency_ch_is_chf_rest_eur`, `test_ch_listing_without_currency_defaults_to_chf_not_eur`,
`test_nl_listing_without_currency_defaults_to_eur`.

> El `1.05` es un mid placeholder (override con la tasa ECB del día vía `FX_RATE_CHF`); `fx_eur`
> nunca inventa una tasa para una moneda desconocida (fail-closed → EUR NULL).

---

## 3 · Salud PG

### 3a · Autovacuum / ANALYZE (planner ciego)
**Problema [VERIFICADO]:** `vehicle_events` creada `WITH (autovacuum_enabled=false)` (en
`indexer.ensure_schema` **y** `init-pg.sql`); ninguna tabla analizada nunca → planner ve
`n_live_tup=0`.

**Fix:** `ALTER TABLE vehicle_events SET (autovacuum_enabled=true)` + `ANALYZE` de las 4 tablas
core + índice `ts`; corregida la fuente (ambos sitios) para que un DB fresco no nazca ciego.

**Evidencia [VERIFICADO]:**
```
EXPLAIN ... country='CH'  rows  189062 → 211977   (real 212524)
n_live_tup: vehicle_index=508339, vehicle_events=539259, discovery_candidates=460378 (analyzed=t)
```

### 3b · Partición de vehicle_events (RANGE mensual)
**Problema [VERIFICADO]:** append-only ilimitado (~2M SEEN/mes), heap único → time-range = full
scan; `idx_ve_hash` crece sin techo.

**Fix:** migración transaccional `scripts/migrate_vehicle_events_partition.sql` (rename-no-drop +
parent PARTITION BY RANGE(ts) + DEFAULT + meses 2026-06/07/08 + copy + setval + **verificación de
conteo que aborta (rollback) si no cuadra**). Scratch-validada antes (routing + pruning). Aplicada
con `--single-transaction` (sin escritores concurrentes). `init-pg.sql` + `ensure_schema`
particionados (fresh) + helper de mantenimiento mensual `ensure_month_partition`/
`ensure_event_partitions` (current+next, con DEFAULT como red de seguridad).

**Evidencia [VERIFICADO]:**
```
NOTICE: vehicle_events partition migration OK: 539259 rows preserved
relkind=p · new=539259 · old_backup=539259 · todas en vehicle_events_2026_06
insert nuevo → vehicle_events_2026_06 · time-range query → Bitmap Index Scan on
  vehicle_events_2026_06_ts_idx (pruning a 1 partición)
ensure_schema idempotente sobre la tabla particionada (relkind=p, 4 particiones)
```
Tests: `test_month_bounds_*`, `test_ensure_month_partition_emits_correct_ddl`,
`test_ensure_event_partitions_covers_current_and_next`.
> `vehicle_events_old` (539K) queda como **backup**; el dueño lo borra tras su verificación.

---

## 4 · Drift-gate cableado a proceso vivo (coordinator)

**Problema [VERIFICADO]:** el config-store + drift-gate (`830bf5d`) existían y pasaban tests pero
**0 callers** en coordinator/workers — la única señal de drift en prod era "cosecha == 0".

**Fix:** `drift_gate.evaluate_volume(cfg, volume)` (solo-volumen, para el caller L1 que no tiene
campos → nunca falsa-alarma por campos ausentes) + `coordinator.check_volume_drift(domain,
url_count)` cableado en `_process_item`: tras cada harvest OK, si el volumen cae bajo el baseline
versionado del portal → **WARNING por origen** ("portal may have changed, repair
configs/portals/<domain>.json"). Opt-in por config. Baselines de producción (1000) en
autotrack/viabovag. La ruta de verificación (`verify_seam_redis`) ya ejercita las dimensiones
SCHEMA+FIELD sobre muestra; el coordinator añade la dimensión VOLUME siempre-activa.

**Evidencia:** tests `test_evaluate_volume_only_for_coordinator`, `test_check_volume_drift_*`
(alert<baseline, ok>baseline, None sin config). Detección por-origen viva en el coordinator.
> Auto-pausa/DLQ automáticos en `alert` quedan como escalón P2 (tras tunear baselines por portal);
> hoy la detección+alerta por origen funciona, que es la semilla pedida.

---

## 5 · Camiones truckscout24 fuera del scope coche

**Problema [VERIFICADO]:** `truckscout24.com` = 72.225 filas DE (`/tsp/ts-*` = camiones), no
turismos → contamina la vertical de coches y el scoring.

**Fix:**
- **Purga** (igualdad exacta, H2): 72.225 `vehicle_index` + 72.225 `vehicle_events` borradas;
  work_queue entry eliminada; VACUUM.
- **Scope guard durable:** `portals.NON_CAR_PORTALS` (frozenset) + `is_car_portal()`; el portal
  **sigue registrado** (scraper válido, futura vertical de camiones, tests intactos) pero el
  coordinator lo **marca done sin harvest** (`_process_item` scope guard) → nunca re-contamina.

**Evidencia [VERIFICADO]:**
```
DELETE 72225 (events) · DELETE 72225 (index) · DE_total 91420 → 19195 · vehicle_index 508339 → 436114
```
Tests: `test_non_car_portals_excludes_trucks`, `test_process_item_non_car_portal_skipped_without_harvest`.

---

## Cierre

- **Suite:** 1263 passed, 0 failed (1246 → +17). Cero regresiones.
- **Estado PG al cierre:** vehicle_events particionada (539.259, +backup), CH=CHF (212.524),
  truckscout24 purgado, autovacuum on, planner con stats reales. vehicles=30 (test data purgada).
- **Archivos:** `fx_eur.py`, `rich_consumer.py`, `enrich_worker.py`, `indexer.py`, `coordinator.py`,
  `portals/__init__.py`, `intelligence/drift_gate.py`, `docker-compose.yml`, `scripts/init-pg.sql`,
  `scripts/migrate_vehicle_events_partition.sql`, configs + 6 archivos de test. Rama
  `feature/p1-hardening`; main intacto en `830bf5d`.
- **Pendiente declarado (P2, no a medias):** auto-pausa/DLQ en drift alert (tras tunear baselines);
  tasa CHF ECB en vivo; A6 field/schema drift en streaming; drop de `vehicle_events_old` (dueño);
  proxies tier-1 (backlog). El backfill de los 508K + arranque sostenido del seam ya pueden correr
  con las fugas cerradas.

*Fin del reporte P1.*
