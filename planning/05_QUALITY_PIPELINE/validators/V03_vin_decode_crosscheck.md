# V03 — VIN decode cross-check DAT/EUR

## Identificador
- ID: V03, Nombre: VIN decode cross-check DAT/EUR, Severity: WARNING
- Phase: Identity, Dependencies: V02 PASS
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
La base de datos vPIC (V02) cubre principalmente vehículos con venta en EEUU. El mercado EU tiene WMIs propios con amplia cobertura de marcas europeas que vPIC no decodifica con precisión (especialmente modelos EU-only de VW, Renault, PSA, SEAT, Dacia). V03 complementa V02 con datasets de VIN europeos open-source para una segunda opinión de decodificación. Cuando V02 y V03 coinciden en Make/Model/Year, la convergencia de identidad gana un vector adicional en V06.

## Input esperado
- `record.VIN` (validado por V01)
- `v02.MakeCanonical` — Make decodificada por V02 (para comparar)

## Fuentes de datos europeos open-source

### DAT Codes (DE)
DAT (Deutsche Automobil Treuhand) publica datasets de códigos de vehículo usados en el mercado de seguros y valoración. Subconjuntos open-source están disponibles en GitHub como diccionarios de WMI/VSN a Make/Model.

### Proyectos GitHub de VIN decode europeo

```
github.com/nicklockwood/VINValidator (Swift, iOS — referencia del algoritmo)
github.com/idmillington/python-vin (Python — WMI table con cobertura EU)
github.com/arthurhammer/vin-decode (múltiples WMIs EU)
github.com/glenndierckx/vin (PHP con WMI EU extendido)
```

El dataset se agrega, normaliza y compila en un SQLite local con cobertura ~8.000 WMIs europeos vs ~3.000 en vPIC.

### WMI Table EU compilada

Campos mantenidos en el dataset local:

```sql
CREATE TABLE wmi_eu (
    wmi TEXT PRIMARY KEY,        -- primeros 3 caracteres del VIN
    make_name TEXT NOT NULL,     -- marca canónica
    country_code TEXT,           -- país de fabricación (ISO 3166-1 alpha-2)
    vehicle_type TEXT,           -- car|truck|motorcycle|bus
    source TEXT                  -- vpic|dat|github|manual
);
```

## Algoritmo

```go
func (v *V03Validator) Validate(ctx context.Context, record *VehicleRecord, graph *KnowledgeGraph) *ValidationResult {
    if record.VIN == nil {
        return skip("V03")
    }

    wmi := (*record.VIN)[:3]

    // Lookup en dataset EU
    var euMake string
    err := v.euDB.QueryRow(`SELECT make_name FROM wmi_eu WHERE wmi = ?`, wmi).Scan(&euMake)
    if err == sql.ErrNoRows {
        // WMI desconocido también en EU dataset → SKIP
        return skip("V03")
    }

    // Cross-check con V02
    v02Make := record.MakeCanonical
    if v02Make != nil && !fuzzyMatchMake(euMake, *v02Make) {
        // Discrepancia entre V02 y V03 → WARNING
        return &ValidationResult{
            Status:   FAIL,
            Severity: WARNING,
            Annotations: map[string]interface{}{
                "v02_make": *v02Make,
                "v03_make": euMake,
                "wmi":      wmi,
            },
            NextAction:      CONTINUE,
            ConfidenceDelta: -0.03,
        }
    }

    // Coincidencia o V02 no disponible → PASS, enriquecer con country_code
    record.Annotations["manufacturing_country"] = euCountry
    return pass("V03", +0.02)
}
```

## Librerías y dependencias
- `modernc.org/sqlite` para consulta del dataset local
- Dataset compilado: `assets/wmi_eu.sqlite` (~5 MB)
- `github.com/lithammer/fuzzysearch` para fuzzy matching de nombres de marca

## Umbral de PASS
- V02 no pasó → SKIP
- WMI no en dataset EU → SKIP (no FAIL — cobertura incompleta esperada)
- Make EU coincide con Make V02 (fuzzy match > 0.85) → PASS
- Make EU diverge de Make V02 → FAIL WARNING

## Severity y justificación
**WARNING** (no BLOCKING): V03 es un cross-check secundario. Una divergencia entre V02 y V03 puede indicar un error de uno de los datasets, no necesariamente un error en el registro. La decisión final la toma V06 con los 4 vectores.

## Interacción con otros validators
- V02: dependency + comparación de Make
- V06: V03 aporta el segundo vector de decode VIN para convergencia de identidad

## Tasa de fallo esperada
- SKIP (WMI desconocido en EU dataset): ~20%
- FAIL WARNING (divergencia V02/V03): ~2-3% (principalmente marcas nicho con WMI compartidos)

## Action on fail
- `NextAction: CONTINUE` — WARNING, el pipeline continúa

## Contribution a confidence_score
- PASS: +0.02
- FAIL: -0.03
- SKIP: +0.00

## Riesgos y false positives
- **False positive:** WMI compartido por múltiples fabricantes de distintos mercados (ocurre con Daewoo/Chevrolet, rebadging de marcas). Mitigación: dataset incluye columna `vehicle_type` y `country_code` para desambiguar.
- **False negative:** dataset EU sin actualización para WMIs nuevos de fabricantes chinos (BYD, NIO, XPENG). Mitigación: dataset actualizable via pull request GitHub de la comunidad.

## Iteración futura
- Contribución al proyecto open-source de WMI EU para mejorar cobertura
- Integración de EUCARIS data cuando formato open-source esté disponible
- Auto-aprendizaje: cuando V02 y V03 divergen y V06 confirma que uno de los dos era correcto, retroalimentar el dataset del incorrecto
