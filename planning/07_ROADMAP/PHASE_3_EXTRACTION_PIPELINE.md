# PHASE_3 — Extraction Pipeline

## Identificador
- ID: P3, Nombre: Extraction Pipeline — E01-E12 + Edge Client
- Estado: PENDING
- Dependencias de fases previas: P2 (DONE)
- Fecha de documentación: 2026-04-14

## Propósito y rationale

Con el knowledge graph poblado (P2), P3 construye el sistema que extrae el inventario de vehículos de cada dealer. P3 convierte el catálogo de dealers del knowledge graph en un catálogo de vehículos raw — sin validar, sin normalizar, pero estructurado para que el pipeline de calidad pueda procesarlos.

La implementación de P3 confirma o refuta las hipótesis sobre qué estrategias de extracción son aplicables a qué tipos de dealers. La distribución real de estrategias en el knowledge graph es información que P3 produce y que calibra el diseño de P4.

## Objetivos concretos

1. Implementar los 12 módulos Go de extracción (E01-E12) conforme a las specs en `04_EXTRACTION_PIPELINE/`
2. Implementar el orquestador de cascada (`ExtractionOrchestrator`) con priorización correcta
3. Implementar `PlaywrightRunner` con CardexBot/1.0 UA y cero técnicas de evasión
4. Implementar el `RateLimiter` por dominio con respeto de `robots.txt`
5. Implementar el Edge Client Tauri MVP (E11) — formulario de autenticación + envío de inventario
6. Implementar la Manual Review UI para E12 (React SPA local)
7. Ejecutar extracción completa en NL (país piloto) con el knowledge graph de P2
8. Medir tasa de éxito real por estrategia para calibrar el modelo

## Entregables

| Entregable | Verificación |
|---|---|
| 12 módulos `internal/extraction/strategies/*.go` | Tests sobre dataset estratificado |
| `internal/extraction/orchestrator.go` | Test de cascada correcta |
| `internal/extraction/playwright.go` | Test de UA correcto, sin stealth |
| `internal/extraction/rate_limiter.go` | Test de respeto de Crawl-Delay |
| `cmd/extraction/main.go` con systemd unit | Corre sin errores en VPS staging |
| Edge Client Tauri MVP (`edge-client/`) | Deployado en ≥3 dealers piloto |
| Manual Review UI (`frontend/review/`) | Operador puede aprobar/rechazar via UI |
| Métricas Prometheus `:9102/metrics` | Todos los labels de `08_OBSERVABILITY.md` presentes |
| Dataset de resultados NL | vehicle_raw records en SQLite para P4 |

## Criterios cuantitativos de salida

### CS-3-1: ≥95% dealers en KG con ≥1 estrategia exitosa asignada

```sql
SELECT
  ROUND(
    COUNT(CASE WHEN last_successful_strategy IS NOT NULL THEN 1 END) * 100.0
    / COUNT(*), 2
  ) AS pct_with_strategy
FROM dealer_entity
WHERE status = 'ACTIVE'
  AND country_code = 'NL';
-- Resultado esperado: ≥95.0
```

### CS-3-2: ≥80% de campos críticos extraídos por vehículo procesado

```sql
-- Campos críticos: VIN, make, model, year, mileage, price, source_url, ≥1 image_url
SELECT
  ROUND(
    COUNT(CASE WHEN
      make IS NOT NULL AND model IS NOT NULL AND year IS NOT NULL
      AND mileage IS NOT NULL AND (price_net IS NOT NULL OR price_gross IS NOT NULL)
      AND source_url IS NOT NULL
    THEN 1 END) * 100.0 / COUNT(*), 2
  ) AS pct_critical_fields_complete
FROM vehicle_raw
WHERE dealer_id IN (SELECT dealer_id FROM dealer_entity WHERE country_code='NL');
-- Resultado esperado: ≥80.0
```

### CS-3-3: Tests sobre dataset estratificado (10 dealers × familia × país piloto)

```bash
# Dataset de integración: debe existir y tests deben pasar
ls testdata/extraction/nl_stratified/
# Resultado esperado: 10 directorios (uno por familia aplicable)

go test -v -tags=integration -run TestExtractionStratified \
  ./tests/integration/extraction/...
# Resultado esperado: todos los tests PASS
```

### CS-3-4: Edge Client deployado en ≥3 dealers piloto activos

```sql
SELECT COUNT(*)
FROM dealer_entity
WHERE source_primary = 'E11'
  AND status = 'ACTIVE'
  AND edge_client_version IS NOT NULL
  AND last_edge_sync > DATETIME('now', '-7 days');
-- Resultado esperado: ≥3
```

### CS-3-5: CardexBot UA en 100% de peticiones HTTP (validado por logs)

```sql
-- Todos los access_log entries del extractor deben tener CardexBot UA
SELECT
  ROUND(
    COUNT(CASE WHEN user_agent LIKE 'CardexBot%' THEN 1 END) * 100.0
    / COUNT(*), 2
  ) AS pct_cardexbot
FROM extraction_access_log
WHERE created_at > DATETIME('now', '-1 day');
-- Resultado esperado: 100.0
```

### CS-3-6: 0 violaciones de robots.txt en logs de extracción

```sql
SELECT COUNT(*)
FROM extraction_access_log
WHERE robots_txt_violation = 1
  AND created_at > DATETIME('now', '-7 days');
-- Resultado esperado: 0
```

### CS-3-7: Rate limiter activo — 0 HTTP 429 en últimas 48h (señal de flood)

```promql
sum(increase(cardex_extraction_failure_total{reason="http_429"}[48h])) == 0
```

## Métricas de progreso intra-fase

| Métrica | Expresión | Objetivo |
|---|---|---|
| Estrategias implementadas | `ls internal/extraction/strategies/*.go \| wc -l` | 12/12 |
| Dealers con estrategia asignada (NL) | CS-3-1 | ≥95% |
| Campos críticos completos | CS-3-2 | ≥80% |
| Edge clients activos | CS-3-4 | ≥3 |
| Tasa de éxito por estrategia | `rate(cardex_extraction_success_total[24h])` | Medida, no threshold |
| Violations robots.txt | CS-3-6 | 0 |

## Actividades principales

1. **Implementar estrategias sin red primero** — E01 (JSON-LD), E02 (WP REST), E06 (Microdata), E09 (CSV/XLSX) son las más simples de testear con fixtures locales
2. **Implementar E03 (sitemaps)** — requiere HTTP básico; probar contra sitemaps reales de dealers NL
3. **Implementar E07 (Playwright)** — la más delicada; verificar UA correcto, sin stealth, con rate limiting
4. **Implementar E04 (RSS/Atom) y E05 (DMS endpoints)** — requiere conocimiento de los providers de P1
5. **Implementar E08 (PDFs) y E10 (APK)** — casos edge, implementar para completitud pero prioridad baja
6. **Implementar E11 (Edge onboarding)** — Tauri client MVP: OAuth dealer + endpoint seguro de envío de inventario
7. **Implementar E12 (manual review queue)** — UI React mínima, operador puede ver dealers en cola y resolver
8. **Implementar orquestador** con cascada correcta y NATS integration
9. **Ejecutar en NL** — extraer inventario de todos los dealers del KG de P2
10. **Analizar distribución de estrategias** — qué porcentaje de dealers resuelve con E01, E02, etc.
11. **Iterar estrategias con baja cobertura** hasta cumplir CS-3-1
12. **Retrospectiva** con datos reales de distribución

## Dependencias externas

- P2 DONE (knowledge graph con dealers NL)
- P0 DONE (sin código stealth — E07 usa Playwright transparente)
- Playwright binaries instalados en VPS staging
- LanguageTool self-hosted running (para E11 outreach emails si aplica)
- Forgejo CI con illegal-pattern scan activo

## Riesgos específicos de la fase

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| E07 (Playwright) detectado y bloqueado por sitio aunque usa CardexBot UA legítimo | MEDIA | MEDIA | Solución: respetar si el sitio bloquea explícitamente bots identificados; ese dealer pasa a E11 o E12 |
| E05 (DMS providers) con endpoints que cambian sin aviso | ALTA | MEDIA | Versionar el registry de endpoints por provider; alertar cuando endpoint retorna error estructural nuevo |
| Tauri Edge Client rechazado por antivirus o políticas IT del dealer | MEDIA | BAJA | Firmar el binario con certificado de desarrollador; documentar el proceso de excepción IT |
| Dataset de testdata insuficiente para representar variedad real | MEDIA | MEDIA | Usar fixtures anonimizados de datos reales del ciclo NL; nunca datos de producción en CI |
| Dealer con inventario grande (>5.000 vehículos) satura la queue de quality | BAJA | MEDIA | Rate limiting en el orquestador; los dealers grandes se procesan en múltiples ciclos |

## Retrospectiva esperada

Al cerrar P3, evaluar:
- Distribución real de estrategias por dealer en NL: ¿qué porcentaje resolvió con E01, E02, E07, E11, E12?
- ¿La tasa de éxito de campos críticos (CS-3-2) es uniforme por estrategia o hay estrategias con baja completitud?
- ¿El Edge Client fue bien recibido por los 3 dealers piloto? ¿Qué fricción hubo en el proceso de onboarding?
- ¿Algún dealer tuvo que ir a E12 (manual) por razones no previstas?
- ¿La distribución de estrategias en NL es consistente con las predicciones de cobertura del OVERVIEW de extracción?
