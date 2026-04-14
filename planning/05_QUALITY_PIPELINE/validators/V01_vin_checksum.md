# V01 — VIN checksum ISO 3779

## Identificador
- ID: V01, Nombre: VIN checksum ISO 3779, Severity: BLOCKING (cuando VIN presente)
- Phase: Identity, Dependencies: ninguna
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
El VIN (Vehicle Identification Number) es el identificador universal de vehículos según ISO 3779 / FMVSS 115. Su 9º carácter es un dígito de comprobación calculado mediante un algoritmo determinístico sobre los otros 16 caracteres. Un VIN con checksum inválido es un VIN malformado: puede ser un error de extracción, un OCR error, una transposición tipográfica, o un VIN sintético/fraudulento. Publicar un registro con VIN malformado contamina el índice y rompe la funcionalidad de búsqueda por VIN.

V01 es el primer validator porque es el más barato (O(17) aritmética pura) y el más discriminante: si el VIN falla el checksum, todos los validators que dependen de VIN (V02, V03, V06, V16) son irrelevantes.

**Nota:** un VIN ausente (campo nulo) no es fallo — muchos listings legítimos no publican el VIN. V01 solo actúa cuando VIN está presente.

## Input esperado
- `record.VIN` — string, puede ser nil

## Algoritmo ISO 3779 checksum

```go
// VINChecksum valida el 9º dígito de control de un VIN.
// Retorna true si el VIN es estructuralmente válido.
func VINChecksum(vin string) bool {
    // 1. Normalización
    vin = strings.ToUpper(strings.TrimSpace(vin))

    // 2. Longitud: exactamente 17 caracteres
    if len(vin) != 17 {
        return false
    }

    // 3. Caracteres válidos: A-Z (excepto I, O, Q) y 0-9
    transliterationTable := map[rune]int{
        'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6, 'G': 7, 'H': 8,
        'J': 1, 'K': 2, 'L': 3, 'M': 4, 'N': 5, 'P': 7, 'R': 9,
        'S': 2, 'T': 3, 'U': 4, 'V': 5, 'W': 6, 'X': 7, 'Y': 8, 'Z': 9,
        '0': 0, '1': 1, '2': 2, '3': 3, '4': 4,
        '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
    }
    positionWeights := []int{8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2}

    // 4. Cálculo de suma ponderada
    sum := 0
    for i, ch := range vin {
        val, ok := transliterationTable[ch]
        if !ok {
            return false // carácter inválido
        }
        sum += val * positionWeights[i]
    }

    // 5. Módulo 11 y check digit
    remainder := sum % 11
    expectedCheck := '0' + rune(remainder)
    if remainder == 10 {
        expectedCheck = 'X'
    }

    return rune(vin[8]) == expectedCheck
}
```

**Excepción Europa:** los VINs europeos pre-1981 pueden no seguir ISO 3779. Para vehículos con `year < 1981`, el validator cambia a SKIP (los clásicos no tienen checksum estandarizado).

## Librerías y dependencias
- Implementación propia en Go (lógica trivial, no requiere librería externa)
- Referencia: `github.com/cdelorme/vin` como validación de compatibilidad durante testing

## Umbral de PASS
- `record.VIN == nil` → SKIP (VIN ausente no es fallo)
- `record.Year != nil && *record.Year < 1981` → SKIP (vehículo clásico)
- `VINChecksum(*record.VIN) == true` → PASS
- `VINChecksum(*record.VIN) == false` → FAIL

## Severity y justificación
**BLOCKING** cuando VIN presente: un VIN con checksum inválido no puede ser un VIN real. Publicar un registro con VIN malformado es un error objetivo de calidad que confundiría a compradores buscando por VIN específico.

`NextAction: DLQ` — el registro puede recuperarse si la extracción re-obtiene el VIN correctamente del dealer.

## Interacción con otros validators
- V02 (VIN decode NHTSA): dependency de V01 PASS
- V03 (cross-check): dependency de V02
- V06 (identity convergence): usa resultado de V02
- V16 (cross-source): usa VIN para matching

## Tasa de fallo esperada
- ~2-5% de VINs extraídos tienen errores de transcripción (OCR, copy-paste errors, extractor bugs)
- Dealers con catálogos PDF escaneados (E08): tasa más alta (~8%)
- Dealers con API estructurada (E01, E02, E05): tasa muy baja (~0.5%)

## Action on fail
- `NextAction: DLQ` — el registro vuelve al extraction pipeline para re-obtención del VIN

## Contribution a confidence_score
- PASS: +0.05
- FAIL: pipeline detiene (BLOCKING)
- SKIP: +0.00 (neutro)

## Riesgos y false positives
- **False positive:** algunos VINs manufacturados en regiones no ISO (Rusia, China para mercado interno) pueden tener checksum diferente. Mitigación: si el WMI (primeros 3 caracteres) corresponde a un fabricante conocido no-ISO, reducir a WARNING.
- **False positive:** VIN corregido manualmente en el DMS del dealer con error tipográfico. Mitigación: DLQ → re-extracción resuelve.

## Iteración futura
- Soporte de VINs de vehículos eléctricos con WMI nuevos (marcas chinas BYD, NIO, XPeng expandiéndose EU)
- Lookup de WMI desconocidos contra base de datos NHTSA de fabricantes actualizada
