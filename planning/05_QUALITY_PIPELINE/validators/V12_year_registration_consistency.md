# V12 — Year vs registration date consistency

## Identificador
- ID: V12, Nombre: Year vs registration consistency, Severity: BLOCKING
- Phase: Data-consistency, Dependencies: V02 (Year canónico)
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Un vehículo no puede matricularse antes de ser fabricado, ni puede ser fabricado en el futuro. Estas dos invariantes son absolutas. Cualquier inconsistencia indica un error de extracción, un error tipográfico del dealer, o datos fraudulentos. V12 verifica estas restricciones simples pero críticas.

## Input esperado
- `record.Year` o `record.YearCanonical` — año de fabricación
- `record.RegistrationDate` — fecha de primera matriculación (si disponible, campo de enriquecimiento)
- Año actual (del sistema)

## Algoritmo

```go
func (v *V12Validator) Validate(ctx context.Context, record *VehicleRecord, graph *KnowledgeGraph) *ValidationResult {
    year := getCanonicalYear(record)
    if year == nil { return skip("V12") }

    currentYear := time.Now().Year()

    // Invariante 1: año de fabricación no puede ser futuro
    if *year > currentYear+1 {
        // +1 de tolerancia para modelos del año próximo ya disponibles (ej. MY2027 en 2026)
        return failBlocking("V12", "future_year", map[string]interface{}{
            "year":         *year,
            "current_year": currentYear,
        })
    }

    // Invariante 2: año de fabricación mínimo razonable (no indexamos pre-1900)
    if *year < 1900 {
        return failBlocking("V12", "invalid_year_too_old", *year)
    }

    // Invariante 3: año de matriculación ≥ año de fabricación (si disponible)
    if record.RegistrationDate != nil {
        regYear := record.RegistrationDate.Year()
        if regYear < *year {
            return failBlocking("V12", "registration_before_manufacture", map[string]interface{}{
                "manufacture_year":    *year,
                "registration_year":   regYear,
            })
        }
        // Advertencia: matriculación muy posterior a fabricación (>5 años sin matricular es raro)
        if regYear - *year > 5 {
            record.WarningFlags = append(record.WarningFlags, "V12_LATE_REGISTRATION")
        }
    }

    // Invariante 4: año de matriculación no puede ser futuro
    if record.RegistrationDate != nil && record.RegistrationDate.Year() > currentYear {
        return failBlocking("V12", "future_registration_date", record.RegistrationDate.Year())
    }

    return pass("V12", +0.03)
}
```

## Librerías y dependencias
- `time` stdlib — año actual
- Sin dependencias externas

## Umbral de PASS
- `1900 ≤ Year ≤ currentYear + 1` → PASS (año plausible)
- `RegistrationDate.Year ≥ Year` → PASS (matriculación posterior a fabricación)
- Cualquier inconsistencia → FAIL BLOCKING

## Severity y justificación
**BLOCKING** — un vehículo con año de fabricación en el futuro o matriculado antes de existir no puede ser real. No hay ambigüedad: es error objetivo.

`NextAction: DLQ` — la extracción puede tener el año incorrecto; re-extracción puede resolverlo.

## Interacción con otros validators
- V02: dependency (Year canónico)
- V11: V12 complementa V11 (V11 verifica km/año, V12 verifica el año mismo)
- V19: V12 PASS necesario para NLG coherente

## Tasa de fallo esperada
- ~1-2% (errores de extracción de año, especialmente en E08 PDF con OCR)

## Action on fail
- `NextAction: DLQ`

## Contribution a confidence_score
- PASS: +0.03
- FAIL: pipeline detiene

## Riesgos y false positives
- **False positive:** modelos del año próximo comercializados con antelación (ej. "BMW 5 Series 2027" disponible en 2026). Mitigación: `+1` de tolerancia en el upper bound.
- **False positive:** vehículos pre-serie o prototipos con Year declarado como año del prototipo. Mitigación: estos raramente entran al mercado de ocasión B2B.

## Iteración futura
- Verificación de `fecha ITV más reciente > fecha fabricación` cuando el dato esté disponible
