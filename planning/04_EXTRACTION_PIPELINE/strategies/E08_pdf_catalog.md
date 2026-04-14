# E08 — PDF inventory catalog parsing

## Identificador
- ID: E08, Nombre: PDF inventory catalog parsing, Categoría: Binary-document
- Prioridad: 300
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Un subconjunto de dealers — principalmente independientes, dealers de vehículos clásicos/premium, y dealers en regiones con adopción digital más baja — publica su inventario como catálogo PDF descargable o linkado desde su web. Aunque el PDF no es un formato estructurado, su contenido tabular (listas de vehículos con columnas Make/Model/Year/Price/Mileage) es parseable con herramientas especializadas. E08 cubre este nicho con pipeline pdfplumber + tabula-py para PDFs con texto seleccionable, y tesseract OCR para PDFs escaneados.

## Target de dealers
- Dealers de vehículos clásicos/youngtimer con catálogos PDF trimestrales
- Dealers premium con presentaciones de stock en PDF
- Dealers de vehículos comerciales/camiones con price lists en PDF
- Dealers en regiones rurales con digitalización limitada
- Estimado: 3-5% del universo dealer (nicho pero con alta valor por vehículo)

## Sub-técnicas

### E08.1 — Discovery de PDFs linkados

Búsqueda de links a PDFs en el site del dealer:
- Parser HTML sobre homepage + inventory page
- Selección de `<a href="*.pdf">` o `<a>` con texto que sugiere inventario ("catálogo", "stock", "Fahrzeugliste", "liste véhicules", "inventory PDF")
- Headers HTTP: `Content-Disposition: attachment; filename="inventory.pdf"` o `Content-Type: application/pdf` en links
- Sitemap: algunos sitemaps incluyen PDFs con `<lastmod>` actualizado

Paths de discovery adicionales:
```
/catalogo.pdf
/stock.pdf
/fahrzeugliste.pdf
/inventory.pdf
/voitures.pdf
/downloads/inventory.pdf
```

### E08.2 — Parsing de PDFs con texto seleccionable (pdfplumber)

Para PDFs generados digitalmente (texto embedded, no escaneado):

1. `pdfplumber` para extracción de tablas: detecta líneas de tabla, celdas, columnas
2. Identificación de columnas via header row: buscar términos en primera fila que coincidan con Make/Model/Year/Price/Km/Fuel etc.
3. Iteración por filas: cada fila es un vehículo candidato
4. Validación básica: fila con al menos Make + Price o Year se acepta como vehículo

Para PDFs sin tablas claras (texto en prosa o layout complejo):
- `pdfplumber.extract_text()` → texto raw
- Regex patterns sobre el texto (similares a E04.5 heurístico)

### E08.3 — Parsing con tabula-py (tablas complejas)

tabula-py usa la librería tabula-java para extracción de tablas de PDFs con layouts complejos (multi-columna, merged cells, rotated headers). Se usa como fallback cuando pdfplumber no detecta estructura tabular clara:

```python
import tabula
tables = tabula.read_pdf("inventory.pdf", pages="all", multiple_tables=True)
# tables es lista de DataFrames pandas → normalización de columnas
```

### E08.4 — OCR con tesseract para PDFs escaneados

Para PDFs que son imágenes escaneadas (no texto seleccionable):

1. `pdf2image` para convertir páginas a PNG/JPEG (300 DPI mínimo para OCR fiable)
2. `pytesseract` con idioma configurado según país del dealer (deu, fra, spa, nld, fra)
3. Post-OCR: mismo pipeline de normalización que texto digital

OCR es costoso (CPU intensivo). Se aplica solo cuando:
- `pdfplumber.extract_text()` retorna vacío o ratio caracteres/página < threshold
- PDF metadata indica `Creator: Acrobat Scan` o similar

### E08.5 — Normalización de datos extraídos de PDF

Los datos de PDF tienen mayor tasa de error que otras fuentes (OCR errors, columnas mal alineadas). Pipeline de normalización específico:

- Números: `28.500 €` → `28500.0`, `45.000 km` → `45000`, manejar separadores locales
- Años: `2021`, `´21`, `2021/22` → `2021`
- Marcas: fuzzy matching contra vocabulario controlado de marcas (BMW, Bmw, B.M.W. → BMW)
- VIN: validación de checksum ISO 3779 — VINs inválidos descartados

## Formato de datos esperado
PDF con tabla de inventario o lista de vehículos. Puede ser: tabla nativa PDF (vector), tabla escaneada (bitmap), texto en prosa con datos de vehículos.

## Campos extraíbles típicamente
Depende de la estructura del catálogo. Mínimo: Make, Model, Year, Price, Mileage. Con catálogos más detallados: FuelType, Transmission, Color, Equipment, SourceURL (si el catálogo incluye links o referencias a web).

## Base legal
- PDFs públicamente linkados: accesibles como cualquier recurso web público
- PDF no implica copyright sobre los datos factuales (Make/Model/Year/Price son facts)
- Base: `public_web_access`
- Si PDF requiere login → E08 no accede

## Métricas de éxito
- `e08_pdf_found_rate` — % dealers con PDF inventory localizado
- `e08_extraction_mode` — ratio texto_digital / OCR (OCR ratio alto = warning)
- `e08_vehicle_extraction_rate` — vehículos extraídos / páginas del PDF
- `e08_field_error_rate` — % campos con errores de normalización post-extracción

## Implementación
- Módulo Go (wrapper): `services/pipeline/extraction/strategies/e08_pdf/`
- Python subprocess: `scrapers/pdf_extractor/` con pdfplumber + tabula + pytesseract
- Comunicación Go↔Python via JSON stdin/stdout (mismo patrón que otros workers Python)
- Dependencias Python: pdfplumber, tabula-py, pytesseract, pdf2image, pandas
- Dependencias sistema: tesseract-ocr con language packs (deu, fra, spa, nld, por, ita)
- Coste cómputo: medio-alto (OCR especialmente), batch nocturno
- Cron: semanal (catálogos PDF se actualizan lentamente)

## Fallback strategy
Si E08 falla o PDF no contiene datos útiles:
- E09 (CSV/Excel) si el dealer también tiene feeds en otros formatos
- E11 (Edge onboarding) como alternativa para get datos estructurados directamente del dealer

## Riesgos y mitigaciones
- R-E08-1: PDF protegido por password. Mitigación: detectar via pdfplumber exception, no intentar bypass, registrar como `PDF_PROTECTED`, escalar a E11.
- R-E08-2: OCR de baja calidad en PDFs escaneados de baja resolución. Mitigación: threshold de calidad mínima de OCR output — si confidence OCR < 60%, marcar vehículo como NEEDS_REVIEW.
- R-E08-3: Layout de PDF cambia entre versiones (dealer rediseña catálogo). Mitigación: column-name matching fuzzy (no posicional) para columnas; adaptarse a cambios de layout.
- R-E08-4: PDFs muy grandes (grupos dealer con 500+ vehículos). Mitigación: page-by-page streaming processing, no cargar todo en memoria.

## Iteración futura
- Modelos de visión (ONNX INT8) para detección de layout de tablas en PDFs complejos
- Soporte de Word documents (DOCX) y presentaciones PowerPoint con catálogos embebidos
- Fine-tuning de tesseract sobre corpus de catálogos dealer europeos para mejor reconocimiento de términos técnicos vehiculares
