# V02 — VIN decode vPIC NHTSA

## Identificador
- ID: V02, Nombre: VIN decode vPIC NHTSA, Severity: WARNING
- Phase: Identity, Dependencies: V01 PASS
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
El VIN codifica los atributos de fábrica del vehículo según el estándar WMI/VDS/VIS. La base de datos vPIC (Vehicle Product Information Catalog) de NHTSA contiene la especificación de todos los VINs de vehículos vendidos en EEUU y es, de facto, la fuente de referencia global más completa para decode de VINs internacionales. NHTSA publica gratuitamente el dataset completo (~2 GB, actualización trimestral) para descarga bulk y uso sin restricciones.

V02 decodifica el VIN contra el dataset vPIC local (sin llamadas a API externa en runtime) para obtener los atributos canónicos de fábrica: Make, Model, Year, BodyType, EngineType, FuelType. Estos atributos son la "verdad de fábrica" contra la cual V06 verificará la convergencia con los datos extraídos del dealer.

## Input esperado
- `record.VIN` (validado por V01)

## Algoritmo

### Preparación del dataset (offline, al iniciar el servicio)

```go
// vPICDatabase es el dataset NHTSA cargado en memoria al arrancar el servicio.
// Fuente: https://vpic.nhtsa.dot.gov/api/
// Descarga: https://vpic.nhtsa.dot.gov/downloads/ → vpic.mdb.zip (Access DB)
// Conversión a SQLite via mdb-tools → vpic.sqlite (mantenido en el repo como asset)
type vPICDatabase struct {
    db *sql.DB // SQLite con el dataset convertido
}
```

### Decode en runtime

```go
func (v *V02Validator) decodeVIN(vin string) (*VINAttributes, error) {
    // WMI = primeros 3 caracteres → fabricante
    wmi := vin[:3]

    // VDS (posiciones 4-9) → modelo, body, engine según el fabricante
    vds := vin[3:9]

    // Año de modelo: posición 10
    modelYearCode := rune(vin[9])
    year := decodeModelYear(modelYearCode)

    // Query a SQLite local
    var attrs VINAttributes
    err := v.db.QueryRow(`
        SELECT make_name, model_name, body_class, fuel_type, engine_kw
        FROM vpic_lookup
        WHERE wmi = ? AND vds_pattern LIKE ?
        LIMIT 1
    `, wmi, vds[:3]+"%").Scan(&attrs.Make, &attrs.Model, &attrs.BodyType, &attrs.FuelType, &attrs.PowerKW)

    if err == sql.ErrNoRows {
        // WMI no encontrado en vPIC → vehículo no vendido en EEUU
        // Intentar WMI lookup simple (solo fabricante)
        err = v.db.QueryRow(`SELECT make_name FROM wmi_table WHERE wmi = ?`, wmi).Scan(&attrs.Make)
        if err != nil {
            return nil, ErrWMIUnknown
        }
        attrs.Source = "WMI_ONLY"
    }

    attrs.Year = year
    return &attrs, nil
}
```

### Decodificación del año de modelo (posición 10)

```go
var modelYearMap = map[rune]int{
    'A': 1980, 'B': 1981, 'C': 1982, 'D': 1983, 'E': 1984,
    'F': 1985, 'G': 1986, 'H': 1987, 'J': 1988, 'K': 1989,
    'L': 1990, 'M': 1991, 'N': 1992, 'P': 1993, 'R': 1994,
    'S': 1995, 'T': 1996, 'V': 1997, 'W': 1998, 'X': 1999,
    'Y': 2000, '1': 2001, '2': 2002, '3': 2003, '4': 2004,
    '5': 2005, '6': 2006, '7': 2007, '8': 2008, '9': 2009,
    'A': 2010, 'B': 2011, 'C': 2012, ... // ciclo repite cada 30 años
}
```

## Librerías y dependencias
- `database/sql` + `modernc.org/sqlite` (SQLite sin CGo) para la base de datos vPIC local
- Dataset: vPIC NHTSA bulk download (~2 GB Access DB, convertido a SQLite ~800 MB)
- Conversión offline: script Python `scripts/vpic_convert.py` usando `mdb-tables` + `mdb-export`
- Actualización: trimestral (aligned con NHTSA release schedule)

## Umbral de PASS
- V01 no pasó → SKIP
- WMI desconocido en vPIC → SKIP con annotation `wmi_unknown: true` (no FAIL — vehículos europeos pre-2000 pueden no estar)
- Make extraída por V02 != Make del registro con alta confianza → FAIL WARNING (input para V06)
- Decode exitoso → PASS, campos enriquecidos: `record.MakeCanonical`, `record.ModelCanonical`, `record.YearCanonical`

## Severity y justificación
**WARNING** (no BLOCKING): no todos los vehículos EU están en la base vPIC (especialmente vehículos con WMI europeos sin venta en EEUU). El WMI siendo desconocido no implica que el vehículo sea inválido. La severidad real la decide V06 (convergencia).

## Interacción con otros validators
- V01: dependency (PASS requerido)
- V03: V02 aporta el Make canónico para que V03 pueda cross-check
- V06: V02 es una de las 4 fuentes de identidad para convergencia
- V11: V02 aporta año para sanity check de kilometraje
- V12: V02 aporta año de fabricación para consistency check

## Tasa de fallo esperada
- WMI desconocido (SKIP): ~15% (vehículos EU old, marcas nicho)
- FAIL (Make diverge): ~3-5%

## Action on fail
- `NextAction: CONTINUE` — WARNING no detiene el pipeline; V06 decide si la identidad converge

## Contribution a confidence_score
- PASS: +0.08 (V02 aporta alta confianza cuando el decode es exitoso)
- FAIL/SKIP: +0.00

## Riesgos y false positives
- **False positive:** un modelo vendido en múltiples versiones donde el VDS ambiguo no permite discriminar el modelo exacto → V02 retorna familia de modelos, no modelo preciso. Mitigación: V06 acepta variantes.
- **False negative:** vPIC dataset desactualizado respecto a modelos recientes (2025+). Mitigación: actualización trimestral.

## Iteración futura
- Integración de base de datos europea EUCARIS/Eurotax cuando open-source sea disponible
- Cache LRU de los últimos 10.000 VINs decodificados para evitar re-queries SQL en ciclos frecuentes
