# V09 — Watermark/logo detection

## Identificador
- ID: V09, Nombre: Watermark/logo detection, Severity: WARNING
- Phase: Image, Dependencies: V07 PASS
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Muchos dealers marcan sus fotos con el logo o URL de su concesionario como watermark. En un contexto de índice-puntero esto es aceptable — las imágenes las sirve el dealer. Sin embargo, detectar watermarks de un dealer diferente al que está indexando el vehículo es señal de que las imágenes fueron copiadas/robadas de otro listing, lo que indica un fraude de listing o un error de gestión de inventario.

V09 detecta watermarks y logos de dealer en las imágenes mediante un CNN binario ligero (watermark presente / watermark ausente), y cuando detecta uno, intenta identificar si corresponde al dealer correcto o a uno diferente.

## Input esperado
- `record.ImageURLs[0]` — imagen principal
- `record.DealerID` — para comparación de logos

## Modelo

### Arquitectura
- CNN binario (watermark presente/ausente): MobileNetV3 Small fine-tuned
- Dataset: 10.000 imágenes de listings con watermarks variados (logos dealer, URLs, texto superpuesto) + 10.000 imágenes limpias
- Output: `{has_watermark: bool, confidence: float, region: [x,y,w,h]}`

### Logo identification (si watermark detectado)
Si watermark presente, intenta extraer el texto del watermark via OCR ligero (tesseract sobre el crop de la región) y compara con:
- Nombre del dealer actual (`record.DealerCanonicalName`)
- Dominio del dealer (`record.DealerDomain`)

```python
def detect_watermark(image_url: str, dealer_name: str, dealer_domain: str) -> WatermarkResult:
    img = load_image_from_url(image_url)

    # CNN binary classifier
    has_watermark, confidence, region = watermark_model.predict(img)
    if not has_watermark or confidence < 0.7:
        return WatermarkResult(has_watermark=False)

    # OCR del crop de la región del watermark
    crop = img.crop(region)
    watermark_text = pytesseract.image_to_string(crop, config="--psm 7").strip().lower()

    # Comparar con dealer actual
    is_own_dealer = (
        dealer_name.lower() in watermark_text or
        dealer_domain.lower().replace("www.", "") in watermark_text
    )

    return WatermarkResult(
        has_watermark=True,
        is_own_dealer=is_own_dealer,
        watermark_text=watermark_text,
        confidence=confidence
    )
```

## Librerías y dependencias
- ONNX Runtime para CNN (mismo patrón que V05)
- `pytesseract` para OCR del watermark
- Modelo: `assets/watermark_detector_mobilenetv3_int8.onnx` (~4 MB)

## Umbral de PASS
- No watermark detectado (confidence < 0.7) → PASS
- Watermark detectado + es del propio dealer → PASS + annotation `has_own_watermark: true`
- Watermark detectado + es de otro dealer → FAIL WARNING + flag `cross_dealer_watermark: true`
- Watermark detectado + no identificable → PASS (watermark presente pero inofensivo)

## Severity y justificación
**WARNING** — una imagen robada de otro dealer es una señal de fraude pero no invalida la existencia del vehículo. El flag permite revisión humana y potencial contacto con el dealer fuente.

## Interacción con otros validators
- V07: dependency
- V08: complementario — V08 detecta hash duplicados, V09 detecta marcas de agua

## Tasa de fallo esperada
- Watermark de otro dealer: ~1-2%

## Action on fail
- `NextAction: CONTINUE` + flag en el registro para revisión humana

## Contribution a confidence_score
- PASS: +0.01
- FAIL (cross-dealer watermark): -0.03

## Riesgos y false positives
- **False positive:** marca de agua del propio aggregator de fotos (ej. mobile.de watermark en imágenes cross-posteadas). Mitigación: lista de watermarks de aggregators conocidos que son aceptables.

## Iteración futura
- Detector de watermarks de aggregators (mobile.de, AutoScout24) para casos donde las imágenes provienen de marketplaces
- Logo brand detection para identificar marcas OEM (fotos de stock de BMW, Mercedes, etc.) — cross con V08
