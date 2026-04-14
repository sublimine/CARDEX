# V11 — Mileage sanity check

## Identificador
- ID: V11, Nombre: Mileage sanity check, Severity: WARNING
- Phase: Data-consistency, Dependencies: V02 (para Year canónico)
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
El kilometraje declarado debe ser razonable para la edad del vehículo y el uso típico en el país de origen. Un VW Golf 2018 con 600.000 km es estadísticamente imposible (implicaría ~100.000 km/año, el doble del máximo razonable). Un vehículo 2022 con 3.000 km puede ser real (kilometraje bajo) pero es outlier y merece anotación.

V11 verifica que el kilometraje declarado cae dentro de ±3σ del modelo estadístico de uso por año de fabricación y país.

## Input esperado
- `record.Mileage` (km)
- `record.Year` o `record.YearCanonical` (de V02)
- `record.CountryCode` — país del dealer
- `record.FuelType` — ajuste por tipo de motor (diesel típicamente más km/año que gasolina)

## Algoritmo

```go
func (v *V11Validator) Validate(ctx context.Context, record *VehicleRecord, graph *KnowledgeGraph) *ValidationResult {
    if record.Mileage == nil { return skip("V11") }

    year := getYear(record)
    if year == nil { return skip("V11") }

    age := currentYear - *year
    if age < 0 { return failBlocking("future_vehicle") } // capturado mejor por V12

    // Estadísticas de uso por país
    stats := mileageStats(*record.CountryCode, record.FuelType)
    // DE: 14.000 km/año media, σ=4.500
    // FR: 13.000 km/año media, σ=4.200
    // ES: 12.000 km/año media, σ=4.000
    // NL: 16.000 km/año media, σ=5.000 (alta densidad, mucho uso)
    // BE: 14.500 km/año media, σ=4.500
    // CH: 12.500 km/año media, σ=4.000

    expectedMileage := float64(age) * stats.KMPerYear
    expectedStdDev := float64(age) * stats.StdDev

    // Límites: ±3σ
    lowerBound := expectedMileage - 3*expectedStdDev
    upperBound := expectedMileage + 3*expectedStdDev

    // Límites absolutos adicionales
    absMin := 0.0
    absMax := 500000.0 // ningún coche de ocasión tiene sentido >500k km

    km := float64(*record.Mileage)

    if km > absMax {
        return failWarning("V11", "mileage_above_absolute_max", km, absMax)
    }

    if km < lowerBound || km > upperBound {
        zScore := (km - expectedMileage) / expectedStdDev
        return failWarning("V11", "mileage_outlier", map[string]interface{}{
            "mileage_km":     km,
            "expected_range": [2]float64{lowerBound, upperBound},
            "z_score":        zScore,
            "age_years":      age,
        })
    }

    return pass("V11", +0.02)
}
```

## Librerías y dependencias
- Estadísticas de uso: tabla embebida en el código (hardcoded con valores calibrados)
- Fuentes para calibración: Eurostat Mobility Survey, ADAC data, DGT España, RDW Países Bajos
- Sin dependencias externas

## Umbral de PASS
- `lowerBound ≤ record.Mileage ≤ upperBound` Y `record.Mileage ≤ 500.000` → PASS
- Fuera de rango → FAIL WARNING

**Casos especiales:**
- Vehículos nuevos/casi nuevos (age ≤ 1 año): umbral relajado (0-30.000 km siempre OK)
- Vehículos clásicos (year < 1990): estadística diferente (uso histórico vs colección)
- Camiones/comerciales: estadística diferente (~80.000 km/año media)

## Severity y justificación
**WARNING** — el kilometraje puede ser legítimamente bajo (propietario que no conduce) o alto (empresa de alquiler, taxista). El outlier merece revisión pero no descarte automático.

## Interacción con otros validators
- V02: dependency para Year canónico
- V20 (coherence): V20 incluye el resultado de V11 en su check final

## Tasa de fallo esperada
- ~5-8% (outliers estadísticos legítimos o errores de extracción)

## Action on fail
- `NextAction: CONTINUE` + annotation

## Contribution a confidence_score
- PASS: +0.02
- FAIL: -0.06

## Riesgos y false positives
- **False positive:** vehículo con historial especial (usado como pace car, exposición, km muy bajos por coleccionista). Mitigación: threshold generoso (±3σ); el flag es solo advisory.
- **False positive:** error de unidades (dealer declaró millas en lugar de km). Mitigación: si km / 1.609 cae en rango, añadir annotation `possible_miles_instead_of_km`.

## Iteración futura
- Modelo estadístico con granularidad por segmento (ciudad vs rural, uso profesional vs particular)
- Calibración periódica con datos propios acumulados en CARDEX
