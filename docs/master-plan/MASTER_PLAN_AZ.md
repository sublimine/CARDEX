# CARDEX — MASTER PLAN A→Z (Documento Maestro Institucional)

> **Estado de verdad.** Este plan se basa en lectura REAL del repo
> `C:\Users\elias\projects\cardex-integration` (verificado 2026-06-09) y en la integración de
> los 7 diseños de subsistema. Cada afirmación sobre el código es **[VERIFICADO]** (leído en
> fuente) o **[ASUMIDO]** (marcado explícitamente). CARDEX **no es greenfield**: el ~70% del
> esqueleto existe y está parcialmente probado E2E. Este plan **no reescribe lo que funciona:
> lo gobierna, lo cierra y lo proyecta** a cobertura 100% pan-europea.
>
> **Discrepancia verificada a corregir (gana el código):** STATUS.md declara `llama.cpp :8081
> (Qwen2.5-Coder-7B)`; el código vivo (`scrapers/llm/ollama_client.py`) usa
> `Ollama 127.0.0.1:11434 / qwen2.5:3b`, env-overridable por `OLLAMA_URL`/`OLLAMA_MODEL`. Se
> unifica tras esa interfaz y se actualiza STATUS.md.

---

## 1. Visión y estado-final — definición de "TERMINADO"

**Misión.** CARDEX es el índice de inventario de coches usados **pan-europeo** con cobertura
**100%** — "hasta el dealer perdido en la montaña" — de los 6 países **ES, FR, BE, NL, DE, CH**.
De TODA entidad con web + inventario de vehículos (concesionarios, compraventas, garajes,
desguaces/chatarreros y plataformas Tier-1), el ciclo de vida completo:

```
descubrir → resolver web → extraer 100% inventario → enjaular en API per-entidad VIVA con DELTA
(altas/bajas/precio/foto/historial) → verificación adversarial multi-vía → alertas + resiliencia
```

**Fin último real:** acuerdos LEGALES con cada dealer/plataforma (XML/API directo a CARDEX). El
scraping es el **puente** hasta tener ese poder. Producto: ayuda al mercado real + máquina de
dinero.

**"100%" no es fe, es un veredicto medible.** Operativamente, por slice `(país, provincia,
actividad/tier)`:

| Veredicto | Condición | Acción |
|---|---|---|
| **COMPLETE** | `observado/estimado ≥ 0.99` por las **3 vías** de completitud (re-derivación de registro + captura-recaptura Chapman + censo flota), con cero gaps en la re-derivación | cerrar slice, sellar |
| **NEAR** | `0.95 ≤ ratio < 0.99` | seguir cosechando, prioridad media |
| **GAP** | `< 0.95` | dispara protocolo de agotamiento de vías + agente Investigador |

**Definición dura de "terminado"** (la puerta de finalización del fundador):

1. **Descubrimiento:** cada slice `(país, provincia, actividad)` con veredicto COMPLETE/NEAR/GAP
   emitido; FR alcanza COMPLETE en ≥90% de departamentos 45.11Z; DE/BE con plan documentado
   mientras su fuente censal esté `BLOCKED`/`NEEDS_CREDENTIAL` (verdict `PROVISIONAL`, nunca
   COMPLETE sobre denominador proxy).
2. **Identidad institucional:** 100% de entidades físicas tienen **un** `cdx_code` legible y
   **un** `entity_id`, ubicadas en `país→provincia→ciudad`; cero duplicados; cero `legacy_id`
   huérfano en el crosswalk.
3. **Extracción:** toda entidad con inventario alcanza **≥98%** del conteo declarado (umbral
   AS24), verificado por vía independiente; el conteo NO se publica sin
   `CountVerdict.trustworthy=true`.
4. **API viva:** cada entidad expone `/v1/entities/{ulid}/{inventory,delta,snapshots,freshness}`
   con feed unificado (SEEN/GONE/PRICE/PHOTO/MILEAGE), auth+scope per-tenant, frescura con SLA
   por tier.
5. **Verificación adversarial:** ningún dato (número o contenido) se confía sin **quórum ≥2 vías
   ortogonales convergentes**; el gate de publicación bloquea lo no corroborado.
6. **Resiliencia:** un dealer caído NO tumba CARDEX (aislamiento por mensaje + circuit-breaker +
   FK `ON DELETE SET NULL`); todo es reanudable tras crash (ledgers append-only).
7. **Portabilidad:** cada entidad tiene receta JSON git-trackeada con bloque `provenance`
   reproducible por Codex u otra herramienta sin leer el código.
8. **Cero regresiones:** la suite verde existente (1.439 tests [VERIFICADO en uno de los specs])
   se mantiene; cada módulo nuevo con tests ≥80%.

---

## 2. Arquitectura de sistema-de-sistemas

CARDEX es **siete subsistemas** gobernados por **una capa de mando delgada**. Principio rector
transversal: **fuentes/workers pasivos, sink idempotente, gobierno declarativo, verificación
co-igual.** Todo estado de orquestación vive en **PostgreSQL** (write-ahead, append-only); Redis
**solo** como transporte de Streams (restricción dura del repo: "Redis: solo Streams. Estado de
inventario en Redis prohibido"). El estado del **engine** de scraping vive en **SQLite** `engine.db`
(no migrar a PG: la testabilidad in-memory del coordinator depende de ello).

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  CAPA DE MANDO  (scrapers/orchestration/)  — sistema-de-sistemas                    │
│  TOP-orquestador (Claude/Elias) → supervisa por EXCEPCIÓN vía wf_dashboard          │
│  JEFES por workflow (Opus) ─ workers (Sonnet/Haiku/Ollama) ─ VERIFICADOR co-igual   │
│  ledgers PG: wf_run · wf_phase · wf_ledger · wf_verdict   (crash-safe, resumible)    │
└───────────────┬──────────────────────────────────────────────────────────────────┘
                │ orquesta los 7 subsistemas
   ┌────────────┼──────────────┬───────────────┬───────────────┬───────────────┐
   ▼            ▼              ▼               ▼               ▼               ▼
┌────────┐ ┌──────────┐ ┌────────────┐ ┌──────────────┐ ┌───────────┐ ┌──────────────┐
│ S1     │ │ S2       │ │ S3         │ │ S4           │ │ S5        │ │ S6 / S7      │
│DISCOVERY│→│ANTI-DETECT│→│EXTRACCIÓN  │→│VERIF. ADVERS.│→│API VIVA + │ │MODELO DATOS  │
│ 100%   │ │ TIER-1   │ │+RECETAS    │ │MULTI-VÍA(VAM)│ │DELTA+LEGAL│ │CANÓNICO +    │
│        │ │(Camoufox)│ │+TIERS 2-EJE│ │              │ │           │ │ORQUESTACIÓN  │
└───┬────┘ └────┬─────┘ └─────┬──────┘ └──────┬───────┘ └─────┬─────┘ └──────┬───────┘
    │           │             │               │               │              │
    ▼           ▼             ▼               ▼               ▼              ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│  STORES REALES [VERIFICADO]                                                          │
│  PostgreSQL 16 (asyncpg) — source of truth: discovery_candidates(~112k), dealers,    │
│    source_entities, vehicle_index(~436k), vehicles, vehicle_events(part. mensual),   │
│    entity_matches, source_overlap_matrix*, coverage_matrix*, fleet_census*,          │
│    operator_alerts, portal_cadence, coverage_ledger    (* = DEFINIDAS, sin worker)   │
│  Redis Streams — transporte: stream:harvest_batches, :operator_events, :dlq, ...     │
│  SQLite engine.db — estado del engine: identities, proxy_health, domain_tier_state,  │
│    work_queue, dlq, schema_registry, warming_schedule, proxy_affinity                │
│  configs/{portals,dealers,families,verify,geo}/*.json — recetas PORTABLES git-tracked│
│  LLM local Ollama :11434 qwen2.5:3b (+ nomic-embed) — clasificación/dedup/redacción  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Cómo encajan los 7 (flujo de una entidad de punta a punta):**
`Discovery (S1)` la encuentra y le resuelve dominio → `Modelo canónico (S7)` le asigna
`cdx_code`, geo `país→provincia→ciudad` y tier → `Anti-detección (S2)` clasifica su defensa y
elige el tier de ataque más barato → `Extracción (S3)` resuelve/genera receta (familia-CMS si
aplica), cosecha el 100%, enjaula en `vehicle_index/vehicles` bajo `source_entities` → `VAM (S4)`
corrobora número y contenido por vías ortogonales y emite veredicto → `API viva (S5)` la expone
con delta, frescura y auth; cuando hay acuerdo legal, **flip de canal** a `legal_xml/legal_api`
reusando todo el backbone → `Orquestación (S6)` gobierna el ciclo, los gates y el coste.

---

## 3. FASES A→Z con GATES de calidad/verificación

Cada fase **se cierra solo cuando su GATE pasa**, verificado por el agente VERIFICADOR co-igual.
Las fases F1–F3 son **fundacionales y serializadas** (tocan estado global/migraciones); F4–F8 se
**paralelizan por país** una vez clavado el patrón en un país-piloto (FR). Regla del repo:
paralelizar solo lo aislado en datos (`country=XX`), serializar lo que toca estado compartido.

### FASE A (F0) — Cimientos de gobierno y verdad
**Entrega:** capa de mando mínima + reconciliación de discrepancias + ledgers.
- Migraciones aditivas reversibles: `wf_run/wf_phase/wf_ledger/wf_verdict` (orquestación),
  `verification_verdicts` (VAM), run-ledger de discovery (`discovery_runs/discovery_source_runs`).
- Unificar endpoint LLM tras `OLLAMA_URL/OLLAMA_MODEL`; corregir STATUS.md (gana el código).
- Cablear el discovery orchestrator en `master_scheduler.py` (cierra brecha real: el docstring
  promete "discovery orchestrator every 24h" pero NO está en `JOBS` [VERIFICADO]).
**GATE A:** `master_scheduler` arranca el sweep sin caerse si una fuente falla; toda migración
tiene `.down.sql` probado (rollback limpio); ledgers escriben write-ahead. Cero regresión en
suite verde.

### FASE B (F1) — Columna vertebral institucional (Modelo canónico S7)
**Entrega:** jerarquía `geo_country/geo_region/geo_city` (NUTS 2021 + LAU, sembrada de DUMPS
gratis), tabla `entity` con `cdx_code` inmutable, `entity_xref` (crosswalk a las 4 identidades
legacy sin romper FKs), taxonomía de tiers unificada (`entity_tier`), `coverage_ledger_v2`
agregable + `coverage_rollup`.
- Migraciones `0006..0012` con `NOT VALID + VALIDATE` en ventana (patrón exacto de la `0001`
  ya en repo, para no bloquear las ~436k filas).
- Backfill `entity` desde `discovery_candidates`/`dealers`/`source_entities`/`coverage_ledger`
  reusando `entity_matches` (Fellegi-Sunter) + match exacto domain/registry_id.
**GATE B:** geo cuadra con totales oficiales (±0.5%); 100% entidades con UN `entity_id` y UN
`cdx_code`, cero duplicados, cero huérfanos; las 18 tablas comerciales que cuelgan de `entities`
intactas. Verificado por vía independiente (suma de communes por departamento == total nacional).

### FASE C (F2) — Taxonomía de tiers de dos ejes + clasificación
**Entrega:** separar los ejes hoy colapsados — `defense_tier` (D0–D3, anti-bot) × `entity_tier`
(naturaleza/multiplicador) + descriptor `cms`. Backfill no destructivo `T1/T2/T3 → D0–D3`.
- Extender `dealer_classifier._assign_tier` y `router/classifier.classify_signals`.
- `cms_fingerprint.py` puro (izmocars/dealer.com/dealerk/WordPress/Next/modix...).
**GATE C:** `source_entities.{nature,cms,defense_tier D0-D3}` poblados para el 100% de entidades
con `inventory_tier` ya probado; distribución plausible (desguaces no superan compraventas; OEM
coinciden con `brand_affiliation`). Backfill T→D sin pérdida (test de carga).

### FASE D (F3) — Anti-detección Tier-1 cerrada (S2)
**Entrega:** Solver Abstraction Layer, `free_pool`, máquina de estados Breach Response, cierre de
los degraded-mode honestos (`tcp.py` httpcloak, `sensor.py` hyper-sdk-go), catálogo de
herramientas open-source con estado 2026 verificado.
**GATE D:** mobile.de rinde ≥99% del catálogo SIN proxy de pago (regresión del verificado);
`tcp.is_available()` y `sensor.hyper_sdk_path()` True en producción; tests coherencia
OS↔UA↔TCP↔TLS pasan; todo portal que falla E0–E2 produce fila terminal en `breach_attempts`
(SOLVED/BLOCKED_BY_PAID/OPEN_RESEARCH); **cero** "imposible".

### FASE E (F4) — Discovery gobernado, país-piloto FR (S1)
**Entrega:** `source_matrix.yaml` declarativa (fuente×país, rank+fallbacks), orquestador-líder
con run-ledger, dedup canónico 3 capas (exacta → blocking H3+trigram → Fellegi-Sunter con LLM
local), motor de completitud 3-vías, recetas de fuente versionadas.
**GATE E (FR):** `source_matrix.yaml` valida; el sweep escribe `discovery_source_runs` por
`(source,country,rank)`; `dealers` poblado con `cdx_code` y `discovery_sources`; duplicados <1%
(muestreo 200 filas); FR COMPLETE (ratio≥0.99) en ≥90% de departamentos 45.11Z. Todo GAP con
`gap_sample` concreto.

### FASE F (F5) — Extracción + multiplicador CMS, país-piloto FR (S3)
**Entrega:** resolución de receta cache-first con tercer store `configs/families/<cms>.json`,
conectores de feed DMS por proveedor, completitud por faceteo+sort-estable elevada a contrato,
`playwright_xhr` cableado.
**GATE F (FR):** ≥1 receta de familia rinde en ≥10 dealers del cluster sin detección por-dealer,
conteo corroborado en cada uno; ≥1 conector DMS verificado contra HTML; cualquier entidad con cap
alcanza ≥98%; el 19% `details_no_fields` baja medido en muestreo de 100 dealers SPA.

### FASE G (F6) — Verificación adversarial como gate (VAM, S4)
**Entrega:** `verdict.py` (quórum engine), despertar `source_overlap_matrix` (E2) y
`coverage_matrix` (E5) con workers, `registry_audit` (E1 generalizado a 6 países),
`live_sample` (E3), `dedup_audit` (E4), `publish_gate` (E5/WF-5).
**GATE G:** ningún `verdict='TRUSTWORTHY'` con `quorum_reached < quorum_required` o métodos
no-ortogonales; `publish_gate` bloquea el 100% de targets sin veredicto TRUSTWORTHY vigente
(test E2E: un DISPUTED no aparece en Meili/API); el verifier reabre ≥1 entidad marcada "ok" con
evidencia de divergencia (prueba de que desconfía de verdad). Replica la captura de la mentira
dacia 17-vs-229.

### FASE H (F7) — API viva + delta + frescura + ingestión legal (S5)
**Entrega:** feed unificado en `vehicle_events` (extender `event_type` a
PRICE/PHOTO/MILEAGE_CHANGE, columna `detail` JSONB), cierre del gap PHOTO_CHANGE (capturar
`photo_urls` previo en la CTE `prior`), `inventory_snapshot` (fingerprint/versionado),
`api_keys` (auth+scope+cuota), `freshness_sentinel`, `ingest_adapter` (flip de canal legal con
periodo dual + `trust_score`).
**GATE H:** delta <2s (SEEN) / <1s (GONE) bajo carga; PHOTO_CHANGE emitido; key con
`scope.entities=[X]` recibe 403 al pedir `Y`; toda entidad activa con `next_due_at` y alerta
`dead` en <15min al superar el tope del tier; una entidad `channel='legal_api'` sirve idéntico por
la misma API con scraping desactivado.

### FASE Z (F8) — Abanico a los 6 países + sello de cobertura
**Entrega:** replicar E→H por país (DE/ES/BE/NL/CH), cada uno con su `census_authority`
(FR sirene, NL rdw, CH zefix; DE/BE con plan mientras BLOCKED), refresco continuo de
`coverage_rollup`.
**GATE Z (el sello del fundador):** los 6 países con veredicto por slice; cada país con ≥1
fuente censal activa o plan PROVISIONAL declarado; `coverage_rollup` muestra
`pct_extraction_closed` por `(país, provincia, tier)` + KPI de descubrimiento (Lincoln-Petersen);
cero GAP cerrado en silencio; recetas portables al 100% de `recipe_proven`.

---

## 4. Los 7 subsistemas

### S1 — DISCOVERY 100%
**Resumen.** Sobre el orchestrator fan-out real (~36 fuentes [VERIFICADO]) y las tablas
`discovery_candidates`(~112k)/`dealers`, añade **gobierno**: matriz declarativa, run-ledger,
dedup canónico, motor de completitud 3-vías. No reescribe el contrato fuente
`discover(country)→dict` ni el sink idempotente de doble upsert.
**Estrategias rankeadas:** S1 dumps gov por código de actividad (PRIMARIA censo) · S2 directorios
profesionales/asociaciones (PRIMARIA dominios) · S3 OSM/Overpass (SECUNDARIA geo) · S4 OEM
dealer-locators (SECUNDARIA long-tail) · S5 plataformas como directorio (SECUNDARIA) · S6
resolución dominio CT-logs/Common-Crawl/web-search (TERCIARIA) · S7 Maps de pago (FALLBACK última
milla, gated por GAP).
**Workflows/agentes:** `discovery-lead` (Opus, lee matriz, planifica, cierra) · `discovery-verifier`
(Sonnet, 3 vías ortogonales) · `discovery-researcher` (Sonnet/Opus, GitHub/Reddit/foros ante GAP)
· `discovery-auditor` (Haiku, puerta de cierre).
**Aceptación:** matriz valida y se ejecuta entera (no-BLOCKED); ledger con fila por
`(source,country,rank)`; `dealers` con `cdx_code` y `discovery_sources`; duplicados <1%;
veredicto por slice de los 6 países; cero GAP silencioso.

### S2 — ANTI-DETECCIÓN & TIER-1
**Resumen.** 17 módulos vivos en `scrapers/engine/` + coordinator + docs maestros. Cierra los
degraded-modes honestos, formaliza "NUNCA no se puede" como workflow ejecutable, añade Solver
Abstraction Layer y pool de proxies gratis. Frontera real verificada: Akamai (mobile.de) cae
GRATIS con Camoufox; DataDome/PerimeterX requieren residencial del país (reputación IP/ASN).
**Estrategias rankeadas:** E0 RE de API / curl_cffi (más barato) · E1 Camoufox nativo · E2
Camoufox+behavioral+residencial · E3 Breach Response · E4 spoofing de red (TCP+JA3). Orden
coste-ascendente FIJO; T1→T3 multiplica ~80x.
**Workflows/agentes:** Lead "Anti-Detect Commander" · WAF Recon · Identity Forge+Warming · Engage
Engine · Breach Response · Research Scout · Adversarial Verifier (co-igual).
**Aceptación:** mobile.de ≥99% sin pago; degraded-modes cerrados; `breach_attempts` con estado
terminal por portal fallido; gasto proxy ≤60% presupuesto; ratio T0/T1 vs T2/T3 ≥80/20.

### S3 — EXTRACCIÓN + RECETAS + TIERS (2 ejes)
**Resumen.** Bucle `detector→harvester→drift_gate→remediation` VERIFICADO E2E (dacia 230/230,
AS24 92.759 al 98,8%). Tres saltos: multiplicador CMS (recetas de familia, 1 receta = N dealers),
taxonomía de dos ejes, completitud+verificación como contrato.
**Estrategias rankeadas:** S0 resolución de receta cache-first · S1 estático multi-estrategia ·
S2 render E07 Camoufox · S3 conector de feed DMS (multiplicador long-tail) · S4 faceteo+sort
estable · S5 mobile-API · S6 behavioral+proxy residencial+solver (último recurso pagado).
**Workflows/agentes:** Prober · CMS-Fingerprinter · Family-Recipe-Author · DMS-Connector-Builder ·
Harvester · Completeness-Driver · Adversarial-Verifier (sesión separada) · Drift-Sentinel ·
Remediator · Research-Scout.
**Aceptación:** ≥1 receta de familia en ≥10 dealers; ≥1 conector DMS verificado; cap→≥98%; gate
de conteo replica dacia 17-vs-229; cero regresiones (suite verde).

### S4 — VERIFICACIÓN ADVERSARIAL MULTI-VÍA (VAM)
**Resumen.** Compone los átomos probados (count_verify, validate.confirms_dealer,
verify_discovery, revalidate, poison, drift_gate, decisions-LLM) en un sistema con contrato de
veredicto único append-only (`verification_verdicts`), ortogonalidad obligatoria y quórum.
Despierta `source_overlap_matrix` y `coverage_matrix` (DEFINIDAS sin worker [VERIFICADO]).
**Estrategias rankeadas:** E1 re-derivación desde fuente-de-verdad · E2 captura-recaptura
Chapman · E3 muestreo adversarial live (correctness+frescura+no-inventado) · E4 over/under-dedup ·
E5 censo flota · E6 quórum + agente retador.
**Workflows/agentes:** `verification-orchestrator` (Opus) · `verification-challenger` (Sonnet,
puede DEGRADAR un TRUSTWORTHY) · `research-scout` · `data-correctness-auditor` ·
`universe-estimator`.
**Aceptación:** cero TRUSTWORTHY sin quórum≥2 ortogonal; `publish_gate` bloquea no-corroborado;
E1 sobre DUMP (no API) con contraejemplos; E2 ≥3 pares por país; E3 muestra Wilson (error≤2%);
HALLUCINATED>1% → alerta CRÍTICA.

### S5 — API VIVA + DELTA + RESILIENCIA + ALERTAS + INGESTIÓN LEGAL
**Resumen.** API read-only sobre VIEW `entity_inventory` (sin copia), delta always-on
(`delta_worker`, SEEN ~1.9s/GONE ~0.3s probado), detección de cambio precio/mileage VERIFICADA.
Cierra: PHOTO_CHANGE (gap real), auth/versionado, snapshot/fingerprint, ingestión legal como flip
de canal.
**Estrategias rankeadas:** S1 delta event-driven always-on (PRIMARIA) · S2 snapshot+fingerprint
diff (FALLBACK) · S3 ingestión legal XML/API (FUTURO, convive) · S4 agotar-todas-las-vías.
**Workflows/agentes:** delta-applier · rich-persister · remediator · circuit-guardian · scheduler ·
freshness-sentinel · verifier (separado) · legal-feed-normalizer · líder Opus + verificador
co-igual + investigación.
**Aceptación:** delta <2s/<1s; feed unificado 4+ tipos; aislamiento (payload veneno → DLQ, resto
sigue); auth/scope 403; frescura con SLA; snapshot por ciclo; flip legal idéntico por la misma
API; toda migración con `.down.sql`.

### S6 — ORQUESTACIÓN, AGENTES Y COSTE
**Resumen.** Capa de mando delgada (`scrapers/orchestration/`) sobre coordinator/scheduler_pg/
discovery-orchestrator/capa-LLM/lazo-remediación ya vivos. Promueve `master_scheduler` a
TOP-orquestador con health rollup; formaliza el VERIFICADOR como worker de primera clase;
fija routing de coste.
**Estrategias rankeadas:** S1 capa de mando PG-nativa (PRIMARIA) · S2 Redis Streams con
consumer-groups (FALLBACK >10k microtareas) · S3 escalera de vías como máquina de estados del
verdict · S4 routing de coste por capacidad cognitiva · S5 plantillas de prompt versionadas.
**Workflows/agentes:** TOP (Claude/Elias, supervisión por excepción vía `wf_dashboard`) · JEFES
por workflow (Opus) · workers (Sonnet/Haiku/Ollama) · VERIFICADOR/MOTIVADOR co-igual por workflow.
**Aceptación:** TOP no es cuello de botella (solo ve escalaciones/jefes muertos); ledger
write-ahead reanudable; ningún worker invoca Claude directo (solo escala evento); escalera de
vías sin éxito → `blocked_researched` documentado (nunca "no se puede" silencioso).

### S7 — MODELO DE DATOS CANÓNICO + ESTRUCTURA INSTITUCIONAL
**Resumen.** Capa canónica que APUNTA a lo existente vía `entity_xref` (cero DROP de tablas
vivas). `entity` = fuente de verdad de identidad+geo+tier; `cdx_code` legible e inmutable;
jerarquía NUTS+LAU sembrada de dumps; coverage agregable por provincia con 2 KPIs honestos.
**Estrategias rankeadas:** E1 capa canónica sobre PG existente · E2 resolución geo multi-señal
con cascada de fallbacks · E3 CDX-code determinístico · E4 recetas portables (reutilizar+extender)
· E5 cobertura agregable (ledger v2) · E6 agente de investigación ante muro.
**Workflows/agentes:** geo-seeder · geo-seed-auditor · entity-orchestrator · xref-matcher ·
geo-resolver · poly-indexer · tier-classifier · cdx-assigner · recipe-indexer ·
coverage-aggregator · institutional-lead + adversarial-verifier.
**Aceptación:** geo completa (±0.5%); identidad única; ≥90% geo con confidence≥0.6 (resto a
`needs_geo_review`, nunca silencioso); cdx_code UNIQUE+inmutable; rollup con 2 KPIs; recetas con
`content_sha256` == hash del archivo; muestra estratificada verificada por vía independiente
(discrepancia <2%).

---

## 5. Jerarquía de orquestación y reporting

```
                    ┌───────────────────────────────────────────────┐
                    │ TOP-ORQUESTADOR  (Claude/Elias, Opus)          │
                    │ supervisa por EXCEPCIÓN · único wf_dashboard    │
                    │ decide irreversibles · arbitra escalaciones     │
                    └───────────────┬───────────────────────────────┘
            ┌───────────────────────┼───────────────────────────────────┐
            ▼                       ▼                                     ▼
   ┌────────────────┐     ┌────────────────┐  ...  (un JEFE por workflow / subsistema)
   │ JEFE workflow  │     │ JEFE workflow  │       discovery-lead, anti-detect-commander,
   │ (Opus)         │     │ (Opus)         │       extract-lead, verification-orchestrator,
   │ planifica·cierra│    │ planifica·cierra│      api-lead, institutional-lead
   └───┬────────┬───┘     └───┬────────┬───┘
       ▼        ▼             ▼        ▼
  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌──────────────────────────────┐
  │ WORKERS │ │VERIFICADOR│ │ WORKERS │ │ VERIFICADOR/MOTIVADOR co-igual │
  │(Sonnet/ │ │/MOTIVADOR │ │         │ │ - NO subordinado al jefe        │
  │Haiku/   │ │ co-igual  │ │         │ │ - desconfía de cada entregable  │
  │Ollama)  │ │           │ │         │ │ - puede DEGRADAR un "verde"     │
  └─────────┘ └──────────┘ └─────────┘ │ - dispara research ante muro     │
                                        └──────────────────────────────────┘
```

**Reglas de mando:**
- **El TOP supervisa por excepción**, nunca por polling de workers — así escala sin volverse
  cuello de botella. Ve un único `wf_dashboard` materializado: solo lo que rompió o lo que un
  jefe escaló.
- **El VERIFICADOR es co-igual, no subordinado.** Ni el jefe ni el verificador deciden solos: el
  **quórum** decide. El verificador puede degradar un TRUSTWORTHY a DISPUTED si halla fallo de
  método.
- **Ningún worker invoca a Claude directamente.** Solo escala un evento (`stream:operator_events`)
  que el TOP arbitra. El routing de coste lo fija el jefe.
- **Estado en disco, no en contexto volátil.** Cada jefe mantiene `wf_run/wf_phase/wf_ledger`
  (write-ahead: registrar la intención ANTES de actuar). Al arrancar, el jefe reconcilia filas
  `started` sin `finished` más viejas que un TTL → re-encola (igual que `_safe_process_item`
  rescata jobs colgados).
- **Reporting:** workers → ledger PG + métricas Prometheus; jefes → rollup de salud al
  `wf_dashboard`; alertas operador (3 sinks: `stream:operator_events` + `operator_alerts` PG +
  JSONL); el notifier Go SSRF-hardened como canal externo para alertas críticas.

---

## 6. Doctrina de verificación adversarial multi-vía (transversal)

**Principio:** *CARDEX no vende mentiras.* Ningún número ni contenido se confía por la primera
respuesta de ningún agente o workflow. Esta doctrina es **co-igual** en TODOS los subsistemas, no
un paso final opcional.

1. **Ortogonalidad obligatoria.** Un verificador solo cuenta si **no comparte el camino de fallo**
   con la extracción que valida. Matriz: extracción por API → verificar por DUMP; por paginación
   → por sitemap PDP y JSON-LD; por web-search → por registro gov + OSM; por fingerprint de texto
   → por phash de foto; por fetcher/identidad X → muestreo por fetcher/identidad Y. Dos métodos
   del mismo camino **NO son quórum**.
2. **Quórum ≥2 vías ortogonales convergentes** como condición ÚNICA de TRUSTWORTHY. Sin quórum →
   DISPUTED → BLOQUEO en `publish_gate`.
3. **Números Y contenido.** No basta el conteo: muestreo live re-fetch por identidad distinta +
   `poison.detect` (no validar contra honeypot) + correctness (precio/año/km plausibles) +
   frescura (`last_seen`) + completitud (required_fields ratio).
4. **Contenido domina sobre conteo.** HALLUCINATED/POISONED/STALE vencen a cualquier número
   convergente.
5. **Trazabilidad append-only.** `verification_verdicts` + `audit_log`: una re-verificación
   inserta fila nueva; gana la evidencia más reciente (como `revalidate` purga FPs sin destruir en
   fallo transitorio).
6. **El "no se puede" está prohibido.** Todo DISPUTED/GAP dispara el retador → escalera de vías →
   research-scout (GitHub/Reddit/foros/OSS). Solo se cierra con quórum o **BLOQUEO declarado con
   la lista de vías agotadas**.
7. **El verificador NO comparte fetcher/discovery con el productor** (desconfianza estructural;
   sesión/proceso separado).

---

## 7. Coste (LLM local vs Claude) y arsenal open-source

**Routing de capacidad cognitiva al problema (no por coste, por idoneidad):**

| Capa | Motor | Para qué |
|---|---|---|
| **Determinista primero** | heurística/reglas/dumps | clasificación de actividad, conteos, re-derivación, faceteo — coste 0 |
| **LLM LOCAL** | Ollama `:11434 qwen2.5:3b` (+ nomic-embed) [VERIFICADO] | normalización de nombres, clasificación entity_tier, desempate de matches dudosos C3, redacción de veredictos, segunda opinión en banda ambigua (fail-open). Coste 0/token |
| **Claude Opus** | — | SOLO arquitectura, decisiones irreversibles (desactivar scraping de una entidad, confiar feed legal, flip de canal) y el research-scout de muros |
| **Claude Sonnet/Haiku** | — | jefes de workflow / workers de orquestación cuando la decisión excede al LLM local |

**Regla dura:** ningún worker invoca Claude directamente; el LLM local es siempre **fail-open** a
heurística determinista y **nunca es la única vía** de un veredicto de aceptación (las decisiones
aceptar/rechazar las cierra una regla determinista sobre números).

**Coste de extracción — orden estricto gratis→pago:** GOV_DUMP/GOV_API/OSM/WEB_INDEX/ASSOC
(coste 0) → curl_cffi (impersonate chrome) → Camoufox (si `block_rate>0.3`) → free_pool
(datacenter/Tor, solo sin reputación-IP) → ScrapeOps residential free (100MB) → residencial/móvil
de pago del país (frontera de pago, gated por GAP del motor de completitud, presupuesto acotado).
**Proxies de pago JAMÁS para verificar** salvo justificación declarada. Gasto proxy ≤60% del
presupuesto.

**Arsenal open-source clave (verificar vivacidad 2026 con research-scout antes de adoptar):**
`curl_cffi` (JA3/JA4 impersonation, instalado) · `Camoufox[geoip]` (Firefox parcheado C++,
instalado; riesgo: mantenedor en hiato → pinnear build known-good, fork @coryking como respaldo) ·
`capsolver` (de pago, tras el Solver Layer) · candidatas a evaluar: `nodriver`, `patchright`,
`botasaurus`, `hrequests`, `tls-client`, `FlareSolverr`, solvers OSS DataDome/PerimeterX ·
`mitmproxy+frida` (RE de API móvil = bypass total del WAF web) · `splink`/`dedupe` (record
linkage) · `imagehash` (phash anti-over-dedup) · dumps gratis (Eurostat NUTS/LAU, SIRENE
opendatasoft, INSEE/INE/Destatis/CBS/Statbel/BFS).

---

## 8. Modelo de datos canónico + estructura del repo

**Identidad institucional.** Toda entidad física = UN `entity_id` (UUID técnico) + UN `cdx_code`
legible e inmutable: `CDX-{CC}-{REGcode}-{LETTER}{NNNN}` (ej. `CDX-FR-75-D0042`), asignado por
secuencia con advisory-lock por bucket `(país, región, tier_letter)`. La re-geolocalización NO
cambia el código (auditada en `entity_geo_history`).

**Jerarquía geográfica** (`país→provincia→ciudad`, NUTS 2021 + LAU, sembrada de DUMPS gratis):
`geo_country(6)` → `geo_region` (NUTS2/NUTS3: departamento/provincia/cantón/bundesland) →
`geo_city` (LAU: commune/municipio/Gemeinde/gemeente) con postcodes, h3_res7, trgm.

**Taxonomía de tiers (3 ejes ortogonales, hoy colapsados):**
- `defense_tier` D0–D3 (anti-bot: sin WAF / CF-free / Akamai-CF-challenge / DataDome-PerimeterX).
- `entity_tier`/`nature` (qué es y multiplicador): `T0_PLATFORM`/`E-PLATFORM`, `E-FAMILY`
  (1 receta = N dealers), `OEM_LOCATOR`, `DEALER_INDEP`, `GARAGE`, `SCRAPYARD`, `FLEET`,
  `INSTITUTION`, `E-DMS` (1 conector = N dealers).
- `cms` (descriptor que habilita el multiplicador).

**Cobertura agregable + 2 KPIs honestos:** `coverage_ledger_v2` (PK `entity_id`, con
región/tier) + `coverage_rollup` (vista materializada por `país×provincia×tier`):
- **Cobertura de extracción** = `pct_extraction_closed` (de lo conocido, cuánto está
  enjaulado+verificado).
- **Cobertura de descubrimiento** = conocidas / estimación Lincoln-Petersen (cruza
  `source_overlap_matrix`) → responde "¿conocemos TODOS los dealers de esta provincia?".

**Recetas persistidas y portables (git-tracked).** `configs/{portals,dealers,families,verify,geo}/`.
Cada receta lleva bloque `provenance` (qué estrategia/anti-bot/discovery/verificación se usaron) +
`verification` (primary, vías independientes, converged) → reproducible por Codex sin leer el
código. Índice PG espejo `entity_recipe` con `content_sha256` para detectar drift índice↔archivo.

**Estructura del repo (sobre lo existente):**
```
cardex-integration/
├── configs/{portals,dealers}/        (EXISTE: 16 portales + 246 dealers [VERIFICADO])
│   ├── families/<cms>.json           (NUEVO: recetas de familia, multiplicador CMS)
│   ├── verify/<key>.json             (NUEVO: recetas de verificación VAM)
│   └── geo/{seeds,shapefiles,postcode_lau}/   (NUEVO: dumps NUTS+LAU)
├── discovery/registry/source_matrix.yaml + matrix_schema.json   (NUEVO: matriz fuente×país)
├── discovery/recipes/<source>.json                              (NUEVO: recetas de fuente)
├── scrapers/
│   ├── discovery/sources/*           (EXISTE: 36 módulos) + faltantes de la matriz
│   ├── discovery/{consolidate,completeness/}.py                 (NUEVO: dedup + 3 vías)
│   ├── dealer_scraping/{cms_fingerprint,dms/}.py                (NUEVO: multiplicador)
│   ├── intelligence/{verdict,capture_recapture,dedup_audit,live_sample,registry_audit,coverage,publish_gate}.py  (NUEVO: VAM)
│   ├── orchestration/                (NUEVO: capa de mando)
│   ├── delta/{freshness_sentinel}.py · ingest/legal_feed_worker.py   (NUEVO: S5)
│   └── engine/                       (EXISTE: 17 módulos; cerrar tcp/sensor degraded-modes)
├── services/entity_api/{auth.py,openapi.yaml}                   (NUEVO: auth+scope)
└── scripts/migrations/0006..00XX.{up,down}.sql                  (NUEVO: todas reversibles)
```

---

## 9. Riesgos top + mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| 1 | **Backfill `entity` genera duplicados** (matching domain/registry/Fellegi-Sunter mal calibrado); un `cdx_code` mal asignado a un duplicado es difícil de revertir por inmutabilidad | Verificación adversarial ANTES de asignar `cdx_code`; umbral conservador (auto-merge ≥0.92, revisión 0.75–0.92, LLM local); muestreo manual 200 filas como AC |
| 2 | **DataDome/PerimeterX por reputación IP/ASN**: sin residencial del país no hay vía gratis (verificado); riesgo de presupuesto si muchos portales son T3/D3 | Priorizar RE de API móvil (bypass total) antes de pagar; MAPS/residencial gated por GAP del motor de completitud, presupuesto acotado por celda H3 |
| 3 | **Censo poblacional erróneo → veredicto de completitud falso** (denominador inflado/deflactado por códigos de actividad) | V2 captura-recaptura es independiente del censo y cruza-valida V3; reportar siempre IC |
| 4 | **Captura-recaptura asume independencia**; dos fuentes del mismo origen (SIRENE dump y su API) sesgan Chapman | Emparejar solo fuentes genuinamente ortogonales (SIRENE vs OSM vs OEM); el retador escala a 3ª fuente si el IC explota |
| 5 | **Falso positivo de CMS fingerprint**: una receta de familia mal asignada zeroa/corrompe N dealers (el multiplicador amplifica errores) | confidence ≥2 señales; verificar receta en ≥3 dealers antes de publicar; drift_gate captura el colapso |
| 6 | **GAP REAL: PHOTO_CHANGE no existe** (COALESCE de `photo_urls` descarta la señal) y **entity_api Python sin auth** (fuga entre tenants) | Capturar `photo_urls` previo en la CTE `prior` + emitir evento; tabla `api_keys` con scope per-entidad + 403 |
| 7 | **Fuentes BLOCKED (DE 502, BE credencial)** dejan 2 países sin census_authority → veredicto provisional sobre denominador proxy | Marcar `verdict='PROVISIONAL'` hasta desbloquear; nunca COMPLETE sobre proxy; research-scout busca dumps regionales |
| 8 | **RAM/OOM** del host (render E07 + faceteo masivo + snapshot de gigantes ~92k) | Patrón RAM-safe ya en `resolver.py`/`harvester` (keyset, GC, RSS watchdog, E07 conc 2, 1 browser/batch); snapshot por streaming/chunking; rate-limiters globales |
| 9 | **Drift de recetas/fuente-de-verdad**: HTML cambia (verdict EMPTY parece "no hay dealers"); dump gov desactualizado (E1 reporta GAP falsos) | `entity_recipe.content_sha256` vs hash; auditor marca recetas >30d; versionar fecha del dump en `evidence`; V2/V3 detectan caída de `observed` como anomalía |
| 10 | **Cuello de botella en el TOP** si supervisa cada worker; **livelock de remediación/reto** | Supervisión por excepción + `wf_dashboard`; anti-churn por ventana (`MAX_REMEDIATIONS=3/6h` ya presente) + estado terminal `blocked_researched` |
| 11 | **Camoufox depende de fork con mantenedor en hiato** | Pinnear build known-good; research-scout monitorea upstream mensual; nodriver/patchright como alternativa evaluada |
| 12 | **Migraciones sobre tablas grandes y vivas** (vehicle_index 436k) bloquean producción | `NOT VALID + VALIDATE` en ventana (patrón exacto de la `0001`); columnas nuevas NULLABLE; `.down.sql` simétrico probado; FK `ON DELETE SET NULL` preservada |

---

## 10. Métricas que ve el fundador

El fundador juzga el avance por **un único tablero** (`coverage_rollup` materializado), no por
logs de workers. Lo que ve:

1. **% de cobertura por país y provincia** — los 2 KPIs honestos, lado a lado, por
   `(país, provincia, tier)`:
   - **Cobertura de descubrimiento** = conocidas / estimación Lincoln-Petersen → "¿conocemos
     todos los dealers?" (con IC; un país "100% de lo conocido" pero N estimado >> conocido **no**
     está cerrado).
   - **Cobertura de extracción** = `pct_extraction_closed` → "¿de los que conocemos, cuántos
     tienen inventario enjaulado y VERIFICADO?".
2. **Veredicto por slice** COMPLETE/NEAR/GAP/PROVISIONAL por `(país, provincia, actividad)` — con
   `gap_sample` clicable (ejemplos concretos de lo que falta, no solo números).
3. **Inventario enjaulado total** (`caged_inventory`) y **frescura** (entidades con delta <SLA
   por tier; alertas `dead`).
4. **Salud del pipeline** por excepción: entidades `degraded/dead`, `breach_attempts` abiertos
   (`OPEN_RESEARCH`), recetas stale, slices en GAP sin plan.
5. **Confianza de los datos**: % de targets TRUSTWORTHY (pasaron el gate de publicación) vs
   DISPUTED/UNVERIFIED bloqueados.
6. **Coste**: gasto de proxy vs presupuesto (≤60%), ratio de requests gratis vs pago (≥80/20),
   tokens LLM (local vs Claude).

**Regla de honestidad:** ninguna métrica sube sin que el VERIFICADOR la haya corroborado por vía
independiente. Un "100% FR" en el tablero significa: 3 vías concuerdan, gaps materializados o
cerrados, recetas probadas y portables. Cero maquillaje.

---

### Cierre — autointerrogatorio del plan

- *¿Afirmé algo sin verificar?* Las claves (defense_tier T1/T2/T3, tablas estadísticas sin worker,
  brecha del scheduler, endpoints sin auth, Ollama :11434 vs STATUS.md :8081, 16+246 recetas,
  36 fuentes) están **[VERIFICADO]** por lectura directa.
- *¿Dejé huecos?* Cada fase tiene GATE medible; cada subsistema, criterios de aceptación; cada
  riesgo, mitigación concreta.
- *¿Causa o síntoma?* El plan ataca la causa común a los 7 diseños: **falta de gobierno**, no de
  componentes. Añade gobierno sin reescribir lo probado.
- *¿Es lo mejor o lo suficiente?* Es el documento maestro A→Z, denso, sin relleno, anclado al
  código real y a la doctrina del fundador.