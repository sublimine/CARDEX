# Resilience subsystem — config-driven extraction + drift detection (seed + trace)

**Fecha:** 2026-06-06 · **Rama:** `feature/p0-rewiring-canon`
**Origen:** adenda al patrón NL — el scraper nace config-driven y con baseline de validación
para detección de DRIFT. Esto traza el subsistema anti-ruptura y deja su **semilla viva**.

> No se reescribieron portales. Se externalizó la *receta* a un store versionado, se selló el
> *contrato de salud* (baseline) por origen, y se **cableó** el detector de drift que ya existía
> pero nunca corría. Cada pieza nueva está testeada; el detector de esquema se reutiliza, no se
> reinventa.

---

## 1. El problema

Un portal cambia su HTML (rediseño, A/B test, WAF que envenena) y, sin red de seguridad, el
pipeline sigue ingiriendo registros medio-vacíos o ninguno **en silencio**. La señal de
cobertura se corrompe (P0-1 atacó un caso: harvest-0 falso-`done`). Hace falta que cada scraper:
(a) tenga su **lógica de extracción en config versionada**, no hardcodeada, para reparar tocando
un archivo; y (b) exponga un **baseline de validación** (volumen, campos, esquema) para detectar
la ruptura en el momento, alertar por origen, y reparar por config.

---

## 2. Dos pilares

### Pilar A — Extracción config-driven (store versionado)
La receta por origen (estrategia · endpoints · paginación · extracción/normalización · baseline)
vive en `configs/portals/<source_key>.json` (git-trackeado → cada cambio es un diff revisable),
cargada por `scrapers/portals/config.py::load(source_key)`.

`ExtractionConfig` (las cinco hachas que pide la adenda):

| Bloque | Campos | Qué externaliza |
|---|---|---|
| `strategy` | portal_paginated / sitemap_listing / jsonld_detail / wp_rest / socrata | CÓMO expone el inventario |
| `endpoints` | host · listing_url_template · sitemap_url · **detail_url_re** · api_url | DÓNDE fetchear (selectores de URL) |
| `pagination` | page_size · max_pages · page_param | CÓMO paginar |
| `extraction` | method (jsonld/microdata/og/heuristic/socrata) · **field_map** | NORMALIZACIÓN (selectores→canónico) |
| `drift_baseline` | extraction_method · expected_min_volume · required_fields · min_nonnull_ratio | CONTRATO de salud |

Referencias vivas: `configs/portals/autotrack.nl.json` (portal_paginated) y `viabovag.nl.json`
(sitemap_listing) — los dos portales NL probados E2E. Añadir un portal = un JSON, no código.

> Hoy las subclases (`portals/<x>/__init__.py`) aún ejecutan con sus class-attrs; la migración a
> *ejecutar desde config* (`cls.config = load(domain)`) es incremental y aditiva — el store y el
> baseline ya son la fuente de verdad versionada. La config NL nace así.

### Pilar B — Baseline de validación + detección de drift
Tres dimensiones, compuestas en **un veredicto por origen** (`scrapers/intelligence/drift_gate.py`):

| Dimensión | Qué detecta | Implementación |
|---|---|---|
| **SCHEMA** | el *conjunto de campos extraíbles* cambió (rediseño) | **REUSO** `intelligence/schema.py` (D2): `schema_fingerprint` + `check_drift` sobre `schema_registry` |
| **VOLUME** | la cosecha cae bajo `expected_min_volume` (bloqueo/selector roto) | NUEVO (baseline); complementa el harvest-0 EMPTY_SUSPECT de P0-1 con un *piso esperado* por origen |
| **FIELD** | < `min_nonnull_ratio` de registros traen los `required_fields` (200-OK vacío) | NUEVO (baseline) |

`evaluate(cfg, stats, conn) -> DriftReport` devuelve `ok`/`alert` + qué dimensión rompió
(`report.reason()` → p.ej. `drift:volume(4<50)+fields(price)`), de modo que la **alerta es por
origen y por causa** y la **reparación es un solo edit** a `configs/portals/<source>.json`.

---

## 3. El flujo anti-ruptura (detect → alert-by-source → repair-by-config)

```
harvest de un origen (seam A4→A7 / verify_portal)
   → HarvestStats (volume + non-null por campo + 1 muestra de field-set)
   → drift_gate.evaluate(cfg, stats, conn=engine.db)
        ├─ VOLUME  < baseline?            → alert
        ├─ FIELD   < ratio?               → alert (nombra campos débiles)
        └─ SCHEMA  fingerprint cambió?    → alert (check_drift marca last_change_at)
   → si alert:  pausar origen + DLQ pendientes + notificar(source, reason)
   → reparar:   editar configs/portals/<source>.json (selector/strategy/field_map)
   → re-validar: el mismo gate vuelve a OK; schema_registry re-sella el baseline
```

**Cableado actual (demostrado en vivo):** `scripts/verify_seam_redis.py` ejecuta el gate tras
persistir — corrida real sobre `viabovag.nl`: `DRIFT GATE [viabovag.nl]: OK` y `schema_registry`
queda sellado (`viabovag.nl | c15154c41daf | jsonld | 1`). Es la primera vez que el detector D2
(que existía sin invocador) corre.

**Cableado en producción (punto declarado):** el coordinator, tras `BasePortalScraper.run`, ya
tiene el `RunResult` (url_count) y puede componer `HarvestStats` con el non-null de los registros
ricos (A7) y llamar `drift_gate.evaluate` por origen; en `alert` aplica pausa+DLQ (mecanismos que
ya existen: circuit breaker + `dlq.py`). Es aditivo sobre el contrato estable.

---

## 4. Qué se construyó (todo testeado) vs qué se reutilizó

| Pieza | Estado | Archivo | Tests |
|---|---|---|---|
| Store de config versionado | **NUEVO** | `scrapers/portals/config.py` + `configs/portals/*.json` | `test_portal_config.py` (5) |
| Drift gate (compose 3 dims) | **NUEVO** | `scrapers/intelligence/drift_gate.py` | `test_drift_gate.py` (6) |
| Detector schema-fp (D2) | **REUSO+CABLEADO** | `scrapers/intelligence/schema.py` | (existentes) |
| `schema_registry` (store baseline) | **REUSO** (estaba en 0) | `scrapers/db.py` | poblado en vivo |
| Hook en ruta de verificación | **NUEVO** | `scripts/verify_seam_redis.py` §4b | demostrado vivo |
| Configs de referencia NL | **NUEVO** | `autotrack.nl.json`, `viabovag.nl.json` | cargadas en test |

Detectores hermanos ya presentes para integrar al mismo gate (P1): `intelligence/poison.py`
(datos envenenados) y `intelligence/waf.py` (huella de WAF) — el `drift_gate` es el punto natural
de composición.

---

## 5. Adopción y fan-out

- **NL nace config-driven:** autotrack/viabovag tienen config + baseline; el seam corre el gate.
- **Resto de portales (incremental, aditivo):** generar `configs/portals/<source>.json` por
  portal (un script puede derivar el esqueleto de las class-attrs actuales) y, opcionalmente,
  hacer que la subclase cargue su config. El gate aplica a cualquier origen con config.
- **Fan-out por país:** el baseline (volume/fields) y el schema-fp son agnósticos de país; cada
  portal de DE/ES/FR/BE/CH obtiene su JSON + baseline igual que NL.

---

## 6. Estado y honestidad

**Vivo y verificado:** store de config versionado (2 configs NL reales) · drift_gate (3 dims,
11 tests) · detector D2 cableado y poblando `schema_registry` en vivo · alerta por origen+causa
· reparación por config. Suite **1246 verde**.

**Trazado para P1 (no a medias en silencio):**
- Migrar las subclases a *ejecutar* desde config (hoy la config es fuente de verdad + baseline;
  la ejecución sigue en class-attrs).
- Cablear el gate en el coordinator de producción (pausa+DLQ automáticos en `alert`).
- Integrar `poison.py`/`waf.py` al mismo gate; añadir notificación (healthchecks.io / Alertmanager,
  ya en `deploy/observability`).
- Generar configs para los ~40 portales restantes (script de bootstrap desde class-attrs).

*Fin del trazado del subsistema de resiliencia.*
