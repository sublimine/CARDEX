# CRITICAL FINDINGS — TRACK 1 AUDIT

**Fecha:** 2026-04-16 · **Rama:** `audit/track-1-code-docs`  
**Referencia:** `01_code_docs_coherence.md` (hallazgos #1–13 CRITICAL)

Este documento aísla los hallazgos de severidad CRITICAL que requieren decisión de equipo antes del próximo release. Cada uno representa una de las siguientes categorías: claim falso en documentación pública, código roto en silencio, o riesgo de compliance/legal.

---

## CF-01 — RobotsChecker no existe (claim falso en docs públicos)

**Tipo:** Claim falso / riesgo legal  
**Refs:** `01_code_docs_coherence.md` #1, #2

### Evidencia

```
README.md:75:
  "robots.txt compliance — `RobotsChecker` is wired in all HTTP crawl paths."

ARCHITECTURE.md:172:
  "`RobotsChecker` verifies robots.txt compliance before crawling any URL."

grep -rn "RobotsChecker" discovery/internal/ extraction/internal/
→ 0 resultados — el tipo NO EXISTE

discovery/internal/browser/browser.go:18:
  "// robots.txt compliance is the caller's responsibility."

discovery/internal/browser/config.go:5:
  "//  2. Respect for robots.txt (checked by caller before invoking this package)."
```

### Impacto

README y ARCHITECTURE afirman una salvaguarda de compliance que **no existe en código**. Cualquier familia que no implemente manualmente el check puede crawlear URLs marcadas con `Disallow`. Si un tercero audita el sistema, encontrará la afirmación y la ausencia del control.

### Acción requerida

**Opción A (recomendada):** Implementar `RobotsChecker` en `discovery/internal/browser/` con interfaz que fuerce el check antes de cualquier request HTTP. Wiring en `browser.go`. CI que falle si una familia no usa el browser package.

**Opción B:** Eliminar el claim de README:75 y ARCHITECTURE:172. Documentar explícitamente que robots.txt es responsabilidad del caller. Añadir linting/test que verifique que cada familia llama al checker.

**Plazo recomendado:** Antes de cualquier demo externa o publicación de docs.

---

## CF-02 — E11/E12 intercambiados: planning vs código (contrato roto)

**Tipo:** Contrato de arquitectura roto  
**Refs:** `01_code_docs_coherence.md` #3, #4, #5, #35, #61

### Evidencia

```
planning/04_EXTRACTION_PIPELINE/INTERFACES.md:30-31:
  ├── e11_edge_onboarding/        ← planning dice E11 = Edge
  └── e12_manual_review/          ← planning dice E12 = Manual

planning/04_EXTRACTION_PIPELINE/INTERFACES.md:252-253:
  PriorityE11 = 100  // Edge onboarding
  PriorityE12 = 0    // Manual review

extraction/internal/extractor/ (dirs reales):
  e11_manual/                     ← código: E11 = Manual
  e12_edge/                       ← código: E12 = Edge

extraction/internal/pipeline/strategy.go:22:
  PriorityE12 = 1500 // Edge push (Tauri client) — highest trust
```

### Impacto

- **Planning dice E12 es last resort (priority 0).** Código lo ejecuta primero (priority 1500).
- Cualquier desarrollador que lea el planning y añada lógica basada en E11=Edge cometerá bugs.
- La cascade de extracción ejecuta en orden diferente al diseñado. Dealers con cliente Edge activo pueden estar siendo procesados incorrectamente.
- `INTERFACES.md`, `CONTRIBUTING.md`, y `ARCHITECTURE.md` están todos desalineados entre sí y con el código.

### Acción requerida

1. Convocar reunión de arquitectura para decidir la fuente de verdad (planning o código).
2. Si el código es correcto (E12=Edge con alta prioridad), actualizar: `INTERFACES.md`, `planning/E11*.md`, `planning/E12*.md`, `ARCHITECTURE.md`, `CONTRIBUTING.md`.
3. Si el planning es correcto (E12=Manual con prioridad 0), actualizar `strategy.go` y mover los dirs.
4. Añadir CI test que valide que los nombres de directorio coinciden con el mapping declarado en `INTERFACES.md`.

---

## CF-03 — E10: estrategia Mobile API especificada, Email implementado

**Tipo:** Implementación diverge de spec  
**Refs:** `01_code_docs_coherence.md` #6, #7, #30, #31, #58

### Evidencia

```
planning/04_EXTRACTION_PIPELINE/strategies/E10_mobile_app_api.md:1:
  "E10 — Mobile app API"
  Scope: APK analysis, Play Store/App Store reverse engineering,
         apktool, gplaycli, endpoint discovery via strings analysis

extraction/internal/extractor/e10_email/email.go:1-3:
  // Package e10_email implements extraction strategy E10 — Email-Based Inventory.
  // Some micro-dealers have no website feed; they send inventory updates via email
  // with a CSV or Excel attachment.

extraction/internal/extractor/e10_email/email.go:19-21:
  // This sprint delivers the skeleton: interface definition, Applicable logic,
  // and an Extract stub that signals "awaiting attachment" when no staging rows
  // are present. The real IMAP poller and staging table wiring are Phase 4 work.

planning/INTERFACES.md:251:  PriorityE10 = 200   // Mobile app API
strategy.go:32:               PriorityE10 = 600   // Email-based inventory
```

### Impacto

- E10 (Mobile API) según planning cubre <2% del universo dealer pero es un diferenciador estratégico. No está implementado.
- Lo que sí está implementado (Email/EDI) puede ser valioso, pero su spec no existe en planning.
- Las métricas declaradas para E10 (`e10_app_found_rate`, `e10_apk_extracted_rate`) no tienen código que las incremente.
- El código de Email es un skeleton con `Extract()` stub y Phase 4 wiring pendiente.

### Acción requerida

1. Crear `planning/04_EXTRACTION_PIPELINE/strategies/E10_email_edi.md` con la spec real de lo implementado.
2. Renombrar `E10_mobile_app_api.md` a un número libre (E13 si VLM se implementa como E13, o E14+).
3. Corregir la prioridad en `strategy.go` para que coincida con el planning actualizado.
4. Completar la implementación de `e10_email` (IMAP poller, staging table) o marcarlo explícitamente como Phase 4 en el roadmap.

---

## CF-04 — E13 VLM: spec de 227 líneas, cero código

**Tipo:** Feature declarada sin implementación  
**Refs:** `01_code_docs_coherence.md` #8, #39, #47, #48, #49, #50, #59

### Evidencia

```
planning/04_EXTRACTION_PIPELINE/strategies/E13_vlm_screenshot_extraction.md:1-6:
  Estado: DOCUMENTADO — implementación Sprint 8+
  Fecha: 2026-04-15

find extraction/internal/extractor/ -name "*e13*" -o -name "*vlm*"
→ 0 resultados

extraction/go.mod: sin dependencia ONNX, ni modelo VLM
```

### Impacto

- 227 líneas de spec (prompts, arquitectura ONNX, benchmark de modelos) sin una sola línea de código.
- Sin impacto operacional inmediato (Sprint 8+ declarado), pero hay riesgo de que esta deuda se olvide.
- El INTERFACES.md:10 asume que E13+ se puede añadir "sin refactorización" — verificar que el orchestrator tenga auto-discovery o registro explícito.

### Acción requerida

1. Crear issue/ticket formal para E13 con estimación de Sprint 8+.
2. Añadir `// TODO(E13): Sprint 8+ — VLM screenshot extraction` en `extraction/internal/pipeline/` donde se registran estrategias.
3. Verificar que el orchestrator soporta añadir E13 sin refactorización (INTERFACES.md:10 claim).

---

## CF-05 — CONTRIBUTING.md apunta a directorio inexistente

**Tipo:** Documentación de onboarding incorrecta  
**Refs:** `01_code_docs_coherence.md` #9

### Evidencia

```
CONTRIBUTING.md:22:
  "Follow the same pattern as families but in
   `extraction/internal/strategy/e{NN}_{name}/`."

Directorio real: extraction/internal/extractor/e{NN}_{name}/

ls extraction/internal/:
  config/  extractor/  metrics/  normalize/  pipeline/  storage/
  (sin 'strategy/')
```

### Impacto

Todo colaborador nuevo que siga el CONTRIBUTING creará el paquete en `extraction/internal/strategy/` (ruta inexistente). La estrategia nunca sería encontrada por el orchestrator y Go daría error de módulo.

### Acción requerida

Corregir `CONTRIBUTING.md:22`:
```diff
- Follow the same pattern as families but in `extraction/internal/strategy/e{NN}_{name}/`.
+ Follow the same pattern as families but in `extraction/internal/extractor/e{NN}_{name}/`.
```

**Tiempo estimado:** 5 minutos. Máximo impacto por mínimo esfuerzo.

---

## CF-06 — V05–V19: 15 validadores con nombres swapped

**Tipo:** Desalineación sistémica planning↔código  
**Refs:** `01_code_docs_coherence.md` #10–#24, #66

### Evidencia

```
planning dir → código dir (15 divergencias):
V05 image_classification_ml   → v05_image_quality
V06 identity_convergence      → v06_photo_count
V07 image_quality             → v07_price_sanity
V08 image_phash_dedup         → v08_mileage_sanity
V09 watermark_logo_detection  → v09_year_consistency
V10 vehicle_binary_classifier → v10_source_url_liveness
V11 mileage_sanity            → v11_nlg_quality
V12 year_registration_consistency → v12_cross_source_dedup
V13 price_outlier_detection   → v13_completeness
V14 vat_mode_detection        → v14_freshness
V15 currency_normalization    → v15_dealer_trust
V16 cross_source_convergence  → v16_photo_phash
V17 geolocation_validation    → v17_sold_status
V18 equipment_normalization   → v18_language_consistency
V19 nlg_description_generation → v19_currency
```

### Impacto

- Los pesos del composite scorer (V20) están declarados en planning por número de validador. Si `v07_price_sanity` tiene el peso de `V07_image_quality` en `v20_composite/`, el pricing y la calidad de imagen recibirán pesos incorrectos.
- Cualquier referencia en tickets, issues o PRs a "V07" es ambigua: ¿planning V07 (image quality) o código v07 (price sanity)?
- El Knowledge Graph schema (`planning/03_DISCOVERY_SYSTEM/KNOWLEDGE_GRAPH_SCHEMA.md`) puede referenciar validadores por nombre.

### Acción requerida

1. **Inmediato:** Crear tabla de mapping canónico `V_MAPPING.md` en `planning/05_QUALITY_PIPELINE/` con planning_name↔código_name para V05-V19.
2. **Sprint siguiente:** Decidir si renombrar dirs de código (breaking change para scripts) o actualizar planning.
3. **Auditar `v20_composite/*.go`** para verificar que los pesos corresponden a la función real de cada validador, no al nombre de planning.

---

## CF-07 — E05 Priority: 1050 (planning) vs 950 (código)

**Tipo:** Cascada de extracción ejecuta en orden diferente al diseñado  
**Refs:** `01_code_docs_coherence.md` #25

### Evidencia

```
planning/04_EXTRACTION_PIPELINE/INTERFACES.md:244:
  PriorityE05 = 1050  // DMS hosted API

planning/04_EXTRACTION_PIPELINE/strategies/E05_dms_hosted_api.md:11:
  "E05 tiene prioridad 1050 (entre E01 y E02) porque cuando aplica,
   la calidad del dato es comparable a E02 (API nativa) pero el endpoint
   es más estable (mantenido por el proveedor DMS)"

extraction/internal/pipeline/strategy.go:26:
  PriorityE05 = 950  // DMS hosted API
```

### Impacto

Con prioridad 950, E05 se ejecuta DESPUÉS de E02 (1100) y E03 (1000). El planning requiere que E05 se ejecute ENTRE E01 y E02. Dealers con DMS API pueden estar siendo procesados con E02/E03 primero, produciendo datos de menor calidad que lo que E05 entregaría.

### Acción requerida

Actualizar `strategy.go:26`: `PriorityE05 = 1050` para que coincida con el diseño arquitectónico documentado.

---

## CF-08 — E12 Priority 1500: Edge toma prioridad máxima sin justificación en planning

**Tipo:** Comportamiento de producción sin spec  
**Refs:** `01_code_docs_coherence.md` #4, #7

### Evidencia

```
strategy.go:22:
  PriorityE12 = 1500 // Edge push (Tauri client) — dealer-signed, highest trust

planning/INTERFACES.md:253:
  PriorityE12 = 0    // Manual review (last resort)
```

### Impacto

Si E12 es el Edge client con `PriorityE12 = 1500`, se intenta PRIMERO para todos los dealers (incluyendo los que no tienen cliente Edge activo). El `Applicable()` check debe filtrar esto correctamente, pero sin spec que documente este comportamiento, un bug en `Applicable()` podría hacer que E12 intente crawlear todos los dealers.

### Acción requerida

1. Verificar que `e12_edge/edge.go` implementa `Applicable()` con check estricto (dealer tiene cliente Edge activo).
2. Documentar en `INTERFACES.md` por qué E12 tiene la prioridad más alta si es la estrategia "Edge push dealer-signed".
3. Añadir test que verifique que `Applicable()` retorna false para dealers sin cliente Edge.

---

## CF-09 — Prioridades E06-E09 incorrectas (cascade order diferente al diseñado)

**Tipo:** Cascade de extracción ejecuta en orden no especificado  
**Refs:** `01_code_docs_coherence.md` #26, #27, #28, #29

### Evidencia

```
          Planning    Código    Delta
E06:       800         850      +50
E07:       700         800      +100
E08:       300         700      +400
E09:       400         700      +300
```

### Impacto

- E08 (PDF, 300 planning) se ejecuta al mismo nivel que E09 (Excel, 700 planning) con priority 700 en código. El orden entre E08/E09 es indeterminado (misma prioridad = orden de registro).
- E07 (Playwright/XHR) tiene mayor prioridad en código que en planning, lo que aumenta la carga de Playwright para dealers que podrían ser servidos por E06 (Microdata, más ligero).

### Acción requerida

Alinear las prioridades E06-E09 en `strategy.go` con los valores del planning, o documentar la decisión de negocio que justifica los valores actuales.

---

## CF-10 — CONTRIBUTING.md declara `internal/strategy/` como ruta canónica (ya cubierto en CF-05)

Ver CF-05.

---

## CF-11 — E10 Mobile API: estrategia diferenciadora no implementada

**Tipo:** Feature estratégica ausente  
**Refs:** `01_code_docs_coherence.md` #6, #30

**Ver CF-03** para detalle completo. Resumen: la estrategia de APK/Play Store reverse engineering que cubre dealers con apps móviles propias NO está implementada. Es una fuente de datos diferenciadora para dealers de alta calidad.

---

## CF-12 — E11 Tauri client completo: fase de onboarding dealer ausente

**Tipo:** Feature declarada parcialmente implementada  
**Refs:** `01_code_docs_coherence.md` #32, #40, #41, #42, #43

### Evidencia

```
planning/E11_dealer_edge_onboarding.md especifica:
  - Tauri app (Rust + SvelteKit)
  - OAuth2 PKCE authentication
  - DMS connectors: EasyCar, DealerPoint, SalesPoint
  - Data Sharing Agreement UI (GDPR Art. 6(1)(a))
  - Email outreach workflow (DE/FR/ES/NL templates)
  - Push API via HTTPS POST to CARDEX Ingestion API

e11_manual/manual.go:25-28:
  "# Sprint 18 deliverable"
  "wired in main.go Phase 4"
```

### Impacto

El canal de onboarding de dealers premium (los que tienen DMS local) no está operativo. Si hay dealers que esperan integración Edge, no hay infraestructura para recibirlos. La referencia al EU Data Act en planning implica compromisos legales que el código no puede cumplir.

### Acción requerida

1. Añadir E11 completo al roadmap Phase 4 con estimación.
2. Si hay compromisos legales relacionados con EU Data Act/DSA, escalar a legal antes de Phase 4.

---

## CF-13 — Confidence scorer usa fórmula simplificada (TODO Sprint 3)

**Tipo:** Deuda técnica stale / comportamiento de producción incorrecto  
**Refs:** `01_code_docs_coherence.md` #46

### Evidencia

```
discovery/internal/kg/confidence.go:6:
  "// Full formula (TODO Sprint 3): Bayesian combination with source independence"
```

### Impacto

El confidence score de cada dealer/entidad no usa la fórmula Bayesiana diseñada. La fórmula simplificada puede sobreestimar o subestimar la confianza, afectando las decisiones del orchestrator de extracción y la priorización de dealers.

### Acción requerida

1. Crear issue formal: "Implement Bayesian confidence combination (confidence.go:6)".
2. Documentar qué fórmula simplificada se usa actualmente para que el equipo pueda evaluar el impacto.

---

## Resumen de acciones por urgencia

| CF | Título | Urgencia | Esfuerzo |
|----|--------|----------|---------|
| CF-05 | CONTRIBUTING path incorrecto | Inmediata | 5 min |
| CF-01 | RobotsChecker ghost | Alta — antes de demo externa | Medio |
| CF-02 | E11↔E12 swap | Alta — reunión de arquitectura | Bajo (decisión) |
| CF-07 | E05 priority 1050→950 | Alta — afecta cascade hoy | 1 línea |
| CF-09 | E06-E09 priorities | Alta — afecta cascade hoy | 4 líneas |
| CF-03 | E10 spec vs código | Media — Sprint 19 planning | Medio |
| CF-06 | V05-V19 naming | Media — crear mapping doc | Bajo |
| CF-04 | E13 no implementado | Baja — Sprint 8+ | — |
| CF-08 | E12 priority 1500 | Media — verificar Applicable() | Bajo |
| CF-11 | E10 Mobile API ausente | Media — product decision | Alto |
| CF-12 | E11 Tauri client ausente | Media — Phase 4 | Alto |
| CF-13 | Confidence scorer simplificado | Media — crear issue | Bajo |
