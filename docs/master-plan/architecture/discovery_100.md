# DISCOVERY 100% — Descubrimiento exhaustivo de toda entidad con web+inventario de vehículos en ES/FR/BE/NL/DE/CH (concesionarios, compraventas, garajes, desguaces y plataformas), con orquestación multi-estrategia, dedup canónico, verificación adversarial de completitud y agente de investigación de nuevas vías.

## Resumen
CARDEX ya tiene un subsistema de discovery REAL y sustancial (~112k candidatos), no greenfield. [VERIFICADO leyendo el código]: existe `scrapers/discovery/orchestrator.py` (fan-out funcional de 8 fuentes + 6 standalone), ~40 módulos de fuentes en `scrapers/discovery/sources/`, una tabla intake canónica `discovery_candidates` (source_layer 1-5, dedup por domain/identity), una tabla consolidada `dealers` (multi-source merge + H3), `domain_resolution/` completo (search→rank→validate), `verify_discovery.py` (verificación adversarial PERO solo FR-SIRENE), y tablas listas-pero-sin-runner `source_overlap_matrix` (capture-recapture Lincoln-Petersen/Chapman) y `coverage_matrix` (censo de flota). El problema no es falta de fuentes: es falta de GOBIERNO. El orquestador actual (a) no cubre todas las fuentes existentes (faltan de_11880, fr_pagesjaunes, de_gelbeseiten, ch_agvs, osm_full, ct_logs solo en standalone), (b) no tiene matriz fuente×país declarativa con fallbacks, (c) no se ejecuta desde el `master_scheduler.py` (el docstring promete "discovery orchestrator every 24h" pero NO está en la lista JOBS — hueco declarado), (d) no persiste un run-ledger para trazabilidad/reanudación, (e) no tiene una taxonomía de tiers formal, (f) la verificación de completitud es ad-hoc y monofuente, (g) no existe el agente de investigación de vías nuevas, (h) el dedup es solo por clave exacta (domain/registry_id), sin resolución de entidad difusa (la tabla `entity_matches` Fellegi-Sunter existe pero sin pipeline). Mi diseño NO reescribe: formaliza. Propongo (1) una MATRIZ FUENTE×PAÍS declarativa (`discovery/registry/source_matrix.yaml`) que rankea por tier y declara fallbacks; (2) un ORQUESTADOR-LÍDER con run-ledger persistente (`discovery_runs`/`discovery_source_runs`) que ejecuta la matriz, respeta rate-limiters globales (lección SIRENE: dumps>APIs), y orquesta el ciclo descubrir→resolver→consolidar→verificar; (3) un pipeline de DEDUP CANÓNICO en 3 capas (clave exacta → blocking H3+trigram → Fellegi-Sunter scoring) que puebla `dealers` y `entity_matches`; (4) un MOTOR DE COMPLETITUD que mide "¿están TODOS?" por 3 vías independientes (re-derivación de fuente, capture-recapture entre fuentes, censo top-down flota×rotación) y emite un veredicto COMPLETE/NEAR/GAP por (país, provincia, actividad); (5) RECETAS de fuente versionadas y portables (`discovery/recipes/<source>.json`); (6) un trío de AGENTES — Líder Orquestador, Verificador Adversarial, Investigador de Vías (que busca en GitHub/Reddit/foros herramientas open-source como Camoufox cuando una vía cae) — más un agente Motivador/Auditor que impide cerrar con huecos silenciosos. Todo coste-eficiente (LLMs locales para clasificación/normalización, herramientas gratis/open-source, proxy de pago solo en muro real), grado institucional (trazable, resiliente, idempotente).

## Estrategias
- **S1 — Dumps de registros gov por código de actividad (PRIMARIA para censo masa)**: Descargar dumps descargables completos (no APIs con tope) y filtrar por código de actividad auto. FR: SIRENE StockEtablissement (data.gouv.fr, ~505k auto reachable sin tope — ya verificado) sustituye a recherche-entreprises.api.gouv.fr (cap 10k/query, 7req/s, bans). NL: RDW erkende bedrijven (Socrata, ya vivo en nl_rdw.py) + KvK. DE: Handelsregister/OffeneRegister dump SQLite 773MB procesado en VPS (no en sandbox). BE: KBO/BCE Open Data CSV (NACEBEL 45.x). ES: no hay dump CNAE libre fiable → S2/S4 cubren. CH: Zefix all-cantons mirror (companies_<KT>.csv, 26 cantones, ya en ch_zefix_allcantons.py). Códigos: FR NAF 45.11Z/45.19Z/45.20A/45.20B/45.31Z/45.32Z/45.40Z; ES CNAE 4511/4519/4520/4531/4532/4540; DE WZ 45.11/45.19/45.20/45.31/45.32/45.40; NACE equivalente BE/NL; NOGA CH 45.x.
- **S2 — Directorios profesionales y asociaciones (PRIMARIA para dominios + filtro de calidad)**: Cosechar directorios que YA exponen el sitio web del dealer (cierran name→domain sin resolver). Asociaciones: BOVAG/RDW (NL, ya en bovag.py/nl_bovag.py), AGVS/UPSA (CH, ch_agvs.py), FEBIAC/Traxio (BE), FACONAUTO/GANVAM (ES), ZDK/Mobilitätsverband (DE), CNPA (FR). Páginas amarillas: PagesJaunes (FR, fr_pagesjaunes.py), GelbeSeiten + 11880 (DE, de_gelbeseiten.py/de_11880.py), PaginasAmarillas (ES), GoudenGids (NL/BE), local.ch (CH). Cada uno = módulo `XxxSource.discover(country)` que yield dicts compatibles con discovery_candidates, source_layer=2(portal)/3(registry).
- **S3 — OSM/Overpass full por país (SECUNDARIA, cobertura geográfica)**: Barrido Overpass por boundary de país de TODOS los tags de comercio auto (osm.py ya lo hace: shop=car/car_dealer/second_hand+car/car_repair/car_parts/tyres/motorcycle/truck/caravan, craft=car_repair, office=car_dealer, amenity=car_rental). Ampliar osm_full.py a barrido por sub-área (admin_level=6 provincia) cuando el país entero excede timeout. Muchos nodos traen website directo. Endpoints con fallback (overpass-api.de→kumi→mail.ru) ya implementado.
- **S4 — OEM dealer-locators TODAS las marcas (SECUNDARIA, franquicia long-tail)**: Golpear los locators de cada marca (no solo 10). Ya existen oem_bmw.py (STOLO verificado), oem_locators.py (vw/audi/skoda/toyota/hyundai/kia — verificado 2026-06-09), oem_wave2.py (renault/dacia/seat), oem_brands_ext.py (cupra). Ampliar a marcas restantes: mercedes, ford, opel/vauxhall, peugeot/citroen/DS, fiat/jeep/alfa, nissan, mazda, honda, volvo, mini, porsche, tesla, suzuki, mitsubishi, ssangyong, smart, etc. Cada locator = endpoint JSON por país/código postal. Muchos no dan web propia → entran como identity y van a domain_resolution.
- **S5 — Plataformas/portales como directorio de dealers (SECUNDARIA, descubre vendedores pro)**: Las plataformas Tier-1 exponen el directorio de sus dealers. AS24 dealer-search API (as24_dealers.py, ~34.5k identities 5 países, verificado coste-cero) ya rinde. Añadir: mobile.de Händler-Suche, coches.net concesionarios, leboncoin pro, marktplaats/2dehands handelaars, autoscout24.ch. Esto descubre la entidad-dealer Y su perfil en la plataforma (útil para el cruce y para el futuro acuerdo legal: sabemos quién es y dónde publica).
- **S6 — Resolución dominio e identidad (CT logs + Common Crawl + web search) (TERCIARIA, cierra huecos)**: Para identidades sin web: (a) crt.sh Postgres directo por keyword+TLD (ct_logs.py, verificado), (b) Common Crawl URL index por keyword/TLD (common_crawl.py), (c) domain_resolution/ (search DDG→Mojeek→ranking→validación de homepage, resolver.py ya RAM-safe e idempotente). Para dominios sin identidad: head_classifier/dealer_classifier infieren país/CMS/inventario. Validación SIEMPRE: un dominio se persiste solo si la homepage prueba que es ESE dealer.
- **S7 — Mapas (Google/Bing Places) (FALLBACK de pago, última milla)**: Text Search + Nearby Search por celda H3 res7 sobre las zonas donde el motor de completitud detecta GAP (provincia/ciudad con censo > observado). Query 'car dealer'/'concesionario'/'Autohaus'/'garage automobile' por celda. Devuelve place_id (clave de dedup ya prevista en tabla dealers), nombre, web, rating. Sólo se dispara dirigido por el GAP, no a ciega.

## Spec completa
# CARDEX · Subsistema DISCOVERY 100% — Especificación de implementación

> Estado de verdad: este documento se basa en lectura REAL del repo en
> `C:\Users\elias\projects\cardex-integration` (2026-06-09). Cada afirmación sobre
> el código es [VERIFICADO] salvo marca explícita [ASUMIDO]. No reescribe lo que
> funciona: lo formaliza y cierra las brechas de gobierno.

---

## 0. Misión del subsistema y definición de "100%"

Encontrar **toda entidad con web + inventario de vehículos** en ES/FR/BE/NL/DE/CH:
concesionarios oficiales, compraventas independientes, garajes, desguaces/chatarreros
y plataformas/portales (Tier-1). Estructura institucional **país → provincia/región →
ciudad**, cada entidad con **código único**, clasificada por una **taxonomía de tiers**.

"100%" es inalcanzable como certeza absoluta, pero **sí es medible y demostrable**.
Se define operativamente como veredicto por slice `(país, provincia, actividad)`:

- **COMPLETE**: `observado / estimado ≥ 0.99` por las tres vías de completitud (§7) y
  cero gaps en la re-derivación de la fuente de censo.
- **NEAR**: `0.95 ≤ ratio < 0.99`.
- **GAP**: `< 0.95` → dispara protocolo de agotamiento de vías (§8) + agente Investigador.

El subsistema NO declara "completo" porque un harvester diga "escribí N". Eso es
mentira hasta que el **Verificador Adversarial** lo prueba por una vía independiente
(doctrina ya encarnada en `scripts/verify_discovery.py`, que aquí se generaliza).

---

## 1. Reconocimiento: qué existe HOY (construir sobre esto)

### 1.1 Componentes vivos [VERIFICADO]

| Componente | Archivo | Estado real |
|---|---|---|
| Orquestador fan-out | `scrapers/discovery/orchestrator.py` | Funcional. Fan-out de 8 sources (`_SOURCES`) + 6 standalone (`_STANDALONE_RUNNERS`). Sink idempotente con doble upsert (domain / identity). **Brecha: no cubre todas las fuentes existentes, sin matriz declarativa, sin run-ledger, sin scheduling.** |
| Tabla intake | `discovery_candidates` (en `scripts/init-pg.sql`) | Canónica. `source_layer` SMALLINT 1-5, dedup parcial-unique por `(domain,country)` y por `(source,registry_id,country)`. Estados sitemap/indexer/ddg. ~112k filas. |
| Tabla consolidada | `dealers` (en `scripts/init-pg.sql`) | Registro físico merge-de-fuentes, H3 res4/res7, `discovery_sources TEXT[]`, `place_id/registry_id/osm_id`, `is_whale`, `spider_status`. **Brecha: sin pipeline que la pueble desde candidates.** |
| Capture-recapture | `source_overlap_matrix` (tabla) | DDL completo (Lincoln-Petersen, Chapman, CI). **Brecha: sin runner que la calcule.** |
| Dedup difuso | `entity_matches` (tabla, Fellegi-Sunter) | DDL completo. **Brecha: sin pipeline de matching.** |
| Censo flota | `coverage_matrix` + `fleet_census` (tablas) | DDL completo (fleet × turnover × avg_dom / 365). **Brecha: sin loader de censo de entidades (solo de vehículos).** |
| Resolución dominio | `scrapers/discovery/domain_resolution/*` | Completo: `search.py` (DDG→Mojeek), `candidate.py` (ranking), `validate.py` (prueba homepage), `resolver.py` (RAM-safe, idempotente, keyset), `worker.py`, `directories.py`, `proxy_pool.py`, `fr_resolver.py`. |
| Verificación adversarial | `scripts/verify_discovery.py` | Real pero **solo FR-SIRENE**: re-deriva sirens de la fuente y mide completeness por dpto, con `--fill` para cerrar gap. Es el molde a generalizar. |
| Fuentes (~40 módulos) | `scrapers/discovery/sources/*` | OEM (bmw, locators, wave2, brands_ext), registros (fr_sirene, mass_registry, es_openmercantil, ch_zefix/_bs/_allcantons, de_offeneregister, be_kbo, nl_rdw), directorios (bovag, nl_bovag, ch_agvs, de_gelbeseiten, de_11880, fr_pagesjaunes), OSM (osm, osm_full, osm_expanded_run, osm_nametail), CT/CC (ct_logs, common_crawl), portales (as24_dealers, portal_aggregator, trustpilot). |
| Diccionario dialectos | `scrapers/discovery/dealer_terms.py` | `{country:{lang:[terms]}}`, token "auto" excluido (falsos positivos). |
| Scheduler | `scripts/master_scheduler.py` | Corre enrichers/resolver/backfill/audit. **Brecha: el docstring promete "discovery orchestrator every 24h" pero NO está en JOBS.** |
| Anti-detección | `scrapers/engine/antidetect/*`, `scrapers/engine/identity/*` | curl_cffi + Camoufox instalados, JA3/TLS/TCP, identidades, aging, coherence. |

### 1.2 Lecciones grabadas (no repetir el dolor)

- **Dumps > APIs de lookup** (FANOUT report + memoria): recherche-entreprises cap 10k/query
  y ~7 req/s con bans bajo IP penalizada → preferir SIRENE StockEtablissement dump.
- **Rate-limiter GLOBAL token-bucket desde el inicio** (mass_registry `_RateLimiter`): la
  concurrencia NO controla el rate; el bucket sí.
- **Token genérico mata precisión**: "auto" matcheaba "Automation"/"automatique" → excluido.
- **DE/BE bloqueados por la FUENTE** (502 / registro), no por incapacidad → documentar con
  plan y usar vías ortogonales (DE ya ~45k, BE ~4k de otras fuentes). Nunca inventar datos.

---

## 2. Arquitectura del subsistema

```
                         ┌────────────────────────────────────────────┐
                         │  AGENTE LÍDER ORQUESTADOR (discovery-lead)   │
                         │  lee source_matrix.yaml · planifica · cierra │
                         └───────────────┬──────────────────────────────┘
                                         │ dispara ciclo por país
        ┌────────────────────────────────┼─────────────────────────────────┐
        ▼                                ▼                                  ▼
┌───────────────┐              ┌──────────────────┐              ┌──────────────────┐
│ FASE DESCUBRIR │              │ FASE RESOLVER     │              │ FASE CONSOLIDAR   │
│ source runners │──candidates─▶│ domain_resolution │──resolved──▶ │ dedup canónico    │
│ (S1..S7)       │              │ + classifier      │              │ → dealers/matches │
└───────┬────────┘              └──────────────────┘              └─────────┬────────┘
        │ run-ledger                                                        │
        ▼                                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│              FASE VERIFICAR (motor de completitud, 3 vías independientes)            │
│  V1 re-derivación de fuente  ·  V2 capture-recapture  ·  V3 censo top-down           │
│              → veredicto COMPLETE/NEAR/GAP por (país, provincia, actividad)          │
└───────────────────────────────────┬──────────────────────────────────────────────┘
                                     │ GAP
                          ┌──────────▼───────────┐        ┌───────────────────────────┐
                          │ AGENTE VERIFICADOR    │        │ AGENTE INVESTIGADOR        │
                          │ ADVERSARIAL           │        │ DE VÍAS (GitHub/Reddit/    │
                          │ (desconfía, prueba)   │        │ foros/Camoufox & more)     │
                          └───────────────────────┘        └───────────────────────────┘
```

Principio rector: **fuentes pasivas, sink idempotente** (ya en orchestrator.py). El
diseño añade GOBIERNO (matriz, ledger, fases, veredicto) sin tocar el contrato de fuente.

---

## 3. Taxonomía de TIERS (diséñala — aquí está)

Dos ejes ortogonales que hoy están implícitos y mezclados. Se separan formalmente.

### 3.1 Tier de FUENTE (`source_tier`) — confianza/coste de la vía de descubrimiento

Reemplaza el `source_layer` 1-5 numérico (ambiguo) por un enum trazable. Migración:
`source_layer` se mantiene por compatibilidad pero se añade `source_tier TEXT`.

| source_tier | Significado | Ejemplos | Coste |
|---|---|---|---|
| `GOV_DUMP` | Registro gov descargable, censo poblacional | SIRENE dump, KvK, Zefix all-cantons, KBO CSV | 0 |
| `GOV_API` | Registro gov vía API (con tope) | recherche-entreprises, RDW Socrata | 0 |
| `ASSOC` | Asociación profesional | BOVAG, AGVS, FACONAUTO, ZDK | 0 |
| `DIRECTORY` | Páginas amarillas | PagesJaunes, GelbeSeiten, 11880 | 0 / anti-bot |
| `OEM` | Dealer-locator de marca | BMW STOLO, VW, Toyota… | 0 |
| `PLATFORM` | Directorio de dealers en portal | AS24 dealer-search, mobile.de Händler | 0 / anti-bot |
| `OSM` | OpenStreetMap Overpass | shop=car* | 0 |
| `WEB_INDEX` | CT logs / Common Crawl | crt.sh, CC URL index | 0 |
| `SEARCH` | Resolución por buscador | DDG/Mojeek + validación | 0 / proxy |
| `MAPS` | Places de pago | Google/Bing Places | $ (quirúrgico) |

### 3.2 Tier de ENTIDAD (`entity_tier`) — qué es y cuánto vale el inventario

| entity_tier | Definición | Señal de detección |
|---|---|---|
| `T0_PLATFORM` | Plataforma/portal Tier-1 | dominio en lista de portales; miles de listings |
| `T1_WHALE` | Dealer/grupo grande | `estimated_listings ≥ 200` o DMS conocido (dealerk) |
| `T2_DEALER` | Compraventa/concesionario con inventario web | `has_inventory` + 10-199 listings |
| `T3_GARAGE` | Garaje/taller con stock ocasional | actividad reparación + inventario fino |
| `T4_SCRAP` | Desguace/chatarrero | actividad 45.40/desguace + piezas/vehículos |
| `T5_IDENTITY` | Entidad sin web confirmada aún | identity-only row pendiente de resolución |

`entity_tier` lo asigna el classifier (ya existe `_assign_tier` en dealer_classifier.py,
se extiende). `T4_SCRAP` y `T0_PLATFORM` son nuevos respecto al T0-T3 actual.

### 3.3 Tier de DEFENSA (`defense_tier`) — ya existe en `source_entities` (T1/T2/T3)

Se reutiliza tal cual; lo consume el subsistema de extracción, no discovery. Discovery
solo lo anota cuando el classifier detecta WAF (campo `waf_type` en `dealers`).

---

## 4. Matriz FUENTE × PAÍS declarativa (núcleo del diseño)

**Archivo nuevo: `discovery/registry/source_matrix.yaml`** (portable, versionado, legible
por Codex u otra herramienta — cumple el requisito de portabilidad de recetas).

```yaml
# Cada fila: una vía de descubrimiento para un país, con su rank y fallback.
# El orquestador ejecuta por rank ascendente; si una vía da verdict!=COMPLETE
# para un slice, activa el siguiente fallback. primary=rank 1.
version: 3
defaults:
  rate_limit_rps: 2.0          # token-bucket global por host/fuente
  retry: {max: 5, backoff: exponential, base_s: 1.0}
  respect_robots: true
  user_agent: "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"

sources:
  fr_sirene_dump:
    module: scrapers.discovery.sources.sirene_ods_load   # dump path, NO la API
    source_tier: GOV_DUMP
    countries: [FR]
    activity_codes: ["45.11Z","45.19Z","45.20A","45.20B","45.31Z","45.32Z","45.40Z"]
    partition_by: departement
    yields: identity
    rank: 1
    census_authority: true     # esta fuente define el denominador FR
  fr_recherche_api:
    module: scrapers.discovery.sources.fr_recherche_entreprises
    source_tier: GOV_API
    countries: [FR]
    rank: 2                     # fallback del dump (verificación cruzada)
  nl_rdw:
    module: scrapers.discovery.sources.nl_rdw
    source_tier: GOV_API
    countries: [NL]
    rank: 1
    census_authority: true
  ch_zefix_allcantons:
    module: scrapers.discovery.sources.ch_zefix_allcantons
    source_tier: GOV_DUMP
    countries: [CH]
    partition_by: canton
    rank: 1
    census_authority: true
  de_offeneregister:
    module: scrapers.discovery.sources.de_offeneregister
    source_tier: GOV_DUMP
    countries: [DE]
    rank: 1
    status: BLOCKED            # fuente 502; plan: dump 773MB en VPS
    fallback_rank_bump: true   # mientras BLOCKED, DE asciende DIRECTORY/OEM/OSM
  be_kbo:
    module: scrapers.discovery.sources.be_kbo
    source_tier: GOV_DUMP
    countries: [BE]
    rank: 1
    status: NEEDS_CREDENTIAL   # CSV requiere registro; plan documentado
  oem_all:
    modules: [oem_bmw, oem_locators, oem_wave2, oem_brands_ext, oem_brands_full]
    source_tier: OEM
    countries: [DE,FR,ES,NL,BE,CH]
    rank: 2
  directories:
    modules: [fr_pagesjaunes, de_gelbeseiten, de_11880, es_paginasamarillas, nl_goudengids, ch_local]
    source_tier: DIRECTORY
    countries: [FR,DE,ES,NL,BE,CH]
    rank: 2
    engine: curl_cffi          # escala a camoufox si block_rate>0.3
  assoc:
    modules: [bovag, nl_bovag, ch_agvs, es_faconauto, de_zdk, fr_cnpa, be_traxio]
    source_tier: ASSOC
    countries: [NL,CH,ES,DE,FR,BE]
    rank: 2
  osm_full:
    module: scrapers.discovery.sources.osm_full
    source_tier: OSM
    countries: [DE,FR,ES,NL,BE,CH]
    partition_by: province     # admin_level=6 si el país excede timeout
    rank: 3
  platform_dealers:
    modules: [as24_dealers, mobile_de_haendler, coches_concesionarios, marktplaats_handelaars]
    source_tier: PLATFORM
    countries: [DE,FR,ES,NL,BE,CH]
    rank: 3
  web_index:
    modules: [ct_logs, common_crawl]
    source_tier: WEB_INDEX
    countries: [DE,FR,ES,NL,BE,CH]
    rank: 4
  maps_gap_fill:
    module: scrapers.discovery.sources.places_gapfill
    source_tier: MAPS
    countries: [DE,FR,ES,NL,BE,CH]
    rank: 9                     # SOLO disparado por GAP del motor de completitud
    budget_usd_month: 200
    gated_by: completeness_gap
```

El orquestador carga este YAML, lo valida con un esquema, y lo ejecuta. **Añadir una
fuente = añadir una fila + un módulo `XxxSource.discover(country)`** (contrato existente).
La matriz es la única fuente de verdad de "qué vías hay y en qué orden".

---

## 5. Recetas de fuente versionadas y portables

**Directorio nuevo: `discovery/recipes/<source>.json`** — persiste CÓMO se extrae cada
fuente (cumple: "si mañana se usa Codex debe saber qué pasos/configs se tomaron").

```json
{
  "source": "fr_pagesjaunes",
  "source_tier": "DIRECTORY",
  "country": "FR",
  "verified_at": "2026-06-09",
  "verified_by": "discovery-verifier",
  "transport": {"engine": "curl_cffi", "impersonate": "chrome",
                "fallback_engine": "camoufox", "fallback_trigger": "block_rate>0.3"},
  "endpoint": "https://www.pagesjaunes.fr/recherche/{quoi}/{ou}",
  "pagination": {"type": "page_param", "param": "page", "page_size": 20, "max_pages": 50},
  "query_terms_ref": "dealer_terms.FR.fr",
  "extract": {"strategy": "json_ld_or_microdata", "selectors": {
      "name": "h3.bi-denomination", "website": "a.bi-site[href]",
      "phone": "span.coord-numero", "city": "span.bi-address"}},
  "yields": "domain",
  "rate_limit_rps": 1.0,
  "robots": "respected",
  "known_failures": ["WAF DataDome on >5 rps → camoufox + slow"],
  "last_run": {"seen": 0, "written": 0, "verdict": "PENDING"}
}
```

Cada runner LEE su receta al arrancar. Una receta que cambia se versiona en git
(`docs(discovery): recipe fr_pagesjaunes v2`). Esto es lo que hace el sistema portable
y auditable a través de herramientas.

---

## 6. Esquemas de datos (DDL nuevo — migraciones aditivas, reversibles)

**Archivo nuevo: `scripts/migrations/0006_discovery_governance.up.sql`**

```sql
BEGIN;

-- 6.1 Run-ledger: trazabilidad y reanudación del orquestador.
CREATE TABLE IF NOT EXISTS discovery_runs (
    run_ulid       TEXT PRIMARY KEY,            -- ULID
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ,
    countries      TEXT[] NOT NULL,
    matrix_version INT NOT NULL,                -- source_matrix.yaml version
    status         TEXT NOT NULL DEFAULT 'RUNNING'
                   CHECK (status IN ('RUNNING','COMPLETE','PARTIAL','FAILED')),
    summary        JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS discovery_source_runs (
    id             BIGSERIAL PRIMARY KEY,
    run_ulid       TEXT NOT NULL REFERENCES discovery_runs(run_ulid),
    source         TEXT NOT NULL,               -- 'fr_sirene_dump'
    source_tier    TEXT NOT NULL,
    country        CHAR(2) NOT NULL,
    rank           SMALLINT NOT NULL,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ,
    seen           INT NOT NULL DEFAULT 0,
    written        INT NOT NULL DEFAULT 0,      -- new inserts
    refreshed      INT NOT NULL DEFAULT 0,      -- last_seen heartbeats
    errors         INT NOT NULL DEFAULT 0,
    block_rate     NUMERIC(4,3),                -- anti-bot signal → escalate engine
    verdict        TEXT CHECK (verdict IN ('OK','PARTIAL','BLOCKED','EMPTY','ERROR')),
    note           TEXT
);
CREATE INDEX IF NOT EXISTS idx_dsr_run ON discovery_source_runs(run_ulid);
CREATE INDEX IF NOT EXISTS idx_dsr_src ON discovery_source_runs(source, country);

-- 6.2 Tier de entidad + tier de fuente en el intake (aditivo, sin romper).
ALTER TABLE discovery_candidates ADD COLUMN IF NOT EXISTS source_tier TEXT;
ALTER TABLE discovery_candidates ADD COLUMN IF NOT EXISTS entity_tier TEXT;
ALTER TABLE discovery_candidates ADD COLUMN IF NOT EXISTS province TEXT;  -- admin_level=6 / dpto / provincia
ALTER TABLE discovery_candidates ADD COLUMN IF NOT EXISTS h3_res7 TEXT;   -- blocking key para dedup
CREATE INDEX IF NOT EXISTS idx_disc_cand_province ON discovery_candidates(country, province);
CREATE INDEX IF NOT EXISTS idx_disc_cand_h3 ON discovery_candidates(h3_res7) WHERE h3_res7 IS NOT NULL;

-- 6.3 Código único institucional de entidad (país-provincia-secuencia).
--   Formato: <CC>-<PROV>-<base32(seq)>  ej. FR-75-0001K3
ALTER TABLE dealers ADD COLUMN IF NOT EXISTS cardex_code TEXT UNIQUE;
ALTER TABLE dealers ADD COLUMN IF NOT EXISTS entity_tier TEXT;
ALTER TABLE dealers ADD COLUMN IF NOT EXISTS province TEXT;

-- 6.4 Censo de ENTIDADES (no de vehículos) por slice — el denominador de completitud.
CREATE TABLE IF NOT EXISTS entity_census (
    id             BIGSERIAL PRIMARY KEY,
    country        CHAR(2) NOT NULL,
    province       TEXT,
    activity_code  TEXT NOT NULL,               -- NAF/CNAE/WZ/NACE/NOGA
    source         TEXT NOT NULL,               -- 'sirene_dump'
    entity_count   BIGINT NOT NULL CHECK (entity_count >= 0),
    as_of_date     DATE NOT NULL,
    ingested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (country, province, activity_code, source, as_of_date)
);
CREATE INDEX IF NOT EXISTS idx_entity_census_slice ON entity_census(country, province, activity_code);

-- 6.5 Veredicto de completitud por slice (lo que responde "¿están TODOS?").
CREATE TABLE IF NOT EXISTS discovery_completeness (
    id             BIGSERIAL PRIMARY KEY,
    country        CHAR(2) NOT NULL,
    province       TEXT,
    activity_code  TEXT,
    estimated      BIGINT,                       -- max(census, capture_recapture)
    observed       BIGINT NOT NULL,              -- distinct entities in dealers
    ratio          NUMERIC(5,4) NOT NULL,
    verdict        TEXT NOT NULL CHECK (verdict IN ('COMPLETE','NEAR','GAP')),
    method_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,  -- {v1:..,v2:..,v3:..}
    gap_sample     JSONB,                        -- ejemplos concretos de lo que falta
    computed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (country, province, activity_code, computed_at)
);
CREATE INDEX IF NOT EXISTS idx_completeness_verdict ON discovery_completeness(verdict, country);

COMMIT;
```

`down.sql` simétrico (DROP de tablas nuevas, columnas aditivas ON IF EXISTS). Totalmente
reversible — sin riesgo sobre las 112k filas existentes (solo ADD COLUMN/CREATE).

### 6.6 Contrato de candidato (ya existente, formalizado)

Todo `XxxSource.discover(country)` yield un dict con exactamente estas claves (ya es el
contrato de facto en osm.py/fr_sirene.py/oem_bmw.py/common_crawl.py):

```
domain, country, source_layer, source, url, name, address, city, postcode,
phone, email, lat, lng, registry_id, external_refs
```

Se AMPLÍA con dos claves opcionales sin romper: `source_tier`, `province`. El sink
(`orchestrator._upsert`) las mapea a las columnas nuevas. Los runners viejos que no las
emitan siguen funcionando (NULL).

---

## 7. Motor de completitud — "¿están TODOS?" (verificación adversarial integrada)

Tres vías **independientes** (distintas entre sí y distintas de la extracción). Ningún
veredicto COMPLETE se emite si las tres no concuerdan. Implementado en módulo nuevo
`scrapers/discovery/completeness/` con un runner por vía + un consolidador.

### V1 — Re-derivación de la fuente de censo (`completeness/rederive.py`)
Generaliza `scripts/verify_discovery.py` (hoy solo FR). Para cada fuente con
`census_authority: true`, re-enumera INDEPENDIENTEMENTE el conjunto completo de IDs por
slice y verifica que cada ID está en `discovery_candidates`. `completeness = in_db/source_total`.
Cualquier ID faltante = gap exacto → se re-cosecha (modo `--fill`). Esto desconfía del
conteo Y de la cobertura del harvester. Ya probado FR (98,8% AS24, gaps cerrados).

### V2 — Capture-recapture entre fuentes (`completeness/capture_recapture.py`)
Puebla `source_overlap_matrix` (tabla ya existe, sin runner). Para cada par de fuentes
independientes (A=SIRENE dump, B=OSM) cuenta overlap y estima la población total por
Chapman (Lincoln-Petersen sesgo-corregido): `N̂ = (n_A+1)(n_B+1)/(m+1) − 1`, con varianza
y CI. Si `observed << N̂`, hay entidades que NINGUNA fuente capturó → GAP estructural que
exige una vía nueva (dispara Investigador). Esta es la única vía que detecta "lo que no
está en ningún registro".

### V3 — Censo top-down flota × rotación (`completeness/census_topdown.py`)
Carga `entity_census` desde los dumps gov (conteo de establecimientos por código auto y
provincia — el denominador poblacional puro). Compara con `observed` (entidades distintas
en `dealers`). Para inventario: cruza con `coverage_matrix` existente (flota × turnover ×
avg_dom/365 = vehículos esperados a la venta). Si una provincia tiene 1.200 establecimientos
45.11Z en censo y solo 800 en `dealers`, hay 400 sin descubrir → GAP localizado.

### Consolidador (`completeness/verdict.py`)
`estimated = max(census_V3, chapman_V2)`. `ratio = observed/estimated`. Veredicto por
umbral (§0). Escribe `discovery_completeness` con `method_breakdown` y `gap_sample`
(ejemplos concretos: 50 registry_id / nombres / celdas H3 que faltan — NO solo números).
Esto cumple la doctrina: verificar **números Y contenido** (frescura, correctness,
completitud), no solo conteos.

---

## 8. Protocolo "agotar TODAS las vías" + Agente Investigador

Cuando un slice queda en **GAP** tras ejecutar la matriz hasta el último rank no-MAPS:

1. **Escalada dentro de la matriz**: subir un rank (p.ej. activar PLATFORM/WEB_INDEX si
   solo se usó GOV+OEM). `fallback_rank_bump` automatiza esto para fuentes BLOCKED.
2. **Escalada de engine**: si `block_rate > 0.3` en una fuente DIRECTORY/PLATFORM,
   conmutar `curl_cffi → Camoufox` (ya instalado) con rate más lento + identidad rotada
   (`scrapers/engine/identity`). Proxy de pago SOLO si el block persiste tras Camoufox.
3. **MAPS gap-fill quirúrgico**: disparar `places_gapfill` SOLO en las celdas H3 res7 del
   `gap_sample`, con presupuesto acotado (`budget_usd_month`).
4. **Agente Investigador de Vías** (§9): si tras 1-3 el GAP persiste, se lanza el agente
   que busca en GitHub/Reddit/foros/Internet una **vía nueva** (nuevo dump regional, nuevo
   directorio, nueva técnica anti-detección, nueva herramienta open-source). Su hallazgo
   se materializa como una nueva fila en `source_matrix.yaml` + un módulo + una receta.

Nunca se cierra un slice en GAP sin haber pasado por 1-4 y haberlo registrado. "No se
puede" está prohibido: si no se resuelve, se documenta exactamente qué se intentó y cuál
es el siguiente paso accionable (doctrina DE/BE: BLOCKED con plan, nunca inventado).

---

## 9. Workflows y Agentes

### 9.1 Workflow `discovery-full-sweep` (ciclo completo, ejecutado por el scheduler)
Fases secuenciales con verificación entre cada una:
`descubrir (matriz) → resolver (domain_resolution) → consolidar (dedup) → verificar (completitud) → [GAP → agotar vías] → cerrar`.
Persiste `discovery_runs`/`discovery_source_runs`. Reanudable: si el contexto/proceso muere,
el ledger sabe qué `(source,country)` quedó a medias.

### 9.2 Workflow `discovery-consolidate` (dedup canónico candidates → dealers)
Tres capas (la tabla `entity_matches` Fellegi-Sunter ya existe):
- **C1 clave exacta**: por `domain` (apex normalizado), por `(source,registry_id)`, por `place_id`.
- **C2 blocking**: agrupa candidatos por `h3_res7` + trigram(name) (pg_trgm ya instalado) →
  solo compara dentro del bloque (evita O(n²)).
- **C3 scoring Fellegi-Sunter**: features (name jaro-winkler, address trigram, phone exacto,
  geo-distance H3, postcode) → score → `entity_matches` con `confidence`. Match ≥ 0.92 funde;
  0.75-0.92 → revisión; usa LLM local (Qwen 7B GGUF ya en SPEC §2) para los dudosos
  (coste 0/token). Resultado: una fila canónica en `dealers` con `cardex_code` único y
  `discovery_sources TEXT[]` (todas las fuentes que la vieron — clave para capture-recapture).

### 9.3 Workflow `discovery-verify` (motor de completitud §7)
Corre V1/V2/V3 + consolidador. Read-mostly (V1 con `--fill` opcional). Emite veredictos.

### 9.4 Agentes

| Agente | Rol | Responsabilidad | Tools | Criterio de calidad |
|---|---|---|---|---|
| **discovery-lead** (Opus) | Líder orquestador | Lee `source_matrix.yaml`, planifica el sweep por país/provincia/actividad, decide escaladas (§8), abre/cierra `discovery_runs`, NUNCA cierra con GAP no documentado | Read/Grep/Bash (ejecuta runners), DB read/write al ledger | Cero slice cerrado sin veredicto; toda escalada registrada |
| **discovery-verifier** (Sonnet) | Verificador adversarial CO-IGUAL | Desconfía de TODO output de los runners; corre V1/V2/V3 por vías distintas a las de extracción; verifica frescura+correctness+completitud, no conteos; produce `gap_sample` concreto | Read/Bash (runners de completitud), DB read, httpx (re-derivación) | Un COMPLETE solo si las 3 vías concuerdan; reporta gaps con ejemplos reales |
| **discovery-researcher** (Sonnet/Opus) | Investigador de vías | Ante GAP/BLOCKED persistente: busca en GitHub (`gh search`), Reddit, foros, registros regionales, herramientas open-source (Camoufox y otras) una vía NUEVA; entrega fila YAML + módulo + receta | gh, WebSearch/Exa, Context7, Read/Write | No vuelve sin ≥1 vía nueva accionable o prueba exhaustiva de que no existe |
| **discovery-auditor** (Haiku) | Motivador/Puerta de cierre | Antes de declarar el sweep terminado, autointerroga el ledger: ¿hay slice GAP sin plan? ¿runner con verdict ERROR sin reintento? ¿receta sin verified_at reciente? Bloquea el cierre si hay huecos | DB read, Read | Cero ítem abierto sin bloqueo real declarado |

Orquestación: `discovery-lead` despliega `discovery-verifier` tras cada fase y
`discovery-researcher` en paralelo por cada GAP (Task paralelo, no secuencial, por país).
`discovery-auditor` corre al final como Stop-gate.

### 9.5 Integración con el scheduler [cierra brecha real]
Añadir a `scripts/master_scheduler.py` JOBS la entrada que su propio docstring promete:
```python
("discovery_sweep", "scrapers.discovery.orchestrator", {"DISCOVERY_MATRIX": "discovery/registry/source_matrix.yaml"}, 24*3600, False),
("discovery_consolidate", "scrapers.discovery.consolidate", {}, 12*3600, False),
("discovery_verify", "scrapers.discovery.completeness.run", {}, 6*3600, False),
```

---

## 10. Anti-detección y coste (grado institucional)

- **Por defecto coste-cero**: GOV_DUMP/GOV_API/OSM/WEB_INDEX/ASSOC no necesitan nada.
- **DIRECTORY/PLATFORM**: `curl_cffi` (impersonate chrome, instalado) primero; escalar a
  **Camoufox** (instalado) si `block_rate>0.3`; JA3/TLS coherente vía `engine/antidetect`.
- **Rate-limiter GLOBAL token-bucket** por host (patrón `mass_registry._RateLimiter`),
  obligatorio en toda fuente desde el primer commit (lección SIRENE).
- **Proxies de pago**: SOLO en muro real persistente, vía `domain_resolution/proxy_pool.py`.
- **LLM local** (Qwen 7B GGUF, SPEC §2) para: normalización de nombres, clasificación de
  entity_tier, desempate de matches dudosos C3, clasificación de actividad. Coste 0/token.
- **robots.txt respetado** (ya en classifier/frontier); UA identificable CardexBot.

---

## 11. Criterios de aceptación (medibles)

1. `source_matrix.yaml` existe, valida contra esquema, y el orquestador ejecuta TODAS sus
   filas no-BLOCKED (verificable: `discovery_source_runs` tiene una fila por
   `(source,country,rank)` esperado por run).
2. El orquestador está cableado en `master_scheduler.py` y corre cada 24h sin caerse si
   una fuente falla (resiliencia: una fuente BLOCKED no aborta el run — ya es así en
   `_drain_source` try/except; se verifica con un run completo).
3. `discovery_runs.status='COMPLETE'` solo si ningún `discovery_source_runs.verdict='ERROR'`
   quedó sin reintento.
4. Pipeline de consolidación puebla `dealers` con `cardex_code` único y
   `discovery_sources` poblado; `entity_matches` tiene filas con `confidence` para los
   pares C3. Tasa de duplicados en `dealers` (mismo dealer físico, distinta fila) < 1%
   medida por muestreo manual de 200 filas.
5. `source_overlap_matrix` y `entity_census` se pueblan; `discovery_completeness` emite
   veredicto por cada slice `(país, provincia, actividad)` de los 6 países.
6. Por cada país, ≥1 fuente `census_authority` activa (FR sirene, NL rdw, CH zefix;
   DE/BE con plan documentado mientras BLOCKED). FR alcanza COMPLETE (ratio≥0.99) en
   ≥90% de departamentos para 45.11Z (extiende el resultado ya logrado).
7. Todo slice en GAP tiene `gap_sample` con ejemplos concretos y un registro de las vías
   agotadas (§8). Cero GAP cerrado en silencio.
8. Cada fuente tiene una receta `discovery/recipes/<source>.json` con `verified_at` y
   `last_run.verdict`. Una receta stale (>30d) la marca `discovery-auditor`.
9. Cobertura de tests ≥80% en módulos nuevos (transform puro testeable sin red, patrón
   ya usado en `tests/test_fanout_sources.py`).

---

## 12. Objetivos realistas por país (orden de magnitud, a refinar con el censo V3)

| País | Fuente censo (denominador) | Censo aprox. entidades auto | Estado discovery actual | Vía de cierre |
|---|---|---|---|---|
| FR | SIRENE dump 45.x | ~505k auto reachable (memoria) | dump+API verificados | dump completo en VPS, V1 por dpto |
| DE | OffeneRegister dump | decenas de miles dealers | ~45k candidatos (otras fuentes) | dump 773MB VPS + OEM + DIRECTORY |
| ES | sin dump CNAE libre | decenas de miles | OpenMercantil parcial | OEM-locators por CP + FACONAUTO + OSM |
| NL | RDW erkende bedrijven | ~miles dealers reconocidos | nl_rdw vivo | RDW completo + BOVAG |
| BE | KBO/BCE CSV | ~miles | ~4k candidatos | registrar KBO + Traxio + OSM |
| CH | Zefix all-cantons | ~miles (26 cantones) | BS verificado | mirror 26 cantones + AGVS |

El número exacto NO se inventa: lo fija V3 (entity_census) tras cargar cada dump. El
"objetivo" es `ratio≥0.99` por slice, no un absoluto a ciegas.

---

## 13. Archivos a crear / tocar (mapa concreto de ejecución)

**Crear:**
- `discovery/registry/source_matrix.yaml` — matriz fuente×país
- `discovery/registry/matrix_schema.json` — validación de la matriz
- `discovery/recipes/<source>.json` — una por fuente (≈25)
- `scrapers/discovery/consolidate.py` — dedup canónico C1/C2/C3 → dealers/entity_matches
- `scrapers/discovery/completeness/__init__.py`
- `scrapers/discovery/completeness/rederive.py` — V1 (generaliza verify_discovery.py)
- `scrapers/discovery/completeness/capture_recapture.py` — V2 (puebla source_overlap_matrix)
- `scrapers/discovery/completeness/census_topdown.py` — V3 (puebla entity_census + cruza coverage_matrix)
- `scrapers/discovery/completeness/verdict.py` — consolidador → discovery_completeness
- `scrapers/discovery/completeness/run.py` — entrypoint del workflow verify
- `scrapers/discovery/sources/places_gapfill.py` — MAPS gap-fill (S7, quirúrgico)
- `scrapers/discovery/sources/{es_paginasamarillas,nl_goudengids,ch_local,es_faconauto,de_zdk,fr_cnpa,be_traxio,oem_brands_full,mobile_de_haendler,coches_concesionarios,marktplaats_handelaars}.py` — fuentes faltantes de la matriz
- `scripts/migrations/0006_discovery_governance.{up,down}.sql`
- `.claude/agents/{discovery-lead,discovery-verifier,discovery-researcher,discovery-auditor}.md`
- `tests/test_completeness.py`, `tests/test_consolidate.py`, `tests/test_source_matrix.py`

**Tocar (mínimo, sin romper):**
- `scrapers/discovery/orchestrator.py` — cargar `source_matrix.yaml` en vez de `_SOURCES`
  hardcodeado; escribir `discovery_runs`/`discovery_source_runs`; mapear `source_tier`/`province`.
- `scrapers/discovery/dealer_classifier.py` — extender `_assign_tier` a la taxonomía §3.2
  (añadir T0_PLATFORM/T4_SCRAP).
- `scripts/master_scheduler.py` — añadir los 3 JOBS de §9.5 (cierra la brecha del docstring).
- `scrapers/discovery/sources/sirene_ods_load.py` / `sirene_standalone.py` — apuntar al
  dump como `census_authority` FR (preferir dump sobre API).

## Decisiones clave
- Construir sobre el orchestrator.py existente, NO reescribir: el contrato fuente (discover(country) → dict) y el sink idempotente de doble upsert ya funcionan y se conservan. El diseño añade gobierno (matriz, ledger, fases, veredicto), no un sistema paralelo.
- Matriz fuente×país DECLARATIVA en YAML (source_matrix.yaml) con rank+fallbacks como única fuente de verdad de las vías, reemplazando la lista _SOURCES hardcodeada. Añadir una fuente = una fila + un módulo. Portable a Codex u otra herramienta.
- Separar formalmente TRES tiers ortogonales hoy mezclados: source_tier (vía de descubrimiento), entity_tier (qué es la entidad: T0_PLATFORM..T5_IDENTITY, añadiendo desguace y plataforma), defense_tier (ya existe, lo usa extracción). El source_layer numérico 1-5 se mantiene por compatibilidad pero se complementa con source_tier enum trazable.
- Dumps gov descargables como PRIMARIA de censo (no APIs con tope): lección dolorosa ya grabada (SIRENE dump > recherche-entreprises API). El dump da el DENOMINADOR poblacional que ninguna otra vía aporta y es la base del motor de completitud.
- Verificación de completitud por TRES vías independientes y co-iguales (re-derivación de fuente + capture-recapture Chapman + censo top-down flota×rotación), reutilizando las tablas ya existentes pero sin runner (source_overlap_matrix, coverage_matrix) y generalizando verify_discovery.py (hoy solo FR). Un COMPLETE exige concordancia de las tres. Se verifica contenido (gap_sample con ejemplos reales), no solo conteos.
- Dedup canónico en 3 capas (clave exacta → blocking H3+trigram → Fellegi-Sunter con LLM local para dudosos) que puebla la tabla dealers (con cardex_code único) y entity_matches (ambas ya existen sin pipeline). Evita O(n²) por blocking; coste 0/token usando Qwen local.
- Cablear el orquestador en master_scheduler.py: cierra una brecha REAL (el docstring promete discovery orchestrator every 24h pero no está en JOBS).
- Run-ledger persistente (discovery_runs/discovery_source_runs) para trazabilidad y reanudación: el estado no vive en contexto volátil; si un proceso muere, el ledger sabe qué (source,country) quedó a medias.
- Cuatro agentes con roles separados: Líder (planifica/cierra), Verificador adversarial (desconfía/prueba por vía distinta), Investigador de vías (GitHub/Reddit/foros/Camoufox ante GAP), Auditor-motivador (puerta de cierre que bloquea huecos silenciosos). Despliegue paralelo por país.
- Protocolo de agotamiento de vías formal y escalonado (escalada de rank → escalada de engine curl_cffi→Camoufox → MAPS quirúrgico por celda H3 → Investigador). MAPS de pago SOLO disparado por GAP del motor de completitud, nunca barrido total. Prohibido cerrar en GAP sin documentar las vías agotadas.
- Coste-eficiente por defecto: 90% de las vías son coste-cero (dumps/OSM/CT/CC/asociaciones); curl_cffi/Camoufox gratis para anti-bot; LLM local para clasificación/dedup; proxies de pago solo en muro persistente.
- Migraciones puramente aditivas y reversibles (ADD COLUMN / CREATE TABLE IF NOT EXISTS) sobre las 112k filas existentes: cero riesgo, down.sql simétrico.

## Riesgos
- Sobre-ingeniería del gobierno: el riesgo de añadir matriz+ledger+veredicto es ralentizar lo que ya rinde. Mitigación: la matriz solo formaliza lo existente; los runners no cambian de contrato; el ledger es write-only ligero.
- Censo poblacional erróneo → veredicto de completitud falso. Si entity_census tiene un denominador inflado (códigos de actividad que incluyen no-auto) o deflactado (códigos faltantes), el ratio miente. Mitigación: V2 capture-recapture es independiente del censo y cruza-valida V3.
- Capture-recapture asume independencia de fuentes; si dos fuentes derivan de la misma base (SIRENE dump y recherche-entreprises API son ambas INSEE), el estimador Chapman se sesga a la baja (subestima la población). Mitigación: emparejar solo fuentes genuinamente ortogonales (SIRENE vs OSM vs OEM), nunca dos del mismo origen.
- Anti-bot en DIRECTORY/PLATFORM (PagesJaunes DataDome, mobile.de) puede escalar más rápido que curl_cffi→Camoufox, forzando proxies de pago antes de lo previsto y rompiendo el supuesto coste-cero.
- Dedup difuso C3 con falsos merges: fundir dos dealers distintos del mismo grupo en la misma celda H3 con nombres similares destruye entidades reales. Mitigación: umbral conservador (≥0.92 auto-merge), banda de revisión 0.75-0.92, LLM local + muestreo manual de 200 filas como criterio de aceptación.
- Dependencia de fuentes BLOCKED (DE 502, BE credencial) deja dos países sin census_authority real → su veredicto de completitud es provisional. Riesgo de declarar COMPLETE en DE/BE sobre un denominador proxy. Mitigación: marcar explícitamente verdict='PROVISIONAL' hasta desbloquear la fuente gov.
- El run completo de la matriz × 6 países puede saturar RAM/sockets del VPS CX42 (16GB) si se ejecutan demasiadas fuentes en paralelo. Mitigación: el patrón RAM-safe de resolver.py (keyset, gc, RSS watchdog) y rate-limiters globales ya existen; aplicarlos a todo runner.
- Drift de recetas: una fuente cambia su HTML/endpoint y la receta queda stale silenciosamente, produciendo verdict='EMPTY' que parece 'no hay dealers' en vez de 'la receta se rompió'. Mitigación: discovery-auditor marca recetas >30d sin verified_at; V2/V3 detectan la caída de observed como anomalía, no como verdad.