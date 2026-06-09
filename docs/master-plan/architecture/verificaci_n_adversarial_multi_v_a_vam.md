# Verificación Adversarial Multi-Vía (VAM) — el sistema anti-mentiras de CARDEX

## Resumen
CARDEX ya tiene los átomos de verificación adversarial dispersos y probados, pero NO tiene el sistema que los compone, los orquesta con agentes que se retan entre sí, y emite veredictos trazables que bloquean datos no corroborados. Lo que existe (todo [VERIFICADO] leyendo el código): scrapers/intelligence/count_verify.py (cross_check + CountVerdict, tolerancia, convergencia — el gate "no vende mentiras" que cazó la mentira dacia 17-vs-229), scrapers/discovery/domain_resolution/validate.py (confirms_dealer: gate anti-falso-positivo strong/weak/non-dealer), scripts/verify_discovery.py (re-deriva la verdad del registro fuente e independientemente mide completeness=in_db/source con veredicto COMPLETE/NEAR/GAP), scrapers/discovery/domain_resolution/revalidate.py (re-derivación independiente que purga FPs sin destruir en fallo transitorio), scrapers/intelligence/poison.py (detección de honeypot AI-Labyrinth, 7 señales), scrapers/intelligence/drift_gate.py + schema.py (drift VOLUME/FIELD/SCHEMA), scrapers/llm/decisions.py (segunda opinión LLM local Ollama qwen2.5:3b SOLO en banda ambigua, fail-open), scrapers/pipeline/quality.py (4 gates C3). Y crítico: el schema PG (scripts/init-pg.sql) YA define source_overlap_matrix (Lincoln-Petersen/Chapman captura-recaptura con IC) y coverage_matrix (fleet-census expected vs observed) — pero NINGÚN worker los puebla (verificado: solo init-pg.sql los menciona). Esa es la espina dorsal estadística dormida que VAM despierta. VAM es la capa que: (1) define un contrato de veredicto único y trazable (tabla verification_verdicts append-only), (2) compone N métodos ORTOGONALES a la extracción (re-derivación de registro, captura-recaptura entre fuentes, muestreo adversarial live, conteo independiente por sitemap/JSON-LD, anti-over-dedup), (3) exige QUÓRUM de verificadores con lentes distintas antes de confiar un número O un contenido, (4) corre un agente-LÍDER orquestador y un agente VERIFICADOR-RETADOR que, cuando un workflow no llega al estándar, NO acepta el "no se puede": dispara fallbacks rankeados y un agente de INVESTIGACIÓN que busca en GitHub/Reddit/foros nuevas vías y herramientas open-source, y (5) instala GATES que bloquean la publicación de cualquier dato sin corroboración independiente. Robustez sobre velocidad, coste-eficiente (heurística determinista primero, LLM local solo en duda, proxies de pago jamás para verificar), grado institucional.

## Estrategias
- **E1 — Re-derivación independiente desde la fuente-de-verdad (registro/sitemap)**: Para discovery: re-enumerar el universo desde el registro gubernamental por DUMP descargable (no API rate-limitada) — SIRENE opendatasoft ~505k FR, KBO BE, Zefix CH, OSM Overpass — y medir completeness = in_db/source por slice (depto/provincia/código-actividad). Extiende scripts/verify_discovery.py (hoy solo FR via recherche-entreprises) a los 6 países leyendo una vía distinta de la que usó la extracción: si la extracción usó la API, la verificación usa el dump, y viceversa. Para inventario: re-derivar el conteo de una entidad por su PROPIO sitemap PDP (count_verify.count_pdp_in_sitemap) y por su JSON-LD numberOfItems (count_verify.count_jsonld_total), ambos independientes del pipeline discover->seam. Gate por count_verify.cross_check (convergencia <=tolerancia).
- **E2 — Captura-recaptura entre fuentes ortogonales (Lincoln-Petersen/Chapman)**: Despertar source_overlap_matrix (ya en el schema, sin worker). Para un país, tomar 2+ fuentes INDEPENDIENTES del mismo universo (p.ej. SIRENE-registro vs OSM-shop=car vs portal-directory AS24 vs CT-logs de dominios). Calcular overlap M, only_A, only_B; estimar el universo real N por Chapman: N=((nA+1)(nB+1)/(M+1))-1 con varianza e IC. Si el agente trae 900k dealers ES y Chapman estima 600k±40k, el número es inflado (over-count/duplicados); si trae 300k y Chapman estima 600k, falta cobertura (under-count). Esto confirma '~esos, ni más ni menos' por 2-3 fuentes que NO comparten método de extracción. Implementar scrapers/intelligence/capture_recapture.py (puro: pares de sets->Chapman) + scripts/run_overlap_audit.py (escribe source_overlap_matrix).
- **E3 — Muestreo adversarial live (correctness + frescura + no-inventado)**: Tomar una muestra ALEATORIA estratificada (por país×fuente×tier) de N registros ya persistidos y RE-VISITAR la URL fuente en vivo por una identidad/fetcher DISTINTO al de la extracción, comparando campo a campo (precio, año, km, fotos, estado activo/vendido). Extiende scrapers/discovery/quality_sample.py (hoy solo fill-rate de Meili) a verificación contra el live. Cada divergencia clasifica: STALE (frescura), WRONG_FIELD (correctness), HALLUCINATED (la URL ya no existe o nunca tuvo ese coche → dato inventado), OK. Tamaño de muestra por intervalo de Wilson para una cota de error <=2% con 95% confianza. El poison.detect corre sobre el HTML re-visitado para no validar contra un honeypot.
- **E4 — Detección de over-dedup / under-count en el fingerprint**: El riesgo [VERIFICADO en rich_consumer.compute_fingerprint]: VIN presente -> fp=vin:vin:color:mileage (dos coches físicos con mismo VIN+color+km colapsan; y un VIN repetido entre plataformas es match cross-source legítimo, no duplicado a borrar); VIN ausente -> fp=url exacta (misma URL con querystring distinto = 2 filas falsas; mismo coche en 2 URLs = 0 dedup). VAM audita: (a) over-dedup = contar cuántos pares colapsados por fp comparten fingerprint pero difieren en source_url/plataforma (deberían ser entity_matches, no un solo registro), (b) under-count = clustering de quasi-duplicados por (make,model,year,price,mileage,phash-de-foto) que el fp NO unió. phash de fotos (imagehash OSS) como vía ortogonal al texto. Implementar scrapers/intelligence/dedup_audit.py.
- **E5 — Censo macro / sanity por fleet-census (coverage_matrix)**: Despertar coverage_matrix (ya en schema). Para país×marca×año: expected_for_sale = fleet_count × turnover_rate (de fleet_census: KBA DE, RDW NL, DGT ES, etc.) y coverage = observed/expected. Una cobertura >1.0 (más coches a la venta que el parque rotando) = over-count/inventado; <<esperado = hueco. Es el sanity-check macro de último recurso que ningún agente puede falsear porque la fuente (estadística gov de matriculaciones) es totalmente externa a CARDEX.
- **E6 — Quórum de verificadores + agente retador (cuando E1-E5 no convergen)**: Ningún número/contenido se marca TRUSTWORTHY con una sola vía. El agente-LÍDER exige que >=2 métodos ortogonales converjan (quórum). Si no convergen, el agente VERIFICADOR-RETADOR no acepta 'no se puede': (1) re-ejecuta con parámetros distintos (otra fuente, otra ventana, sort estable + multi-pasada como en run_giant_scraping), (2) escala a un método más caro (E3 muestreo, E5 censo), (3) dispara el agente de INVESTIGACIÓN (GitHub/Reddit/foros/Exa) para hallar una NUEVA vía ortogonal o herramienta open-source (Camoufox, imagehash, librerías de record-linkage como dedupe/splink) y la integra como nuevo verificador. El veredicto final es DISPUTED hasta que el quórum se alcance; DISPUTED bloquea la publicación.

## Spec completa
# Subsistema VAM — Verificación Adversarial Multi-Vía (anti-mentiras de CARDEX)

> Doctrina encarnada: *CARDEX no vende mentiras*. Ningún número y ningún contenido se confía por
> la primera respuesta de ningún agente o workflow. Todo se corrobora por vías INDEPENDIENTES de las
> que produjeron el dato. La invención es el único fallo imperdonable; VAM es el sistema que la caza.

---

## 0. Estado real verificado (reconocimiento, no greenfield)

Leído directamente del repo `C:\Users\elias\projects\cardex-integration` ([VERIFICADO]):

| Pieza existente | Archivo | Qué aporta a VAM |
|---|---|---|
| `cross_check` + `CountVerdict` | `scrapers/intelligence/count_verify.py` | Gate de convergencia de conteos (tolerancia, `trustworthy`, `max_divergence`). Cazó la mentira dacia 17-vs-229. **Núcleo del veredicto de NÚMERO.** |
| `count_pdp_in_sitemap`, `count_jsonld_total` | id. | Dos vías independientes de conteo (sitemap PDP, JSON-LD `numberOfItems`). |
| `confirms_dealer` / `confirms_automotive` | `scrapers/discovery/domain_resolution/validate.py` | Gate anti-FP de discovery (strong/weak/non-dealer, whole-word, anti-namesake). **Núcleo del veredicto de IDENTIDAD.** |
| `verify_fr` (completeness) | `scripts/verify_discovery.py` | Re-deriva el universo del registro fuente e independientemente mide `completeness=in_db/source`, veredicto COMPLETE/NEAR/GAP, con `--fill` para cerrar el hueco. **Plantilla de E1.** |
| `revalidate` (purga FP) | `scrapers/discovery/domain_resolution/revalidate.py` | Re-derivación con gate más estricto que purga FPs y **nunca destruye en fallo transitorio**. **Patrón de re-derivación segura.** |
| `poison.detect` (D3) | `scrapers/intelligence/poison.py` | 7 señales de honeypot AI-Labyrinth. **Evita verificar contra contenido envenenado.** |
| `drift_gate.evaluate` + `schema.*` | `scrapers/intelligence/drift_gate.py`, `schema.py` | Drift VOLUME/FIELD/SCHEMA por origen, baseline en `schema_registry`. **Detecta ruptura silenciosa.** |
| `classify_is_car_dealer` (LLM) | `scrapers/llm/decisions.py` | Segunda opinión LLM local (Ollama `qwen2.5:3b`) SOLO en banda ambigua, fail-open, modos economy/precision/off. **El "retador" determinista→LLM ya existe a micro-escala.** |
| 4 gates C3 | `scrapers/pipeline/quality.py` | structural / poison / cross-source-VIN / staleness. |
| `compute_fingerprint` | `scrapers/rich_consumer.py` | `vin:{vin}:{color}:{km}` o `url:{url}`. **Superficie del riesgo over-dedup/under-count.** |
| `source_overlap_matrix` (Lincoln-Petersen/Chapman, IC) | `scripts/init-pg.sql` | **DEFINIDA, sin worker que la pueble.** Espina dorsal de E2. |
| `coverage_matrix` (fleet×turnover vs observed) | id. | **DEFINIDA, sin worker.** Sanity macro E5. |
| `entity_matches` (Fellegi-Sunter) | id. + `scrapers/entity_resolver.py` | Dedup cross-source VIN exacto (V12). Base para anti-over-dedup E4. |
| `fleet_census` | `scripts/init-pg.sql` | Censo gov de matriculaciones por país/marca/año. Fuente externa de E5. |

**Stores reales** ([VERIFICADO], MEMORY confirma docs stale): **PostgreSQL 16** (`discovery_candidates`,
`vehicles`, `vehicle_index`, `vehicle_events`, `entity_matches`, `source_overlap_matrix`,
`coverage_matrix`, `fleet_census`, `audit_log`) + **Redis Streams** (delta) + **SQLite** `engine.db`
(estado de scraping: identities, proxy_health, work_queue, dlq, **`schema_registry`**). `ARCHITECTURE.md`
describe una arquitectura Go/SQLite OBSOLETA — se ignora; manda el código Python observado.

**Conclusión del reconocimiento:** VAM no se inventa de cero. Se construye COMPONIENDO estos átomos,
**despertando** `source_overlap_matrix` y `coverage_matrix`, **endureciendo** el contrato de veredicto, y
**orquestando** todo con agentes adversariales. Anti-atajo: no se reescribe lo probado; se cablea y se eleva.

---

## 1. Principio de diseño: ORTOGONALIDAD obligatoria

Un verificador solo cuenta como vía independiente si **no comparte el camino de fallo** con la extracción
que valida. Regla operativa (la "matriz de ortogonalidad"):

- Si la extracción usó **API del registro** → la verificación usa el **DUMP descargable** (y viceversa).
- Si la extracción contó por **paginación del listado** → la verificación cuenta por **sitemap PDP** y/o **JSON-LD total**.
- Si la extracción identificó al dealer por **web-search** → la verificación lo confirma por **registro gov** y por **OSM**.
- Si la extracción dedupó por **fingerprint de texto** → la verificación detecta huecos por **phash de foto** y clustering de atributos.
- Si la extracción corrió por **fetcher/identidad X** → el muestreo live corre por **fetcher/identidad Y**.

Cada veredicto registra QUÉ métodos se usaron y prueba que son ortogonales al productor (campo
`producer_path` vs `verifier_paths`). Un "quórum" de dos métodos del MISMO camino NO es quórum.

---

## 2. Arquitectura de componentes

```
                        ┌──────────────────────────────────────────────┐
                        │      AGENTE-LÍDER  (verification-orchestrator) │
                        │  descompone objetivo → plan multi-vía → quórum │
                        └───────────────┬──────────────────────────────┘
            ┌──────────────────┬────────┼────────────┬──────────────────┐
            ▼                  ▼         ▼            ▼                  ▼
   ┌────────────────┐ ┌──────────────┐ ┌──────────┐ ┌─────────────┐ ┌──────────────┐
   │ E1 re-derive   │ │ E2 capture-  │ │ E3 live  │ │ E4 dedup-   │ │ E5 census    │
   │ (registry/     │ │ recapture    │ │ sampling │ │ audit       │ │ sanity       │
   │  sitemap/jsonld│ │ (overlap mtx)│ │ (content)│ │ (over/under)│ │ (coverage)   │
   └───────┬────────┘ └──────┬───────┘ └────┬─────┘ └──────┬──────┘ └──────┬───────┘
           └─────────────────┴──────────────┴──────────────┴───────────────┘
                                            │  veredictos por método
                                            ▼
                        ┌──────────────────────────────────────────────┐
                        │      QUÓRUM ENGINE  (scrapers/intelligence/    │
                        │      verdict.py)  → VerificationVerdict        │
                        │  TRUSTWORTHY · DISPUTED · GAP · OVERCOUNT ·    │
                        │  STALE · HALLUCINATED · POISONED · UNVERIFIED  │
                        └───────────────┬──────────────────────────────┘
              no-convergencia / bajo estándar │                 │ convergencia
                                              ▼                 ▼
              ┌──────────────────────────────────────┐  ┌───────────────────────┐
              │ AGENTE VERIFICADOR-RETADOR            │  │ GATE de publicación   │
              │ (verification-challenger)            │  │ (publish_gate)        │
              │  reta: otra vía, otro parámetro,     │  │ DISPUTED → BLOQUEA     │
              │  escala método, dispara investigación│  │ persiste verdict +    │
              └───────────────┬──────────────────────┘  │ audit_log (trazable)  │
                              ▼                          └───────────────────────┘
              ┌──────────────────────────────────────┐
              │ AGENTE INVESTIGACIÓN                  │
              │ (research-scout)                     │
              │  GitHub/Reddit/foros/Exa → nueva vía │
              │  u herramienta OSS (Camoufox, splink,│
              │  imagehash, dedupe) → la integra     │
              └──────────────────────────────────────┘
```

Todos los verificadores E1-E5 son **funciones puras + shell async** (mismo estilo que `count_verify`,
`poison`, `drift_gate`): testables sin red. La red (fetch/dump/query) se inyecta. Esto mantiene el
determinismo y el grado institucional.

---

## 3. Esquema de datos (nuevo + despertar de existente)

### 3.1 `verification_verdicts` (NUEVO, append-only, PG) — el registro trazable

```sql
CREATE TABLE verification_verdicts (
    verdict_ulid     TEXT PRIMARY KEY,
    target_type      TEXT NOT NULL CHECK (target_type IN
                       ('DISCOVERY_UNIVERSE','ENTITY_INVENTORY','SAMPLE_CONTENT',
                        'DEDUP_INTEGRITY','COVERAGE_SEGMENT')),
    target_key       TEXT NOT NULL,        -- p.ej. 'ES' | 'dacia-meaux.fr:FR' | 'autoscout24.de:DE'
    claim_kind       TEXT NOT NULL CHECK (claim_kind IN ('COUNT','COMPLETENESS','CORRECTNESS','FRESHNESS','UNIQUENESS')),
    claimed_value    NUMERIC,              -- lo que afirmó el productor (p.ej. 900000 dealers)
    producer_path    TEXT NOT NULL,        -- método que PRODUJO el dato (para probar ortogonalidad)
    verifier_paths   JSONB NOT NULL,       -- [{method, value, divergence, orthogonal:true}]
    quorum_required  SMALLINT NOT NULL DEFAULT 2,
    quorum_reached   SMALLINT NOT NULL,
    verdict          TEXT NOT NULL CHECK (verdict IN
                       ('TRUSTWORTHY','DISPUTED','GAP','OVERCOUNT','STALE',
                        'HALLUCINATED','POISONED','UNVERIFIED')),
    confidence       NUMERIC(4,3) CHECK (confidence BETWEEN 0 AND 1),
    estimate_n       NUMERIC,              -- universo estimado (Chapman) cuando aplique
    ci_lower         NUMERIC,
    ci_upper         NUMERIC,
    evidence         JSONB NOT NULL DEFAULT '{}',  -- contraejemplos, sirens faltantes, phash colisiones
    challenger_runs  SMALLINT NOT NULL DEFAULT 0,  -- nº de veces que el retador re-intentó
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
) WITH (fillfactor = 100);  -- append-only, nunca UPDATE

CREATE INDEX idx_vv_target ON verification_verdicts (target_type, target_key, created_at DESC);
CREATE INDEX idx_vv_open   ON verification_verdicts (verdict) WHERE verdict <> 'TRUSTWORTHY';
```

Inmutable: una re-verificación inserta una **nueva fila** (historial de veredictos). El veredicto vigente
es el `created_at` máximo por `(target_type,target_key,claim_kind)`. Cada inserción emite además un
`audit_log` (ya existe) → trazabilidad doble.

### 3.2 Despertar `source_overlap_matrix` (EXISTE, sin worker)

Ya tiene `lincoln_petersen_n, chapman_n, chapman_var, ci_lower, ci_upper, capture_rate_a/b`. El worker
nuevo `scripts/run_overlap_audit.py` la puebla por país/par-de-fuentes.

### 3.3 Despertar `coverage_matrix` (EXISTE, sin worker)

`expected_for_sale = fleet_count × turnover_rate`; `coverage = observed/expected`. Worker nuevo
`scripts/run_coverage_audit.py`.

### 3.4 Receta de verificación por entidad (JSON, git-trackeado, portable)

Para que mañana Codex u otra herramienta sepa CÓMO se verificó cada entidad — `configs/verify/<key>.json`:

```json
{
  "target_key": "dacia-meaux.fr:FR",
  "target_type": "ENTITY_INVENTORY",
  "claim_kind": "COUNT",
  "producer_path": "portal_paginated_listing",
  "verifier_methods": [
    { "method": "sitemap_pdp", "detail_url_re": "/voiture-occasion/.+-\\d+\\.html$", "weight": 1.0 },
    { "method": "jsonld_total", "selector": "numberOfItems", "weight": 0.8 }
  ],
  "tolerance": 0.02,
  "quorum_required": 2,
  "sample": { "size": 0, "stratify_by": [] },
  "notes": "E2E probado 230/230. Sitemap es la vía ortogonal canónica para este dealer."
}
```

Para el universo de un país — `configs/verify/discovery_ES.json`:

```json
{
  "target_key": "ES",
  "target_type": "DISCOVERY_UNIVERSE",
  "claim_kind": "COMPLETENESS",
  "producer_path": "es_openmercantil_api",
  "verifier_methods": [
    { "method": "registry_dump", "source": "opendatasoft:es_mercantil", "activity_codes": ["4511","4519","4531","4532"] },
    { "method": "osm_overpass", "query": "shop=car", "orthogonal": true },
    { "method": "capture_recapture", "pair": ["registry", "osm"] }
  ],
  "quorum_required": 2,
  "macro_sanity": { "method": "fleet_census_coverage", "tolerance_hi": 1.05 }
}
```

---

## 4. Los verificadores (módulos nuevos, todos puros + shell)

### 4.1 `scrapers/intelligence/capture_recapture.py` (E2 — NUEVO)

Función pura `chapman_estimate(n_a:int, n_b:int, m_overlap:int) -> Estimate` con:
- `N = ((n_a+1)*(n_b+1)/(m+1)) - 1` (estimador de Chapman, insesgado para muestras pequeñas).
- `var = ((n_a+1)(n_b+1)(n_a-m)(n_b-m)) / ((m+1)^2 (m+2))`.
- IC 95% = `N ± 1.96*sqrt(var)`.
- `verdict_for_claim(claimed, estimate)` → OVERCOUNT si `claimed > ci_upper`, GAP si `claimed < ci_lower`, sino dentro.

El shell async `audit_country(country, source_a, source_b)` lee los sets de `discovery_candidates` por
`source`, computa overlap por **clave de identidad** (dominio normalizado | `registry_id` | `name+city`
normalizado con pg_trgm), escribe `source_overlap_matrix`, emite `VerificationVerdict`.

**Matching de identidad (anti-falsa-divergencia):** dos filas de fuentes distintas son la MISMA entidad si
comparten dominio, o `registry_id`, o (similaridad nombre>=0.85 AND misma ciudad). Reusa `entity_resolver`
+ `pg_trgm`. Si el matching es pobre, el overlap M se subestima y Chapman infla N → el agente retador lo
detecta porque la varianza explota (IC absurdamente ancho) y escala a una tercera fuente.

### 4.2 `scrapers/intelligence/dedup_audit.py` (E4 — NUEVO)

- `over_dedup_pairs(rows)` puro: filas que comparten `fingerprint_sha256` pero difieren en
  `source_url`/`source_platform` → candidatos a coches FÍSICOS distintos colapsados o a matches
  cross-source que deberían vivir en `entity_matches`, no fundirse. (Caza el riesgo `vin:vin:color:km`.)
- `under_count_clusters(rows, phash_fn)` puro: agrupa por `(make,model,year,round(price),round(km))` y,
  dentro del cluster, por distancia de Hamming de **phash de la foto principal** (imagehash OSS) →
  quasi-duplicados que el fingerprint de texto/URL NO unió. Vía ORTOGONAL (imagen, no texto).
- Shell async sobre `vehicles`/`vehicle_events` por `source_platform`. Veredicto UNIQUENESS.

### 4.3 `scrapers/intelligence/live_sample.py` (E3 — NUEVO; eleva `quality_sample.py`)

- `wilson_sample_size(universe, margin=0.02, conf=0.95)` puro → N de muestra.
- `stratified_offsets(universe, strata)` puro → offsets aleatorios por estrato (país×fuente×tier).
- Shell async `verify_sample(rows, fetcher_B)`: re-fetch live por un **fetcher/identidad distinto**, corre
  `poison.detect` (no comparar contra honeypot), compara campo a campo contra lo persistido:
  - URL 404/desaparecida o coche ausente → **HALLUCINATED** (dato inventado).
  - precio/año/km divergen > umbral → **WRONG_FIELD** (correctness).
  - `last_seen` viejo y el coche sigue activo, o vendido y aún ACTIVE → **STALE** (frescura).
  - todo concuerda → OK.
- Veredicto CORRECTNESS/FRESHNESS con tasa de error y sus IC de Wilson.

### 4.4 `scrapers/intelligence/registry_audit.py` (E1 — NUEVO; generaliza `verify_discovery.py`)

Hoy `verify_discovery.py` solo cubre FR. Se generaliza a una interfaz por país con su fuente-de-verdad
ORTOGONAL al productor: ES (opendatasoft mercantil), BE (KBO dump), CH (Zefix), DE (offeneregister),
NL (KvK/RDW), FR (SIRENE dump opendatasoft — NO la API que se banea). `completeness = in_db/source` por
slice, contraejemplos exactos (los IDs faltantes) en `evidence`, `--fill` opcional. Veredicto COMPLETENESS.

### 4.5 `scrapers/intelligence/verdict.py` (QUÓRUM ENGINE — NUEVO, núcleo)

```python
@dataclass(frozen=True)
class MethodResult:
    method: str
    value: float | None      # conteo/estimación; None si el método no pudo derivar
    divergence: float | None # vs claimed
    orthogonal: bool         # ortogonal al producer_path?
    detail: str

@dataclass(frozen=True)
class VerificationVerdict:
    target_type: str; target_key: str; claim_kind: str
    claimed: float | None
    methods: tuple[MethodResult, ...]
    quorum_required: int
    verdict: str             # TRUSTWORTHY|DISPUTED|GAP|OVERCOUNT|STALE|HALLUCINATED|POISONED|UNVERIFIED
    confidence: float
    estimate_n: float | None; ci: tuple[float,float] | None
    evidence: dict

def decide(claimed, methods, *, quorum_required=2, tolerance=0.02) -> VerificationVerdict
```

Reglas de `decide` (compone, reusa la filosofía de `count_verify.cross_check`):
- Solo cuentan métodos **ortogonales** y con `value` usable (>0).
- **TRUSTWORTHY** ⇔ `>= quorum_required` métodos ortogonales convergen dentro de `tolerance`.
- Si los métodos discrepan sistemáticamente al alza del claim → **OVERCOUNT**; a la baja → **GAP**.
- Si E3 reporta HALLUCINATED/STALE por encima de umbral → ese veredicto domina (contenido manda sobre conteo).
- Si E3/poison marca el contenido envenenado → **POISONED** (no se puede verificar contra honeypot).
- Si hay <quórum (un método o discrepancia sin patrón) → **DISPUTED**; **UNVERIFIED** si ningún método pudo derivar.
- `confidence` = función del nº de métodos convergentes y su divergencia mínima.

---

## 5. Workflows

### WF-1 — Verificación de UNIVERSO de discovery (¿están todos los dealers de un país?)
Disparador: cierre de una pasada de discovery por país, o nightly. Pasos:
1. Líder carga `configs/verify/discovery_<CC>.json`.
2. E1 (`registry_audit`) re-deriva completeness desde el DUMP gov (ortogonal a la API productora).
3. E2 (`capture_recapture`) estima N real cruzando 2-3 fuentes (registry × OSM × portal-directory × CT-logs).
4. E5 (`coverage` macro) sanity: observed dealers vs expected por fleet-census.
5. Quórum: TRUSTWORTHY si E1>=0.99 AND E2 sitúa el claim en su IC. GAP → emite los IDs faltantes y re-encola harvest. OVERCOUNT → audita duplicados (E4 a nivel dealer).
6. Si no hay quórum → WF-4 (retador).

### WF-2 — Verificación de INVENTARIO de una entidad (¿extrajimos el 100%?)
Disparador: cierre de scraping de una entidad (close_entity), promoción de receta. Pasos:
1. E1 conteo independiente por **sitemap PDP** (`count_pdp_in_sitemap`) + **JSON-LD** (`count_jsonld_total`).
2. `cross_check(claimed, {sitemap, jsonld})` con tolerancia de la receta.
3. E4 `dedup_audit` sobre las filas de esa entidad (over/under).
4. Si TRUSTWORTHY → sella receta "probada" (como dacia 230/230). Si shortfall (caso AS24 87.6% una pasada) → recomienda multi-pasada + sort estable (ya implementado en `run_giant_scraping`) y re-verifica.

### WF-3 — Verificación de CONTENIDO (correctness/frescura/no-inventado)
Disparador: nightly sobre inventario vivo + obligatorio antes de marcar receta probada. Pasos:
1. E3 `live_sample`: muestra estratificada, re-fetch por identidad B, `poison.detect`, comparación campo a campo.
2. Veredicto por tasa de HALLUCINATED/WRONG_FIELD/STALE con IC de Wilson.
3. HALLUCINATED>umbral → alerta CRÍTICA (datos inventados) + bloqueo de la fuente + WF-4.

### WF-4 — Reto y agotamiento de vías (el "no se puede" está prohibido)
Disparador: cualquier veredicto DISPUTED/UNVERIFIED o por debajo de estándar. Pasos del retador:
1. Re-ejecuta el método con parámetros distintos (otra fuente del par, ventana temporal, sort estable, +pasadas).
2. Escala a un método más caro (E1→E3 muestreo; añade E5 censo).
3. Si sigue sin quórum, invoca **research-scout** (agente investigación): busca en GitHub/Reddit/foros/Exa una vía ortogonal nueva o herramienta OSS (Camoufox para fuentes con WAF, `splink`/`dedupe` para record-linkage, `imagehash` para phash, datasets/dumps alternativos). El scout devuelve una propuesta de nuevo verificador; el líder la integra como `MethodResult` adicional y re-corre el quórum.
4. Solo se cierra cuando hay quórum o se documenta un BLOQUEO real y declarado (nunca abandono silencioso).

### WF-5 — Gate de publicación (bloqueo de datos no corroborados)
Antes de exponer inventario en la API per-entidad / Meili / marketplace: `publish_gate` consulta el
veredicto vigente. DISPUTED/GAP/OVERCOUNT/HALLUCINATED/POISONED/UNVERIFIED → **BLOQUEA** y enruta a WF-4.
Solo TRUSTWORTHY pasa. (Reusa el patrón de `quality_gate.py` que ya borra docs incompletos en Meili.)

---

## 6. Agentes (rol · responsabilidad · tools · criterio de calidad)

### 6.1 `verification-orchestrator` (AGENTE-LÍDER) — Opus
- **Rol:** descompone el objetivo de verificación en métodos ortogonales, ejecuta los verificadores, compone el quórum, decide el veredicto, persiste y enruta.
- **Responsabilidad:** garantizar que NINGÚN dato se confíe sin >=2 vías ortogonales convergentes; trazabilidad total.
- **Tools:** Read/Grep/Glob, Bash (correr E1-E5 read-only), PG/Redis read, escritura SOLO en `verification_verdicts`/`audit_log`/matrices (reversible y append-only).
- **Criterio de calidad:** cero veredicto TRUSTWORTHY sin prueba de ortogonalidad; cero número confiado sin corroboración; cada veredicto cita evidencia concreta.

### 6.2 `verification-challenger` (RETADOR/MOTIVADOR) — Sonnet
- **Rol:** desconfía del primer resultado de cualquier agente/verificador. Cuando no se llega al estándar, NO acepta "no se puede": reta con otra vía, otro parámetro, método más caro, y dispara investigación.
- **Responsabilidad:** convertir DISPUTED/UNVERIFIED en TRUSTWORTHY o en BLOQUEO declarado; impedir el cierre a medias.
- **Tools:** re-ejecutar verificadores, invocar research-scout, comparar contra veredictos históricos (regresión de confianza).
- **Criterio de calidad:** agota fallbacks antes de declarar bloqueo; cada bloqueo lleva la lista de vías intentadas.

### 6.3 `research-scout` (INVESTIGACIÓN) — Sonnet
- **Rol:** ante un muro, busca en GitHub (`gh search`), Reddit, foros, Exa y registros de paquetes (PyPI/npm/crates) nuevas vías ortogonales y herramientas OSS (Camoufox, splink, dedupe, imagehash, dumps alternativos).
- **Responsabilidad:** entregar una vía nueva accionable o herramienta integrable, evaluada (seguridad, licencia, ajuste).
- **Tools:** GitHub/Exa/web, Read/Grep para integrar, Context7 para docs de la librería propuesta.
- **Criterio de calidad:** propuesta concreta y portable; nada de "quizá exista X"; cita repo/versión.

### 6.4 `data-correctness-auditor` (E3) — Haiku/Sonnet
- **Rol:** muestreo adversarial live; clasifica HALLUCINATED/WRONG_FIELD/STALE/OK.
- **Tools:** fetcher B (curl_cffi/Camoufox), `poison.detect`, comparador de campos.
- **Criterio:** muestra dimensionada por Wilson; jamás compara contra honeypot.

### 6.5 `universe-estimator` (E1+E2+E5) — Sonnet
- **Rol:** re-derivación de registro, captura-recaptura, sanity de censo.
- **Tools:** dumps gov (cacheados), PG read, `capture_recapture`, `coverage`.
- **Criterio:** ortogonalidad probada; IC reportado; contraejemplos (IDs faltantes) materializados.

**Encaje líder↔retador:** el líder produce un veredicto; el retador lo AUDITA por una lente distinta (¿la
ortogonalidad es real? ¿el matching de identidad infló el overlap? ¿la muestra fue representativa?). El
retador puede DEGRADAR un TRUSTWORTHY a DISPUTED si encuentra un fallo de método. Verificación
adversarial co-igual: ni el líder ni el retador tienen la última palabra solos; el quórum la tiene.

---

## 7. Verificación adversarial integrada (cómo se desconfía, en concreto)

1. **Del productor:** todo `claimed_value` se trata como hipótesis, nunca como hecho. El productor declara
   su `producer_path`; los verificadores DEBEN usar caminos distintos (matriz de ortogonalidad §1).
2. **Del verificador:** un solo método nunca basta (quórum>=2). Un método que reporta 0 = "no pude derivar",
   no "confirmado 0". Un método no-ortogonal NO cuenta para quórum.
3. **Del matching (auto-desconfianza de E2):** si el overlap es sospechosamente bajo/alto, el IC de Chapman
   explota → el retador escala a una tercera fuente en vez de confiar el estimado.
4. **Del contenido:** E3 re-visita en vivo por otra identidad y corre `poison.detect` para no validar contra
   un honeypot que devolvería "todo OK" falso.
5. **Del propio VAM:** veredictos append-only + `audit_log` → cualquiera puede re-derivar por qué un dato
   se confió. Si un TRUSTWORTHY previo se contradice con evidencia nueva, se inserta un veredicto que lo
   degrada (gana la evidencia más reciente, como `revalidate` purga FPs).

---

## 8. Criterios de aceptación (medibles)

- **AC-1 (quórum):** ningún `verification_verdicts.verdict='TRUSTWORTHY'` con `quorum_reached < quorum_required` ni con métodos no-ortogonales. (Test + invariante en `decide`.)
- **AC-2 (gate):** `publish_gate` bloquea el 100% de targets sin veredicto TRUSTWORTHY vigente. (Test E2E: un target DISPUTED no aparece en Meili/API.)
- **AC-3 (E1 completeness):** para los 6 países, `registry_audit` corre sobre DUMP (no API) y reporta completeness por slice con contraejemplos materializados; veredicto GAP enumera IDs faltantes y los re-encola.
- **AC-4 (E2 captura-recaptura):** `source_overlap_matrix` poblada para >=3 pares de fuentes por país; Chapman + IC; un claim fuera del IC produce OVERCOUNT/GAP.
- **AC-5 (E3 contenido):** muestra dimensionada por Wilson (error<=2%, conf 95%); tasa HALLUCINATED reportada con IC; HALLUCINATED>1% dispara alerta CRÍTICA + bloqueo.
- **AC-6 (E4 dedup):** detecta over-dedup (mismo fingerprint, distinta plataforma/URL) y under-count (clusters por atributos+phash) con contraejemplos.
- **AC-7 (retador):** todo DISPUTED genera >=1 `challenger_runs`; ningún cierre con DISPUTED sin BLOQUEO declarado y lista de vías intentadas.
- **AC-8 (trazabilidad):** cada veredicto tiene fila append-only + `audit_log`; reproducible por receta `configs/verify/<key>.json`.
- **AC-9 (coste):** heurística/dump primero; LLM local solo en banda ambigua (fail-open); cero proxy de pago en el camino de verificación salvo justificación declarada.
- **AC-10 (regresión):** la suite verde (1246+ tests citados en RESILIENCE_DRIFT_DESIGN.md) no rompe; cada módulo nuevo con sus tests (AAA), cobertura >=80%.

---

## 9. Archivos que se tocarían/crearían (concreto)

**Nuevos:**
- `scrapers/intelligence/verdict.py` — quórum engine (`decide`, `VerificationVerdict`, `MethodResult`).
- `scrapers/intelligence/capture_recapture.py` — Chapman/Lincoln-Petersen (E2).
- `scrapers/intelligence/dedup_audit.py` — over/under-count (E4).
- `scrapers/intelligence/live_sample.py` — muestreo adversarial (E3), eleva `quality_sample.py`.
- `scrapers/intelligence/registry_audit.py` — E1 generalizado a 6 países.
- `scrapers/intelligence/coverage.py` — E5 (fleet-census).
- `scrapers/intelligence/publish_gate.py` — gate de publicación.
- `scripts/run_overlap_audit.py`, `scripts/run_coverage_audit.py`, `scripts/run_verification.py` (CLI líder).
- `configs/verify/*.json` — recetas de verificación portables (por entidad y por universo).
- Migración SQL: `scripts/migrations/00X_verification_verdicts.sql`.
- Tests: `scrapers/tests/test_verdict.py`, `test_capture_recapture.py`, `test_dedup_audit.py`, `test_live_sample.py`, `test_registry_audit.py`.
- Agentes: `.claude/agents/verification-orchestrator.md`, `verification-challenger.md`, `research-scout.md`, `data-correctness-auditor.md`, `universe-estimator.md`.

**Se reutilizan/extienden (no se reescriben):** `scrapers/intelligence/count_verify.py` (cross_check),
`scripts/verify_discovery.py` y `verify_count.py` (plantillas E1), `domain_resolution/validate.py` +
`revalidate.py` (re-derivación), `intelligence/poison.py` (anti-honeypot), `intelligence/drift_gate.py`,
`llm/decisions.py` + `llm/ollama_client.py` (retador determinista→LLM), `entity_resolver.py` (matching),
`rich_consumer.compute_fingerprint` (superficie auditada por E4). Despertar: `source_overlap_matrix`,
`coverage_matrix`, `fleet_census`.

---

## 10. Resiliencia y coste (grado institucional)

- **Resiliencia:** si un dealer/fuente falla, el verificador lo marca UNVERIFIED y CARDEX no se cae (igual
  que `revalidate` no purga en fallo transitorio). Veredictos append-only → recuperable tras crash.
  Dumps cacheados → la verificación no depende de APIs gov vivas (lección dolorosa del ban).
- **Coste:** dumps gratis; sitemap/JSON-LD reusan fetcher; captura-recaptura y censo son queries; muestreo
  es muestra no censo; LLM local Ollama solo en duda (fail-open, `qwen2.5:3b`, keep-alive). Proxy de pago
  jamás para verificar salvo que la fuente ortogonal lo exija y se declare. Robustez > velocidad: el
  retador prefiere una verificación cara y correcta a un TRUSTWORTHY rápido y falso.

## Decisiones clave
- Construir VAM COMPONIENDO los átomos ya probados (count_verify, validate.confirms_dealer, verify_discovery, revalidate, poison, drift_gate, decisions-LLM) en vez de reescribir — anti-atajo, reuso de lo verificado E2E (dacia 230/230, AS24 92.7k).
- Despertar source_overlap_matrix y coverage_matrix: están DEFINIDAS en init-pg.sql pero SIN worker [VERIFICADO] — son la espina dorsal estadística (Chapman/Lincoln-Petersen + fleet-census) que da verificación ortogonal de TAMAÑO de universo sin un censo cerrado.
- Contrato de veredicto único, append-only y trazable (verification_verdicts) + audit_log: cualquiera re-deriva por qué un dato se confió; una re-verificación inserta fila nueva (gana la evidencia más reciente, como revalidate purga FPs).
- Ortogonalidad obligatoria como invariante: un método solo cuenta para quórum si NO comparte el camino de fallo del productor (producer_path vs verifier_paths); dos métodos del mismo camino no son quórum.
- Quórum>=2 métodos ortogonales convergentes como condición ÚNICA de TRUSTWORTHY; sin quórum → DISPUTED y BLOQUEO en publish_gate. El contenido (HALLUCINATED/POISONED) domina sobre el conteo.
- Tríada de agentes adversariales co-iguales: líder (Opus) compone quórum, retador (Sonnet) puede DEGRADAR un TRUSTWORTHY si halla fallo de método, research-scout (Sonnet) agota GitHub/foros/OSS ante un muro. Ni líder ni retador deciden solos.
- Verificar CONTENIDO por re-fetch live con identidad/fetcher DISTINTO + poison.detect, para no validar contra honeypot; muestra dimensionada por intervalo de Wilson (error<=2%, 95%).
- Auditar explícitamente el riesgo de over-dedup/under-count del fingerprint (vin:color:km y url-exacta [VERIFICADO en rich_consumer]) con una vía ortogonal de imagen (phash), no de texto.
- Coste-eficiente por diseño: dumps gratis (no APIs gov baneables), muestreo no censo, LLM local solo en duda fail-open, proxy de pago jamás para verificar salvo justificación declarada.
- Ignorar ARCHITECTURE.md (Go/SQLite, OBSOLETO): el store real es PostgreSQL+Redis+SQLite-engine [VERIFICADO]; gana el código observado sobre el doc stale (antialucinación).

## Riesgos
- Matching de identidad débil en E2 sesga la captura-recaptura: si el overlap M se subestima, Chapman infla N y produce falsos GAP/OVERCOUNT. Mitigación: matching multi-clave (dominio|registry_id|nombre+ciudad pg_trgm) y el retador escala a 3ª fuente cuando el IC explota.
- Falsa sensación de ortogonalidad: si dos verificadores comparten una dependencia oculta (p.ej. ambos leen un sitemap derivado del mismo CMS), el quórum es ilusorio. Mitigación: campo orthogonal probado por producer_path y revisión del retador.
- Honeypot que devuelve 'todo correcto' en el muestreo live → E3 valida datos envenenados. Mitigación: poison.detect obligatorio sobre cada página re-visitada antes de comparar.
- Coste de fetch live de E3 si la muestra crece o si se aplica a fuentes con WAF Tier-1: puede requerir Camoufox/proxy. Mitigación: muestra Wilson (no censo), escalar a Camoufox solo en bloqueo, declarar coste.
- over-dedup real ya cometido en datos persistidos (fingerprint vin:color:km) sería invisible a conteos: E4 debe correr retroactivamente; si ya se purgaron filas colapsadas, la evidencia se perdió. Mitigación: E4 sobre vehicle_events (append-only) además de vehicles.
- Drift de la fuente-de-verdad: un dump gov desactualizado hace que E1 reporte GAP falsos (la fuente cambió, no nosotros). Mitigación: versionar fecha del dump en evidence y tolerancia de frescura del propio registro.
- Bloqueo excesivo del publish_gate frena el producto si los verificadores son demasiado estrictos al inicio (pocos datos corroborados). Mitigación: roll-out por fases, veredicto DISPUTED visible en dashboard antes de activar el bloqueo duro, calibración de umbrales con datos reales.
- Sobre-ingeniería estadística (Chapman, Wilson, Fellegi-Sunter) sin datos suficientes para que sea fiable a baja N. Mitigación: estimador de Chapman precisamente por ser insesgado a baja muestra; reportar siempre IC y degradar a DISPUTED cuando el IC es demasiado ancho.