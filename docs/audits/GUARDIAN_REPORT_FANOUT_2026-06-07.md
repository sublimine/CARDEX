# GUARDIAN — Auditoría FAN-OUT (5 países)

**Auditor:** GUARDIAN · **Conducida:** 2026-06-07 · **Modo:** SOLO LECTURA (sesión E07 en paralelo sobre inventario — no toqué `vehicles`/`vehicle_index`, no reinicié docker, no hice checkout)
**Rama auditada:** `feature/fanout-5countries` @ `6e0be32` · **Base:** `main` @ `a980b3f`
**Relación:** **0 detrás / 1 delante → fast-forward limpio** (commit único, 8 archivos, **+987 / −0, 100% aditivo**)
**Fuente:** `FANOUT_5COUNTRIES_REPORT.md`
**Método:** PG en vivo (SELECT, conteos exactos, set-diff de ortogonalidad), código vía `git show` (sin checkout, para no perturbar la sesión E07), suite en **worktree temporal aislado**, 1 subagente read-only. Cada "hecho" atacado antes de darse por bueno.

> `[V]` = VERIFICADO (comando citado). Foco: fabricación de datos + honestidad de bloqueos.

---

## 0. Resumen ejecutivo — ¿lista para consolidar?

**Sí.** El fan-out es un commit **aditivo, honesto y de bajo riesgo**: replica el molde `nl_rdw` a 5 países sin tocar el core ni el seam, no fabrica una sola fila, declara los bloqueos con transparencia, y la suite queda en **1274 verde**. **No toca inventario** (`vehicles`/`vehicle_index`), así que es inocuo respecto a la sesión E07 en curso. **Recomendación: MERGE a `main` (fast-forward)** — con una nota de secuenciación (§4). No ejecuto el merge.

**Naturaleza del entregable:** es una **prueba-de-patrón country-agnostic**, NO una victoria de cobertura. El rendimiento real es mínimo (552 filas nuevas) y 2 de 5 países quedan bloqueados — coherente y honestamente declarado. La fuga real (cobertura) sigue enorme.

| Ítem | Veredicto | Pérdida/fabricación |
|---|---|---|
| 1 · Discovery cargado real (FR/ES/CH) | 🟢 SOUND (real, ortogonal, país correcto) | **No fabricado** |
| 2 · DE/BE bloqueados honestamente | 🟢 SOUND (0 filas + WARNING, insert-trap test) | **No fabricado** |
| 3 · dealer_terms multilingüe | 🟢 SOUND ("auto" excluido, sin falsos positivos) | n/a |
| 4 · Seam intacto | 🟢 SOUND (0 archivos de seam tocados) | n/a |
| 5 · Regresión | 🟢 1274 passed, 0 failed | n/a |

---

## 1. Ítems críticos

### Item 1 · Discovery cargado real — 🟢 SOUND [V]
Conteos vivos **exactos** (total 460.378 → **460.930**, Δ = 552 = 518+17+17 → solo esas filas):

| Fuente nueva | Filas | País | overlap con fuente FR existente | domain |
|---|--:|---|---|---|
| `recherche_entreprises` | **518** | 100% FR | **0 / 518 con `sirene`** (ortogonal real) | NULL (registro) |
| `openmercantil` | **17** | 100% ES | n/a | NULL |
| `zefix_bs` | **17** | 100% CH | n/a | NULL |

- **Ortogonalidad probada [V]:** los 518 registry_id de `recherche_entreprises` tienen **cero solape** con `sirene` → entidades genuinamente nuevas, no re-etiquetado de la fuente FR existente. Filtra por NAF 45.11Z/45.19Z (concesionarios), método distinto de la volcada SIRENE genérica.
- **No fabricado [V]:** muestras = nombres/ciudades/CIF reales (PALMA-CARS S.COOP Córdoba, AIXA AUTOCARAVANING Navarra…). Subagente confirmó: 0 literales hardcoded; datos solo de `r.json()`.
- **Caveats honestos:** (a) **CH = solo Basel-Stadt** (`data.bs.ch` dataset 100330, ~19k empresas); el censo de 26 cantones queda diferido al mirror `all_cantons`. (b) **ES laxo y mínimo:** 17 filas, CNAE 4519 incluye no-coches (LPK TRUCKS, AUTOKARAVAN campers, CONSTRUCCIONES UNICOM) — reales pero scope amplio; el reporte lo etiqueta "partial". (c) las 3 fuentes son **domain-NULL** (registros) → necesitan resolución A2/OEM para servir al scraping (misma cola larga que RDW).

### Item 2 · DE/BE bloqueados honestamente — 🟢 SOUND [V]
- **0 filas** de `de_offeneregister`/`be_kbo` en `discovery_candidates` (explícito); DE 45.103 y BE 4.048 sin cambio.
- **DE [V]:** ante `httpx.HTTPError` o `status≠200` (SQL API 502), `run()` loguea `WARNING BLOCKED:` y `return inserted` **antes** del `pool.execute` → nunca inserta. **BE [V]:** sin `KBO_DATA_DIR` (CSV requiere registro), `return 0` antes de abrir pool.
- **Construido+testeado, no stub [V]:** transforms reales (`to_candidate`, `is_auto_nace`, `join_kbo`) que funcionarían si la fuente respondiera. El test `test_de_run_blocked_returns_zero_no_invented_data` usa un **pool-trampa que lanza si se intenta insertar** → prueba de que no fabrica. Sin literales `GmbH/sample/fake/dummy`.

### Item 3 · dealer_terms multilingüe — 🟢 SOUND [V]
- Dict `{country:{lang:terms}}`: DE(de), FR(fr), ES(es), NL(nl), **BE bilingüe (nl+fr)**, **CH trilingüe (de+fr+it)**; términos correctos por dialecto (Autohaus/Kfz, garage/concessionnaire, concesionario/taller, autofficina/carrozzeria…).
- **"auto" genérico EXCLUIDO [V]:** grep + ejecución `'auto' in terms_for('DE')→False`, `terms_for('CH')→False`. Compuestos (`automobile`, `autohaus`) presentes; token suelto no.
- **Sin falsos positivos [V]:** match substring accent/case-insensitive; probes `Autobahn GmbH`, `Automation Solutions`, `Studio Automatique` → todos rechazan correctamente.

### Item 4 · Seam intacto — 🟢 SOUND [V]
`git diff main..6e0be32 --stat`: **ninguno** de `enrich_worker.py`/`rich_consumer.py`/`coordinator.py`/`pipeline/generic_extractor.py`/`common/indexer.py` modificado. Las fuentes reusan la tabla `discovery_candidates` con el **mismo** upsert ON CONFLICT que `nl_rdw`. Los tests del seam pasan dentro del 1274. *(No re-ejecuté el E2E vivo del seam por la restricción de no tocar inventario + sesión E07; el seam-intacto queda probado por código + suite, que es suficiente al no tocarse su código.)*

---

## 2. Cobertura — gap real por país vs censo estimado

El fan-out demuestra el patrón pero el rendimiento es testimonial. Censo nacional estimado `[A, conocimiento de dominio]`:

| País | Fuente nueva | Cargado | Censo coches est. | Gap | Causa |
|---|---|--:|--:|--:|---|
| FR | recherche_entreprises | 518 | ~15–20k concesionarios | ~97% | API paginada/parcial; corre más con barrido completo por depto |
| ES | openmercantil | 17 | ~36k | ~99,95% | cobertura CNAE parcial + scope laxo (4519) |
| CH | zefix_bs | 17 | ~5,8k | ~99,7% | **solo Basel-Stadt**; mirror 26 cantones diferido |
| DE | de_offeneregister | **0** | ~38k | 100% | **bloqueado** (SQL API 502) — buscar fuente alterna |
| BE | be_kbo | **0** | ~8k | 100% | **bloqueado** (CSV exige registro) |

**Veredicto cobertura:** el fan-out es **prueba-de-patrón, no cobertura**. Suma 552 dealers reales (todos domain-NULL → aún no scrapeables sin A2/OEM). La cola larga de dominios y los 2 países bloqueados mantienen el gap masivo. Consistente con el estado "esqueleto validado" del sistema.

---

## 3. Dimensiones estándar

| Dim | Veredicto | Evidencia |
|---|---|---|
| **Cobertura** | 🟡 patrón probado, yield mínimo | §2; 552 filas nuevas, 2/5 países bloqueados, todas domain-NULL |
| **Datos** | 🟢 reales, país correcto | nombres/CIF reales, 100% país correcto, 0 fabricación; caveat scope ES (CNAE 4519) |
| **Pipeline** | 🟢 intacto | seam no tocado; discovery reusa upsert canónico |
| **Regresión** | 🟢 1274 passed, 0 failed | corrida en worktree aislado (1263→+11 de `test_fanout_sources`) |
| **Higiene** | 🟢 limpia | rama FF (0/1), worktree temporal de auditoría eliminado; no toqué el working tree de E07 |

---

## 4. Recomendación de consolidación — **GO (fast-forward), con nota de secuenciación**

**Mergear `feature/fanout-5countries` → `main` por fast-forward.** No lo ejecuto.

- ✅ `[V]` 0 detrás / **1 delante** → FF sin conflictos; aditivo (+987/−0); **no toca inventario** → seguro respecto a la sesión E07.
- ✅ `[V]` Suite **1274 verde**; seam intacto; **cero fabricación** (bloqueos honestos con WARNING + insert-trap test); discovery real y ortogonal.
- ✅ Sin riesgo de pérdida de datos (solo añade 552 filas a `discovery_candidates`; no UPDATE/DELETE).

**⚠️ Nota de secuenciación (orquestador):** `feature/fanout-5countries` Y `feature/e07-playwright-xhr` **parten ambas de `main @ a980b3f`**. Tras mergear una por FF, la otra deja de ser fast-forward puro (quedará 1 detrás → rebase/merge). Recomiendo: mergear primero fan-out (aditivo, inocuo, no toca inventario), luego rebasear E07 sobre el nuevo `main` y re-auditar E07 antes de su merge.

**Caveats P2 (NO bloquean):** DE/BE necesitan fuente alterna (502/registro); CH ampliar de Basel-Stadt al mirror 26 cantones; ES afinar CNAE (excluir 4519 no-coches) y subir volumen; resolver dominios (A2/OEM) de las 552 filas domain-NULL para que sean scrapeables.

**No leer como hecho:** el fan-out **prueba el patrón** de discovery country-agnostic; no mueve la aguja de cobertura (552 dealers, 2 países en 0, todos sin dominio).

---

*GUARDIAN — autointerrogatorio: ¿verifiqué sin tocar lo prohibido? Sí — solo SELECTs read-only, código vía `git show` (sin checkout), suite en worktree aislado; no toqué `vehicles`/`vehicle_index`/docker/el working tree de E07. ¿Refuté cada hecho? Sí — ortogonalidad (overlap=0), fabricación (insert-trap + muestras reales), "auto" excluido (ejecutado), seam (diff). Nada refutado → verde. Fin.*
