# V20 — Coherence final check

## Identificador
- ID: V20, Nombre: Coherence final check, Severity: BLOCKING
- Phase: Final, Dependencies: V01-V19 (todos los validators anteriores)
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
V20 es el último validator del pipeline. Después de que todos los validators anteriores han validado campos individuales de forma aislada (VIN, precio, imágenes, equipamiento...), V20 ejecuta un chequeo holístico de coherencia interna del registro completo: ¿todos los campos tienen sentido juntos?

Casos que V20 detecta y que los validators individuales no capturan:
- Un BMW M3 con motor 1.0L diesel declarado (make/model inconsistente con engine)
- Un vehículo de 2023 con 450.000 km (mileage inconsistente con year)
- Un precio de 85.000€ para un Dacia Logan de 2018 con 120.000 km (price inconsistente con make+model+year+mileage)
- Equipamiento de lujo declarado en un vehículo de gama base (equipamiento inconsistente con trim level)
- Descripción NLG que menciona "excelente estado" pero mileage > 300.000 km (descripción inconsistente con mileage)

V20 es BLOCKING porque una incoherencia severa entre campos es evidencia de error de extracción o de datos manipulados — publicar ese vehículo dañaría la confianza del comprador B2B en CARDEX.

## Input esperado
Todo el `VehicleRecord` en su estado final post-V01-V19, incluyendo:
- Todos los campos canónicos (make, model, year, mileage, fuel, power, body type)
- `PriceNetEUR` normalizado (V15)
- `EquipmentNormalized` (V18)
- `DescriptionGeneratedML` (V19)
- Resultados acumulados de V01-V19 (annotations, confidence_delta)

## Algoritmo: dos capas

### Capa 1 — Reglas deterministas

Reglas hard-coded que detectan contradicciones obvias sin necesitar LLM:

```go
type CoherenceRule struct {
    ID          string
    Description string
    Check       func(record *VehicleRecord) (ok bool, reason string)
    Severity    string // "BLOCKING" | "WARNING"
}

var coherenceRules = []CoherenceRule{
    {
        ID:          "C01",
        Description: "Mileage inconsistente con año",
        Check: func(r *VehicleRecord) (bool, string) {
            if r.YearCanonical == nil || r.Mileage == nil { return true, "" }
            age := currentYear - *r.YearCanonical
            if age <= 0 { return true, "" }
            kmPerYear := float64(*r.Mileage) / float64(age)
            // Menos de 500 km/año o más de 80.000 km/año es extremo
            if kmPerYear < 500 && *r.Mileage > 1000 {
                return false, fmt.Sprintf("%.0f km/año implausible (muy bajo)", kmPerYear)
            }
            if kmPerYear > 80000 {
                return false, fmt.Sprintf("%.0f km/año implausible (muy alto)", kmPerYear)
            }
            return true, ""
        },
        Severity: "WARNING",
    },
    {
        ID:          "C02",
        Description: "PowerKW inconsistente con make conocido",
        Check: func(r *VehicleRecord) (bool, string) {
            if r.MakeCanonical == nil || r.PowerKW == nil { return true, "" }
            // Marcas que nunca producen >500 kW en vehículos de ocasión convencionales
            if *r.PowerKW > 750 {
                return false, fmt.Sprintf("%d kW fuera de rango para vehículo de ocasión estándar", *r.PowerKW)
            }
            // Dacia/Seat/Skoda nunca superan ~150 kW en gama básica
            conservativeMakes := map[string]int{
                "dacia": 130, "lada": 80,
            }
            if maxKW, ok := conservativeMakes[strings.ToLower(*r.MakeCanonical)]; ok {
                if *r.PowerKW > maxKW {
                    return false, fmt.Sprintf("%s con %d kW inusual", *r.MakeCanonical, *r.PowerKW)
                }
            }
            return true, ""
        },
        Severity: "WARNING",
    },
    {
        ID:          "C03",
        Description: "FuelType inconsistente con año para vehículos eléctricos",
        Check: func(r *VehicleRecord) (bool, string) {
            if r.FuelType == nil || r.YearCanonical == nil { return true, "" }
            if strings.EqualFold(*r.FuelType, "electric") && *r.YearCanonical < 2010 {
                return false, fmt.Sprintf("vehículo eléctrico declarado en %d (anterior al mercado masivo)", *r.YearCanonical)
            }
            return true, ""
        },
        Severity: "WARNING",
    },
    {
        ID:          "C04",
        Description: "Precio inconsistente con make+year+mileage (outlier extremo)",
        Check: func(r *VehicleRecord) (bool, string) {
            // C04 es complementario a V13: detecta inconsistencias cualitativas
            // que V13 puede perder si no tiene suficientes datos de mercado
            if r.PriceNetEUR == nil || r.MakeCanonical == nil { return true, "" }
            // Dacia con precio > 80.000€ → incoherente
            budgetMakes := map[string]float64{
                "dacia": 30000, "lada": 15000, "skoda": 60000,
            }
            if maxPrice, ok := budgetMakes[strings.ToLower(*r.MakeCanonical)]; ok {
                if *r.PriceNetEUR > maxPrice {
                    return false, fmt.Sprintf(
                        "%s con precio %.0f€ (máximo esperado %.0f€)",
                        *r.MakeCanonical, *r.PriceNetEUR, maxPrice,
                    )
                }
            }
            return true, ""
        },
        Severity: "WARNING",
    },
}
```

### Capa 2 — LLM coherence prompt (Llama 3 8B Q4_K_M)

Cuando las reglas deterministas no detectan incoherencia pero el confidence score acumulado está por debajo del umbral (`< 0.55`) o hay múltiples WARNING flags, se lanza una evaluación LLM:

```go
func (v *V20Validator) llmCoherenceCheck(ctx context.Context, record *VehicleRecord) (coherent bool, issues []string, err error) {
    prompt := v.buildCoherencePrompt(record)

    response, err := v.llm.Infer(ctx, prompt, LLMOptions{
        MaxTokens:   200,
        Temperature: 0.1,   // determinístico para coherence check
        StopTokens:  []string{"---"},
    })
    if err != nil {
        return true, nil, err  // si el LLM falla → skip (no bloquear por fallo del LLM)
    }

    return v.parseCoherenceResponse(response)
}

func (v *V20Validator) buildCoherencePrompt(record *VehicleRecord) string {
    return fmt.Sprintf(`Analiza si los siguientes datos de un vehículo son internamente coherentes.
Responde ONLY con JSON: {"coherent": true/false, "issues": ["issue1", "issue2"]}

Vehículo:
- Make/Model: %s %s (%d)
- Kilometraje: %s km
- Motor: %s, %s
- Potencia: %s kW
- Precio neto: %s EUR
- Equipamiento: %s
- Descripción generada: %s

¿Hay contradicciones internas en estos datos? ¿Algún campo es incompatible con los demás?
---`,
        safeStr(record.MakeCanonical),
        safeStr(record.ModelCanonical),
        safeInt(record.YearCanonical),
        formatMileage(record.Mileage),
        safeStr(record.FuelType),
        safeStr(record.Transmission),
        formatPower(record.PowerKW),
        formatPrice(record.PriceNetEUR),
        formatEquipment(record.EquipmentNormalized),
        truncate(safeStr(record.DescriptionGeneratedML), 200),
    )
}
```

## Flujo de decisión

```go
func (v *V20Validator) Validate(ctx context.Context, record *VehicleRecord, graph *KnowledgeGraph) *ValidationResult {
    blockingIssues := []string{}
    warningIssues  := []string{}

    // Capa 1: reglas deterministas
    for _, rule := range coherenceRules {
        if ok, reason := rule.Check(record); !ok {
            if rule.Severity == "BLOCKING" {
                blockingIssues = append(blockingIssues, fmt.Sprintf("[%s] %s", rule.ID, reason))
            } else {
                warningIssues = append(warningIssues, fmt.Sprintf("[%s] %s", rule.ID, reason))
            }
        }
    }

    // Capa 2: LLM si confidence baja o hay warnings
    accumulatedConfidence := v.computeAccumulatedConfidence(record)
    if accumulatedConfidence < 0.55 || len(warningIssues) >= 2 {
        coherent, llmIssues, err := v.llmCoherenceCheck(ctx, record)
        if err == nil && !coherent {
            warningIssues = append(warningIssues, llmIssues...)
        }
    }

    // Decisión final
    if len(blockingIssues) > 0 {
        return &ValidationResult{
            Status:   FAIL,
            Severity: BLOCKING,
            NextAction: MANUAL_REVIEW,
            Annotations: map[string]interface{}{
                "blocking_issues": blockingIssues,
                "warning_issues":  warningIssues,
            },
            ConfidenceDelta: -0.15,
        }
    }

    if len(warningIssues) >= 3 {
        // Múltiples warnings = incoherencia sistémica → manual review
        return &ValidationResult{
            Status:     FAIL,
            Severity:   BLOCKING,
            NextAction:  MANUAL_REVIEW,
            Annotations: map[string]interface{}{
                "warning_issues":       warningIssues,
                "reason":               "multiple_coherence_warnings",
                "accumulated_confidence": accumulatedConfidence,
            },
            ConfidenceDelta: -0.10,
        }
    }

    if len(warningIssues) > 0 {
        return &ValidationResult{
            Status:   PASS,
            Severity: BLOCKING,
            Annotations: map[string]interface{}{
                "warning_issues": warningIssues,
                "coherence_note": "minor_inconsistencies_flagged",
            },
            ConfidenceDelta: -0.03,
        }
    }

    // Sin incoherencias detectadas → PASS con bonus
    return pass("V20", +0.05)
}
```

## Librerías y dependencias
- `llama.cpp` Go bindings — LLM local para coherence check
- `encoding/json` stdlib — parsing respuesta LLM
- `strings` stdlib — reglas deterministas
- Sin dependencias externas

## Umbral de PASS
- Sin blocking issues + <3 warning issues → PASS
- Sin blocking issues + ≥3 warning issues → FAIL BLOCKING → MANUAL_REVIEW
- Con blocking issues → FAIL BLOCKING → MANUAL_REVIEW

## Severity y justificación
**BLOCKING** — V20 es el guardián final. Si el registro llega a V20 con incoherencias internas que todos los validators anteriores no detectaron de forma aislada, es la última oportunidad para evitar publicar datos erróneos. El comprador B2B que ve un BMW con motor de Dacia pierde confianza en CARDEX permanentemente.

## Interacción con otros validators
- **Todos los anteriores:** V20 lee el estado acumulado post-V01-V19
- V13: V20 C04 es complementario a V13 (V13 usa distribución estadística, V20 usa reglas cualitativas)
- V11: V20 C01 es complementario a V11 (V11 usa distribución normal, V20 usa límites absolutos)
- V19: V20 puede detectar inconsistencias entre descripción generada y campos estructurados

## Tasa de fallo esperada
- Incoherencias bloqueantes: ~1-2%
- Múltiples warnings (MANUAL_REVIEW): ~2-3%
- Warnings menores (pass con nota): ~5%

## Action on fail
- `NextAction: MANUAL_REVIEW`

## Contribution a confidence_score
- PASS limpio: +0.05
- PASS con warnings menores: -0.03
- FAIL (blocking): -0.15
- FAIL (multiple warnings): -0.10

## Riesgos y false positives
- **False positive C01:** clásico recién restaurado (1965 Ford Mustang con 5.000 km declarados). Mitigación: si `YearCanonical < 1985` → omitir regla C01 (vehículos clásicos tienen patrones de uso distintos).
- **False positive C04:** Dacia fabricada en edición especial o modificada con equipamiento aftermarket. Mitigación: el MANUAL_REVIEW permite al operador aprobar manualmente tras investigar.
- **LLM incoherente:** el LLM de la Capa 2 produce falsos positivos por regresión del modelo. Mitigación: Capa 2 solo activa en registros ya sospechosos (confidence <0.55 o ≥2 warnings). En registros limpios, no se lanza la Capa 2.
- **Latencia:** la Capa 2 (LLM) añade 2-8 segundos al pipeline. Mitigación: procesar V20 de forma asíncrona para registros de baja prioridad; sincrónico solo para registros de dealers HIGH confidence.

## Invariante de cierre
V20 PASS es la condición necesaria y suficiente para que un registro sea elegible para publicación. Ningún registro puede transicionar de `PENDING_REVIEW` o `PENDING_NLG` a `ACTIVE` sin un V20 PASS registrado en `pipeline_results`.

```sql
-- Invariante enforced a nivel de aplicación y de trigger SQLite
CREATE TRIGGER enforce_v20_before_active
BEFORE UPDATE ON vehicle_record
WHEN NEW.status = 'ACTIVE'
BEGIN
    SELECT CASE
        WHEN NOT EXISTS (
            SELECT 1 FROM pipeline_results
            WHERE vehicle_id = NEW.vehicle_id
            AND validator_id = 'V20'
            AND status = 'PASS'
        )
        THEN RAISE(ABORT, 'V20 PASS required before ACTIVE status')
    END;
END;
```

## Iteración futura
- Ampliar el conjunto de reglas deterministas (actualmente ~4) a ~20 basándose en false positives observados en producción
- Modelo de coherence score continuo (0.0-1.0) en lugar de binario, para priorizar la cola de MANUAL_REVIEW
- Dashboard de coherence issues por fuente para identificar extractores (E01-E12) con alta tasa de incoherencia
