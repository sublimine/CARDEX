# Familia B — Cartografía geográfica-comercial

## Identificador
- ID: B
- Nombre: Cartografía geográfica-comercial
- Categoría: Geo-comercial
- Fecha: 2026-04-14
- Estado: DOCUMENTADO

## Propósito y rationale
Capturar la ubicación física de toda actividad relacionada con venta/reparación de vehículos en los seis países. Esta familia complementa A: una empresa en registro mercantil sin POI físico identificado puede ser empresa fantasma o pure online; una POI física sin empresa registrada es señal de inconsistencia administrativa o entidad nueva no aún auditada.

Adicionalmente, los POIs aportan datos que A no tiene: horario, teléfono, fotos exteriores, reseñas de usuarios, categorías más finas que NACE.

## Sub-técnicas y fuentes

### B.1 — OpenStreetMap (todos los países)

#### B.1.1 — Overpass API
- URL base: https://overpass-api.de/api/interpreter
- Acceso: HTTP libre, sin autenticación
- Rate limit: documentado en https://wiki.openstreetmap.org/wiki/Overpass_API#Limitations
- Base legal: ODbL (Open Database License)

#### B.1.2 — Tags relevantes
Query combinatorial obligatoria — un solo tag pierde long-tail:

```overpass
[shop=car]                   — venta de coches
[shop=motorcycle]            — venta motos (algunos también coches)
[shop=caravan]               — venta caravanas
[shop=trailer]               — venta remolques
[shop=truck]                 — venta camiones
[craft=car_repair]           — taller (algunos venden)
[office=automotive]          — oficinas comerciales auto
[amenity=car_rental]         — alquiler (vende ex-fleet)
[shop=car;second_hand=only]  — venta exclusiva ocasión
[service:vehicle:car_repair] — atributo de servicio
[brand:wikidata=Q*]          — POIs marca-asociados (BMW, VW, etc.)
```

#### B.1.3 — Query template por país
```overpass
[out:json][timeout:300];
area["ISO3166-1"="DE"]->.searchArea;
(
  node["shop"~"car|motorcycle|caravan|trailer|truck"](area.searchArea);
  way["shop"~"car|motorcycle|caravan|trailer|truck"](area.searchArea);
  node["craft"="car_repair"](area.searchArea);
  way["craft"="car_repair"](area.searchArea);
  node["office"="automotive"](area.searchArea);
);
out center tags;
```

Repetir para FR, ES, BE, NL, CH cambiando el ISO 3166-1.

#### B.1.4 — Datos extraídos por POI
- Coordenadas (lat, lon)
- Nombre comercial
- Dirección normalizada (addr:street, addr:city, addr:postcode)
- Teléfono (phone, contact:phone)
- Website (website, contact:website)
- Email (email, contact:email)
- Horario (opening_hours)
- Marca asociada (brand, brand:wikidata)
- Categoría (shop, craft, office, amenity, second_hand)

### B.2 — Wikidata SPARQL

#### B.2.1 — Endpoint
- URL: https://query.wikidata.org/sparql
- Acceso: HTTP libre
- Base legal: CC0

#### B.2.2 — Query SPARQL para entidades dealer por país
```sparql
SELECT DISTINCT ?dealer ?dealerLabel ?country ?coords ?website WHERE {
  ?dealer wdt:P31/wdt:P279* wd:Q4830453 .   # subclase de business
  ?dealer wdt:P452 wd:Q190960 .             # industria automoción
  ?dealer wdt:P17 ?country .
  ?country wdt:P297 ?iso .
  FILTER(?iso IN ("DE", "FR", "ES", "BE", "NL", "CH"))
  OPTIONAL { ?dealer wdt:P625 ?coords. }
  OPTIONAL { ?dealer wdt:P856 ?website. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }
}
```

#### B.2.3 — Cobertura
- Wikidata privilegia entidades grandes/conocidas
- Cobertura long-tail muy baja
- Útil para validación cruzada con A y para OEM dealers grandes

### B.3 — GeoNames

#### B.3.1 — Servicio
- URL: http://www.geonames.org
- Acceso: API + bulk dump gratis (con cuenta)
- Featurecode: BLDG (building), commerce category
- Estrategia: cross-validation con OSM, no fuente primaria

### B.4 — Yellow Pages digitales

#### B.4.1 — Por país
| País | Servicio | URL | Acceso |
|---|---|---|---|
| DE | Gelbe Seiten | https://www.gelbeseiten.de | HTML, anti-bot moderado |
| DE | Das Örtliche | https://www.dasoertliche.de | HTML |
| FR | Pages Jaunes | https://www.pagesjaunes.fr | HTML, JS-rendered |
| ES | Páginas Amarillas | https://www.paginasamarillas.es | HTML |
| NL | Telefoongids | https://www.detelefoongids.nl | HTML, anti-bot moderado |
| BE | Gouden Gids | https://www.goudengids.be | HTML |
| CH | local.ch | https://www.local.ch | HTML, JS-rendered |

#### B.4.2 — Estrategia
Búsqueda geo-paginated por código postal + categoría "garage automobile" / "Autohändler" / "concesionario" / etc. Acceso transparente, respeto rate limits, sin evasión.

### B.5 — INSPIRE European Geospatial

- Marco legal: Directiva 2007/2/CE INSPIRE
- Datasets nacionales con metadatos comerciales-cartográficos
- Cobertura específica de actividades económicas en algunos países
- Acceso: portales nacionales INSPIRE

### B.6 — Datasets municipales/locales abiertos

- DE: Berlin Open Data (Gewerbedaten Berlin), München Open Data
- FR: data.gouv.fr (catalogues municipaux), Paris Open Data
- ES: datos.madrid.es, opendata.barcelona.cat
- NL: data.overheid.nl
- BE: opendata.brussels, Antwerpen Open Data
- CH: opendata.swiss + portales cantonales

Estrategia: agregación paciente, una vez por ciudad mayor.

## Base legal
- OSM: ODbL
- Wikidata: CC0
- GeoNames: CC BY 4.0
- Yellow Pages: HTML público sujeto a ToS — respeto estricto a robots.txt + rate limits
- INSPIRE: directiva europea explícita de reutilización
- Open data municipal: licencias específicas por dataset, mayoritariamente CC BY o equivalente

## Métricas

- `unique_pois_discovered(país)`
- `geo_resolution_quality(país)` — % POIs con dirección + teléfono + website
- `cross_validation_rate_with_A(país)` — % POIs cuyo dealer está también en familia A
- `web_discovery_rate(país)` — % POIs con website resolvable (input crítico para familia C)

## Implementación

- Módulo Go: `discovery/family_b/`
- Sub-módulos: `osm/`, `wikidata/`, `geonames/`, `yellowpages/`, `inspire/`, `municipal/`
- Persistencia: SQLite tabla `pois_geographic` con índice espacial (R*-tree)
- Cron: full-sync trimestral + sync incremental mensual donde aplique
- Coste cómputo: bajo en queries, medio en agregación cross-source

## Cross-validation con otras familias

| Otra familia | Overlap | Discovery único de B |
|---|---|---|
| A (registros) | ~60% | B captura POIs sin registro formal localizado (entidades nuevas, irregularidades) |
| C (web) | ~70% indirecto | B aporta el seed para discovery web vía dominio resuelto desde POI |
| F (aggregators) | ~50% | B captura dealers sin perfil en marketplace |
| H (OEM) | ~90% para oficiales | B aporta georreferenciación que H no siempre tiene |

## Riesgos y mitigaciones

- **R-B1:** OSM contiene errores de tagging. Mitigación: filtrado de outliers + validación cruzada.
- **R-B2:** Yellow Pages con anti-bot agresivo. Mitigación: rate limits muy conservadores, cache permanente, fallback a fuentes alternativas (no se evade).
- **R-B3:** POIs duplicados entre OSM/Wikidata/Yellow Pages para el mismo dealer. Mitigación: deduplicación por (nombre, dirección normalizada, teléfono).
- **R-B4:** POIs con tagging genérico que captan no-dealers (talleres puros, alquileres puros). Mitigación: clasificador dealer-vs-otro entrenado sobre dataset etiquetado de B+A confirmados.

## Iteración futura

- Integración de Mapillary / Street-Level imagery para validación visual de fachadas dealer
- Captura de cambios temporales (cierre/apertura de POIs vía OSM diff feeds)
- Datasets de geolocalización de transacciones de matriculación (cuando estén accesibles)
