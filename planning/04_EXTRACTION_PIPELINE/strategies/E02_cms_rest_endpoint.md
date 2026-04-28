# E02 — REST endpoint CMS/plugin identificado

## Identificador
- ID: E02, Nombre: REST endpoint CMS/plugin identificado, Categoría: CMS-API
- Prioridad: 1100
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Los plugins de gestión de inventario vehicular para WordPress, Joomla y otros CMS exponen APIs REST públicas diseñadas para integración con aggregators y apps móviles propias del dealer. Estas APIs retornan catálogos completos en JSON con todos los campos estructurados — es la fuente de datos de mayor fidelidad tras JSON-LD. Su existencia es detectable vía Familia D (CMS fingerprinting), y su consumo es legítimo dado que son APIs públicas sin autenticación.

La estrategia E02 es complementaria a E01: mientras E01 consume lo que el dealer quiso publicar en Schema.org, E02 accede a la API nativa del plugin que el dealer instaló para gestionar su inventario.

## Target de dealers
- WordPress con WP Car Manager, Car Dealer Plugin, Vehicle Manager, Auto Parts, DealerPress, AutoDealer, Motors, Classified Engine, WooCommerce + Vehicle extension
- Joomla con JomListing, J2Store Vehicles, VehiclesForSale
- Estimado: 25-35% del universo dealer EU (fuerte penetración WP en dealers independientes)

## Sub-técnicas

### E02.1 — Matriz de endpoints conocidos por plugin

```
Plugin                     | Endpoint REST conocido
─────────────────────────────────────────────────────────────────────────────
WP Car Manager            | /wp-json/wp-car-manager/v1/vehicles
                           | /wp-json/wp-car-manager/v1/vehicles?per_page=100
Car Dealer Plugin (WP)    | /wp-json/car-dealer/v1/cars
                           | /wp-json/car-dealer/v1/cars?status=publish
Vehicle Manager (WP)      | /wp-json/vehicle-manager/v1/listings
DealerPress               | /wp-json/dealerpress/v1/inventory
                           | /wp-json/dealerpress/v1/inventory?format=json
Auto Parts (WP)           | /wp-json/auto-parts/v1/vehicles
Motors Theme (WP)         | /wp-json/wp/v2/listing?listing_type=car&per_page=100
Classified Engine (WP)    | /wp-json/classified-engine/v1/listings?category=vehicles
Inventory Manager (WP)    | /wp-json/im/v1/vehicles
AutoDealer Pro (WP)       | /wp-json/auto-dealer/v1/cars
JomListing (Joomla)       | /index.php?option=com_jomlisting&view=listing&format=json
VehiclesForSale (Joomla)  | /index.php?option=com_vehiclesforsale&task=getlist&format=json
AutoScout24 Embedded      | /api/v1/vehicles (custom por integracion)
```

### E02.2 — WP REST API standard con CPT (Custom Post Type)
Muchos sites WP configuran vehículos como Custom Post Type con slug `car`, `vehicle`, `listing`, `auto`:

```
/wp-json/wp/v2/car?per_page=100
/wp-json/wp/v2/vehicle?per_page=100
/wp-json/wp/v2/listing?per_page=100&listing_type=car
/wp-json/wp/v2/auto?per_page=100
```

Discovery de CPTs vía `/wp-json/` (discovery endpoint de la WP REST API que lista todos los namespaces y routes disponibles).

### E02.3 — WP REST API discovery automático
`GET /wp-json/` retorna el índice completo de namespaces y routes registrados. E02 hace fetch de este índice y busca namespaces que contengan `vehicle`, `car`, `dealer`, `inventory`, `listing`, `auto`. Este discovery es automático y no requiere conocer el plugin de antemano.

### E02.4 — Paginación WP REST API
`per_page` máximo en WP REST API: 100 items por request. Paginación via header `X-WP-TotalPages`. E02 itera todas las páginas hasta consumir el catálogo completo.

Headers relevantes a consumir:
```
X-WP-Total: 347          → total de vehículos
X-WP-TotalPages: 4       → número de páginas
Link: <...?page=2>; rel="next"
```

### E02.5 — Custom meta fields
Los plugins exponden custom meta en `meta`, `acf` (Advanced Custom Fields), o campos top-level. E02 mapea los campos conocidos por plugin a `VehicleRaw`. Los campos desconocidos van a `AdditionalFields` para normalización posterior.

## Formato de datos esperado
JSON REST API response. Ejemplo WP Car Manager:

```json
{
  "id": 1234,
  "title": { "rendered": "BMW 320d 2021 — 45.000 km" },
  "meta": {
    "vehicle_make": "BMW",
    "vehicle_model": "3 Series",
    "vehicle_year": 2021,
    "vehicle_mileage": 45000,
    "vehicle_price": 28500,
    "vehicle_price_currency": "EUR",
    "vehicle_fuel_type": "diesel",
    "vehicle_transmission": "automatic",
    "vehicle_vin": "WBA...",
    "vehicle_images": ["https://...jpg", "https://...jpg"]
  },
  "link": "https://dealer.de/cars/bmw-320d-2021"
}
```

## Campos extraíbles típicamente
Todos los críticos: Make, Model, Year, Mileage, FuelType, Transmission, PowerKW (si el plugin lo expone), BodyType, Color, Price, VIN (si publicado), SourceURL, ImageURLs completas, Equipment (en plugins maduros).

## Base legal
- APIs REST públicas sin autenticación: ninguna barrera técnica ni legal al acceso
- Las WP REST APIs no requieren autenticación por defecto para endpoints públicos
- El plugin fue instalado intencionalmente por el dealer para integración con terceros
- Base: `schema_org_syndication` / `public_api_consumption`
- robots.txt: los paths de API (`/wp-json/`) típicamente no están en `Disallow`. Si lo están, E02 no accede.

## Métricas de éxito
- `e02_applicable_rate(país)` — % dealers con plugin REST identificado via Familia D
- `e02_discovery_rate` — % de endpoints encontrados vía discovery automático `/wp-json/`
- `e02_full_success_rate` — % extracciones completas
- `e02_mean_vehicles_per_dealer` — densidad catálogo

## Implementación
- Módulo Go: `services/pipeline/extraction/strategies/e02_cms_rest/`
- Dependencias: `encoding/json` stdlib, `net/http` stdlib
- Sub-módulo: `plugin_registry.go` — mapa de plugin fingerprint → endpoint(s) conocido(s)
- Sub-módulo: `wp_discovery.go` — fetch de `/wp-json/` + análisis de namespaces
- Sub-módulo: `paginator.go` — iteración por `X-WP-TotalPages` header
- Coste cómputo: bajo — JSON parsing, sin rendering
- Cron: re-extracción cada 24h (API siempre actualizada)

## Fallback strategy
Si E02 falla (404, 403, empty response):
1. Intentar E01 (JSON-LD) si aún no intentado
2. Intentar E03 (Sitemap) para obtener URLs individuales de vehículo
3. Si WordPress confirmado pero API deshabilitada (WP puede deshabilitar REST API) → escalar a E07 (Playwright XHR discovery)

## Riesgos y mitigaciones
- R-E02-1: WordPress con REST API deshabilitada por plugin de seguridad (Wordfence, iThemes Security). Mitigación: detección via HTTP 403 con header `X-WP-Nonce` ausente → escalar a E07.
- R-E02-2: Plugin actualizado y cambio de namespace. Mitigación: discovery automático via `/wp-json/` más robusto que hardcoded paths.
- R-E02-3: CPT privado (vehículos publicados como `private` en WP). Mitigación: sin autenticación no se puede acceder, aceptar como gap.
- R-E02-4: JSON malformado por plugins de bajo nivel de calidad. Mitigación: parser lenient + log.

## Iteración futura
- Registry ampliable sin cambio de código (YAML config de plugin→endpoint)
- Soporte para GraphQL endpoints (algunos plugins modernos WP exponen GraphQL via WPGraphQL)
- Auto-learning: cuando E07 descubre un endpoint JSON desconocido en un WP site, registrarlo en el registry para futuras instancias del mismo plugin
