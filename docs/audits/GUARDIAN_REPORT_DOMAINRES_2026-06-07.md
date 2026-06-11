# GUARDIAN — Auditoría "resolución de dominio a escala" (PARTE II)

**Auditor:** GUARDIAN · **Conducida:** 2026-06-07 · **Modo:** SOLO LECTURA (UNA sesión —barrido A— escribe `discovery_candidates`; NO la escribí ni reinicié docker; auditré el código del resolver + una MUESTRA de dominios persistidos)
**Rama auditada:** `feature/domain-resolution` @ `2bd5cb5` · **main** @ `72b31d5` · **merge-base** `b980f90`
**Relación:** diverge **1/8** (NO FF; main +1 = el FF de dealer) · **3-way con main LIMPIO** (merge-tree exit 0, 0 conflictos; archivos disjuntos de dealer)
**Fuente:** `DOMAIN_RESOLUTION_REPORT.md`
**Método:** muestra real de dominios resueltos (SELECT read-only), código vía `git show` (sin checkout — 3 sesiones activas), suite en worktree detached aislado, 2 subagentes read-only, merge-tree. Cada "hecho" atacado.

> `[V]` = VERIFICADO (comando citado). Foco: el fix anti-falso-positivo (precisión real) + atribución honesta.

---

## 0. Resumen ejecutivo — ¿lista para consolidar?

**Sí, vía merge 3-way (limpio).** El resolver multi-vía es **honesto y bien construido**: el fix anti-FP de raíz es real y cierra la causa original (fuga CSS/JS), `revalidate.py` purga regresiones de verdad, el `worker.py` es idempotente/RAM-safe/atómico, las 5 vías cableadas extraen dominio real, la atribución es **escrupulosamente honesta** (reclama solo ~104 filas tagged, no el salto de país del barrido A), y la **suite queda en 1313 verde**. Muestra empírica: precisión ~92% coherente con lo declarado. **Recomendación: MERGE 3-way a `main`.** No lo ejecuto.

**Caveats P2 (NO bloquean):** (a) residual FP estrecho — la lista no-dealer no cubre 6 idiomas (NL rijschool, IT scuola guida, parts/body shops) y el fallback nombre-genérico→city+auto deja pasar algún vehicle-adjacent (mi muestra: `Artcar→bmwartcarcollection.com`); (b) la capa de cola del worker (`FOR UPDATE SKIP LOCKED` / collision-merge / promote) **sin tests** — justo la parte propensa a bugs de concurrencia junto al barrido paralelo; (c) doc stale (reporte dice 19 tests/1303; reales 29/1313).

| Ítem | Veredicto |
|---|---|
| 1 · Anti-falso-positivo (raíz) | 🟢 SOUND (residual estrecho, documentado) |
| 2 · `revalidate.py` purga regresiones | 🟢 SOUND |
| 3 · Escala/idempotencia worker | 🟢 SOUND |
| 4 · Vías cableadas + CC inviable | 🟢 5/5 reales; CC bien razonado |
| 5 · Atribución honesta | 🟢 HONESTO |
| 6 · Regresión / RAM / higiene | 🟢 1313 verde, RAM-safe |

---

## 1. Anti-falso-positivo (lo más crítico) — 🟢 SOUND [V]
**Fix de raíz en 3 capas, real:**
- **`_text` quita `<script>/<style>/noscript/template/svg` + comentarios, luego TODAS las tags** (`validate.py:57-84`). Los valores de atributos (`cursor:auto`, `class="auto-grid"`) **no fugan** (la tag entera se borra) → la causa original del FP de directorios (CSS/JS fingiendo "auto") está **cerrada**. Residual teórico: un `<script>` sin cierre fugaría (baja incidencia).
- **Señal automotriz de 2 niveles** (`validate.py:48-52`): ≥1 FUERTE (autohaus/gebrauchtwagen/concessionnaire…) **o** ≥2 DÉBILES **distintos** (`set()`); `occasion`/`garage`/`motor` excluidos. **Un "auto" suelto NO pasa** [V refutado].
- **Guard de categoría no-dealer por título** (`validate.py:70-97`, corre ANTES del gate auto, accent-normalizado): rechaza fahrschule/auto-ecole/autoescuela/museum/rental/airport/travel.

**Precisión empírica [V]:** muestra de 30 de las ~104 filas con `resolved_via` → ~26-27 dealers de coches reales (Garage Koch→carrosserie-koch.ch, Hutter Dynamics, Perroud Automobiles, Garage du Lion→lionautomobile.ch…), token del nombre en el dominio. ~3-4 borderline/vehicle-adjacent: `Fendt→mcwit.ch` (agri/campers), `Premium-Cars→voyages-stevic.ch` (match débil), **`Artcar→bmwartcarcollection.com` (FP residual: colección de arte)**. → **~87-90% estricto / ~92% contando comerciales — coherente con el ~92% declarado.**

**Residual FP (estrecho, mayormente documentado):** (a) **puerta más ancha** — dealer de nombre genérico/marca → `name_tokens` vacío → acepta por **city+auto**; una carrocería de la misma ciudad (`carrosserie` es FUERTE y no está en la lista no-dealer) pasaría; (b) vía email omite el chequeo de identidad (acotado por guard freemail); (c) no-dealers en idiomas no cubiertos (NL rijschool, IT scuola guida, parts/body). **Plan P2:** ampliar `_NON_DEALER_RE` a 6 idiomas + parts/body; endurecer el fallback de nombre-genérico.

## 2. `revalidate.py` — purga de regresiones — 🟢 SOUND [V]
Re-fetcha cada fila resuelta y re-corre el gate VIVO (`confirms_dealer`/`confirms_automotive`); si falla → `_PURGE` **UPDATE-only** (`domain=NULL`, `external_refs - 'resolved_via'`, re-encola); `DELETE` solo en colisión con gemelo identidad. **Guard de blip de red** (excepción de transporte → NO purga). Re-usa el mismo gate que el worker → endurecer la verja marca filas stale. **Prueba viva [V]:** los 6 FP del incidente (`boucherie-erard.ch`, `swiss-optik.ch`, `anwaltskanzlei-sh.ch`, `fahrschule-marty.ch`, `saurermuseum.ch`, `gva.ch`) = **0 filas** → purgados. La red de seguridad funciona.

## 3. Escala / idempotencia — `worker.py` — 🟢 SOUND [V]
- **Claim atómico** `FOR UPDATE SKIP LOCKED` + bump `ddg_last_attempt=NOW()` en **una** sentencia (`worker.py:64-79`) → dos sesiones nunca toman la misma fila (coordina con el barrido A).
- **UPDATE-only**: 0 INSERT, 0 fetchall (grep limpio); promote guardado `WHERE id=$ AND domain IS NULL`; fail incrementa attempts; collision-merge funde `external_refs` y borra la fila duplicada (no la resuelta).
- **Resumible/idempotente**: re-claim solo `domain IS NULL` < MAX_ATTEMPTS(5) tras `_MIN_INTERVAL`; crash-tras-claim se difiere (no se pierde ni duplica); colisión concurrente → UniqueViolation → merge.
- **RAM-bound**: batch LIMIT 40, semáforo conc 3, `gc.collect()` por lote, watchdog RSS 1200MB, sleep jitter cortés.

## 4. Vías cableadas + Common Crawl — 🟢 5/5 reales [V]
| Vía | Veredicto | Evidencia |
|---|---|---|
| PagesJaunes (FR) | REAL | `directories._pagesjaunes`: endpoint real, extrae `href` del dealer→apex; test `→garagecurty.com` |
| local.ch (CH) | REAL | website JSON + email de contacto (`email_apex`); test `→emilfrey.ch`, dropa bluewin.ch |
| GelbeSeiten (DE) | REAL 2-step | search→`gsbiz` UUID detail→sitio; test `→autohaus-ostmann.de` |
| DDG/Mojeek | REAL | `curl_cffi impersonate=chrome` [V], `uddg=`+href→apex; (techo honesto: throttle 1-IP → `search_unreachable`) |
| email-domain | REAL | `email_apex` con guard freemail/ISP (gmail/bluewin/t-online→None); test `info@bmw-dimab.ch→bmw-dimab.ch` |
| paginasamarillas (ES) | stub honesto | anti-bot, NO cableada, documentada |
| **Common Crawl CDX** | **inviable, bien razonado** | el CDX es índice URL-prefix; no soporta substring `*kw*.tld` para descubrir por nombre → limitación **estructural**, con reuse-audit del `common_crawl.py` existente. NO es pereza. (Caveat: "No Captures" afirmado de test en vivo, no re-verificable en código — CC correctamente NO cableado.) |

## 5. Atribución honesta — 🟢 HONESTO [V]
Filas con `external_refs.resolved_via` (la marca que pone ESTE worker) = **104-108** (CH 102: localch 67 + ddg 34 + email 1; BE 1; FR 1). El resolver reclama **solo estas ~104 tagged**. **0 filas DE/ES/NL con `resolved_via`** → el salto de `with_web` de país (DE→~22K, CH→~3.9K) es del **barrido A + OSM**, NO del resolver — y el reporte lo declara explícitamente ("NO reclamo esos miles"). Las 16 de la Parte I (keyset) van sin tag, mencionadas aparte. **Atribución limpia, sin maquillaje.**

## 6. Dimensiones estándar
| Dim | Veredicto | Evidencia |
|---|---|---|
| **Regresión** | 🟢 **1313 passed, 0 failed** | worktree aislado (reporte dice 1303 = Parte I stale). **29 tests** (no 19); gap: capa de cola del worker sin tests |
| **RAM-safe** | 🟢 | keyset/batch, gc, watchdog RSS, conc 3, sin fetchall — verificado en código |
| **Higiene** | 🟢 | 3-way limpio; auditado en worktree detached (3 sesiones intactas); **`discovery_candidates` NO escrita** (solo SELECT de muestra) |

---

## 7. Recomendación de consolidación — **GO (merge 3-way limpio)**

**Mergear `feature/domain-resolution` → `main` por merge 3-way.** No lo ejecuto.
- ✅ `[V]` NO es FF (diverge 1/8) pero el **3-way es LIMPIO** (`git merge-tree` exit 0, 0 conflictos; módulo `scrapers/discovery/domain_resolution/` disjunto de `scrapers/dealer_scraping/`+`config.py` de dealer ya en main).
- ✅ Aditivo (módulo nuevo), **UPDATE-only** (no toca esquema ni inventario), anti-FP de raíz sólido, revalidate sólido, worker sólido, 5/5 vías reales, **atribución honesta**, **1313 verde**.
- ✅ Sin riesgo de datos para el merge (es código; el worker en runtime hace UPDATE-only de `discovery_candidates`, coordinado por `SKIP LOCKED` con el barrido A).

**Caveats P2 (NO bloquean):** (1) ampliar `_NON_DEALER_RE` a 6 idiomas + parts/body shops y endurecer el fallback nombre-genérico→city+auto (cierra el residual FP — p.ej. `Artcar→bmwartcarcollection.com`); (2) **añadir tests a la capa de cola del worker** (claim `SKIP LOCKED`/collision-merge/promote — hoy 0 cobertura, es la parte concurrente más sensible junto al barrido A); (3) corregir doc stale (19→29 tests, 1303→1313, "gelbeseiten deferred" de Parte I contradicho por el código cableado en Parte II); (4) techo de throughput DDG (1-IP) → priorizar directorios (la vía robusta) + proxies para ES/NL/BE.

**Mecánica sugerida:** main no está checked out en ningún worktree → mergear en **worktree temporal sobre main** (`git worktree add tmp main && cd tmp && git merge feature/domain-resolution`); suite post-merge esperada **~1349** (1325 main + ~24 nuevos del módulo) — verificar.

**Ramas en vuelo:** fanout ✅ + e07 ✅ + dealer ✅ merged (main=72b31d5); **domain-resolution → merge recomendado**; `feature/discovery-scale` (barrido A, e6b9fa0) activa escribiendo `discovery_candidates` → pendiente de su propia auditoría (su merge será 3-way; probablemente limpio si toca solo discovery sources, disjunto de domain_resolution).

---

*GUARDIAN — autointerrogatorio: ¿toqué lo prohibido? No — `discovery_candidates` solo en SELECT (muestra, lo pedía la misión), sin escribir; no reinicié docker; no perturbé los 3 worktrees activos (usé worktree detached propio, eliminado). ¿Verifiqué ejecutando? Sí — muestra real de 30 dominios, conteo de atribución, 6 FP purgados, suite 1313, merge-tree. ¿Refuté cada hecho? Sí — anti-FP (residual estrecho hallado), atribución (104 tagged ≠ miles de país), vías (5/5 reales), worker (atómico/UPDATE-only). Nada cayó como defecto bloqueante; los residuales son P2 documentados. Fin.*
