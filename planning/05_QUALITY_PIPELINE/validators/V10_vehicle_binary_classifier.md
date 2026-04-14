# V10 — Vehicle/non-vehicle binary classifier

## Identificador
- ID: V10, Nombre: Vehicle/non-vehicle binary classifier, Severity: BLOCKING
- Phase: Image, Dependencies: V07 PASS
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
En ocasiones, el extraction pipeline captura imágenes que no son de vehículos: logos del dealer, fotos del taller, documentos del vehículo, imágenes de error (404 placeholder), o imágenes de interiores de la sala de ventas. Publicar un listing sin ninguna imagen verificada de vehículo es inaceptable para un índice B2B serio. V10 verifica que al menos 1 de las imágenes del listing contiene un vehículo real.

## Input esperado
- `record.ImageURLs` — todas las URLs de imágenes accesibles (validadas por V07)

## Modelo

### Arquitectura
- **MobileNetV3 Small** cuantizado INT8, fine-tuned como clasificador binario (vehicle / non-vehicle)
- Dos clases: `vehicle` (coches, camiones, furgonetas, motos) vs `non-vehicle` (todo lo demás)
- Input: imagen 224×224
- Dataset: ImageNet subset + Stanford Cars (positivos) + COCO "person", "furniture", "building" (negativos)
- ONNX INT8 para inferencia CPU en Go

```python
def is_vehicle(image_url: str) -> VehicleClassResult:
    img = load_image_from_url(image_url)
    img_resized = img.resize((224, 224))
    tensor = preprocess(img_resized)

    # ONNX inference
    probs = session.run(None, {"input": tensor})[0][0]
    vehicle_prob = probs[VEHICLE_CLASS_IDX]

    return VehicleClassResult(
        is_vehicle=vehicle_prob >= 0.80,
        confidence=float(vehicle_prob)
    )
```

## Umbral de PASS
- Al menos 1 de las ImageURLs tiene `is_vehicle=true` con confidence ≥ 0.80 → PASS
- Todas las imágenes clasificadas como non-vehicle → FAIL BLOCKING

## Severity y justificación
**BLOCKING** — publicar un listing sin imagen de vehículo verificada viola el contrato de calidad básico del producto. El comprador B2B espera ver el vehículo que está comprando.

`NextAction: MANUAL_REVIEW` — puede ser que el clasificador cometa error (coche en ángulo raro, interior único), y un revisor humano puede confirmar. No DLQ porque el extraction re-obtendría las mismas imágenes.

## Interacción con otros validators
- V07: dependency
- V05: complementario — V05 identifica la marca, V10 verifica que es un vehículo

## Tasa de fallo esperada
- FAIL BLOCKING: ~1-2% (imágenes no-vehicle en el primer plano del listing)

## Action on fail
- `NextAction: MANUAL_REVIEW`

## Contribution a confidence_score
- PASS: +0.05
- FAIL: pipeline detiene

## Riesgos y false positives
- **False positive:** foto de interior del vehículo como primera imagen (clasificada como non-vehicle). Mitigación: classifier entrenado con interiores de coches como clase "vehicle" también.
- **False positive:** foto de matrícula close-up. Mitigación: incluir matrículas con fondo de coche en el training set como "vehicle".

## Iteración futura
- Multi-class: distinguir car/truck/van/motorcycle para consistencia con BodyType del registro
- Detector de rendering 3D vs foto real (algunos dealers usan renders CGI que no son fotos del vehículo en stock)
