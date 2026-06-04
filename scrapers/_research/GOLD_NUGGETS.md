# GOLD NUGGETS — verified intelligence salvaged from the previous CARDEX system

> Extracted by deep recon of the monorepo (Go pipeline, `common/`, `discovery/`,
> `mobile_re/`, `extraction/`). Only **working, verified** facts are kept — dead
> code and non-functional patterns were deliberately discarded. Each entry is
> tagged `[VERIFIED]` (read from source / confirmed by comment with a date) or
> `[PARTIAL]` / `[UNVERIFIED]` (stub, NotImplementedError, or unconfirmed).
>
> Provenance: paths are relative to the repo root unless noted. Captured 2026-06-03.

---

## 1. AutoScout24 — the core curl_cffi engine (T2, AKAMAI_V3)

Source: `scrapers/common/autoscout24.py` — [VERIFIED as of 2026-05-16]

- **Search URL**: `/lst?atype=C&desc=0&sort=standard&page={N}&year_from={Y}&year_to={Y2}&price_to={P}&fuel={F}`
- **Listing extraction**: listing URLs live in **Next.js embedded JSON**, not in
  `<a href>`. Pattern: `"url":"/angebote/{slug}-{uuid}"`. Parse the JSON script body.
- **Per-country listing path prefixes** (the `/angebote/` segment varies):
  - DE `/angebote/` · FR `/annonces/` · ES `/anuncios/` · NL `/aanbod/`
  - BE `/annonces/` or `/aanbod/` · CH `/annonces/` or `/angebote/`
- **Pagination**: 20 listings/page, max 20 pages → **400 URLs/segment** hard cap.
  When the cap is hit, **subdivide by fuel type** to recover the lost tail.
- **Year bands**: 11 bands (1990-2000, 2000-2005, … 2024-2026).
- **Price ceilings**: 8 thresholds `[5000, 10000, 15000, 20000, 30000, 50000, 100000, None]`.
- **Fuel types**: `P` (petrol/gasoline), `D` (diesel), `E` (electric), `H` (hybrid).
- **Cloudflare softblock markers**: `"cf-browser-verification"`, `"Just a moment"`,
  `"__cf_chl_"`, `"jschl-answer"`.
- **Retry**: 3 attempts, exponential backoff base 2.0s (doubled each attempt).
- **Rate limiting**: jittered sleep base 1.2s ± 40% to break uniform timing.
- **Session**: `AsyncSession(impersonate="chrome", http_version=3)`;
  Windows requires `WindowsSelectorEventLoopPolicy`.

## 2. AutoScout24 — country coverage & dealer directories

Source: `discovery/internal/families/familia_f/autoscout24/autoscout24.go:65-71`
— [VERIFIED via robots.txt checks 2026-04-15]

| Country | Base | Dealer dir | Status |
|---------|------|-----------|--------|
| DE | autoscout24.de | `/haendler/` | ✓ not blocked |
| FR | autoscout24.fr | `/concessionnaires/` | ✓ not blocked |
| NL | autoscout24.nl | `/handelaar/` | ✓ not blocked |
| BE | autoscout24.be | `/handelaar/` | ✓ not blocked |
| CH | autoscout24.ch | `/haendler/` | ✓ not blocked |
| ES | autoscout24.es | — | DEFERRED (robots.txt conn error) |

- Dealer-directory pagination: SPA `?currentPage=N` (starts at 1) until empty page.
- Dealer profile data: `<script id="__NEXT_DATA__">` JSON at
  `props.pageProps.dealerInfoPage.{id,name,address,contact}`.
- AS24 dealer scraper (`scrapers/discovery/sources/as24_curl_cffi.py:37-56`):
  - Profile regex: `href="(?:https?://www\.autoscout24\.[a-z]{2,3})?(/haendler/[a-z0-9][^"/]+)(?:"|/")`
  - External website (JSON-LD): `"url"\s*:\s*"(https?://(?!(?:www\.)?autoscout24)[^"]+)"`
  - Dealer metadata: name (JSON-LD `"name"`), city (`"addressLocality"`), postcode (`"postalCode"`)
  - Concurrency 8 parallel profile fetches; 1s polite delay; `impersonate="chrome124"`.

## 3. Domain → Tier → WAF registry

Source: `scrapers/engine/router/domain_map.py:48-83` — [VERIFIED 2026-05-07].
This is already in the live engine; reproduced here as the authoritative target list.

| Portal | Tier | WAF | Countries | Escalation | Notes |
|--------|------|-----|-----------|------------|-------|
| mobile.de | **T0** | NONE | DE | → T2 | Ad-Stream WSS consumer (mobile API) |
| tweedehands.be | **T0** | NONE | BE | — | Public API (2dehands) |
| kleinanzeigen.de | T1 | CF_PRO | DE | — | curl_cffi sufficient |
| tutti.ch | T1 | CF_FREE | CH | — | — |
| autotrack.nl | T1 | NONE | NL | — | — |
| gaspedaal.nl | T1 | NONE | NL | — | — |
| marktplaats.nl | T1 | CF_PRO | NL | — | — |
| paruvendu.fr | T1 | NONE | FR | — | — |
| largus.fr | T1 | NONE | FR | — | — |
| motor.es | T1 | NONE | ES | — | — |
| autocasion.com | T1 | CF_FREE | ES | — | — |
| coches.net | T1 | CF_PRO | ES | → T2 | — |
| **autoscout24.\*** | **T2** | AKAMAI_V3 | DE,ES,FR,NL,BE,CH | → T3 | Camoufox required |
| wallapop.com | T2 | PERIMETER_X | ES | → T3 | — |
| gocar.be | T2 | CF_BUSINESS | BE | — | — |
| comparis.ch | T2 | CF_BUSINESS | CH | — | — |
| heycar.com | T2 | CF_PRO | DE,FR | — | — |
| autohero.com | T2 | CF_PRO | DE | — | — |
| ouestfrance-auto.fr | T2 | CF_PRO | FR | — | — |
| coches.com | T2 | CF_PRO | ES | — | — |
| **leboncoin.fr** | **T3** | DATADOME | FR | — | Behavioral + residential |
| **lacentrale.fr** | **T3** | DATADOME | FR | — | Behavioral + residential |
| milanuncios.com | T3 | DATADOME | ES | — | — |

**Portals per country (quick index):**
- DE: autoscout24.de, mobile.de, kleinanzeigen.de, heycar.com, autohero.com
- FR: autoscout24.fr, paruvendu.fr, largus.fr, leboncoin.fr(T3), lacentrale.fr(T3), ouestfrance-auto.fr
- ES: autoscout24.es, coches.net, wallapop.com, motor.es, milanuncios.com(T3), coches.com, autocasion.com
- NL: autoscout24.nl, marktplaats.nl, gaspedaal.nl, autotrack.nl
- BE: autoscout24.be, tweedehands.be(API), gocar.be
- CH: autoscout24.ch, tutti.ch, comparis.ch

## 4. Browser base (Camoufox primary / Chromium+stealth fallback)

Source: `scrapers/common/pw_base.py:1-410` — [VERIFIED]

- **Primary**: Camoufox (Firefox-based, native fingerprint randomization).
- **Fallback**: Playwright Chromium + comprehensive stealth JS (lines 37-131):
  webdriver, plugins, hardwareConcurrency, battery API, WebGL, window dims,
  permissions, iframe detection — verified against CreepJS/Sannysoft/DataDome probes.
- **JA3 invariant**: never mix engines within one portal session (Firefox TLS ≠ Chrome TLS).
- Chrome 136 UA (matches curl_cffi impersonate): `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36`
- Paginators: `intercept_paginate()` (XHR pattern + response extraction) and `dom_paginate()`.
- Proxy: `{"server","username","password"}` with geoip awareness for locale/timezone.

## 5. Mobile API reverse engineering

Source: `scrapers/mobile_re/` — [VERIFIED via comments; mapper is a stub]

- `client.py:13-17` portal RE status: mobile.de (Ad-Stream WSS), autoscout24 (same
  API as web + `X-AS24-App` header), leboncoin (mobile API = **full DataDome bypass**),
  lacentrale (idem), wallapop (externally documented API).
- `interceptor.py:1-46`: mitmproxy + frida cert-unpinning infra for Android capture → HAR export. [VERIFIED architecture]
- `mapper.py`: HAR→OpenAPI via mitmproxy2swagger. [UNVERIFIED — stub/NotImplementedError]

## 6. Canonical vehicle schema

Source: `extraction/internal/pipeline/types.go:28-94` — [VERIFIED canonical schema].
Nullable pointers distinguish *absent* from *zero*.

Facts: `VIN`(17-char upper, else dropped), `Make`, `Model`, `Year`(1886-2100),
`Mileage`(km), `FuelType`, `Transmission`, `PowerKW`, `BodyType`, `Color`, `Doors`, `Seats`.
Price: `PriceNet`, `PriceGross` (≥0), `Currency`(ISO 4217 upper), `VATMode`(net|gross|unknown).
Pointers (never copied): `SourceURL`, `SourceListingID`, `ImageURLs[]`.
Extras: `Equipment[]`, `AdditionalFields{}`.

- **Critical fields** for FullSuccess: Make, Model, Year, (PriceNet OR PriceGross),
  SourceURL, ImageURLs(≥1). **FullSuccess = ≥80% of vehicles carry all critical fields.**

## 7. Normalization mappings (canonical enums)

Source: `extraction/internal/normalize/vehicle.go:11-122` — [VERIFIED].
Case-insensitive partial match.

- **FuelType** → `gasoline` {petrol, benzin, essence, gasolina, gas} · `diesel` {gazole, gasoil}
  · `electric` {électrique, eléctrico, elektro, bev} · `hybrid` {hybride, híbrido, phev, plug-in}
  · `lpg` {gpl, autogas} · `cng` {gnv, erdgas} · `hydrogen` {wasserstoff, hydrogène}
- **Transmission** → `manual` {manuell, manuelle, schaltgetriebe, mt}
  · `automatic` {automatique, automático, automatik, dsg, cvt, s tronic}
  · `semi-automatic` {semi-automatique, robotized}
- **BodyType** → `sedan` {berline, limousine, saloon} · `hatchback` {hayon, compacto}
  · `suv` {crossover, 4x4, tout-terrain, geländewagen} · `estate` {break, kombi, variant, touring, sw}
  · `coupe` {coupé, sports} · `convertible` {cabriolet, cabrio, roadster, spider}
  · `van` {minivan, mpv, monospace} · `pickup` {pick-up, truck}

## 8. Persistence & dedup

Source: `extraction/internal/storage/storage.go:74-150` — [VERIFIED]

- **Dedup key**: `VIN + dealer_id` (unique, null-safe).
- **Fingerprint**: SHA256 of vehicle data for change detection.
- **TTL**: 72h auto-expiry for stale listings.
- **Image storage**: pointer model — store only first URL, never duplicate.
- **Price columns**: `price_net_eur`, `price_gross_eur`, `currency_original`, `vat_mode`.
- **Upsert**: `ON CONFLICT(vin, dealer_id) DO UPDATE` on all fields except `source_platform`.

## 9. Extraction strategies & selectors

Source: `extraction/internal/extractor/*` — [VERIFIED where noted]

- **E01 JSON-LD** (`e01_jsonld/jsonld.go:60-89`): `<script type="application/ld+json">`,
  `@type ∈ {Vehicle, Car, MotorVehicle, BusOrCoach, Motorcycle}`; containers
  `{ItemList, OfferCatalog, AutoDealer}`. Inventory paths (by frequency): ``,
  `/inventory`, `/stock`, `/occasions`, `/voitures-occasion`, `/vehicules-occasion`,
  `/gebrauchtwagen`, `/occasion`, `/used-cars`, `/used`, `/pre-owned`,
  `/vehiculos-usados`, `/coches-de-ocasion`, `/occasions.html`, `/inventory.html`, `/auto-usate`.
- **E03 sitemap heuristics** (`e03_sitemap/sitemap.go:549-552`):
  - Year: `\b(19[89]\d|20[012]\d)\b`
  - Mileage: `(?i)\b(\d[\d\s.]*)\s*(km|kms|kilometre|kilometer)\b`
  - Price: `(?i)(\d[\d\s.,]*)[\s]*(€|eur|euro)\b` · num validation `^\d[\d.,\s]*$`
- E02 (CMS REST), E04 (RSS), E06 (microdata), E07 (Playwright XHR) — [PARTIAL].

## 10. Sitemap discovery

Source: `scrapers/discovery/sitemap_resolver.py` — [VERIFIED]

- Fallback paths: `/sitemap.xml`, `/sitemap_index.xml`, `/sitemap-index.xml`, `/sitemap.xml.gz`.
- robots.txt directive regex: `(?im)^\s*sitemap\s*:\s*(\S+)\s*$`.
- XML validation: detect `<urlset` or `<sitemapindex` in first 64 KiB (gzip-aware).

---

### How these nuggets map onto the new build

- **§1 + §2 + §4** → the 6-country AS24 portal scrapers (`portals/`): reuse the URL
  scheme, partition strategy (year×price×fuel), 400-cap subdivision, softblock markers,
  and the Next.js JSON listing extraction verbatim. Per-country path prefixes drive
  `is_result_cap_hit`/listing-URL parsing.
- **§6 + §7 + §8** → the pipeline `normalize`/`quality` stages: canonical enums and
  critical-field rules are the contract; the FullSuccess ≥80% gate is the quality bar.
- **§3** → already live in `router/domain_map.py`; informs scheduler priority + tier dispatch.
- **§9 + §10** → enrichment fallbacks (JSON-LD first) and dealer/sitemap discovery.
- **§5** → T0 mobile-API fast path; leboncoin/lacentrale mobile API is the DataDome bypass
  to pursue before paying the T3 behavioral cost.
