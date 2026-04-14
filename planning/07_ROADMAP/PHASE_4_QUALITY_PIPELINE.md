# PHASE_4 — Quality Pipeline

## Identificador
- ID: P4, Nombre: Quality Pipeline — V01-V20 + NLG
- Estado: PENDING
- Dependencias de fases previas: P3 parcial (suficientes muestras de vehicle_raw para calibrar validators)
- Fecha de documentación: 2026-04-14

## Propósito y rationale

P4 construye el sistema de validación y enriquecimiento que convierte `vehicle_raw` en `vehicle_record` publicable. Los validators V01-V20 son el núcleo editorial de CARDEX: determinan qué datos son fiables, qué datos necesitan revisión manual, y qué datos no son publicables. El NLG pipeline produce la descripción original que es el principal valor editorial añadido de CARDEX frente a los agregadores tradicionales.

P4 puede arrancar parcialmente en paralelo con P3 — se necesitan muestras de `vehicle_raw` para calibrar los validators, pero no hace falta esperar a que P3 esté 100% completa.

## Objetivos concretos

1. Implementar los 20 módulos Go de validators (V01-V20) conforme a `05_QUALITY_PIPELINE/validators/`
2. Implementar el pipeline orquestador con DLQ, manual review queue, y SSE de invalidaciones
3. Implementar el NLG service con llama.cpp + Llama 3 8B Q4_K_M, 6 idiomas, template fallback
4. Implementar el grammar check con LanguageTool self-hosted
5. Implementar la Manual Review UI con SLA tracking <24h
6. Calibrar umbrales de validators con datos reales de P3
7. Ejecutar el pipeline completo sobre el dataset NL de P3
8. Verificar que la tasa de error y el NLG son aceptables antes de exponer a buyers

## Entregables

| Entregable | Verificación |
|---|---|
| 20 módulos `internal/quality/validators/*.go` | Tests ≥90% coverage por validator |
| `internal/quality/pipeline.go` orquestador | Test E2E sobre dataset de validación |
| `internal/nlg/*.go` + llama.cpp bindings | Test de generación sin alucinaciones |
| `internal/nlg/languagetool.go` | Test de grammar check en 6 idiomas |
| Manual Review UI con SLA tracking | Demo operacional para operador |
| `cmd/quality/main.go` + systemd unit | Corre sin errores en VPS staging |
| `cmd/nlg/main.go` + systemd timer | Procesa queue nocturna correctamente |
| Métricas Prometheus `:9103/:9104` | Todos los labels de `08_OBSERVABILITY.md` presentes |
| BLEU reference corpus | ≥100 descripciones evaluadas por humano por idioma |
| Dataset de validación etiquetado | ≥1.000 vehicle_raw con ground truth |

## Criterios cuantitativos de salida

### CS-4-1: 20/20 validators implementados con tests ≥90% coverage

```bash
ls internal/quality/validators/ | grep -c "\.go$"
# Resultado esperado: ≥20 (excluyendo _test.go)

go test -coverprofile=cov.out ./internal/quality/...
go tool cover -func=cov.out | grep "^cardex/internal/quality/validators" | \
  awk '{if ($3+0 < 90.0) print $0}'
# Resultado esperado: (vacío — todos ≥90%)
```

### CS-4-2: Error rate <0.5% sobre dataset de validación

```sql
-- Dataset etiquetado: vehicle_raw con ground_truth (expected_outcome: PASS/FAIL/SKIP)
SELECT
  ROUND(
    COUNT(CASE WHEN pipeline_outcome != ground_truth THEN 1 END) * 100.0
    / COUNT(*), 4
  ) AS error_rate_pct
FROM quality_validation_dataset
WHERE pipeline_run_id = (SELECT MAX(run_id) FROM quality_pipeline_runs);
-- Resultado esperado: ≤0.5
```

### CS-4-3: NLG — BLEU score ≥ T_BLEU calibrado

```bash
# T_BLEU se determina en la evaluación humana inicial del corpus de referencia
# La expresión exacta depende de la herramienta de evaluación (sacrebleu)
python3 -m sacrebleu --input generated_descriptions.txt reference_descriptions.txt
# El output BLEU score debe ser ≥ T_BLEU documentado en retrospectiva de P4
# T_BLEU provisional: ≥15.0 (ajustar tras primera evaluación humana)
```

### CS-4-4: NLG — human eval ≥4.0/5.0 sobre muestra estratificada

```sql
-- Evaluación manual del operador sobre muestra estratificada de 50 descripciones por idioma
SELECT
  language,
  ROUND(AVG(human_score), 2) AS avg_score,
  COUNT(*) AS sample_size
FROM nlg_human_evaluation
WHERE evaluation_date > DATETIME('now', '-30 days')
GROUP BY language;
-- Resultado esperado: avg_score ≥ 4.0 para todos los idiomas, sample_size ≥ 50
```

### CS-4-5: Manual review SLA <24h — 30 días consecutivos

```sql
SELECT
  COUNT(CASE WHEN resolved_at IS NULL OR
    (JULIANDAY(resolved_at) - JULIANDAY(created_at)) * 24 <= 24 THEN 1 END) * 100.0
  / COUNT(*) AS pct_within_sla
FROM manual_review_queue
WHERE created_at > DATETIME('now', '-30 days')
  AND status != 'PENDING'; -- solo items ya resueltos
-- Resultado esperado: ≥100.0 (0 items resueltos fuera de SLA en últimos 30 días)
```

### CS-4-6: DLQ size ≤1% del total de vehicles procesados (steady state)

```sql
SELECT
  ROUND(
    (SELECT COUNT(*) FROM dead_letter_queue WHERE resolved_at IS NULL) * 100.0
    / (SELECT COUNT(*) FROM vehicle_raw WHERE processed_at IS NOT NULL), 2
  ) AS dlq_rate_pct;
-- Resultado esperado: ≤1.0
```

### CS-4-7: NLG alucinación rate <0.5%

```sql
SELECT
  ROUND(
    SUM(nlg_hallucinations_detected) * 100.0
    / SUM(nlg_attempts), 4
  ) AS hallucination_rate_pct
FROM nlg_batch_stats
WHERE batch_date > DATE('now', '-7 days');
-- Resultado esperado: ≤0.5
```

### CS-4-8: Confidence score distribution razonable

```sql
-- No más del 20% de vehicles ACTIVE con confidence < 0.60 (señal de datos de baja calidad)
SELECT
  ROUND(
    COUNT(CASE WHEN confidence_score < 0.60 THEN 1 END) * 100.0
    / COUNT(*), 2
  ) AS pct_low_confidence
FROM vehicle_record
WHERE status = 'ACTIVE';
-- Resultado esperado: ≤20.0
```

## Métricas de progreso intra-fase

| Métrica | Expresión | Objetivo |
|---|---|---|
| Validators implementados | `ls internal/quality/validators/*.go \| wc -l` | 20/20 |
| Coverage medio validators | `go tool cover` | ≥90% |
| Error rate sobre dataset | CS-4-2 | ≤0.5% |
| NLG BLEU score | CS-4-3 | ≥T_BLEU |
| Human eval score | CS-4-4 | ≥4.0/5.0 |
| SLA compliance (30d) | CS-4-5 | 100% |
| DLQ rate | CS-4-6 | ≤1% |
| Hallucination rate | CS-4-7 | ≤0.5% |

## Actividades principales

1. **Dataset de validación** — etiquetar ≥1.000 vehicle_raw de P3 con ground truth (antes de implementar validators para evitar sesgo)
2. **Implementar validators por fase** — en orden de ejecución del pipeline:
   - Fase VIN: V01, V02, V03
   - Fase Identity: V04, V05, V06
   - Fase Image: V07, V08, V09, V10
   - Fase Temporal: V11, V12
   - Fase Price: V13, V14, V15
   - Fase CrossSource: V16
   - Fase Geo: V17
   - Fase Enrichment: V18, V19 (NLG)
   - Fase Final: V20
3. **Descargar modelos ONNX** — YOLOv8n, MobileNetV3, spaCy multilingual; verificar inference en VPS staging
4. **Descargar Llama 3 8B Q4_K_M** — 4.5 GB GGUF, probar en VPS staging (4 vCPU, 16 GB RAM)
5. **Instalar LanguageTool self-hosted** — JAR + configuración de idiomas
6. **Calibrar umbrales de validators** con datos reales (ej: umbral ±3σ para V13 requiere datos de mercado)
7. **Evaluación humana del NLG** — generar 50 descripciones × 6 idiomas; evaluar con escala 1-5
8. **Calcular T_BLEU** del corpus de referencia
9. **Implementar Manual Review UI** con campo de SLA visible
10. **Retrospectiva** con todos los criterios CS-4-* documentados

## Dependencias externas

- P3 parcial (muestras de vehicle_raw para dataset de calibración)
- Modelos ONNX descargables de HuggingFace (públicos, gratuitos)
- Llama 3 8B Instruct GGUF de HuggingFace (Apache 2.0, ~4.5 GB download)
- LanguageTool JAR (LGPL, ~200 MB download)
- NHTSA vPIC mirror descargado (proceso en bootstrap script)
- MaxMind GeoLite2 city database (~100 MB, libre con registro)

## Riesgos específicos de la fase

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Llama 3 8B en 4 vCPU es demasiado lento para la ventana NLG (backlog >5 noches) | MEDIA | MEDIA | Si throughput insuficiente: reducir batch size, aumentar ventana (00:00-07:00), o escalar a S1 antes de P5 |
| V06 convergence (3-of-4) con demasiados MANUAL_REVIEW por falta de imágenes | MEDIA | MEDIA | Ajustar umbral de V06: si no hay imágenes disponibles, 2-of-3 (VIN+NLP+manual) suficiente |
| Dataset de validación sesgado hacia dealers bien formateados | MEDIA | ALTA | Incluir deliberadamente casos edge: dealers con solo foto exterior, sin VIN, precios en CHF sin indicador |
| LanguageTool con baja precisión en neerlandés o alemán técnico automotriz | BAJA | BAJA | Configurar LanguageTool con reglas desactivadas para terminología técnica específica |

## Retrospectiva esperada

Al cerrar P4, evaluar:
- ¿Qué validators tienen la tasa de fallo más alta? ¿Es razonable o indica un problema de calibración?
- ¿El threshold T_BLEU calibrado es un buen predictor de calidad percibida por el operador?
- ¿La ventana NLG nocturna fue suficiente para procesar el dataset NL completo?
- ¿El SLA <24h de manual review es sostenible para el operador con el volumen actual?
- ¿Qué tipos de vehículos acaban en DLQ con mayor frecuencia? ¿Son casos recuperables?
