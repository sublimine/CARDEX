# GUARDIAN — Auditoría E07 (Playwright browser extractor)

**Auditor:** GUARDIAN · **Conducida:** 2026-06-07 · **Modo:** SOLO LECTURA (sesión de barrido de discovery a escala en paralelo en worktree `cardex-discovery-scale` — NO toqué `discovery_candidates` ni docker; auditré inventario + código E07)
**Rama auditada:** `feature/e07-playwright-xhr` @ `7e16152` · **main** @ `6e0be32` · **base común** `a980b3f`
**Relación:** diverge **1/1** (NO fast-forward); **archivos disjuntos del fanout → merge 3-way LIMPIO** (verificado)
**Fuente:** `E07_REPORT.md`
**Método:** re-ejecución E2E del harness sobre inventario (purgado), `git diff`/`merge-tree`, lectura de código, 1 subagente read-only. Cada "hecho" atacado.

> `[V]` = VERIFICADO (comando citado). Foco: integridad del seam estático + escalabilidad del headless.

---

## 0. Resumen ejecutivo — ¿lista para consolidar?

**Sí, vía merge 3-way (NO es FF).** E07 desbloquea el inventario JS/SPA con un vector **genérico** (SEO-meta tras render), es **opt-in por config**, **no reescribe el seam** (A6 solo extendido aditivamente, preserva el reclaim de P1), contrato idéntico, **suite 1273 verde**, y E2E **re-verificado por mí** (autolina.ch 0→3, CHF→EUR exacto). El merge a `main` es **limpio** (merge-tree exit 0, 0 conflictos; archivos disjuntos del fanout).

**Una brecha NO bloqueante (P2/pre-producción): el pool headless es un footgun a alta concurrencia** — sin cap propio, hereda `ENRICH_CONCURRENCY=20` → hasta 20 páginas Chromium (~1-2GB) en una VPS que ya OOMea. Debe acotarse **antes de activar E07 en producción** (no antes del merge: `e07_fetcher` aún no está cableado en el contenedor, el path estático no se ve afectado).

| Ítem | Veredicto |
|---|---|
| 1 · E07 extrae de SPA real (autolina) | 🟢 SOUND (re-run E2E mío) |
| 2 · No rompe path estático (opt-in) | 🟢 SOUND (A6 aditivo, P1 reclaim preservado) |
| 3 · Pureza/tests/meta-gana | 🟢 SOUND |
| 4 · Drift para E07 | 🟢 SOUND (strategy-agnostic por config) |
| 5 · Eficiencia headless pool | 🟡 RISK/FOOTGUN (cap concurrencia E07) |
| Regresión | 🟢 1273 passed, 0 failed |
| Merge 3-way | 🟢 LIMPIO (0 conflictos) |

---

## 1. Ítems

### Item 1 · E07 extrae de SPA real — 🟢 SOUND [V, re-run independiente]
Re-ejecuté `scripts/verify_seam_e07.py --domain autolina.ch --country CH --limit 3` (redis throwaway, render Chromium real, inventario purgado, **sin tocar `discovery_candidates`**):
```
seeded=3 → A6(E07) emitted=3 dlq=0 transient=0 → ingestion_raw=3 → A7 persisted=3 errors=0
vehicles 30 → 33 → PURGED → 30 (restored)
  SKODA Kamiq 2025 29500.00 CHF → EUR 30975.00
  AUDI Q5     2020 37900.00 CHF → EUR 39795.00
  VW Polo     2022 18100.00 CHF → EUR 19005.00
```
Un SPA que con el seam estático daba `dlq=3` ahora rinde **3 fichas reales** vía SEO-meta tras render. **CHF→EUR exacto** (×1.05: 29500→30975, 37900→39795, 18100→19005). Contrato idéntico (mismas columnas `vehicles`), purgado. Vector **genérico** (parsea `og:title`+`<title>`+meta-description, sin selectores CSS por-portal).

### Item 2 · No rompe el path estático — 🟢 SOUND [V]
`git diff a980b3f..7e16152 -- enrich_worker.py`: el cambio es **puramente aditivo**:
- `_is_playwright_source(s)` = `cfg is not None and cfg.strategy in PLAYWRIGHT_STRATEGIES`.
- `enrich_one` rutea a `extract_listing_rendered` **solo si** `e07_fetcher is not None AND _is_playwright_source(s)`; **en cualquier otro caso → `extract_listing` estático** (default sin cambios). Doble guarda (config + fetcher inyectado).
- `process_message`/`reclaim_pending`/`run` solo añaden el param opcional `e07_fetcher` (default None).
- **El reclaim XAUTOCLAIM de P1 se PRESERVA** (sigue en `reclaim_pending`, solo threadea e07_fetcher) → un merge no regresaría P1. `coordinator.py`/`rich_consumer.py` **no tocados**. Seam contract idéntico.

### Item 3 · Pureza / tests / meta-gana — 🟢 SOUND [V]
- `parse_rendered_meta(html)→dict` y `record_from_rendered(...)→(VehicleRecord|None, reason)` **PUROS** (sin I/O; el navegador vive fuera, en `PlaywrightFetcher`).
- **Multilingüe:** labels km/año DE/FR/ES/NL/IT/EN (`Kilometer|Kilométrage|Kilómetros|…`, `Erstzulassung|Mise en circulation|Matriculación|…`); precio por token de moneda (lang-agnóstico), prefijo (`CHF 29'500`) y sufijo (`14 990 EUR`); separadores `'`/`.`/`,`/espacio normalizados.
- **Meta-gana CORRECTO (refutación fallida):** merge `{**static, **meta}` → meta sobrescribe, estático rellena huecos. Probado en vivo: el estático coge `mileage='600 '` (truncado en el `'` de `10'600`); meta lo corrige a `'10600'`. Invertir el merge sería el defecto → **evitado**. `Inserat-ID` no se fuga como precio/km.
- Edge cases: HTML vacío→`no_fields`; precio malformado→sin key, sin excepción; quality fail→reason. Sin raises.
- **Tests:** `test_playwright_extractor.py` = **10**, aserciones reales (incluido el guard exacto `mileage=="10600" not "600"`, y dispatch playwright→E07 / estático→estático con fetcher-trampa). Capa pura exhaustiva; el navegador es E2E-only (gap aceptable, pero **deja el footgun de concurrencia sin cubrir por CI**).

### Item 4 · Drift para E07 — 🟢 SOUND [V]
`configs/portals/autolina.ch.json` lleva `strategy=playwright_meta` + `drift_baseline` (`expected_min_volume:100`, `required_fields:[make,model,year,price]`, `min_nonnull_ratio:0.6`). `coordinator.py` **no tocado** → `check_volume_drift` de P1 se hereda y es **strategy-agnostic** (lee el baseline de config sin mirar la estrategia): `check_volume_drift("autolina.ch",5)→drift:volume(5<100)`. *(Matiz heredado de P1: el field/schema-drift de la salida E07 solo se evalúa en el harness, no en proceso always-on — no es regresión E07.)*

### Item 5 · Eficiencia — pool headless — 🟡 RISK/FOOTGUN [V]
- **Ciclo de vida CORRECTO:** un Chromium + un context en `__aenter__`, cerrados en `__aexit__`; **página nueva por fetch + `page.close()` en `finally`** (sin leak ni en error); `wait_until="domcontentloaded"`+settle 3500ms (no `networkidle`); nav timeout 40s (no cuelga indefinido).
- **FOOTGUN:** **no hay semáforo/pool de páginas propio** en `PlaywrightFetcher`; todos los llamantes concurrentes comparten el mismo context y abren hasta `ENRICH_CONCURRENCY` (default **20**) páginas Chromium simultáneas (~1-2GB RSS) sobre una VPS que **ya OOMea el coordinator** (memoria del proyecto). **Escalable solo a baja concurrencia (2-4).**
- **Cierre (P2, pre-producción):** semáforo dedicado dentro de `PlaywrightFetcher` o lane separada de baja concurrencia para fuentes playwright; tunear `ENRICH_CONCURRENCY` para E07 antes de cablear `e07_fetcher` en el contenedor.

---

## 2. Dimensiones estándar

| Dim | Veredicto | Evidencia |
|---|---|---|
| **Regresión** | 🟢 1273 passed, 0 failed | suite en el working tree e07 (1263+10) |
| **Higiene** | 🟢 limpia | merge-tree 0 conflictos; 2 worktrees legítimos (e07 + discovery-scale); no dejé artefactos (redis throwaway purgado); no toqué `discovery_candidates` |
| **Eficiencia** | 🟡 footgun headless | §Item 5 — cap de concurrencia E07 antes de producción |
| **Inventario** | 🟢 intacto | vehicles=30 SEED_DEMO tras purga; vehicle_index autolina 89.944 sin cambio |

---

## 3. Recomendación de consolidación — **GO (merge 3-way limpio)**

**Mergear `feature/e07-playwright-xhr` → `main` por merge 3-way (o rebase + FF).** No lo ejecuto.

- ✅ `[V]` **No es FF** (diverge 1/1), pero el merge 3-way es **LIMPIO**: `git merge-tree main e07` → exit 0, **0 conflictos**; archivos **disjuntos** de los del fanout ya en main; E07 toca `enrich_worker.py`/`config.py` que el fanout no tocó.
- ✅ `[V]` Aditivo, opt-in, **path estático intacto**, **reclaim P1 preservado**, contrato del seam sin cambios, **1273 verde**, E2E re-verificado.
- ✅ Sin riesgo de datos (E07 vive en el enrich-path; el harness purga; no escribe `discovery_candidates`).

**Mecánica sugerida (el working tree principal está ocupado por e07 y existe el worktree discovery-scale):** el orquestador puede mergear en un **worktree temporal sobre main** (`git worktree add tmp main; cd tmp; git merge feature/e07-playwright-xhr; pytest; …`) — la suite post-merge esperada es **~1284** (1274 de main+fanout + 10 de E07). O rebasear e07 sobre main y FF.

**Condición P2 (NO bloquea el merge; SÍ antes de activar E07 en producción):** acotar la concurrencia del pool headless (footgun OOM). El resto de pendientes del reporte (más configs `playwright_meta` por portal SPA, `playwright_xhr`, wire del `e07_fetcher` en el contenedor, tier-1 anti-bot→P3) son incrementos, no defectos.

**Estado de ramas en vuelo:** fanout ✅ merged (main=6e0be32); **e07 → recomendado merge ahora**; `feature/discovery-scale` (barrido activo) pendiente de su propia auditoría/merge.

---

*GUARDIAN — autointerrogatorio: ¿toqué lo prohibido? No — no toqué `discovery_candidates` (solo SELECT en `vehicles`/`vehicle_index` + harness que purga), no reinicié docker, no perturbé el worktree de discovery-scale. ¿Verifiqué ejecutando? Sí — re-run E2E real (render Chromium), suite, merge-tree, diffs. ¿Refuté cada hecho? Sí — meta-gana (refutado→evitado), A6 aditivo (P1 preservado), merge limpio (merge-tree), routing opt-in (doble guarda). La única brecha real: footgun de concurrencia headless. Fin.*
