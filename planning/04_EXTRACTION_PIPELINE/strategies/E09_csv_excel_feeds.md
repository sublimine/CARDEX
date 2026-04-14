# E09 — CSV/Excel feeds linkados

## Identificador
- ID: E09, Nombre: CSV/Excel feeds linkados, Categoría: Tabular-feed
- Prioridad: 400
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Algunos dealers publican su inventario como archivo CSV o Excel descargable — generalmente porque han configurado una exportación automática desde su DMS para alimentar agregadores, o porque usan spreadsheets para gestión interna y los publican directamente. Estos feeds son frecuentemente la representación más completa del inventario (el DMS exporta todos los campos), y su descarga es completamente legítima dado que el dealer los publica públicamente.

## Target de dealers
- Dealers con DMS que tiene exportación CSV/Excel para agregadores
- Dealers que usan Google Sheets o Excel Online como inventario con link público
- Dealers configurados para exportar a AutoScout24/mobile.de via CSV que también exponen el feed en su web
- Dealers con catálogos Excel B2B para compradores mayoristas
- Estimado: 5-8% del universo dealer

## Sub-técnicas

### E09.1 — Discovery de feeds CSV/Excel en el site

Búsqueda de links a archivos CSV/XLSX/XLS:
- `<a href="*.csv">`, `<a href="*.xlsx">`, `<a href="*.xls">`
- Headers HTTP: `Content-Disposition: attachment; filename="inventory.csv"`
- `Content-Type: text/csv`, `application/vnd.ms-excel`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- Keywords en link text: "download inventory", "export", "feed", "CSV", "Excel", "Datei"

Paths de discovery adicionales:
```
/inventory.csv
/vehicles.csv
/stock.csv
/export.csv
/feed.csv
/fahrzeuge.csv
/voitures.csv
/coches.csv
/datafeed/vehicles.csv
/export/inventory.xlsx
```

### E09.2 — Google Sheets public CSV export

Algunos dealers usan Google Sheets como DMS. Un Sheet publicado públicamente tiene URL de export CSV:
```
https://docs.google.com/spreadsheets/d/SHEET_ID/export?format=csv&gid=SHEET_GID
```

E09 detecta links a Google Sheets y convierte a la URL de export CSV. Completamente legal (el dealer publicó el Sheet como público).

### E09.3 — Parsing CSV

```python
import pandas as pd

df = pd.read_csv(
    url,
    encoding="utf-8",           # intentar primero
    sep=None,                    # auto-detect (comma, semicolon, tab)
    engine="python",
    on_bad_lines="skip",         # saltarse filas mal formadas
    thousands=".",               # separador miles europeo
    decimal=","                  # separador decimal europeo
)
```

Manejo de encodings: UTF-8, UTF-8-BOM, ISO-8859-1, ISO-8859-15, Windows-1252 (frecuente en exports DMS alemanes/franceses). Intento secuencial hasta parseo exitoso.

### E09.4 — Parsing Excel (.xlsx, .xls)

```python
import openpyxl  # para .xlsx
import xlrd      # para .xls legacy

wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
# Seleccionar hoja relevante (heurístico: hoja con más filas, o hoja con nombre "Inventory/Stock/Vehicles")
ws = wb.active
```

Soporte de multiple sheets: si el workbook tiene múltiples hojas, se analiza cada una para determinar cuál contiene el inventario de vehículos.

### E09.5 — Header normalization

Los feeds CSV/Excel tienen headers en el idioma del dealer y con nomenclatura propietaria del DMS. Normalización via matching fuzzy:

```
Header patterns → VehicleRaw field
────────────────────────────────────────────────────────────
Marke|Fabrikat|Marca|Marque|Make → Make
Modell|Modelo|Modèle|Model       → Model
Baujahr|Año|Année|Year|Jahrgang  → Year
KM|Kilometerstand|Km|Miles       → Mileage
Preis|Precio|Prix|Price|Preis_B  → PriceGross
Preis_N|Precio_neto|Prix_HT      → PriceNet
Kraftstoff|Combustible|Carburant → FuelType
Getriebe|Transmision|Boite       → Transmission
FIN|VIN|Fahrgestellnummer        → VIN
Bilder|Fotos|Images|Photos       → ImageURLs (pipe-separated list of URLs)
Link|URL|Detailseite             → SourceURL
```

Headers desconocidos van a `AdditionalFields`.

### E09.6 — Detección de actualización via HTTP ETag/Last-Modified

Para feeds CSV periodicamente actualizados, E09 usa `ETag` y `Last-Modified` headers para determinar si el archivo cambió desde el último fetch. Si no cambió → skip, sin re-processing.

## Formato de datos esperado
CSV con primera fila de headers + N filas de datos, o XLSX con estructura tabular. Separadores variables (coma, punto y coma, tabulador). Encoding variable por país.

## Campos extraíbles típicamente
Con DMS export completo: todos los campos críticos + secundarios (Equipment como columna adicional o string concatenado). Con spreadsheet manual: Make, Model, Year, Price, Mileage mínimo.

## Base legal
- Feeds CSV/Excel públicamente accesibles: no requieren autenticación
- `Content-Disposition: attachment` = el dealer invita la descarga
- Base: `public_web_access`

## Métricas de éxito
- `e09_feed_found_rate` — % dealers con CSV/Excel localizado
- `e09_encoding_error_rate` — % files con problemas de encoding
- `e09_header_match_rate` — % headers reconocidos via fuzzy matching
- `e09_vehicles_extracted_rate` — vehículos extraídos / filas del feed

## Implementación
- Módulo Go (wrapper): `services/pipeline/extraction/strategies/e09_csv_excel/`
- Python subprocess: `scrapers/tabular_extractor/` con pandas + openpyxl + xlrd
- Sub-módulo: `feed_discovery.go` — link HTML + path autodiscovery + Google Sheets detection
- Sub-módulo: `header_normalizer.py` — YAML-driven fuzzy header matching
- Sub-módulo: `encoding_detector.py` — chardet para detección de encoding
- Coste cómputo: bajo (pandas parsing es rápido)
- Cron: semanal para feeds estáticos, diario para feeds con update frecuente (detectado via Last-Modified)

## Fallback strategy
Si E09 no encuentra feed o feed sin datos vehicle:
- E07 (Playwright) si el site tiene inventario dinámico

## Riesgos y mitigaciones
- R-E09-1: CSV con encoding incorrecto en headers (nombres de marca con umlauts/tildes corrompidos). Mitigación: chardet + intento de múltiples encodings + log de encoding seleccionado.
- R-E09-2: Excel con formatos de celda no estándar (fechas serializadas como número serial Excel). Mitigación: openpyxl data_only=True + conversión de fecha serial.
- R-E09-3: Feed CSV con URLs de imágenes inaccesibles (CDN privado, URLs de DMS interno). Mitigación: verificar accesibilidad de URL imagen antes de registrar; si inaccesible → campo ausente.
- R-E09-4: Feed desactualizado (dealer dejó de actualizar el CSV pero el link sigue activo). Mitigación: `Last-Modified` header + comparar con `last_confirmed_at` en knowledge graph; si delta > 30 días sin actualización → alerta.

## Iteración futura
- Soporte de OpenDocument Spreadsheet (.ods) — usado en algunos deployments LibreOffice
- Auto-learning de schemas CSV propietarios nuevos (cuando aparezca DMS no conocido con CSV export)
- Integración con SFTP/FTP push para dealers que prefieren feed vía protocolo file transfer
