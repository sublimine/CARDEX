# E05 — DMS hosted-site API

## Identificador
- ID: E05, Nombre: DMS hosted-site API, Categoría: DMS-API
- Prioridad: 1050 (alta — cuando aplicable, es la fuente más estructurada disponible)
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Las plataformas DMS (Dealer Management System) que incluyen website hosting exponen APIs JSON predecibles y documentadas porque su modelo de negocio requiere integración con aggregators (mobile.de, AutoScout24, etc.). El site del dealer es a menudo solo el frontend de una API que el DMS ya provee públicamente para sus integraciones B2B. Identificar el DMS provider (cross-Familia E del discovery system) permite acceder directamente a esa API sin reverse engineering.

E05 tiene prioridad 1050 (entre E01 y E02) porque cuando aplica, la calidad del dato es comparable a E02 (API nativa) pero el endpoint es más estable (mantenido por el proveedor DMS, no por un plugin aleatorio).

## Target de dealers
- Dealers cuyo site está hosted en DealerSocket, CDK Global, Autobiz (FR), Kerridge Commercial Systems, Autoline, Dealer.com (Cox Automotive), Motortrak, Afcar, incadea, Reynolds & Reynolds
- Detectable via Familia E (DMS hosted domain patterns: `*.dealersocket.net`, `*.cdkglobal.com`, `*.autobiz.com`, etc.)
- Estimado: 15-25% del universo dealer EU usa un DMS con web hosting integrado

## Sub-técnicas

### E05.1 — Matriz de endpoints por proveedor DMS

```
DMS Provider         | Domain pattern          | API endpoint conocido
─────────────────────────────────────────────────────────────────────────────────
DealerSocket         | *.dealersocket.net      | /api/v1/inventory
                     |                         | /api/v2/vehicles?pageSize=100
CDK Global           | *.cdkglobal.com         | /api/inventory/vehicles
                     | *.cdk.com               | /api/v1/used-vehicles
Autobiz (FR)         | *.autobiz.com           | /api/annonces?format=json
                     |                         | /export/vehicules.json
Kerridge (KDS)       | *.kerridge.com          | /api/stock/vehicles
                     | *.autoline.net          | /api/v1/stock
Dealer.com (Cox)     | *.dealer.com            | /api/inventory
                     |                         | /inventory.json
Motortrak            | *.motortrak.com         | /api/vehicles/list
Incadea              | *.incadea.com           | /api/vehicles
Afcar                | *.afcar.fr              | /api/stock/json
EurotaxGlass's       | *.eurotax.com           | /api/inventory (via integration)
AutoHaus Digital     | *.autohaus.digital      | /api/fahrzeuge
SilverStream         | *.silverstream.com      | /inventory/json
netDirector          | *.netdirector.co.uk     | /api/vehicles (NL/BE also present)
iVendi               | *.ivendi.com            | /api/stock
Carbase              | *.carbase.co.uk         | /api/vehicles
```

### E05.2 — Paginación DMS APIs

La mayoría de DMS APIs soportan paginación via:
- Query params: `?page=1&pageSize=100`, `?offset=0&limit=50`, `?start=0&count=100`
- Link headers: `Link: <url?page=2>; rel="next"`
- Response body: `{ "total": 347, "page": 1, "pages": 4, "vehicles": [...] }`

E05 itera hasta agotar páginas (detecta fin por `vehicles: []` o `total <= offset`).

### E05.3 — Feed formats alternativos por DMS

Algunos DMS también exponen feeds XML o CSV además de JSON:
- Autobiz: `/export/vehicules.csv`
- CDK: `/api/inventory/feed.xml`
- Kerridge: SOAP endpoint (legacy) + REST moderno

E05 prefiere JSON sobre XML/CSV cuando ambos disponibles.

### E05.4 — DMS API authentication patterns

La mayoría de las APIs DMS para inventory son públicas (no requieren auth) porque están diseñadas para que los aggregators puedan sincronizar. Sin embargo algunos DMS tienen:
- API key en query param: `?apikey=XXXXX` (obtenida del source HTML del frontend)
- Token en header insertado por el frontend: detectable via E07 (Playwright XHR inspection)
- Subdomain-scoped access: el dealer tiene su propio subdomain y el API solo retorna su stock

E05 opera sin autenticación. Si la API requiere auth y el token es visible en el HTML frontend, E07 lo detecta y lo pasa a E05 como hint.

### E05.5 — Normalización de campos DMS

Cada DMS usa nombres de campo propietarios. El sub-módulo de normalización mapea:

```
DealerSocket field → VehicleRaw field
  "vehicleYear" → Year
  "vehicleMake" → Make
  "vehicleModel" → Model
  "vehicleOdometer" → Mileage
  "vehicleSalePrice" → PriceGross
  "vehicleVin" → VIN
  "vehicleImages" → ImageURLs
  "vehicleFuelType" → FuelType
  "vehicleTransmission" → Transmission

Autobiz field → VehicleRaw field
  "annee" → Year
  "marque" → Make
  "modele" → Model
  "kilometrage" → Mileage
  "prix_ttc" → PriceGross
  "prix_ht" → PriceNet
  "vin" → VIN
  "photos" → ImageURLs
```

El normalizer es un YAML config file → extensible sin recompilación.

## Formato de datos esperado
JSON REST API response con paginación. Estructura altamente variable según proveedor — cada proveedor tiene su schema propietario. El normalizer mapea todos a `VehicleRaw`.

## Campos extraíbles típicamente
Con DMS API bien integrada: todos los campos críticos + campos secundarios (Equipment, opciones, historial si publicado). DMS systems tienen los datos más completos del inventario del dealer.

## Base legal
- APIs DMS públicas: el DMS provider las publica para integración con aggregators (B2B consent)
- El dealer ha contratado el DMS y sabe que su API es accesible públicamente
- Base: `public_api_consumption` — API diseñada para consumo automatizado
- robots.txt: paths de API típicamente no están en `Disallow`
- Si se requiere auth y no está publicada: E05 no accede; escala a E07

## Métricas de éxito
- `e05_applicable_rate(país)` — % dealers con DMS provider identificado via Familia E
- `e05_api_success_rate(dms_provider)` — % dealers de ese DMS con API funcionando
- `e05_field_completeness(dms_provider)` — completitud de campos por proveedor
- `e05_mean_vehicles_per_dealer(dms_provider)` — densidad catálogo

## Implementación
- Módulo Go: `services/pipeline/extraction/strategies/e05_dms_api/`
- Sub-módulo: `provider_registry.go` — mapa DMS provider → endpoint patterns + paginator config
- Sub-módulo: `field_normalizer.go` — YAML-driven field mapping por provider
- Sub-módulo: `paginator.go` — universal paginator (multi-strategy: link headers, body total, empty page)
- Coste cómputo: bajo — JSON parsing, sin rendering
- Cron: re-extracción cada 24h (DMS siempre actualizado)

## Fallback strategy
Si E05 falla (API no disponible, 403, estructura cambiada):
- Intentar E01 (JSON-LD) sobre el frontend del dealer
- Intentar E07 (Playwright XHR) para re-descubrir el endpoint API actualizado
- Actualizar el provider_registry con el nuevo endpoint encontrado

## Riesgos y mitigaciones
- R-E05-1: DMS provider actualiza API version y cambia endpoints. Mitigación: tests automáticos contra endpoints conocidos + alerta cuando 404. E07 como fallback para re-discovery.
- R-E05-2: dealer en DMS compartido (varios dealers en misma instancia) → API solo retorna stock del dealer específico basado en subdomain. Mitigación: E05 siempre incluye el subdomain del dealer en la request.
- R-E05-3: DMS legacy con SOAP en vez de REST. Mitigación: soporte SOAP opcional en el registry, implementar wrapper SOAP→VehicleRaw.
- R-E05-4: API rate limit por proveedor (no por dealer). Mitigación: global rate limiter por DMS provider domain.

## Iteración futura
- Registro de DMS providers emergentes (nuevas plataformas EU como plataformas nórdicas expandiéndose)
- Soporte de webhooks push cuando DMS provider los ofrece (DealerSocket Push Notifications, CDK Data Services)
- Monitoreo de API versioning: suscripción a changelogs de DMS providers conocidos
