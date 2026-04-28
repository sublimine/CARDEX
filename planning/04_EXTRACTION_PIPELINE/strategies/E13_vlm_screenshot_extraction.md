# E13 — VLM screenshot extraction (Innovation #2)

## Identificador
- ID: E13, Nombre: VLM screenshot extraction, Categoría: Visual-AI
- Prioridad: 1300
- Fecha: 2026-04-15, Estado: DOCUMENTADO — implementación Sprint 8+
- Depende de: `discovery/internal/browser` (Sprint 7), ONNX VLM runtime (Sprint 8+)

## Propósito y rationale

E13 es el extractor de último recurso para dealers cuyo inventario no es accesible mediante ninguna estrategia basada en texto o red (E01–E12 excluido E12). En lugar de parsear HTML o interceptar APIs, E13 captura un screenshot full-page del dealer site usando el módulo browser transparente y lo pasa a un modelo VLM (Vision-Language Model) local para extraer los datos de inventario estructurados.

**Caso de uso primario:** dealer sites con JavaScript ofuscado o altamente dinámico cuyo DOM no contiene texto parseable, cuyas APIs están protegidas con auth de sesión, y cuyo tráfico de red no revela estructuras JSON accesibles. El screenshot contiene visualmente toda la información del listing — E13 la extrae visualmente.

**Innovación #2 en la roadmap de CARDEX:** E13 es la materialización directa de la estrategia de extracción visual de la roadmap de innovación. La combinación Playwright headless → ONNX VLM permite un extractor completamente local, sin APIs externas, sin costes por inferencia, con privacidad completa de los datos scraped.

## Target de dealers

- Sites con heavy obfuscation de JavaScript donde el DOM contiene texto ilegible
- Sites con canvas rendering (algunos DMS legacy renderizan tablas en `<canvas>`)
- Sites donde E01–E07 fallan por bot protection pero el contenido es visualmente accesible
- Dealers en regiones con DMS locales no cubiertos por E02/E05 (ej. plataformas BalticCar, PolAuto)
- Estimado: 5–10% del universo dealer como último fallback antes de E12 (manual review)

## Cadena de fallback completa

```
E01 (JSON-LD/Schema.org)
  ↓ fallo
E02 (CMS REST endpoint directo)
  ↓ fallo
E03 (Sitemap XML)
  ↓ fallo
E07 (Playwright XHR discovery)
  ↓ fallo
E13 (VLM screenshot)  ← este documento
  ↓ fallo
E12 (Manual review)
```

E13 se posiciona antes de E12 porque, aunque costoso en cómputo, es completamente automático. E12 (manual) es el único fallback inferior.

## Stack tecnológico

### Capa 1 — Captura de screenshot

**Módulo:** `discovery/internal/browser` (implementado en Sprint 7)

```go
result, err := b.Screenshot(ctx, dealerURL, &browser.ScreenshotOptions{
    FullPage:     true,
    Format:       "png",
    ClipSelector: ".inventory-list", // opcional: recortar al grid de inventario
})
```

- **UA:** `CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)` — identificable, sin evasión
- **Viewport:** 1920×1080 (desktop rendering, máxima densidad de información)
- **WaitUntil:** `networkidle` — garantiza que el inventario JS esté completamente renderizado
- **Recursos:** imágenes permitidas (las fotos de vehículos pueden informar al VLM)
- **Rate limiting:** heredado del módulo browser (5s min interval per host, SQLite persisted)

### Capa 2 — Inferencia VLM local

**Runtime:** ONNX Runtime Go bindings (`github.com/yalue/onnxruntime_go`)

**Modelos candidatos (evaluación Sprint 8):**

| Modelo | VRAM | Throughput | Idiomas | Notas |
|--------|------|------------|---------|-------|
| Phi-3.5-vision-instruct (ONNX) | ~4 GB | ~8s/img | EN/DE/FR/ES/NL | Primera opción — Microsoft, ONNX nativo |
| LLaVA-CoT-11B (GGUF Q4) | ~6 GB | ~15s/img | Multilingual | Mayor precisión estructurada con CoT |
| Qwen2-VL-2B (ONNX) | ~2 GB | ~3s/img | Multilingual | Opción liviana para VPS sin GPU dedicada |
| InternVL2-2B (ONNX) | ~2 GB | ~4s/img | EN/ZH/multilingual | Buena precisión para tablas |

**Criterio de selección final:** benchmark en dataset de 200 screenshots de dealer sites reales europeos (DE/FR/ES/NL) en Sprint 8.

### Capa 3 — Prompt de extracción

Prompt template para instrucción al VLM:

```
You are a vehicle inventory data extractor. Analyze the screenshot of a car dealer website.
Extract all vehicle listings visible in the image.

For each vehicle, output a JSON object with these fields (use null if not visible):
{
  "make": string,
  "model": string,
  "year": integer,
  "price_eur": number,
  "mileage_km": integer,
  "fuel_type": string,
  "transmission": string,
  "color": string,
  "source_url": string
}

Output ONLY a JSON array of these objects, no other text.
```

**Consideraciones multilingüe:** el prompt es en inglés pero los datos del screenshot pueden estar en DE/FR/ES/NL. Los VLMs candidatos son suficientemente multilingües para manejar esta asimetría.

### Capa 4 — Post-procesamiento y normalización

1. **JSON parsing:** el output del VLM es JSON nominalmente; en la práctica requiere robustez ante truncaciones y errores de formato
2. **Validation:** schema validation con `encoding/json` + validación de rangos (year ∈ [1900, 2030], price > 0)
3. **Normalización:** mismo pipeline que E01–E07 (make/model normalizer, fuel_type enum, VIN decoder si presente)
4. **Confidence score:** base `0.45` para E13 — inferior a E01 (0.95) por incertidumbre inherente del VLM; ajustado según `vlm_confidence_field` del modelo si disponible

## Sub-técnicas

### E13.1 — Screenshot full-page

Captura del inventario completo. Para páginas con paginación, E13.1 captura solo la primera página visible (la más representativa para el registro de dealer, no para inventario completo).

### E13.2 — Screenshot paginado

Para extracción completa de inventario, E13.2 itera sobre las páginas de inventario:
1. Detectar paginación (selector `.pagination`, botón "Next", URL param `?page=N`)
2. Capturar screenshot de cada página
3. Invocar VLM por screenshot, agregar resultados
4. Límite: max 10 páginas por dealer per ciclo (balance cómputo / cobertura)

### E13.3 — ClipSelector targeting

Cuando el site tiene un selector CSS conocido para el grid de inventario (ej. `.vehicle-list`, `#inventory-container`), E13.3 usa `ClipSelector` para capturar solo el área relevante y reducir:
- Tamaño del screenshot (menos tokens VLM, menor latencia)
- Ruido en la extracción (header, footer, navbar, ads excluidos)

Los selectors conocidos se almacenan en el registry de dealer web presence.

### E13.4 — VLM batch inference

Para dealers con inventario grande (>50 vehículos), E13.4 divide el screenshot en tiles verticales solapados (overlap 10%) y ejecuta inferencia en paralelo sobre los tiles. Los resultados se de-duplican por (make, model, year, price) con tolerancia del 5%.

## Formato de datos

```go
type E13Result struct {
    DealerURL   string
    Screenshots []ScreenshotCapture
    Extractions []VLMExtraction
    TotalItems  int
    Duration    time.Duration
    VLMModel    string
    VLMVersion  string
}

type VLMExtraction struct {
    ScreenshotIndex int
    RawOutput       string    // VLM output antes de parsing
    ParsedListings  []Listing // listings parseados
    ParseError      error     // si JSON inválido
    Confidence      float32
    InferenceDuration time.Duration
}
```

## Campos extraíbles

| Campo | Fiabilidad E13 | Notas |
|-------|---------------|-------|
| Make | Alta (95%) | Texto y logo visible |
| Model | Alta (90%) | Texto visible |
| Year | Media (80%) | A veces ambiguo |
| Price | Alta (85%) | Formato monetario reconocible |
| Mileage | Media (75%) | Unidades varían (km/miles) |
| Fuel type | Media (70%) | A veces icono solo |
| Transmission | Baja (55%) | Frecuentemente no visible |
| Color | Alta (85%) | Visual directo |
| VIN | Muy baja (30%) | Texto pequeño, truncado |

## Implementación

```
discovery/internal/extraction/strategies/e13_vlm_screenshot/
├── e13_extractor.go         # Orchestrator — browser + VLM pipeline
├── vlm_client.go            # ONNX Runtime interface (modelo intercambiable)
├── prompt_builder.go        # Prompt templates multilingual
├── response_parser.go       # JSON parsing robusto del output VLM
├── tile_splitter.go         # E13.4 — batch tiling para inventarios grandes
└── e13_extractor_test.go    # Tests con screenshots de fixtures
```

**Dependencias:**
- `discovery/internal/browser` — captura de screenshots (Sprint 7, implementado)
- `github.com/yalue/onnxruntime_go` — ONNX Runtime Go bindings
- Modelo ONNX (descargado en setup, no en repo): ~2–6 GB según modelo elegido

**Hardware requerido (VPS mínimo):**
- CPU: 4 vCPU (inferencia CPU-only con Phi-3.5 ONNX ~8s/imagen)
- RAM: 8 GB (4 GB modelo + 2 GB buffer + 2 GB browser)
- GPU (opcional): NVIDIA con 4 GB+ VRAM reduce latencia a ~1s/imagen con CUDA ONNX EP

## Base legal

- Screenshot captura solo contenido visualmente público del dealer site
- Sin bypass de controles de acceso
- Sin extracción de datos tras login
- UA CardexBot identificable — el site puede bloquear, no se evade
- robots.txt consultado antes de navegar — si inventory path en `Disallow`, E13 no navega
- GDPR: screenshots pueden contener datos personales (nombres de vendedores, fotos de staff) — el pipeline extrae solo datos de vehículos; el screenshot raw se descarta tras inferencia (no se persiste)

## Métricas de éxito

- `e13_screenshot_success_rate` — % URLs donde Screenshot() retorna imagen no vacía
- `e13_vlm_parse_rate` — % screenshots donde VLM produce JSON válido parseadle
- `e13_extraction_precision` — F1 de campos extraídos vs ground truth (evaluación manual periódica)
- `e13_avg_inference_ms` — latencia media de inferencia VLM (objetivo: <15s en CPU, <2s en GPU)
- `e13_items_per_screenshot` — vehículos extraídos por screenshot (baseline: 8–12 listings por viewport)

## Riesgos y mitigaciones

- **R-E13-1:** VLM alucina campos no visibles (fabricar precio, año). Mitigación: validation range checks; confidence threshold mínimo; si >20% de campos son null → resultado marcado LOW_CONFIDENCE.
- **R-E13-2:** Screenshot bloqueado por bot detection (pantalla de captcha, blank page). Mitigación: detección de screenshot vacío o con texto "captcha/blocked" → registrar E13_BLOCKED, escalar a E12.
- **R-E13-3:** Inferencia ONNX demasiado lenta en VPS sin GPU. Mitigación: modelo Qwen2-VL-2B como fallback (3s vs 8s); queue serializado con max 2 inferencias concurrentes.
- **R-E13-4:** Output VLM no es JSON parseable. Mitigación: regex extraction de objetos JSON parciales; si falla → raw output guardado para análisis + escalar a E12.
- **R-E13-5:** Modelo no reconoce idioma del dealer (sitio en húngaro, croata). Mitigación: Qwen2-VL y LLaVA son más multilingües que Phi-3.5; fallback de modelo para dealers en idiomas no cubiertos.

## Iteración futura

- **Fine-tuning:** dataset de 5.000 screenshots dealer europeos anotados → fine-tune VLM para dominio automotive — mejora estimada de 15–20% en precisión
- **Structured output:** modelos con function calling (GPT-4V-style) para output JSON garantizado — reduce post-processing
- **Video extraction:** algunos dealer sites usan carouseles con animación; captura de múltiples frames con comparación temporal
- **OCR híbrido:** para sites con texto muy pequeño (tablas de specs), combinar VLM con Tesseract OCR sobre crops del screenshot
