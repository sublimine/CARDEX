# PHASE_2 — Discovery Buildout

## Identificador
- ID: P2, Nombre: Discovery Buildout — Sistema de discovery 15 familias
- Estado: PENDING
- Dependencias de fases previas: P0 (DONE)
- Fecha de documentación: 2026-04-14

## Propósito y rationale

P2 construye el sistema nervioso de CARDEX: el mecanismo que descubre y cataloga todos los dealers profesionales de vehículos de ocasión en los 6 países objetivo. Sin discovery, no hay extracción; sin extracción, no hay índice. P2 es el fundamento sobre el que todo lo demás se asienta.

El objetivo de P2 no es simplemente "que el código corra" — es que el knowledge graph produzca una cobertura verificable contra denominadores reales. La diferencia entre "discovery implementado" y "discovery correcto" es empírica: se mide contra RDW (NL), KBA (DE), y las demás fuentes oficiales documentadas en P1.

## Objetivos concretos

1. Implementar los 15 módulos Go de discovery (familias A-O) conforme a las specs en `03_DISCOVERY_SYSTEM/families/`
2. Implementar el knowledge graph SQLite conforme a `KNOWLEDGE_GRAPH_SCHEMA.md`
3. Implementar la lógica de cross-fertilization conforme a `CROSS_FERTILIZATION.md`
4. Implementar el saturation tracker y su lógica de evaluación por nivel
5. Exponer métricas Prometheus por familia y país desde el primer día
6. Ejecutar el primer ciclo completo en NL (país piloto) y medir cobertura real contra RDW
7. Activar el dashboard Grafana "Coverage Overview" como primera herramienta de monitoring del operador

## Entregables

| Entregable | Verificación |
|---|---|
| 15 módulos `internal/discovery/families/*.go` | Tests ≥80% coverage por módulo |
| `internal/graph/*.go` knowledge graph CRUD | Tests ≥80% coverage |
| `internal/discovery/deduplicator.go` | Tests con casos VAT, domain, name+geo |
| `internal/discovery/saturation.go` | Tests de transición de niveles |
| `cmd/discovery/main.go` con systemd unit | Corre sin errores en VPS staging |
| Métricas Prometheus `:9101/metrics` | Todos los labels de `08_OBSERVABILITY.md` presentes |
| Dashboard "Coverage Overview" importado en Grafana | Screenshots en retrospectiva |
| Primer ciclo NL ejecutado | Datos en knowledge graph, coverage ratio calculado |

## Criterios cuantitativos de salida

### CS-2-1: 15/15 familias implementadas con tests ≥80% coverage

```bash
# Verificar que existen 15 módulos
ls internal/discovery/families/ | grep -c "\.go$"
# Resultado esperado: ≥15

# Coverage por módulo (ejecutado en CI)
go test -coverprofile=cov.out ./internal/discovery/families/...
go tool cover -func=cov.out | awk '{if ($3+0 < 80.0) print $0}'
# Resultado esperado: (vacío — todos ≥80%)
```

### CS-2-2: Cobertura cruzada ≥3 fuentes para ≥80% de dealers en país piloto (NL)

```sql
-- Requiere primer ciclo completo ejecutado en NL
SELECT
  ROUND(
    COUNT(CASE WHEN source_count >= 3 THEN 1 END) * 100.0 / COUNT(*), 2
  ) AS pct_with_3_sources
FROM (
  SELECT dealer_id, COUNT(DISTINCT family_id) AS source_count
  FROM discovery_record
  WHERE country_code = 'NL'
    AND dealer_id IN (SELECT dealer_id FROM dealer_entity WHERE status = 'ACTIVE')
  GROUP BY dealer_id
);
-- Resultado esperado: ≥80.0
```

### CS-2-3: Health-check de 15 familias >95%

```promql
# Porcentaje de familias que completaron su último ciclo sin error
avg(
  rate(cardex_discovery_errors_total[24h]) == 0
) by (family) >= 0.95
```

Expresado como query SQL alternativa:

```sql
SELECT
  ROUND(
    COUNT(CASE WHEN last_error IS NULL OR last_success_at > last_error_at THEN 1 END) * 100.0
    / COUNT(*), 2
  ) AS health_pct
FROM discovery_family_health
WHERE country_code = 'NL';
-- Resultado esperado: ≥95.0
```

### CS-2-4: Cobertura del knowledge graph vs denominador oficial NL

```sql
-- El denominador oficial NL viene de P1 (RDW + KvK data)
SELECT
  de.total_dealers AS kg_count,
  md.denominator_dealers AS official_denominator,
  ROUND(de.total_dealers * 100.0 / md.denominator_dealers, 2) AS coverage_pct
FROM (SELECT COUNT(*) AS total_dealers FROM dealer_entity WHERE country_code='NL' AND status='ACTIVE') de
CROSS JOIN (SELECT denominator_dealers FROM market_denominator WHERE country_code='NL') md;
-- No hay threshold fijo para este criterio — se documenta el valor real como denominador de referencia para P6
-- El criterio binario es: coverage_pct IS NOT NULL (el cálculo puede ejecutarse)
```

### CS-2-5: Saturation protocol operativo

```sql
-- Verificar que el saturation tracker registra ciclos
SELECT COUNT(*) FROM saturation_cycle_log
WHERE country_code = 'NL'
AND completed_at IS NOT NULL;
-- Resultado esperado: ≥3 (al menos 3 ciclos completados en NL)
```

### CS-2-6: Deduplicador sin duplicados en knowledge graph

```sql
-- No deben existir dealers duplicados por VAT
SELECT primary_vat, COUNT(*) AS cnt
FROM dealer_entity
WHERE primary_vat IS NOT NULL
GROUP BY primary_vat
HAVING cnt > 1;
-- Resultado esperado: (vacío — 0 filas)

-- No deben existir dealers duplicados por dominio
SELECT domain, COUNT(*) AS cnt
FROM dealer_web_presence
GROUP BY domain
HAVING cnt > 1;
-- Resultado esperado: (vacío — 0 filas)
```

## Métricas de progreso intra-fase

| Métrica | PromQL / SQL | Objetivo |
|---|---|---|
| Familias implementadas | `ls internal/discovery/families/*.go \| wc -l` | 15/15 |
| Coverage promedio tests | `go tool cover` | ≥80% por módulo |
| Dealers en KG (NL) | `SELECT COUNT(*) FROM dealer_entity WHERE country='NL'` | Crece monotónicamente |
| Familias con health=OK | CS-2-3 expression | ≥95% |
| Ciclos de saturación completados | CS-2-5 expression | ≥3 en NL |
| Duplicados VAT | CS-2-6 expression | 0 |

## Actividades principales

1. **Setup del knowledge graph** — crear schema SQLite (`KNOWLEDGE_GRAPH_SCHEMA.md`), migrations, CRUD básico
2. **Implementar familias de mayor rendimiento primero** — orden recomendado por ROI:
   - A (plataformas nacionales) → E (sitios propios, sitemaps) → B/C (registros oficiales) → G/H (maps/OEMs) → resto
3. **Implementar deduplicador** con los 5 mecanismos: VAT match, domain match, normalized_name+geo, phone, Place-ID
4. **Implementar cross-fertilization** — función `confidence_score` con pesos por familia y decaimiento temporal
5. **Implementar saturation tracker** — 4 niveles según `SATURATION_PROTOCOL.md`
6. **Exponer métricas Prometheus** — desde el primer deploy, no post-hoc
7. **Ejecutar primer ciclo NL** — pilot run completo, analizar resultados contra RDW
8. **Configurar dashboard Coverage Overview** — importar en Grafana, verificar paneles
9. **Iterar sobre familias con cobertura baja** hasta cumplir CS-2-2
10. **Retrospectiva** — ejecutar todos los criterios CS-2-* y documentar

## Dependencias externas

- P0 completa (código sin técnicas ilegales — el crawler usa CardexBot/1.0)
- P1 completa o en progreso avanzado (denominadores necesarios para CS-2-4)
- Acceso a VIES (validación VAT batch) — gratuito
- Acceso a RDW data API o dataset público NL — gratuito
- SearXNG self-hosted corriendo (para familia K)
- VPS staging disponible para pruebas (puede ser VPS temporal distinto del de producción)

## Riesgos específicos de la fase

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Denominador oficial NL no suficientemente granular para validar cobertura | BAJA | MEDIA | RDW tiene datos VIN-level, alta granularidad. Si hay restricciones de acceso, usar KvK (cámara de comercio) como proxy |
| Familia N (infra intelligence) con recursos externos limitados (Censys 250 req/mes) | ALTA | BAJA | Diseñar N para usar primariamente crt.sh (ilimitado) + BGP.he.net; Censys solo para casos que crt.sh no resuelve |
| Deduplicador produce falsos positivos (fusion de dealers distintos) | MEDIA | ALTA | Tests con casos edge documentados; umbral conservador para merge automático; candidatos a fusión van a manual review |
| Familia B (registros mercantiles) con acceso limitado en algunos países | MEDIA | MEDIA | Handelsregister DE tiene API; INFOGREFFE FR requiere suscripción (plan gratuito limitado); documentar limitaciones en retrospectiva |

## Retrospectiva esperada

Al cerrar P2, evaluar:
- Cobertura real obtenida en NL vs denominador RDW — ¿es el porcentaje esperado razonable o sorprendente?
- ¿Qué familias producen el mayor volumen de dealers únicos? ¿Coincide con las predicciones de base_weights de CROSS_FERTILIZATION.md?
- ¿El deduplicador ha producido falsos positivos o falsos negativos detectados en revisión manual?
- ¿Los 3 ciclos de NL muestran convergencia o aún hay delta significativo?
- ¿Qué familias tienen health <95% y por qué?
