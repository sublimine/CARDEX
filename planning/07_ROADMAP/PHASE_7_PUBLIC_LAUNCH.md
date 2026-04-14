# PHASE_7 — Public Launch

## Identificador
- ID: P7, Nombre: Public Launch — Soft launch + apertura pública
- Estado: PENDING
- Dependencias de fases previas: P6 DONE para ≥1 país (NL suficiente para soft launch)
- Fecha de documentación: 2026-04-14

## Propósito y rationale

P7 introduce a compradores B2B reales al sistema. El "launch" no es un evento puntual sino un proceso iterativo: primero un grupo reducido de buyers piloto con acceso controlado, luego iteración sobre su feedback, luego apertura a un universo mayor. La apertura pública no ocurre hasta que las métricas operativas demuestren estabilidad prolongada y la auditoría legal ha validado el modelo de negocio.

La diferencia entre P6 y P7 es que P6 valida el sistema internamente (el operador verifica los datos) y P7 valida el sistema externamente (los buyers verifican el valor). Un sistema que pasa P6 pero falla P7 tiene un problema de producto, no de calidad de datos.

## Objetivos concretos

1. Identificar y contactar ≥10 buyers B2B piloto (dealers importadores, gestores de flota, revendedores B2B)
2. Proveer acceso controlado a la API con API keys de test
3. Recopilar feedback estructurado: NPS, errores encontrados, features solicitadas
4. Resolver ≥80% del feedback actionable antes de apertura pública
5. Mantener métricas operativas estables 60 días consecutivos
6. Obtener auditoría legal del modelo de negocio (validación robots.txt compliance, EU Data Act, GDPR)
7. Apertura pública: acceso a la API para buyers adicionales con onboarding self-service

## Entregables

| Entregable | Verificación |
|---|---|
| ≥10 buyers piloto activos con acceso API | `SELECT COUNT(*) FROM api_key WHERE status='active' AND buyer_type='pilot'` ≥10 |
| NPS survey implementado | Tool o proceso de encuesta documentado |
| Feedback backlog resuelto ≥80% | Tracker de issues con estado |
| Auditoría legal completada | Documento firmado por asesor legal o autoevaluación detallada |
| Métricas estables 60 días | CS-7-3 PromQL |
| Documentación pública API | OpenAPI spec + guía de inicio |
| Onboarding self-service | Proceso de solicitud de API key documentado y funcional |

## Criterios cuantitativos de salida

### CS-7-1: ≥10 buyers piloto activos con uso real

```sql
SELECT COUNT(DISTINCT buyer_id)
FROM api_usage_log
WHERE created_at > DATETIME('now', '-7 days')
  AND request_count > 0
  AND buyer_type = 'pilot';
-- Resultado esperado: ≥10
```

### CS-7-2: NPS ≥T_NPS calibrado sobre muestra piloto

```sql
-- NPS = % Promotores (score 9-10) - % Detractores (score 0-6)
SELECT
  ROUND(
    (COUNT(CASE WHEN nps_score >= 9 THEN 1 END) -
     COUNT(CASE WHEN nps_score <= 6 THEN 1 END)) * 100.0
    / COUNT(*), 0
  ) AS nps_score
FROM buyer_nps_survey
WHERE survey_date > DATETIME('now', '-30 days');
-- T_NPS provisional: ≥20 (ajustar tras primera encuesta)
-- NPS de 20+ indica más promotores que detractores — umbral mínimo viable
```

### CS-7-3: Métricas operativas estables 60 días consecutivos

```promql
# API uptime 60 días
avg_over_time(up{job="cardex-api"}[60d]) >= 0.99

# Error rate bajo
avg_over_time(
  rate(cardex_quality_validator_fail_total{severity="BLOCKING"}[24h]) /
  rate(cardex_quality_validator_pass_total[24h])
  [60d]
) <= 0.005

# Latencia API p99 bajo control
avg_over_time(
  histogram_quantile(0.99, rate(cardex_api_query_duration_seconds_bucket[1h]))
  [60d]
) <= 3.0
```

### CS-7-4: ≥80% del feedback actionable resuelto antes de apertura

```sql
SELECT
  ROUND(
    COUNT(CASE WHEN status = 'RESOLVED' THEN 1 END) * 100.0
    / COUNT(CASE WHEN is_actionable = 1 THEN 1 END), 2
  ) AS pct_feedback_resolved
FROM buyer_feedback_log
WHERE source = 'pilot'
  AND is_actionable = 1;
-- Resultado esperado: ≥80.0
```

### CS-7-5: Auditoría legal completada sin bloqueantes

```sql
SELECT COUNT(*)
FROM legal_audit_findings
WHERE severity = 'BLOCKING'
  AND status != 'RESOLVED';
-- Resultado esperado: 0
```

### CS-7-6: OpenAPI spec publicada y funcional

```bash
# OpenAPI spec existe y es válida
npx @apidevtools/swagger-cli validate docs/api/openapi.yaml
# Resultado esperado: exit code 0

# Al menos los endpoints críticos documentados
grep -c "^  /api/vehicles" docs/api/openapi.yaml
# Resultado esperado: ≥3 (GET /vehicles, GET /vehicles/{id}, GET /vehicles/vin/{vin})
```

## Métricas de progreso intra-fase

| Métrica | Expresión | Objetivo |
|---|---|---|
| Buyers piloto activos | CS-7-1 | ≥10 |
| NPS | CS-7-2 | ≥T_NPS |
| Uptime 60d | CS-7-3 promql | ≥99% |
| Feedback actionable resuelto | CS-7-4 | ≥80% |
| Findings legales bloqueantes | CS-7-5 | 0 |
| API queries/día (crecimiento) | `rate(cardex_api_requests_total[24h])` | Crece monotónicamente |

## Actividades principales

### Soft launch (buyers piloto)
1. **Identificar buyers piloto** — dealers importadores activos en NL/DE, gestores de flota conocidos del sector; outreach directo por el operador
2. **Proceso de onboarding piloto** — API key manual, briefing sobre las capacidades del índice, hoja de feedback
3. **Soporte activo** — el operador responde preguntas en <4h durante el período piloto
4. **Recogida de feedback** — encuesta NPS quincenal, canal de feedback directo (email/ticket)
5. **Triage de feedback** — clasificar como actionable/no-actionable, priorizar, resolver en sprints

### Preparación apertura pública
6. **Redactar OpenAPI spec** — documentar todos los endpoints con ejemplos de request/response
7. **Proceso self-service de API key** — formulario de solicitud, review del operador, aprobación en <48h
8. **Auditoría legal** — revisar robots.txt compliance de todos los targets activos, GDPR (no hay datos personales de individuos — solo dealers que son empresas), EU Data Act compliance para E11
9. **Terms of Service para buyers** — redactar ToS de acceso a la API
10. **Apertura pública** — anuncio en canales del sector, activar onboarding self-service

### Post-apertura
11. **Monitorizar** — dashboards Grafana, alertas, NPS mensual
12. **Iterar** — feedback de nuevos buyers → mejoras al producto

## Dependencias externas

- P6 DONE para ≥1 país (NL)
- Red de contactos del operador en el sector B2B para encontrar buyers piloto
- Asesor legal (o capacidad de autoevaluación legal detallada) para la auditoría
- Dominio público + TLS activo (de P5)

## Riesgos específicos de la fase

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Buyers piloto no dan feedback estructurado | ALTA | MEDIA | Hacer el proceso de feedback tan sencillo como sea posible; NPS de una sola pregunta + campo abierto |
| NPS bajo (<20) por razones no relacionadas con calidad de datos | MEDIA | ALTA | Investigar qué aspectos del producto generan detracción: si es UI, precio, velocidad de actualización; no asumir que es calidad de datos |
| Auditoría legal revela problemas con el modelo de extracción | BAJA | ALTA | La auditoría se hace antes de la apertura pública; si hay hallazgos, P7 se pausa hasta resolver |
| Carga de API de buyers piloto excede capacidad del VPS S0 | BAJA | MEDIA | Rate limiting por API key (1.000 req/hora); si se agota, upgrade a CX51 o activar S1 |
| Competidor lanza producto similar durante P7 | BAJA | MEDIA | CARDEX tiene ventaja de tiempo; la respuesta correcta es acelerar la apertura pública, no retrasar |

## Retrospectiva esperada

Al cerrar P7 (apertura pública activa y métricas estables 60 días):
- ¿Qué fue lo que más valoraron los buyers piloto? ¿Coincide con las hipótesis del diseño?
- ¿Qué fue lo más criticado? ¿Era anticipado?
- ¿El NPS inicial fue el esperado? ¿Qué lo mueve más: cobertura, precisión de datos, o latencia de actualización?
- ¿La auditoría legal encontró algo que requiriera cambios de diseño?
- ¿El volumen de queries de los buyers piloto fue suficiente para estresar el sistema?
