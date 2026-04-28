# V07 — Image quality validation

## Identificador
- ID: V07, Nombre: Image quality validation, Severity: WARNING
- Phase: Image, Dependencies: ninguna
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
La calidad de las imágenes es fundamental para la experiencia del comprador B2B. Una imagen de 320×240 píxeles borrosa o un CDN que retorna 404 degrada directamente la percepción del producto. V07 verifica la accesibilidad y calidad mínima de las imágenes via HTTP HEAD request (sin descarga completa) y, cuando es necesario, con una descarga ligera del header de imagen para obtener las dimensiones.

V07 no descarga las imágenes completas — usa HEAD requests para verificar disponibilidad, content-type y size, y solo descarga los primeros bytes para leer las dimensiones del header de imagen (JPEG/PNG/WebP).

## Input esperado
- `record.ImageURLs` — lista de URLs de imágenes del listing

## Algoritmo

```go
func (v *V07Validator) validateImageURL(url string) ImageQualityResult {
    // 1. HEAD request para verificar accesibilidad y metadata
    resp, err := v.httpClient.Head(url)
    if err != nil || resp.StatusCode != 200 {
        return ImageQualityResult{Accessible: false, StatusCode: resp.StatusCode}
    }

    contentType := resp.Header.Get("Content-Type")
    if !strings.HasPrefix(contentType, "image/") {
        return ImageQualityResult{Accessible: true, ValidContentType: false, ContentType: contentType}
    }

    // Tamaño: idealmente >50 KB (baja resolución si <20 KB)
    contentLength := resp.ContentLength

    // 2. Descarga parcial para leer dimensiones del header de imagen
    // Solo los primeros 512 bytes (suficiente para JPEG SOI/SOF, PNG IHDR, WebP VP8)
    width, height, err := v.readImageDimensions(url)
    if err != nil {
        return ImageQualityResult{Accessible: true, DimensionsReadable: false}
    }

    return ImageQualityResult{
        Accessible:       true,
        ValidContentType: true,
        ContentType:      contentType,
        Width:            width,
        Height:           height,
        FileSizeBytes:    contentLength,
    }
}
```

### Lectura de dimensiones sin descarga completa

```go
func (v *V07Validator) readImageDimensions(url string) (width, height int, err error) {
    // Range request: primeros 512 bytes
    req, _ := http.NewRequest("GET", url, nil)
    req.Header.Set("Range", "bytes=0-511")
    req.Header.Set("User-Agent", "CardexBot/1.0")

    resp, err := v.httpClient.Do(req)
    if err != nil { return 0, 0, err }
    defer resp.Body.Close()

    header := make([]byte, 512)
    io.ReadFull(resp.Body, header)

    // JPEG: parse SOF0/SOF2 markers para dimensiones
    // PNG: IHDR chunk en bytes 16-23
    // WebP: VP8 bitstream header
    // AVIF: ftyp/mdat box

    return parseImageHeader(header)
}
```

## Criterios de evaluación

| Criterio | Umbral WARNING | Umbral INFO |
|---|---|---|
| Accesibilidad | 0 imágenes accesibles → WARNING | — |
| Content-Type | imagen con tipo no-image → WARNING | — |
| Resolución mínima | <640×480 → WARNING | <1024×768 → INFO |
| Tamaño archivo | <20 KB → WARNING (baja resolución probable) | <50 KB → INFO |
| Número de imágenes | 0 imágenes → WARNING | 1 sola imagen → INFO |

## Librerías y dependencias
- `net/http` stdlib para HEAD + Range requests
- `image/jpeg`, `image/png` stdlib para parsing de headers de imagen
- `github.com/nickalie/go-webpbin` para WebP si necesario
- `golang.org/x/image/webp` para WebP header parsing

## Umbral de PASS
- Al menos 1 imagen accesible + ContentType image/* + resolución ≥640×480 → PASS
- 0 imágenes accesibles → FAIL WARNING
- Todas las imágenes con resolución <640×480 → FAIL WARNING

## Severity y justificación
**WARNING** — un listing sin imagen o con imagen de baja calidad puede publicarse pero con degradación de experiencia. La decisión de publicar o no pertenece al threshold de warnings acumulados en V06.

## Interacción con otros validators
- V08 (pHash dedup): dependency de V07 PASS (no tiene sentido deduplicar imágenes inaccesibles)
- V09 (watermark detection): dependency de V07 PASS
- V10 (vehicle classifier): no tiene dependency formal de V07 pero corre en la misma fase

## Tasa de fallo esperada
- 0 imágenes accesibles: ~3% (CDN del dealer caído, URL rotada)
- Resolución insuficiente: ~5%

## Action on fail
- `NextAction: CONTINUE`

## Contribution a confidence_score
- PASS: +0.03
- FAIL: -0.05

## Riesgos y false positives
- **False positive:** CDN con Range request no soportado (algunos CDNs ignoran Range → descarga completa involuntaria). Mitigación: detectar si Range no soportado via `Accept-Ranges: none` header, usar HEAD-only y omitir dimensiones si es así.
- **False positive:** imagen de alta calidad servida sin `Content-Length` en HEAD. Mitigación: aceptar como accesible si HEAD retorna 200 sin Content-Length — dimensiones desconocidas pero imagen probablemente OK.

## Iteración futura
- Verificación de thumbnails vs imagen full-size para detectar dealers que solo publican thumbnails
- Análisis de duración del CDN: dealers que usan CDN temporal (subidos a un Google Drive o Dropbox) → señal de que las URLs expirarán
