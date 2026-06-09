# Modelo de Datos Canonico y Estructura Institucional (geo-jerarquia pais→provincia→ciudad, codigo unico de entidad, taxonomia de tiers, recetas portables, ledger de cobertura medible y delta/historico verificado)

## Resumen
CARDEX ya tiene un store real maduro en PostgreSQL 16 (verificado leyendo scripts/init-pg.sql, las 5 migraciones de scripts/migrations/ y discovery/internal/db/schema.sql) pero le falta exactamente lo que pide este subsistema: una COLUMNA VERTEBRAL institucional. Hoy la geografia vive como senales sueltas y heterogeneas (entities.country_code + h3_index_res4; dealers.country/city/postcode/canton/lat/lng/h3; discovery_candidates.country/city/postcode/lat/lng; vehicle_index.country CHAR(2)), NO existe ninguna tabla provincia/region ni ciudad, NO hay codigo unico legible por dealer (las claves son entity_ulid, source_entities.entity_ulid='se_'||md5, dealers.id BIGSERIAL, coverage_ledger.domain TEXT — cuatro identidades distintas para la misma entidad fisica), y la cobertura se mide por dominio (coverage_ledger.status) sin poder agregarse por provincia. La taxonomia de tipos esta fragmentada en al menos cinco vocabularios incompatibles (entities.entity_type DEALER/FLEET/INSTITUTION/INDIVIDUAL; dealers.dealer_type INDEPENDENT; source_entities.kind platform/dealer; discovery_candidates.source_layer 1-5; dealer_profile.tier T0-T3). El inventario canonico SI existe y es bueno (scrapers/pipeline/schema.py VehicleRecord congelado con content_fingerprint + price_hash; delta puro en pipeline/delta.py; historico append-only en vehicle_events particionado). Las recetas YA son portables y git-trackeadas (configs/portals|dealers/*.json via scrapers/portals/config.py) — exactamente lo que el mandato exige para Codex. Mi diseno NO es greenfield: introduce una capa institucional canonica (geo_country/geo_region/geo_city normalizadas a NUTS+LAU, una tabla unica entity con CDX-code estable y legible, un crosswalk que une las 4 identidades existentes sin romper ninguna FK, una taxonomia de tiers unificada, y un coverage_ledger reescrito como matriz pais x provincia x tier agregable) construida con migraciones reversibles NOT VALID/backfill al estilo de las que ya existen, reutilizando h3, pg_trgm, los triggers de scope de 6 paises y el patron emit-recipe. El resultado: toda entidad fisica tiene UN codigo, vive en UN punto de la jerarquia, su cobertura es medible y agregable por provincia, su receta es portable, y su inventario+delta+historico es verificable adversarialmente por una via independiente a la extraccion.

## Estrategias
- **E1 — Capa institucional canonica sobre el store PG existente (PRIMARIA)**: Crear migraciones reversibles en scripts/migrations/ (siguiente indice 0006..0012) que anaden: (1) geo_country/geo_region/geo_city sembradas desde dumps oficiales gratuitos (Eurostat NUTS 2021 + LAU, INSEE COG FR, INE ES, BFS CH, CBS NL, KBO/Statbel BE, Destatis AGS DE) — NUNCA APIs rate-limitadas, siguiendo la leccion SIRENE; (2) tabla canonica `entity` con CDX-code estable+legible (esquema en spec) y FKs a la jerarquia; (3) `entity_xref` crosswalk que mapea entity_id a las 4 identidades vivas (entities.entity_ulid, source_entities.entity_ulid, dealers.id, coverage_ledger.domain, discovery_candidates.id) SIN tocar esas tablas — cero rotura de las 18 tablas comerciales; (4) `entity_tier` taxonomia unificada; (5) coverage_ledger v2 agregable. Backfill por fases (geocode inverso lat/lng->NUTS via punto-en-poligono local con shapefiles, fallback postcode->LAU por tabla, fallback ciudad por pg_trgm). Reutiliza is_safe_public_url, triggers scope 6-paises, h3.
- **E2 — Resolucion geografica multi-senal con cascada de fallbacks**: Pipeline de asignacion entity->city->region->country con 5 niveles rankeados por confianza: (1) lat/lng -> punto-en-poligono contra shapefiles NUTS3/LAU locales (confianza 0.99); (2) postcode+country -> tabla postcode->LAU precargada del dump nacional (0.95); (3) registry_id (SIRET/KBO/CHE) -> el codigo geografico embebido (SIRET deciles dept, CHE canton) (0.9); (4) ciudad textual -> match pg_trgm contra geo_city.name normalizada (0.7, requiere desambiguacion por country); (5) TLD+heuristica dominio (0.3, ultimo recurso, marca needs_review). Cada asignacion guarda geo_method + geo_confidence + geo_evidence (JSONB). Por debajo de umbral 0.6 -> cola de revision, nunca asignacion silenciosa.
- **E3 — CDX-code: codigo unico estable, legible y deterministico**: Formato CDX-{CC}-{REG}-{TYPE}{NNNN} (ej. CDX-FR-75-D0042). CC=ISO pais; REG=codigo NUTS2/provincia corto; TYPE=letra de tier (D dealer indep, O OEM, P plataforma, S desguace, F flota, G garaje); NNNN=secuencia estable por (pais,region,type) asignada en orden de first_seen. El codigo es INMUTABLE una vez asignado (si una entidad se re-geolocaliza a otra provincia, conserva su CDX-code original y se registra el movimiento en entity_geo_history — la legibilidad es una etiqueta, la identidad es el codigo). La generacion es una funcion PG con secuencia por bucket + advisory lock para concurrencia. Alternativa de respaldo si se exige determinismo puro sin secuencia: CDX-{CC}-{REG}-{TYPE}-{base32(sha1(domain|registry_id))[:6]} (colisiones manejadas).
- **E4 — Recetas portables versionadas (REUTILIZAR lo existente, extender)**: El sistema YA persiste recetas en configs/portals|dealers/*.json con scrapers/portals/config.py (ExtractionConfig: strategy/endpoints/pagination/extraction/drift_baseline; emit() create-if-absent que no clobbera ediciones humanas; load() portal-wins-over-dealer). NO reinventar. Extender: (a) anadir bloque `provenance` a la receta (discovered_by, resolver_method, last_proven_at, proven_volume, declared_total_cross_check) para portabilidad total a Codex; (b) anadir `entity_code` (CDX) al JSON para enlace bidireccional receta<->entity; (c) un indice receta-en-PG (tabla entity_recipe espejo del archivo con hash de contenido) para queries 'que entidades tienen receta probada' sin escanear 30k archivos. El archivo sigue siendo la fuente de verdad git-trackeada; PG es solo indice.
- **E5 — Cobertura medible y agregable (coverage_ledger v2)**: El coverage_ledger actual (PK domain, status yielded/no_inventory/no_web/error/timeout) es por-dominio y NO agregable por provincia. Reescribir como: coverage_ledger keyed por entity_code, con FK a geo_city/region/country, mas una VISTA materializada coverage_rollup que computa % cerrado por (country,region,tier) = entidades yielded / entidades descubiertas-con-web. Cruzar con coverage_matrix (fleet census) y source_overlap_matrix (Lincoln-Petersen, ya existe) para estimar el DENOMINADOR real (cuantas entidades faltan por descubrir, no solo cuantas de las conocidas estan cerradas). Dos KPIs honestos: cobertura-de-descubrimiento (conocemos todas las entidades?) y cobertura-de-extraccion (extraemos el inventario de las que conocemos?).
- **E6 — Agente de investigacion ante muro (protocolo agotar-todas-las-vias)**: Cuando la resolucion geografica o la deduplicacion de identidad falla para un bucket (>X% needs_review en una provincia, o un pais sin dump LAU usable), disparar un agente de investigacion que busca en GitHub/Reddit/foros/Internet datasets abiertos alternativos (geonames, openaddresses, whosonfirst, geoboundaries, pgeocode, libpostal para parsing de direcciones, Camoufox-style fallbacks para portales-fuente que requieran render). Persiste hallazgos en docs/research/geo-<pais>.md. Nunca declara 'no se puede': escala a fuente alternativa.

## Spec completa
## CARDEX — Subsistema: Modelo de Datos Canonico y Estructura Institucional

> Estado de partida [VERIFICADO leyendo el repo]. Diseno objetivo + migraciones reversibles sobre el store REAL. NO greenfield.

---

### 0. Reconocimiento real (lo que YA existe — citado, no asumido)

Store real = PostgreSQL 16 (`scripts/init-pg.sql`, 1157 lineas) + 5 migraciones (`scripts/migrations/0001..0005`, `002_portal_cadence.sql`). El `discovery/internal/db/schema.sql` es SQLite del modulo Go legacy (knowledge graph) — coexiste pero NO es el store de produccion (lo confirman `grind_coverage.py` y `close_entity.py`, ambos golpean `postgres://cardex@localhost:5432/cardex`). La memoria del proyecto ya lo advierte: "store REAL = PostgreSQL+Redis (NO SQLite; docs/skill stale)".

Activos canonicos que se REUTILIZAN tal cual:
- **Inventario L1 (punteros):** `vehicle_index` (PK `url_hash`, ~436K filas vivas, deep-links + precio/km/anio ligeros). Index `idx_vi_dc (source_domain,country)`.
- **Inventario L2 (rico):** `vehicles` (PK `vehicle_ulid`, `fingerprint_sha256` UNIQUE, make/model/price/scoring/geo h3). FK nullable `entity_ulid -> source_entities` (migr 0001, `ON DELETE SET NULL`, `NOT VALID`).
- **Historico/Delta:** `vehicle_events` (append-only, PARTITION BY RANGE(ts), event_type SEEN/ENRICHED/GONE) + `pipeline/delta.py` (set-diff puro + `price_hash`) + `pipeline/schema.py` (`VehicleRecord` congelado, `content_fingerprint`, `price_hash`).
- **Recetas portables:** `configs/portals/*.json` (curadas) y `configs/dealers/*.json` (auto-generadas), gobernadas por `scrapers/portals/config.py` (`ExtractionConfig`, `emit()` create-if-absent, `load()` portal-wins). Ejemplos reales: `autotrack.nl.json` (portal_paginated con field_map JSON-LD completo), `autolina.ch.json` (playwright_meta), `dacia-calais.fr.json` (sitemap_listing).
- **Cobertura:** `coverage_ledger` (DDL embebido en `grind_coverage.py`: PK `domain`, status, inventory_count, recipe, drift_ok, purged). `coverage_matrix` (fleet census x turnover). `source_overlap_matrix` (Lincoln-Petersen/Chapman — capture-recapture YA implementado).
- **Descubrimiento:** `discovery_candidates` (~112K, source_layer 1-5, sitemap/ddg/indexer state). `dealers` (registro fisico merged). `dealer_profile` (DDL en `dealer_classifier.py`: cms_type, tier T0-T3, estimated_listings).
- **Dedup cross-source:** `entity_matches` (Fellegi-Sunter, match_type VEHICLE|DEALER).
- **Tenant comercial:** `entities` (PK `entity_ulid`, vault_dek_id, Stripe/KYC, RLS, 18 tablas dependientes). `source_entities` (supply-side, kind platform/dealer, `entity_ulid='se_'||md5(source_key)`).
- **Resiliencia/alertas:** `operator_alerts` (stage/signal/severity/evidence). `portal_cadence` (scheduling adaptativo).
- **Invariante de scope:** trigger + CHECK constraint de 6 paises ES/FR/DE/BE/NL/CH en `discovery_candidates`/`source_entities`/`vehicle_index` (migr 0004/0005 — endurecido tras un incidente real de ampliacion ilegal a 10 paises).
- **Geo libre:** `scrapers/discovery/geocode.py` (Nominatim 1req/s — usable solo a baja escala).

**GAP confirmado (lo que NO existe y este subsistema crea):**
1. NO hay tabla de provincia/region ni de ciudad. La geo es texto suelto y heterogeneo en 4 tablas.
2. NO hay codigo unico de entidad legible. Hay 4 identidades para la misma entidad fisica: `entities.entity_ulid`, `source_entities.entity_ulid`, `dealers.id`, `coverage_ledger.domain`.
3. La cobertura NO es agregable por provincia/tier (ledger por domain).
4. La taxonomia de tipos esta fragmentada en 5 vocabularios incompatibles.
5. NO hay enlace bidireccional receta<->entidad<->geografia.

---

### 1. Arquitectura objetivo — la columna vertebral institucional

```
                         CAPA INSTITUCIONAL CANONICA  (NUEVA)
   geo_country ──< geo_region ──< geo_city
        │              │              │
        └──────────────┴──────────────┴───────────┐
                                                   ▼
                          ┌──────────────  entity  ───────────────┐
                          │  entity_id (UUID)  ·  cdx_code (legible)│
                          │  country/region/city FK · tier FK       │
                          │  domain · registry_id · geo_method/conf │
                          │  coverage_state · recipe_ref            │
                          └───────────────┬───────────────────────┘
                                          │
          ┌───────────────┬──────────────┼───────────────┬──────────────────┐
          ▼               ▼              ▼               ▼                  ▼
   entity_xref      entity_tier   entity_recipe   coverage_ledger    entity_geo_history
   (crosswalk a    (taxonomia    (indice PG de    v2 (por entity,    (auditoria de
    las 4 IDs       de tiers)     configs/*.json)  agregable)         re-geolocalizacion)
    existentes)
          │
          ▼ (sin tocar las tablas existentes — solo apuntar a ellas)
   entities · source_entities · dealers · discovery_candidates · coverage_ledger(v1)
```

Principio rector: **la capa canonica APUNTA a lo existente, no lo reemplaza.** Cero `DROP` de tablas vivas. `entity` es la nueva fuente de verdad de identidad+geografia+tier; `entity_xref` la reconcilia con las 4 identidades legacy via FKs `ON DELETE SET NULL`. Las 18 tablas comerciales que cuelgan de `entities` no se tocan: una entity canonica de tipo DEALER puede enlazar (cuando onboarda) a un `entities.entity_ulid` comercial via `entity_xref`.

---

### 2. Esquemas de datos (DDL objetivo — migraciones reversibles)

#### 2.1 Jerarquia geografica (migr `0006_geo_hierarchy.up.sql`)

```sql
-- Sembradas desde DUMPS oficiales gratuitos (NUNCA APIs). NUTS 2021 + LAU.
CREATE TABLE geo_country (
    country_code   CHAR(2) PRIMARY KEY CHECK (country_code IN ('ES','FR','DE','BE','NL','CH')),
    name_en        TEXT NOT NULL,
    name_local     TEXT NOT NULL,
    nuts0          CHAR(2) NOT NULL,          -- NUTS level 0 == ISO alpha-2 here
    currency       CHAR(3) NOT NULL,          -- EUR / CHF
    lang_primary   CHAR(2) NOT NULL,
    seeded_from    TEXT NOT NULL,             -- 'eurostat_nuts_2021' | 'bfs_2024' ...
    seeded_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE geo_region (
    region_id      TEXT PRIMARY KEY,          -- '{CC}-{NUTS2}' e.g. 'FR-FR10' (Ile-de-France)
    country_code   CHAR(2) NOT NULL REFERENCES geo_country(country_code),
    nuts2          TEXT,                       -- NUTS2 (region/province level harmonised)
    nuts3          TEXT,                       -- NUTS3 (departement / provincia / Kanton group)
    admin_kind     TEXT NOT NULL,             -- 'departement'|'provincia'|'kanton'|'provincie'|'bundesland'|'comunidad'
    code_national  TEXT,                       -- INSEE dept '75' | INE prov '28' | CHE canton 'ZH' | CBS | AGS
    name_en        TEXT NOT NULL,
    name_local     TEXT NOT NULL,
    centroid_lat   NUMERIC(9,6),
    centroid_lng   NUMERIC(9,6),
    geom_ref       TEXT,                       -- path to local NUTS3 shapefile feature id
    seeded_from    TEXT NOT NULL,
    UNIQUE (country_code, code_national)
);
CREATE INDEX idx_geo_region_country ON geo_region (country_code);
CREATE INDEX idx_geo_region_nuts3   ON geo_region (nuts3);

CREATE TABLE geo_city (
    city_id        TEXT PRIMARY KEY,          -- '{CC}-{LAU}' e.g. 'FR-75056' (Paris commune)
    region_id      TEXT NOT NULL REFERENCES geo_region(region_id),
    country_code   CHAR(2) NOT NULL REFERENCES geo_country(country_code),
    lau_code       TEXT NOT NULL,             -- LAU (commune / municipio / Gemeinde / gemeente)
    name_local     TEXT NOT NULL,
    name_norm      TEXT NOT NULL,             -- unaccented lower, for pg_trgm matching
    postcodes      TEXT[] NOT NULL DEFAULT '{}',
    lat            NUMERIC(9,6),
    lng            NUMERIC(9,6),
    h3_res7        TEXT,
    population     INT,
    seeded_from    TEXT NOT NULL,
    UNIQUE (country_code, lau_code)
);
CREATE INDEX idx_geo_city_region    ON geo_city (region_id);
CREATE INDEX idx_geo_city_postcodes ON geo_city USING GIN (postcodes);
CREATE INDEX idx_geo_city_name_trgm ON geo_city USING GIN (name_norm gin_trgm_ops);
CREATE INDEX idx_geo_city_h3        ON geo_city (h3_res7);
```

Fuentes de seed (todas dumps gratis, descargables, sin tope — leccion SIRENE aplicada):
- NUTS 2021 + correspondencia NUTS-LAU: Eurostat (CSV/GISCO shapefiles).
- FR: INSEE COG (communes/departements) + shapefiles ADMIN-EXPRESS.
- ES: INE relacion municipios-provincias + codigos postales.
- DE: Destatis AGS (Gemeindeverzeichnis) + Bundeslaender.
- NL: CBS gemeenten + PC-tabel.
- BE: Statbel/NIS communes + provincias.
- CH: BFS Gemeindeverzeichnis + cantones.

#### 2.2 Taxonomia de tiers unificada (migr `0007_entity_tier.up.sql`)

Unifica los 5 vocabularios fragmentados en UNO. Diseno propio de TIERS (responde al mandato):

```sql
CREATE TABLE entity_tier (
    tier_code      TEXT PRIMARY KEY,          -- estable, usado en cdx_code
    family         TEXT NOT NULL,             -- 'SUPPLY' (fuente de inventario) | 'PLATFORM'
    label          TEXT NOT NULL,
    cdx_letter     CHAR(1) NOT NULL UNIQUE,   -- letra en el CDX-code
    extraction_complexity SMALLINT NOT NULL,  -- 0..3 expected defense tier
    description    TEXT NOT NULL
);
INSERT INTO entity_tier (tier_code, family, label, cdx_letter, extraction_complexity, description) VALUES
 ('PLATFORM_T1','PLATFORM','Portal Tier-1 (anti-bot fuerte)','P',3,'AS24, mobile.de, coches.net, leboncoin — faceted_ssr/render'),
 ('PLATFORM_T2','PLATFORM','Portal Tier-2','Q',2,'autotrack, autolina — paginado/render moderado'),
 ('OEM_LOCATOR','SUPPLY','Concesionario oficial / OEM locator','O',2,'red oficial de marca (BMW STOLO etc.)'),
 ('DEALER_INDEP','SUPPLY','Compraventa independiente','D',1,'el grueso del long-tail, web propia + sitemap/jsonld'),
 ('GARAGE','SUPPLY','Garaje / taller con stock','G',1,'taller que ademas vende ocasion'),
 ('SCRAPYARD','SUPPLY','Desguace / chatarrero','S',1,'piezas + vehiculos para despiece, web minima'),
 ('FLEET','SUPPLY','Flota / renting / leasing','F',2,'devoluciones de flota, gran volumen'),
 ('INSTITUTION','SUPPLY','Institucional / subasta','I',2,'subastas, administracion publica');
```

Cada entidad recibe `tier_code` por el clasificador (`dealer_classifier.py` extendido) usando senales ya capturadas: CMS fingerprint, OEM affiliation (`dealers.brand_affiliation`/`oem_brand_url`), keywords de dominio (desguace/chatarra/casse/sloperij/Verwertung), estimated_listings, registry NACE/SBI/NOGA code.

#### 2.3 Entidad canonica + CDX-code (migr `0008_entity_canonical.up.sql`)

```sql
CREATE TABLE entity (
    entity_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cdx_code         TEXT NOT NULL UNIQUE,     -- 'CDX-FR-75-D0042' (inmutable)
    -- identidad de la entidad fisica
    canonical_name   TEXT NOT NULL,
    domain           TEXT,                     -- registered domain (su web)
    registry_id      TEXT,                     -- SIRET/KBO/CHE/AGS ref
    vat_id           TEXT,
    -- jerarquia institucional
    country_code     CHAR(2) NOT NULL REFERENCES geo_country(country_code),
    region_id        TEXT REFERENCES geo_region(region_id),
    city_id          TEXT REFERENCES geo_city(city_id),
    lat              NUMERIC(9,6),
    lng              NUMERIC(9,6),
    h3_res7          TEXT,
    -- como se resolvio la geo (trazabilidad)
    geo_method       TEXT CHECK (geo_method IN
                     ('latlng_poly','postcode_lau','registry_embedded','city_trgm','tld_heuristic','manual')),
    geo_confidence   NUMERIC(3,2) CHECK (geo_confidence BETWEEN 0 AND 1),
    geo_evidence     JSONB NOT NULL DEFAULT '{}'::jsonb,
    needs_geo_review BOOLEAN NOT NULL DEFAULT FALSE,
    -- clasificacion
    tier_code        TEXT REFERENCES entity_tier(tier_code),
    tier_confidence  NUMERIC(3,2),
    -- ciclo de vida de cobertura (resumen; el detalle en coverage_ledger v2)
    coverage_state   TEXT NOT NULL DEFAULT 'discovered' CHECK (coverage_state IN
                     ('discovered','resolved','recipe_proven','caged','verified','live','degraded','dead')),
    recipe_ref       TEXT,                     -- 'configs/dealers/<domain>.json' o portal
    -- linaje
    discovery_sources TEXT[] NOT NULL DEFAULT '{}',
    first_seen       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- scope guard (mismo invariante que el resto del store)
    CONSTRAINT chk_entity_scope CHECK (
        country_code IN ('ES','FR','DE','BE','NL','CH')
        AND (domain IS NULL OR lower(domain) !~ '\.(it|at|pt|pl)$'))
);
CREATE UNIQUE INDEX ux_entity_domain ON entity (domain) WHERE domain IS NOT NULL;
CREATE INDEX idx_entity_region  ON entity (region_id);
CREATE INDEX idx_entity_city    ON entity (city_id);
CREATE INDEX idx_entity_tier    ON entity (tier_code);
CREATE INDEX idx_entity_cov     ON entity (coverage_state);
CREATE INDEX idx_entity_review  ON entity (needs_geo_review) WHERE needs_geo_review;
CREATE INDEX idx_entity_name_trgm ON entity USING GIN (canonical_name gin_trgm_ops);

-- CDX-code generator: secuencia por bucket (country,region,tier) + advisory lock.
CREATE TABLE cdx_sequence (
    bucket  TEXT PRIMARY KEY,   -- '{CC}|{REGcode}|{cdx_letter}'
    next_n  INT  NOT NULL DEFAULT 1
);
CREATE OR REPLACE FUNCTION assign_cdx_code(p_cc CHAR(2), p_regcode TEXT, p_letter CHAR(1))
RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE n INT; bucket TEXT;
BEGIN
  bucket := p_cc||'|'||coalesce(p_regcode,'00')||'|'||p_letter;
  PERFORM pg_advisory_xact_lock(hashtext(bucket));
  INSERT INTO cdx_sequence(bucket,next_n) VALUES (bucket,2)
    ON CONFLICT (bucket) DO UPDATE SET next_n = cdx_sequence.next_n + 1
    RETURNING next_n - 1 INTO n;
  RETURN 'CDX-'||p_cc||'-'||coalesce(p_regcode,'00')||'-'||p_letter||lpad(n::text,4,'0');
END $$;
```

CDX-code = `CDX-{CC}-{REGcode}-{LETTER}{NNNN}`. Legible para acuerdos legales/soporte. Inmutable: si la entidad se re-geolocaliza, el codigo se conserva y el movimiento queda en `entity_geo_history` (la legibilidad es etiqueta, la identidad es la cadena). REGcode = `geo_region.code_national` (dept FR, provincia ES, canton CH...).

#### 2.4 Crosswalk a las 4 identidades legacy (migr `0009_entity_xref.up.sql`)

```sql
CREATE TABLE entity_xref (
    entity_id        UUID NOT NULL REFERENCES entity(entity_id) ON DELETE CASCADE,
    legacy_kind      TEXT NOT NULL CHECK (legacy_kind IN
                     ('tenant_entity','source_entity','dealer_row','discovery_candidate','coverage_domain')),
    legacy_id        TEXT NOT NULL,           -- entity_ulid | se_ulid | dealers.id::text | dc.id::text | domain
    confidence       NUMERIC(3,2) NOT NULL DEFAULT 1.0,
    matched_by       TEXT NOT NULL,           -- 'domain_exact'|'registry_id'|'fellegi_sunter'|'manual'
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (legacy_kind, legacy_id)
);
CREATE INDEX idx_xref_entity ON entity_xref (entity_id);
```

Reconciliacion automatica reutilizando `entity_matches` (Fellegi-Sunter) + match exacto por `domain`/`registry_id`. Una entity puede tener N xrefs (la misma entidad fisica vista como discovery_candidate + dealers row + coverage_ledger domain, y opcionalmente un tenant comercial cuando onboarda).

#### 2.5 Indice PG de recetas + provenance (migr `0010_entity_recipe.up.sql`)

El archivo JSON (`configs/*.json`) SIGUE siendo la fuente de verdad portable git-trackeada. Esto es solo un INDICE para queries y para enriquecer provenance.

```sql
CREATE TABLE entity_recipe (
    entity_id        UUID PRIMARY KEY REFERENCES entity(entity_id) ON DELETE CASCADE,
    cdx_code         TEXT NOT NULL,
    config_path      TEXT NOT NULL,           -- 'configs/dealers/dacia-calais.fr.json'
    kind             TEXT NOT NULL CHECK (kind IN ('portal','dealer')),
    strategy         TEXT NOT NULL,           -- mirror of ExtractionConfig.strategy
    version          INT  NOT NULL,
    content_sha256   TEXT NOT NULL,           -- hash of the file (detect drift vs index)
    expected_min_volume INT,
    last_proven_at   TIMESTAMPTZ,
    proven_volume    INT,
    declared_total   INT,                     -- dealer's own declared count (close_entity cross-check)
    coverage_vs_declared NUMERIC(4,3),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_recipe_strategy ON entity_recipe (strategy);
```

Extension del JSON de receta (bloque `provenance` anadido a `scrapers/portals/config.py` ExtractionConfig — campo nuevo, retrocompatible via `_only()`):
```json
{
  "source_key": "dacia-calais.fr",
  "entity_code": "CDX-FR-62-D0117",
  "country": "FR", "strategy": "sitemap_listing", "version": 2,
  "endpoints": { "...": "..." },
  "extraction": { "...": "..." },
  "drift_baseline": { "expected_min_volume": 230, "...": "..." },
  "provenance": {
    "discovered_by": ["registry:fr_sirene","osm"],
    "resolver_method": "sitemap",
    "last_proven_at": "2026-06-08T12:00:00Z",
    "proven_volume": 230,
    "declared_total": 230,
    "coverage_vs_declared": 1.0,
    "antidetect": "curl_cffi",
    "notes": "PDP regex /stock/.*-fr-fr.htm verified E2E"
  }
}
```
Portabilidad a Codex: el JSON es autocontenido (que estrategia, que endpoints, que pasos, que volumen probado, como se verifico). Un agente externo puede ejecutar la receta sin leer el codigo.

#### 2.6 coverage_ledger v2 agregable + historico geo (migr `0011_coverage_v2.up.sql`)

```sql
-- v1 (PK domain) se conserva intacto; v2 lo enlaza a la jerarquia.
CREATE TABLE coverage_ledger_v2 (
    entity_id        UUID PRIMARY KEY REFERENCES entity(entity_id) ON DELETE CASCADE,
    cdx_code         TEXT NOT NULL,
    country_code     CHAR(2) NOT NULL,
    region_id        TEXT,
    city_id          TEXT,
    tier_code        TEXT,
    status           TEXT NOT NULL CHECK (status IN
                     ('yielded','no_inventory','no_web','error','timeout','not_attempted')),
    inventory_count  INT NOT NULL DEFAULT 0,   -- verified vehicles (pre-purge)
    declared_total   INT,
    coverage_ratio   NUMERIC(4,3),             -- inventory_count / declared_total
    drift_ok         BOOLEAN,
    recipe_proven    BOOLEAN NOT NULL DEFAULT FALSE,
    verified_at      TIMESTAMPTZ,
    last_delta_at    TIMESTAMPTZ
);
CREATE INDEX idx_cov2_region ON coverage_ledger_v2 (region_id, status);
CREATE INDEX idx_cov2_tier   ON coverage_ledger_v2 (tier_code, status);

-- Rollup agregable por provincia/tier (vista materializada, refresco por cron).
CREATE MATERIALIZED VIEW coverage_rollup AS
SELECT c.country_code, c.region_id, r.name_local AS region_name, c.tier_code,
       count(*) FILTER (WHERE c.status <> 'not_attempted')                 AS attempted,
       count(*) FILTER (WHERE c.status = 'yielded')                        AS yielded,
       count(*) FILTER (WHERE c.recipe_proven)                             AS recipe_proven,
       count(*)                                                            AS known_entities,
       sum(c.inventory_count)                                             AS caged_inventory,
       round(100.0 * count(*) FILTER (WHERE c.status='yielded')
             / nullif(count(*),0), 2)                                      AS pct_extraction_closed
FROM coverage_ledger_v2 c
JOIN geo_region r ON r.region_id = c.region_id
GROUP BY c.country_code, c.region_id, r.name_local, c.tier_code;
CREATE UNIQUE INDEX ux_cov_rollup ON coverage_rollup (country_code, region_id, tier_code);

-- Auditoria de re-geolocalizacion (cdx_code es inmutable; movimientos quedan aqui).
CREATE TABLE entity_geo_history (
    id           BIGSERIAL PRIMARY KEY,
    entity_id    UUID NOT NULL REFERENCES entity(entity_id) ON DELETE CASCADE,
    old_region   TEXT, old_city TEXT, new_region TEXT, new_city TEXT,
    reason       TEXT, geo_method TEXT, geo_confidence NUMERIC(3,2),
    changed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Dos KPIs HONESTOS (el mandato exige verificar completitud, no solo conteos):
- **Cobertura de extraccion** = `pct_extraction_closed` (de las entidades conocidas, cuantas tienen inventario enjaulado+verificado).
- **Cobertura de descubrimiento** = entidades conocidas / estimacion Lincoln-Petersen de entidades totales (cruza `source_overlap_matrix`, ya existente). Responde "conocemos todos los dealers de esta provincia?".

#### 2.7 Vista de inventario por entidad con geo (migr `0012_entity_inventory_geo.up.sql`)

Extiende la `entity_inventory` VIEW existente (migr 0001) anadiendo la dimension geografica via `entity_xref` -> `entity` -> jerarquia, para servir el API per-entidad y agregaciones provinciales sin copiar datos.

---

### 3. Estructura de carpetas/configs en el repo (grado institucional)

```
cardex-integration/
├── configs/
│   ├── portals/        (EXISTE — recetas curadas, git-tracked)
│   ├── dealers/        (EXISTE — recetas auto-generadas)
│   └── geo/            (NUEVO — seeds y crosswalks portables)
│       ├── seeds/      nuts_2021.csv, lau_2021.csv, fr_insee_cog.csv, es_ine.csv,
│       │               de_ags.csv, nl_cbs.csv, be_statbel.csv, ch_bfs.csv
│       ├── shapefiles/ nuts3/, lau/  (GISCO/ADMIN-EXPRESS, para punto-en-poligono)
│       └── postcode_lau/  fr.csv, es.csv, de.csv, nl.csv, be.csv, ch.csv
├── scripts/
│   ├── migrations/     (EXISTE — 0006..0012 nuevas, reversibles, con .down.sql)
│   ├── geo_seed.py     (NUEVO — carga geo_* desde configs/geo/seeds via COPY)
│   ├── entity_backfill.py  (NUEVO — puebla entity + entity_xref desde las 4 fuentes)
│   ├── geo_resolve.py  (NUEVO — cascada E2 de resolucion geografica)
│   ├── cdx_assign.py   (NUEVO — asigna CDX-code a entidades sin codigo)
│   ├── grind_coverage.py   (EXISTE — se adapta para escribir coverage_ledger_v2)
│   ├── close_entity.py     (EXISTE — emite entity_recipe + provenance)
│   └── verify_discovery.py (EXISTE — base del verificador adversarial geo)
└── docs/
    ├── adr/            (EXISTE — anadir 0009-modelo-institucional-canonico.md)
    └── research/       (EXISTE — geo-<pais>.md cuando E6 investiga muros)
```

---

### 4. Workflows + Agentes del subsistema

Orquestacion segun `~/.claude/rules/common/agents.md` (lider Opus, workers el modelo justo; verificacion adversarial co-igual).

**WF-1 Geo-Seed** (una vez, idempotente). Agente `geo-seeder` (Haiku): descarga dumps, valida columnas, `COPY` a geo_country/region/city. Criterio de calidad: conteos por pais cuadran con totales oficiales publicados (FR ~34.945 communes, etc.). Verificador `geo-seed-auditor` (Sonnet): re-cuenta por via independiente (suma de communes por departement == total nacional) y comprueba que todo region_id referencia un country valido.

**WF-2 Entity-Reconcile** (backfill + continuo). Agente-lider `entity-orchestrator` (Opus): coordina poblado de `entity` + `entity_xref` desde discovery_candidates/dealers/source_entities/coverage_ledger. Worker `xref-matcher` (Sonnet): aplica match exacto domain/registry_id, luego Fellegi-Sunter (`entity_matches`). Criterio: cero entidad fisica con 2 entity_id (sin duplicados), cero legacy_id huerfano.

**WF-3 Geo-Resolve** (motor E2). Agente `geo-resolver` (Sonnet): cascada 5-niveles (latlng_poly -> postcode_lau -> registry_embedded -> city_trgm -> tld_heuristic), escribe geo_method/confidence/evidence. Worker `poly-indexer` (Haiku): punto-en-poligono contra shapefiles locales. Criterio: >=90% entidades con geo_confidence>=0.6; el resto a `needs_geo_review`, nunca asignacion silenciosa.

**WF-4 Tier-Classify**. Agente `tier-classifier` (Sonnet, extiende `dealer_classifier.py`): asigna tier_code por CMS+OEM+keywords+registry NACE+estimated_listings. Criterio: distribucion plausible (los desguaces no superan a las compraventas; OEM coinciden con brand_affiliation).

**WF-5 CDX-Assign**. Agente `cdx-assigner` (Haiku): llama `assign_cdx_code` por bucket. Criterio: cdx_code UNIQUE, formato valido, inmutabilidad (nunca re-emite para una entity con codigo).

**WF-6 Recipe-Index + Provenance**. Agente `recipe-indexer` (Haiku): tras cada cierre exitoso (grind/close_entity ya existentes), escribe `entity_recipe` con content_sha256 del JSON y enriquece provenance. Criterio: content_sha256 del indice == hash del archivo (cero drift indice/archivo).

**WF-7 Coverage-Rollup**. Agente `coverage-aggregator` (Sonnet): refresca `coverage_rollup`, computa los 2 KPIs honestos cruzando `source_overlap_matrix`/`coverage_matrix`. Emite a `operator_alerts` provincias que retroceden en cobertura.

**Agente-lider orquestador (Opus)** `institutional-lead`: secuencia WF-1..WF-7, mantiene PLAN.md/PROGRESO.md a disco (doctrina: estado no vive solo en contexto), decide re-ejecuciones, y NUNCA cierra con items abiertos sin bloqueo declarado.

**Agente verificador/motivador (Opus)** `adversarial-verifier`: desconfia de TODO output de los workflows; ver seccion 5.

---

### 5. Verificacion adversarial integrada (co-igual, por vias DISTINTAS)

Principio (mandato + `verify_discovery.py` ya existente): un workflow que dice "escribi N" NO es prueba. Se re-deriva la verdad por una via independiente a la que uso la extraccion/poblado.

- **Geo (via independiente):** WF-2/3 asignan geo via lat/lng+postcode. El verificador re-deriva por OTRA via: toma una muestra estratificada por provincia y comprueba `postcode -> LAU` contra el dump nacional Y `nombre-ciudad -> centroide` contra geonames (fuente distinta a la usada). Discrepancia provincia != provincia => flag. Verifica CONTENIDO (la ciudad asignada es coherente con el dominio/telefono/CP), no solo conteos.
- **Completitud de descubrimiento (denominador real):** Lincoln-Petersen sobre `source_overlap_matrix` (ya implementado, Chapman CI): si dos fuentes independientes (SIRENE vs OSM vs CT-logs) capturan poblaciones que solo se solapan al X%, la estimacion del total revela el gap. Una provincia con cobertura "100% de lo conocido" pero N estimado >> conocido => NO esta cerrada. Reutiliza el patron de `verify_discovery.py` (re-fetch independiente del registry, diff exacto de sirens, `--fill` para cerrar el gap).
- **Inventario/Delta (anti-mentira):** ya existe el cross-check de `close_entity.py` (caged vs PDPs vs declared_total del propio sitio). Se eleva: el verificador toma la `declared_total` de una via distinta (numberOfItems JSON-LD vs conteo de paginacion vs sitemap count) y exige concordancia 3-vias antes de marcar `verified`.
- **Recetas (drift):** `entity_recipe.content_sha256` vs hash real del archivo detecta divergencia indice/fuente. `drift_baseline` (ya existe) detecta caida de volumen/campos.
- **Cadencia:** verificacion no es one-shot. `coverage-aggregator` re-corre semanal por provincia; una provincia que retrocede dispara `operator_alerts`.

Regla dura: la PRIMERA respuesta de cualquier workflow se trata como [ASUMIDO] hasta que el verificador la convierte en [VERIFICADO] por via independiente.

---

### 6. Resiliencia, trazabilidad y coste (grado institucional)

- **Resiliencia:** si un dealer/fuente cae, su `entity.coverage_state -> degraded` y `operator_alerts` lo registra; CARDEX no se cae (entidades aisladas, ya es el patron spider/reaper/indexer de ADR-0007). Backfill resumible (como `grind_coverage` via ledger).
- **Trazabilidad:** geo_method/geo_confidence/geo_evidence + entity_geo_history + entity_xref.matched_by + provenance en receta => toda decision es auditable. cdx_code inmutable como ancla de auditoria.
- **Coste:** todo el seed es dump gratis local (cero APIs de pago, leccion SIRENE). Punto-en-poligono local (shapely/GDAL o PostGIS opcional) evita Nominatim a escala. Clasificacion de tier por reglas+CMS fingerprint (sin LLM); LLM local (Qwen, ya hay ADR-0002 de clasificador fiscal Qwen) solo para casos ambiguos de tier/desambiguacion de ciudad. Proxies de pago: NO necesarios para este subsistema (es data modeling + lookups locales).

---

### 7. Criterios de aceptacion medibles

1. **Jerarquia completa:** geo_country (6), geo_region (todas las NUTS3/provincias de los 6), geo_city (todas las LAU). Conteo por pais cuadra con totales oficiales (+-0.5%). [VERIFICADO por WF-1 auditor]
2. **Identidad unica:** 100% de las entidades fisicas tienen exactamente UN entity_id y UN cdx_code; cero duplicados (misma entidad con 2 codigos); cero legacy_id huerfano en entity_xref. Las 18 tablas comerciales siguen funcionando (cero FK rota).
3. **Geo asignada:** >=90% de entidades con geo_confidence>=0.6; 100% del resto en needs_geo_review (cero asignacion silenciosa bajo umbral).
4. **CDX-code:** UNIQUE, formato `CDX-{CC}-{REG}-{L}{NNNN}` valido, inmutable bajo re-geolocalizacion (movimiento en entity_geo_history).
5. **Cobertura agregable:** coverage_rollup devuelve % por (pais,provincia,tier) y los 2 KPIs honestos; el de descubrimiento cruza Lincoln-Petersen.
6. **Recetas portables:** 100% de entidades con `coverage_state>=recipe_proven` tienen archivo JSON con bloque provenance + entity_code, y entity_recipe.content_sha256 == hash del archivo.
7. **Verificacion adversarial:** muestra estratificada por provincia verificada por via independiente con discrepancia <2%; gaps detectados re-encolados (no silenciados).
8. **Reversibilidad:** cada migracion 0006..0012 tiene su .down.sql probado (rollback limpio), al estilo de las 0001..0005 existentes.

## Decisiones clave
- La capa institucional canonica (entity/geo_*) APUNTA a lo existente via entity_xref; NO reemplaza ni dropea ninguna de las tablas vivas (entities con 18 dependientes, source_entities, dealers, coverage_ledger). Cero rotura de FKs comerciales.
- cdx_code legible e INMUTABLE (CDX-FR-75-D0042) como identidad institucional; la geografia legible es etiqueta — los movimientos de re-geolocalizacion se auditan en entity_geo_history, el codigo no cambia. Identidad tecnica = entity_id UUID.
- Jerarquia normalizada a estandares oficiales: NUTS 2021 (region) + LAU (ciudad), sembrada desde DUMPS gratis descargables (Eurostat/INSEE/INE/Destatis/CBS/Statbel/BFS), NUNCA APIs rate-limitadas — aplicando la leccion dolorosa de SIRENE ya registrada en memoria del proyecto.
- Reutilizar el sistema de recetas YA existente (scrapers/portals/config.py, configs/portals|dealers/*.json, emit() create-if-absent) en vez de reinventarlo; solo extender con bloque provenance + entity_code para portabilidad total a Codex, y un indice PG espejo (entity_recipe) para queries.
- coverage_ledger v1 (PK domain) se conserva intacto; v2 (PK entity_id, con region/tier) lo enlaza a la jerarquia y habilita agregacion provincial + 2 KPIs honestos (cobertura-de-extraccion vs cobertura-de-descubrimiento via Lincoln-Petersen ya implementado en source_overlap_matrix).
- Taxonomia de tiers PROPIA y unificada (8 tier_code: PLATFORM_T1/T2, OEM_LOCATOR, DEALER_INDEP, GARAGE, SCRAPYARD, FLEET, INSTITUTION) que consolida los 5 vocabularios fragmentados existentes; cada tier mapea a una cdx_letter y a una complejidad de extraccion esperada.
- Resolucion geografica como cascada de 5 fallbacks rankeados por confianza con evidencia trazable y umbral 0.6 -> needs_geo_review; nunca asignacion geografica silenciosa bajo umbral (alineado con la doctrina anti-alucinacion).
- Migraciones reversibles 0006..0012 con .down.sql, NOT VALID + backfill por fases para no bloquear las ~436K filas, reutilizando el patron exacto de las migraciones 0001..0005 ya en el repo, mas el invariante de scope de 6 paises (CHECK + trigger ENABLE ALWAYS).

## Riesgos
- Backfill de entity sobre ~112K discovery_candidates + ~49K dealers + source_entities puede producir duplicados si el matching domain/registry_id/Fellegi-Sunter no esta bien calibrado; mitigar con la fase de verificacion adversarial ANTES de asignar cdx_code (un codigo mal asignado a un duplicado es dificil de revertir por la inmutabilidad).
- Asignacion geografica erronea (geo_method=tld_heuristic, confidence baja) contaminando coverage_rollup si se cuenta como resuelta; mitigar con el gate needs_geo_review estricto y excluir del rollup las entidades bajo umbral.
- Drift indice-vs-archivo de recetas: si un agente edita configs/*.json sin actualizar entity_recipe.content_sha256, los KPIs de 'recipe_proven' mienten; mitigar con un check periodico que recomputa el hash (mismo espiritu que el incidente del trigger de scope sobreescrito, migr 0005).
- Coste de mantener las 4 identidades legacy + la canonica: si un proceso legacy sigue insertando en dealers/discovery_candidates sin pasar por entity, la capa canonica se desincroniza; mitigar con triggers de propagacion o un reconcile continuo (WF-2 en modo daemon).
- Las migraciones tocan tablas grandes y vivas (vehicle_index 436K, vehicles): un ADD CONSTRAINT VALIDATE mal hecho bloquea produccion; mitigar con NOT VALID + VALIDATE en ventana, exactamente como hizo la migr 0001.
- Seeds geograficos desactualizados (fusiones de communes FR, cambios de Gemeinde DE) degradan el match con el tiempo; mitigar con seeded_from + seeded_at y un refresco anual versionado en configs/geo/seeds.