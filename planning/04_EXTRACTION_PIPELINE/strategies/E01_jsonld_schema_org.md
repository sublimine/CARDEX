# E01 — JSON-LD Schema.org Vehicle inline

## Identificador
- ID: E01, Nombre: JSON-LD Schema.org Vehicle inline, Categoría: Structured-data
- Prioridad: 1200 (máxima en cascada)
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Schema.org define tipos `Vehicle`, `Car`, `MotorVehicle`, `BusOrCoach`, `AutoDealer` que los webmasters embeben como bloques JSON-LD en el `<head>` o en el `<body>` de sus páginas. Este markup está diseñado explícitamente para que motores de búsqueda lo consuman — es sindicación intencional de datos estructurados. E01 es la estrategia de extracción de mayor calidad porque los datos ya están normalizados en el markup sin necesidad de HTML parsing frágil.

Google Search Console incentiva activamente la adopción de Schema.org para `Vehicle` (rich results en búsquedas de coches). Esto ha llevado a una adopción creciente en CMS modernos: WordPress con Yoast SEO, Rank Math, All in One SEO genera markup automáticamente; Shopify tiene apps para ello; cualquier Next.js/Nuxt moderno puede incluirlo.

## Target de dealers
- Sites WordPress con plugins de inventario vehicular + SEO plugin (Yoast/RankMath)
- Sites Shopify con Vehicle schema app
- Sites React/Vue/Next.js con JSON-LD component
- Sites construidos sobre plataformas dealer modernas que generan Schema.org automáticamente
- Estimado: 30-40% del universo dealer EU con website propio

## Sub-técnicas

### E01.1 — Extracción desde inventory listing pages
1. Fetch de la página de inventario principal del dealer (`/inventory`, `/ocasion`, `/gebrauchtwagen`, `/occasions`, etc. — discovery desde sitemap o slug patterns conocidos)
2. Parse del `<head>` buscando `<script type="application/ld+json">`
3. Extracción de todos los bloques JSON-LD del documento
4. Filtro por `@type` in `{"Vehicle", "Car", "MotorVehicle", "BusOrCoach", "Motorcycle"}`
5. Si el bloque es `ItemList` → iterar `itemListElement` extrayendo cada `Vehicle` child
6. Si el bloque es `AutoDealer` con `hasOfferCatalog` → descender al catálogo

### E01.2 — Extracción desde product/vehicle detail pages
Si la inventory page contiene enlaces a páginas de detalle individuales:
1. Fetch de cada vehicle detail page (respetando rate limit — 1 req/s por defecto)
2. Extracción del bloque `Vehicle`/`Car` individual
3. Merge con datos ya extraídos desde listing page

### E01.3 — Extracción desde homepage (AutoDealer schema)
Algunos dealers embeben un `AutoDealer` schema en la homepage con `makesOffer` que lista vehículos directamente. Este es el caso más eficiente (1 request = catálogo completo).

### E01.4 — Paginación de inventory
Si la inventory page tiene paginación (`?page=2`, `?offset=20`, `?p=3`):
- Detección de paginación via links `rel="next"` en `<head>` o via `ListItem` position en JSON-LD
- Fetch recursivo hasta agotar páginas (máximo configurable, default 50 páginas)
- Dedup por `url` + `sku` (VIN)

### E01.5 — Vocabulario Schema.org completo para Vehicle

Propiedades mapeadas:

```
Schema.org property         → VehicleRaw field
─────────────────────────────────────────────────────
sku / vehicleIdentificationNumber → VIN
brand.name / manufacturer   → Make
name / model / vehicleModelDate → Model, Year
mileageFromOdometer.value   → Mileage
fuelType                    → FuelType
vehicleTransmission         → Transmission
vehicleEngine.enginePower.value → PowerKW
bodyType                    → BodyType
color                       → Color
numberOfDoors               → Doors
numberOfForwardGears / seatingCapacity → seats
offers.price                → PriceNet o PriceGross
offers.priceCurrency        → Currency
offers.priceSpecification.valueAddedTaxIncluded → VATMode
url / @id                   → SourceURL
image.contentUrl / image    → ImageURLs
additionalProperty (list)   → Equipment
```

## Formato de datos esperado

JSON-LD embebido en `<script type="application/ld+json">` tag. Puede ser:
- Un objeto singular `{ "@type": "Car", ... }`
- Un array `[{ "@type": "Car" }, { "@type": "Car" }]`
- Un `ItemList` con `itemListElement` de tipo `Car`
- Un `AutoDealer` con `hasOfferCatalog.itemListElement`
- Una combinación (múltiples bloques JSON-LD en el mismo documento)

## Campos extraíbles típicamente
Con schema.org bien implementado: VIN (si publicado), Make, Model, Year, Mileage, FuelType, Transmission, PowerKW, BodyType, Color, PriceGross/Net, Currency, SourceURL, ImageURLs (hasta N), Equipment (via additionalProperty).

Con schema.org mínimo (frecuente en implementaciones rápidas): Make, Model, Year, Price, SourceURL, 1 imagen.

## Base legal
- Schema.org markup está diseñado para consumo por motores de búsqueda: `"Structured data markup helps search engines understand your content"` (Google Search Central).
- Consentimiento implícito por publicación: el operador del site embede JSON-LD intencionalmente para indexación.
- Base: `schema_org_syndication` — datos publicados en formato de sindicación estándar para consumo automatizado.
- Ningún bypass de control de acceso. robots.txt respetado. Si `/inventory` está en `Disallow`, E01 no accede.

## Métricas de éxito
- `e01_applicable_rate(país)` — % dealers con JSON-LD Vehicle detectado
- `e01_full_success_rate` — % de extracciones con todos los campos críticos
- `e01_vehicles_per_dealer` — densidad de catálogo extraído
- `e01_field_completeness` — % campos del VehicleRaw cubiertos en media

## Implementación
- Módulo Go: `services/pipeline/extraction/strategies/e01_jsonld/`
- Dependencias: `golang.org/x/net/html` para parsing HTML, `encoding/json` stdlib para JSON-LD
- Sin dependencias externas: cero Playwright, cero headless browser
- Parser: extracción de todos los `<script type="application/ld+json">` → unmarshal → walk de types
- Gestión de errores: JSON-LD malformado frecuente (falta de escape, BOM) → parser lenient con recover
- Coste cómputo: muy bajo — puro CPU, sin I/O adicional más allá del fetch HTML inicial
- Cron: re-extracción cada 24h

## Fallback strategy
Si E01 falla o `PartialSuccess` con `FieldsMissing` críticos:
1. Intentar E02 si `dealer.CMSDetected` en KnownCMSWithRestAPI
2. Intentar E03 (Sitemap) para obtener lista completa de URLs de detalle y reintento E01 por página
3. Intentar E06 (Microdata/RDFa) si site tiene structured data en formato legacy

## Riesgos y mitigaciones
- R-E01-1: JSON-LD malformado (falta de escape, encoding issues). Mitigación: parser con fallback lenient, log de parse errors.
- R-E01-2: JSON-LD presente pero con campos mínimos (solo nombre y precio). Mitigación: `PartialSuccess` + complementar con E03/E07.
- R-E01-3: JSON-LD dinámico (generado por JS, no en HTML inicial). Mitigación: si el fetch estático no retorna JSON-LD pero Familia D detectó site React/Vue → escalar directamente a E07 (Playwright).
- R-E01-4: Datos intencionalmente incompletos (dealer oculta VIN en schema). Mitigación: aceptar sin VIN, campo opcional.

## Iteración futura
- Feed de nuevas propiedades Schema.org Vehicle a medida que evoluciona el vocabulario (EV-specific props: `batteryCapacity`, `electricRange`)
- Parser de `AutoDealer.department` para dealers multi-marca con secciones por marca
- Detección de `Offer.availability` → `ItemAvailability.InStock` para filtrar ya-vendidos
