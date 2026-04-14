# Familia H — Redes oficiales OEM

## Identificador
- ID: H, Nombre: Redes oficiales OEM, Categoría: OEM-network
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Cada fabricante publica su red oficial de concesionarios vía dealer locator propio, diseñado para consumidores. Estos directorios son exhaustivos para los dealers con contrato oficial, georreferenciados, actualizados y siempre con website oficial del dealer. Aportan ~10.000 dealers oficiales cross-marca en los 6 países.

## OEMs objetivo (30+ marcas)

### H.1 — Grupos mass-market
| OEM | Dealer locator URL | Cobertura 6 países |
|---|---|---|
| Volkswagen Group | https://www.volkswagen.{de\|fr\|es\|be\|nl\|ch}/dealer-search | VW + Audi + Skoda + Seat + Cupra + Bentley + Porsche + Lamborghini via sub-sites |
| Stellantis | https://www.stellantis.com/dealers | Peugeot, Citroën, DS, Opel, Fiat, Alfa Romeo, Lancia, Jeep, Chrysler |
| Renault Group | https://www.renault.{fr\|es\|de...}/concessionnaires | Renault + Dacia + Alpine |
| BMW Group | https://www.bmw.{de\|fr\|es...}/de/fastlane/dealer-locator.html | BMW + MINI + Rolls-Royce |
| Mercedes-Benz Group | https://www.mercedes-benz.{de\|fr...}/passengercars/being-an-owner/dealer-locator.html | MB + Smart |
| Toyota | https://www.toyota.{de\|fr...}/dealer-search | Toyota + Lexus |
| Hyundai Motor Group | https://www.hyundai.{de\|fr...}/haendler-suche | Hyundai + Kia + Genesis |
| Ford | https://www.ford.{de\|fr...}/dealer-search | — |
| Nissan | https://www.nissan.{de\|fr...}/dealers | — |
| Volvo Cars | https://www.volvocars.com/{de\|fr...}/retailers | Volvo + Polestar |
| Honda | https://www.honda.{de\|fr...}/cars/dealer-search | — |

### H.2 — Premium y specialty
- Porsche, Jaguar Land Rover (JLR), Aston Martin, Bentley, Rolls-Royce, Maserati, Ferrari (limited dealer network), McLaren, Lotus, Bugatti, Pagani

### H.3 — Electric-only / newer entrants
- Tesla (company-owned stores — no dealers en sentido clásico, pero sí service centers)
- Polestar, Lucid, Rivian (emerging EU), NIO, BYD, XPeng (2024+ EU expansion)
- Fisker, VinFast

### H.4 — Commercial vehicles
- MAN Truck & Bus, Scania, Iveco, DAF Trucks, Mercedes-Benz Trucks, Volvo Trucks, Renault Trucks

### H.5 — Motorcycles (inclusión si vende también coches)
- BMW Motorrad (subset of BMW), Harley-Davidson, Ducati, etc.

## Sub-técnicas

### H.M1 — Dealer locator scraping
Cada OEM expone dealer search con geo-query (código postal + radius) o paginación por país/región. Estrategia:
- API REST subyacente cuando exista (reverse engineering pasivo del frontend)
- HTML paginado como fallback
- Rate limit por OEM
- UA CardexBot transparente

### H.M2 — Geo-exhaustive crawl
Para asegurar cobertura total, sweeping por todas las postcodes del país con radius overlap. Deduplica por Dealer-ID.

### H.M3 — Multi-brand dealerships
Un dealer físico puede representar 3+ marcas (ej. VW Group dealer: VW + Audi + Skoda). Familia H debe reconocer la entidad legal única detrás de las múltiples entries por marca.

## Base legal
Dealer locators publicados por OEMs como servicio al consumidor, diseñados para indexación. Consentimiento implícito.

## Métricas
- `official_dealers_per_oem(país)` — red oficial por marca
- `multi_brand_dealer_count(país)` — dealers representando >1 marca
- `coverage_quality_per_oem` — completitud campos (website, teléfono, servicios)
- `cross_validation_with_A` — ~100% (oficiales están siempre registrados)

## Implementación
- Módulo Go: `discovery/family_h/`
- Parser por OEM (estructura UI distinta cada uno)
- Persistencia: tabla `oem_dealers` con relación N:M entidad↔marca
- Cron: sync trimestral
- Coste: medio (muchos OEMs × muchas postcodes)

## Cross-validation

> Hipótesis de diseño — porcentajes de overlap a validar empíricamente. "~100% con A" es hipótesis fuerte (se asume que dealers OEM oficiales siempre están registrados), pero puede haber casos de registro con retraso o datos desactualizados.

| Familia | Overlap hipotético | Único de H |
|---|---|---|
| A | ~90-100% (hipótesis) | H aporta marca representada, categoría oficial |
| B | ~90% | H aporta dealer-ID canónico OEM + servicios específicos |
| G | ~50% | H captura oficiales no asociados a trade body nacional |
| F | ~70% | H captura oficiales no listados en aggregators independientes |

## Riesgos y mitigaciones
- R-H1: OEM cambia estructura de dealer locator. Mitigación: tests + fallback a sitemap.
- R-H2: rate limits estrictos algunos OEMs. Mitigación: distribuir queries en tiempo.
- R-H3: dealer con contrato finalizado pero aún en locator obsoleto. Mitigación: cross-check A para estado activo.

## Iteración futura
- Specialty brands emergentes (marcas chinas entrando EU)
- Used-vehicle programs oficiales de OEMs (Das WeltAuto VW, Mercedes Young Stars, Porsche Approved, BMW Premium Selection)
- Integración de OEM fleet remarketing networks cuando sean públicos
