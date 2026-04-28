# Definition of Done — MVP Institucional

## Identificador
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito

Este documento define cuándo CARDEX ha alcanzado el estado de **MVP institucional completo** — el punto en que el sistema opera de forma autónoma, confiable, legal, y con valor verificado para los compradores B2B. No es el fin del proyecto (P8 continúa indefinidamente), sino el fin de la fase de construcción.

El MVP institucional no es un "producto mínimo" en el sentido de compromiso de calidad. Es el sistema completo operando en estándar institucional en los 6 mercados objetivo.

> **Nota sobre tablas operacionales:** Las tablas `country_status_view`, `market_denominator`, `buyer_nps_survey`, `legal_incident_log`, `operations_log`, `ci_pipeline_log`, `legal_audit_findings` referenciadas en los criterios D-1 a D-9 no forman parte del Knowledge Graph definido en `03_DISCOVERY_SYSTEM/KNOWLEDGE_GRAPH_SCHEMA.md`. Son tablas operacionales que se definen e implementan en P5 (Infrastructure). Su schema exacto se documentará en `06_ARCHITECTURE/` durante P5.

---

## Criterios del MVP Institucional

### D-1: 6 países activos al estándar institucional

```sql
-- Todos los criterios del gate P6 cumplidos para los 6 países, sostenidos ≥90 días
SELECT
  country_code,
  CASE
    WHEN coverage_pct >= coverage_threshold
     AND error_rate < 0.003
     AND freshness_sla_pct >= 99.0
     AND open_legal_incidents = 0
     AND open_valid_complaints = 0
     AND nlg_coverage_pct >= 95.0
    THEN 'DONE'
    ELSE 'NOT_DONE'
  END AS status,
  active_days
FROM country_status_view
WHERE country_code IN ('NL', 'DE', 'FR', 'ES', 'BE', 'CH')
  AND active_days >= 90;
-- Resultado esperado: 6 filas, todas con status = 'DONE'
```

### D-2: Knowledge graph con cobertura auditable

```sql
-- La cobertura del knowledge graph puede calcularse contra denominadores oficiales
-- con una query y no requiere trabajo manual de verificación
SELECT
  de.country_code,
  COUNT(DISTINCT de.dealer_id) AS dealers_active,
  md.denominator_dealers AS official_denominator,
  ROUND(COUNT(DISTINCT de.dealer_id) * 100.0 / md.denominator_dealers, 2) AS coverage_pct,
  md.source_url  -- fuente oficial verificable
FROM dealer_entity de
JOIN market_denominator md ON de.country_code = md.country_code
WHERE de.status = 'ACTIVE'
GROUP BY de.country_code, md.denominator_dealers, md.source_url;
-- Resultado esperado: 6 filas, todas con coverage_pct calculado y source_url no nulo
```

### D-3: Error rate <0.3% sostenido ≥60 días

```promql
# Error rate global del quality pipeline (más estricto que el threshold de P6 de 0.5%)
avg_over_time(
  (
    rate(cardex_quality_validator_fail_total{severity="BLOCKING"}[24h])
    / rate(cardex_quality_validator_pass_total[24h])
  )[60d:]
) < 0.003
```

### D-4: NPS buyers ≥ T_NPS sostenido ≥3 meses

```sql
-- NPS de compradores B2B activos, medición mensual, ≥3 meses consecutivos por encima del threshold
SELECT
  survey_month,
  ROUND(
    (COUNT(CASE WHEN nps_score >= 9 THEN 1 END) -
     COUNT(CASE WHEN nps_score <= 6 THEN 1 END)) * 100.0
    / COUNT(*), 0
  ) AS nps_score,
  COUNT(*) AS respondents
FROM buyer_nps_survey
GROUP BY survey_month
ORDER BY survey_month DESC
LIMIT 3;
-- Resultado esperado: 3 filas, nps_score ≥ T_NPS en las 3, respondents ≥ 10
```

### D-5: 0 incidentes legales abiertos en ningún país

```sql
SELECT COUNT(*)
FROM legal_incident_log
WHERE status = 'OPEN';
-- Resultado esperado: 0
```

### D-6: CI/CD pipeline operativa con 0 intervenciones manuales en 30 días

```sql
-- El pipeline de CI/CD ha ejecutado deploys sin intervenciones manuales
SELECT COUNT(*)
FROM operations_log
WHERE action IN ('manual_deploy', 'manual_restart', 'manual_hotfix')
  AND created_at > DATETIME('now', '-30 days');
-- Resultado esperado: 0
```

```sql
-- Y el illegal-pattern scanner ha estado activo sin fallos en 30 días
SELECT COUNT(*)
FROM ci_pipeline_log
WHERE step = 'illegal-pattern-scan'
  AND status = 'FAILED_TO_RUN'  -- distinto de FAILED_PATTERN_FOUND — queremos que corra
  AND created_at > DATETIME('now', '-30 days');
-- Resultado esperado: 0
```

### D-7: Runbook operacional testeado con ≥2 simulacros

```bash
# Simulacros de restore documentados
ls docs/backup-restore-test-*.md | wc -l
# Resultado esperado: ≥2

# Simulacro de failover documentado
ls docs/failover-drill-*.md | wc -l
# Resultado esperado: ≥1

# Cada documento tiene fecha y resultado (SUCCESS/FAILURE)
grep -h "Result:" docs/backup-restore-test-*.md docs/failover-drill-*.md
# Resultado esperado: todas las líneas dicen "Result: SUCCESS"
```

### D-8: Observabilidad end-to-end operativa

```promql
# Los 6 dashboards de Grafana tienen datos frescos (<1h) en todos sus paneles
# (verificación manual — Grafana no tiene endpoint de "todos los paneles tienen datos")
# Criterio binario: operador confirma en retrospectiva que todos los dashboards muestran datos
```

```sql
-- Prometheus scrapea todos los endpoints de métricas
SELECT COUNT(*)
FROM prometheus_targets_up  -- vista de la API de Prometheus /api/v1/targets
WHERE health = 'down';
-- Resultado esperado: 0
```

### D-9: Auditoría legal completada sin findings bloqueantes

```sql
SELECT COUNT(*)
FROM legal_audit_findings
WHERE severity = 'BLOCKING'
  AND status != 'RESOLVED';
-- Resultado esperado: 0
```

### D-10: Scaling path documentado y primeros triggers monitorizados

```promql
# Los criterios de S0→S1 del scaling path están siendo monitorizados activamente
# (no han sido triggereados aún — o si lo han sido, S1 está en curso)
(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes)
/ node_memory_MemTotal_bytes
# Este valor es visible en Grafana (criterio: está en el dashboard VPS Resources)
```

---

## Tabla consolidada del MVP

| # | Criterio | Expresión | Threshold | Verificación |
|---|---|---|---|---|
| D-1 | 6 países ACTIVE ≥90 días | SQL country_status_view | 6/6 = 'DONE' | Automática |
| D-2 | Cobertura auditable vs denominadores | SQL coverage query | source_url NOT NULL × 6 | Automática |
| D-3 | Error rate <0.3% (60d) | PromQL avg_over_time | <0.003 | Automática |
| D-4 | NPS ≥T_NPS (3 meses) | SQL nps_survey | ≥T_NPS × 3 meses | Manual encuesta |
| D-5 | 0 incidentes legales abiertos | SQL legal_incident_log | 0 | Automática |
| D-6 | CI/CD sin intervenciones (30d) | SQL operations_log | 0 | Automática |
| D-7 | Runbook con ≥2 simulacros OK | bash ls + grep | SUCCESS × 3 docs | Manual |
| D-8 | Observabilidad end-to-end | PromQL targets + manual | 0 down + dashboards OK | Semi-manual |
| D-9 | Auditoría legal sin bloqueantes | SQL legal_audit_findings | 0 BLOCKING OPEN | Automática |
| D-10 | Scaling path monitorizando | PromQL RAM visible | En Grafana | Manual |

---

## Declaración formal de MVP

Cuando los 10 criterios están cumplidos simultáneamente, el operador (Salman) firma la siguiente declaración:

```markdown
---
DECLARACIÓN DE MVP INSTITUCIONAL CARDEX
Fecha: [YYYY-MM-DD]
Operador: Salman

Los 10 criterios del DEFINITION_OF_DONE.md han sido verificados
instrumentalmente. El sistema CARDEX cumple el estándar institucional
de MVP en los 6 mercados objetivo (DE/FR/ES/BE/NL/CH).

La construcción del MVP está completa. El sistema entra en régimen
de operación sostenida (PHASE_8).

Firma: _______________
---
```

---

## Lo que el MVP *no* incluye

Para evitar ambigüedad sobre el alcance del MVP, esto explícitamente **no** es parte del Definition of Done:

- **Monetización activa** — el MVP valida el producto, no el modelo de ingresos
- **UI web para compradores** — el MVP es API-first; la UI web es una iteración futura
- **Soporte multiidioma del dashboard** — el dashboard es para el operador (Salman), que habla español
- **Cobertura ≥80% en todos los países** — los thresholds de coverage son los de P6, no una cobertura "completa" (que quizás sea imposible por denominadores)
- **Procesamiento de vehículos clásicos/colección** — el mercado objetivo es vehículos de ocasión estándar 2000-2026
- **Integración con DMS de dealer en tiempo real** — E11 es batch/periódico, no en tiempo real
- **SLA contractual con los buyers** — el MVP no incluye contratos de nivel de servicio; eso viene con la monetización