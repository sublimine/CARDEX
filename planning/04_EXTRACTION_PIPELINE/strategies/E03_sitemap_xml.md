# E03 — Sitemap.xml + sitemap_index.xml + robots.txt sitemap directives

## Identificador
- ID: E03, Nombre: Sitemap.xml crawl estructurado, Categoría: Sitemap
- Prioridad: 1000
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
El protocolo Sitemaps (sitemaps.org) fue diseñado exactamente para que los webmasters indiquen a los crawlers qué URLs indexar. Un dealer que publica un sitemap no solo permite el crawl: lo invita explícitamente. E03 es la estrategia de cobertura más amplia (la mayoría de CMS modernos generan sitemap automáticamente) y el fundamento legal más sólido (consentimiento explícito por publicación del sitemap).

E03 opera en dos modos:
1. **Index mode:** extrae URLs y aplica E01 (JSON-LD) o E06 (Microdata) sobre cada página vehicle — actúa como orquestador secundario.
2. **Sitemap-only mode:** cuando las páginas vehicle no tienen structured data, E03 produce una lista de URLs que el orquestador marca para E07 (Playwright).

## Target de dealers
- Todos los dealers con CMS moderno que genera sitemaps (WordPress, Shopify, Joomla, Drupal, Wix, Squarespace, Webflow, y los DMS dealer platforms)
- Estimado: 60-70% de dealers con website tienen sitemap expuesto

## Sub-técnicas

### E03.1 — Discovery de sitemap

Secuencia de discovery en orden:
1. `robots.txt` — parse de directivas `Sitemap:` (puede haber múltiples)
2. URLs canónicas de fallback probadas en secuencia si robots.txt no tiene Sitemap:
   ```
   /sitemap.xml
   /sitemap_index.xml
   /sitemap-index.xml
   /sitemap/sitemap.xml
   /page-sitemap.xml
   /post-sitemap.xml
   /car-sitemap.xml
   /vehicle-sitemap.xml
   /listing-sitemap.xml
   /wp-sitemap.xml              (WordPress 5.5+)
   /sitemap_vehicles.xml
   ```
3. HTML `<head>` parse: algunas CMS incluyen `<link rel="sitemap" href="...">` o meta robots con sitemap hint

### E03.2 — Parse de sitemap_index

Un `sitemap_index.xml` contiene referencias a N sub-sitemaps. E03 los descarga todos y construye la lista completa de URLs. Sub-sitemaps relevantes: aquellos cuyo nombre contiene `car`, `vehicle`, `listing`, `inventory`, `gebraucht`, `occasion`, `voiture`, `coche`.

Ejemplo de estructura típica:
```xml
<sitemapindex>
  <sitemap><loc>https://dealer.de/sitemap-vehicles.xml</loc></sitemap>
  <sitemap><loc>https://dealer.de/sitemap-pages.xml</loc></sitemap>
  <sitemap><loc>https://dealer.de/sitemap-posts.xml</loc></sitemap>
</sitemapindex>
```

### E03.3 — Filtro de URLs vehicle por patterns

De la lista completa de URLs del sitemap, filtrar aquellas que corresponden a vehículos:

```
Path patterns positivos:
  /gebrauchtwagen/, /gebrauchte-, /pkw/,
  /occasion/, /occasions/, /vehicules-occasion/,
  /voitures-occasion/, /voiture-d-occasion/,
  /coche/, /coches-ocasion/, /vehiculos/,
  /auto/, /autos/, /tweedehands-auto/,
  /voertuigen/, /occasiewagens/,
  /cars/, /used-cars/, /inventory/,
  /vehicles/, /stock/, /listings/

URL parameter patterns:
  ?type=car, ?category=vehicles, ?post_type=car
  listing_id=, vehicle_id=, car_id=

Exclusiones:
  /sitemap, /page/, /blog/, /news/, /contact,
  /about, /impressum, /mentions-legales
```

### E03.4 — Fetch individual con E01/E06

Para cada URL filtrada:
1. Fetch con rate limit configurable (default: 1 req/s para el dominio)
2. Extracción JSON-LD (E01 inline)
3. Si no hay JSON-LD: extracción Microdata/RDFa (E06 inline)
4. Si ni JSON-LD ni Microdata: página marcada para E07 (XHR discovery)

E03 actúa como multiplexor: delega la extracción real a E01/E06 por página, y agrega resultados.

### E03.5 — `lastmod` y delta crawling

Las entradas de sitemap pueden incluir `<lastmod>`. E03 usa este campo para:
- En re-extracciones, saltar URLs donde `lastmod < last_extraction_at` (sin cambios)
- Priorizar URLs con `lastmod` reciente (vehículos nuevos primero)

Esto reduce drásticamente el número de fetches en ciclos incrementales.

### E03.6 — Gestión de sitemaps muy grandes

Algunos dealers tienen >10.000 URLs en sitemap (grupos grandes). Estrategia:
- Procesamiento en batches de 100 URLs con paralelismo controlado (5 workers concurrentes por dominio)
- Back-pressure: si el dominio retorna 429 (Too Many Requests), reducir workers y respetar Retry-After
- Checkpoint: guardar posición en sitemap para reanudar si el proceso se interrumpe

## Formato de datos esperado
XML siguiendo el protocolo sitemaps.org (versión 0.9):

```xml
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://dealer.de/gebrauchtwagen/bmw-320d-2021</loc>
    <lastmod>2026-04-10</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>
</urlset>
```

## Campos extraíbles típicamente
E03 no extrae datos de vehículo directamente — provee la lista de URLs. Los campos provienen de E01/E06 aplicados sobre esas URLs. Sin embargo, `<loc>` y el slug de URL pueden aportar: Make/Model/Year via URL parsing (heurístico, baja confianza, complementario).

## Base legal
- Sitemaps protocol: diseñado explícitamente para crawlers automatizados
- Publicación intencionada: el dealer (o su CMS) generó y publicó el sitemap
- Base: `sitemap_implicit_license` — consentimiento implícito máximo
- Sitemap respetado como guía: si una URL está en Sitemap pero también en `Disallow` robots.txt → no se accede (robots.txt gana)

## Métricas de éxito
- `e03_sitemap_found_rate(país)` — % dealers con sitemap localizado
- `e03_vehicle_urls_per_dealer` — URLs de vehículos filtradas
- `e03_lastmod_coverage` — % URLs con `lastmod` (permite delta crawling)
- `e03_page_extraction_success_rate` — % URLs que producen datos via E01/E06

## Implementación
- Módulo Go: `services/pipeline/extraction/strategies/e03_sitemap/`
- Dependencias: `encoding/xml` stdlib, `net/http` stdlib
- Sub-módulo: `sitemap_discovery.go` — secuencia de discovery
- Sub-módulo: `sitemap_parser.go` — parse de sitemap_index + urlset + filtrado
- Sub-módulo: `delta_tracker.go` — gestión de lastmod + checkpoints
- Worker pool con back-pressure via semaphore
- Coste cómputo: medio-bajo por URL (markup fetch es ligero)
- Cron: re-extracción cada 48h, delta crawling en cada ciclo

## Fallback strategy
Si E03 no encuentra sitemap o el sitemap no contiene URLs vehicle:
- Intentar E04 (RSS/Atom feeds)
- Si el site usa WP → intentar E02 (WP REST API)
- Si todo falla en structured/semi-structured → escalar a E07 (Playwright)

## Riesgos y mitigaciones
- R-E03-1: sitemap mal-formado (XML inválido). Mitigación: parser lenient que tolera entidades sin escapar + namespaces incorrectos.
- R-E03-2: sitemap presente pero sin URLs de vehículos (site web solo institucional, inventario en subdomain). Mitigación: detección de subdominios via Familia N + retry en subdomain.
- R-E03-3: sitemap muy grande (>50k URLs) en grupos dealer grandes. Mitigación: procesamiento en streaming + checkpoints de estado.
- R-E03-4: `lastmod` falsamente actualizado (CMS actualiza siempre `lastmod` aunque no haya cambios). Mitigación: `fingerprint_sha256` del contenido de la página — si fingerprint igual al anterior, no re-procesar.

## Iteración futura
- Soporte de Sitemap extensions para imágenes (`<image:image>`) → extracción directa de ImageURLs desde sitemap sin fetch adicional de página
- Soporte para Sitemap extensions de noticias (`<news:news>`) para cross-Familia O (prensa)
- Detección de sitemaps rotados (dealer cambia URL de sitemap) via CT logs (cross-Familia N)
