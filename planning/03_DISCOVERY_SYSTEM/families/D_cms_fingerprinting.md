# Familia D — CMS + plugin fingerprinting

## Identificador
- ID: D
- Nombre: CMS + plugin fingerprinting
- Categoría: Tech-stack
- Fecha: 2026-04-14
- Estado: DOCUMENTADO

## Propósito y rationale
La gran mayoría de dealers long-tail (target estratégico de CARDEX según R4) usan un conjunto finito de CMS y plugins comerciales. Identificar el stack tecnológico de cada dominio (output de Familia C) permite mapear endpoints REST predecibles que entregan catálogo estructurado JSON nativo, sin scraping HTML.

Esta familia es la palanca de extracción más eficiente para el long-tail: un parser específico por plugin cubre cientos de dealers que comparten el mismo software.

## Sub-técnicas

### D.1 — Detección de CMS

#### D.1.1 — Heurísticas pasivas
- Meta `<meta name="generator">` en HTML
- Headers HTTP (`X-Powered-By`, `Server`, `X-Drupal-Cache`)
- Cookies características (`wordpress_logged_in_*`, `joomla_user_state`)
- Assets enqueued (CSS/JS con paths reveladores: `/wp-content/`, `/sites/default/files/`)

#### D.1.2 — Endpoint probing
- WordPress: `GET /wp-json/` debe responder 200 con WP REST root
- Joomla: `GET /administrator/manifests/files/joomla.xml`
- Drupal: `GET /core/MAINTAINERS.txt` o `?q=user`

### D.2 — Plugins WordPress dealer (lista exhaustiva)

| Plugin | Endpoint REST típico | Notas |
|---|---|---|
| WP Car Manager | `/wp-json/car-manager/v1/cars` | Plugin gratuito popular |
| Car Dealer Pro | `/wp-json/cdp/v1/inventory` | Premium, popular DE/FR |
| Easy Auto Listings | `/wp-json/wp/v2/eal_listing` | Custom Post Type |
| Vehicle Manager | `/wp-json/wp/v2/vehicles` | CPT + REST estándar |
| Smart Manager for WooCommerce | WC REST + atributos vehicle | Sobre WooCommerce |
| AutoListings | `/wp-json/wp/v2/auto-listings` | Plugin gratuito |
| Cars.com Plugin | `/wp-json/cars/v1/listings` | Integración con Cars.com |
| MotorMarket | `/wp-json/mm/v1/inventory` | Premium ES |
| AutoPro | `/wp-json/autopro/v1/cars` | Premium FR |
| CarDealer Pro (Realmag777) | `/wp-json/wp/v2/listings` | Popular ES/IT |
| Stratus | `/wp-json/stratus/v1/inventory` | Premium DE |
| ListingPro Auto | `/wp-json/lp/v1/listings` | Multi-niche con vertical auto |
| WP-CarManager | Endpoint custom | Plugin DE-popular |
| Vehicle Inventory plugin | `/wp-json/vi/v1/vehicles` | |
| Auto Listings | `/wp-json/wp/v2/listing` | |
| AutoManager | `/wp-json/automanager/v1/inventory` | |

Lista expandible iterativamente. Cada plugin nuevo descubierto se añade.

### D.3 — Plugins Joomla dealer

| Plugin | Endpoint típico | Notas |
|---|---|---|
| JoomCar | `index.php?option=com_joomcar&view=cars&format=json` | |
| JM Vehicles | `index.php?option=com_jmvehicles&format=json` | |
| MotorJoom | Custom endpoint | |
| AutoExtension | `index.php?option=com_autoextension&format=feed` | RSS/Atom |
| JCarManager | Custom | |

### D.4 — Drupal modules dealer

- Vehicle Inventory module: `/api/vehicles` + JSON:API
- Auto Dealer suite: endpoints custom

### D.5 — Plataformas no-CMS (templates fijos)

#### D.5.1 — Wix Auto Dealer
- Signature HTML: classes `wix-auto-listing`, scripts `wix-auto-dealer.js`
- Endpoint: Wix expone JSON via `/_api/wix-store-products-collection-data`
- Estrategia: parser específico para Wix dealers

#### D.5.2 — Squarespace Auto template
- Signature CSS: classes específicas del template
- Endpoint: `/api/inventory.json` en sitios con template Auto

#### D.5.3 — Shopify Auto themes
- Signature: `/cdn/shop/products/` patterns
- Endpoint: Shopify Storefront API (público con token)

#### D.5.4 — PrestaShop con auto modules
- Endpoint: `/api/products?ws_key=...` (solo si dealer expuso la WS)

#### D.5.5 — OpenCart con auto extensions
- Endpoint variable según extension

#### D.5.6 — Webflow Auto templates
- Signature CSS específica
- Sin endpoint REST estándar; scrape HTML estructurado

#### D.5.7 — Webnode, Jimdo
- Sites builders simples; scrape HTML respetando ToS

#### D.5.8 — IONOS, OVH website builders
- Templates pre-construidos detectables

### D.6 — Plataformas dealer-específicas por país

#### D.6.1 — Alemania
- Dealersuite (https://www.dealersuite.de) — feed XML
- AutoTRACK Online — endpoint propietario
- Mobility Center — JSON
- Motorbase — RSS + JSON

#### D.6.2 — Francia
- ConcessionnaireWeb — feed XML
- AutoLiveWeb — JSON
- NovaConcept — RSS
- Garage du Net — endpoint específico
- Idiamotors — feed propietario

#### D.6.3 — España
- DealerWeb España — JSON feed
- MyConcesionarioWeb — RSS
- Solera Spain — endpoint propietario

#### D.6.4 — Países Bajos
- AutoDealerWeb — JSON
- AutoSiteOnline — feed
- AutoTrack white-label — endpoint compartido

#### D.6.5 — Bélgica
- AutoConcessieWeb — JSON
- AutoDealerSite — RSS
- FastTrack — feed propietario

#### D.6.6 — Suiza
- AutoHändlerWeb — JSON
- GarageWebCH — RSS
- AutoScout24 dealer subsites — endpoint inferido del parent

## Base legal
- Endpoints REST públicos sin auth: explícitamente expuestos por el dealer/plugin para consumo público (Schema.org-equivalent — sindicación intencional)
- Respeto estricto a `robots.txt` por dominio
- Rate limits conservadores
- UA transparente CardexBot

## Métricas

- `cms_distribution(país)` — % dominios por CMS detectado
- `extraction_success_rate(plugin)` — % dealers cubiertos por cada plugin
- `unique_dealers_via_plugin(plugin)` — dealers únicos extraídos por plugin
- `plugin_endpoint_uptime(plugin)` — disponibilidad temporal del endpoint

## Implementación

- Módulo Go: `discovery/family_d/`
- Sub-módulos: `cms_detector/`, `wp_plugins/`, `joomla_plugins/`, `drupal_modules/`, `wix/`, `squarespace/`, `shopify/`, `country_specific/`
- Persistencia: SQLite tabla `dealer_tech_stack` + tabla `extraction_endpoints`
- Cron: detection inicial al añadir dealer + re-check trimestral (CMS puede cambiar)
- Coste cómputo: bajo (probing pasivo + 1-2 requests por dealer)

## Cross-validation con otras familias

> Hipótesis de diseño — porcentajes de overlap a validar empíricamente. Nota: C→D es 100% por diseño (D consume output de C), no una hipótesis empírica.

| Otra familia | Overlap hipotético | Discovery único de D |
|---|---|---|
| C | 100% (D consume URLs de C) | D no descubre dealers nuevos sino características técnicas de los descubiertos |
| E | ~30% | D detecta CMS propio; E detecta hosting en DMS provider |

D no es family de "discovery de dealers" sino de "discovery de capacidad de extracción". Crítica para Fase 04 (Extraction Pipeline).

## Riesgos y mitigaciones

- **R-D1:** Plugins evolucionan sus endpoints. Mitigación: regression tests por plugin, version detection.
- **R-D2:** Plugin con endpoint protegido por auth. Mitigación: documentar como "no extraíble vía D", fallback a Familia E o E11 (Edge dealer).
- **R-D3:** Misidentificación de CMS (false positives). Mitigación: validación cruzada de heurísticas (mínimo 2 confirmaciones).
- **R-D4:** Plugins de pago con DRM/protecciones. Mitigación: respeto absoluto, no se intenta bypass.

## Iteración futura

- Mapeo de plugins emergentes mediante monitoreo de WordPress.org plugin directory + filtrado por categoría auto
- Detección de plugins custom (no comerciales) por análisis de endpoints REST únicos
- Onboarding directo de dealer custom via outreach Edge
