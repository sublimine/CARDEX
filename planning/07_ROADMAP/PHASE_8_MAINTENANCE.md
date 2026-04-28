# PHASE_8 — Maintenance & Growth

## Identificador
- ID: P8, Nombre: Maintenance & Growth — Operación sostenida y expansión
- Estado: PENDING
- Dependencias de fases previas: P7 (DONE)
- Fecha de documentación: 2026-04-14

## Propósito y rationale

P8 no tiene criterios de salida — es el estado operativo estable de CARDEX. Una vez P7 está cerrada, el sistema está en producción con compradores B2B activos. P8 define qué significa "mantener bien" el sistema: qué métricas deben sostenerse, qué ciclos de mejora son obligatorios, y cuándo la expansión a nuevos países o mercados está justificada.

La tentación en P8 es añadir features indefinidamente. La disciplina de P8 es mantener lo que existe en estándar institucional mientras se expande solo cuando hay evidencia de que el mercado lo requiere.

## Régimen de operación sostenida

### Métricas en steady state (SLA permanente)

Estas métricas deben cumplirse en todo momento. Un fallo sostenido >48h activa el protocolo de regresión (ver `00_PRINCIPLES.md`):

| Métrica | Threshold | Expresión PromQL / SQL |
|---|---|---|
| API uptime | ≥99.5% (30d rolling) | `avg_over_time(up{job="cardex-api"}[30d]) >= 0.995` |
| Error rate global | <0.3% | `rate(fail_total[30d]) / rate(pass_total[30d]) < 0.003` |
| Discovery freshness | <5% coverage drop en 30d | `cardex_coverage_score >= prev_30d * 0.95` |
| API latency p99 | <2s (mejora de P7) | `histogram_quantile(0.99, rate(duration_bucket[1h])) < 2.0` |
| NLG queue backlog | <1 noche | `cardex_nlg_queue_depth < daily_ingestion_rate` |
| Backup success | 100% (30d) | 0 fallos en rotation log |
| Manual review SLA | <24h, 100% | `pct_within_sla = 100.0` |
| DLQ size | <0.5% de total | `dlq_count / total_vehicles < 0.005` |

### Ciclos de mantenimiento obligatorios

#### Ciclo diario (automatizado)
```
00:30 CET  — NLG batch (systemd timer)
01:30 CET  — Backup incremental a Storage Box (systemd timer)
02:00 CET  — TTL expiration check (systemd timer)
03:00-05:00 — Ventana de deploy CI/CD (si hay cambios)
17:00 CET  — Descarga FX rates ECB (systemd timer)
Continuo   — Discovery ciclo por país (cada 6h por familia)
Continuo   — Extraction queue processing (cada hora)
Continuo   — Quality pipeline (continuo)
```

#### Ciclo semanal (manual)
```
□ Revisar Grafana dashboards: tendencias en las 6 métricas de SLA
□ Revisar manual review queue: items pendientes >12h
□ Revisar DLQ: items con >3 reintentos fallidos → análisis de causa raíz
□ Revisar fail2ban bans: tendencias anómalas
□ Revisar auditd log: accesos inesperados
□ Ejecutar govulncheck: 0 vulnerabilidades conocidas en dependencias Go
```

#### Ciclo mensual (manual)
```
□ Evaluar NPS de buyers activos (encuesta mensual)
□ Revisar coverage score por país vs denominadores P1: ¿hay regresión?
□ Evaluar muestra estratificada de NLG: 50 descripciones × 6 idiomas, escala 1-5
□ Revisar saturation protocol: ¿algún país ha bajado de nivel?
□ Revisar legal incidents log: 0 abiertos
□ Actualizar NHTSA vPIC mirror si hay nueva release mensual
□ Actualizar MaxMind GeoLite2 (actualización mensual)
□ Revisar equipment vocabulary: ≥20 nuevos ítems en unrecognized_items con alta frecuencia?
□ Security checklist completo (ver 09_SECURITY_HARDENING.md)
□ Backup restore test: descargar backup, decrypt, verificar integridad
```

#### Ciclo trimestral (manual)
```
□ Rotación de secrets: API key salt, Grafana admin password (ver 09_SECURITY_HARDENING.md)
□ Revisar scaling path: ¿algún criterio de S0→S1 está cerca del threshold?
□ Revisar competidores (02_COMPETITIVE_LANDSCAPE.md): ¿nuevos entrants relevantes?
□ Revisar denominadores oficiales por país: ¿actualizados con datos del año corriente?
□ Retrospectiva del trimestre: qué ha mejorado, qué ha degradado
```

## Expansión a nuevos países

La expansión a países adicionales (más allá de los 6 iniciales) debe satisfacer:

### Criterios de expansión

```sql
-- Criterio E-8-1: Los 6 países actuales están todos en estándar P6
SELECT COUNT(DISTINCT country_code)
FROM country_status
WHERE coverage_pct >= coverage_threshold
  AND error_rate < 0.003
  AND active_days_since_rollout >= 90;
-- Resultado esperado: 6 (todos los países actuales estables ≥90 días)

-- Criterio E-8-2: Revenue signal o demand evidence para el nuevo mercado
-- (métrica cualitativa — registro de buyers que solicitan explícitamente el nuevo mercado)
SELECT COUNT(*)
FROM buyer_market_request_log
WHERE requested_country = 'UK'  -- ejemplo
  AND created_at > DATETIME('now', '-90 days');
-- Umbral: ≥3 buyers solicitando el mercado (demand evidence)
```

### Proceso de expansión
1. Verificar CE-8-1 y CE-8-2
2. Revisar el marco legal del nuevo mercado (robots.txt prevalentes, legislación aplicable, E11 si EU)
3. Si el nuevo mercado es UK post-Brexit: no EU Data Act, GBP moneda (V15 extensión), GDPR UK equivalente
4. Ejecutar las fases P2→P6 para el nuevo mercado (P1 ya establece el framework analítico)
5. No activar el nuevo mercado hasta que pase su propio gate P6

## Refinamiento continuo

### Mejoras del vocabulario V18 (equipment normalization)
```
Trigger: unrecognized_items con frecuencia > 50 apariciones en 7 días
Acción: añadir al vocabulary YAML con validación humana
Ciclo: semanal
```

### Mejoras del NLG
```
Trigger: human eval mensual < 4.0/5.0 en algún idioma
Acción: revisar prompt template para ese idioma, posible fine-tuning futuro
Ciclo: mensual
```

### Mejoras de validators
```
Trigger: validator fail rate diverge >2x del expected rate (documentado en cada V*.md)
Acción: revisar threshold del validator, recalibrar con nuevos datos
Ciclo: mensual
```

### Ampliación del Edge Client (E11)
```
Trigger: ≥50 dealers han completado E12 (manual) en los últimos 6 meses
Acción: contactar proactivamente a estos dealers para E11 onboarding
Ciclo: trimestral
```

## Criterios de regresión que reabren fases anteriores

| Condición | Fase reabierta | Acción |
|---|---|---|
| Coverage de un país baja >10% en 30 días | P2 (discovery) o P3 (extraction) | Investigar qué familia o estrategia falló; re-ejecutar ciclo |
| Error rate sube >0.5% sostenido 7 días | P4 (quality) | Revisar validators, identificar validator que produce falsos positivos |
| NLG human eval <3.5/5.0 | P4 (NLG) | Revisar prompt templates, modelo, grammar check |
| Incidente legal abierto | P6 del país afectado | Protocolo de respuesta, suspender extracción si necesario |
| API uptime <99% 7 días | P5 (infrastructure) | Escalado S0→S1, o diagnóstico de fallo de servicio |

## Path de monetización (cuando proceda)

P8 es el momento adecuado para introducir revenue si el modelo de negocio lo requiere. Opciones documentadas para cuando el operador decida monetizar:

1. **API key tier B2B** — free tier (100 req/día), pro tier (10.000 req/día, €X/mes), enterprise (unlimited, contrato)
2. **Suscripción de dealer** — dealers pagan por aparecer más prominentemente o por analytics de su propio stock
3. **Datos analíticos** — reportes de mercado por país/make/model a buyers B2B corporativos

La monetización no cambia los criterios de calidad de los datos ni introduce presión para relajar los gates de calidad.

## Indicadores de éxito en P8

CARDEX en P8 tiene éxito cuando:

```sql
-- 6 países activos con coverage sostenida
SELECT COUNT(*) FROM country_status WHERE active = 1;
-- Resultado esperado: 6

-- Buyers activos creciendo o estables
SELECT COUNT(DISTINCT buyer_id) FROM api_usage_log
WHERE created_at > DATETIME('now', '-30 days');
-- Tendencia: estable o creciente

-- 0 incidentes legales abiertos en ningún país
SELECT COUNT(*) FROM legal_incident_log WHERE status = 'OPEN';
-- Resultado esperado: 0

-- Error rate <0.3% sostenido (mejor que el threshold de P7)
-- Expresión en Prometheus
```
