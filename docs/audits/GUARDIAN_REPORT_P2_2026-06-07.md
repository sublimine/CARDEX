# GUARDIAN — Auditoría "P2 hardening" (cierre de los P2 acumulados)

**Auditor:** GUARDIAN · **Conducida:** 2026-06-07 · **Modo:** SOLO LECTURA (barrido cerrado; código + tablas throwaway, sin tocar datos de producción ni docker)
**Rama auditada:** `feature/p2-hardening` @ `d331f49` · **main** @ `7a03433` · **merge-base** `6219527`
**Relación:** diverge **6/1** (NO FF) · **3-way con main LIMPIO** (merge-tree exit 0, 0 conflictos)
**Fuente:** `P2_HARDENING_REPORT.md`
**Método:** verificación directa del orquestador (call-sites, word-boundary determinista, suite, merge-tree) + 1 subagente read-only (tests cola/reclaim/migración/docs). **Esta rama cierra los P2 que GUARDIAN mismo flageó** en las auditorías previas — verificación del bucle de cierre.

> `[V]` = VERIFICADO (comando citado). Cada "hecho" atacado adversarialmente.

---

## 0. Resumen ejecutivo — ¿lista para consolidar?

**Sí, vía merge 3-way (limpio).** P2 cierra **5/5** los cabos pendientes (incluidos los dos que GUARDIAN **refutó** en auditorías previas: trigger de remediación muerto y FP Artcar), con tests reales, **suite 1366 verde** y docs corregidos sin falsificar históricos. **Recomendación: MERGE 3-way a `main`.** No lo ejecuto.

**Único caveat (P2/P3, NO bloquea):** el fix anti-FP es **forward-only** — la fila histórica `Artcar→bmwartcarcollection.com` **sigue** en `discovery_candidates` (1 fila); conviene re-correr `revalidate.py` (que ya usa el gate word-boundary) para purgarla. Trivial.

| Ítem | Veredicto |
|---|---|
| 1 · Trigger auto-remediación cableado | 🟢 SOUND (mi refutación previa CERRADA) |
| 2 · Anti-FP 6 idiomas + word-boundary | 🟢 SOUND (fix real; fila histórica no purgada → P2) |
| 3 · Tests de cola contra PG real | 🟢 SOUND (SKIP-LOCKED real; collision-merge fake fiel) |
| 4 · Reclaim cap/DLQ + migración BEGIN/COMMIT | 🟢 SOUND (mis hallazgos P1 CERRADOS) |
| 5 · Docs stale corregidos sin falsificar | 🟢 SOUND |
| 6 · Regresión / higiene | 🟢 1366 verde, sin tmp_, 3-way limpio |

---

## 1. Trigger de auto-remediación REALMENTE cableado — 🟢 SOUND [V]
Call-site real `harvester.py:259-264`:
```python
if not drift.ok and remediator is not None:
    log.warning("drift on %s ... triggering remediation", ...)
    remediation = await remediator(domain, country)
```
Callback **inyectable** (`Remediator` type, `harvester.py:53`), no importado → sin ciclo `remediation→harvester`; la revalidación de remediation pasa `remediator=None` → **no recursa** (`harvester.py:201-204`). Caller de producción real: `run_dealer_scraping.py:36` (`make_remediator`) wired en el flujo (L144-154). **Tests [V]:** `test_harvest_triggers_remediation_when_drift_trips` (floor=100, 2<100 → `remediator.calls == [("dealer.example","DE")]`, `r.remediation["recovered"] is True`); `test_harvest_no_remediation_when_healthy_or_unwired` (sano → `remediator.calls == []`, `r.remediation is None`). → **Mi refutación previa ("código muerto, solo lo llaman tests") queda CERRADA**: hay caller real + dispara en drift / no dispara sano.

## 2. Anti-FP 6 idiomas + word-boundary — 🟢 SOUND (caveat P2) [V]
`validate.py` declara vocabulario "matched as WHOLE WORDS (`\b`)"; `_NON_DEALER_RE` ampliado a 6 idiomas. **Verificación determinista [V]:**
```
name_tokens("Artcar") = ['artcar']
naive-substring 'artcar' in 'bmwartcarcollection'      = True   (el bug viejo)
word-boundary  \bartcar\b in 'bmwartcarcollection'     = False  (el FIX)
candidate.py usa \b para el match de token            = True
```
→ el FP `Artcar→bmwartcarcollection.com` **no recurre** (el token deja de casar como substring dentro de la palabra larga).
**🟡 Caveat (P2/P3):** el fix es **forward-only** — la fila histórica `Artcar→bmwartcarcollection.com` **sigue persistida** en `discovery_candidates` (1 fila, `via=search:ddg`) [V]. P2 no re-corrió `revalidate.py` para limpiarla. **Recomendación:** correr `revalidate.py` (ya usa el gate word-boundary endurecido) → purgará esa fila y cualquier otro FP histórico residual. Coste trivial (1 comando), no bloquea el merge.

## 3. Tests de la cola del worker contra PG real — 🟢 SOUND (caveat honesto) [V]
`test_domain_resolution_worker.py` (4 tests):
- **`FOR UPDATE SKIP LOCKED` = PG REAL [V]:** `asyncpg.create_pool(_DSN)` (skip si PG caído), tabla throwaway aislada `_p2_claim_probe` (NUNCA `discovery_candidates`), 60 filas, **3 claimers concurrentes** → asserts **disjoint + exactly-once** (`sorted(a+b+c)==range(1,61)`, `set(a).isdisjoint(b)...`), `DROP TABLE` en `finally`.
- **collision-merge = fake fiel:** `_FakePool` lanza `UniqueViolationError` y asserta que el worker emite `DELETE FROM discovery_candidates` / `MARK_FAIL` — **nivel lógico (control-flow + SQL), no semántica PG**. El docstring lo **etiqueta honestamente** ("Tested with a fake pool ... no PG"). Las assertions son fieles al SQL real del worker. → No sobre-declara; transparente.

## 4. Reclaim cap/DLQ + migración transaccional — 🟢 SOUND [V] (cierra hallazgos P1)
**4a · A6 reclaim cap → DLQ + try/except (paridad A7) [V]:** `MAX_DELIVERIES=5` (env), lee el contador real `times_delivered` vía `XPENDING` (`_delivery_counts`); `> MAX_DELIVERIES` → `_to_dlq` (`xadd(DLQ)` **+** `xack` → sale del PEL) → **mata el poison-livelock**. Per-mensaje `try/except` (L395-399, "try/except like A7") → un mensaje malo no tumba el loop (paridad con `rich_consumer:430-434`); **A6 ahora SUPERA a A7** (A7 no tiene cap). Tests: `test_reclaim_dlqs_message_past_max_deliveries`, `test_reclaim_isolates_a_raising_message`. → **Mi hallazgo previo (sin cap → churn infinito + A6 sin try/except) CERRADO.**
**4b · Migración BEGIN/COMMIT [V]:** `migrate_vehicle_events_partition.sql` envuelto en `BEGIN;`(L19)…`COMMIT;`(L82) con `RAISE EXCEPTION` de row-count **dentro** → abort-safety **auto-contenida**, ya no depende de `--single-transaction`. Tests: estructural (asserta posiciones `BEGIN < ALTER < COMMIT` en el archivo real) + integración (rollback del **patrón** en throwaway `_p2_mig_probe` sin el flag → `to_regclass IS None`). **Caveat honesto (disclosed):** el test de rollback ejerce un script **sintético**, no el archivo real (que renombraría `vehicle_events` de prod — correctamente nunca se ejecuta); prueba el **mecanismo**, no el script específico end-to-end. → **Mi hallazgo P1 (SQL no auto-transaccional) CERRADO.**

## 5. Docs stale corregidos sin falsificar históricos — 🟢 SOUND [V]
3 docs tocados (`DEALER_SCRAPING_REPORT.md` + `docs/MULTI_STRATEGY_PORTALS_2026-06.md` + `docs/PYTHON_SCRAPER_AUDIT_2026-06.md`). Todas son **anotaciones fechadas point-in-time** que **preservan el número original** y añaden el estado actual con ancla de commit (p.ej. `# 1324 at this report's merge; 1366 on main after domain-resolution + P2 (2026-06-07)`; `[P2 update 2026-06-07] ... 1366 passed, 0 failed ... above is the point-in-time record`). Solo se corrige el único claim genuinamente stale-en-presente (el "1 failed gate" muerto). Los conteos históricos de los mission-reports (1232/1263/1324…) **no se reescriben** (son registros point-in-time, correctos en su contexto) — postura editorial defendible, no defecto. **Sin reescritura ni fabricación de históricos.**

## 6. Regresión + higiene — 🟢 [V]
- **Suite 1366 passed, 0 failed** (corrida por mí en worktree aislado). Conteos por-archivo verificados estáticamente (worker 4, migration 2, domain_resolution 31, harvester+remediation 13, A6+A7 38 con parametrize).
- **Sin `tmp_*` tracked** en `d331f49`; diff = sources + tests + 4 `.md`.
- Auditado en worktree detached propio (eliminado); `discovery_candidates` **solo SELECT** (1 fila Artcar leída).

---

## 7. Recomendación de consolidación — **GO (merge 3-way limpio)**

**Mergear `feature/p2-hardening` → `main` por merge 3-way.** No lo ejecuto.
- ✅ `[V]` NO es FF (diverge 6/1) pero **3-way LIMPIO** (`merge-tree` exit 0, 0 conflictos): p2 toca `harvester.py`/`validate.py`/`enrich_worker.py`/`migrate_*.sql` (de dealer/domain-res/P1, ya en main) pero **discovery-scale** —lo único que main ganó desde el merge-base— no tocó ninguno → disjunto.
- ✅ Cierra **5/5** los P2 acumulados (incluidos los 2 que GUARDIAN refutó), con tests reales, **1366 verde**, docs honestos.
- ✅ Sin riesgo de datos (código; los workers en runtime mantienen INSERT/heartbeat/UPDATE-only ya auditados).

**Caveats (P2/P3, NO bloquean):**
1. **Purgar la fila histórica `Artcar`** (`revalidate.py` con el gate word-boundary) — 1 fila residual; trivial. **(P2)**
2. Transparencia (ya disclosed en docstrings, no defectos): collision-merge testeado a nivel lógico (no PG), y el test de rollback de migración prueba el mecanismo (no el script real end-to-end). **(P3, opcional: test integración con el archivo real sobre tabla throwaway.)**

**Mecánica:** main no checked out → mergear en **worktree temporal sobre main** (`git merge feature/p2-hardening`); suite post-merge esperada **~1432** (1427 main + ~5 netos de p2; los conteos de p2 ya incluyen tests de dealer/domain-res que solapan con main, así que validar el número exacto post-merge).

**Cierre de la jornada:** con este merge, `main` queda con los **7 frentes** (P0+P1+fanout+E07+dealer+domain-res+discovery-scale+P2-hardening). Es el último pendiente. `origin/main` sigue en `6e084a5` (sin push — decisión del dueño).

---

*GUARDIAN — autointerrogatorio: ¿toqué prod? No — `discovery_candidates` solo SELECT, sin docker, worktrees activos intactos (detached propio eliminado). ¿Verifiqué ejecutando? Sí — call-site remediación + 2 tests, word-boundary determinista, suite 1366, merge-tree, BEGIN/COMMIT + cap en código. ¿Refuté cada hecho? Sí — y los DOS que refuté en auditorías previas (trigger muerto, FP Artcar) ahora resisten: trigger cableado con caller real, word-boundary rechaza el substring. Único residual: la fila histórica Artcar (forward-only fix) → P2. Nada bloqueante. Fin de la auditoría P2 y de la jornada de consolidación.*
