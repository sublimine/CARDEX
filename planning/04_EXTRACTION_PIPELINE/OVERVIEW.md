# Extraction Pipeline — Overview arquitectónico

## Identificador
- Documento: EXTRACTION_PIPELINE_OVERVIEW
- Versión: 1.0
- Fecha: 2026-04-14
- Estado: AUTORITATIVO

## Propósito
El pipeline de extracción convierte el knowledge graph de dealers (producto de las 15 familias de discovery) en registros `vehicle_record` indexados en CARDEX. La extracción opera sobre el site web del dealer o su DMS, respetando robots.txt, con UA identificable, y produciendo únicamente metadatos factuales + punteros URL (modelo índice-puntero, nunca copia de contenido).

## Principio de cascada

El pipeline asigna a cada dealer una o más estrategias en orden de prioridad decreciente. Cada estrategia se evalúa por su `Applicable(dealer)` check rápido antes de intentarla. El orquestador ejecuta la primera estrategia aplicable y, si produce al menos `PartialSuccess`, detiene la cascada. Si falla o produce `FullFailure`, avanza a la siguiente.

```
E01 → E02 → E03 → E04 → E05 → E06 → E07 → E08 → E09 → E10 → E11 → E12
```

Prioridad técnica justificada:
- **E01-E02:** datos ya estructurados en el HTML o API — máxima calidad, mínimo coste, sin riesgo de anti-bot.
- **E03-E04:** índices oficiales (sitemap, RSS) — semi-estructurado, consentimiento implícito por publicación.
- **E05:** plataformas DMS conocidas — APIs predecibles, cobertura alta para ese segmento.
- **E06:** structured data legacy — calidad media, sin dependencies Playwright.
- **E07:** endpoint discovery activo — mayor coste, requiere Playwright.
- **E08-E09:** formatos binarios — parsers especializados, cobertura nichos.
- **E10:** APIs móviles — cobertura muy limitada, alto esfuerzo.
- **E11:** onboarding activo — requiere outreach, días de latencia.
- **E12:** revisión manual — último recurso, SLA humano.

## Matriz estrategia × cobertura × complejidad × dependencias

| ID | Nombre corto | Cobertura estimada | Complejidad impl. | Dep. externas | Requiere Playwright |
|---|---|---|---|---|---|
| E01 | JSON-LD inline | 30-40% dealers modernos | Baja | ninguna | No |
| E02 | CMS REST endpoint | 25-35% (WP ecosystem) | Baja-Media | ninguna | No |
| E03 | Sitemap XML | 60-70% (tienen sitemap) | Baja | ninguna | No |
| E04 | RSS/Atom feeds | 10-15% | Baja | ninguna | No |
| E05 | DMS hosted API | 15-25% (DMS dealers) | Media | DMS providers | No |
| E06 | Microdata/RDFa | 5-10% (legacy sites) | Media | ninguna | No |
| E07 | XHR discovery | 40-55% (SPA/React) | Alta | Playwright | Sí |
| E08 | PDF catalog | 3-5% (nicho) | Alta | pdfplumber, tesseract | No |
| E09 | CSV/Excel | 5-8% | Baja-Media | pandas, openpyxl | No |
| E10 | Mobile app API | <2% | Muy Alta | apktool | No |
| E11 | Edge onboarding | long-tail (post-saturation) | Muy Alta | Tauri client, email | No |
| E12 | Manual review | fallback absoluto | N/A (human) | Equipo humano | No |

**Cobertura acumulada esperada post-cascada completa (E01-E10 automatizados):**
- Dealers con site moderno (WP/Shopify/DMS): ~85% automatizable vía E01-E07.
- Dealers con site estático/legacy sin structured data ni sitemap limpio: ~60% vía E03+E07.
- Dealers sin site o site completamente cerrado: E11 (outreach) o E12 (manual).

## Flujo decisional por dealer

El `ExtractionOrchestrator` determina el orden de intentos basándose en señales de Familia D (CMS fingerprinting) y Familia E (DMS hosted):

```
dealer.PlatformType == "DMS_HOSTED" && dealer.DMSProvider != ""
    → intenta E05 primero (DMS API directa)
    → fallback E03, E07, E12

dealer.CMSDetected == "wordpress" && plugin in KnownRestPlugins
    → intenta E02 primero
    → fallback E01, E03, E07, E12

dealer.CMSDetected in {"shopify", "prestashop", "squarespace"}
    → intenta E01 primero (JSON-LD output nativo)
    → fallback E03, E07, E12

dealer.CMSDetected == "unknown" || dealer.PlatformType == "NATIVE"
    → intenta E01, luego E03, luego E06, luego E07
    → si todos fallan: E08/E09 según Content-Type detection
    → si todo falla: E11

dealer.Domain == "" || dealer.WebStatus == "DOWN"
    → E11 directo (outreach para obtener acceso)
    → E12 si E11 no responde en T_E11
```

## Manejo de errores y fallbacks

### Categorías de fallo

- `STRATEGY_NOT_APPLICABLE` — el `Applicable()` check falla; no se intenta, se pasa a siguiente.
- `STRATEGY_FAILED_TRANSIENT` — error HTTP 5xx, timeout, conexión. Se reintentan hasta 3 veces con backoff exponencial. Si persiste, se continúa con siguiente estrategia.
- `STRATEGY_FAILED_PERMANENT` — robots.txt Disallow, HTTP 403, respuesta vacía consistente, parser error sin datos. No se reintenta en el ciclo actual. Se registra en `extraction_audit` con razón.
- `STRATEGY_PARTIAL_SUCCESS` — algunos campos extraídos pero no todos los críticos (VIN/marca/modelo/precio/URL). Se acepta, se registra `FieldsMissing`, se intenta complementar con la siguiente estrategia en modo "enriquecimiento".

### Dead-letter queue

Los dealers para los que E01-E10 producen `FullFailure` entran en la `dead_letter_queue` con:
- Último error por estrategia intentada
- Señales de diagnóstico (qué se vio en robots.txt, qué status HTTP, si hay JS-rendered page sin datos)
- Priority score (dealer con muchos vehículos estimados → alta prioridad)

La DLQ es el input de E11 (Edge onboarding outreach batch) y E12 (manual review queue).

### Enriquecimiento post-extracción

Si una estrategia extrae datos parciales pero otra complementa con campos faltantes, el orquestador realiza un merge:
- Campos del resultado de mayor prioridad ganan en conflicto
- `SourceURL` se mantiene el de la estrategia primaria (índice-puntero)
- `confidence_score` del vehículo refleja el número de estrategias que lo confirmaron

## Ciclo de re-extracción

Cada dealer tiene un `next_extraction_at` calculado como:
- E01/E02/E05: re-extraer cada 24h (APIs structured → datos cambian frecuentemente)
- E03/E04: re-extraer cada 48h
- E06/E07: re-extraer cada 72h
- E08/E09/E10: re-extraer semanal (datos estáticos)
- E11/E12: re-verificar trimestral

El `fingerprint_sha256` del payload detecta cambios reales vs fetches sin novedad → evita escritura innecesaria en SQLite.

## Métricas globales del pipeline

- `extraction_success_rate(strategy, country)` — % dealers donde estrategia produce resultado
- `mean_vehicles_per_dealer(strategy)` — productividad por estrategia
- `cascade_depth_distribution` — distribución de cuántas estrategias se intentan antes de éxito
- `dead_letter_rate(country)` — % dealers que llegan a E11/E12
- `pipeline_latency_p50_p99` — tiempo medio desde dealer confirmado hasta primer vehículo indexado
