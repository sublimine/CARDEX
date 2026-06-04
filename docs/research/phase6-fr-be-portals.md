# Phase 6 — FR/BE Portal Expansion Research

Date: 2026-06-04

## Implemented Portals

### 2ememain.be (BE) — T0
- **Type**: Francophone mirror of 2dehands.be (same Adevinta/Marktplaats backend)
- **API**: `GET /lrp/api/search?l1CategoryId=91&offset=N&limit=30&attributeRanges[]=constructionYear:Y:Y&attributeRanges[]=PriceCents:P:P`
- **WAF**: None (CloudFront CDN, no bot detection)
- **Inventory**: ~102,498 vehicles
- **Detail URL**: `/v/autos/{brand}/m{ITEM_ID}-{slug}`
- **Notes**: Same database as 2dehands.be. In production, run one OR the other.

### cardoen.be (BE) — T1
- **Type**: Aramis Group Belgian subsidiary, dealer supermarket
- **Tech**: Nuxt.js SSR, Cloudflare CDN for images
- **WAF**: Cloudflare Free (CDN only, no JS challenge on SSR)
- **Inventory**: ~850 used vehicles
- **Search**: `GET /fr/achat/occasions/?page=N` (24/page, 36 pages)
- **Detail URL**: `/fr/auto/{brand}/{model}/{slug}/?vehicleId={ID}`

### aramisauto.com (FR) — T1
- **Type**: Aramis Group parent (European leader online used cars)
- **Tech**: Next.js SSR, Cloudflare CDN, Sentry monitoring
- **WAF**: Cloudflare Free (CDN only)
- **Inventory**: ~3,000 reconditioned vehicles
- **Search**: `GET /achat/occasion?page=N` (24/page)
- **Detail URL**: `/achat/{brand}/{model}/{slug}/`

### leparking.fr (FR) — T1
- **Type**: Pan-European meta-aggregator (926 source sites)
- **Tech**: SSR HTML + jQuery, Sibdata consent
- **WAF**: None
- **Inventory**: ~14.8M listings aggregated
- **Search**: `GET /voiture-occasion/{brand}.html?p=N`
- **Detail URL**: `/voiture-occasion/{slug}.html` (linkAd class)

### autosphere.fr (FR) — T0
- **Type**: Emil Frey / ex-Groupe PSA dealer network (250+ dealerships)
- **Tech**: Next.js App Router, AWS S3 for images
- **API**: `GET /api/stock/vehicles?voiture=occasion&sortField=popularity&sortDirection=asc&internal_type=vo,vd&size=100&from=N`
- **WAF**: None
- **Inventory**: ~15,600 VO
- **Detail URL**: `/recherche/{slug}`

### reezocar.com (FR) — T1
- **Type**: European aggregator (search-to-delivery platform)
- **Tech**: SSR frontend
- **WAF**: Minimal
- **Search**: `GET /fr/voiture-occasion.html?page=N&price_min=P&price_max=P&year_min=Y&year_max=Y`
- **Detail URL**: `/fr/occasion/{slug}.html`

### spoticar.fr (FR) — T1
- **Type**: Stellantis official used vehicle brand
- **Tech**: SSR frontend, Cloudflare CDN for images
- **WAF**: Cloudflare Free (CDN only)
- **Inventory**: ~80,000 vehicles across 1,200+ sales points
- **Search**: `GET /voitures-occasion?page=N&prix-min=P&prix-max=P&annee-min=Y&annee-max=Y`
- **Detail URL**: `/voitures-occasion/{brand}/{model}/{slug}`

## Investigated but NOT Implemented

### ouestfrance-auto.fr — T2 (CF_PRO)
Already in domain_map. Requires Camoufox browser. Deferred to Phase 7.

### caradisiac.fr — Media site
Automotive journalism site with links to other platforms. Not a primary classifieds portal.

### vivastreet.com — General classifieds
General classifieds with vehicle section. Low vehicle density, heavy ads. Skip.

### promoneuve.fr — New cars only
Stellantis/Caradisiac site for NEW vehicles in stock. Not used cars. Skip.

### elite-auto.fr, starterre.fr, distinxion.com — Dealer networks
Small dealer networks with limited online inventory. Low ROI. Skip.

### carizy.com — P2P with inspection
Small P2P marketplace with professional inspection. Tiny inventory. Skip.

### kapaza.be — DEAD
Merged into 2ememain.be in May 2017. Domain redirects.

### automobile.be, autotrack.be — Need further investigation
May be aliases or small portals. Deferred.

### vroom.be — Need further investigation
Belgian car portal. Modern interface. Needs live probing for WAF assessment.
