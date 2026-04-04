# CARDEX Discovery Engine — Architecture Document
# Pan-European Vehicle Indexing System
# Target: 100% territory coverage across DE, ES, FR, NL, BE, CH

---

## MISSION

Index every vehicle for sale in 6 European countries. Every dealer, every platform, every private seller listing. Redirect to original source. Never host content.

## MARKET REALITY (Audited, 2024/2025)

| Metric | Number | Source |
|--------|--------|--------|
| Annual used car transactions (6 countries) | 17.4M | KBA, BOVAG, Traxio, ASTRA, Autovista24 |
| Active listings at any moment (gross, all portals) | 5-7M | Portal self-reported data |
| Unique vehicles for sale (deduplicated) | 3.5-4.5M | Derived (dealers multi-list on 3-5 portals) |
| Formal car dealers | 80,000-95,000 | ZDK, CNPA, GANVAM, BOVAG, Traxio, AGVS |
| Micro-dealers / informal traders | +30,000-60,000 | Industry estimates |
| Total selling entities | ~120,000-150,000 | |

AutoUncle covers 2,600 webs = 1.7% of territory. CARDEX targets 100%.

---

## LAYER 0 — OFFICIAL BUSINESS REGISTRIES (Free, Bulk, Immediate)

### France — INSEE SIRENE (GOLD)
- **Status**: 100% open data, Licence Ouverte v2.0
- **Access**: Bulk CSV download at data.gouv.fr (~12 GB) + REST API at api.insee.fr
- **Filter**: NAF code 45.11Z (vente auto), 45.19Z, 45.20A/B
- **Fields**: SIREN, SIRET, company name, address, NAF code, legal form, workforce
- **Update**: Daily delta files available
- **Volume**: ~700,000+ establishments with NAF 45.xx (filter to ~40,000 dealers)

### Belgium — KBO/BCE (GOLD)
- **Status**: 100% open data since 2017
- **Access**: Monthly bulk CSV at economie.fgov.be/open-data
- **Filter**: NACE-BEL 45.110 (wholesale/retail trade of cars)
- **Fields**: Enterprise number (=VAT), company name, address, NACE codes, status
- **Files**: enterprise.csv, establishment.csv, activity.csv, denomination.csv (join required)
- **Volume**: ~30,000+ automotive enterprises

### Switzerland — Zefix (GOOD)
- **Status**: Free, REST API, bulk download
- **Access**: zefix.admin.ch/ZefixREST/ — no auth needed. Bulk at opendata.swiss
- **Filter**: NOGA code 45.11 + text search "Automobile", "Fahrzeug", "Garage"
- **Fields**: Company name, UID, legal seat, NOGA, purpose description
- **Volume**: ~10,000+ automotive companies

### Netherlands — KvK (PARTIAL)
- **Status**: Partially open. Free tier API at developers.kvk.nl
- **Filter**: SBI code 45.11 (trade in cars)
- **Limitation**: No bulk download. Rate-limited search API
- **Workaround**: Iterate SBI codes for automotive dealers via API
- **Volume**: ~25,000+ automotive trade businesses

### Germany — OffeneRegister (PARTIAL)
- **Status**: Civic project (Open Knowledge Foundation). Free bulk JSON dump (~4.5M companies)
- **Limitation**: NO activity codes — must cross-reference with other sources to identify auto dealers
- **Access**: offeneregister.de — bulk download
- **Strategy**: Download full dump, cross-reference with ZDK member search + yellow pages

### Spain — NO OPEN REGISTRY
- **Status**: Registro Mercantil is NOT open data. Individual lookups are paid
- **No CNAE-filtered company database** exists publicly
- **Strategy**: Rely on other layers (OSM, yellow pages, portal directories, Google Places)

---

## LAYER 1 — GEOSPATIAL DISCOVERY (Free/Low-Cost)

### OpenStreetMap / Overpass API (FREE, IMMEDIATE)
- **Tags**: `shop=car`, `shop=car_repair`, `shop=car_parts`
- **Coverage estimate**: 50-70% of actual dealers mapped
  - DE: ~15,000-20,000 nodes
  - FR: ~8,000-12,000
  - ES: ~5,000-8,000
  - NL: ~3,000-5,000
  - CH: ~3,000-4,000
  - BE: ~2,000-3,000
- **Access**: Overpass API (free, no auth) or bulk country extracts from download.geofabrik.de
- **Fields**: name, brand, address, phone, website, opening_hours, coordinates

### HERE Places API (75,000 req/month FREE)
- **Categories**: "Automobile Dealership - New Cars", "Automobile Dealership - Used Cars"
- **Quality**: Excellent in Western Europe (Nokia/Navteq heritage)
- **ToS**: More permissive than Google for data storage

### TomTom Places API (75,000 req/month FREE)
- **Categories**: "Car Dealer" (7315)
- **Quality**: Good in Western Europe
- **Most generous free tier** among commercial geo providers

### Foursquare Places API (FREE tier)
- **Categories**: "Auto Dealer" (4bf58dd8d48988d124951735)
- **Quality**: Good (acquired Factual in 2020)
- **Most permissive ToS** for data usage among all geo providers

### Google Places API ($200/month free credit)
- **~6,250 Nearby Search requests/month free**
- **Best coverage** but restrictive ToS (cannot build competing database)
- **Strategy**: Use ONLY for validation, not primary discovery

### Certificate Transparency Logs (FREE)
- **Source**: crt.sh (Sectigo) — search for new SSL certs with automotive keywords
- **Keywords**: autohaus, autobedrijf, garage, concessionnaire, concesionario, autohändler
- **Yield**: ~500-2,000 new automotive domains/month across EU TLDs
- **Cost**: Free. crt.sh is public.

---

## LAYER 2 — INDUSTRY DIRECTORIES & ASSOCIATIONS (Free, Scrapable)

### Dealer Association Member Searches
| Association | Country | URL | Est. Members | Scrapable |
|-------------|---------|-----|-------------|-----------|
| ZDK Betriebssuche | DE | kfzgewerbe.de/betriebssuche | ~36,000 | Yes |
| BOVAG Leden | NL | bovagleden.nl | ~8,000 | Yes (excellent) |
| TRAXIO Ledenzoeker | BE | traxio.be/nl/ledenzoeker | ~3,500 | Yes |
| AGVS Garagensuche | CH | agvs-upsa.ch/de/konsumenten/garagensuche | ~4,000 | Yes |
| GANVAM | ES | ganvam.es | ~3,500 | Limited |
| CNPA | FR | cnpa.fr | ~20,000 | Limited |

### Yellow Pages (all scrapable)
| Directory | Country | URL | Est. Auto Listings |
|-----------|---------|-----|-------------------|
| Gelbe Seiten | DE | gelbeseiten.de | ~30,000 |
| Pages Jaunes | FR | pagesjaunes.fr | ~50,000 |
| Paginas Amarillas | ES | paginasamarillas.es | ~15,000 |
| Gouden Gids | NL | goudengids.nl | ~5,000 |
| Gouden Gids / Pages d'Or | BE | goudengids.be / pagesdor.be | ~3,000 |
| local.ch | CH | local.ch | ~8,000 |

### OEM Dealer Locators (ALL brands, ALL countries)
Every OEM has a public dealer locator:
- VW: volkswagen.{tld}/haendlersuche
- BMW: bmw.{tld}/haendlersuche
- Mercedes: mercedes-benz.{tld}/dealer-locator
- Audi: audi.{tld}/haendlersuche
- Porsche, Toyota, Hyundai, Renault, Peugeot, Citroen, Opel, Ford, Kia, etc.

Strategy: Crawl every OEM locator for every country. Returns structured data (name, address, phone, services).

### OEM Certified Pre-Owned Programs
| Program | Brand | URL Pattern |
|---------|-------|-------------|
| Das WeltAuto | VW | dasweltauto.{tld} |
| BMW Premium Selection | BMW | bmwpremiumselection.{tld} |
| Mercedes Certified | MB | Country-specific |
| Audi Gebrauchtwagen :plus | Audi | Country-specific |
| Volvo Selekt | Volvo | volvocars.com/{cc}/selekt |
| Toyota Plus | Toyota | Country-specific |
| Porsche Approved | Porsche | finder.porsche.com |

These have structured, clean inventory data.

---

## LAYER 3 — PORTAL SCRAPING (27+ portals across 6 countries)

### Germany (DE)
| Portal | Est. Listings | Strategy |
|--------|--------------|----------|
| mobile.de | ~1.4M | Playwright + curl_cffi |
| AutoScout24.de | ~800K | Playwright (SPA, __NEXT_DATA__) |
| Kleinanzeigen (eBay) | Large | Playwright |
| AutoHero | ~30K | HTTP (Auto1 Group) |
| pkw.de | Aggregator | HTTP |
| automobile.de | Redirects to mobile.de | Skip |
| heycar.de | Check status | May be dead |
| kalaydo.de | Regional | HTTP |
| Quoka.de | Small | HTTP |
| motor-talk.de | Forum + marketplace | HTTP |
| Gebrauchtwagen.de | Small | HTTP |

### Spain (ES)
| Portal | Est. Listings | Strategy |
|--------|--------------|----------|
| Wallapop | ~713K | Playwright |
| Milanuncios | ~350K | Playwright |
| coches.net | ~250K | Playwright |
| AutoScout24.es | Good presence | Playwright |
| autocasion.com | Medium | HTTP |
| motor.es | Medium | HTTP |
| coches.com | Medium | HTTP |
| Clicars | Online dealer | HTTP |
| Kavak.com/es | Expanding | HTTP |
| vibbo.com | Small | HTTP |

### France (FR)
| Portal | Est. Listings | Strategy |
|--------|--------------|----------|
| LeBonCoin | ~815K | Playwright (Adevinta) |
| La Centrale | ~350K | Playwright |
| AutoScout24.fr | Good presence | Playwright |
| ParuVendu | Medium | HTTP |
| L'Argus | Medium + valuations | HTTP |
| Caradisiac | Medium | HTTP |
| OuestFrance Auto | Regional, large | HTTP |
| Aramis Auto | ~30K (Stellantis) | HTTP |
| Reezocar | Cross-border aggregator | HTTP |

### Netherlands (NL)
| Portal | Est. Listings | Strategy |
|--------|--------------|----------|
| Marktplaats | Large | Sitemap + Playwright |
| AutoScout24.nl | Good | Playwright |
| AutoTrack | ~170K | Playwright |
| Gaspedaal | ~300K (meta-search) | HTTP |
| ViaBOVAG | BOVAG dealers | HTTP |
| AutoWeek.nl | Medium | HTTP |
| Bynco | Online dealer | HTTP |

### Belgium (BE)
| Portal | Est. Listings | Strategy |
|--------|--------------|----------|
| 2dehands.be / 2ememain.be | Large | Sitemap + Playwright |
| AutoScout24.be | ~115K | Playwright |
| AutoGids / AutoGuide | Medium | HTTP |
| GoCAR.be | Medium | HTTP |
| Cardoen.be | Single dealer, large | HTTP |

### Switzerland (CH)
| Portal | Est. Listings | Strategy |
|--------|--------------|----------|
| AutoScout24.ch | ~60K | Playwright |
| Comparis.ch | Aggregator | Playwright |
| Tutti.ch | Medium | HTTP |
| AutoRicardo / CarForYou | Medium | HTTP |
| Autolina.ch | Small | HTTP |
| anibis.ch | Small | HTTP |

### Technical Stack for Portal Scraping
- **curl_cffi**: Chrome TLS fingerprint. 70-90% success against Cloudflare standard
- **Camoufox**: Firefox anti-detect at C++ level. 60-80% against Cloudflare
- **FlareSolverr**: Solves Cloudflare JS challenges, returns cookies
- **Playwright**: For SPAs (AutoScout24 __NEXT_DATA__ extraction)
- **IP rotation**: Home residential + mobile data + Oracle Cloud free tier (4 VMs forever free)

---

## LAYER 4 — DMS / MULTIPOSTING FEEDS (The Game Changer)

This is where CARDEX goes beyond any scraper.

### DMS Integrations (Clean, Real-Time, Structured)
| DMS | Dealers | API | Action Required |
|-----|---------|-----|-----------------|
| **Keyloop** | 15,000+ EU | developer.keyloop.io — documented partner program | Apply for certification |
| **Nextlane** | 10,000+ in 14 countries | REST APIs, 60+ OEM brands | Contact for marketplace destination |
| **MotorK / StockSparK** | 5,000+ in 8 countries | Multiposting platform | Register as portal destination |
| **incadea** | 4,000+ | MS Dynamics 365 backbone = standard REST/OData | Partner integration |

**Total DMS reach: ~30,000 dealers with clean, real-time inventory feeds.**

### Portal APIs (With Partner Access)
| Portal | API | Key Endpoint |
|--------|-----|-------------|
| mobile.de | services.mobile.de/docs/seller-api.html | **Ad Stream** — real-time listing changes |
| AutoScout24 | listing-creation.api.autoscout24.com/docs | Listing Creation API (schema reference) |
| Marktplaats | api.marktplaats.nl/docs/v1/ | REST API |

### Multiposting Services (Become a Destination)
| Service | How It Works |
|---------|-------------|
| MotorK StockSparK | Dealer uploads inventory once → publishes to N portals. CARDEX = portal N+1 |
| Carflow (now MotorK) | Same — 1,300+ dealers in BE/NL/FR |
| Nextlane Marketplace Connect | Nextlane DMS → approved marketplace destinations |

**Strategy**: Build a CARDEX Inbound API (JSON endpoint). Approach DMS/multiposters: "Add CARDEX as a free distribution channel for your dealers." Zero cost to them, adds value to their product.

### CARDEX Inbound API Spec (What We Build)
```
POST /v1/dealer/inventory
Content-Type: application/json
Authorization: Bearer <dealer_api_key>

{
  "dealer_id": "...",
  "vehicles": [
    {
      "vin": "WBA...",
      "make": "BMW",
      "model": "3 Series",
      "variant": "320d xDrive",
      "year": 2022,
      "mileage_km": 45000,
      "price": 35900,
      "currency": "EUR",
      "fuel_type": "DIESEL",
      "transmission": "AUTOMATIC",
      "color": "Black",
      "images": ["https://dealer-site.com/img/1.jpg"],
      "source_url": "https://dealer-site.com/vehicle/12345",
      "listing_status": "ACTIVE"
    }
  ]
}
```

---

## LAYER 5 — OPEN DATA ENRICHMENT

### Netherlands — RDW Open Data (EXCEPTIONAL)
- **URL**: opendata.rdw.nl
- **Status**: 100% free, no auth, SODA API
- **Dataset**: 15M+ vehicle records — every registered vehicle in NL
- **Fields**: Make, model, body type, fuel, weight, registration date, APK (MOT) expiry
- **Use**: Enrich NL vehicle data, validate mileage, detect anomalies

### Common Crawl — Schema.org/Vehicle Mining
- **Status**: Free, petabyte-scale web crawl
- **Strategy**: Filter for Schema.org/Vehicle markup → extract dealer URLs + inventory
- **Estimated yield**: 8,000-25,000 European dealer websites with structured vehicle data
- **Cost**: ~$50-200 on AWS Athena for filtered queries

### Web Data Commons
- **Status**: Pre-extracted Schema.org data from Common Crawl
- **Volume**: 106 billion RDF quads from 12.8M websites
- **Filter**: schema.org/Vehicle, schema.org/Car, schema.org/Product with automotive properties

---

## LAYER 6 — AUCTION / FLEET / WHOLESALE

### B2B Auction Platforms
| Platform | Volume | Coverage | Public Access |
|----------|--------|----------|--------------|
| BCA | ~3M/year | Pan-EU | Partial (some online auctions viewable) |
| Autorola | ~1M/year | 20+ countries | Online platform |
| CarOnSale | ~100K/year | DE-focused | B2B only |
| Openlane (ex-ADESA) | Significant | Pan-EU | B2B online |
| Auto1 Group | ~600K+/year | Pan-EU | B2B + B2C (AutoHero) |

### Leasing Return Portals (Direct B2C)
| Company | Portal |
|---------|--------|
| Ayvens (ALD+LeasePlan) | CarNext (carnext.com) |
| Arval (BNP Paribas) | Country-specific |
| Alphabet (BMW) | Country-specific |
| Athlon (Mercedes) | Country-specific |

### Rental Fleet Disposal
| Company | URL |
|---------|-----|
| Sixt | sixt.{tld}/gebrauchtwagen |
| Hertz | hertzcarssales.com |
| Enterprise | enterprisecarsales.com |

### Government Auctions
| Country | Platform |
|---------|----------|
| DE | vebeg.de, zoll-auktion.de |
| FR | encheres-domaine.gouv.fr |
| ES | Agencia Tributaria subastas |
| NL | domeinenrz.nl |
| BE | finshop.belgium.be |

---

## LAYER 7 — NICHE & SPECIALTY

### Classic Car Platforms
Classic Trader, Classic Driver, Elferspot (Porsche), Oldtimer.de, Car & Classic, Catawiki, Collecting Cars, Bonhams, RM Sotheby's, Artcurial

### Subscription / Flex Lease (Emerging Inventory)
FINN.com, INSTADRIVE, ViveLaCar, Like2Drive, Fleetpool — all have full online inventories

### Cross-Border Platforms
Reezocar, Carvago — aggregate cross-border inventory

---

## DEDUPLICATION STRATEGY

The same vehicle appears on 3-5 platforms. CARDEX shows it ONCE with links to all sources.

### Primary: VIN Match
- If VIN available → exact match → merge all sources under one entity
- ~65% of dealer listings include VIN

### Secondary: Fingerprint
- SHA256(make + model + year + mileage_km + color + dealer_city)
- Handles listings without VIN
- ~85% dedup accuracy

### Tertiary: Perceptual Image Hash
- pHash of main photo → fuzzy match
- Catches cases where specs differ slightly across portals
- Tie-breaker only

### Result
```
Vehicle Entity {
  vehicle_ulid: "01ABC...",
  make: "BMW",
  model: "3 Series",
  year: 2022,
  mileage_km: 45000,
  price_eur: 35900,
  sources: [
    { platform: "mobile.de", url: "https://...", price: 35900 },
    { platform: "autoscout24.de", url: "https://...", price: 36200 },
    { platform: "dealer-website.de", url: "https://...", price: 35900 }
  ],
  thumbnail_url: "https://...", // hotlinked, never downloaded
  dealer: { name: "Autohaus Schmidt", city: "Berlin", country: "DE" }
}
```

---

## FRESHNESS STRATEGY

| Dealer Size | Re-crawl Interval |
|-------------|-------------------|
| Large (>100 vehicles) | 6 hours |
| Medium (20-100) | 24 hours |
| Small (<20) | 72 hours |
| Portals (AutoScout24, mobile.de) | Continuous (stream-based if partner) |
| DMS feeds | Real-time (push-based) |

- HTTP conditional requests (If-Modified-Since, ETag) to minimize bandwidth
- Sitemap lastmod/changefreq respected
- Vehicle disappears from source → mark SOLD after 48h grace period

---

## ANTI-BLOCK TECHNICAL STACK

### HTTP Client
- **curl_cffi** (NOT requests/aiohttp) — matches Chrome TLS/JA3 fingerprint exactly
- Success rate: 70-90% against Cloudflare standard protection

### Browser Automation
- **Camoufox** — Firefox patched at C++ level, eliminates all automation fingerprints
- **Playwright** — for SPAs that require full JS rendering
- **FlareSolverr** — Cloudflare JS challenge solver, returns session cookies

### IP Strategy (Budget 0)
| Source | IPs | Type | Cost |
|--------|-----|------|------|
| Home connection | 1 | Residential (best) | Free |
| Mobile data (airplane toggle) | 1-2 | Residential/CGNAT | Free |
| Oracle Cloud free tier | 4 | Data center | Free forever |
| Friend/family SSH tunnel | 1-2 | Residential | Free |
| **Total** | **~6-10** | Mix | **0** |

### Rate Limiting
- Default: 1 request / 3-5 seconds per domain with ±30% jitter
- Adaptive: if response time >2s, slow down. If 429, exponential backoff
- Respect robots.txt Crawl-Delay
- Distribute across domains (never hammer one site)

---

## LEGAL FRAMEWORK

| Activity | Status | Basis |
|----------|--------|-------|
| Indexing public listings | LEGAL | Standard search engine activity |
| Storing vehicle metadata | LEGAL | Not personal data under GDPR |
| Linking to original source | LEGAL | This is what Google does |
| Automated access to public pages | LEGAL | EU Copyright Directive Art. 4 (TDM exception) |
| Respecting robots.txt | BEST PRACTICE | Art. 4 opt-out mechanism |
| Storing private seller names/phones | CAREFUL | GDPR applies — strip or use legitimate interest |

Key precedent: hiQ v. LinkedIn (US) — scraping public data is not unauthorized access.
EU Copyright Directive Art. 4 — TDM allowed unless rightsholder explicitly opts out.

---

## EXECUTION ORDER

### Phase 1 — Foundation (Week 1)
1. Build CARDEX Inbound API (JSON endpoint for dealers/DMS/multiposters)
2. Download + ingest SIRENE (FR), KBO (BE), Zefix (CH)
3. Query OSM Overpass for shop=car across all 6 countries
4. Crawl ZDK, BOVAG, TRAXIO, AGVS member directories

### Phase 2 — Portal Coverage (Week 2-3)
5. AutoScout24 Playwright scraper (1 scraper, 6 TLDs)
6. Marktplaats + 2dehands sitemap-based ingestion
7. curl_cffi scrapers for HTTP-accessible portals
8. Camoufox/FlareSolverr for Cloudflare-heavy portals

### Phase 3 — Dealer Web Crawl (Week 3-4)
9. For each discovered dealer with a website URL → crawl inventory
10. Schema.org/Vehicle parser
11. Sitemap detection + vehicle URL pattern matching
12. Generic inventory page detector (DOM heuristics)

### Phase 4 — DMS Integration (Month 2+)
13. Apply to Keyloop Partner Programme
14. Contact Nextlane for marketplace destination
15. Contact MotorK for StockSparK integration
16. Build onboarding documentation for dealers

### Phase 5 — Enrichment & Scale (Ongoing)
17. OEM dealer locator crawling (every brand, every country)
18. OEM CPO program inventory indexing
19. RDW open data integration (NL vehicle enrichment)
20. Common Crawl mining for Schema.org/Vehicle
21. Classic car, fleet, auction platforms

---

## SUCCESS METRICS

| Metric | Target (3 months) | Target (12 months) |
|--------|-------------------|-------------------|
| Dealers discovered | 50,000+ | 120,000+ |
| Unique vehicles indexed | 500,000+ | 3,000,000+ |
| Countries fully covered | 6 | 6 (+ expansion ready) |
| Portal sources | 15+ | 27+ |
| DMS integrations | 1+ | 3+ |
| Data freshness (avg) | <48h | <12h |
| Search latency | <50ms | <50ms |
