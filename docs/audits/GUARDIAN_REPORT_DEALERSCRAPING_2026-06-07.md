# GUARDIAN — Auditoría "sistema de scraping a medida por dealer" (frente C)

**Auditor:** GUARDIAN · **Conducida:** 2026-06-07 · **Modo:** SOLO LECTURA (DOS sesiones escribiendo `discovery_candidates` en paralelo — resolución de dominio + barrido — NO toqué esa tabla ni docker; auditré inventario + código frente C)
**Rama auditada:** `feature/dealer-scraping-system` @ `72b31d5` · **main** @ `b980f90` · **merge-base** = `b980f90`
**Relación:** **0 detrás / 1 delante → HOY es FF-able** (main es ancestro; será 3-way solo si otra rama mergea antes)
**Fuente:** `DEALER_SCRAPING_REPORT.md` + `sweep_random.json` + `dealer_yielders.json` + `configs/dealers/*.json`
**Método:** re-ejecución E2E sobre inventario (purgado), suite en worktree detached aislado, lectura de código vía `git show` (sin checkout — 3 sesiones activas), 2 subagentes read-only, `git grep`. Cada "hecho" atacado.

> `[V]` = VERIFICADO (comando citado). Foco: las 4 correcciones HIGH de seguridad + honestidad del yield + RAM-safety.

---

## 0. Resumen ejecutivo — ¿lista para consolidar?

**Sí.** El sistema construye scraping a-medida-pero-config-driven por dealer, **reusa el seam sin reescribirlo**, las **4 correcciones HIGH de seguridad están aplicadas y son sólidas**, es **RAM-safe**, el yield ~3% es **honesto** (ruido de censo, no fallo del extractor), y la **suite queda en 1325 verde**. E2E **re-verificado por mí** (15 coches reales con límite 5, purgado). **Recomendación: MERGE a `main`** (hoy FF; 3-way limpio si procede). No ejecuto el merge.

**Una refutación parcial (P2, NO bloquea):** la **auto-remediación existe y es real pero su trigger NO está cableado** — el harvester detecta drift (`drift_ok`) pero nunca llama `remediate()`; solo los tests lo invocan. El reporte dice "cableados" → sobredeclara: detección sí, acción no.

| Ítem | Veredicto |
|---|---|
| 1 · E2E real (dealers → vehicles, purga) | 🟢 SOUND |
| 2 · Config por dealer aditiva (no reescribe seam) | 🟢 SOUND |
| 3 · Drift + auto-remediación | 🟡 PARCIAL (remediación real, **trigger no cableado**) |
| 4 · Honestidad del yield ~3% | 🟢 HONESTO |
| 5 · 4 correcciones HIGH de seguridad | 🟢 4/4 SOUND |
| 6 · Regresión / RAM-safe / higiene | 🟢 1325 verde, RAM-safe |

---

## 1. E2E real — 🟢 SOUND [V, re-run independiente]
`run_dealer_scraping --domains "dacia-meaux.fr:FR,nissan-epernay.fr:FR,mercedes-benz-compiegne.fr:FR" --limit 5` (redis throwaway, **`--domains` explícitos → NO lee `discovery_candidates`**; script solo borra `vehicles`/`vin_history_cache` en la purga):
```
dacia-meaux.fr              sitemap_listing  disc=17  persisted=5  YIELDS
nissan-epernay.fr           sitemap_listing  disc=48  persisted=5  YIELDS
mercedes-benz-compiegne.fr  jsonld_detail    disc=34  persisted=5  YIELDS
yield_rate=1.0 inventory=15 · vehicles 30 -> 30 (purge_restored=True)
```
Coches reales cruzan **todo el seam** (A6→`ingestion_raw`→A7→`vehicles`+`vin_history`+`meili_sync`), medidos y **purgados exacto** → inventario restaurado a 30 `[V]`. (Con `--limit 8` = 24 como el reporte.) **El sistema rinde inventario real vía el seam existente.**

## 2. Config por dealer aditiva — 🟢 SOUND [V]
`git diff b980f90..72b31d5 -- portals/config.py` es **puramente aditivo**: nuevo `_DEALER_DIR` + `_dealer_path` + `load()` busca `(_config_path, _dealer_path)` (portal curado primero, dealer fallback) + `save(kind=)`/`list_configs(kind=)` con default backward-compatible. El store curado `_config_path` intacto. `configs/dealers/*.json` versionados (`version:1`, strategy ∈ STRATEGIES, drift_baseline). **El seam lo resuelve nativo:** `enrich_worker._is_playwright_source` llama el MISMO `portal_config.load()` → cero cambio en el seam. **`enrich_worker`/`rich_consumer` ausentes del diff** [V].

## 3. Drift + auto-remediación — 🟡 PARCIAL (refutación parcial) [V]
- **Detección de drift: CABLEADA por dealer** — cada config lleva `drift_baseline.expected_min_volume` (refinado al volumen real por `_refine_baseline`); `harvester` evalúa `drift_gate.evaluate_volume(cfg, discovered)` por dealer (`harvester.py:241`).
- **`remediation.py` es REAL, no stub** — `remediate()` ejecuta re-detect (`detector.detect_web_type`) → regenerate (`build_config` + `version++` + `portal_config.save(kind="dealer")`, persiste de verdad) → revalidate (`harvest_dealer`, `recovered = persisted>0`), con escalado honesto (no reintento infinito). 4 tests asertan comportamiento real (persistencia, version bump, migración static→E07).
- **🟡 PERO el trigger drift→remediación NO está cableado [V]:** el harvester guarda `drift_ok` en el resultado pero **nunca llama `remediate()`**. `git grep "remediate|needs_remediation"` fuera del módulo/tests = **vacío** → ningún proceso/script lo dispara. Un dealer driftado en producción pondría `drift_ok=False` y **no pasaría nada**. El reporte ("drift + auto-remediación cableados") **sobredeclara**: la capacidad existe y está testeada, pero está **muerta** (sin caller productivo). **Plan P2:** `if not drift.ok: remediate(...)` en el harvester/orquestador; corregir el wording del reporte.

## 4. Honestidad del yield ~3% — 🟢 HONESTO [V]
`sweep_random.json`: **90 dealers** (15×6 países), **3 yielders = 3,3%** (coincide con ~3%; `by_classification` suma 90, consistente). Desglose **real por dealer**:

| Clasificación | N | % | ¿Extractor alcanzado? |
|---|--:|--:|---|
| `no_inventory_links` (ruido OSM no-coches) | 46 | 51% | No (disc=0) |
| `unreachable` (4xx/5xx/bloqueo IP) | 21 | 23% | No (disc=0) |
| `details_no_fields` (JS/XHR) | 17 | 19% | Sí (URLs, sin campos) |
| `timeout`/`spa_shell` | 3 | 3% | — |
| yield (sitemap_listing+jsonld_detail) | 3 | 3% | Sí → extraído |

**77% (69/90) tienen `discovered=0`** → el extractor **nunca se alcanzó** (no hay URLs = ruido/host muerto) → causa genuinamente **upstream**, no fallo del extractor. Los 3 yielders: **100% éxito** (extractor funciona). El bucket extractor-adjacent (`details_no_fields`, 19%) **se declara abiertamente como backlog `playwright_xhr`** (probaron 2 con navegador → persisted=0, XHR sin SEO-meta) — caracterización correcta, no oculta. **Veredicto: el ~3% es ruido de censo real, no un fallo enmascarado.** *(Discrepancia menor honesta: `discovered` difiere entre sweep y yielders json — dos corridas distintas, censo-cap vs harvest-live; no fabricación.)*

## 5. Seguridad — 4/4 correcciones HIGH SOUND [V]
| Fix | Veredicto | Evidencia |
|---|---|---|
| **SSRF `expand_catalogs`** | 🟢 SOUND | `is_safe_public_url` (net_guard) bloquea esquemas≠http(s) e IPs privadas/loopback/link-local/metadata 169.254.169.254; re-check en call-site (`discovery.py:84-105`) + la extracción interna re-basa y re-valida cada link. SSRF a target interno **cerrado**. Residual no explotable: scope same-public-host. |
| **Path-traversal config store** | 🟢 SOUND | `_dealer_path` (`config.py:135-146`) `replace("/","_")` + `.resolve()` + `is_relative_to(_DEALER_DIR)`→ValueError. Probado: `..\..\windows`→**ValueError** (el `/`-replace no toca `\`, pero `is_relative_to` lo caza). Load+save funnelean por el guard. |
| **Browser cleanup** | 🟢 SOUND | `finally` en ambos scripts driver (`run_dealer_scraping.py:130-159`, `sweep_dealers.py:57-83`), abierto-dentro-del-try; `__aexit__` + `aclose` por batch, sin leak en error. |
| **Memoria por batch** | 🟢 SOUND | LIMIT acotado por país (sin `fetchall` sobre 30k), `E07_CONCURRENCY=2`, `BATCH_SIZE=20` + `gc.collect()` por batch, body read MemoryError-safe, discovery cap 150. |

## 6. Dimensiones estándar
| Dim | Veredicto | Evidencia |
|---|---|---|
| **Regresión** | 🟢 **1325 passed, 0 failed** | en worktree aislado (base b980f90=1284 +41). *(Reporte dice 1324/"36 nuevos" — leve subconteo, inmaterial.)* |
| **RAM-safe** | 🟢 | E07 conc=2, sin fetchall, GC por batch, 1 navegador/batch cerrado, timeout por dealer; el run+sweep+E07 corrieron sin OOM |
| **Higiene** | 🟢 | FF-able; auditado en worktrees detached aislados (sesiones intactas); redis throwaway purgado; **`discovery_candidates` NO tocada**; in-flight branches no tocan `config.py` (sin contención de merge) |

---

## 7. Recomendación de consolidación — **GO**

**Mergear `feature/dealer-scraping-system` → `main`.** No lo ejecuto.

- ✅ `[V]` **Hoy es FF** (0 detrás / 1 delante, main ancestro). Si domain-resolution/discovery-scale mergean antes → 3-way, pero **limpio** (dealer toca `scrapers/dealer_scraping/` + `config.py`; las in-flight **no tocan `config.py`** → disjunto).
- ✅ `[V]` Aditivo, **seam no reescrito**, **4/4 HIGH de seguridad SOUND**, **RAM-safe**, **1325 verde**, E2E re-verificado, yield honesto.
- ✅ Sin riesgo de datos (escribe solo `vehicles` vía seam + purga; lee `discovery_candidates` read-only en modo sweep, no en `--domains`).

**Condición P2 (NO bloquea el merge):** **cablear el trigger de auto-remediación** (`if not drift.ok: remediate(...)`) — hoy la remediación es una capacidad real pero muerta; corregir el wording "cableados" del reporte. Resto de backlog del reporte (sesgar discovery anti-ruido-OSM, recetas por plataforma de marca, `playwright_xhr` para `details_no_fields`, feed DMS, proxies P3) son incrementos dirigidos, no defectos.

**Ramas en vuelo:** fanout ✅ + e07 ✅ merged (main=b980f90); **dealer → merge recomendado**; `feature/domain-resolution` (b037a07) y `feature/discovery-scale` (e6b9fa0) activas escribiendo `discovery_candidates` → pendientes de su propia auditoría.

---

*GUARDIAN — autointerrogatorio: ¿toqué lo prohibido? No — no escribí `discovery_candidates` (E2E con `--domains` explícitos solo toca `vehicles`+purga), no reinicié docker, no perturbé los 3 worktrees activos (usé worktree detached propio, eliminado). ¿Verifiqué ejecutando? Sí — E2E real, suite 1325, `git grep`, merge-base. ¿Refuté cada hecho? Sí — seguridad (4/4 resistieron incl. prueba `..\..\windows`), yield (refutación "no es fallo extractor" sostenida), config aditiva (seam ausente del diff), y **drift-remediación cayó: trigger no cableado**. Fin.*
