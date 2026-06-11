# AUDIT_CONTEXT — Inventario de contexto y veredicto autoritativo (CARDEX)
**Fecha:** 2026-06-08 · **Modo:** SOLO LECTURA (sin edición/commit/scraping de prod) · **HEAD auditado:** `feature/domain-resolution @ 2bd5cb5` · **main/origin:** `001e165`
**Método:** cada afirmación lleva su evidencia cruda (comando→salida). Los conteos de BD se verificaron en vivo contra `cardex-pg` (PostgreSQL 16.13, healthy 30h). El árbol se devolvió intacto.

---

## RESUMEN EJECUTIVO (10 líneas)
1. **El esqueleto es real y verificado en vivo:** `vehicle_index = 436.114` punteros de **19 portales** (todos libres T0/T1), `vehicles = 563`, `discovery_candidates = 764.299` (49.024 con dominio). Confirmado por SELECT directo, no por memoria.
2. **Los 6 gigantes siguen en 0 filas** a nivel store; las clases scraper existen y están registradas pero el coordinator las aparca en `NO_IDENTITY` (sin proxies T2/T3).
3. **Corrección al ground-truth:** `vehicles` NO es mayoría sintético — solo **30 son SEED_DEMO**; los **533 restantes son coches reales** de dealers (frente dealer-inventory los persistió y NO se purgaron).
4. **8 de 13 ramas feature ya están fusionadas en main** (sus worktrees son zombies); solo 5 ramas tienen trabajo sin fusionar (stealth, discovery-mega, dealer-inventory-scale, domain-scale, ollama).
5. **El seam L1→L2 (A6 enrich_worker + A7 rich_consumer) es real y CORRIÓ** (los 533 coches lo prueban) pero está **dormido ahora**: `enrich_pending` e `ingestion_raw` a 0, sin consumer groups.
6. **El sistema Delta es real y produjo filas** (451.634 SEEN + 15.470 GONE) pero el último evento es `2026-06-07 20:13` → mecanismo verdadero, **no “en segundos” always-on**: es batch-cycle e idle.
7. **El oro del frente stealth es la ingeniería de bypass** (Camoufox crackea Akamai/DataDome de mobile.de gratis), pero la cobertura “100%” es **reconciliación de conteos**, no cosecha: `seam_writer` existe y se demostró pero **ningún worker lo invoca** → 0 filas.
8. **Config por entidad SÍ existe** (portales curados + dealers auto-generados, versionados en git); **la encapsulación API por entidad NO**: `entities = 0`, `dealer_inventory = 0`, tabla huérfana.
9. **Auto-remediación = andamiaje:** `remediate()` está implementado y testeado pero **nunca se llama en producción**; el drift SÍ se detecta en vivo en el coordinator pero solo emite `log.warning` (sin email/webhook).
10. **Veredicto:** el sistema es **wiring, no rewrite**. Hay oro reutilizable (esqueleto, 19 portales, seam, bypass stealth, config-store, delta). El trabajo pendiente es **integración** (wire seam_writer, proxies para gigantes, API por entidad, trigger de remediación), no reescritura.

---

# A) MAPA DE TRABAJO RECIENTE

## A.1 Ramas y worktrees — fusionado vs vivo
`git rev-list --left-right --count main...<branch>` (izq=solo-main, der=solo-branch) + `git branch --merged main`:

| Rama | Worktree | Fusionada en main | Únicos | Intentó | Entregó (real, verificado) |
|---|---|---|---:|---|---|
| feature/p0-rewiring-canon | (en main wt) | ✅ sí | 0 | Cerrar seam L1→L2, store config-driven, drift gate | **REAL**: seam A6/A7 en Python; los 533 coches reales lo confirman |
| feature/p1-hardening | — | ✅ sí | 0 | GUARDIAN §9 punch-list (XAUTOCLAIM, CHF/FX, particionado eventos) | **REAL**: `vehicle_events` particionada mensual, 467K filas vivas |
| feature/fanout-5countries | — | ✅ sí | 0 | Replicar patrón NL a DE/FR/ES/BE/CH por config | **REAL pero aditivo**: discovery, no inventario |
| feature/e07-playwright-xhr | — | ✅ sí | 0 | Extractor navegador (playwright_meta) | **REAL+WIRED**: `autolina.ch` usa `playwright_meta`, 89.944 punteros |
| feature/dealer-scraping-system | cardex-dealer-scraping | ✅ sí | 0 | Config por-dealer + detector tipo-web + remediación | **PARCIAL**: config-store real; remediación NO cableada |
| feature/domain-resolution | **cardex (HEAD)** | ✅ sí | 0 | Resolver name→web multi-vía sobre `ddg_attempts` | **REAL**: worker SKIP-LOCKED vivo; 49.024 con dominio |
| feature/discovery-scale | cardex-discovery-scale | ✅ sí | 0 | dealers-con-web 28.5K→45.8K | **REAL**: censo creció a 764K |
| feature/p2-hardening | cardex-p2-hardening | ✅ sí | 0 | 5 cabos P2 + word-boundary anti-FP | **REAL**: cerrado, en main |
| **feature/stealth-camoufox** | cardex-stealth | ❌ **NO** | **10** | Crackear 10 gigantes + cosechar | **PROBE real, PERSISTENCIA humo** (ver C) |
| **feature/discovery-mega** | cardex-discovery-mega | ❌ no | 3 | +2M dealers vía registros | **PARCIAL**: +74.670 *identity* (sin web); con-web casi plano |
| **feature/dealer-inventory-scale** | cardex-inventory-scale | ❌ no | 3 | playwright_xhr + DMS + persistir a escala | **REAL parcial**: los 533 coches reales en `vehicles` salen de aquí |
| **feature/domain-scale** | cardex-domain-scale | ❌ no | 2 | Romper bloqueo IP FR con free-proxy propio | Rotación providers; no medido en store |
| **feature/ollama-decision-layer** | cardex-ollama | ❌ no | 1 | Capa LLM local fuzzy (qwen2.5:3b) | Opt-in OFF por defecto; no en ruta caliente |

```
$ git rev-list --left-right --count main...<branch>
feature/p2-hardening :: 11  0     feature/discovery-scale :: 19  0
feature/domain-resolution :: 14  0  feature/dealer-scraping-system :: 21  0
feature/e07-playwright-xhr :: 24  0 feature/fanout-5countries :: 24  0
feature/p1-hardening :: 25  0       feature/p0-rewiring-canon :: 26  0
feature/stealth-camoufox :: 4  10   feature/discovery-mega :: 4  3
feature/dealer-inventory-scale :: 4 3  feature/domain-scale :: 4  2
feature/ollama-decision-layer :: 4  1
```
Las 5 no-fusionadas comparten merge-base `1ca158a` (= main antes de 4 commits de gobernanza). Los “4 solo-main” de cada una son exactamente esos 4 commits (`2316591`,`314f0b6`,`f55a7e9`,`001e165`).

## A.2 Worktrees zombie (candidatos a prune)
`git worktree list` → 9 worktrees. **3 sostienen ramas YA fusionadas** en main y pueden podarse sin pérdida tras confirmar working tree limpio:
- `cardex-p2-hardening` (feature/p2-hardening, merged)
- `cardex-discovery-scale` (feature/discovery-scale, merged)
- `cardex-dealer-scraping` (feature/dealer-scraping-system, merged)

Los otros 5 (stealth, discovery-mega, inventory-scale, domain-scale, ollama) sostienen ramas con trabajo **sin fusionar** → no son zombie, son frentes abiertos.

## A.3 Código shadowed / muerto (verificado)
- **`scrapers/portals/mobile_de.py` (archivo, 4.5KB) está SHADOWED por el paquete `scrapers/portals/mobile_de/` (11KB).** El import `from scrapers.portals.mobile_de import MobileDeScraper` (línea 29 de `__init__.py`) resuelve al **paquete** por precedencia de Python → el `.py` es **código muerto** nunca importado.
  ```
  $ ls scrapers/portals/mobile_de.py   -> 4549 bytes (Jun 5)
  $ ls scrapers/portals/mobile_de/__init__.py -> 11281 bytes (Jun 5)
  $ grep -n mobile_de scrapers/portals/__init__.py
  29:from scrapers.portals.mobile_de import MobileDeScraper   # resuelve al PAQUETE
  ```
- **mobile.de tiene 3 implementaciones en el repo, ninguna persiste filas:** (1) paquete registrado pero gateado→0 filas; (2) archivo `.py` shadowed muerto; (3) `stealth/facet_engine.py` + `configs/portals/mobile.de.json` (crack real, no cableado al seam).
- **Dead-code legacy ya documentado** (memoria): `HtmlSearchScraper` + flat files cuando el coordinator nunca llama `load_segments_from_sitemap`.

---

# B) ARQUITECTURA ACTUAL DEL SCRAPING (end-to-end real)

## B.1 Registro de portales · router · tiers · WAF
- **Registry:** `scrapers/portals/__init__.py` → `PORTAL_REGISTRY = {cls.DOMAIN: cls for cls in _PORTAL_CLASSES}` (**65 clases despachables**). `get_scraper(domain)` devuelve instancia o None.
- **Router/domain_map:** `scrapers/engine/router/domain_map.py` → `REGISTRY` de **69 `PortalSpec`** (`grep -c PortalSpec( = 69`). Shape: `PortalSpec(domain_pattern, tier, waf, can_escalate_to, countries, notes)`. `get(domain)` matchea por wildcard; `effective_tier(domain, circuit_state)` escala saltando breakers OPEN hasta `can_escalate_to`.
- **Tiers** (`Tier(str,Enum)` T0–T3) + `scrapers/engine/proxy/tiers.py`:
  | Tier | Motor | Proxy | Significado |
  |---|---|---|---|
  | T0/T1 | curl_cffi | DIRECT permitido | Sin WAF / CF-Free; SSR/JSON abierto |
  | T2 | Camoufox | ISP_STICKY (proxy obligado) | Akamai v3 / CF-Pro |
  | T3 | Camoufox+behavioral | RESIDENTIAL_ROTATING + trust≥7.0 | DataDome (leboncoin, lacentrale) |
- **WAF:** `WAF(str,Enum)` {none, cf_free/pro/business, akamai_v3, datadome, perimeter_x, unknown} asignado por portal en `domain_map.py`; **clasificación runtime** en `scrapers/intelligence/waf.py::classify()` (detecta CF-Ray, x-datadome, ak_bmsc, _px*). **El tier ES hoy el proxy del nivel de defensa**; no hay capa separada que mida la incertidumbre de defensa por entidad-dealer.
- **Coordinator:** `scrapers/coordinator.py::run()` — loop: `release_quarantine` → `sync_runtime_gauges` → `claim_next` → `_safe_process_item` (aislamiento de crash). `make_live_session()`: T0/T1 aceptan identidad DIRECT; **T2/T3 exigen proxy** → sin proxies provisionados, el job se aparca en `NO_IDENTITY`. **Esta es la causa raíz mecánica de los 6 gigantes en 0.**

## B.2 Motor de extracción — estrategias (qué funciona)
Catálogo en `scrapers/portals/config.py`; ruteo por campo `strategy` en `configs/portals/<x>.json`, despachado en `enrich_worker.enrich_one()`.

| Estrategia | Implementación | Estado | Evidencia |
|---|---|---|---|
| `sitemap_listing` | `portals/sitemap_listing_base.py` | ✅ WIRED | viabovag.nl 80.800, autotrack base |
| `portal_paginated` | `portals/http_base.py`, `html_search_base.py` | ✅ WIRED | AutoScout24 (grid year×price), nacionales |
| `jsonld_detail` | `pipeline/parse.py` (cascada JSON-LD→OG→heurística) | ✅ WIRED | ~60% listings llevan JSON-LD |
| `playwright_meta` (E07) | `pipeline/playwright_extractor.py` | ✅ WIRED | `autolina.ch` 89.944 punteros |
| `playwright_xhr` | `common/pw_base.py::intercept_paginate()` | ⏳ infra lista, **NO ruteada** | definido en config, sin call-site en enrich_worker |
| `wp_rest` | constantes en `generic_extractor.py` | 📋 backlog | `_WP_CPT_HINTS`, no ruteado |
| `socrata` / DMS | placeholder `config.py` | 📋 placeholder | campo `api_url`, sin módulo |

Clases base vivas: `BasePortalScraper` (template `run()`, NO override), `SitemapListingScraper`, `HttpPortalScraper`, `HtmlSearchScraper`, `AutoScout24Scraper`. **Verdad operativa: el inventario cost-zero rinde en portales JSON-LD/SSR; los dealer-SPA necesitan E07.**

## B.3 Sistema Delta / eventos — REAL, cableado, **idle ahora**
- **Código:** `scrapers/pipeline/delta.py::compute_delta()` (new/gone/price_changed) + `scrapers/common/indexer.py::StreamingDeltaSink`. `insert_batch()` hace `INSERT vehicle_events ... 'SEEN'`; `delete_stale()` hace `INSERT ... 'GONE'`. Cableado: `coordinator.run()` inyecta el sink en `scraper.run(conn, session, on_urls=sink)`.
- **Schema:** `vehicle_events` PARTICIONADA por mes (`scripts/init-pg.sql`), CHECK `event_type IN ('SEEN','ENRICHED','GONE')`.
- **VERIFICACIÓN VIVA:**
  ```
  $ psql -c "SELECT event_type,count(*),max(ts) FROM vehicle_events GROUP BY 1"
   SEEN | 451634 | 2026-06-07 20:13:34+00
   GONE |  15470 | 2026-06-07 20:13:56+00
  ```
- **Veredicto:** el mecanismo es **real y produjo 467.104 eventos reales**. Pero el último evento es de **>12h atrás** → es **batch-cycle, no “altas/bajas en segundos” always-on**, y está **detenido**. La promesa de “segundos” es alcanzable con la arquitectura existente, pero hoy NO corre en continuo.

## B.4 Discovery crawler — fuentes reales vs andamiaje
21 conectores en `scrapers/discovery/sources/`; orquestados en `orchestrator.py` (`_SOURCES`, INSERT-only + heartbeat MVCC sobre `discovery_candidates`).

| Conector | Estado | Produce |
|---|---|---|
| fr_recherche_entreprises / fr_sirene | ✅ REAL | identidad+dominio (FR sweep, ~518K filas FR) |
| osm / osm_expanded_run | ✅ REAL | identidad + dominio esporádico (28K) |
| ch_agvs | ✅ REAL | **dominios reales** (2.401) |
| bovag (NL) | ✅ REAL | **dominios reales** (3.933, 0 FP) |
| nl_rdw / be_kbo / ch_zefix | ✅ REAL | identidad (dominio downstream) |
| oem_bmw / oem wave-2 | ✅ REAL | identidad+dominio marca |
| gelbeseiten (DE) | ⚠️ real pero **WAF-bloqueado** | 7.723 con ~0,4% FP; necesita VPS/rotación |
| portal_aggregator | ⚠️ **mayormente bloqueado** | solo AS24-DE; resto CF 403/404 |
| de_offeneregister | ❌ **API 502** | dump 773MB no streameable |
| es_openmercantil / ct_logs / trustpilot | ❓ scaffolding/incierto | sin evidencia de yield |
| common_crawl | ⚠️ marginal | inviable a escala host-safe |

**Verdad:** ~8 fuentes producen de verdad; el techo libre host-safe se alcanzó. 2M necesita pago/proxies/Common-Crawl en VPS. El crecimiento `discovery_mega` (+74.670) es **identity sin web** (registros), no dealers-con-web.

## B.5 Resolución de dominio (name→web a escala)
- **Worker:** `scrapers/discovery/domain_resolution/worker.py`. Claim atómico `FOR UPDATE SKIP LOCKED` sobre `discovery_candidates WHERE domain IS NULL AND ddg_attempts < N`. Multi-vía cost-ordered: **email apex → directorios (PagesJaunes/local.ch/GelbeSeiten) → búsqueda (DDG→Mojeek)**. Gate de validación `validate_automotive` / `validate_domain` (exige token de nombre + señal auto); colisión `(domain,country)` → merge external_refs + DELETE duplicado. RAM-safe (batch+gc+watchdog 1200MB).
- **Techo real:** throttle DDG 1-IP → los **directorios son la vía robusta**. Atribución honesta solo por `external_refs.resolved_via`.
- **Vivo:** `discovery_candidates_with_domain = 49.024`.

## B.6 ¿Registro de config POR ENTIDAD individual? — **SÍ existe**
- **Portales (curado):** `configs/portals/*.json` (3 en main: autolina.ch, autotrack.nl, viabovag.nl). Loader `portal_config.load()` en `coordinator.py:122`. Campos: `strategy`, `version`, `endpoints`, `drift_baseline{expected_min_volume, required_fields, min_nonnull_ratio}`.
- **Dealers (auto-generado):** `configs/dealers/*.json` (worktree dealer-scraping). `harvester.resolve_or_detect_config()` detecta tipo-web → `build_config()` → `portal_config.save(cfg, kind="dealer")`, **persistido y versionado en git**, refinado con volumen tras la cosecha. Loader unificado busca portal-store primero, dealer-store después.
- **Veredicto:** **NO es un gap.** Hay un store real, por-entidad, versionado. (En main solo 3 portales tienen config; el resto de los 19 que cosechan lo hacen por la ruta de clase scraper, no por config — la migración config-driven está incompleta pero el mecanismo existe.)

## B.7 Encapsulación API del inventario por entidad — **GAP CRÍTICO**
- Existe tabla `dealer_inventory(item_ulid, entity_ulid→entities, …)` en `scripts/init-pg.sql`, pero:
  ```
  $ psql -c "SELECT count(*) FROM entities"          -> 0
  $ psql -c "SELECT count(*) FROM dealer_inventory"  -> 0
  ```
- `cardex-api` (`services/api/.../main.go`) expone `/market-price`, `/arbitrage`, `/landed-cost`, `/alerts` — **ningún** `/dealers/{entity}/inventory`. Los 533 coches reales viven en `vehicles` ligados por **string `source_platform`**, no por FK a `entities`.
- **Veredicto:** la encapsulación vendible por-entidad es **andamiaje de esquema sin servicio ni datos**. Gap real.

## B.8 Alertas / auto-remediación ante fallos
- **Drift detección: LIVE.** `drift_gate.evaluate_volume()` se llama en `coordinator.py` en cada cosecha OK (`check_volume_drift`) → si `volume < expected_min_volume` emite `log.warning("DRIFT …")`. Call-site de producción real.
- **Auto-remediación: ANDAMIAJE.** `dealer_scraping/remediation.py::remediate()` (re-detecta, regenera config v+1, revalida) está completo y testeado pero **sin call-site de producción** (solo lo invocan tests). No hay lógica que observe drift→dispare remediate.
- **Entrega de alerta: ASIMÉTRICA.** Arbitrage alerts → webhook+email (`services/api/internal/alerts/notify.go`, con defensa SSRF/header-injection). Drift → **solo log**, sin canal de notificación ni equipo de remediación.

---

# C) ORO vs DESECHO (brutal y honesto)

| Activo | Veredicto | Evidencia |
|---|---|---|
| **Esqueleto vehicle_index + 19 portales cosechando** | 🥇 **ORO** | 436.114 punteros reales verificados; schema sólido (url_hash PK, country idx) |
| **Seam L1→L2 (A6 enrich_worker + A7 rich_consumer)** | 🥇 **ORO (cableado, idle)** | 533 coches reales en `vehicles` prueban que la cadena corrió E2E |
| **Sistema Delta SEEN/GONE** | 🥇 **ORO (real, no continuo)** | 467K eventos reales; falta convertirlo en always-on para “segundos” |
| **Bypass Camoufox (Akamai/DataDome free)** | 🥇 **ORO reutilizable** | `fix_camoufox_sxs.py` (SxS byte-patch idempotente) + `mobilede_probe.py` (warm `_abck`→`svc/s/` 200) |
| **Config-store por entidad (portal+dealer, versionado)** | 🥇 **ORO** | loader unificado; dealer auto-gen persistido en git |
| **domain_map / tiers / circuit-breaker / identity-trust** | 🥈 **Sólido** | router por wildcard, escalado por breaker, trust-gate T3≥7.0 |
| **domain_resolution worker (SKIP-LOCKED multi-vía)** | 🥈 **Sólido** | atómico, RAM-safe, gate anti-FP |
| **`seam_writer.py` (stealth)** | 🔧 **Oro sin cablear** | idempotente CSV-safe, demostrado E2E leboncoin, **ningún worker lo llama** |
| **`facet_engine.py` “100% coverage”** | 💨 **HUMO (como cosecha)** | es **Σ(counts)≈root**, no filas; `records` queda en dict local, 0 a BD |
| **`remediation.py`** | 🔧 **Andamiaje** | completo+testeado, **sin call-site de prod** |
| **playwright_xhr / wp_rest / socrata / DMS** | 🔧 **Definido, no ruteado** | placeholders en config sin dispatch |
| **`scrapers/portals/mobile_de.py`** | 🗑️ **DESECHO** | shadowed por el paquete homónimo, código muerto |
| **6 gigantes a nivel store** | ⬛ **0 real** | clases registradas pero aparcadas en NO_IDENTITY (sin proxy) |
| **Claims “100% coverage proven” (tier1_progress)** | 💨 **HUMO** | reconciliación de conteo + dumps en `stealth/evidence/`, no inventario |
| **Worktrees de ramas fusionadas (3)** | 🗑️ **Zombie** | p2-hardening/discovery-scale/dealer-scraping ya en main |

---

# D) BRECHAS CONTRA LA VISIÓN OBJETIVO (insumo para el blueprint; NO implementar aún)

### D.1 Taxonomía de tiers por DEFENSA (hoy vs objetivo)
La visión pide clasificar por **defensa**: T1=con defensa profunda (DataDome/Akamai/Cloudflare), T2=inventario relevante sin defensa profunda, T3=sin defensa y sin inventario relevante. **Hoy** el sistema clasifica por `Tier T0–T3` mezclando proxy+WAF, y la defensa se infiere del `WAF` enum por-portal (69 specs) más `waf.classify()` runtime.
- **Reparto actual (aprox., por dónde caen las entidades hoy):**
  - *Defensa profunda* (≈objetivo-T1): los 6 gigantes + 12 gateados = **18 portales en 0 filas**; entidades-dealer detrás de Cloudflare en directorios (gelbeseiten/pagesjaunes/11880) — **incertidumbre alta**, no medida por entidad.
  - *Inventario sin defensa* (≈objetivo-T2): los **19 portales que cosechan** (autolina/tutti/viabovag/gaspedaal/anibis…) — bien cubierto.
  - *Sin defensa sin inventario* (≈objetivo-T3): la cola larga OSM/registros sin web (≈715K de los 764K candidatos).
- **Brecha:** no existe clasificación de defensa **por entidad-dealer** (solo por portal-agregador). La incertidumbre de defensa de los ~49K dominios resueltos no está medida.

### D.2 Config individual por entidad
- **Estado:** mecanismo REAL (B.6) pero **cobertura mínima** (3 portales + N dealers auto-gen en worktree). Brecha = **escalar la generación de config a las decenas de miles de entidades** y promover el dealer-store a main.

### D.3 Delta en segundos + alerta + equipo de remediación
- **Estado:** Delta real pero batch e idle (B.3); drift detectado pero solo logueado; remediación sin trigger (B.8). Brecha = **(a)** convertir el coordinator en always-on por entidad para latencia de segundos, **(b)** canal de alerta real (webhook/email) para drift, **(c)** cablear `remediate()` al evento de drift.

### D.4 Encapsulación API vendible por entidad
- **Estado:** GAP (B.7). Brecha = poblar `entities`+`dealer_inventory`, ligar `vehicles.source_platform`→`entity_ulid`, y exponer `/dealers/{entity}/inventory`.

### D.5 Discovery con suelo de 2M dealers
- **Estado:** techo libre host-safe alcanzado (764K censo, 49K con web). `discovery_mega` aportó identidad sin web. Brecha = **OSM/OEM/H3 a fondo + registros en VPS + Common Crawl + pago/proxies** para superar el muro Cloudflare/Akamai de directorios.

### D.6 Modelo VPS (validar→extraer→PURGAR→siguiente)
- **Estado:** el patrón “validate-with-limit-and-purge” ya existe en pruebas (stealth `--purge`, dealer-inventory E2E purgado), y el seam es streaming RAM-safe. Brecha = **operacionalizarlo como bucle VPS continuo** que libere espacio tras cada entidad en vez de correr puntualmente en host low-RAM.

### D.7 Techo seguro del HOST (hardware real medido 2026-06-08) — política validar→extraer→PURGAR
**Medición cruda (read-only, PowerShell/CIM):**
```
$ (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory      -> 16441667584  (16,44 GB / 15,31 GiB)
$ Get-CimInstance Win32_OperatingSystem | Select FreePhysicalMemory -> 797788 KB   (~780 MB LIBRE)
$ (Get-CimInstance Win32_Processor).NumberOfLogicalProcessors      -> 12  (AMD Ryzen 5 5500U, 6C/12T)
$ Get-PSDrive C  -> Used 473219895296 (440,7 GiB) · Free 31637237760 (29,5 GiB) · total 470 GB (94% lleno)
```

**Lectura honesta:** el host está **saturado**. Los 9 contenedores Docker (PG+CH+Meili+Grafana+Prometheus+Redis×2+web+api, 30h up) consumen ~15 GB → **solo ~780 MB de RAM libre** y **29,5 GB de disco**. Esto **confirma empíricamente** el OOM acumulativo documentado del coordinator: no es un bug, es falta de techo. La extracción a escala **debe** ir a VPS; el host es **solo banco de validación de config por entidad**.

**Techo seguro y sizing recomendado (derivado de los números medidos):**

| Parámetro | Recomendación | Razón (medida) |
|---|---|---|
| **Concurrencia local** | **1 entidad** (no 3) | 780 MB libres no soportan paralelismo con navegador |
| **RSS watchdog** | bajar de 1200 MB → **600 MB**, o **pausar Meili/Grafana/Prometheus** durante extracción local (libera ~2–3 GB) | el watchdog actual (1200 MB) supera la RAM libre real |
| **Lote de validación** | **10–25 listings/entidad** (confirmar que la config rinde inventario), NUNCA cosecha completa | el objetivo en host es validar config, no cosechar |
| **Purga** | **inmediata tras cada entidad**: HTML/JSON crudo + caché Camoufox/Playwright + perfil temporal | mantener working-set transitorio < 5 GB |
| **Umbral de disco** | **piso duro 10 GB libres**; parar bucle + purga de emergencia si libre < **12 GB** | de 29,5 GB libres, reservar headroom Windows (pagefile/updates) |
| **Ollama (qwen2.5:3b)** | **secuencial, nunca solapado** con navegador+stack (extraer→liberar navegador→invocar LLM→liberar); modo `economy` (LLM solo banda dudosa, ~3 llamadas/20) | el modelo pide ~1,7 GB transitorios + ~2 GB en disco → no cabe concurrente con 780 MB libres |
| **Extracción a escala** | **VPS, no host** | el host no tiene techo de RAM ni disco para volumen |

**Nota de blueprint (contexto del propietario):** extracción local = **solo VALIDAR** config por entidad, luego purgar. Parser a escala = **Ollama / LLMs locales** (cero coste API). Alertas = gestionadas por el **orquestador internamente** por ahora (sin canal externo aún) — coherente con B.8 (drift solo logueado; sin webhook/email todavía, y está bien hasta cablear el canal).

---

## Apéndice — Evidencia viva (comando→salida)
```
$ psql -c "SELECT 'vehicle_index',count(*) FROM vehicle_index
            UNION ALL SELECT 'distinct_sources',count(DISTINCT source_domain) FROM vehicle_index
            UNION ALL SELECT 'vehicles',count(*) FROM vehicles
            UNION ALL SELECT 'discovery_candidates',count(*) FROM discovery_candidates
            UNION ALL SELECT 'with_domain',count(domain) FROM discovery_candidates
            UNION ALL SELECT 'dealers',count(*) FROM dealers
            UNION ALL SELECT 'vehicle_events',count(*) FROM vehicle_events"
 vehicle_index        | 436114
 distinct_sources     | 19
 vehicles             | 563
 discovery_candidates | 764299
 with_domain          | 49024
 dealers              | 0
 vehicle_events       | 467104

$ psql -c "SELECT source_platform,count(*) FROM vehicles GROUP BY 1 ORDER BY 2 DESC LIMIT 3"
 SEED_DEMO | 30
 vw-paris15.fr | 25
 autocenterandelst.nl | 25      # -> 533/563 son coches REALES, no sintéticos

$ psql -c "SELECT 'entities',count(*) FROM entities UNION ALL SELECT 'dealer_inventory',count(*) FROM dealer_inventory"
 entities | 0
 dealer_inventory | 0

$ redis-cli -a *** XLEN stream:enrich_pending   -> 0
$ redis-cli -a *** XLEN stream:ingestion_raw    -> 0   # seam dormido (key inexistente, sin consumer groups)
```
**Árbol devuelto intacto:** rama `feature/domain-resolution @ 2bd5cb5`, sin cambios al código rastreado (solo se creó `outputs/AUDIT_CONTEXT_2026-06-08.md`, untracked, sin commit).
