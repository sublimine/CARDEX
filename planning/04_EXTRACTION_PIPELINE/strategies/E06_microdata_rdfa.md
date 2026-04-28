# E06 — Microdata (HTML5) y RDFa fallback

## Identificador
- ID: E06, Nombre: Microdata/RDFa structured data, Categoría: Legacy-structured
- Prioridad: 800
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Antes de que JSON-LD se convirtiera en el formato dominante para structured data (circa 2016+), los webmasters usaban Microdata (HTML5 W3C spec) y RDFa (W3C) para embeber Schema.org markup directamente en los atributos HTML. Aunque JSON-LD es ahora la recomendación de Google, un porcentaje de sites dealer — especialmente aquellos con CMS custom o temas WordPress antiguos — aún usan Microdata o RDFa. E06 captura ese segmento sin requerir JavaScript rendering.

## Target de dealers
- Sites WordPress con temas antiguos (pre-2016) que usan `itemscope`/`itemtype` en lugar de JSON-LD
- Sites custom PHP/ASP.NET con Schema.org Microdata embebido en plantillas
- Sites Joomla legacy con structured data components
- Sites con CMS propietario de bajo mantenimiento
- Estimado: 5-10% del universo dealer (segmento decreciente pero aún relevante)

## Sub-técnicas

### E06.1 — Microdata HTML5 parsing

Los atributos clave a buscar en el HTML:

```html
<!-- Ejemplo de Vehicle en Microdata -->
<div itemscope itemtype="http://schema.org/Car">
  <span itemprop="name">BMW 320d</span>
  <span itemprop="brand" itemscope itemtype="http://schema.org/Brand">
    <span itemprop="name">BMW</span>
  </span>
  <span itemprop="vehicleModelDate">2021</span>
  <span itemprop="mileageFromOdometer" content="45000">45.000 km</span>
  <span itemprop="offers" itemscope itemtype="http://schema.org/Offer">
    <span itemprop="price" content="28500">28.500 €</span>
    <span itemprop="priceCurrency" content="EUR">EUR</span>
  </span>
  <link itemprop="url" href="https://dealer.de/cars/bmw-320d-2021"/>
  <img itemprop="image" src="https://cdn.dealer.de/bmw-320d.jpg"/>
</div>
```

Estrategia de extracción:
1. Buscar todos los elementos con `itemscope` + `itemtype` que contienen `schema.org/Car`, `schema.org/Vehicle`, `schema.org/MotorVehicle`
2. Para cada elemento, iterar sus descendientes con `itemprop`
3. Extraer el valor: para `content` attribute → usar `content`; para `href` → usar `href`; para `src` → usar `src`; para texto → usar `textContent` limpio
4. Manejar nested `itemscope` (offers, brand, engine) recursivamente

### E06.2 — RDFa parsing

```html
<!-- Ejemplo RDFa Lite -->
<div vocab="http://schema.org/" typeof="Car">
  <span property="name">BMW 320d xDrive</span>
  <span property="brand" typeof="Brand">
    <span property="name">BMW</span>
  </span>
  <span property="vehicleModelDate">2021</span>
  <div property="offers" typeof="Offer">
    <span property="price">28500</span>
    <span property="priceCurrency">EUR</span>
  </div>
  <a property="url" href="https://dealer.de/bmw-320d">Ver detalles</a>
</div>
```

RDFa usa `vocab` (o `prefix`), `typeof`, `property` en lugar de `itemscope`, `itemtype`, `itemprop`. El parser E06 soporta ambas syntaxis.

### E06.3 — OpenGraph + meta tags como señal auxiliar

Cuando neither JSON-LD ni Microdata/RDFa están presentes, algunos sites tienen:

```html
<meta property="og:title" content="BMW 320d 2021 — 28.500€">
<meta property="og:image" content="https://cdn.dealer.de/bmw.jpg">
<meta property="og:url" content="https://dealer.de/cars/bmw-320d">
<meta name="description" content="BMW 320d 2021, 45.000km, diesel, automatico">
```

OpenGraph no tiene tipos vehicle, pero `og:title` + `og:image` + `og:url` permiten extraer SourceURL e ImageURL. El título puede parsearse heurísticamente (como en E04.5). Confidence reducido.

### E06.4 — Inventario multi-página

Al igual que E01, E06 aplicado a una inventory listing page puede encontrar múltiples vehículos si el HTML contiene N bloques `itemscope`. Cada bloque se extrae independientemente.

Si el dealer tiene paginación de inventario, E06 itera páginas usando links de paginación detectados en el HTML (`<a rel="next">`, `?page=2`, etc.).

## Formato de datos esperado
HTML estático con atributos `itemscope`/`itemtype`/`itemprop` (Microdata) o `vocab`/`typeof`/`property` (RDFa). No requiere JavaScript execution.

## Campos extraíbles típicamente
Con Microdata bien implementado: mismo rango que E01 (Make, Model, Year, Mileage, Price, SourceURL, ImageURLs, VIN si publicado). Con implementación mínima: Make, Model, Year, Price, SourceURL, 1 imagen (via og:image).

## Base legal
- Microdata/RDFa: markup embebido en HTML público, accesible via robots (mismo racional que JSON-LD)
- Base: `schema_org_syndication` — intención de sindicación explícita via structured markup
- robots.txt respetado

## Métricas de éxito
- `e06_applicable_rate(país)` — % dealers con Microdata/RDFa Vehicle detectado
- `e06_vs_e01_rate` — ratio E06 usable / E01 usable (evolución de adopción JSON-LD)
- `e06_field_completeness` — completitud comparada con E01

## Implementación
- Módulo Go: `services/pipeline/extraction/strategies/e06_microdata/`
- Dependencias: `golang.org/x/net/html` para HTML parsing
- Sub-módulo: `microdata_parser.go` — walk del DOM buscando itemscope/itemtype
- Sub-módulo: `rdfa_parser.go` — walk del DOM buscando vocab/typeof/property
- Sub-módulo: `opengraph_extractor.go` — meta tags como fallback auxiliar
- Coste cómputo: bajo-medio — HTML tree walk, sin I/O adicional
- Cron: re-extracción cada 72h (sites legacy cambian menos frecuentemente)

## Fallback strategy
Si E06 falla o datos insuficientes:
- E07 (Playwright XHR) si el site tiene inventario dinámico invisible en HTML estático
- E08 (PDF) si el site linkea a un catálogo PDF descargable

## Riesgos y mitigaciones
- R-E06-1: HTML mal formado que rompe el parser. Mitigación: usar parser lenient `golang.org/x/net/html` que tolera HTML inválido.
- R-E06-2: Microdata presente pero datos en texto localizado con separadores numéricos locales (`28.500,00` vs `28500`). Mitigación: normalizer numérico que detecta locale por `content` attribute.
- R-E06-3: RDFa con prefijos custom (`ex:vehicle`) en lugar de vocab schema.org. Mitigación: solo procesar cuando vocab sea schema.org; custom RDFa ignorado.
- R-E06-4: Deprecated rapidez — sites con Microdata migran a JSON-LD progresivamente. Mitigación: si E01 ya extrae datos, E06 no se ejecuta (economía de requests).

## Iteración futura
- Soporte de Microdata extensions para propiedades vehicle EV (cuando la industria las estandarice)
- Detector automático de "degradación de structured data" (un dealer que tenía E01 pasa a E06 → alerta de regresión para outreach)
