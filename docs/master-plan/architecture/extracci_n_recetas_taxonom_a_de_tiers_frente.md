# Extracción + Recetas + Taxonomía de Tiers (frente C: activar el 100% del inventario por entidad)

## Resumen
El subsistema de extracción de CARDEX ya existe y está VALIDADO, no es greenfield: el bucle por-dealer detector → harvester → drift_gate → remediation está construido sobre el seam L1→L2 y probado E2E (dacia-meaux.fr 230/230, ~24 vehículos reales en `vehicles`, AS24-FR 92.759 al 98,8%). Las recetas se persisten en `configs/dealers/<domain>.json` (estricto, auto-generado por `detector.build_config`) y `configs/portals/<portal>.json` (libre, curado). La verificación adversarial ya capturó una mentira real (count_verify, dacia 17-vs-229). La detección de CMS/DMS embebido existe (`detector_helpers._DMS_PROVIDERS`: modix, dealerk, planetvo, dealer.com, incadea...) PERO solo como etiqueta de no-yield, nunca como multiplicador.

El diseño NO reescribe nada de esto: lo eleva. Tres saltos arquitectónicos concretos cierran la misión. (1) EL MULTIPLICADOR CMS: convertir la detección de plataforma latente en un sistema de RECETAS DE FAMILIA — una receta por CMS (izmocars, dealer.com/dealerk, WordPress, Next.js dealer themes) que cierra MILES de dealers del mismo CMS de golpe; el `details_no_fields` 19% (inventario JS/widget) y el `embedded_dms` se resuelven con un conector de feed por proveedor DMS, no dealer a dealer. (2) TAXONOMÍA DE TIERS DE DOS EJES (defensa anti-bot D0-D3 × naturaleza E-PLATFORM/E-FAMILY/E-INDEP/E-GARAGE/E-SCRAP) que el código hoy colapsa en un solo eje T0-T3 mezclando defensa con tamaño. (3) COMPLETITUD POR ENTIDAD elevada a contrato verificable: el patrón multi-pasada+sort-estable de AS24 se generaliza a toda entidad faceteable y la verificación adversarial (count_verify) se promueve de check ad-hoc a GATE obligatorio que bloquea la publicación de un conteo no corroborado por una vía independiente.

La estrategia es siempre multi-vía rankeada con un protocolo de agotamiento + un agente de investigación que busca herramientas open-source (Camoufox ya instalado, y muchas más) ante cualquier muro, y un orquestador-líder con un verificador adversarial co-igual que desconfía de la primera respuesta de todo agente. Coste cero por defecto (curl_cffi + Camoufox + LLM local Qwen2.5-Coder en :8081 ya operativo para generar/reparar recetas), proxies de pago solo donde aportan valor medible (los 12 gigantes gateados y el 23% unreachable por bloqueo de IP datacenter).

## Estrategias
- **S0 — Resolución de receta (cache-first, el camino más barato siempre primero)**: Antes de tocar la red, `portal_config.load(domain)` busca receta curada (portal) → receta de dealer → RECETA DE FAMILIA por CMS (nuevo). Si existe receta de familia para el CMS detectado del dealer, se instancia con los parámetros del dealer (host, sitemap) SIN re-probar. Reutiliza `scrapers/portals/config.py:load()` extendido con un tercer store `configs/families/<cms>.json`. Coste: 0 red en hit.
- **S1 — Extracción estática multi-estrategia (cascada verificada)**: `generic_extractor.extract_listing` ya encadena JSON-LD (schema.org Car/Vehicle/MotorVehicle) → microdata → OpenGraph/SEO-meta (con guarda de procedencia de precio/año que ya evita el bug del 'acompte' de 1.000€) → heurística. Discovery catalog-aware: sitemap → wp-rest → homepage-links → catalog → catalog-follow (`discovery.discover_detail_urls`). Transporte curl_cffi impersonate chrome131, JA3 coherente p1→pN por dominio (`make_dealer_fetcher`).
- **S2 — Render E07 (Camoufox/Playwright) playwright_meta + playwright_xhr**: Cuando la estática ve un shell SPA (`detect_spa_markers`: __NEXT_DATA__, __NUXT__, data-reactroot...) y el catálogo pinta su grid client-side, `discover_detail_urls` hace render-follow con `e07_fetcher`. Dos sub-estrategias: playwright_meta (render + parse SEO meta, ya operativo) y playwright_xhr (render + intercepta el XHR de datos del SPA — declarado en STRATEGIES pero pendiente de cablear; cierra el 19% `details_no_fields`). Camoufox primario (Firefox, fingerprint nativo), Chromium+stealth fallback. RAM-safe: 1 browser/batch, concurrencia 2, GC entre batches.
- **S3 — Conector de feed DMS por proveedor (el multiplicador del long-tail)**: `detect_embedded_dms` ya identifica el proveedor (modix, dealerk, planetvo, dealer.com, incadea, autinity...). En vez de etiquetar 'embedded_dms' y rendirse, un CONECTOR POR PROVEEDOR harvestea el feed del proveedor (su API/iframe-endpoint) con el dealer_id como parámetro. Una integración por DMS cierra todos los dealers que lo embeben. Recetas en `configs/families/dms_<provider>.json`.
- **S4 — Faceteo + sort estable para completitud (multi-pasada)**: Para entidades con cap de resultados (portales y dealers grandes con buscador): partición por facetas ortogonales (año×precio×combustible, patrón AS24 verbatim de GOLD_NUGGETS §1: 11 bandas de año × 8 techos de precio × 4 combustibles, cap 400/segmento) + sort estable (sort=age&desc) para que la paginación no pierda la cola. Generalizado a `faceted_ssr` (ya en STRATEGIES).
- **S5 — Mobile-API / endpoint oculto (bypass de WAF behavioral)**: Para gigantes D3 (DataDome/PerimeterX): la API móvil suele saltarse el WAF web. Ya verificado vivo 2026-06-09: autohero GraphQL no-auth (DE total=7155), heycar REST no-auth (FR total=34239). leboncoin/lacentrale mobile API = bypass DataDome documentado (GOLD_NUGGETS §5). Protocolo: capturar con mitmproxy+frida (infra ya presente en mobile_re/), mapear a receta T0.
- **S6 — Browser behavioral + proxy residencial + solver (último recurso pagado)**: D3 real (DataDome/PerimeterX que resisten S5): Camoufox + Oxymouse behavioral + proxy residencial/móvil + CAPTCHA solver. JA3 coherente, warm-up de cookies (_abck/datadome). Solo cuando S0-S5 se agotaron y un agente de investigación confirmó que no hay vía gratis.

## Spec completa
# CARDEX — Subsistema de EXTRACCIÓN + RECETAS + TAXONOMÍA DE TIERS

> Especificación de grado institucional. Construida sobre el código REAL verificado
> en `C:\Users\elias\projects\cardex-integration` (no greenfield). Cada componente
> existente se cita; cada componente nuevo se ancla a una extensión aditiva de lo que
> ya funciona. Marca [VERIFICADO] = leído en fuente; [NUEVO] = a construir.

---

## 0. Misión del subsistema y veredicto del reconocimiento

**Misión.** Por CADA entidad con web + inventario (concesionario, compraventa, garaje,
desguace, plataforma), extraer el 100% de su inventario, persistir una RECETA portable
de cómo se hizo, enjaular el inventario en `vehicle_index`/`vehicles` bajo un
`source_entities` vivo con delta, y verificarlo adversarialmente. Escala objetivo:
millones de entidades, los 6 países (ES/FR/BE/NL/DE/CH).

**Veredicto del recon (sin maquillaje).** El bucle por-entidad EXISTE y está validado:

- [VERIFICADO] `scrapers/dealer_scraping/detector.py` — probe dominio → `DetectionResult` →
  `build_config` → `ExtractionConfig`. Decide estática vs render por la primera ficha que
  rinde un `VehicleRecord` real.
- [VERIFICADO] `scrapers/dealer_scraping/discovery.py` — `discover_detail_urls`:
  sitemap → wp-rest → homepage → catalog → catalog-follow (estático) → render-follow.
  Resuelve "el sitemap apunta a `/fahrzeuge` no a las fichas".
- [VERIFICADO] `scrapers/dealer_scraping/harvester.py` — runner RAM-safe (cursor id-paged,
  E07 conc 2, 1 browser/batch, validate-with-limit-and-purge, retry transitorio in-fetcher).
- [VERIFICADO] `scrapers/dealer_scraping/remediation.py` — drift→re-detect→regenerate→
  revalidate, funcional (no stub).
- [VERIFICADO] `scrapers/pipeline/generic_extractor.py` — cascada JSON-LD→microdata→OG/SEO→
  heurística con guarda de procedencia de precio/año (evita el bug del 'acompte' 1.000€ y del
  'año copyright 2000').
- [VERIFICADO] `scrapers/intelligence/count_verify.py` — verificación adversarial:
  `count_pdp_in_sitemap` + `count_jsonld_total` + `cross_check`. Capturó la mentira real
  dacia 17-vs-229 (12×).
- [VERIFICADO] `scrapers/intelligence/schema.py` — fingerprint de schema (set de campos
  presentes + método) con `compare_drift` read-only para el sweep.
- [VERIFICADO] `scrapers/portals/config.py` — store versionado de recetas:
  `ExtractionConfig` (5 ejes: strategy·endpoints·pagination·extraction·drift_baseline),
  `load/save/emit/list_configs`, dos stores (portals curado, dealers auto-generado).
- [VERIFICADO] `scrapers/engine/router/classifier.py` + `domain_map.py` — clasificación WAF
  pura (`classify_signals`) → Tier; registro de 69 specs.
- [VERIFICADO] `scrapers/dealer_scraping/inventory_probe.py` — clasificación a escala
  T1/T2/T3/DEAD sobre `discovery_candidates` con HARD SCOPE GUARD (6 países, excluye IT/AT).
- [VERIFICADO] `scrapers/dealer_scraping/detector_helpers.py` — `_DMS_PROVIDERS` y
  `detect_embedded_dms`: detecta modix/dealerk/planetvo/dealer.com/incadea/autinity... PERO
  solo etiqueta `embedded_dms:<x>` como NO-YIELD. **Latente, no explotado.**
- [VERIFICADO] DB: `scripts/migrations/0001_source_entities.up.sql` — `source_entities`
  (entity_ulid, source_key, kind platform/dealer, defense_tier T1/T2/T3, waf, config_ref),
  vista `entity_inventory` (proyección pointer+rich), FKs ON DELETE SET NULL (borrar fuente
  NUNCA borra inventario — resiliencia).

**Gaps honestos declarados** (`goal/memory/fronts/project_dealer_scraping_system.md`):
yield estático OSM cost-zero ~3% (OSM es ~mitad no-coches); ~23% unreachable (bloqueo IP
datacenter); ~19% `details_no_fields` (inventario JS/widget no recuperable ni con E07-meta).
El alto yield cost-zero está en BRAND/GROUP dealers con CMS estándar (1 receta → N dealers,
ej. `.audi` ×1354). `playwright_xhr` declarado pero sin cablear. Conector DMS en backlog.

**Conclusión de diseño.** No hay que reconstruir; hay que ELEVAR tres cosas: el multiplicador
CMS (§3), la taxonomía de dos ejes (§2), y la completitud+verificación como contrato (§5, §6).

---

## 1. Arquitectura del subsistema (componentes y flujo)

```
                          ┌─────────────────────────────────────────────┐
  discovery_candidates    │  AGENTE-LÍDER (orquestador, Opus)            │
  (READ-ONLY, otra        │  decide cola, modelo por subtarea, presupuesto│
   sesión es dueña)       └───────────────┬─────────────────────────────┘
        │                                 │ despacha microtareas frescas
        ▼                                 ▼
  ┌───────────────┐   ┌──────────────────────────────────────────────────┐
  │ inventory_probe│──▶│ CLASIFICADOR DE ENTIDAD (§2)                      │
  │  T1/T2/T3/DEAD │   │ defensa D0-D3 (classify_signals) ×                │
  │  +signals      │   │ naturaleza E-* (nuevo) × CMS (fingerprint, §3)   │
  └───────────────┘   └───────────────┬──────────────────────────────────┘
                                       ▼
              ┌────────────────────────────────────────────────┐
              │ RESOLUCIÓN DE RECETA (config.load extendido)     │
              │ portal curada → dealer → FAMILIA-CMS (nuevo,§3)  │
              └───────────┬───────────────────────┬─────────────┘
                  hit     │                       │ miss → DETECTOR (probe)
                          ▼                       ▼
              ┌───────────────────┐   ┌──────────────────────────────┐
              │ HARVESTER         │   │ DETECTOR → build_config       │
              │ (RAM-safe runner) │◀──│ emite receta versionada       │
              └─────────┬─────────┘   └──────────────────────────────┘
                        │ ejecuta estrategia rankeada S1..S6
                        ▼
        ┌──────────────────────────────────────────────────┐
        │ MOTOR DE EXTRACCIÓN (cascada multi-estrategia)     │
        │ S1 estático · S2 render E07 · S3 feed DMS ·        │
        │ S4 faceteo · S5 mobile-API · S6 behavioral+proxy  │
        └─────────┬────────────────────────────────────────┘
                  ▼ records canónicos
        ┌──────────────────────────────────────────────────┐
        │ COMPLETITUD (§5) multi-pasada + sort estable       │
        └─────────┬────────────────────────────────────────┘
                  ▼
        ┌──────────────────────────────────────────────────┐
        │ VERIFICACIÓN ADVERSARIAL (§6, GATE bloqueante)     │
        │ count_verify por vías independientes + contenido   │
        └─────────┬────────────────────────────────────────┘
       converge   │  no converge → UNVERIFIED → re-harvest / escala
                  ▼
        ┌──────────────────────────────────────────────────┐
        │ ENJAULADO: vehicle_index/vehicles + source_entities│
        │ delta (altas/bajas/precio/foto) + emit() receta    │
        └─────────┬────────────────────────────────────────┘
                  ▼
        ┌──────────────────────────────────────────────────┐
        │ RESILIENCIA: drift_gate (volumen) + schema fp +    │
        │ remediation (re-detect→regenerate→revalidate)      │
        └──────────────────────────────────────────────────┘
```

**Principio rector.** Microagentes frescos por microtarea (ya en la doctrina del repo):
cada flecha es un agente con un único trabajo, un contrato de entrada/salida y un criterio
de calidad. El estado vive en disco (recetas JSON git-tracked) y en PG, nunca solo en
contexto volátil.

---

## 2. Taxonomía de TIERS de DOS EJES [NUEVO — corrige el colapso actual]

**Problema actual.** El repo usa un solo eje `Tier T0-T3` que MEZCLA defensa anti-bot con
naturaleza/tamaño: `domain_map.py` T0="mobile API directa", T2="Camoufox"... mientras
`inventory_probe.py` usa T1/T2/T3 para "tiene inventario + WAF" / "tiene inventario sin WAF" /
"no detecté inventario". Dos significados incompatibles del mismo símbolo. La verdad operativa
necesita DOS ejes ortogonales.

### Eje 1 — DEFENSA ANTI-BOT (D, cuánto cuesta acceder)

| Tier | Significado | Detección (ya existe) | Estrategia primaria |
|------|-------------|----------------------|---------------------|
| **D0** | Sin WAF, API/JSON abierta o SSR limpio | `classify_signals` → WAF.NONE | S1 estático / endpoint directo |
| **D1** | Pasivo: Cloudflare-free, sin challenge | WAF.CF_FREE, status 200 | S1 curl_cffi impersonate |
| **D2** | Activo: Akamai/CF-challenge/CF-business | WAF.AKAMAI_V3, CF_PRO, `_abck` | S2 Camoufox + storageState |
| **D3** | Behavioral: DataDome/PerimeterX | WAF.DATADOME, PERIMETER_X, `x-datadome` | S5 mobile-API → S6 behavioral+residential |

`classify_signals(status, headers, body)` ya devuelve exactamente este eje. La migración es
RENOMBRAR el enum `Tier`→`DefenseTier D0-D3` y mapear el T1/T2/T3 de `inventory_probe`
(que es realmente "yield + waf") a D + un campo `yields_inventory` separado.

### Eje 2 — NATURALEZA DE LA ENTIDAD (E, qué es y cómo se cierra)

| Clase | Qué es | Multiplicador | Estrategia |
|-------|--------|---------------|------------|
| **E-PLATFORM** | Portal/agregador (AS24, mobile.de, marktplaats) | 1 receta = 1 portal, miles de dealers dentro | S4 faceteo (cap hit) o API |
| **E-FAMILY** | Dealer sobre CMS conocido (izmocars, dealer.com, WordPress theme, Next dealer) | **1 receta = N dealers** (el gran salto) | Receta de familia §3 |
| **E-INDEP** | Concesionario/compraventa con web propia única | 1 receta = 1 dealer | Detector → receta dealer |
| **E-GARAGE** | Garaje/taller VO, inventario pequeño en 1 página | 1 receta = 1 dealer | S1 homepage-links |
| **E-SCRAP** | Desguace/chatarrero (piezas + algún vehículo) | nicho, baja densidad | S1 + filtro semántico vehículo |
| **E-DMS** | Inventario embebido de proveedor DMS (modix/dealerk...) | **1 conector = N dealers** | S3 feed DMS §3 |

`detect_embedded_dms` ya distingue E-DMS; `inventory_probe` ya distingue vivo/parked/dead.
Lo NUEVO es el campo `nature` y el clasificador de CMS que asigna E-FAMILY.

### Tercer descriptor — CMS/PLATAFORMA (el fingerprint que habilita el multiplicador)

Almacenado por entidad: `cms` (izmocars|dealer_com|dealerk|wordpress|next_dealer|nuxt_dealer|
modix|planetvo|incadea|symfony|custom|unknown). Se deriva del fingerprint §3.

**Esquema persistido** (extensión aditiva de `source_entities`, columnas NULLABLE — reversible):

```sql
ALTER TABLE source_entities ADD COLUMN IF NOT EXISTS nature TEXT
  CHECK (nature IS NULL OR nature IN
    ('E-PLATFORM','E-FAMILY','E-INDEP','E-GARAGE','E-SCRAP','E-DMS'));
ALTER TABLE source_entities ADD COLUMN IF NOT EXISTS cms TEXT;          -- fingerprint §3
ALTER TABLE source_entities ADD COLUMN IF NOT EXISTS dms_provider TEXT; -- cuando nature=E-DMS
-- defense_tier YA existe; ampliar el CHECK a D0-D3 en una migración con backfill T->D.
CREATE INDEX IF NOT EXISTS idx_se_nature ON source_entities(nature);
CREATE INDEX IF NOT EXISTS idx_se_cms    ON source_entities(cms);
```

**Por qué dos ejes importan.** El despacho del orquestador (§4) es una función de AMBOS:
un E-FAMILY/D0 es trabajo masivo cost-zero (prioridad máxima); un E-INDEP/D3 es caro y se
aparca; un E-PLATFORM/D3 (los 12 gigantes) es alto valor que justifica S5/S6. Un solo eje no
puede expresar esto.

---

## 3. EL MULTIPLICADOR CMS — recetas de familia [NUEVO, el mayor ROI]

**Insight.** Miles de dealers comparten CMS. Una receta por CMS cierra todos. El código YA
detecta proveedores DMS (`_DMS_PROVIDERS`) pero los descarta como no-yield. Se eleva a sistema.

### 3.1 Fingerprint de CMS [NUEVO: `scrapers/dealer_scraping/cms_fingerprint.py`]

Función PURA `fingerprint_cms(home_html, headers, sample_detail_html) -> CmsVerdict`. Señales
ordenadas (la primera fuerte gana), todas verificables en HTML/headers:

```
izmocars      : 'izmostatic' | 'data-izmo' | '/cdn.izmocars' en src
dealer.com    : 'static.dealer.com' | 'data-dealer-com' | 'ddc-' class prefix
dealerk       : 'dealerk' en src/host | '/dk-' endpoints
modix         : 'modix' | 'gw-trends' host (ya en _DMS_PROVIDERS)
planetvo      : 'planetvo' | 'autralis' host
incadea       : 'incadea' | 'dms.incadea'
wordpress     : '/wp-content/' | '/wp-json/' | generator meta WordPress
next_dealer   : '__NEXT_DATA__' + JSON-LD Car en detail (Next dealer theme)
nuxt_dealer   : '__NUXT__' + vehicle route
symfony       : 'X-Debug-Token' header | sf- cookies
custom/unknown: ninguna anterior
```

Reutiliza `detect_embedded_dms` (E-DMS) y `detect_spa_markers` (Next/Nuxt). El verdict lleva
`confidence` (alta si ≥2 señales, media si 1) para que el orquestador decida si fía la receta
de familia o cae a detección por-dealer.

### 3.2 Store de recetas de familia [NUEVO: `configs/families/<cms>.json`]

Tercer store en `config.py` (extensión aditiva de `_CONFIG_DIR`/`_DEALER_DIR`). `load()` busca
en orden: portal curada → dealer específico → **familia-CMS**. Una receta de familia es un
`ExtractionConfig` PARAMETRIZADO: define la estrategia y los patrones del CMS, no el host
concreto. Al resolver para un dealer E-FAMILY se instancia con `endpoints.host` del dealer.

**Esquema de receta de familia** (JSON):
```json
{
  "family_key": "dealer_com",
  "kind": "family",
  "version": 3,
  "matches": { "cms": "dealer_com", "min_confidence": "high" },
  "strategy": "jsonld_detail",
  "endpoints": {
    "sitemap_hint": "/sitemap-inventory.xml",
    "catalog_path_tokens": ["used-inventory", "inventory"],
    "detail_url_re": "/used-[\\w-]+/vehicle/\\d+"
  },
  "extraction": { "method": "jsonld", "field_map": {} },
  "drift_baseline": {
    "extraction_method": "jsonld",
    "required_fields": ["make","model","year","price"],
    "min_nonnull_ratio": 0.7
  },
  "provenance": {
    "verified_on_dealers": ["abc-motors.de","xyz-auto.fr"],
    "verified_count": 2,
    "verified_date": "2026-06-09",
    "tool": "qwen2.5-coder local"
  }
}
```

### 3.3 Conectores de feed DMS [NUEVO: `scrapers/dealer_scraping/dms/<provider>.py`]

Para E-DMS (inventario en widget de tercero): un conector por proveedor que harvestea el feed
del proveedor con el `dealer_id` como parámetro. RE 1 vez por proveedor → cierra todos sus
dealers. El conector emite la misma `cage_inventory` que el resto (homogéneo en `vehicle_index`).
Backlog priorizado por nº de dealers que cada proveedor cubre (medir desde
`source_entities WHERE dms_provider=...`).

### 3.4 Flujo del multiplicador

```
dealer nuevo (E-FAMILY/D0)
  → fingerprint_cms → cms=dealer_com, confidence=high
  → config.load → encuentra configs/families/dealer_com.json
  → instancia con host del dealer (CERO probe, CERO red de detección)
  → harvest directo
  → emit() registra el dealer en provenance.verified_on_dealers
```

Una receta de familia bien probada convierte miles de detecciones por-dealer (caras, una red
cada una) en una lectura de JSON + un harvest. Este es el camino a millones de entidades.

---

## 4. WORKFLOWS + AGENTES

Cada workflow es una cadena de microagentes frescos. Modelo por subtarea (doctrina del repo:
orquestador Opus, subagentes el justo; LLM local Qwen2.5-Coder en :8081 [VERIFICADO en STATUS]
para generar/reparar recetas a coste cero).

### W1 — Clasificación a escala (pueblo el universo)
- **Agente: Prober** (Haiku/determinista). Tool: `inventory_probe.run_probes`. Rol: sobre
  `discovery_candidates` pending, clasifica defensa D + vivo/parked/dead + señales de inventario.
  Calidad: SSRF-guard activo, scope 6 países, RAM-aware, escribe `inventory_tier`+`signals`.
- **Agente: CMS-Fingerprinter** [NUEVO] (Haiku). Tool: `cms_fingerprint`. Rol: asigna
  `nature` + `cms` + `dms_provider`. Calidad: confidence reportada, nunca asume CMS con 1 señal débil.

### W2 — Síntesis de receta de familia (el multiplicador)
- **Agente: Family-Recipe-Author** [NUEVO] (Qwen local → Opus si falla). Rol: dado un cluster
  de dealers del mismo CMS, sintetiza UNA receta de familia, la prueba contra ≥3 dealers del
  cluster por vías independientes, la persiste en `configs/families/`. Tool: `detector`,
  `generic_extractor`, `count_verify`. Calidad: receta NO se publica si no rinde en ≥3 dealers
  con conteo corroborado.
- **Agente: DMS-Connector-Builder** [NUEVO] (Opus, RE). Rol: por proveedor DMS de alto volumen,
  RE del feed → conector. Calidad: feed verificado contra el HTML del dealer (mismo nº vehículos).

### W3 — Harvest por entidad (el caballo de batalla)
- **Agente: Harvester** (Sonnet/determinista). Tool: `harvester.harvest_dealer` /
  `inventory_harvester.harvest_t2_dealer`. Rol: resolve-receta → discover → extrae → enjaula →
  drift → (remediate) → purga. Calidad: RAM-safe, una entidad mala nunca aborta el batch,
  validate-with-limit-and-purge en banco local.
- **Agente: Completeness-Driver** [NUEVO] (Sonnet). Rol: para entidades con cap hit, ejecuta
  S4 faceteo+sort-estable hasta cubrir el conteo declarado. Calidad: cobertura ≥98% (umbral AS24).

### W4 — Verificación adversarial (CO-IGUAL, desconfía de W3)
- **Agente: Adversarial-Verifier** [NUEVO, eleva count_verify a gate] (Sonnet, sesión SEPARADA
  de W3). Rol: re-deriva el conteo por vías DISTINTAS a las que usó la extracción (sitemap PDP
  count, JSON-LD total declarado, paginación independiente, muestreo de contenido) y verifica
  CONTENIDO no solo números (frescura: last_seen; correctness: precio/año plausibles; completitud:
  required_fields ratio). Tool: `count_verify.cross_check`, `schema.compare_drift`. Calidad: un
  conteo sin ≥1 vía independiente convergente = UNVERIFIED, BLOQUEA publicación.
  **Desconfianza estructural:** este agente NO comparte fetcher ni discovery con el harvester.

### W5 — Resiliencia / auto-remediación
- **Agente: Drift-Sentinel** (determinista). Tool: `drift_gate.evaluate_volume`,
  `schema.compare_drift` (read-only, no avanza baseline). Rol: detecta volumen colapsado o
  fingerprint de schema cambiado, alerta by-source.
- **Agente: Remediator** (Sonnet). Tool: `remediation.remediate`. Rol: re-detect → regenerate
  receta (version++, audit en git) → revalidate. Calidad: escala (recovered=False) si no rinde
  tras re-detección; nunca loop infinito.

### W6 — Agotamiento + investigación (el "nunca no se puede")
- **Agente: Research-Scout** [NUEVO] (Opus). Disparado cuando una entidad de alto valor agota
  S1-S5 sin yield. Tool: búsqueda GitHub/Reddit/foros (gh search code/repos, web). Rol: encontrar
  herramientas open-source (Camoufox y más: solvers, fingerprint libs, RE de móvil) o vías nuevas
  (endpoint oculto, mirror, mobile API). Calidad: entrega ≥1 vía nueva accionable o un veredicto
  fundamentado de "requiere proxy de pago" con coste estimado. NUNCA cierra con "no se puede".

### Orquestación: AGENTE-LÍDER + VERIFICADOR/MOTIVADOR
- **Líder (Opus).** Mantiene la cola priorizada por (nature × defense × valor), asigna modelo
  por subtarea, gestiona presupuesto (proxies solo donde aportan), persiste PLAN/PROGRESO a
  disco, paraleliza solo lo aislado en datos (country=XX), serializa lo que toca estado global
  (migraciones, tablas compartidas). Primero clava el patrón en 1 entidad/país, luego abanica a 6.
- **Verificador/motivador (co-igual, Opus).** Desconfía de la PRIMERA respuesta de cualquier
  agente. Exige prueba por vía distinta. Si un agente reporta "hecho", el verificador re-deriva.
  Si un agente reporta "no se puede", dispara W6. Mantiene el estándar: nada se da por cerrado
  sin evidencia independiente.

---

## 5. COMPLETITUD POR ENTIDAD [eleva el patrón AS24 a contrato]

**Contrato.** Una entidad está COMPLETA cuando el inventario enjaulado cubre ≥98% del conteo
declarado por la fuente, verificado por vía independiente. Patrón probado: AS24-FR 98,8%.

**Mecanismo (S4, ya parcialmente en STRATEGIES como `faceted_ssr`).**
1. **Detectar cap.** Si paginación simple topa (resultados < conteo declarado), hay cap.
2. **Facetear ortogonal.** Año×precio×combustible (AS24: 11 bandas año × 8 techos precio × 4
   combustibles, GOLD_NUGGETS §1). Cada segmento debe quedar bajo el cap (400 AS24).
3. **Sort estable.** `sort=age&desc=1` para que la cola no se pierda entre páginas (clave del
   98,8%).
4. **Subdividir recursivo.** Si un segmento aún topa, subdividir esa faceta.
5. **Unir + dedup** por `url_hash` (ya en `cage_inventory`).

**Para dealers pequeños** (E-GARAGE/E-INDEP) no hay cap: completitud = todas las fichas del
sitemap/catálogo. `discover_detail_urls` con `detail_url_re` de la receta (ya separa PDP de
índices, ej. dacia `/stock/` vs `/occasion-{make}-` index).

---

## 6. VERIFICACIÓN ADVERSARIAL [gate bloqueante, no opcional]

**Doctrina.** Desconfiar de la primera respuesta. Verificar por vías DISTINTAS a la extracción.
Verificar NÚMEROS Y CONTENIDO. `count_verify.py` ya implementa el núcleo; se promueve a GATE.

**Vías independientes (≥1 debe converger dentro de tolerancia):**
- `count_pdp_in_sitemap(sitemap_xml, detail_url_re)` — cuenta los PDP del sitemap PROPIO de la
  fuente (no nuestra extracción). [VERIFICADO]
- `count_jsonld_total(html)` — total declarado por la fuente (numberOfItems/totalCount). [VERIFICADO]
- **Paginación independiente** [NUEVO] — recorrer la última página del listado y leer el contador
  "N resultados" (regex `INVENTORY_COUNT_RE` ya en `inventory_probe`).
- **Muestreo de contenido** [NUEVO] — re-fetch de K fichas al azar y comparar campos clave con
  lo enjaulado (correctness, no solo conteo).

**Gate.** `cross_check(primary, independent, tolerance=0.02)` → `CountVerdict.trustworthy`.
Si NO converge: el inventario se marca UNVERIFIED, NO se publica el conteo, se dispara re-harvest
o escalada. [VERIFICADO que cross_check ya hace esto; lo nuevo es cablearlo como gate obligatorio
antes de exponer un conteo en `/v1/entities/{ulid}`].

**Contenido y frescura (más allá del conteo):**
- Frescura: `last_seen` de los pointers < umbral (delta vivo).
- Correctness: `min_nonnull_ratio` sobre required_fields (drift_baseline).
- Completitud: cobertura ≥98% (§5).

---

## 7. ESQUEMA DE RECETA PERSISTIDA (portable a Codex u otra herramienta)

Hoy hay DOS formatos divergentes: dealer-store estricto (`configs/dealers/dacia-meaux.fr.json`,
splat a dataclass) y portal-store libre (`configs/portals/autoscout24.be.json`, campos
`access`/`waf`/`verified`/`status`). **Decisión:** unificar bajo un superconjunto donde los
campos extra del portal son anotaciones toleradas (`_only()` ya las filtra al cargar). Toda
receta lleva un bloque `provenance` para portabilidad total (qué pasos se tomaron):

```json
{
  "source_key": "dacia-meaux.fr",
  "country": "FR",
  "nature": "E-FAMILY",
  "cms": "izmocars",
  "defense_tier": "D0",
  "strategy": "sitemap_listing",
  "version": 2,
  "endpoints": {
    "host": "www.dacia-meaux.fr",
    "listing_url_template": "https://dacia-meaux.fr/occasion-fr-fr.htm",
    "sitemap_url": "",
    "detail_url_re": "/stock/",
    "api_url": ""
  },
  "pagination": { "page_size": 0, "max_pages": 0, "page_param": "page", "cap_results": 0 },
  "extraction": { "method": "jsonld", "field_map": {} },
  "drift_baseline": {
    "extraction_method": "jsonld",
    "expected_min_volume": 229,
    "required_fields": ["make","model","year","price"],
    "min_nonnull_ratio": 0.6
  },
  "verification": {
    "method": "count_verify",
    "primary": 229,
    "independent": { "sitemap_pdp": 230, "jsonld_total": 229 },
    "converged": true,
    "verified_date": "2026-06-09"
  },
  "provenance": {
    "detected_by": "detector.detect_web_type",
    "anti_bot_used": "curl_cffi chrome131",
    "discovery_method": "sitemap",
    "tool": "qwen2.5-coder local",
    "notes": "E2E 230/230; sort stable; lección dacia 17-vs-229 verificada"
  }
}
```

`provenance` es lo que hace la receta PORTABLE: cualquier herramienta futura (Codex) lee qué
estrategia, qué anti-bot, qué método de discovery y qué verificación se aplicaron, sin re-derivar.

---

## 8. RESILIENCIA Y TRAZABILIDAD (grado institucional)

- **Borrar fuente nunca borra inventario.** FK `ON DELETE SET NULL` [VERIFICADO en migración].
- **Drift de volumen** (`drift_gate.evaluate_volume`) + **drift de schema** (`schema.compare_drift`
  read-only para sweep, `check_drift` solo en ingest sano) → alerta by-source → remediation.
- **Recetas git-tracked.** Cada cambio es un diff revisable; `emit()` version-bumpea y eleva el
  floor de drift SIN clobbear ediciones de operador (detail_url_re, field_map) [VERIFICADO].
- **Audit trail.** `source_entities.config_ref` apunta a la receta; `provenance` + `verification`
  en la receta; eventos en `vehicle_events`.
- **Rate-limiters desde el inicio** (lección dolorosa SIRENE: usar dumps, no APIs gov rate-limited;
  jitter 1.2s±40% AS24). Aplica a TODA fuente, no como afterthought.
- **Coste.** Cost-zero por defecto (curl_cffi + Camoufox + Qwen local). Proxies de pago SOLO
  para los 12 gigantes D3 y el 23% unreachable, aparcados en backlog con coste estimado, nunca
  bloqueando el avance.

---

## 9. CRITERIOS DE ACEPTACIÓN (medibles)

1. **Multiplicador CMS operativo:** ≥1 receta de familia (ej. WordPress o dealer.com) que rinde
   en ≥10 dealers distintos del cluster sin detección por-dealer, conteo corroborado en cada uno.
2. **Taxonomía de dos ejes en DB:** `source_entities.nature`+`cms`+`defense_tier D0-D3` poblados
   para el 100% de entidades con `inventory_tier` ya probado, backfill T→D sin pérdida.
3. **Completitud:** cualquier entidad con cap hit alcanza ≥98% del conteo declarado (umbral AS24).
4. **Verificación como gate:** ningún conteo se expone en `/v1/entities/{ulid}` sin
   `CountVerdict.trustworthy=true`; el gate replica la detección de la mentira dacia 17-vs-229.
5. **playwright_xhr cableado:** el 19% `details_no_fields` baja midiendo yield antes/después en
   un muestreo de 100 dealers SPA.
6. **Conector DMS:** ≥1 proveedor (el de más dealers) con feed harvestado, verificado contra HTML.
7. **Agotamiento:** W6 Research-Scout cierra cada muro de entidad de alto valor con vía nueva o
   veredicto fundamentado; cero "no se puede" sin agotar S1-S6 + investigación.
8. **Cero regresiones:** suite (1.439 verde [VERIFICADO]) se mantiene; cada componente nuevo con
   tests (cobertura ≥80%, patrón de fakes in-memory ya usado en generic_extractor/harvester).

---

## 10. ARCHIVOS QUE SE TOCAN / CREAN

**Extender (aditivo):**
- `scrapers/portals/config.py` — tercer store `configs/families/`, `load()` busca familia,
  bloque `provenance`/`verification` tolerado por `_only()`.
- `scrapers/engine/router/domain_map.py` + `classifier.py` — renombrar `Tier`→`DefenseTier D0-D3`.
- `scrapers/dealer_scraping/harvester.py` — resolución de receta de familia antes de detect.
- `scrapers/intelligence/count_verify.py` — añadir vía de paginación independiente + muestreo
  de contenido; promover a gate.
- DB: nueva migración `0006_entity_taxonomy.up.sql` (nature, cms, dms_provider, CHECK D0-D3, backfill).

**Crear:**
- `scrapers/dealer_scraping/cms_fingerprint.py` — fingerprint puro de CMS (§3.1).
- `scrapers/dealer_scraping/dms/<provider>.py` — conectores de feed DMS (§3.3).
- `configs/families/<cms>.json` — recetas de familia (§3.2).
- Drivers de agentes W2/W4/W6 (scripts orquestables, modelo por subtarea).

## Decisiones clave
- NO reescribir: el bucle detector→harvester→drift→remediation está VERIFICADO y validado E2E (dacia 230/230). El diseño es ADITIVO sobre código real, citando cada archivo.
- Taxonomía de DOS EJES ortogonales (defensa D0-D3 × naturaleza E-PLATFORM/E-FAMILY/E-INDEP/E-GARAGE/E-SCRAP/E-DMS) + descriptor CMS. Corrige el colapso actual donde 'Tier T0-T3' significa cosas distintas en domain_map.py vs inventory_probe.py.
- EL MULTIPLICADOR CMS es el mayor ROI: la detección de proveedor (detect_embedded_dms, _DMS_PROVIDERS) ya existe pero solo etiqueta no-yield. Se eleva a recetas de familia (configs/families/<cms>.json) — 1 receta cierra N dealers del mismo CMS.
- Conector de feed DMS por proveedor para E-DMS: 1 RE por proveedor cierra todos sus dealers, resolviendo el 19% details_no_fields y el embedded_dms sin ir dealer a dealer.
- Completitud elevada a contrato verificable (≥98%, umbral AS24) vía S4 faceteo año×precio×combustible + sort estable (patrón AS24 verbatim de GOLD_NUGGETS §1).
- Verificación adversarial promovida de check ad-hoc a GATE bloqueante: count_verify ya capturó la mentira dacia 17-vs-229; ningún conteo se publica sin convergencia por vía independiente. El verificador NO comparte fetcher/discovery con el harvester (desconfianza estructural).
- Estrategia siempre multi-vía rankeada S0..S6 (cache→estático→render→DMS→faceteo→mobile-API→behavioral+proxy) con coste creciente; proxies de pago solo en S6, último recurso.
- Receta unificada con bloque provenance+verification para portabilidad total a Codex u otra herramienta (qué estrategia/anti-bot/discovery/verificación se usaron).
- Orquestación: líder Opus + verificador adversarial co-igual + Research-Scout (W6) que ante cualquier muro busca open-source/foros y nunca cierra con 'no se puede'. LLM local Qwen2.5-Coder :8081 (ya operativo) genera/repara recetas a coste cero.
- Migración de defense_tier con backfill T->D no destructivo; columnas nuevas NULLABLE; FK ON DELETE SET NULL preservada (borrar fuente nunca borra inventario).

## Riesgos
- RAM/OOM: el host OOMa acumulativamente (nota memoria 2026-06). El render E07 y el faceteo masivo amplifican el riesgo. Mitigación: caps ya en harvester (E07 conc 2, 1 browser/batch, GC), extender la disciplina a los nuevos drivers W2/W4.
- Falso positivo de CMS fingerprint: una receta de familia mal asignada zeroa o corrompe N dealers de golpe (el multiplicador amplifica errores). Mitigación: confidence >=2 señales, verificar receta en >=3 dealers antes de publicar, drift_gate captura el colapso.
- Glob de subdirectorios falló de forma intermitente en el mount durante el recon (junction/symlink): el recursivo ** funcionó pero el directo no. Riesgo de que herramientas asuman rutas inexistentes. Mitigación: verificar con Read directo antes de tocar.
- Dos formatos de receta divergentes (dealer estricto vs portal libre) ya en producción: unificar sin romper los configs existentes. Mitigación: _only() ya tolera campos extra; migración con test de carga de todos los JSON actuales.
- Bloqueo de IP datacenter (23% unreachable) puede empeorar al escalar el volumen de requests desde una sola IP. Mitigación: rate-limiters desde el inicio, proxy residencial barato para unreachable, JA3 coherente.
- WAF arms race: las recetas D2/D3 (Akamai/DataDome) caducan (comparis re-verificado 2026-06-09 cambió de T1 a DataDome; wallapop GET bypass murió). Mitigación: re-verificación periódica, drift de schema, Research-Scout permanente.
- El conteo declarado por la fuente puede ser él mismo una mentira de marketing (count_jsonld_total infla): el gate trata divergencia >tolerancia como UNVERIFIED, pero hay que distinguir 'fuente miente' de 'extracción incompleta'. Mitigación: max_divergence ya se reporta; muestreo de contenido desambigua.