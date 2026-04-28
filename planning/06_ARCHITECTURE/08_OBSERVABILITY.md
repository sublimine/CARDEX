# 08 — Observability

## Identificador
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Principios

1. **Metrics-first:** cada servicio expone `/metrics` en Prometheus format desde el primer deploy
2. **Alert on symptoms, not causes:** las alertas disparan sobre efectos observables (coverage drop, queue depth) no sobre causas internas
3. **Dashboard por audiencia:** dashboards diferenciados para operación diaria vs auditoría legal vs debugging de pipeline
4. **No datos personales en métricas:** los labels de Prometheus nunca contienen VINs, emails, ni identificadores de personas

---

## Catálogo de Métricas Prometheus

### Discovery Service (:9101/metrics)

```prometheus
# Dealers descubiertos por familia y país
cardex_discovery_dealers_discovered_total{family="A",country="DE"} 1234
cardex_discovery_dealers_discovered_total{family="K",country="FR"} 892

# Delta por ciclo (nuevos vs actualizaciones vs sin cambio)
cardex_discovery_cycle_delta{action="created",country="DE"} 23
cardex_discovery_cycle_delta{action="merged",country="DE"} 156
cardex_discovery_cycle_delta{action="unchanged",country="DE"} 1055

# Duración de ciclo por familia
cardex_discovery_family_duration_seconds{family="E",country="DE"} 1823.4

# Tasa de saturación por país (0.0-1.0)
cardex_discovery_saturation_score{country="DE"} 0.73
cardex_discovery_saturation_score{country="CH"} 0.31

# Errores por familia (HTTP timeouts, parse errors, etc.)
cardex_discovery_errors_total{family="N",error="timeout"} 12
cardex_discovery_errors_total{family="M",error="vies_unavailable"} 3

# Tamaño del knowledge graph
cardex_knowledge_graph_dealers_total{status="ACTIVE"} 8234
cardex_knowledge_graph_dealers_total{status="DORMANT"} 1203
cardex_knowledge_graph_dealers_total{status="CLOSED"} 421
```

### Extraction Service (:9102/metrics)

```prometheus
# Éxito/fallo por estrategia
cardex_extraction_success_total{strategy="E01"} 12345
cardex_extraction_failure_total{strategy="E01",reason="parse_error"} 234
cardex_extraction_failure_total{strategy="E07",reason="timeout"} 45

# Tasa de éxito por estrategia (calculado en Grafana)
# cardex_extraction_success_rate = success / (success + failure)

# Vehículos extraídos por estrategia y país
cardex_extraction_vehicles_total{strategy="E02",country="DE"} 8923

# Latencia de extracción
cardex_extraction_duration_seconds{strategy="E01",quantile="0.5"} 2.3
cardex_extraction_duration_seconds{strategy="E07",quantile="0.99"} 45.1

# Queue de extracción (profundidad)
cardex_extraction_queue_depth 342

# Playwright instances activas
cardex_extraction_playwright_active 3

# Rate limiter state (dealers en cooldown)
cardex_extraction_rate_limited_domains 23
```

### Quality Service (:9103/metrics)

```prometheus
# Resultados por validator
cardex_quality_validator_pass_total{validator="V01"} 45231
cardex_quality_validator_fail_total{validator="V01",severity="BLOCKING"} 123
cardex_quality_validator_skip_total{validator="V13"} 1203

# Tasa de fallo por validator (alertar si >umbral esperado)
# V01 BLOCKING fail rate expected: <1%
# V06 WARNING fail rate expected: <5%
# V13 WARNING fail rate expected: <8%

# Distribución de confidence scores en records procesados
cardex_quality_confidence_score_bucket{le="0.3"} 234
cardex_quality_confidence_score_bucket{le="0.6"} 8923
cardex_quality_confidence_score_bucket{le="0.85"} 41203
cardex_quality_confidence_score_bucket{le="1.0"} 45231

# DLQ (dead-letter queue)
cardex_quality_dlq_size 45
cardex_quality_dlq_oldest_item_age_seconds 86400

# Manual review queue
cardex_quality_review_queue_size 12
cardex_quality_review_queue_oldest_item_age_seconds 3600

# Duración del pipeline completo
cardex_quality_pipeline_duration_seconds{quantile="0.5"} 0.82
cardex_quality_pipeline_duration_seconds{quantile="0.99"} 4.2
```

### NLG Service (:9104/metrics)

```prometheus
# Descripciones generadas por método
cardex_nlg_descriptions_generated_total{method="LLM_GENERATED",lang="de"} 3421
cardex_nlg_descriptions_generated_total{method="TEMPLATE_FALLBACK",lang="de"} 234
cardex_nlg_descriptions_generated_total{method="LLM_GENERATED",lang="fr"} 2103

# Hallucinations detectadas
cardex_nlg_hallucinations_detected_total{lang="de"} 12

# Tiempo de inferencia
cardex_nlg_inference_duration_seconds{lang="de",quantile="0.5"} 8.3
cardex_nlg_inference_duration_seconds{lang="de",quantile="0.99"} 45.2

# Tokens generados por descripción
cardex_nlg_tokens_generated{quantile="0.5"} 87
cardex_nlg_tokens_generated{quantile="0.99"} 142

# Profundidad de queue pendiente
cardex_nlg_queue_depth 892

# Progreso del batch nocturno (0-1)
cardex_nlg_batch_progress 0.67

# Grammar check results
cardex_nlg_grammar_issues_total{lang="fr",severity="minor"} 234
cardex_nlg_grammar_issues_corrected_total{lang="fr"} 198
```

### Index Service (:9106/metrics)

```prometheus
# Vehículos por estado en el índice
cardex_index_vehicles_total{status="ACTIVE"} 48234
cardex_index_vehicles_total{status="EXPIRED"} 12341
cardex_index_vehicles_total{status="SOLD"} 8923
cardex_index_vehicles_total{status="WITHDRAWN"} 2341
cardex_index_vehicles_total{status="PENDING_NLG"} 892

# Expirados en la última hora
cardex_index_expired_last_hour 23

# Escribas OLAP DuckDB
cardex_index_olap_writes_total 45231
cardex_index_olap_write_duration_seconds{quantile="0.99"} 0.12

# TTL manager
cardex_index_ttl_extensions_total 1234
```

### API Service (:9105/metrics)

```prometheus
# Requests por endpoint y código de respuesta
cardex_api_requests_total{endpoint="/api/vehicles",method="GET",status="200"} 234123
cardex_api_requests_total{endpoint="/api/vehicles",method="GET",status="429"} 234

# Latencia de queries B2B
cardex_api_query_duration_seconds{endpoint="/api/vehicles",quantile="0.5"} 0.045
cardex_api_query_duration_seconds{endpoint="/api/vehicles",quantile="0.99"} 0.312

# DuckDB query performance
cardex_api_duckdb_query_duration_seconds{quantile="0.5"} 0.038
cardex_api_duckdb_query_duration_seconds{quantile="0.99"} 0.289

# SSE connections activas
cardex_api_sse_connections_active 12

# Edge ingestion
cardex_api_edge_ingestion_total{status="accepted"} 1234
cardex_api_edge_ingestion_total{status="rejected"} 12

# API keys activas
cardex_api_active_keys 8
```

### Coverage Score (métrica de negocio crítica)

```prometheus
# Cobertura estimada por país (dealers indexados / total estimado)
cardex_coverage_score{country="DE"} 0.34
cardex_coverage_score{country="FR"} 0.28
cardex_coverage_score{country="ES"} 0.21
cardex_coverage_score{country="BE"} 0.19
cardex_coverage_score{country="NL"} 0.25
cardex_coverage_score{country="CH"} 0.15

# Vehículos ACTIVE por país
cardex_coverage_vehicles_active{country="DE"} 23412
cardex_coverage_vehicles_active{country="FR"} 18923

# Dealers con extracción fallida (E12 backlog)
cardex_coverage_extraction_failed_dealers{country="DE"} 234
```

---

## Dashboards Grafana

### Dashboard 1: Coverage Overview (pantalla principal del operator)
**UID:** `cardex-coverage-overview`

Panels:
- **Vehicles ACTIVE total** (stat, big number) — suma de todos los países
- **Coverage score por país** (gauge 0-100%, 6 gauges) — alerta si <15%
- **Dealers ACTIVE en knowledge graph** (stat) — con trend 7 días
- **Nuevos vehículos hoy** (stat) — comparado con media 7 días
- **Últimos 7 días: vehicles added vs expired** (time series) — tendencia de inventario
- **DLQ size** (stat, rojo si >100)
- **Manual review pending** (stat, naranja si >10)
- **NLG queue depth** (gauge)

### Dashboard 2: Discovery Health
**UID:** `cardex-discovery-health`

Panels:
- **Saturation score por país** (heatmap familia×país)
- **Delta últimas 24h por familia** (bar chart) — nuevos vs merges vs unchanged
- **Errores por familia** (tabla con top 10)
- **Duración de ciclo por familia** (time series)
- **VIES validation status** (stat: % VAT activos en M.M1)

### Dashboard 3: Quality Pipeline
**UID:** `cardex-quality-pipeline`

Panels:
- **Fail rate por validator** (bar chart, ordenado por tasa de fallo)
- **Confidence score distribution** (histograma)
- **DLQ age** (stat con alerta si >48h)
- **V20 coherence issues por tipo** (tabla: C01, C02, C03, C04)
- **Pipeline throughput** (records/min últimas 2h)
- **V13 price outliers por país** (mapa de calor país×make)

### Dashboard 4: NLG Queue
**UID:** `cardex-nlg-queue`

Panels:
- **Queue depth evolución** (time series 24h)
- **Batch progress** (gauge, solo activo durante ventana nocturna)
- **LLM vs Template ratio** (pie chart)
- **Hallucinations detectadas** (stat, rojo si >0.5%)
- **Inferencia p50/p99 por idioma** (bar chart)
- **Grammar issues por idioma** (tabla)

### Dashboard 5: VPS Resources
**UID:** `cardex-vps-resources`

Panels (datos de `node_exporter`):
- **CPU usage** (time series, por core) — alerta si >85% sostenido 5min
- **RAM usage** (time series) — alerta si >90%
- **Disk /srv usage** (gauge) — alerta si >80%
- **Network I/O** (time series)
- **systemd services status** (tabla: discovery/extraction/quality/nlg/index/api — verde/rojo)
- **Load average** (stat)

### Dashboard 6: Legal Compliance Monitor
**UID:** `cardex-legal-compliance`

Panels:
- **CardexBot/1.0 UA rate** (stat: % requests con UA correcto — debe ser 100%)
- **robots.txt violations** (stat, debe ser 0)
- **Rate limiter activations por dominio** (tabla top 10)
- **E11 deployments activos** (mapa por país, solo EU-6 sin CH)
- **Illegal pattern CI failures** (stat: 0 en 30 días = verde)
- **Dominios en blacklist** (tabla)

---

## Alerting Rules

### Prometheus AlertManager (configurado en Grafana)

```yaml
# /srv/cardex/docker/prometheus/alerts.yml

groups:
  - name: cardex-critical
    rules:
      # Coverage drop repentino (posible problem de extracción o legal)
      - alert: CoverageDropCritical
        expr: cardex_coverage_vehicles_active < (cardex_coverage_vehicles_active offset 24h) * 0.95
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "Coverage drop >5% en 24h para {{ $labels.country }}"
          description: "Vehicles active: {{ $value }}. Podría indicar problema de extracción o acción legal."

      # DLQ creciendo sin resolver
      - alert: DLQSizeHigh
        expr: cardex_quality_dlq_size > 500
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "DLQ size {{ $value }} — >500 records bloqueados"

      # Queue de extracción saturada (extractor atascado)
      - alert: ExtractionQueueDepthHigh
        expr: cardex_extraction_queue_depth > 10000
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "Extraction queue depth: {{ $value }}"

      # Memory del VPS alta
      - alert: VPSMemoryHigh
        expr: (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes > 0.90
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "VPS memory usage >90%: {{ $value | humanizePercentage }}"

      # Servicio caído
      - alert: ServiceDown
        expr: up{job=~"cardex.*"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.job }} is DOWN"

      # Validator fail rate anómala
      - alert: ValidatorFailRateHigh
        expr: rate(cardex_quality_validator_fail_total[5m]) / rate(cardex_quality_validator_pass_total[5m]) > 0.15
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Validator {{ $labels.validator }} fail rate >15%"

      # Illegal pattern detectado en CI
      - alert: IllegalPatternDetectedInCI
        expr: increase(cardex_ci_illegal_pattern_violations_total[1h]) > 0
        labels:
          severity: critical
        annotations:
          summary: "ILLEGAL PATTERN detectado en CI — revisar inmediatamente"

      # Disco /srv al 80%
      - alert: DiskUsageHigh
        expr: (node_filesystem_size_bytes{mountpoint="/srv"} - node_filesystem_free_bytes{mountpoint="/srv"}) / node_filesystem_size_bytes{mountpoint="/srv"} > 0.80
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Disco /srv >80% lleno: {{ $value | humanizePercentage }}"

      # NLG queue sin procesar (batch no se ejecutó anoche)
      - alert: NLGQueueStale
        expr: cardex_nlg_queue_depth > 1000 and hour() > 8
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "NLG queue {{ $value }} items — ¿falló el batch nocturno?"
```

---

## Log Schema

### Formato JSON estructurado (todos los servicios)

```json
{
  "time": "2026-04-14T03:42:11.234Z",
  "level": "INFO",
  "service": "cardex-quality",
  "component": "pipeline",
  "vehicle_id": "01HX7Z...",
  "dealer_id": "01HX2A...",
  "validator": "V05",
  "status": "PASS",
  "confidence_delta": 0.03,
  "duration_ms": 234,
  "msg": "validator V05 passed"
}
```

```json
{
  "time": "2026-04-14T03:42:11.890Z",
  "level": "WARN",
  "service": "cardex-extraction",
  "component": "strategy-e07",
  "dealer_id": "01HX2A...",
  "strategy": "E07",
  "url": "https://dealer-example.de/inventory",
  "error": "timeout after 30s",
  "attempt": 2,
  "next_strategy": "E01",
  "msg": "E07 timeout, falling back to E01"
}
```

### Campos obligatorios en todos los logs
- `time` — RFC3339 con ms
- `level` — DEBUG | INFO | WARN | ERROR | FATAL
- `service` — nombre del servicio
- `component` — subcomponente interno
- `msg` — mensaje legible

### Campos prohibidos en logs
- VINs completos (ofuscar: `BMW****1234`)
- Emails de personas físicas
- Tokens/keys de autenticación
- Contenido de descripciones NLG (pueden contener datos del dealer)

---

## Distributed Tracing (plan fase S1)

Fase S0: logging estructurado + métricas suficiente para 1 developer con 1 VPS.

Fase S1 (cuando hay >1 VPS): OpenTelemetry SDK en cada servicio Go, exporta a Jaeger self-hosted. Spans para:
- `discovery.family.run` — trace completo de una familia
- `extraction.dealer.cascade` — trace de E01→E07 con spans por estrategia
- `quality.pipeline.validate` — trace con spans por validator
- `nlg.generate` — trace de inference LLM

```go
// Instrumentación OpenTelemetry en Go (preview)
tracer := otel.Tracer("cardex-quality")
ctx, span := tracer.Start(ctx, "quality.pipeline.validate")
defer span.End()

span.SetAttributes(
    attribute.String("vehicle_id", record.VehicleID),
    attribute.String("dealer_id", record.DealerID),
    attribute.Float64("initial_confidence", initialConfidence),
)
```
