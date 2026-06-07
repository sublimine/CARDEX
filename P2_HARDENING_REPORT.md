# P2 HARDENING REPORT — cabos sueltos cerrados

**Misión:** cerrar los P2 acumulados que Guardian documentó. Solo código; **no toca
`discovery_candidates`** (el barrido A sigue activo ahí), ni docker, ni migración en vivo.
**Rama:** `feature/p2-hardening` desde `main 6219527`, en **worktree aislado**
(`C:/Users/elias/projects/cardex-p2-hardening`) — sin tocar el working tree principal ni
el de `discovery-scale`. **Sin push.** **Fecha:** 2026-06-07.
**Suite:** baseline `1354 passed` → final **`1366 passed, 0 failed`** (+12 tests, cero
regresiones). Tests de integración (PG real) sobre **tablas throwaway aisladas**, nunca
`discovery_candidates`.

---

## Ítem 1 — Trigger de auto-remediación (dealer-scraping)
**Problema:** el harvester calculaba `drift = drift_gate.evaluate_volume(...)` y guardaba
`drift_ok`, pero **nunca llamaba `remediate()`** — la capacidad existía dormida
(`remediation.py` real, solo invocado por tests).

**Fix de raíz:**
- `harvester.harvest_dealer` recibe un callback **`remediator` inyectable**; cuando el
  drift gate falla y hay remediator, dispara la reparación **en el flujo** y registra el
  resultado en `result.remediation`. Inyectable (no import directo) para evitar el ciclo
  `remediation → harvester` y para que la revalidación interna de `remediate` (que llama
  `harvest_dealer` SIN remediator) **no recurse**.
- `remediation.make_remediator(...)` enlaza `remediate` al callback que el harvester espera.
- El driver de producción `scripts/run_dealer_scraping.py` lo cablea por defecto:
  `harvest_dealer(..., remediator=make_remediator(static, e07, seam, purger, limit))`.

**Tests (`test_dealer_harvester.py`):**
- `test_harvest_triggers_remediation_when_drift_trips` — recipe con `expected_min_volume=100`
  guardada, harvest de un sitio con 2 listings → drift falla → el remediator se invoca con
  `(domain, country)` y el resultado se adjunta. ✅
- `test_harvest_no_remediation_when_healthy_or_unwired` — harvest sano (baseline=discovered)
  NO llama al remediator; sin remediator cableado el drift queda dormido sin crash. ✅
- Verificado: `13 passed` (harvester+remediation), sin ciclo de import.

## Ítem 2 — Anti-FP a 6 idiomas + endurecer nombre genérico (domain-resolution)
**Problema:** `_NON_DEALER_RE` cubría pocos idiomas/categorías; y el FP residual
`Artcar → bmwartcarcollection.com` (el token corto "artcar" colándose por SUBSTRING en un
sitio de colección BMW no relacionado).

**Fix de raíz (`validate.py`):**
- `_NON_DEALER_RE` ampliado a **6 idiomas** (DE/FR/ES/IT/NL/EN) y a **parts/body shops**:
  driving schools (fahrschule, auto-école, autoescuela, **rijschool**, **scuola guida**),
  rental, museum, airport, travel agency, y **spare-parts** (ersatzteile, autoteile,
  **ricambi**, **recambios**, repuestos, onderdelen, pièces détachées).
- **Match de nombre por PALABRA COMPLETA** (`\b`), no substring → un token corto del dealer
  ya no puede montar una marca mayor no relacionada. Cierra `Artcar`→`bmwartcarcollection`.

**Tests (`test_domain_resolution.py`):**
- `test_non_dealer_six_languages_and_parts_shops` — 10 títulos no-dealer en 6 idiomas
  rechazados; un título de dealer real NO. ✅
- `test_name_match_is_whole_word_not_substring` — "Artcar" NO valida contra "bmw art car
  collection" (`name_not_on_page`); sí valida contra "Artcar Tuning". ✅
- Verificado: `31 passed`.

## Ítem 3 — Tests de la capa concurrente del worker (domain-resolution)
**Problema:** el `FOR UPDATE SKIP LOCKED` claim + el collision-merge (lo más sensible) no
tenían cobertura.

**Tests nuevos (`test_domain_resolution_worker.py`):**
- `test_resolve_one_promotes_when_domain_free` — PROMOTE ocurre cuando el dominio está libre. ✅
- `test_resolve_one_collision_merges_not_crashes` — `UniqueViolation` en PROMOTE →
  **collision-merge** (no crash, no invención), `stats.collided==1`. ✅ (pool + sesión fakes,
  sin PG ni red).
- `test_resolve_one_marks_fail_with_granular_reason_when_no_candidate` — MARK_FAIL con razón. ✅
- `test_skip_locked_claim_is_disjoint_under_concurrency` — **PG real, tabla throwaway
  `_p2_claim_probe`** (creada+dropeada, NUNCA `discovery_candidates`): 3 claimers concurrentes
  reclaman las 60 filas **exactamente una vez** y **disjuntas** (prueba real de SKIP LOCKED). ✅
- Verificado: `4 passed` (incl. el de integración contra PG).

## Ítem 4 — P1 reclaim anti-churn + migración blindada
**4a — reclaim XAUTOCLAIM (A6 `enrich_worker`):**
- **Cap de entregas / DLQ anti-churn:** un mensaje reclamado demasiadas veces
  (`times_delivered > MAX_DELIVERIES`, leído vía XPENDING) se **parquea en DLQ + ACK** en vez
  de re-encolarse para siempre. Reintentos acotados, sin churn infinito.
- **`try/except` por-mensaje** en el reclaim (como ya tenía A7): un mensaje reclamado que
  vuelve a fallar **no mata el loop** (se cuenta transient, sigue).
- Helpers `_delivery_counts` (XPENDING, tolerante a ambas formas de redis-py) y `_sid`.

**Tests (`test_enrich_worker.py`):**
- `test_reclaim_dlqs_message_past_max_deliveries` — entrega `MAX_DELIVERIES+1` → DLQ + ACK,
  `stats.dlq==1`, NO reprocesado. ✅
- `test_reclaim_isolates_a_raising_message` — `process_message` que lanza → aislado, loop
  sobrevive, `stats.transient==1`. ✅
- Verificado: `38 passed` (A6+A7).

**4b — `scripts/migrate_vehicle_events_partition.sql`:** envuelta en **`BEGIN;` … `COMMIT;`**
explícitos → atomicidad/abort-safety **independiente del flag** `--single-transaction`.

**Tests (`test_migration_partition.py`):**
- `test_migration_is_explicitly_transactional` — el archivo abre con `BEGIN`, cierra con
  `COMMIT`, y el `RAISE EXCEPTION` de verificación queda entre ambos. ✅
- `test_explicit_begin_commit_rolls_back_on_failure_without_flag` — **PG real, tabla
  throwaway** (la migración real NUNCA se ejecuta — renombraría `vehicle_events` de prod):
  un `BEGIN/…/RAISE/COMMIT` ejecutado **sin** `--single-transaction` hace rollback completo
  (la tabla no queda) → prueba que el patrón, no el flag, da abort-safety. ✅

## Ítem 5 — Conteos de tests stale en docs
**Hallazgo:** los reportes de misión citan conteos **point-in-time** (P0 1232, P1 1263, E07
1273, FANOUT 1274, DEALER 1324, DOMAIN_RES 1303/1313…) — correctos en su contexto histórico;
**no se falsifican**. Lo genuinamente stale (afirmación en presente, ahora falsa): dos docs
de auditoría declaraban un **"1 failed" pre-existente** como regression-gate vivo, y ya no
existe (suite actual **1366 passed, 0 failed**).

**Fix (anotación dada, preservando el registro):**
- `docs/PYTHON_SCRAPER_AUDIT_2026-06.md` y `docs/MULTI_STRATEGY_PORTALS_2026-06.md`: nota P2
  con la corrección (fallo resuelto; suite actual 1366/0).
- `DEALER_SCRAPING_REPORT.md`: el comando runnable `# 1324 passed` actualizado al estado
  actual (1366 tras merge de domain-resolution + P2).
- Docs vivos (`STATUS.md`/`CONTEXT_FOR_AI.md`) no citan conteos → nada que corregir ahí.

---

## Verificación global
- **Suite:** `python -m pytest scrapers/tests/ -q` → **1366 passed, 0 failed** (1354 → +12).
- Integración (SKIP LOCKED claim, abort-safety de migración) corre contra PG real en tablas
  **throwaway aisladas**; `discovery_candidates` jamás tocada.
- `py_compile` OK en módulos y driver editados.
- `main`, segundo checkout, worktree `discovery-scale`, docker: intactos. Sin push.

## Cómo correr
```bash
python -m pytest scrapers/tests/ -q                                   # 1366 passed
python -m pytest scrapers/tests/test_dealer_harvester.py \
                 scrapers/tests/test_domain_resolution.py \
                 scrapers/tests/test_domain_resolution_worker.py \
                 scrapers/tests/test_enrich_worker.py \
                 scrapers/tests/test_migration_partition.py -q        # los 5 ítems
```
