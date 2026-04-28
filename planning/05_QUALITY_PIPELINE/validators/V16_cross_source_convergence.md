# V16 — Cross-source convergence

## Identificador
- ID: V16, Nombre: Cross-source convergence, Severity: WARNING
- Phase: Cross-source, Dependencies: V01 PASS, V15 PASS
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Cuando el mismo VIN aparece indexado desde múltiples fuentes (mobile.de + AutoScout24 + el sitio propio del dealer), los campos deberían ser sustancialmente consistentes. Una divergencia significativa de precio entre fuentes (>15%) es señal de que uno de los datos está desactualizado, tiene un error de extracción, o el dealer está publicando precios distintos intencionalmente en distintas plataformas (práctica de pricing diferencial aceptable pero que debe documentarse).

V16 compara el registro en proceso con todos los `vehicle_source_witness` previamente indexados para el mismo VIN.

## Input esperado
- `record.VIN` (validado V01)
- `record.PriceNetEUR` (normalizado V15)
- `record.Make`, `record.Model`, `record.Year` (canónicos)

## Algoritmo

```go
func (v *V16Validator) Validate(ctx context.Context, record *VehicleRecord, graph *KnowledgeGraph) *ValidationResult {
    if record.VIN == nil { return skip("V16") }

    // Buscar otras instancias del mismo VIN en el knowledge graph
    witnesses, err := graph.GetVehicleByVIN(*record.VIN)
    if err != nil || len(witnesses) == 0 {
        // Primera vez que se ve este VIN → no hay comparación posible
        return pass("V16", +0.02)  // bonus por VIN único (no duplicado conocido)
    }

    type Divergence struct {
        Field    string
        Source1  string
        Value1   interface{}
        Source2  string
        Value2   interface{}
        PctDiff  float64
    }

    divergences := []Divergence{}

    for _, witness := range witnesses {
        // Price comparison (en EUR)
        if record.PriceNetEUR != nil && witness.PriceNetEUR != nil {
            pctDiff := math.Abs(*record.PriceNetEUR - *witness.PriceNetEUR) / *witness.PriceNetEUR * 100
            if pctDiff > 5 {
                divergences = append(divergences, Divergence{
                    Field:   "price_net_eur",
                    Value1:  *record.PriceNetEUR,
                    Value2:  *witness.PriceNetEUR,
                    PctDiff: pctDiff,
                    Source1: record.SourcePlatform,
                    Source2: witness.SourcePlatform,
                })
            }
        }

        // Make/Model consistency
        if record.MakeCanonical != nil && witness.MakeCanonical != nil {
            if !strings.EqualFold(*record.MakeCanonical, *witness.MakeCanonical) {
                divergences = append(divergences, Divergence{
                    Field:   "make",
                    Value1:  *record.MakeCanonical,
                    Value2:  *witness.MakeCanonical,
                })
            }
        }

        // Year consistency
        if record.YearCanonical != nil && witness.YearCanonical != nil {
            if math.Abs(float64(*record.YearCanonical - *witness.YearCanonical)) > 1 {
                divergences = append(divergences, Divergence{
                    Field:  "year",
                    Value1: *record.YearCanonical,
                    Value2: *witness.YearCanonical,
                })
            }
        }
    }

    // Clasificar por nivel de divergencia
    maxPriceDivPct := maxPriceDivergence(divergences)

    if maxPriceDivPct < 5 {
        return pass("V16", +0.06) // alta convergencia = alta confianza
    }

    if maxPriceDivPct < 15 {
        // Divergencia moderada (5-15%): flag pero publicar
        return failWarning("V16", "moderate_price_divergence", map[string]interface{}{
            "max_divergence_pct": maxPriceDivPct,
            "divergences":        divergences,
        })
    }

    // Divergencia alta (>15%): manual review
    return &ValidationResult{
        Status:   FAIL,
        Severity: WARNING,
        NextAction: MANUAL_REVIEW,
        Annotations: map[string]interface{}{
            "max_divergence_pct": maxPriceDivPct,
            "divergences":        divergences,
            "reason":             "high_price_divergence",
        },
        ConfidenceDelta: -0.10,
    }
}
```

## Librerías y dependencias
- Knowledge graph (SQLite) para `GetVehicleByVIN`
- `math` stdlib para cálculo de divergencia
- Sin dependencias externas

## Umbral de PASS
- Sin otros witnesses del mismo VIN → PASS (primer avistamiento)
- Precio diverge <5% entre todas las fuentes → PASS
- Precio diverge 5-15% → FAIL WARNING (flag, continúa publicación)
- Precio diverge >15% → FAIL WARNING con MANUAL_REVIEW

## Severity y justificación
**WARNING** — la divergencia de precio entre plataformas puede ser intencional (pricing diferencial). No se bloquea automáticamente pero sí se documenta. Si el comprador ve el mismo vehículo a precios muy distintos en CARDEX y en mobile.de, la confianza en CARDEX se reduce.

## Interacción con otros validators
- V01: dependency (VIN necesario para cross-source matching)
- V15: dependency (precios en EUR para comparación)
- V16 PASS enriquece `vehicle_source_witness` con el nuevo registro

## Tasa de fallo esperada
- Divergencia 5-15%: ~8% (variaciones de precio entre plataformas frecuentes)
- Divergencia >15%: ~2%

## Action on fail
- Moderado: `NextAction: CONTINUE`
- Alto: `NextAction: MANUAL_REVIEW`

## Contribution a confidence_score
- PASS (alta convergencia): +0.06
- PASS (primer avistamiento): +0.02
- FAIL (5-15%): -0.05
- FAIL (>15%): -0.10

## Riesgos y false positives
- **False positive:** precio actualizado por el dealer recientemente y solo actualizado en una plataforma. Mitigación: `last_seen_at` de los witnesses — si el witness es >30 días, la divergencia puede ser actualización legítima.
- **False positive:** precio de una plataforma incluye IVA y la otra no (V14/V15 no lo detectó correctamente). Mitigación: comparar con rango de divergencia del ratio IVA del país (si divergencia ~20% en país con IVA 21% → probable diferencia net/gross).

## Iteración futura
- Tracking de evolución de precio por VIN a lo largo del tiempo (serie temporal)
- Alertas automáticas cuando un VIN tiene precio bajando rápidamente (señal de urgencia de venta)
