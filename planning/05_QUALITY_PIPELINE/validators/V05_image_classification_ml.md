# V05 — Image classification ML make/model

## Identificador
- ID: V05, Nombre: Image ML make/model classifier, Severity: WARNING
- Phase: Convergence, Dependencies: ninguna
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
La imagen del vehículo es la señal visual más directa de su identidad. Un clasificador de visión entrenado sobre vehículos puede inferir Make/Model/Year desde la foto con alta precisión para marcas y modelos comunes. V05 aporta el cuarto vector de identidad para V06 — completamente independiente de VIN, título y decodificadores de texto.

Restricción crítica: V05 NO descarga las imágenes. Opera con URLs de las imágenes y delega la descarga únicamente cuando es necesario para el análisis, manteniendo el modelo índice-puntero. La imagen se descarga temporalmente en memoria, se clasifica, y se descarta.

## Input esperado
- `record.ImageURLs[0]` — primera imagen del listing (asumida la más representativa)

## Modelo y dataset de entrenamiento

### Arquitectura
- **YOLOv8n** (nano) fine-tuned para clasificación de make/model
- Convertido a **ONNX INT8** para inferencia CPU-only en Go via `onnxruntime-go`
- Alternativa: **MobileNetV3 Small** cuantizado INT8 (menor precisión, menor latencia)
- Selección final: YOLOv8n ONNX INT8 — mejor trade-off calidad/velocidad en benchmark CX41

### Dataset de entrenamiento
- **Stanford Cars Dataset**: 16.185 imágenes, 196 clases (make/model/year) — base
- **Kaggle European Used Cars**: ~200k+ imágenes de listings europeos — dominio específico
- Augmentation: flip horizontal, random crop, brightness/contrast variation, simulated dealer watermarks
- Clases cubiertas: ~80 make/model combinations más frecuentes en EU (>95% del inventario esperado)
- Out-of-distribution: clase "unknown" para vehículos no en las 80 clases

### Preprocessing

```python
import onnxruntime as ort
import numpy as np
from PIL import Image
import requests
from io import BytesIO

def classify_vehicle_image(image_url: str) -> VehicleClassification:
    # 1. Descarga temporal en memoria
    response = requests.get(
        image_url,
        headers={"User-Agent": "CardexBot/1.0"},
        timeout=10,
        stream=True
    )
    response.raise_for_status()

    # Limit: no descargar imágenes >5 MB
    if int(response.headers.get("Content-Length", 0)) > 5_000_000:
        raise ImageTooLargeError()

    img = Image.open(BytesIO(response.content)).convert("RGB")

    # 2. Resize a 224×224 (YOLOv8n input)
    img = img.resize((224, 224), Image.LANCZOS)
    input_tensor = np.array(img).astype(np.float32) / 255.0
    input_tensor = np.transpose(input_tensor, (2, 0, 1))  # CHW
    input_tensor = np.expand_dims(input_tensor, axis=0)   # NCHW

    # 3. Inferencia ONNX
    session = ort.InferenceSession("vehicle_classifier.onnx")
    outputs = session.run(None, {"input": input_tensor})
    probs = softmax(outputs[0][0])

    top_class_idx = np.argmax(probs)
    top_prob = probs[top_class_idx]

    return VehicleClassification(
        make=CLASS_LABELS[top_class_idx]["make"],
        model=CLASS_LABELS[top_class_idx]["model"],
        year_approx=CLASS_LABELS[top_class_idx]["year_range"],
        confidence=float(top_prob),
        source="V05_IMAGE_ML"
    )
```

## Librerías y dependencias
- `onnxruntime-go` — `github.com/yalue/onnxruntime_go` (ONNX Runtime Go bindings, CPU-only)
- Python subprocess para el clasificador (alternativa a Go binding si compilación compleja)
- Modelo: `assets/vehicle_classifier_yolov8n_int8.onnx` (~8 MB)
- Labels: `assets/vehicle_classifier_labels.json`

## Umbral de PASS
- Confidence ≥ 0.75 Y Make inferida coincide con Make del registro (fuzzy match > 0.85) → PASS
- Confidence ≥ 0.75 Y Make diverge → FAIL WARNING (input crítico para V06)
- Confidence < 0.75 → SKIP (imagen no informativa para clasificación — interior, detalle, ángulo raro)
- Imagen no descargable (404, timeout, Content-Type no image) → SKIP con annotation

## Severity y justificación
**WARNING** — el clasificador tiene precisión limitada en vehículos raros, ángulos no estándar, o clases not-in-training-set. La clasificación incorrecta es posible y esperada para el 15-20% de imágenes.

## Interacción con otros validators
- V07 (image quality): complementario — V07 valida la calidad de la imagen antes de que V05 intente clasificarla. Arquitectura: en la práctica, V07 corre antes, pero V05 no tiene dependency formal de V07.
- V06: V05 aporta el cuarto vector de identidad

## Tasa de fallo esperada
- SKIP (confidence < 0.75): ~25% (imágenes de interior, ángulos rarísimos, vehículos raros)
- FAIL WARNING (divergencia): ~8%

## Action on fail
- `NextAction: CONTINUE`

## Contribution a confidence_score
- PASS: +0.06 (alta contribución — imagen con confidence alta es señal fuerte)
- FAIL: -0.04
- SKIP: +0.00

## Riesgos y false positives
- **False positive:** gemelos de plataforma (VW Golf / Seat León / Skoda Octavia comparten silueta). Mitigación: nivel de clase a nivel de fabricante (no modelo específico) reduce false positives.
- **False positive:** foto de stock de OEM genérica donde el modelo base coincide con el registro. Mitigación: la class label incluye año aproximado que puede divergir.
- **False negative:** vehículos custom/tuned con bodykit que altera silueta. Mitigación: clase "unknown" absorbe estos casos → SKIP.

## Iteración futura
- Dataset específico para vehículos eléctricos y modelos 2023+ (insuficientemente representados en Stanford Cars)
- Ensemble V05a (exterior) + V05b (interior) para mayor precisión
- Multi-image classification: clasificar las primeras 3 imágenes del listing y votar por mayoría
