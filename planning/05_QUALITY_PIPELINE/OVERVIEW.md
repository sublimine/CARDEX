# Quality Pipeline — Overview arquitectónico

## Identificador
- Documento: QUALITY_PIPELINE_OVERVIEW
- Versión: 1.0
- Fecha: 2026-04-14
- Estado: AUTORITATIVO

## Propósito
El pipeline de calidad es el gateway obligatorio entre el resultado bruto del extraction pipeline (E01-E12) y el índice live de CARDEX. Opera como un sistema de compuertas: un `VehicleRaw` que no supera la cascada de validators no llega nunca al índice. La calidad del dato es un invariante no negociable del producto — un buyer que ve un VIN malformado, un precio en moneda errónea o una descripción con alucinaciones decide no volver.

## Arquitectura gateway

```
VehicleRaw (extraction output)
         ↓
  [Validation Pipeline]
  V01 → V02 → V03  (Identity phase)
  V04 → V05 → V06  (Convergence phase)
  V07 → V08 → V09 → V10  (Image phase)
  V11 → V12        (Data-consistency phase)
  V13 → V14 → V15  (Price phase)
  V16              (Cross-source phase)
  V17              (Geo phase)
  V18              (Equipment phase)
  V19              (NLG phase)
  V20              (Final coherence phase)
         ↓
  PipelineOutcome
         ↓
  [Decision Router]
  PUBLISH → vehicle_record (ACTIVE)
  REVIEW  → manual_review_queue
  DLQ     → dead_letter_queue
  REJECT  → vehicle_record (REJECTED) + log
```

## Severity matrix

| Severity | Significado | Acción on fail |
|---|---|---|
| BLOCKING | El dato es incorrecto o indetectable. Publicar sería un error de calidad crítico. | DLQ o MANUAL_REVIEW según tipo |
| WARNING | El dato es sospechoso o incompleto pero puede ser correcto. | Flag en el registro + MANUAL_REVIEW si acumulan N warnings |
| INFO | Observación de mejora. El dato es aceptable. | Log + annotation en registro |

Un registro con 0 BLOCKING fails y <N WARNING fails → PUBLISH.
Un registro con 0 BLOCKING fails y ≥N WARNING fails → REVIEW (N configurable, default: 3).
Un registro con ≥1 BLOCKING fail → DLQ o MANUAL_REVIEW (según la acción del validator específico).

## Orden de ejecución y rationale

### Fase Identity (V01-V03)
Primero porque si no hay VIN válido, ninguna validación posterior tiene sentido. V01 es el filter gate más barato.

### Fase Convergence (V04-V06)
Antes de image validation porque la convergencia de identidad (VIN+título+imagen→mismo coche) define si el registro es coherente. Un fallo de convergencia temprano evita correr los costosos modelos de imagen.

### Fase Image (V07-V10)
Después de convergencia: solo se validan imágenes de registros con identidad confirmada. V10 (non-vehicle classifier) corre primero dentro de la fase para abortar el resto si la imagen no es un vehículo.

### Fase Data-consistency (V11-V12)
Checks de coherencia de datos numéricos simples. Rápidos, sin ML.

### Fase Price (V13-V15)
V15 (normalización moneda) antes de V13 (outlier detection) porque el outlier se calcula en EUR.

### Fase Cross-source (V16)
Después de normalización de precio para que la comparación cross-source sea en la misma moneda.

### Fase Geo (V17)
Validación ligera — solo requiere knowledge graph (sin ML).

### Fase Equipment (V18)
Normalización terminológica — no bloquea, solo enriquece.

### Fase NLG (V19)
Antes de V20 porque V20 verifica coherencia del registro incluyendo la descripción generada.

### Fase Final (V20)
LLM coherence check como sanity final sobre el registro completo.

## Flujo de decisiones detallado

```
for each validator V in order:
    result = V.Validate(ctx, record, graph)

    switch result.Status:
        case PASS:
            record.confidence_score += result.ConfidenceDelta
            continue

        case FAIL:
            switch result.Severity:
                case BLOCKING:
                    switch result.NextAction:
                        case DLQ:
                            → send to dead_letter_queue with diagnostic
                            → STOP pipeline (remaining validators not run)
                            return PipelineOutcome{Decision: DLQ}
                        case MANUAL_REVIEW:
                            → send to manual_review_queue with diagnostic
                            → STOP pipeline
                            return PipelineOutcome{Decision: REVIEW}
                        case QUARANTINE:
                            → set record.status = QUARANTINED
                            → continue pipeline (collect all evidence)

                case WARNING:
                    record.warning_flags = append(flags, result.ValidatorID)
                    record.confidence_score += result.ConfidenceDelta  // negativo
                    continue  // no detiene el pipeline

                case INFO:
                    record.info_annotations[result.ValidatorID] = result.Annotations
                    continue

        case SKIP:
            // dependencies no satisfechas, validator skipped
            log.Info("skipped", "validator", V.ID())
            continue

        case ERROR:
            // error interno del validator (bug, dep externa caída)
            log.Error("validator_error", "validator", V.ID(), "err", result.ErrorDetails)
            // trata como WARNING para no bloquear por infraestructura rota
            record.warning_flags = append(flags, result.ValidatorID+"_ERROR")
            continue

if len(record.warning_flags) >= WARNING_THRESHOLD:
    return PipelineOutcome{Decision: REVIEW}

if record.confidence_score < PUBLISH_THRESHOLD:
    return PipelineOutcome{Decision: REVIEW}

return PipelineOutcome{Decision: PUBLISH}
```

## Dead-letter queue (DLQ)

Los registros en DLQ contienen:
- `vehicle_raw` original (snapshot completo)
- `failed_validator` — ID del validator que lo envió a DLQ
- `diagnostic` — annotations del validator con evidencia específica
- `retry_count` — número de veces que se ha re-intentado el pipeline
- `created_at`, `last_attempt_at`

Re-procesamiento automático:
- En cada re-extracción del dealer (si la fuente cambia, el registro puede mejorar)
- Tras actualización de un validator (un fix puede dejar pasar registros antes bloqueados)
- Manual trigger por operador

DLQ es de primera clase: tiene su propia tabla SQLite, dashboard de monitorización, y métricas. No es un bin olvidado.

## Manual Review Queue (MRQ)

Los registros en MRQ tienen:
- `vehicle_raw` original
- `failed_validators` — lista de validators con `NextAction: MANUAL_REVIEW`
- `warning_flags` — si llegó por acumulación de warnings
- `briefing` — descripción generada automáticamente del problema para el revisor
- `sla_deadline` = `entered_at + 24h`
- `priority_score` = f(dealer_importance, vehicle_price_estimated, warning_count)

El revisor puede:
- `APPROVE` — publicar el registro con anotación de revisión manual
- `REJECT` — descartar con razón documentada
- `ENRICH` — completar campos faltantes + re-run del pipeline
- `ESCALATE` — elevar a operador senior

## Confidence score acumulativo

```
initial_confidence = base_confidence(extraction_strategy)
  // E01 = 0.85, E02 = 0.80, E03 = 0.70, E07 = 0.65, etc.

for each validator:
    confidence += ConfidenceDelta(validator, result)
    // PASS: delta positivo (+0.01 a +0.05 según peso del validator)
    // FAIL WARNING: delta negativo (-0.05 a -0.15)
    // FAIL BLOCKING: pipeline stops (no accumulated further)

final_confidence = clamp(confidence, 0.0, 1.0)
```

Thresholds de publicación:
- `final_confidence ≥ 0.70` → PUBLISH
- `0.50 ≤ final_confidence < 0.70` → REVIEW
- `final_confidence < 0.50` → DLQ (re-evaluar desde extraction)

## Métricas globales del pipeline

- `pipeline_pass_rate(country, strategy)` — % registros que llegan a PUBLISH
- `dlq_rate(validator)` — % registros enviados a DLQ por cada validator
- `mrq_sla_compliance` — % casos resueltos en <24h
- `false_positive_rate(validator)` — calculado mensualmente sobre muestra auditada
- `pipeline_latency_p50_p99` — tiempo desde VehicleRaw a PipelineOutcome
- `confidence_distribution` — histograma de scores finales
