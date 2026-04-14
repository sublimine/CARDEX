# V08 — Image pHash deduplication

## Identificador
- ID: V08, Nombre: Image pHash deduplication, Severity: WARNING
- Phase: Image, Dependencies: V07 PASS
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
El perceptual hash (pHash) es un fingerprint de imagen que es similar para imágenes visualmente parecidas, incluso si difieren en resolución, compresión, o leve edición. V08 usa pHash para detectar dos tipos de duplicados problemáticos:

1. **Cross-listing duplicates**: el mismo vehículo listado por múltiples dealers simultáneamente (posible error, vehículo consignado, o fraude de listings). Flag para revisión.

2. **Stock photos / manufacturer photos**: imágenes genéricas de OEM o de stock que no son fotos reales del vehículo específico. Si la misma imagen aparece en >N listings de >M dealers distintos, es claramente no una foto del vehículo individual.

## Input esperado
- `record.ImageURLs` (accesibles, validadas por V07)

## Algoritmo

### Cálculo de pHash

```go
import "github.com/corona10/goimagehash"

func computePHash(imageURL string) (uint64, error) {
    // Descarga temporal en memoria
    resp, err := http.Get(imageURL)
    if err != nil { return 0, err }
    defer resp.Body.Close()

    img, _, err := image.Decode(resp.Body)
    if err != nil { return 0, err }

    hash, err := goimagehash.PerceptionHash(img)
    if err != nil { return 0, err }

    return hash.GetHash(), nil
}
```

### Lookup en índice de hashes conocidos

```sql
-- Tabla de pHashes conocidos en el knowledge graph
CREATE TABLE image_phash_index (
    phash_value INTEGER NOT NULL,       -- uint64 pHash
    vehicle_id  TEXT NOT NULL,
    dealer_id   TEXT NOT NULL,
    first_seen  TIMESTAMP NOT NULL,
    INDEX idx_phash ON image_phash_index(phash_value)
);
```

```go
func (v *V08Validator) checkForDuplicates(phash uint64) *DuplicateInfo {
    // Búsqueda de hashes con distancia Hamming ≤ 10 (visualmente similar)
    // En SQLite: buscar en rango de phash±tolerance (aproximación eficiente)
    rows, _ := v.db.Query(`
        SELECT vehicle_id, dealer_id, COUNT(*) as appearances
        FROM image_phash_index
        WHERE ABS(CAST(phash_value AS INTEGER) - CAST(? AS INTEGER)) < 1000
        GROUP BY vehicle_id, dealer_id
    `, int64(phash))

    // Post-filtro: distancia Hamming exacta ≤ 10
    // ...

    // Contar dealers únicos con esta imagen
    uniqueDealers := countUniqueDealers(rows)

    if uniqueDealers > 5 {
        return &DuplicateInfo{Type: "STOCK_PHOTO", DealerCount: uniqueDealers}
    }
    if uniqueDealers > 1 {
        return &DuplicateInfo{Type: "CROSS_LISTING", DealerCount: uniqueDealers}
    }
    return nil
}
```

### Distancia Hamming en Go

```go
func hammingDistance(h1, h2 uint64) int {
    xor := h1 ^ h2
    return bits.OnesCount64(xor)
}
// Umbral: ≤ 10 = imágenes visualmente similares
// > 10 = imágenes diferentes
```

## Librerías y dependencias
- `github.com/corona10/goimagehash` — pHash puro Go, sin CGo
- `math/bits` stdlib — Hamming distance
- `image` stdlib — decode multi-format

## Umbral de PASS
- pHash computado, no hay duplicado en índice → PASS + hash indexado
- pHash = stock photo (>5 dealers, >50 listings con este hash) → FAIL WARNING + flag `is_manufacturer_stock_photo: true`
- pHash = cross-listing sospechoso (2-5 dealers) → FAIL WARNING + flag `cross_dealer_duplicate: true`

## Severity y justificación
**WARNING** — una imagen de stock no invalida el listing. El comprador puede ver que es una foto de catálogo, no del vehículo real. El flag en el registro permite al buyer decidir. Una imagen cross-listing puede indicar el mismo vehículo vendido por dos dealers a la vez — útil señal de mercado, no error de calidad per se.

## Interacción con otros validators
- V07: dependency (imágenes deben ser accesibles)
- V09 (watermark detection): complementario — V08 detecta copias exactas, V09 detecta marcas de agua

## Tasa de fallo esperada
- Stock photos: ~10% (imágenes genéricas OEM muy comunes en algunos DMS)
- Cross-listing: ~2%

## Action on fail
- `NextAction: CONTINUE` + annotation en el registro

## Contribution a confidence_score
- PASS: +0.02
- FAIL (stock photo): -0.03
- FAIL (cross-listing): -0.05

## Riesgos y false positives
- **False positive:** la misma imagen aparece en el mismo dealer en múltiples listados (error de gestión de fotos). Mitigación: contar dealers únicos, no solo apariciones totales.
- **False positive:** imagen de un modelo muy común (ej: foto de plata de VW Golf VIII que múltiples dealers usan legítimamente). Mitigación: umbral alto (>50 listings + >5 dealers distintos) antes de clasificar como stock photo.

## Iteración futura
- dHash (difference hash) como complemento al pHash para mayor robustez ante rotaciones
- Índice ANN (Approximate Nearest Neighbor) con FAISS para escala de millones de hashes
