# V06 — Identity convergence (3-of-4)

## Identificador
- ID: V06, Nombre: Identity convergence, Severity: BLOCKING
- Phase: Convergence, Dependencies: V02, V03, V04, V05
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
V06 es el árbitro de identidad. Recopila los resultados de V02 (VIN decode NHTSA), V03 (VIN decode EU), V04 (NLP título), y V05 (clasificación de imagen), y verifica que al menos 3 de los 4 vectores disponibles convergen en la misma Make. Si la identidad del vehículo no puede ser confirmada por al menos 3 fuentes independientes, el registro no se publica — ya que el riesgo de error es demasiado alto para un índice B2B de calidad.

El criterio "3 de 4" es deliberado: requiere mayoría cualificada sin exigir unanimidad (que fallaría por WMIs desconocidos en V02/V03 o imágenes de baja calidad en V05). Tolera ±1 año entre vectores para el Year check.

## Input esperado
- `v02.MakeCanonical`, `v02.YearCanonical` — resultados de V02 (puede ser nil si V02 SKIP)
- `v03.EUMake` — resultado de V03 (puede ser nil si V03 SKIP)
- `v04.InferredMake`, `v04.InferredYear` — resultado de V04 (puede ser nil si V04 SKIP)
- `v05.ClassifiedMake`, `v05.YearApprox` — resultado de V05 (puede ser nil si V05 SKIP)
- `record.Make`, `record.Year` — campos del listing del dealer (fuente base)

## Algoritmo

```go
func (v *V06Validator) Validate(ctx context.Context, record *VehicleRecord, graph *KnowledgeGraph) *ValidationResult {

    // Recopilar los vectores disponibles (no nil, no SKIP)
    type IdentityVector struct {
        Source string
        Make   string
        Year   *int
    }

    vectors := []IdentityVector{}

    // Fuente base: datos del dealer
    if record.Make != nil {
        vectors = append(vectors, IdentityVector{Source: "DEALER", Make: *record.Make, Year: record.Year})
    }
    if v02Make := record.Annotations["v02_make"]; v02Make != nil {
        y := record.Annotations["v02_year"]
        vectors = append(vectors, IdentityVector{Source: "V02_NHTSA", Make: v02Make.(string), Year: y.(*int)})
    }
    if v03Make := record.Annotations["v03_make"]; v03Make != nil {
        vectors = append(vectors, IdentityVector{Source: "V03_EU", Make: v03Make.(string)})
    }
    if v04Make := record.Annotations["v04_make"]; v04Make != nil {
        y := record.Annotations["v04_year"]
        vectors = append(vectors, IdentityVector{Source: "V04_NLP", Make: v04Make.(string), Year: y.(*int)})
    }
    if v05Make := record.Annotations["v05_make"]; v05Make != nil {
        vectors = append(vectors, IdentityVector{Source: "V05_IMAGE", Make: v05Make.(string)})
    }

    // Si menos de 3 vectores disponibles → no hay suficiente información
    if len(vectors) < 3 {
        return &ValidationResult{
            Status:   FAIL,
            Severity: BLOCKING,
            NextAction: MANUAL_REVIEW,
            Annotations: map[string]interface{}{
                "vectors_available": len(vectors),
                "reason": "insufficient_vectors",
            },
        }
    }

    // Contar cuántos vectores coinciden en la Make canónica
    makeGroups := map[string][]string{}
    for _, vec := range vectors {
        canonical := normalizeMake(vec.Make) // lowercase, remove spaces, aliases
        makeGroups[canonical] = append(makeGroups[canonical], vec.Source)
    }

    // La Make más votada
    var topMake string
    var topVoters []string
    for make, voters := range makeGroups {
        if len(voters) > len(topVoters) {
            topMake = make
            topVoters = voters
        }
    }

    // Criterio: ≥3 vectores convergen en la misma Make
    if len(topVoters) >= 3 {
        // Year check: ±1 año de tolerancia entre vectores que tienen Year
        yearConsistent := checkYearConsistency(vectors, topMake, 1)

        record.MakeCanonical = &topMake

        if !yearConsistent {
            // Convergencia de Make pero divergencia de Year
            return &ValidationResult{
                Status:   PASS, // PASS pero con warning
                Severity: INFO,
                Annotations: map[string]interface{}{
                    "make_converged": topMake,
                    "voters": topVoters,
                    "year_inconsistency": true,
                },
                ConfidenceDelta: +0.08, // reducido vs convergencia perfecta (+0.10)
            }
        }

        return &ValidationResult{
            Status:          PASS,
            ConfidenceDelta: +0.10,
            Annotations: map[string]interface{}{
                "make_converged": topMake,
                "voters": topVoters,
            },
        }
    }

    // Menos de 3 vectores convergen → BLOCKING
    return &ValidationResult{
        Status:   FAIL,
        Severity: BLOCKING,
        NextAction: MANUAL_REVIEW, // no DLQ — puede haber datos correctos, solo no convergentes
        Annotations: map[string]interface{}{
            "top_make": topMake,
            "top_voters": topVoters,
            "all_makes": makeGroups,
            "reason": "make_divergence",
        },
    }
}
```

## Librerías y dependencias
- Lógica pura Go — sin dependencias externas
- `github.com/lithammer/fuzzysearch` para `normalizeMake` fuzzy canonical form

## Umbral de PASS
- ≥3 vectores de los disponibles convergen en la misma Make canónica → PASS
- <3 vectores convergen → FAIL BLOCKING

**Consideraciones especiales:**
- Si VIN ausente (V02/V03 SKIP) → la convergencia se basa en V04 + V05 + DEALER (3 vectores). Aceptable.
- Si imagen de baja calidad (V05 SKIP) → V02 + V03 + V04 + DEALER = 4 vectores posibles. Requiere 3 de 4.
- Si VIN ausente Y imagen no clasificable → solo V04 + DEALER = 2 vectores. FAIL → MANUAL_REVIEW.

## Severity y justificación
**BLOCKING** — si la identidad del vehículo no puede ser confirmada por mayoría cualificada de vectores independientes, el riesgo de publicar un registro incorrectamente identificado es demasiado alto. MANUAL_REVIEW (no DLQ) porque un revisor humano puede confirmar la identidad inspeccionando el registro directamente.

## Interacción con otros validators
- V02, V03, V04, V05: todos los dependencies directos
- V11, V12: usan `record.YearCanonical` establecido por V06
- V19: V06 PASS es precondición (no generar descripción para identidad incierta)

## Tasa de fallo esperada
- FAIL BLOCKING: ~5-8% (listings con Make divergente o VIN ausente + imagen no clasificable)

## Action on fail
- `NextAction: MANUAL_REVIEW` (no DLQ — un revisor puede verificar visualmente)

## Contribution a confidence_score
- PASS (4 vectores convergentes): +0.10
- PASS (3 vectores, year inconsistente): +0.08
- FAIL: pipeline detiene

## Riesgos y false positives
- **False positive:** gemelos de plataforma (Seat León declarado como Volkswagen Golf si 3 vectores identifican Golf). Mitigación: el campo `record.Make` del dealer tiene precedencia; si dealer dice Seat y 3 vectores dicen VW, marcarlo como WARNING no como FAIL.
- **False positive:** rebadging/OEM (Dacia Logan vendida como Renault Logan en ciertos mercados). Mitigación: tabla de equivalencias de rebadging en el normalizer.

## Iteración futura
- Añadir V02b (decode por base de datos EU-específica mejorada) como quinto vector cuando esté disponible
- Ponderación de vectores (V02 tiene más peso que V04 cuando VIN está presente)
