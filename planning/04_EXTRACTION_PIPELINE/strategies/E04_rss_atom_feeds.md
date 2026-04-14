# E04 — RSS/Atom feeds expuestos

## Identificador
- ID: E04, Nombre: RSS/Atom feeds expuestos, Categoría: Feed
- Prioridad: 900
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
RSS y Atom son protocolos de sindicación de contenido diseñados para consumo automatizado. Algunos dealers exponen feeds de inventario de vehículos — ya sea porque su CMS los genera automáticamente para Custom Post Types, porque configuraron un feed para aggregators, o porque su DMS tiene exportación vía feed. Un feed de inventario es la forma más explícita de consentir la ingesta automatizada: el operador publicó el feed exactamente para ese propósito.

E04 es complementario a E03: mientras E03 cubre la mayoría de sites CMS, E04 captura el subconjunto que no tiene sitemap pero sí feed, además de feeds de actualización que operan en tiempo real (se actualiza cuando entra un coche nuevo).

## Target de dealers
- WordPress con CPT cars/vehicles (genera feed de CPT automáticamente en `/feed/?post_type=car`)
- Dealers con feeds de inventario configurados para AutoScout24, mobile.de importadores
- Dealers con DMS que exporta via RSS
- Plataformas que generan feeds de novedades de stock
- Estimado: 10-15% de dealers con website

## Sub-técnicas

### E04.1 — Discovery de feeds via HTML link tags

El método estándar de publicar feeds es via `<link>` en el `<head>`:

```html
<link rel="alternate" type="application/rss+xml" title="New Cars" href="/feed/cars">
<link rel="alternate" type="application/atom+xml" title="Vehicles" href="/vehicles.atom">
```

E04 parsea el `<head>` de la homepage buscando `rel="alternate"` con `type` en `{"application/rss+xml", "application/atom+xml", "application/feed+json"}` y título que contenga keywords vehicle.

### E04.2 — Autodiscovery por paths canónicos

Sondeo de paths estándar si el discovery via link tags no da resultado:

```
WordPress CPT feeds:
  /feed/?post_type=car
  /feed/?post_type=vehicle
  /feed/?post_type=listing
  /feed/?post_type=auto

Feeds genéricos:
  /feed/cars
  /feed/vehicles
  /inventory.rss
  /inventory.xml
  /cars.rss
  /cars.atom
  /vehicles.rss
  /vehicles.atom
  /voitures.rss
  /gebrauchtwagen.rss
  /coches.rss
  /occasions.rss

DMS-specific feeds:
  /export/rss (algunos DMS)
  /api/feed/vehicles (alguns DMS)
  /datafeed/inventory.xml
```

### E04.3 — Parsing RSS 2.0

Campos de interés en un item RSS vehicle:

```xml
<item>
  <title>BMW 320d xDrive 2021 — 45.000 km — 28.500€</title>
  <link>https://dealer.de/car/bmw-320d-2021</link>
  <description>...</description>
  <pubDate>Mon, 10 Apr 2026 10:00:00 +0200</pubDate>
  <guid>vin:WBAXXX123456789</guid>
  <!-- Extensiones de namespace vehicle (cuando presentes) -->
  <vehicle:make>BMW</vehicle:make>
  <vehicle:model>3 Series</vehicle:model>
  <vehicle:year>2021</vehicle:year>
  <vehicle:mileage>45000</vehicle:mileage>
  <vehicle:price>28500</vehicle:price>
  <vehicle:fuel>diesel</vehicle:fuel>
  <vehicle:vin>WBAXXX123456789</vehicle:vin>
  <enclosure url="https://dealer.de/images/bmw-320d.jpg" type="image/jpeg"/>
  <!-- Media RSS extensions -->
  <media:content url="https://..." medium="image"/>
  <media:thumbnail url="https://..."/>
</item>
```

E04 soporta: RSS 2.0, Atom 1.0, JSON Feed 1.1, Media RSS extensions, namespace vehicle extensions.

### E04.4 — Parsing Atom 1.0

```xml
<entry>
  <title>BMW 320d xDrive 2021</title>
  <link href="https://dealer.de/car/bmw-320d-2021"/>
  <id>urn:uuid:vehicle-12345</id>
  <updated>2026-04-10T10:00:00Z</updated>
  <content type="html">...</content>
  <link rel="enclosure" href="https://..." type="image/jpeg"/>
</entry>
```

### E04.5 — Extracción heurística desde `<description>`

Cuando los campos estructurados del feed son mínimos (solo title + link), E04 aplica un extractor heurístico sobre el `<description>`:
- Regex para Make/Model/Year en el título (`/^(?P<make>\w+)\s+(?P<model>[\w\s]+)\s+(?P<year>20\d{2})/`)
- Regex para precio (`/(?P<price>\d[\d.]+)\s*(?:€|EUR|CHF)/)
- Regex para mileage (`/(?P<km>\d+[\d.]*)\s*(?:km|Km|KM)/`)

Los resultados heurísticos tienen `confidence_contributed` reducido (0.4 vs 0.9 para campos estructurados).

### E04.6 — Monitoreo de feed para delta real-time

Los feeds RSS se actualizan cuando hay cambios. E04 puede ejecutarse en polling cada hora (muy ligero: solo los N últimos items son nuevos en cada ciclo). `<pubDate>` / `<updated>` permiten filtrar items ya procesados sin re-fetch de la página de detalle.

## Formato de datos esperado
XML (RSS 2.0 o Atom 1.0) o JSON (JSON Feed). El feed de vehículos puede tener extensiones de namespace propietario o seguir RSS/Atom puro con toda la info en el `<title>` y `<description>`.

## Campos extraíbles típicamente
Con feed estructurado: Make, Model, Year, Price, SourceURL, ImageURLs (via `<enclosure>` o Media RSS), VIN (si `<guid>` usa patrón `vin:` o hay namespace vehicle).
Con feed mínimo (heurístico): Make, Model, Year, Price (confianza media), SourceURL.

## Base legal
- RSS/Atom: protocolos de sindicación diseñados para consumo automatizado
- Un feed publicado = consentimiento explícito de sindicación
- Base: `sitemap_implicit_license` (mismo racional que sitemaps: publicado para indexación)
- Si `/feed/` está en robots.txt `Disallow`: no acceder (poco frecuente pero posible)

## Métricas de éxito
- `e04_feed_found_rate(país)` — % dealers con feed vehicle localizado
- `e04_structured_field_rate` — % items con campos estructurados (vs heurístico)
- `e04_mean_items_per_feed` — densidad media de catálogo en feed
- `e04_feed_freshness` — `pubDate` del item más reciente (detector de feeds activos vs abandonados)

## Implementación
- Módulo Go: `services/pipeline/extraction/strategies/e04_rss_atom/`
- Dependencias: `encoding/xml` stdlib, `github.com/mmcdole/gofeed` (parser feed multi-formato)
- Sub-módulo: `feed_discovery.go` — link tags + path autodiscovery
- Sub-módulo: `feed_parser.go` — RSS/Atom/JSON Feed con namespace extensions
- Sub-módulo: `heuristic_extractor.go` — regex sobre title/description
- Sub-módulo: `feed_monitor.go` — polling horario con delta detection via pubDate
- Coste cómputo: muy bajo — XML/JSON parsing, sin I/O adicional
- Cron: polling horario para feeds activos, weekly para feeds inactivos

## Fallback strategy
Si E04 no encuentra feed o feed sin datos vehicle:
- E03 (Sitemap) si aún no intentado para este dealer
- E07 (Playwright) si el site tiene inventario visible pero sin feeds ni sitemap vehicle

## Riesgos y mitigaciones
- R-E04-1: feed declarado pero con items vacíos o con solo 10 últimos vehículos. Mitigación: detectar si feed es completo o parcial via `<channel><item>` count vs indicador total en descripción. Si parcial, complementar con E03.
- R-E04-2: feeds con texto HTML en `<description>` no escapado. Mitigación: CDATA-aware parser.
- R-E04-3: feeds de blog/noticias detectados erróneamente como inventario. Mitigación: keyword filter en feed title + primer item sample — si keywords vehicle ausentes, descartar.
- R-E04-4: feed HTTPS con certificado inválido. Mitigación: fetch con TLS strict (no skip verify); logear para alerta operativa.

## Iteración futura
- JSON Feed 1.1 tiene soporte nativo para metadata personalizada — soporte extendido cuando se detecte
- Auto-aprendizaje de namespaces vehicle propietarios no conocidos a priori
- Cross-feed comparison entre mismo dealer en aggregators vs feed propio → detección de discrepancias de precio
