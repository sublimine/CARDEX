# V13 — Price outlier detection

## Identificador
- ID: V13, Nombre: Price outlier detection, Severity: WARNING
- Phase: Price, Dependencies: V15 (precio normalizado a EUR)
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Un precio demasiado bajo o demasiado alto respecto al mercado es señal de error de extracción (precio en otra moneda no detectada, precio de cuota mensual en lugar de total, IVA mal manejado) o de caso excepcional (vehículo dañado, dealer en liquidación, vehículo premium con equipamiento especial). V13 usa un modelo estadístico de precios de mercado para detectar estos outliers.

## Input esperado
- `record.PriceNetEUR` o `record.PriceGrossEUR` (normalizados por V15)
- `record.MakeCanonical`, `record.ModelCanonical`, `record.YearCanonical` (de V02/V06)
- `record.Mileage`
- `record.CountryCode`

## Algoritmo

```go
func (v *V13Validator) Validate(ctx context.Context, record *VehicleRecord, graph *KnowledgeGraph) *ValidationResult {
    price := getPriceEUR(record)
    if price == nil { return skip("V13") }

    make := getCanonicalMake(record)
    model := getCanonicalModel(record)
    year := getCanonicalYear(record)

    if make == nil || year == nil { return skip("V13") }

    // Consulta al knowledge graph para estadísticas de mercado
    stats, err := graph.GetPriceStats(*make, safeStr(model), *year, record.CountryCode)
    if err != nil || stats.Count < 20 {
        // No hay suficiente data para calibrar → SKIP (no penalizar por falta de datos)
        return skip("V13")
    }

    // ±3σ como outlier bounds
    lowerBound := stats.Mean - 3*stats.StdDev
    upperBound := stats.Mean + 3*stats.StdDev

    // Límites absolutos
    absMin := 500.0   // ningún coche de ocasión por menos de 500€ es creíble
    absMax := 2000000.0 // Bugatti, Pagani, etc.

    p := *price

    if p < absMin {
        return failWarning("V13", "price_too_low_absolute", p, absMin)
    }

    if p < lowerBound || p > upperBound {
        zScore := (p - stats.Mean) / stats.StdDev
        return &ValidationResult{
            Status:   FAIL,
            Severity: WARNING,
            Annotations: map[string]interface{}{
                "price_eur":      p,
                "market_mean":    stats.Mean,
                "market_range":   [2]float64{lowerBound, upperBound},
                "z_score":        zScore,
                "sample_count":   stats.Count,
            },
            NextAction:      CONTINUE,
            ConfidenceDelta: -0.08,
        }
    }

    return pass("V13", +0.03)
}
```

## Bootstrap del modelo estadístico

En las fases iniciales, CARDEX no tiene datos propios suficientes. Estrategia de bootstrap:

1. **Fase 0 (pre-launch):** estadísticas de aggregators públicos (AutoScout24 tiene precios públicos → dataset de calibración inicial via E03/sitemap)
2. **Fase 1+:** modelo actualizado semanalmente con datos propios acumulados
3. **Separación por antigüedad:** el modelo de hace 3 meses se usa para calibración (no el tiempo real — evita sesgos de mercado cambiante)

## Librerías y dependencias
- Knowledge graph (SQLite) para `GetPriceStats`
- Estadísticas: mean, stddev calculados con running statistics (Welford's algorithm) sin almacenar todos los valores históricos

## Umbral de PASS
- `lowerBound ≤ price ≤ upperBound` Y `price ≥ 500€` → PASS
- Fuera de rango → FAIL WARNING

## Severity y justificación
**WARNING** — un precio outlier puede ser legítimo (dealer en liquidación, vehículo con daños, equipamiento excepcional). No se bloquea la publicación pero se anota para revisión y para informar al comprador de que el precio difiere de mercado.

## Interacción con otros validators
- V15: dependency (precio debe estar en EUR para comparar)
- V14: complementario (V14 detecta modo IVA, V13 valora el precio resultante)
- V20: V20 incluye el outlier flag en su coherence check

## Tasa de fallo esperada
- ~5-8% (outliers estadísticos + errores de extracción de precio)

## Action on fail
- `NextAction: CONTINUE`

## Contribution a confidence_score
- PASS: +0.03
- FAIL: -0.08

## Riesgos y false positives
- **False positive:** vehículo con equipamiento fuera de lo común (VIN de base + 30.000€ de opciones). Mitigación: en V18 el equipamiento normalizado contribuye al modelo de precio en iteraciones futuras.
- **False positive:** precio expresado como cuota mensual por error de extracción. Mitigación: si price < 500€ → annotation `possible_monthly_payment` + fail.

## Iteración futura
- Modelo de precio con feature: equipamiento (V18 output) como covariable
- Modelo hedónico por mileage: ajustar el precio esperado por la combinación año+km
- Alertas de tendencias de mercado (cuando el mercado cambia rápido, el modelo histórico puede ser impreciso)
