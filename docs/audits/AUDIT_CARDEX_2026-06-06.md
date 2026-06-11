# AUDITORÍA INTEGRAL Y ADVERSARIAL — CARDEX

**Fecha:** 2026-06-06 · **Repo auditado:** `C:\Users\elias\projects\cardex` (`main` @ `6e084a5`, remote `github.com/sublimine/CARDEX.git`)
**Naturaleza:** SOLO DIAGNÓSTICO. No se modificó código de producción, no se abrieron PRs, no se tocó `main`. Toda lectura sobre PG/SQLite fue de solo-lectura.
**Método:** verificación empírica directa (consultas a PostgreSQL vivo, SQLite `engine.db`, logs de runtime, `docker ps`, builds Go) + 4 agentes forenses paralelos sobre el código. Cada cifra material se midió ejecutando algo; lo no verificable se marca `[NO VERIFICADO]` / `[ASUMIDO]`.

---

## 0. ADVERTENCIA PREVIA — existen DOS repos CARDEX divergentes

El usuario pidió detenerse si este no fuera el repo correcto. **Lo es**, pero el hallazgo es relevante:

| | `projects/cardex` (ESTE, auditado) | `C:\Users\elias\CARDEX` (el otro) |
|---|---|---|
| `main` @ | `6e084a5` (2026-06-06 20:41) | `42dec67` (2026-06-02 13:04) |
| ¿contiene `6e084a5`? | sí | **NO** (`fatal: Not a valid object name`) |
| `.py` en `scrapers/` | **226** | 84 |
| Foco de commits recientes | scrapers/discovery (objeto de esta auditoría) | frontend `workspace/web` (landing/shaders) |
| Trabajo sin commitear | scripts ops | `workspace/web` (Landing, DESIGN.md, audits) |

Ambos comparten `origin/main`. **Riesgo de higiene git:** dos working copies divergentes apuntando al mismo remoto; un push desde el rezagado pisaría trabajo. `projects/cardex` es el correcto (commits más recientes, todo el trabajo de scraping, y a donde apuntan sesión/CLAUDE.md/memoria).

---

## 1. RESUMEN EJECUTIVO (honesto y crudo)

CARDEX **no cumple hoy ninguno de los dos GOALs**, pero **no es un esqueleto para tirar**. Es ingeniería real, bien testeada, **parada en seco por tres muros**: (1) techo económico (sin proxies ni registros de pago), (2) cableado/orquestación incompleta entre piezas que individualmente funcionan, y (3) un puñado de bugs concretos. La distancia entre "lo que hay" y "lo que se pide" es grande pero salvable construyendo encima, no reescribiendo.

### Veredicto contra GOAL #1 (inventario íntegro y live de cada portal)
**NO DA LA TALLA — cobertura real ≈ fracción mínima del mercado.**
- `vehicle_index` (PostgreSQL, store real) = **508.339 listings** [VERIFICADO `count(*)`], pero concentrados en **solo 20 dominios**, todos medianos/agregadores.
- **Los 8 portales líderes están en CERO listings**: `mobile.de`, `autoscout24.{de,fr,es,nl,be,ch}`, `leboncoin.fr`, `coches.net`, `milanuncios.com`, `kleinanzeigen.de`, `lacentrale.fr`, `wallapop.com`. Es decir, **0% del grueso real del mercado europeo de VO.** El ejemplo del encargo (mobile.de 4,4M → objetivo 4,4M) está hoy en 0.
- Causa raíz: son T2/T3 (Akamai/DataDome/Cloudflare) y el sistema tiene **18 identidades, todas `direct`, CERO proxies** [VERIFICADO `engine.db`]. Sin proxy residencial parkean en `no_identity` por diseño. **No es un bug; es el bloqueador económico que el propio PLAN.md §0 declara como Clase B `[NEEDS-PROXY]`.**

### Veredicto contra GOAL #2 (~900K+ dealers de los 6 países, balanceado)
**NO DA LA TALLA — y la cadena de dealers está muerta tras el primer eslabón.**
- `discovery_candidates` = **460.078** [VERIFICADO], pero **84% son franceses** (FR 388K) y **78% de una sola fuente** (registro SIRENE, 360K). DE 45K, ES 12,8K, NL 5,4K, CH 4,3K, BE 4K.
- **Solo el 6,2% (28.570) tiene dominio web**; el 93,8% son razones sociales SIRENE sin web → no crawleables.
- `sitemap_status` de los 460.078 = **`pending`** (cero sitemaps probados). **`indexed_dealers = 0`, dealers crawleados = 0.** `dealers`=0, `dealer_inventory`=0, `crawl_frontier`=0. **NI UN SOLO dealer individual ha sido indexado.** El path T3 (long-tail) está al 0% de ejecución.

### Qué se SALVA (pepitas de oro — construir encima, no tirar)
1. **Motor anti-detección `scrapers/engine/` — REAL y cableado** (~3.599 LOC, 31 archivos): TLS/JA3 vía `curl_cffi impersonate`, Camoufox, identity store, circuit breaker, warming 3-fases, behavioral Bézier. Usado en el camino vivo (`coordinator.py:418`). Solo 2 puntos de degradación honesta declarada (`tcp.py:96`, `sensor.py:96`), no stubs falsos.
2. **`portals/base.py` — template-method sólido**: sink streaming (no acumula millones en RAM), detección estructural de cap → subdivisión, refetch de página-cero anti-truncación. Buena ingeniería.
3. **Pipeline de indexación que SÍ funciona E2E parcial**: `coordinator.py` → `indexer.StreamingDeltaSink` → `vehicle_index` (508K) + `vehicle_events` (539K SEEN/GONE). Delta funcional.
4. **`generic_extractor.py` (T3 dealer) — COMPLETO y testeado** (JSON-LD→wp-json→sitemap→microdata). Solo le falta estar cableado.
5. **Módulos Go core** (`discovery`/`extraction`/`quality`): `GOWORK=off go vet ./...` **limpio en los 3**; E01-E13 y V01-V21 son código sustancial real (no stubs).
6. **Tests verdes: 1.188/1.188 passed** en 5,58s [VERIFICADO, suite Python completa mockeada].
7. **Discovery de candidatos sobre fuentes abiertas funciona** (SIRENE 360K, OSM 99K reales).

### Qué se REFORMULA
- **Discovery multi-país**: romper la dependencia 84% francesa. FR tiene SIRENE abierto; el resto necesita yellow-pages/OEM-locators/OSM exhaustivo + resolución name→domain a escala (hoy solo 78 hits).
- **Cableado del enriquecimiento y de la cadena de dealers** (ver §4): hoy son piezas correctas sin tubería entre ellas.
- **Consolidar los DOS sistemas de discovery** (Go→SQLite vs Python→PG) y los DOS pipelines (Go-SQLite vs Python-PG) en uno solo. Hoy compiten y se canibalizan.
- **Diccionario de términos de dealer**: existe y el mapeo idioma↔país es correcto, pero hay huecos (CH sin italiano, BE inconsistente) y duplicación anti-DRY en 6+ archivos.

### Qué se TIRA (código muerto verificado)
- ~13 dirs top-level que solo contienen `.exe`/`node_modules` gitignored (cascarones de build, 0 archivos tracked): `alpha, api, core-api, gateway, corporate, edge, financial, forensics, pipeline, vision, bin, terminal, ingestion, b2b-dashboard`.
- Duplicación: `api/`+`core-api/`+`gateway/` → superados por `services/api/` (31 .go vivos). `pipeline/` → `scrapers/pipeline/`. `terminal/` → `frontend/terminal/`.
- 6 archivos planos legacy de portal sombreados por sus paquetes homónimos + 2 bases huérfanas (`HtmlSearchScraper`, `HttpPortalScraper`) sin un solo consumidor.
- `.fuse_hidden*` = WAL/shm huérfanos de `engine.db`; `coordinator.out.log.old`; doble `.pre-commit-config.{yaml,yml}`.

### ¿Reescribir el esqueleto desde cero o construir encima?
**CONSTRUIR ENCIMA.** Reescribir tiraría 3.600 líneas de anti-detección real + un template de portal sólido + un generic_extractor completo + 1.188 tests verdes + módulos Go que compilan. Los fallos no son de arquitectura podrida sino de **(a) presupuesto cero** (proxies/registros — aparcado en backlog, no es deuda de código) y **(b) cableado/orquestación** que se arregla con trabajo dirigido, no con borrón y cuenta nueva. La única deuda estructural real es la **duplicación de pipelines/discovery** que conviene unificar antes de escalar.

---

## 2. INVENTARIO REAL DE PORTALES

**Conteo verificado: 71 portales registrados** en `_PORTAL_CLASSES` (`scrapers/portals/__init__.py:88-175`) y en `work_queue` (`engine.db`, 71 filas). El "71" del encargo es correcto **como conteo de registro** (no como conteo de portales que producen datos).

**Por clase base** [VERIFICADO]: 45 `BasePortalScraper` directo · 19 `SitemapListingScraper` · 6 `AutoScout24Scraper` · 1 `TuttiCHScraper` (anibis hereda de tutti).

**Estado de cola** (`engine.db work_queue`): 28 `done` · 42 `pending` · 1 `running`. **Pero "done" ≠ cobertura**: 12 de los 28 "done" produjeron 0 filas (fallo silencioso, ver §2.3).

### 2.1 Portales CON datos reales en `vehicle_index` (los únicos que producen)

| Portal | País | Estrategia | Listings (VERIFICADO) | Cuello de botella | Veredicto |
|---|---|---|---|---|---|
| autolina.ch | CH | API-JSON | 89.944 | — (parece ~completo p/ su tamaño) | DA LA TALLA |
| tutti.ch | CH | Next.js embebido | 81.558 | OOM intermitente en host low-RAM | DA LA TALLA |
| viabovag.nl | NL | Next.js/data-route | 80.800 | — | DA LA TALLA |
| truckscout24.com | DE | sitemap-XML | 72.225 | (camiones, no turismos) | DA LA TALLA (nicho) |
| gaspedaal.nl | NL | JSON-LD | 58.396 | — | DA LA TALLA |
| anibis.ch | CH | hereda tutti | **40.000** (redondo) | **CAP no batido** | REFORMULAR (subdividir) |
| autohero.com | DE | API-JSON | 19.195 | — | DA LA TALLA |
| vroom.be | BE | sitemap | 17.983 | — | DA LA TALLA |
| autotrack.nl | NL | curl_cffi pager | 16.927 | — | DA LA TALLA |
| ocasionplus.com | ES | API-JSON | 13.518 | — | DA LA TALLA |
| simplicicar.com | FR | sitemap | 5.997 | — | DA LA TALLA |
| marktplaats.nl | NL | API-móvil (T0) | 4.107 | **DataDome; real ≫** | NO DA LA TALLA |
| occasions.jeanlain.com | FR | sitemap | 2.542 | — | DA LA TALLA (dealer) |
| distinxion.fr | FR | sitemap | 1.597 | — | DA LA TALLA (dealer) |
| paruvendu.fr | FR | HTML | 1.182 | posible cap | REFORMULAR |
| comparis.ch | CH | Next.js | **1.000** (redondo) | **CAP no batido** | REFORMULAR (subdividir) |
| 2ememain.be | BE | API-móvil | 660 | DataDome; real ≫ | NO DA LA TALLA |
| 2dehands.be | BE | API-móvil | 651 | DataDome; real ≫ | NO DA LA TALLA |
| clicars.com | ES | API-JSON | 35 | harvest casi vacío | REFORMULAR |
| gowago.ch | CH | API-JSON | 22 | harvest casi vacío | REFORMULAR |

> `anibis.ch=40000` y `comparis.ch=1000` son números redondos exactos = topes de paginación no batidos por subdivisión (evidencia estructural de cobertura incompleta). `marktplaats/2dehands/2ememain` son T0 vía API móvil pero dan cifras ridículas frente a su inventario real (DataDome limita).

### 2.2 Portales GIGANTES en CERO (0% del mercado real) — bloqueo económico

| Portal | País | Tier/WAF | Listings | Cuello de botella | Veredicto |
|---|---|---|---|---|---|
| mobile.de | DE | T2 Akamai | **0** | `[NEEDS-PROXY]` sin identidad proxy | NO DA LA TALLA (aparcado) |
| autoscout24.de/.fr/.es/.nl/.be | DE/FR/ES/NL/BE | T2 Akamai | **0** | `[NEEDS-PROXY]`; además configs AS24 ausentes (INTEL.md) | NO DA LA TALLA (aparcado) |
| autoscout24.ch | CH | T2 CF | **0** | 403 datacenter | NO DA LA TALLA (aparcado) |
| leboncoin.fr | FR | T3 DataDome | **0** | `[NEEDS-PROXY]` | NO DA LA TALLA (aparcado) |
| coches.net | ES | T3 DataDome | **0** | `[NEEDS-PROXY]` (soft-block en log) | NO DA LA TALLA (aparcado) |
| milanuncios.com | ES | T3 DataDome | **0** | `[NEEDS-PROXY]` | NO DA LA TALLA (aparcado) |
| kleinanzeigen.de | DE | T2 Akamai | **0** | `[NEEDS-PROXY]` | NO DA LA TALLA (aparcado) |
| lacentrale.fr | FR | T3 CF/Akamai | **0** | `[NEEDS-PROXY]` | NO DA LA TALLA (aparcado) |
| wallapop.com | ES | T0 PerimeterX | **0** | **BUG `_paginate` (corregido en HEAD, falta re-run)** | REFORMULAR (re-ejecutar) |
| zoomcar.fr | FR | T2 | **0** | `no_identity` | NO DA LA TALLA (aparcado) |

> Totales "anunciados" de estos portales: `[ASUMIDO público, NO verificado en vivo en esta auditoría]` — del orden de cientos de miles a millones cada uno. Lo VERIFICADO es que su contribución actual es **0**.

### 2.3 BUG de fallo silencioso — 12 portales "done" con 0 filas [VERIFICADO]

`annonces-automobile.com, aramisauto.com, autosphere.fr, capcar.fr, caravenue.com, cardoen.be, carizy.com, classic-trader.com, flexicar.es, myway.be, starterre.fr, youcar.be` → status `done`, `attempts=0`, `last_error=NULL`, **0 filas**.

**Causa raíz** (verificada en código): `ZeroUrlTracker` exige **3 ciclos vacíos consecutivos** (`softblock.py: ZERO_URL_CYCLES=3`), pero todo `SitemapListingScraper`/pager-global tiene **un solo segmento** (`sitemap_listing_base.py:66`, `partition_params` = single segment) → aporta 1 muestra < 3 → nunca dispara soft-block → `RunStatus.OK` → el coordinator marca `done` con harvest 0 y sin error. **Un harvest vacío se confunde con éxito.** Bug real, de severidad ALTA (corrompe la señal de cobertura).

### 2.4 Portales soft-blocked en la última tirada (IP datacenter)
`auto.de, auto-selection.com, autoboerse.de, autohaus24.de, autohus.de, autokopen.nl, autowereld.nl, belgiemobiel.be, buscocoches.com, carforyou.ch, comparis.ch, gueudet.fr, largus.fr, leparking.fr, moniteurautomobile.be, nederlandmobiel.nl, pkw.de, reezocar.com, spoticar.fr` → `soft block 3 empty cycles` / `all 3 attempts failed` / `could not resolve buildId` en `coordinator.out.log`. Código correcto; bloqueo operativo por egress de datacenter.

### 2.5 Crashes de runtime observados [VERIFICADO en logs]
- **`MemoryError`** en `tutti.ch`, `autoboerse.de`, `autocasion.com` al materializar `response.text` en host low-RAM (`curl_cffi/models.py`). Ya mitigado en HEAD por `base.py:_read_body` (captura MemoryError→""), pero el host sigue siendo el cuello.
- **`TypeError: WallapopComScraper._paginate() takes 4 positional arguments but 6 were given`** — firma vieja override. Corregido en HEAD `6e084a5`; `work_queue` aún muestra estado viejo `unhandled_exception` (falta re-run).

### 2.6 Portales relevantes AUSENTES (deberían estar)
- **AutoUncle** (meta-agregador presente en los 6 países — un solo conector cubriría todos los mercados). Ausencia transversal de alto impacto.
- **caradisiac.com** (FR), **gebrauchtwagen.de** (DE), variantes `autouncle.{de,fr,es,nl,be}`.
- `promoneuve.fr` está en `domain_map` (T3) pero es solo coche nuevo y sin scraper registrado.

---

## 3. DISCOVERY CRAWLER (dealers)

### 3.1 Estado real de cobertura [VERIFICADO]

| País | Candidatos | Con dominio | Comentario |
|---|---|---|---|
| FR | 388.423 (84%) | 5.044 | dominado por SIRENE (sin web) |
| DE | 45.103 | 16.575 | mayor mercado de Europa, casi todo OSM sin verificar |
| ES | 12.818 | 1.463 | famélico |
| NL | 5.430 | 2.913 | famélico |
| CH | 4.256 | 1.393 | famélico |
| BE | 4.048 | 1.182 | famélico |
| **Total** | **460.078** | **28.570 (6,2%)** | **objetivo ~900K balanceado** |

**Por fuente:** sirene 360.162 (78%) · osm 98.865 · oem:bmw 606 · ct_logs 367 · name2dom 78.

### 3.2 La cadena está MUERTA tras el candidato [VERIFICADO]
- `sitemap_status` de los **460.078 = `pending`** (cero sitemaps probados).
- `indexer_last_run` = NULL en todos → **0 dealers crawleados**, `sum(indexer_urls_seen)=0`.
- `dealers`=0, `dealer_inventory`=0, `crawl_frontier`=0.

**Por qué** (causas verificadas en código):
1. **93,8% sin dominio**: `sitemap_resolver.py:108` solo procesa `domain IS NOT NULL` → las 431K filas SIRENE quedan `pending` para siempre por diseño.
2. **El resolver de mayor yield (`ddg_worker`) NO está orquestado**: ausente de `master_scheduler` y `watchdog`; solo corrida manual. `name_to_domain` (único que corrió, 78 hits) tiene match durísimo (ambos tokens en apex del cert SSL).
3. **Dos arquitecturas post-candidato compiten y ninguna corre sostenida**: el flujo productivo (`candidates→sitemap_resolver→sitemap_bridge→vehicle_index`) coexiste con una arquitectura alternativa (`dealer_classifier`/`frontier_runner`/`crawl_frontier`) **con tests pero nunca cableada**.
4. **El `orchestrator` solo hace fan-out** (pobló los 460K bien); depende del scheduler/watchdog, que no están vivos en el host (consistente con el OOM del coordinator).

### 3.3 Diccionario de términos por país/idioma — el "bug conocido" NO se reproduce
[VERIFICADO] El mapeo idioma↔país es **CORRECTO**: DE→alemán, FR→francés, ES→español, NL→neerlandés, BE→NL+FR, CH→DE+FR (`common_crawl.py:50-57`, `ct_logs.py:39-67`, `ddg_resolver.py:58-65`, `ch_zefix.py:53-62`). **NO hay español-contra-Alemania ni cruce equivalente.**

**Defectos REALES (de cobertura, no de cruce):**
1. **CH sin NINGÚN término italiano** (Tesino sin cobertura).
2. **BE inconsistente** entre módulos (algún módulo omite `autobedrijf` y/o los términos franceses).
3. **Fragmentación anti-DRY**: los mismos términos copiados en 6+ archivos.
4. **`ddg_resolver` pobrísimo** (1-2 términos/país vs 8-12 en `ct_logs`).

Veredicto: el diccionario **existe, no es buggy por idioma cruzado, no es monolingüe**, pero está fragmentado y con huecos IT/BE.

### 3.4 Fuentes de discovery — real vs stub
- **Go `discovery/` (15 familias A-O)**: `GOWORK=off go vet ./...` **EXIT 0** (compila limpio). 9 plenamente reales (A,B,C,D,F,G,I,K,M), 4 parciales (E,J,O), 1 mayoritariamente stub (L: maps/linkedin stub, solo youtube real). H y N reales pero inertes sin Playwright/API-keys. **PERO escriben a SQLite `./data/discovery.db` (que ni existe en disco), no a la PG auditada** → universo paralelo invisible.
- **Python `scrapers/discovery/sources/`**: producen datos sirene (360K), osm (99K), oem_bmw (606), ct_logs (367). Estériles/gated: `common_crawl` (CDX 502/503), `ch_zefix` (sin credenciales), `portal_aggregator` (solo AS24-DE).
- **DDG ban**: `[ASUMIDO]` — la memoria lo afirma; el código solo lo marca como riesgo, sin evidencia de ban observado en el repo.

---

## 4. PIPELINE END-TO-END (eslabón por eslabón) [VERIFICADO]

| Eslabón | ¿Código? | ¿Cableado? | ¿Corre? | ¿Datos? | Veredicto |
|---|---|---|---|---|---|
| census | sí (`fleet_census`) | no | no | 0 | AUSENTE en ejecución |
| discovery (candidatos) | sí | sí (Python→PG) | sí | 460K | **FUNCIONA** (sesgado FR) |
| name→domain | sí | parcial | apenas | 78 | CÓDIGO-PERO-CASI-NO-CORRE |
| clasificación dealer | sí | **no** (arq. alternativa) | no | dealers=0 | CÓDIGO-NO-CABLEADO |
| crawl dealer (sitemap probe) | sí | no (solo domain≠NULL) | no | sitemap_status all `pending` | CÓDIGO-NO-CORRE |
| extracción rica (T3 `generic_extractor`) | **sí, completo+test** | **no** (nadie lo invoca) | no | dealer_inventory=0 | CÓDIGO-NO-CABLEADO |
| scraping portales (URL) | sí | sí | sí | vehicle_index 508K | **FUNCIONA** (20 dominios) |
| entity resolution (V21/V12) | sí (790 LOC) | **no** (vive en pipeline Go-SQLite muerto) | no | entities=0, entity_matches=0 | CÓDIGO-NO-CABLEADO |
| delta (SEEN/GONE) | sí | sí | sí | vehicle_events 539K | **FUNCIONA** |
| enrich → `vehicles` (rico) | sí | **roto** (ver abajo) | no | vehicles=30 (semilla) | ROTO |
| vehicle_index | sí | sí | sí | 508K | **FUNCIONA** |

### 4.1 Dónde se rompe exactamente el enriquecimiento [VERIFICADO]
El salto "puntero URL → vehículo rico" no ocurre por **triple gap**:
- El productor escribe `stream:enrich_pending` (solo URLs) — `scrapers/common/indexer.py:27`.
- El consumidor rico Go lee `stream:ingestion_raw` — `services/pipeline/cmd/pipeline/main.go:33`. **Streams distintos: nadie consume lo que el productor emite.**
- `docker-compose.yml:811` lanza `command: ["-m", "enrich_worker"]`, **módulo que no existe** (no hay `enrich_worker.py` en el repo).

Resultado: `vehicles`=30 (semilla vieja), `vin_history_cache`=0, `entities`=0.

### 4.2 Módulos Go core — código vivo EN REPOSO
`extraction` (E01-E13) y `quality` (V01-V21) son código real y sustancial; `go vet` limpio. **Pero ningún proceso/contenedor los ejecuta** y escriben a SQLite `./data/discovery.db`, no a la PG cardex. Son la "Strategy A SQLite" superada por el pipeline Python→PG. Los 460K/508K son del Python, no de ellos. Únicos stubs: E10 (skeleton) y E07 (interceptor no-op por defecto).

### 4.3 Crash `cardex-api` en vivo [VERIFICADO]
`docker logs cardex-api` repite `lookup postgres on 127.0.0.11:53: no such host`. El contenedor vivo está SOLO en la red `cardex_default`, mientras `cardex-pg` (alias DNS `postgres`) vive en `cardex_data` → DNS interno no resuelve. **Causa: topología de red obsoleta del contenedor, no bug de código.** Fix esperado: `docker compose up -d` (no aplicado — esto es diagnóstico).

### 4.4 Contradicción documental resuelta
`CONTEXT_FOR_AI.md` afirma "no PostgreSQL / ClickHouse / Redis / MeiliSearch — storage es SQLite". **FALSO contra la realidad**: `docker ps` muestra `cardex-pg`, `cardex-ch`, `cardex-meili`, `cardex-redis`, `cardex-grafana`, `cardex-prometheus`, `cardex-web` todos healthy. El store real rico es PostgreSQL. **CONTEXT_FOR_AI.md está stale (predata Strategy B); gana el código observado.**

---

## 5. ANTI-DETECCIÓN — ¿real o teatro?

**REAL, no teatro** [VERIFICADO leyendo 31 archivos / 3.599 LOC]. Cableado al runtime (`coordinator.py`, `scheduler.py`, `portals/base.py`, `cli/bootstrap.py` lo importan y usan).
- TLS/JA3 (`curl_cffi impersonate`) en el camino vivo (`coordinator.py:418` → `tls.make_session`).
- Camoufox + camino T2/T3 (browser pool, behavioral Bézier, conditioning, warming 3-fases): código real y completo, **latente** porque no hay proxies (`proxy_health`=0 filas).
- Solo 2 degradaciones honestas declaradas: `tcp.py:96` (httpcloak ausente) y `sensor.py:96` (`refresh_abck` → None). Caen al fallback en vez de fingir éxito.
- PLAN.md/INTEL.md (en `scrapers/`) describen behavioral/warming como "base" cuando el código ya los tiene completos: **la doc va por detrás del código.**

---

## 6. ESTADO GIT / HIGIENE [VERIFICADO]

- `git status`: limpio salvo untracked ops scripts (`check_now.ps1`, `relaunch.ps1`, `retry_all.ps1`, `verify_status.ps1`, `run_coordinator_supervised.py`) + `.fuse_hidden*` + `coordinator.out.log.old`.
- `git worktree list`: solo el principal. `git stash list`: vacío. **Sin zombis.**
- Ramas remotas (`codex/auditar-sistema-de-indexacion-completo`, `codex/cardex-13-10-functional-coverage-plan`, `phase5-portals`): **ahead_of_main = 0** → su contenido ya está en `main`, solo están rezagadas.
- **No hay git hook de auto-commit**: `.git/hooks` vacío (solo gitleaks pre-commit); el "auto-commit" es el script untracked `auto_commit_check.ps1` (`git add/commit/push origin main`) — **riesgo si se ejecuta desatendido** (puede pushear a main sin review).
- `.fuse_hidden*` = WAL/shm huérfanos de `engine.db` (borrado de archivo abierto en montaje FUSE), no código.
- **Segundo checkout divergente** en `C:\Users\elias\CARDEX` (ver §0).

---

## 7. DEUDA TÉCNICA / DUPLICACIÓN / CÓDIGO MUERTO

| Item | Estado | Acción sugerida |
|---|---|---|
| `alpha,api,core-api,gateway,corporate,edge,financial,forensics,pipeline,vision,bin,terminal,ingestion,b2b-dashboard` | cascarones `.exe`/`node_modules`, 0 tracked | borrar del árbol o `.gitignore` explícito |
| `api/`+`core-api/`+`gateway/` vs `services/api/` (31 .go vivos) | duplicado | consolidar en `services/api` |
| `pipeline/` (worker.exe) vs `scrapers/pipeline/` (Python) | duplicado | quedarse con el Python vivo |
| `discovery/` Go (→SQLite) vs `scrapers/discovery/` Python (→PG) | **dos discovery** | unificar; el Python es el que produce |
| `extraction/`+`quality/` Go (→SQLite) vs `scrapers/pipeline/` Python (→PG) | **dos pipelines** | decidir uno; entity resolution Go está aquí |
| 6 `.py` planos de portal + 2 bases huérfanas | muerto | borrar |
| `internal/shared` en go.work sin importadores | huérfano | revisar |
| `.pre-commit-config.{yaml,yml}` | duplicado | unificar |
| `STATUS.md` (2026-04-27) y `CONTEXT_FOR_AI.md` (2026-04-15) | stale, contradicen el código | reescribir contra la realidad |

---

## 8. BACKLOG APARCADO (presupuesto cero — no bloquea, pero gobierna el techo)
1. **Proxies residenciales/ISP** (Decodo/Oxylabs) → desbloquea los 10 gigantes T2/T3 (mobile.de, AS24×6, leboncoin, coches.net, milanuncios, kleinanzeigen, lacentrale). **Sin esto, GOAL #1 es estructuralmente inalcanzable** en su grueso.
2. **API keys** carapis.com / auto-api.ch (conectores ya escritos, `[NEEDS-KEY]`).
3. **Fuentes de dealers no-FR** (yellow-pages, OEM-locators completos, registros DE/ES/NL/BE/CH de pago) → para acercarse a los 900K balanceados.
4. **Captcha solver** (capsolver) para challenge de DataDome/PerimeterX.

---

## 9. PRIORIZACIÓN DE ARREGLOS (orden recomendado, todo "construir encima")

**P0 — bugs que corrompen señal o bloquean (gratis, sin presupuesto):**
1. Arreglar fallo silencioso de soft-block (los 12 "done con 0 filas"): tratar harvest-0 en portal de 1 segmento como sospecha, no como éxito.
2. Re-ejecutar wallapop (bug `_paginate` ya corregido en HEAD).
3. `docker compose up -d` para recablear `cardex-api` a la red `cardex_data`.
4. Batir caps de `anibis.ch`/`comparis.ch` (subdivisión por año/precio/marca).

**P1 — cableado de la cadena (gratis):**
5. Crear el `enrich_worker` faltante o alinear streams (`enrich_pending` ↔ consumidor) para llenar `vehicles`.
6. Cablear `generic_extractor` (T3) al crawl de los 28.570 dealers con dominio → primer inventario de dealers real.
7. Orquestar `ddg_worker`/`name_to_domain` para subir el ratio con-dominio desde 6,2%.
8. Cablear/ubicar entity resolution (V21/V12) contra la PG real.

**P2 — consolidación estructural (gratis):**
9. Unificar los dos discovery y los dos pipelines; borrar cascarones muertos.
10. Reescribir `CONTEXT_FOR_AI.md` y `STATUS.md` contra la realidad observada.
11. Completar diccionario de términos (IT para CH, normalizar BE, DRY a un solo módulo).

**P3 — con presupuesto (backlog §8):** proxies → gigantes; fuentes no-FR → 900K dealers.

---

## Anexo — Evidencia y reproducibilidad
- Conteos PG: `docker exec cardex-pg psql -U cardex -d cardex -c "SELECT count(*) FROM <tabla>"`.
- Estado scraping: `scrapers/engine.db` (SQLite WAL) tablas `work_queue`, `domain_tier_state`, `identities`.
- Logs runtime: `scrapers/coordinator.live.log`, `coordinator.out.log`, `monitor.log`.
- Builds: `cd {discovery,extraction,quality} && GOWORK=off go vet ./...` (limpio).
- Tests: `cd scrapers && python -m pytest tests -q` → 1.188 passed.
- Informes forenses detallados por área: `C:\Users\elias\AUDIT_SCRATCH\{portales,discovery,pipeline,engine_git}.md`.
- Stack vivo: `docker ps` (8 contenedores; `cardex-api` en crash-loop por red).

*Fin del informe. Cero archivos de producción modificados durante la auditoría.*
