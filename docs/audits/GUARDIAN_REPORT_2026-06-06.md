# GUARDIAN — Auditoría de consolidación CARDEX

**Auditor:** GUARDIAN (auditoría continua + anti-fugas)
**Conducida:** 2026-06-06 → 07 · **Rama auditada:** `feature/p0-rewiring-canon` @ `830bf5d`
**Base:** `main` @ `6e084a5` · **Relación:** 0 detrás / 7 delante (fast-forward limpio)
**Método:** verificación empírica contra runtime vivo (PG/Redis/CH/Meili/API), suite de tests, muestreo de datos, re-run E2E del seam, lectura de código. 4 subagentes read-only + verificación adversarial directa del orquestador sobre cada afirmación de mayor carga.

> **Convención:** cada cifra es `[V]` = VERIFICADA (salida de comando citada por mí o por subagente y re-confirmada) o `[A]` = ASUMIDA (estimación declarada con base). Nada inventado. Las afirmaciones de subagente con carga fueron **re-ejecutadas por el orquestador** antes de grabarse.

---

## 0. Resumen ejecutivo — ¿estamos en la meta?

**No en datos; sí en fontanería.** CARDEX es hoy un **esqueleto validado, no un producto poblado**. La pregunta rectora —"¿conseguimos de verdad la meta (100%)?"— tiene una respuesta cruda y cuantificada:

| Capa | Meta implícita | Realidad VIVA `[V]` | % meta |
|---|---|---|---|
| **Discovery (censo dealers)** | universo europeo de concesionarios | 460.378 candidatos, **6,2% con dominio** (28.570), **100% `sitemap_status=pending`** | techo libre alcanzado; **0% resuelto a inventario** |
| **L1 — índice de punteros** | listings de los 6 países | 508.339 URLs de **20 portales**, **100% sin atributos** (precio/título/año/km = NULL en las 508.339) | 26,7% de los 20 portales; **0% de los gigantes** |
| **L2 — vehículos ricos (el producto)** | millones de coches con precio/score/fiscal | **30 filas, todas `SEED_DEMO`** (sembradas a mano). 0 reales jamás persistidos durablemente | **≈0%** |
| **Seam L1→L2 (enrich)** | bombeo continuo puntero→rico | **probado E2E, dormido en producción** (en redis vivo `enrich_pending` no existe; `ingestion_raw` last-delivered `0-0`) | mecanismo 100%, ejecución 0% |
| **OLAP (ClickHouse)** | candles/arbitraje | **19 tablas, 0 filas** — provisionada y vacía | 0% (coste RAM sin retorno) |

**La distinción clave que GUARDIAN obliga a hacer:** los reportes P0/NL declaran "HECHO" con honestidad sobre lo que realmente hicieron —**tender y probar la fontanería**— y declaran abiertamente que el poblado a escala (backfill) es "pendiente operativo". El "done" es correcto **para el alcance de rewiring**; sería falso leerlo como "el producto tiene datos". No hay maquillaje en los reportes; sí hay una **enorme distancia entre fontanería-probada y producto-poblado** que este informe cuantifica.

**Dónde está la fuga (resumen):**
1. **El seam nunca corrió en producción** — la ruta enrich está dormida; el producto tiene 0 coches reales. *(fuga de ejecución, no de código)*
2. **Cobertura parcial-a-pobre** — 26,7% del inventario de los 20 portales activos; **51 de 71 portales configurados con cobertura CERO** (mobile.de, AutoScout24×6, leboncoin…), todos gated por anti-bot/proxy de pago.
3. **Resiliencia construida pero desconectada** — config-store y drift-gate existen y pasan tests, pero **ningún proceso always-on los invoca**; la única señal de drift en producción es "cosecha == 0".
4. **Defectos de datos latentes** que estallarán al escribir precio: `moneda` default EUR mal-etiqueta el 41,8% (CH=CHF); FX sin `FX_RATE_CHF`; contaminación de scope (72.225 camiones en DE).
5. **Fugas de durabilidad en el seam** a escala: sin reclaim (XAUTOCLAIM) los transient/error quedan varados en el PEL para siempre.

**Veredicto de consolidación (detalle en §9):** la rama es **aditiva, verde (1246 tests), sin regresiones y estrictamente superior a `main`** (corrige un bug de **corrupción de datos** —el wipe por harvest-0—, tiende el seam, rompe el monocultivo FR). **Recomendación: MERGE a `main` (fast-forward)**, con un punch-list P1 obligatorio **antes** de correr el seam a escala. El merge NO lo ejecuto — queda para el orquestador.

---

## 1. Estado de infraestructura — la "ground truth" estaba stale `[V]`

`CONTEXT_FOR_AI.md` (fechado 2026-04-15) afirma taxativamente que **PostgreSQL, Redis y MeiliSearch NO existen** y que el store es SQLite. **Refutado en runtime:**

```
docker ps → cardex-{pg,ch,meili,redis,grafana,prometheus,api} Up (healthy) + cardex-web Up
PG: cardex db = 495 MB; vehicle_index=508339, vehicle_events=539259, discovery_candidates=460378, vehicles=30
```

> **Brecha documental (P1-doc):** `CONTEXT_FOR_AI.md` es el "file trust hierarchy #1" pero está obsoleto en su afirmación más central. Debe actualizarse para reflejar el stack Docker real (PG/Redis/Meili/CH desplegados, Strategy B), o seguirá induciendo a codificar contra una realidad falsa. *(Nota: `pg_stat_user_tables.n_live_tup` muestra 0/300 por autovacuum nunca corrido — ver D4; los `COUNT(*)` reales confirman las cifras de los reportes con exactitud.)*

---

## 2. Tabla por componente (estado / evidencia / gap / causa / plan)

| Componente | Estado | Evidencia `[V]` | Gap | Causa | Plan |
|---|---|---|---|---|---|
| **RDW discovery (`nl_rdw`)** | 🟢 real, parcial | `source='rdw_erkende_bedrijven'` = **300**; NL 5.430→5.730 | 300 de ~24.700 (Bedrijfsvoorraad) = **98,8% sin cargar** | `RDW_LIMIT=300` (validación con límite) | correr `nl_rdw` completo (sin RDW_LIMIT) en VPS |
| **Discovery censo** | 🟢 techo libre | 460.378 (sirene 360k/FR, osm 99k) | 6,2% con dominio; **0% resuelto a listings** (`sitemap_status` 100% pending) | A2 (name→domain) lento; sitemap-prober nunca corrido | OEM locators `?postcode=` (P1) > crt.sh |
| **L1 vehicle_index** | 🟡 cáscara | 508.339 URLs, 20 portales | **100% atributos NULL**; 26,7% cobertura; 51/71 portales en 0 | sitemap = solo URLs; harvest abortados; gigantes proxy-gated | re-run portales libres no-WAF (+~700k); proxy P3 |
| **L2 vehicles (producto)** | 🔴 vacío | **30 filas, todas `SEED_DEMO`**; vin/score/h3/net_cost 100% NULL | **0 coches reales** | seam dormido en prod (backfill pendiente) | backfill §6.1 blueprint + arrancar enrich-worker |
| **Seam A6 enrich_worker** | 🟢 real / 🟡 estable | re-run E2E mío: 30→32, eur correcto, purgado | sin reclaim; sin try/except por-msg | diseño incompleto (PEL) | XAUTOCLAIM + red de seguridad (P1) |
| **Seam A7 rich_consumer** | 🟢 real / 🟡 estable | persisted=2 errors=0; meili_sync emitido | `ON CONFLICT DO UPDATE` → dead-tuples a escala; FX CHF=NULL | re-scrape toca `last_updated_at` siempre | gate "solo update si cambió" + `FX_RATE_CHF` (P1) |
| **fx_eur** | 🟢 correcto / 🟡 incompleto | EUR=1; CHF requiere env | **CH (41,8%) → eur NULL** sin `FX_RATE_CHF` | env no provisto | setear `FX_RATE_CHF` en compose (P1) |
| **entity_resolver (VIN)** | 🟢 real, 0-output | `entity_matches`=0; idempotente | 0 por **falta de datos** (sin solape VIN cross-source aún) | vehicles=30 seed | se activa tras backfill; capa fuzzy V21 → P1 |
| **cardex-api** | 🟢 healthy | `/healthz` 200; market-price sirve PG | sirve sobre 30 seed | depende de L2 | n/a (sano) |
| **P0-1 harvest-0 fix** | 🟢 verificado | 12 portales reseteados `pending`/att=0 `[V]` | — | corregía wipe + falso-done | mergear (protege datos) |
| **Resiliencia (config+drift)** | 🟡 construido, **desconectado** | `830bf5d`; drift-gate disparó en mi re-run | **0 callers en coordinator/workers** | migración de ejecución = P1 (lo admite el commit) | cablear `drift_gate.evaluate` al ciclo (P1) |
| **ClickHouse OLAP** | 🔴 vacío | 19 tablas, **0 filas** | 0% poblado | enrich no rutea a CH | poblar o parar contenedor |
| **Block0 (2º checkout)** | 🔴 hazard vivo | `C:\Users\elias\CARDEX`@42dec67, trabajo frontend único sin commitear | — | doble working-copy | decisión del dueño (bundle ya protege) |

---

## 3. D1 — Integridad de cobertura (prioridad) `[V]`

**Por país (vehicle_index):** CH 212.524 (41,8%) · NL 160.230 (31,5%) · DE 91.420 · BE 19.294 · ES 13.553 · FR 11.318. → **el monocultivo FR es de *discovery* (84,4%), NO de *listings*** (ahí domina CH).

**Gap por portal (20 activos, suma = 508.339 = ground truth).** Estimado real = total anunciado por docstring del scraper / WebSearch `[A donde se indica]`:

| Portal | Extraído `[V]` | Real est. | Gap % | Causa |
|---|--:|--:|--:|---|
| marktplaats.nl | 4.107 | ~268.000 | 98% | T1 paid-proxy corrido directo → casi-cero |
| autotrack.nl | 16.927 | ~200.000 `[A]` | 92% | segmentación incompleta (grid parcial) |
| paruvendu.fr | 1.182 | ~120.066 | 99% | harvest apenas corrió (~1 de 88 celdas) |
| 2dehands.be / 2ememain.be | 651 / 660 | ~102.000 c/u | 99% | sitemap abortado; espejo Adevinta (correr 1) |
| viabovag.nl | 80.800 | ~129.000 | 37% | **cap de paginación real** (SSR ~100k techo) |
| anibis.ch | 40.000 | ~78.000 | 49% | harvest truncado (subdivisión precio no disparó) |
| gaspedaal.nl | 58.396 | ~338.817 | 83% | **meta-agregador → dedup target, no fuente** |
| comparis.ch | 1.000 | ~214.000 | 100% | meta-agregador; ciclo abortó en 1 celda |
| gowago.ch / clicars.com | 22 / 35 | ~5k / ~2k | ~100% | harvest-casi-cero / selector roto SPA |
| autolina.ch, tutti.ch, ocasionplus, simplicicar, jeanlain, autohero, vroom | — | — | 0–4% | **completos/sanos** (7 portales) |
| **TOTAL 20** | **508.339** | **~1,9M** | **73%** | cobertura efectiva **26,7%** |

**Hallazgo sobre los números redondos:** `anibis=40000` y `comparis=1000` **NO son caps del portal** sino **harvests truncados** (ciclos interrumpidos; ambos `pending att=1`). El único cap estructural genuino es viabovag.

**Gap oculto — 51 de 71 portales configurados con cobertura CERO `[V]`** (set-difference work_queue vs vehicle_index, confirmado por mí):
`mobile.de, autoscout24.{be,ch,de,es,fr,nl}, leboncoin.fr, lacentrale.fr, kleinanzeigen.de, milanuncios.com, coches.net, wallapop.com, heycar.com, carvago.com, …` (+39 más). Causa uniforme: **T2/T3 (Akamai/PerimeterX/DataDome) sin identidad proxied → parkean `no_identity`**. Aquí está el **mayor reservorio sin tocar (~4M+ listings)**, gated por capital (proxies P3). `wallapop.com` está `pending unhandled_exception` (crash de código, distinto de bloqueo).

**dlq vacío (0 filas) `[V]`** — confirma que la extracción detalle (L1→L2) no ha ejercido rutas de fallo: solo el harvest de URLs ha corrido a escala.

**Top-5 cierres por ROI:** (1) autotrack re-run **gratis** +183k; (2) paruvendu **gratis** +119k; (3) 2dehands sitemap **gratis** +101k; (4) marktplaats vía proxy +264k (P3); (5) **deprioritizar** gaspedaal/comparis (doble-cuentan). ~**700k recuperables sin gasto de proxy** antes de tocar los gigantes.

**Veredicto D1:** la cobertura **no puede llamarse honestamente adecuada; es parcial-a-pobre**. El fallo dominante NO son caps estructurales sino **ciclos de harvest incompletos/abortados** en portales libres ya codificados + **gating anti-bot** en los gigantes.

---

## 4. D2 — Integridad de datos `[V]`

- **vehicle_index (508.339):** `precio`, `titulo_modelo`, `anio`, `kilometraje`, `thumbnail_url` = **0 non-null en TODAS las filas** (re-verificado por mí: `count(precio)=0`). Es un roster de URLs deduplicadas (0 url_hash dup, 0 url_original dup) — sano como puntero, **vacío como inventario**.
- **vehicles (30):** 100% `SEED_DEMO`. `vin`, `net_landed_cost_eur`, `h3_index_res4/7`, `cardex_score`, `risk_score`, `photo_urls` = **100% NULL**. `fingerprint_sha256` único (0 dup). → **ninguna capa de enriquecimiento/scoring/geo ha corrido E2E sobre datos reales.**
- **vehicle_events (539.259):** SEEN 523.799 + GONE 15.460 + **ENRICHED 0** `[V]`. 30.920 eventos referencian url_hash ausente de vehicle_index (15.460 pares SEEN+GONE — consistente, pero **sin FK** que lo imponga).
- **discovery_candidates (460.378):** `sitemap_status` = **100% pending** `[V]`. name 99,9% poblado; domain 6,2%. RDW/sirene con domain NULL por diseño (registros).
- **Defecto de moneda `[V]`:** `vehicle_index.moneda` default `'EUR'` aplica a las **212.524 filas CH** (precio real será CHF). En cuanto la extracción escriba `precio` sin fijar `moneda='CHF'`, **mal-etiqueta el 41,8% del índice**. No hay columna que permita detectarlo a posteriori.
- **Contaminación de scope `[V]`:** `truckscout24.com` aporta **72.225 filas DE** que son **camiones/comerciales** (`/tsp/ts-*`), no turismos → contamina la vertical de coches y el scoring futuro.

**Veredicto D2:** la estructura es sólida (sin duplicados, sin corrupción, tipos correctos) pero **el contenido del producto no existe**; y hay **2 defectos latentes** (moneda CH, scope camiones) que deben cerrarse **antes** de que la extracción escriba a escala.

---

## 5. D3 — Integridad de pipeline (el seam) — REAL, estabilidad caveada

**Re-run E2E independiente del orquestador `[V]`** (`verify_seam_redis --domain autotrack.nl --limit 2`, redis throwaway, PG vivo):
```
seeded=2 → A6 emitted=2 dlq=0 transient=0 → ingestion_raw=2 → A7 persisted=2 rejected=0 errors=0
vehicles 30 → 32 → PURGED → 30 (restored)
  Peugeot 2008 2020 eur=20700.00  · SEAT Ateca 2019 eur=16950.00 (EUR, source_id no-null, platform=autotrack.nl)
meili_sync depth=2
```
**El seam es REAL y mueve datos ricos E2E.** El Go A7 está **genuinamente muerto** (`services/pipeline` sin `go.mod`, ausente de `go.work` `[V]`) → el Python es la implementación correcta.

**Fugas de estabilidad encontradas por revisión de código adversarial (3 hipótesis):**

| # | Hipótesis | Resultado | Severidad |
|---|---|---|---|
| H1 | A6/A7 sin reclaim (XAUTOCLAIM) → transient/error varados en el PEL | **CONFIRMADA** `[V]` (los "reclaim" del grep son comentarios; ambos leen solo `>`) | **ALTA** a escala |
| H2 | A6 sin try/except por-mensaje (A7 sí) → 1 excepción tumba el worker | **PARCIAL** `[V]` (`generic_extractor` captura faults del fetcher; pero un fallo en `_emit`/redis sí tumbaría A6) | MEDIA |
| H3 | Trigger PG bloquea UPDATE → `ON CONFLICT DO UPDATE` rompe en steady-state | **REFUTADA** `[V]` (0 triggers en toda la DB; el "hook ADR-0006" es git/Go) | — |

**Adicional:** el seam **nunca corrió en producción** (`enrich_pending` ausente en redis vivo, `ingestion_raw` last-delivered `0-0`). El E2E siempre usó redis throwaway. → la ruta está **dormida**, no fluyendo.

**Veredicto D3:** fix **real y probado** (independientemente, 3ª vez); **no probado-estable a escala** — H1 (reclaim) es una fuga productor↔consumidor real que el demo purge-con-límite nunca expuso (0 transient). Cerrar antes del backfill.

---

## 6. D4 — Eficiencia y organización para escala `[V]`

| # | Deuda | Impacto a millones | Fix |
|---|---|---|---|
| P-1 | **Autovacuum nunca corrió** (`last_autovacuum` NULL en todas; planner ve `n_live_tup=0` para tablas de 508k) | EXPLAIN estima `rows=1` → planes de join catastróficos al fluir datos | `ANALYZE` + revisar config autovacuum |
| P-2 | **vehicle_events sin particionar, sin índice en `ts`, crecimiento ilimitado** (append-only, ~2M SEEN/mes) | a ~20M filas: time-range = full scan; `idx_ve_hash` → 700MB | partición RANGE mensual + índice `ts` interino |
| P-3 | **Sin índice `(country, precio, anio)`** en vehicle_index | búsqueda país+precio+año escanea todo el país en heap a escala | crear tras poblar columnas |
| P-4 | **`titulo_modelo` denormalizado** (make+model juntos) en index y events | imposible filtrar/indexar make o model; `ILIKE '%x%'` = full scan | split `make`/`model` + GIN trigram |
| P-5 | **`url_hash TEXT(32)` como PK+FK** | a 10M: pkey 730MB (vs ~460MB bytea16); cada join paga | migrar a `bytea(16)`/`uuid` |
| P-6 | **ClickHouse vacío consumiendo ~0,5–1GB RAM** | quema recursos del único VPS sin retorno | rutear enrich→CH o parar contenedor |
| — | **A7 `ON CONFLICT DO UPDATE` toca `last_updated_at` siempre** | re-scrape de 500k/día → 500k dead-tuples/día aunque nada cambie | gate "update solo si precio/estado mutó" |

Proyección de tamaño a 10M filas de vehicle_index: ~9GB total `[A, basado en row-size medido]` — cabe en CPX51 (80GB), justo en CPX31 (40GB). discovery_candidates está **bien indexada** (7 índices parciales). engine.db (112KB) adecuada.

**Veredicto D4:** esquema sólido pero **operativamente estancado**; los dos peligros reales a escala son **vehicle_events sin particionar** y el **planner ciego por autovacuum**. Ambos baratos de cerrar ahora.

---

## 7. D7 — Diseño de resiliencia (config-driven + drift) — construido, desconectado

**(A) Config-driven: NO (hoy).** La flota de portales son **~70 subclases Python hardcoded** (`PORTAL_REGISTRY` = tupla de imports). Existe un **config-store versionado** (`scrapers/portals/config.py` + `configs/portals/*.json`, commit `830bf5d`) con 2 configs de referencia (autotrack, viabovag) — pero **`config.load()` no tiene ningún caller de producción** (solo tests + el script manual). Onboarding de portal = **escribir código**, no añadir config. El `generic_extractor` SÍ es site-agnóstico (JSON-LD/schema.org), pero es la ruta dealer long-tail, separada, y tampoco lee el store.

**(B) Drift detection: PARCIAL (construido, no cableado).** Existe un gate de 3 dimensiones real y testeado (`intelligence/drift_gate.py`: VOLUME + FIELD + SCHEMA fingerprint sobre `schema_registry`) — **lo vi disparar en mi re-run** (`ALERT volume(2<3)`). Pero **ningún proceso always-on lo invoca**: coordinator/workers no lo importan. La única señal de drift en producción es `EMPTY_SUSPECT` (cosecha == **exactamente** 0). Un portal que cae el 80% de volumen, o devuelve páginas con `precio`/`año` en NULL, o cambia su JSON-LD, **pasa como OK→done**. `schema_registry` tiene **1 fila** (viabovag, sembrada por el script).

**Respuesta a "¿nace config-driven con hooks de drift?" → NO** (con un PARCIAL construido-pero-desconectado en drift). **Es una brecha** — pero honestamente declarada: el propio mensaje de `830bf5d` dice *"execution migration is P1"*. El diseño está documentado en `RESILIENCE_DRIFT_DESIGN.md`.

**Brechas a cerrar (P1):** G1 ejecutor que lea `config.load()` (migrar autotrack/viabovag primero); G2 llamar `drift_gate.evaluate` al cierre de cada ciclo del coordinator; G3 baseline de volumen por portal en la ruta viva; G4 backfill de `schema_registry` (69/70 portales sin baseline); G5 `nl_rdw` no está en `orchestrator._SOURCES` (corre solo por invocación manual; fan-out por país **necesita código**, no config — refuta parcialmente la afirmación "country-agnostic por config" del NL report a nivel de orquestación).

---

## 8. D5 — No regresión + Higiene ejecutada `[V]`

- **Suite: `1246 passed, 0 failed` en 8.70s** `[V]` — **por encima** del ~1235 esperado (resiliencia añadió `test_drift_gate`+`test_portal_config`). **Cero regresiones.**
- **Higiene ejecutada por mí (reversible, en scope):**
  - 🗑️ Borrada rama **`feature/p0-rewiring`** (era `4ad40cb`, **0 commits únicos**, ancestro de `-canon` — confirmado por `git log --not` antes de borrar). Recuperable por reflog.
  - 🗑️ Limpiados: `scrapers/.fuse_hidden*` (×2, basura FUSE), `scrapers/coordinator.out.log.old` (log stale), mi `.guardian_pytest.log`, contenedor `cardex-redis-throwaway`.
  - ✋ **Preservados** (NO borrados — posible trabajo del dueño): `run_coordinator_supervised.py` (supervisor OOM, crítico), `check_now.ps1`/`relaunch.ps1`/`retry_all.ps1`/`verify_status.ps1`.
- **Disco: 91% (46GB libres)** — watch item, no crítico. `.git`=233MB.
- **Block0 hazard VIVO:** `C:\Users\elias\CARDEX` @ `42dec67` (68 commits atrás de main, 0 únicos en historia) con **trabajo frontend único sin commitear** (`workspace/web/src/...`). **NO lo toqué** (tiene trabajo único). Bundle de rescate intacto en `AUDIT_SCRATCH/block0_rescue/`. **Decisión del dueño** consolidar.

---

## 9. Backlog priorizado

**P0 — antes de declarar el producto vivo (no bloquean el merge, sí el "go-live"):**
- Correr el seam a escala: backfill (re-encolar punteros sin `vehicles`) + arrancar `enrich-worker`/`pipeline` contra redis vivo. *(la fontanería ya está probada)*

**P1 — antes de correr el seam a escala (cerrar fugas):**
1. **Reclaim del seam** (H1): XAUTOCLAIM periódico en A6/A7 o no perderás transient/error a escala.
2. **`FX_RATE_CHF`** en compose + fijar `moneda='CHF'` en scrapers CH → o el 41,8% sale con eur NULL / mal-etiquetado.
3. **Autovacuum/ANALYZE** + índice `(country,precio,anio)` tras poblar.
4. **Partición de `vehicle_events`** (RANGE mensual) + índice `ts`.
5. **Cablear drift-gate** al coordinator (G2) + baseline volumen (G3) + backfill `schema_registry` (G4).
6. **A6 red de seguridad** por-mensaje (H2). Filtrar **camiones truckscout24** del scope.
7. **Re-run portales libres** (autotrack, paruvendu, 2dehands, gowago, clicars) → +~700k sin proxy.

**P2 — escala/calidad:**
- Migrar portales a ejecución config-driven (G1); `nl_rdw`→`orchestrator._SOURCES` (G5); split make/model (P-4); `url_hash`→bytea (P-5); capa fuzzy V21 (entity dealers).

**P3 — capital-gated:**
- Proxies residenciales para gigantes (mobile.de, AutoScout24×6, leboncoin, marktplaats) → ~4M+ listings.

**Doc/Infra:**
- Actualizar `CONTEXT_FOR_AI.md` (stack real). Poblar o **parar ClickHouse** (P-6). Resolver Block0 (dueño).

---

## 10. Recomendación de consolidación — **GO (fast-forward), con condiciones**

**Recomendación: MERGEAR `feature/p0-rewiring-canon` → `main` por fast-forward.** No lo ejecuto; queda para el orquestador.

**Por qué es seguro y debido:**
- `[V]` 0 detrás / **7 delante** de main → fast-forward sin conflictos; `main` intacto durante toda la auditoría.
- `[V]` Suite **1246 verde, 0 regresiones**; los 1188 originales siguen pasando.
- El cambio es **aditivo** (nuevos: enrich_worker, rich_consumer, fx_eur, entity_resolver, nl_rdw, config, drift_gate, dashboard) + ediciones quirúrgicas (base.py, coordinator.py, docker-compose.yml).
- **Corrige un bug de corrupción de datos** (P0-1: un bloqueo transitorio borraba el inventario entero de un portal vía `delete_stale`). `main` HOY tiene ese bug → merge es **net-positivo y algo urgente**.
- Rompe el monocultivo FR en discovery y tiende un seam probado.

**Las condiciones NO bloquean el merge** (son forward-looking, y los workers están dormidos en prod): el merge no empeora nada. **Pero el punch-list P1 (§9) es obligatorio ANTES de activar el seam a escala** — sobre todo reclaim (H1), FX CHF y autovacuum/partición. Activar el backfill sin cerrarlos producirá pérdida silenciosa de datos (PEL) y un 41,8% del índice con precio inválido.

**Lo que NO debe leerse como hecho:** "508K listings" = 508K URLs sin atributos; "30 vehicles" = seed, no producto; "RDW done" = 1,2% del censo; "resiliencia" = scaffolding sin cablear. El merge consolida **fontanería probada**, no un producto poblado.

**Independiente del merge:** resolver el hazard Block0 (segundo checkout con frontend único) — decisión del dueño.

---

*GUARDIAN — autointerrogatorio de cierre: ¿afirmé algo sin verificar? No — cada cifra tiene comando (las de subagente, re-ejecutadas por mí). ¿Di un "done" por bueno con cobertura parcial sin explicar el faltante? No — cuantificado en §3/§4. ¿Refuté cada "completo"? Sí — H1/H2/H3 sobre el seam, config/drift sobre resiliencia, cobertura real vs anunciada. ¿Toqué main o prod más allá de higiene reversible? No. Fin del informe.*
