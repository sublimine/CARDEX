# Interfaces Go — Quality Pipeline

## Identificador
- Documento: QUALITY_INTERFACES
- Versión: 1.0
- Fecha: 2026-04-14
- Estado: AUTORITATIVO

## Package y ubicación

```
services/pipeline/quality/
├── interfaces.go       ← definiciones canónicas (este documento)
├── pipeline.go         ← ValidationPipeline + orquestador
├── outcome.go          ← PipelineOutcome + Decision types
├── dlq.go              ← DeadLetterQueue
├── mrq.go              ← ManualReviewQueue
└── validators/
    ├── v01_vin_checksum/
    ├── v02_vin_decode_nhtsa/
    ├── ...
    └── v20_coherence_final/
```

## Interfaces

```go
package quality

import (
    "context"
    "time"
)

// Severity define el impacto de un fallo del validator.
type Severity int

const (
    INFO     Severity = iota // observación, no bloquea
    WARNING                  // sospecha, no bloquea pero acumula
    BLOCKING                 // fallo crítico, detiene publicación
)

// Status es el resultado de la ejecución de un validator.
type Status int

const (
    PASS  Status = iota // validación superada
    FAIL                // validación fallida
    SKIP                // no ejecutado (dependencias no satisfechas)
    ERROR               // error interno del validator
)

// Action es la acción que el pipeline debe tomar ante un fallo.
type Action int

const (
    CONTINUE     Action = iota // continuar pipeline (solo para WARNING/INFO)
    DLQ                        // enviar a dead-letter queue
    MANUAL_REVIEW              // enviar a manual review queue
    QUARANTINE                 // marcar como cuarentena y continuar recolectando evidencia
)

// Decision es el veredicto final del pipeline sobre el registro.
type Decision int

const (
    PUBLISH Decision = iota // registro listo para el índice live
    REVIEW                  // enviado a manual review queue
    REJECT                  // descartado definitivamente
    DLQ_DECISION            // enviado a dead-letter queue para re-intento futuro
)

// Validator es la interfaz que cada V01-V20 (y futuros) debe implementar.
type Validator interface {
    // ID devuelve el identificador canónico ("V01", "V02", ...).
    ID() string

    // Name devuelve el nombre descriptivo.
    Name() string

    // Severity devuelve el impacto de un fallo de este validator.
    Severity() Severity

    // Dependencies lista los IDs de validators cuyo PASS es precondición.
    // Si alguna dependencia no pasó, este validator retorna Status=SKIP.
    Dependencies() []string

    // Validate ejecuta la validación sobre el registro.
    // graph es el knowledge graph para acceso a datos contextuales (dealer_entity, etc.)
    Validate(ctx context.Context, record *VehicleRecord, graph *KnowledgeGraph) *ValidationResult
}

// ValidationResult encapsula el resultado de un validator individual.
type ValidationResult struct {
    ValidatorID string
    Status      Status
    Severity    Severity

    // ConfidenceDelta es la variación en confidence_score.
    // Positivo en PASS, negativo en FAIL WARNING, cero en SKIP/ERROR/INFO.
    ConfidenceDelta float64

    // Annotations contiene evidencia y contexto específico del validator.
    // Ej: {"expected_make": "BMW", "detected_make": "Mercedes", "source": "V04"}
    Annotations map[string]interface{}

    // NextAction indica qué debe hacer el pipeline ante este resultado.
    // Solo relevante cuando Status=FAIL y Severity=BLOCKING.
    NextAction Action

    DurationMS   int64
    ErrorDetails *ValidationError
}

// ValidationError encapsula un error interno del validator (no un fallo del dato).
type ValidationError struct {
    Code    string
    Message string
    Cause   error
}

// VehicleRecord es el registro en proceso de validación.
// Combina los campos de VehicleRaw (extraction) con campos enriquecidos y estado de pipeline.
type VehicleRecord struct {
    // Campos heredados de VehicleRaw
    VIN          *string
    Make         *string
    Model        *string
    Year         *int
    Mileage      *int
    FuelType     *string
    Transmission *string
    PowerKW      *int
    BodyType     *string
    Color        *string
    PriceNet     *float64
    PriceGross   *float64
    Currency     *string
    VATMode      *string
    SourceURL    string
    ImageURLs    []string
    Equipment    []string

    // Campos enriquecidos por validators
    VINValidated    bool
    MakeCanonical   *string   // normalizado por V02/V04/V05
    ModelCanonical  *string
    YearCanonical   *int
    PriceNetEUR     *float64  // normalizado por V15
    PriceGrossEUR   *float64
    EquipmentNorm   []string  // normalizado por V18
    Description     *string   // generado por V19

    // Estado del pipeline
    ConfidenceScore  float64
    WarningFlags     []string
    InfoAnnotations  map[string]interface{}
    ValidatorsPassed []string
    ValidatorsFailed []string
    ValidatorsSkipped []string
}

// KnowledgeGraph provee acceso al grafo de dealers para contextualización.
type KnowledgeGraph interface {
    GetDealer(dealerID string) (*DealerEntity, error)
    GetDealerLocation(dealerID string) (*DealerLocation, error)
    GetVehicleByVIN(vin string) ([]*VehicleRecord, error) // cross-source lookup
    GetPriceStats(make, model string, year int, country string) (*PriceStats, error)
    GetMileageStats(make, model string, year int) (*MileageStats, error)
}

// PriceStats contiene estadísticas de precio para outlier detection (V13).
type PriceStats struct {
    Mean   float64
    StdDev float64
    P05    float64
    P95    float64
    Count  int
}

// MileageStats contiene estadísticas de kilometraje para sanity check (V11).
type MileageStats struct {
    ExpectedKMPerYear float64 // media por país/segmento
    StdDev            float64
}

// ValidationPipeline orquesta la ejecución secuencial de validators.
type ValidationPipeline struct {
    validators []Validator
    config     PipelineConfig
}

// PipelineConfig parámetros configurables del pipeline.
type PipelineConfig struct {
    WarningThreshold     int     // número de warnings que activan REVIEW (default: 3)
    PublishConfThreshold float64 // confidence mínima para PUBLISH (default: 0.70)
    ReviewConfThreshold  float64 // confidence mínima para REVIEW (default: 0.50)
}

// Run ejecuta el pipeline completo sobre un registro.
func (p *ValidationPipeline) Run(ctx context.Context, record *VehicleRecord, graph *KnowledgeGraph) *PipelineOutcome {
    outcome := &PipelineOutcome{
        VehicleID: record.SourceURL, // o ULID si asignado
        Results:   make([]*ValidationResult, 0, len(p.validators)),
    }

    passed := map[string]bool{}

    for _, v := range p.validators {
        // Check dependencies
        for _, dep := range v.Dependencies() {
            if !passed[dep] {
                outcome.Results = append(outcome.Results, &ValidationResult{
                    ValidatorID: v.ID(),
                    Status:      SKIP,
                })
                outcome.ValidatorsSkipped++
                continue
            }
        }

        result := v.Validate(ctx, record, graph)
        outcome.Results = append(outcome.Results, result)
        outcome.ValidatorsRun++

        switch result.Status {
        case PASS:
            passed[v.ID()] = true
            record.ConfidenceScore += result.ConfidenceDelta
            outcome.ValidatorsPassed++

        case FAIL:
            outcome.ValidatorsFailed = append(outcome.ValidatorsFailed, v.ID())
            if result.Severity == BLOCKING {
                outcome.FinalConfidence = record.ConfidenceScore
                switch result.NextAction {
                case DLQ:
                    outcome.PublishDecision = DLQ_DECISION
                case MANUAL_REVIEW:
                    outcome.PublishDecision = REVIEW
                }
                return outcome
            }
            record.ConfidenceScore += result.ConfidenceDelta
            record.WarningFlags = append(record.WarningFlags, v.ID())

        case ERROR:
            record.WarningFlags = append(record.WarningFlags, v.ID()+"_ERROR")
        }
    }

    outcome.FinalConfidence = clamp(record.ConfidenceScore, 0.0, 1.0)

    if len(record.WarningFlags) >= p.config.WarningThreshold {
        outcome.PublishDecision = REVIEW
    } else if outcome.FinalConfidence >= p.config.PublishConfThreshold {
        outcome.PublishDecision = PUBLISH
    } else if outcome.FinalConfidence >= p.config.ReviewConfThreshold {
        outcome.PublishDecision = REVIEW
    } else {
        outcome.PublishDecision = DLQ_DECISION
    }

    return outcome
}

// PipelineOutcome es el resultado final del pipeline para un registro.
type PipelineOutcome struct {
    VehicleID        string
    ValidatorsRun    int
    ValidatorsPassed int
    ValidatorsFailed []string
    ValidatorsSkipped int
    FinalConfidence  float64
    PublishDecision  Decision
    Results          []*ValidationResult
    ProcessedAt      time.Time
}

func clamp(v, min, max float64) float64 {
    if v < min { return min }
    if v > max { return max }
    return v
}
```

## Constantes de ConfidenceDelta por validator

```go
const (
    // PASS deltas (positivos)
    DeltaV01Pass = +0.05 // VIN checksum valid
    DeltaV02Pass = +0.08 // VIN decoded NHTSA
    DeltaV06Pass = +0.10 // identity convergence confirmed
    DeltaV10Pass = +0.05 // vehicle confirmed by classifier
    DeltaV12Pass = +0.03 // year/registration consistent
    DeltaV15Pass = +0.04 // currency normalized
    DeltaV16Pass = +0.06 // cross-source convergent
    DeltaV19Pass = +0.05 // NLG description generated
    DeltaV20Pass = +0.04 // coherence confirmed

    // FAIL WARNING deltas (negativos)
    DeltaV03Fail = -0.03
    DeltaV04Fail = -0.04
    DeltaV05Fail = -0.04
    DeltaV07Fail = -0.05 // image quality poor
    DeltaV08Fail = -0.03 // stock photo detected
    DeltaV11Fail = -0.06 // mileage suspicious
    DeltaV13Fail = -0.08 // price outlier
    DeltaV16Fail = -0.10 // cross-source divergence
)
```
