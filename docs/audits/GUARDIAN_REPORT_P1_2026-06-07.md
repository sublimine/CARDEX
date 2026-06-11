# GUARDIAN — Auditoría P1-hardening

**Auditor:** GUARDIAN · **Conducida:** 2026-06-07
**Rama auditada:** `feature/p1-hardening` @ `a980b3f` · **Base:** `main` @ `830bf5d`
**Relación:** **0 detrás / 1 delante → fast-forward limpio** (commit único)
**Fuente:** `P1_HARDENING_REPORT.md` (cierre del punch-list GUARDIAN §9)
**Método:** verificación empírica contra PG vivo (conteos exactos, set-diff), suite completa, E2E del seam, revisión de código adversarial (2 subagentes read-only + verificación directa del orquestador). Cada "hecho" del reporte fue **atacado** antes de darse por bueno.

> `[V]` = VERIFICADO (comando citado). `[A]` = ASUMIDO. Foco: alto riesgo de pérdida de datos.

---

## 0. Resumen ejecutivo — ¿lista para consolidar?

**Sí. Los 5 ítems del punch-list están cerrados con evidencia real, sin pérdida de datos ni daño colateral, suite 1263 verde.** La rama es aditiva, fast-forward, y `main` quedó intacta durante la auditoría. **Recomendación: MERGE a `main` (fast-forward).** No lo ejecuto — decisión del orquestador.

La revisión adversarial encontró **2 brechas NO bloqueantes** (refinamientos P2, sin pérdida ni corrupción): (a) el reclaim del PEL carece de cap max-delivery → una entrada permanentemente-transient hace *churn* indefinido; (b) el `.sql` de migración no auto-embebe la transacción (depende del flag `--single-transaction`). Ninguna afecta la integridad de los datos ya migrados.

| Ítem crítico | Veredicto | Pérdida de datos |
|---|---|---|
| 1 · Reclaim PEL (XAUTOCLAIM) | 🟢 idempotente / 🟡 RISK (sin cap retry) | **No** |
| 2 · Moneda CH (EUR→CHF) | 🟢 SOUND | **No** |
| 3a · Autovacuum / ANALYZE | 🟢 SOUND | **No** |
| 3b · Partición `vehicle_events` | 🟢 SOUND / 🟡 RISK menor (SQL no auto-transaccional) | **No (539.259 preservadas + backup)** |
| 4 · Drift-gate cableado | 🟢 SOUND | n/a |
| 5 · Purga camiones (72.225) | 🟢 SOUND (exacta, recuperable) | **No (cero colateral)** |

---

## 1. Ítems críticos — veredicto por ítem

### Item 1 · Reclaim del PEL (XAUTOCLAIM) — 🟢 idempotente / 🟡 RISK

**Idempotencia: SÓLIDA (no genera duplicados) [V].** `reclaim_pending` existe en A6 (`enrich_worker.py:294-332`) y A7 (`rich_consumer.py:404-438`), corre **antes** del read `>` cada iteración. No se pudo refutar la creación de duplicados:
- A7 dedup por `fingerprint_sha256` (`INSERT … ON CONFLICT DO UPDATE`) — re-persist = UPSERT, nunca fila nueva.
- A6 re-emite a `ingestion_raw` (entrada de stream duplicada) pero A7 la colapsa por fingerprint → dedup **aguas abajo** (matiz: el "A6 dedup by url_hash" del reporte es impreciso; el dedup real es 100% de A7).
- VIN-history: LISTING gated por `is_insert=(xmax=0)` (False en reclaim de fila existente) → sin duplicar; MILEAGE con `ON CONFLICT DO NOTHING`.
- Tombstones ACKeados (drena el PEL). Tests: `test_reclaim_pending_reprocesses_stranded_entry`, `test_reclaim_tombstone_is_acked`.
- E2E del reporte (PEL 1→0) coherente; mi re-run del seam (autotrack, 30→32, purgado) confirmó que el seam sobrevive el refactor.

**🟡 RISK — re-procesa indefinidamente para "poison" [V]:** NO hay cap max-delivery / DLQ-after-N (grep `delivery|max_retr|xpending` = 0 en ambos workers). Una entrada **permanentemente**-transient (p.ej. dominio T2/T3 sin identidad → `RuntimeError` tragado por `_safe_fetch` → `fetch_error` = transient → nunca ACK) se reclama en **cada** iteración para siempre (livelock: gasto CPU/fetch, PEL creciente). **Radio acotado: sin pérdida ni corrupción.** Además A6 reclaim/read **carece** del `try/except` por-mensaje que A7 sí tiene (`enrich_worker.py:366` vs `rich_consumer.py:430-434`) → un fallo Redis en A6 reclaim tumba su loop. **Plan P2:** cap de entregas → DLQ tras N; envolver A6 reclaim en try/except (simetría con A7).

> **Net:** P1 corrigió la fuga original (transient genuinos ahora se recuperan en vez de quedar varados para siempre). El churn de poison es una arista nueva, menor, sin impacto en datos.

### Item 2 · Moneda CH (EUR→CHF) — 🟢 SOUND

- **Datos existentes [V]:** `vehicle_index` CH=**CHF (212.524)**; BE/DE/ES/FR/NL siguen **EUR**; **0 filas CHF en países no-CH** (sin fuga). Exacto.
- **Lógica [V, determinista]:** `fx_eur.country_currency('CH')='CHF'`, resto `'EUR'` (`fx_eur.py:32-37`, case-insensitive/null-safe). `rich_consumer.py:180` = `currency_raw or country_currency(country)` → un listing CH sin moneda resuelve a CHF, nunca al default EUR.
- **gross_eur coherente [V]:** `to_eur(40000, 'CHF', {CHF:1.05}) = 42000.00`; `EUR→EUR` identidad; moneda desconocida → `None` (fail-closed, nunca inventa tasa).
- **Config [V]:** `docker-compose.yml:298` `FX_RATE_CHF: "${FX_RATE_CHF:-1.05}"`. Tests: `test_country_currency_ch_is_chf_rest_eur`, `test_ch_listing_without_currency_defaults_to_chf_not_eur`.

### Item 3a · Autovacuum / ANALYZE — 🟢 SOUND

- **[V]** `vehicle_index` (n_live_tup=436.114), `discovery_candidates` (460.378), `vehicles` (30) → todas `analyzed=t`. El planner ya tiene stats reales (antes veía 0 → estimaba `rows=1`).
- **Fuente corregida [V]:** `autovacuum_enabled=false` eliminado de **ambos** sitios (`init-pg.sql` + `indexer.ensure_schema`); grep repo-wide de `autovacuum_enabled` solo aparece en el reporte → un DB fresco ya no nace ciego.

### Item 3b · Partición `vehicle_events` — 🟢 SOUND / 🟡 RISK menor

- **Estado vivo [V]:** `relkind='p'`; particiones `default` + `2026_06/07/08`; `2026_06=467.034`, resto y `default=0` (suma = total, **nada varado en DEFAULT**); cada partición con `ts_idx` + `url_hash_idx` + `pkey(event_id,ts)`; ninguna con autovacuum=false.
- **Preservación [V]:** `vehicle_events_old` existe con **539.259** (backup intacto). La migración insertó las 539.259 (`n_tup_ins=539.260`); el guard de conteo pasó → commit honesto.
- **Migración [V]:** `migrate_vehicle_events_partition.sql` = rename-no-drop (sin DROP en el archivo), `PARTITION BY RANGE(ts)` + DEFAULT + meses, **`RAISE EXCEPTION` que aborta y revierte si `old_n≠new_n`** (líneas 67-76), `setval` correcto.
- **Fresh-install [V]:** `init-pg.sql:1111-1127` y `ensure_schema` (`indexer.py:109-134`) nacen particionados, idempotentes, autovacuum ON; helpers `ensure_month_partition`/`ensure_event_partitions` (current+next) con DEFAULT de red. Pruning verificado (time-range → Bitmap Index Scan a 1 partición). Tests `test_partition.py` (5).
- **🟡 RISK menor:** el `.sql` no embebe `BEGIN;/COMMIT;` — la atomicidad depende de ejecutar con `--single-transaction` (documentado en línea 11). Sin el flag, el RENAME podría commitear y un fallo posterior dejar la tabla a medias. **Plan P2:** envolver el archivo en `BEGIN;…COMMIT;` para que sea auto-enforcing.

### Item 4 · Drift-gate cableado al coordinator — 🟢 SOUND

- **Realmente llamado [V]:** `coordinator._process_item:336-342` invoca `check_volume_drift(domain, result.url_count)` tras cada harvest OK (el bug previo "0 callers" está **corregido**).
- **Sin falsas alarmas [V]:** retorna `None` cuando no hay config del portal (solo autotrack/viabovag tienen) → los ~70 restantes nunca alertan. `evaluate_volume` fija `fields_ok=True, schema_changed=False` (solo evalúa volumen) → no falsea por campos/schema ausentes.
- **Efecto [V]:** solo `log.warning` por origen; sin auto-pausa/DLQ (diferido a P2, declarado). Baselines `expected_min_volume=1000` en ambos JSON. Tests: `test_evaluate_volume_only_for_coordinator`, `test_check_volume_drift_*`.

### Item 5 · Purga camiones truckscout24 — 🟢 SOUND (exacta, recuperable)

- **Conteos exactos [V]:** `vehicle_index` 508.339→**436.114**; truckscout24=**0**; DE 91.420→**19.195** (= 91.420−72.225). `vehicle_events` −72.225 (truck events=0).
- **Cero colateral [V]:** otros portales **idénticos** al baseline (autolina 89.944, tutti 81.558, viabovag 80.800, autohero 19.195, vroom 17.983); por país solo cambió DE; **set-diff en events: `in_old_not_new=72.225, 100% truckscout24.com`, `new ⊂ old`** → solo se borraron filas de camiones, nada más. **Recuperable en `vehicle_events_old`.**
- **Guard durable [V]:** `NON_CAR_PORTALS = frozenset({"truckscout24.com"})` — **un solo miembro**, `is_car_portal` = membresía exacta (sin bug de substring); `_process_item` marca el portal `done` pre-harvest; truckscout24 **sigue registrado** (scraper válido para futura vertical camiones). No puede sobre-excluir un portal de coches.
- **Matiz de mecanismo [V]:** el delete se ejecutó vía `scrapers/cli/verify_direct_live.py:133` (delete por dominio); el resultado es exacto y la re-contaminación la previene el guard durable. **Plan P2 (opcional):** un script de purga dedicado/idempotente en vez del tool de verificación.

---

## 2. Dimensiones estándar

| Dim | Veredicto | Evidencia |
|---|---|---|
| **Cobertura** | 🟡 sin cambio (mejora de scope) | index 436.114 (−72K camiones, mejora de calidad, NO pérdida de coches); discovery 460.378 intacto; vehicles 30. **Bonus risk:** CH (212.524, 41,8%) **no expone JSON-LD** (autolina.ch dio dlq=2 en mi E2E) → el bloque CH no enriquecerá por la vía genérica sin E07. |
| **Datos** | 🟢 mejor que P0 | moneda CH ahora correcta (CHF); sin duplicados/corrupción. Persisten (P0-conocidos, fuera de alcance P1): index 100% atributo-NULL, vehicles=30 seed. |
| **Pipeline** | 🟢 seam vivo + endurecido | re-run E2E mío OK; reclaim añadido; sigue **dormido en prod** (esperado — el backfill es el siguiente paso, ya desbloqueado). |
| **Eficiencia** | 🟢 P1 cerró 3 deudas D4 | partición (D4-P2) + ANALYZE (D4-P1) + índice `ts` hechos. Abiertas (P2): `url_hash`→bytea, split make/model, índice `(country,precio,anio)`. |
| **Regresión** | 🟢 1263 passed, 0 failed | exacto al claim (1246→+17). Cero regresiones. |
| **Higiene** | 🟢 limpia | rama FF (0/1), árbol sin mods tracked. `vehicle_events_old` (539.259) = backup a dropear tras verificación del dueño (consideración de disco). Mi `GUARDIAN_REPORT_2026-06-06.md` sigue untracked (deliverable previo). |

---

## 3. Backlog (P2 — NO bloquean el merge)

1. **Reclaim:** cap max-delivery → DLQ tras N entregas (mata el livelock de poison); envolver A6 reclaim en try/except (simetría con A7).
2. **Migración SQL:** embeber `BEGIN;…COMMIT;` para auto-enforcing (hoy depende de `--single-transaction`).
3. **Enriquecimiento CH:** los portales CH no dan JSON-LD → el 41,8% del índice necesita E07 (playwright-XHR) o feed por dealer para enriquecer.
4. **Drift:** auto-pausa/DLQ en `alert` tras tunear baselines por portal; tasa CHF ECB en vivo; A6 field/schema drift en streaming.
5. **Purga camiones:** script dedicado idempotente (vs el tool de verificación).
6. **Backup:** dropear `vehicle_events_old` tras verificación del dueño (libera disco).
7. **Heredados de P0/D4:** `url_hash`→bytea, split make/model + GIN trigram, índice compuesto de búsqueda, poblar/parar ClickHouse, actualizar `CONTEXT_FOR_AI.md`, resolver Block0.

---

## 4. Recomendación de consolidación — **GO (fast-forward)**

**Mergear `feature/p1-hardening` → `main` por fast-forward.** No lo ejecuto.

- ✅ `[V]` 0 detrás / **1 delante** → FF sin conflictos; `main` intacta en `830bf5d`; árbol limpio.
- ✅ `[V]` Suite **1263 verde, 0 regresiones**.
- ✅ `[V]` **Sin pérdida de datos:** 539.259 events preservadas + backup; purga de camiones exacta y recuperable; CH currency sin fuga; particiones cubren todo el dato.
- ✅ Cierra **5/5** ítems del punch-list GUARDIAN §9 con evidencia, **endureciendo las fugas antes del backfill** (que ya puede correr).
- ⚠️ Las 2 brechas (reclaim cap, SQL transaccional) son **P2 no bloqueantes** — sin impacto en integridad de datos; cerrarlas antes de operar la fleet a gran escala T2/T3 (donde el poison-churn del reclaim importaría).

**No leer como hecho:** sigue siendo un esqueleto (index atributo-NULL, vehicles=30 seed, seam dormido); P1 **endureció la fontanería**, no pobló el producto. El bloque CH no enriquecerá sin E07.

**Independiente del merge:** dropear `vehicle_events_old` (tras verificación) y resolver el Block0 — decisiones del dueño.

---

*GUARDIAN — autointerrogatorio: ¿afirmé algo sin verificar? No — conteos exactos por comando, set-diff para la purga, E2E para el seam, lectura file:line para el código. ¿Refuté cada "hecho"? Sí — reclaim (refutado: livelock de poison), migración (refutado: no auto-transaccional), guard/drift/currency (no refutables → verde). ¿Toqué main/prod más allá de lectura + redis throwaway purgado? No. Fin.*
