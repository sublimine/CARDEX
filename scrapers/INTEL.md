<!-- Verified extraction intel harvested from the existing codebase (Go pipeline,
common/, discovery/). Every fact here is literally present in repo code. Use this
as the field-mapping + endpoint bible when authoring portal scrapers. -->
# CARDEX scraping — verified extraction intel

## 1. AutoScout24 — the one fully-built portal blueprint
`scrapers/common/autoscout24.py` [VERIFIED]
- Per-country host + path prefix: DE `autoscout24.de` `/angebote/`, FR `.fr` `/annonces/`,
  ES `.es` `/anuncios/`, NL `.nl` `/aanbod/`, BE `.be` `/annonces/`|`/aanbod/`,
  CH `.ch` `/annonces/`|`/angebote/`.
- Search URL (verbatim): `{base}?atype=C&desc=0&sort=standard&year_from={yf}&year_to={yt}&page={p}`
  + optional `&price_to={price_to}` + `&fuel={fuel}`.
- Listings live in Next.js embedded JSON, NOT `<a href>`. Regex `config["listing_json_re"]`
  matches `"url":"/angebote/{slug}-{uuid}"` (re.IGNORECASE).
- Pagination/cap: `_PAGE_SIZE=20`, `_MAX_PAGE=20` → 400/segment ceiling. Beat cap with
  `_YEAR_BANDS` (11 bands 1990→2026), `_PRICE_CEILINGS=[5000,10000,15000,20000,30000,50000,100000,None]`,
  `_FUELS=["P","D","E","H"]`. Subdivide by fuel when `len(urls) >= _MAX_PAGE*_PAGE_SIZE`.
- Anti-bot: `AsyncSession(impersonate="chrome", http_version=3)` (curl_cffi, JA3 fixed per session).
  `_SLEEP_BASE=1.2`, `_SLEEP_JITTER=0.4`; `_RETRY_ATTEMPTS=3`, `_RETRY_BACKOFF_BASE=2.0`;
  `_BLOCK_STATUSES={403,429,503}`. CF markers: "cf-browser-verification", "Just a moment",
  "checking your browser", "__cf_chl_", "jschl-answer", "Attention Required! | Cloudflare".
- [GAP] Per-country `config` dicts (`search_base`,`base_url`,`listing_json_re`,`source`,`country`,`domain`)
  consumed by `run(config)` are NOT in repo. `portals/{de,fr,es,nl,be,ch}/__init__.py` are EMPTY.

AS24 verified reachability (`portal_aggregator.py`, "Verified 2026-04-10"): only AS24 **DE** dealer
dir `/haendler/`→200. AS24 ES/FR/NL/BE→404, CH→403 (Cloudflare). mobile.de/LeBonCoin/Coches.net→403.

## 2. Generic dealer extraction — Go `extraction/` cascade (field-mapping bible)
Canonical schema `extraction/internal/pipeline/types.go` `VehicleRaw` (all pointers):
VIN, Make, Model `*string`; Year, Mileage(km) `*int`; FuelType `gasoline|diesel|hybrid|electric|lpg|cng|hydrogen`;
Transmission `manual|automatic|semi-automatic`; PowerKW `*int`;
BodyType `sedan|hatchback|suv|estate|coupe|convertible|van|pickup`; Color/Doors/Seats;
PriceNet/PriceGross `*float64`; Currency ISO4217; VATMode `net|gross|unknown`;
SourceURL; SourceListingID; ImageURLs `[]string`. CriticalFields={Make,Model,Year,PriceNet|PriceGross,SourceURL,ImageURLs};
FullSuccess ≥0.8. Dealer.CountryCode ISO `DE|FR|ES|BE|NL|CH`; PlatformType `CMS_WORDPRESS|CMS_SHOPIFY|DMS_HOSTED|NATIVE|UNKNOWN`.

- E01 JSON-LD: selector `script[type="application/ld+json"]`; types {Vehicle,Car,MotorVehicle,BusOrCoach,Motorcycle};
  containers {ItemList,OfferCatalog,AutoDealer}. VIN←`vehicleIdentificationNumber|sku`; Make←`brand.name|manufacturer`;
  Model←`vehicleModel|model|name`; Year←`vehicleModelDate`; Mileage←`mileageFromOdometer` (miles→km ×1.60934);
  FuelType←`fuelType`; Transmission←`vehicleTransmission`; PowerKW←`vehicleEngine.enginePower.value`;
  BodyType←`bodyType`; Price←`offers.price`; Currency←`offers.priceCurrency`; images←`image/contentUrl/url`.
  EU price parse `"28.500,00 €"→28500.00`. UA `CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)`.
- E02 CMS REST: `/wp-json/wp-car-manager/v1/vehicles`, `/wp-json/car-dealer/v1/cars`,
  `/wp-json/vehicle-manager/v1/listings`, `/wp-json/dealerpress/v1/inventory`,
  `/wp-json/wp/v2/listing?listing_type=car&per_page=100`. perPage 100, maxPages 50; pagination via
  `X-WP-TotalPages` header + `Link rel="next"`. Fields `vehicle_make/model/year/mileage/price/fuel_type/transmission/vin`.
- E03 sitemap: `/sitemap.xml`,`/sitemap-vehicles.xml`,`/sitemap-cars.xml`,`/sitemap-inventory.xml`,…
  vehiclePathPatterns `/vehicle(s)/`,`/auto(s)/`,`/voiture(s)/`,`/coche(s)/`,`/fahrzeug(e)/`,`/gebrauchtwagen/`,`/annonce(s)/`,`/occasion(s)/`.
  OG fallback `og:title`,`product:price:amount`,`og:image`. reYear `\b(19[89]\d|20[012]\d)\b`.
  `normalize/vehicle.go`: multilingual EN/DE/FR/ES/IT maps + NormalizeVIN(17) + NormalizeCurrency.

## 3. Persistence contract
- `indexer.py` PG: `vehicle_index(url_hash PK=sha256[:32], url_original, source_domain, country,
  sitemap_source, titulo_modelo, precio NUMERIC(12,2), moneda CHAR(3) DEFAULT 'EUR', kilometraje INT,
  anio SMALLINT, thumbnail_url, last_seen, created_at)` + `vehicle_events` (SEEN/GONE). Redis
  `stream:enrich_pending` maxlen 5_000_000. `run_portal(*, source, country, domain, fetch_all_urls)` is the entrypoint.
- `pw_base.py` [VERIFIED]: Camoufox (Firefox JA3, `geoip=True` w/ proxy) primary; Playwright Chromium
  fallback UA `Chrome/136.0.0.0`. Coroutines `intercept_paginate` (XHR sniff `api_pattern`) and
  `dom_paginate`; `max_pages=100`, `page_wait_ms=3000`. `playwright-stealth` removed (CI-blocked 2026-05-16).

## 4. Anti-bot reality (verified 2026-04-10)
mobile.de / LeBonCoin / Coches.net / AS24-CH hard-block (403/CF). Only AS24-DE listings and
open-gov registries are friction-free. `sitemap_indexer` is a sealed/missing module (unresolved import).
