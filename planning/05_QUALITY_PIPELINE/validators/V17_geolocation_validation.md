# V17 — Geolocation validation

## Identificador
- ID: V17, Nombre: Geolocation validation, Severity: INFO
- Phase: Geo, Dependencies: ninguna
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Un vehículo debe estar fisicamente donde el dealer dice estar. Si un dealer registrado en Munich publica un vehículo con location declarada en Barcelona, hay una inconsistencia geográfica que merece anotación. Esto puede indicar: dealer que gestiona stock de otra sede, error en el campo de location, o actividad sospechosa.

V17 es INFO (no BLOCKING) porque la inconsistencia geográfica no invalida el vehículo — solo merece documentación.

## Input esperado
- `record.DealerID` → ubicación del dealer vía knowledge graph
- `record.LocationDeclared` — ciudad/código postal declarado en el listing (si extraído)

## Algoritmo

```go
func (v *V17Validator) Validate(ctx context.Context, record *VehicleRecord, graph *KnowledgeGraph) *ValidationResult {
    location, err := graph.GetDealerLocation(record.DealerID)
    if err != nil || location == nil { return skip("V17") }

    declaredLocation := record.Annotations["location_declared"]
    if declaredLocation == nil { return pass("V17", +0.01) }

    // Geocodificación de la location declarada (offline, usando Nominatim local o MaxMind)
    declaredCoords, err := v.geocoder.Geocode(declaredLocation.(string))
    if err != nil { return skip("V17") }

    // Cálculo de distancia haversine entre dealer location y location declarada
    dist := haversineKM(
        location.Lat, location.Lon,
        declaredCoords.Lat, declaredCoords.Lon,
    )

    if dist > 100 {
        return &ValidationResult{
            Status:   PASS,  // INFO no cambia el Status a FAIL
            Severity: INFO,
            Annotations: map[string]interface{}{
                "dealer_city":         location.City,
                "declared_location":   declaredLocation,
                "distance_km":         dist,
                "geo_inconsistency":   true,
            },
            ConfidenceDelta: 0.0,
        }
    }

    return pass("V17", +0.01)
}
```

## Librerías y dependencias
- MaxMind GeoLite2 (descargable gratis) para geocodificación offline de ciudades
- `math` stdlib para haversine
- Sin llamadas externas en runtime

## Umbral de PASS
- Siempre PASS (severity INFO — solo anota, no bloquea)
- Si distancia >100 km → annotation `geo_inconsistency: true`

## Severity y justificación
**INFO** — la inconsistencia geográfica es informativa, no determinante. Un dealer puede tener un depósito en otra ciudad.

## Interacción con otros validators
- Ninguna dependency formal

## Tasa de fallo esperada
- N/A — siempre PASS

## Contribution a confidence_score
- PASS: +0.01

## Iteración futura
- Validación de que el país del dealer y el país declarado son el mismo (evitar dealers que publican vehículos de un mercado en el índice de otro)
