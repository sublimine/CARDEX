# CARDEX Discovery Engine v2.0
# Autonomous Pan-European Vehicle Intelligence System
# Target: Total market coverage — DE, ES, FR, NL, BE, CH

---

## 1. MISSION

Build the first vehicle indexing system that **knows what it doesn't know**.

Every existing platform — AutoUncle, AutoScout24, mobile.de — operates blind. They scrape their sources and call it a day. None of them can answer: "What percentage of the market am I actually seeing?" None can identify which dealers, which vehicles, which geographic regions are invisible to them.

CARDEX can. The system maintains a probabilistic model of market completeness, identifies gaps, and autonomously hunts to fill them. The result: 100% territory coverage across 6 countries, ~150,000 dealer entities, 3.5-4.5M unique vehicles at any moment.

**Not an aggregator. An autonomous cartographer of the European used car market.**

---

## 2. MARKET REALITY (Audited)

| Metric | Number | Source |
|--------|--------|--------|
| Annual used car transactions (6 countries) | 17.4M | KBA, BOVAG, Traxio, ASTRA, Autovista24 |
| Active listings at any moment (gross) | 5-7M | Portal self-reported |
| Unique vehicles (deduplicated) | 3.5-4.5M | Derived: dealers multi-list 3-5 portals |
| Formal dealers | 80,000-95,000 | ZDK, CNPA, GANVAM, BOVAG, Traxio, AGVS |
| Micro-dealers / informal | +30,000-60,000 | Industry estimates |
| **Total selling entities** | **~150,000** | |

AutoUncle: 2,600 webs = 1.7% territory. The largest platforms cover 15-20% at best.

---

## 3. THE AUTONOMOUS CORE — What Makes This Unprecedented

The architecture has two halves. The **Acquisition Layers** (Section 4) collect data. The **Autonomous Core** (this section) makes the system intelligent, self-aware, and self-improving. Without this, CARDEX is just another scraper with more sources. With it, CARDEX is a fundamentally different kind of system.

### 3.1 Coverage Estimation Engine — Modeling Ignorance

The central innovation. The system doesn't just track what it has; it statistically estimates what exists that it hasn't found yet.

#### Capture-Recapture (Lincoln-Petersen)

The same statistical method used to estimate animal populations without counting every individual. If Source A finds 5,000 dealers and Source B finds 4,000 dealers, and 2,500 appear in both — the estimated total population is:

```
N̂ = (n₁ × n₂) / m₂ = (5000 × 4000) / 2500 = 8,000
```

If we've found 6,500 unique across both sources, we estimate ~1,500 remain undiscovered.

Applied systematically across ALL source pairs (registries × geo × directories × portals × DMS), this produces a coverage estimate for every `(region, entity_type)` cell. The Chapman estimator corrects for small-sample bias. The Schnabel method extends to k>2 sources.

**Implementation**: After each ingestion cycle, the entity resolution system produces source-overlap matrices. A background worker computes population estimates per region using multi-source capture-recapture (Chao's Mth model for heterogeneous capture probabilities — because a dealer on mobile.de is more likely to be on AutoScout24 than one selling from a field).

#### Species Richness Estimators (from Ecology)

Capture-recapture assumes all entities are equally "catchable." They're not — a 200-car BMW dealer is far more visible than a 5-car micro-trader. Ecological species richness estimators handle this heterogeneity:

- **Chao1**: Lower-bound estimate based on singleton/doubleton frequencies. If many dealers appear in only one source, the true population is much larger than what we see.
- **ACE (Abundance-based Coverage Estimator)**: Partitions into rare (≤10 sources) and abundant (>10) species. Estimates unseen count from the rare stratum.
- **Jackknife estimators** (1st and 2nd order): Reduce bias of the naïve observed count by accounting for entities missed by all-but-one or all-but-two samples.

These give confidence intervals, not point estimates. The system can say: *"We estimate 14,200 ± 1,100 dealers in Nordrhein-Westfalen (95% CI). We have 12,340. Estimated gap: 1,860 dealers."*

#### Good-Turing Frequency Estimation

Estimates the probability that the *next* dealer discovered will be completely new (not in any source). As coverage saturates, this probability drops. The system uses this to decide when diminishing returns make further crawling of a region unproductive — and shifts effort to regions with higher expected discovery rates.

#### Coverage Heat Map

All estimates feed into a real-time spatial coverage map:

```
┌─────────────────────────────────────────────────────┐
│ Region          │ Found │ Estimated │ Coverage │ Gap │
├─────────────────────────────────────────────────────┤
│ Bayern, DE      │ 8,200 │ 9,100     │ 90.1%    │ 900 │
│ Île-de-France   │ 5,100 │ 6,800     │ 75.0%    │1700 │
│ Zuid-Holland, NL │ 2,300 │ 2,500     │ 92.0%    │ 200 │
│ Cataluña, ES    │ 3,400 │ 5,200     │ 65.4%    │1800 │
│ Vlaanderen, BE  │ 1,800 │ 2,100     │ 85.7%    │ 300 │
│ Zürich, CH      │   900 │ 1,000     │ 90.0%    │ 100 │
└─────────────────────────────────────────────────────┘
```

This drives the entire system. Low-coverage cells trigger targeted discovery campaigns.

### 3.2 Knowledge Graph — Structural Gap Detection

The Coverage Estimation Engine tells you *how many* entities you're missing. The Knowledge Graph tells you *what kind* and *where to look*.

#### Entity Model

```
Dealer ──[operates_in]──▶ Region
Dealer ──[affiliated_with]──▶ Brand
Dealer ──[listed_on]──▶ Portal
Dealer ──[uses_dms]──▶ DMS_Provider
Dealer ──[sells]──▶ Vehicle
Vehicle ──[listed_on]──▶ Portal
Portal ──[covers]──▶ Region
Brand ──[has_authorized_dealers]──▶ Region  (from OEM locators)
```

#### Gap Detection via Structural Inference

1. **Brand coverage gaps**: BMW says they have 65 authorized dealers in Baden-Württemberg (from OEM locator). We have 58. Seven are invisible — likely small, single-brand, not on major portals. Action: targeted geo search in BW zip codes we haven't covered.

2. **Portal coverage gaps**: In region X, 80% of dealers appear on AutoScout24. In region Y, only 30%. Either Y genuinely has low AS24 adoption (possible for Spain) or our AS24 scraper is failing for Y (pagination bug, geo-filter issue). Action: investigate scraper health.

3. **DMS shadow network**: Dealer A uses Keyloop and lists on portals X, Y, Z. Dealer B also uses Keyloop but only appears on X. Statistically, B should also be on Y and Z → either B chose not to (fine) or our scraper missed B on Y/Z (investigate).

4. **Co-citation analysis**: Dealers that appear on portal X have a 72% probability of also appearing on portal Y. For dealers found on X but NOT on Y, there's a 72% chance Y has them and we failed to match → triggers re-crawl with relaxed entity resolution parameters.

#### Implementation

PostgreSQL stores entities and relationships. A materialized view computes the overlap matrix hourly. Gap detection runs as a batch job that outputs:
- Missing dealer candidates (with probability scores)
- Scraper health anomalies (expected vs. actual overlap deviations)
- Region × source coverage percentages
- Targeted discovery campaigns (prioritized by expected yield)

### 3.3 Crawl Frontier — Intelligent Orchestration

Traditional scrapers use fixed schedules: "crawl mobile.de every 6 hours." This is wasteful. The system should crawl what will teach it the most, right now.

#### OPIC (Online Page Importance Computation)

Lightweight alternative to PageRank that doesn't require holding the full graph in memory. Each URL has a "cash" value that flows to linked pages. High-cash pages get crawled first. Applied to CARDEX:

- A registry page linking to 500 dealers has high importance (distributes cash to 500 entities)
- A dealer page with 0 outbound links to other dealers has low network importance
- A portal search result page that reveals 50 new dealers accumulates cash rapidly

OPIC runs incrementally — no batch recomputation needed. New URLs inherit importance from their parent page.

#### Multi-Armed Bandit for Source Allocation

Given finite crawl budget (requests/hour), how do you allocate across sources? This is a classic explore/exploit problem.

- **Exploit**: Crawl the source that historically yields the most new entities per request
- **Explore**: Try under-sampled sources that might yield more

Thompson Sampling with Beta priors per source. Each source maintains `(successes, failures)` where success = "discovered a new entity or updated a stale one." The bandit naturally shifts budget from exhausted sources to productive ones, while periodically re-testing low-performers.

#### Bayesian Change-Point Detection for Scheduling

Fixed re-crawl intervals are wrong. A dealer that changes inventory weekly needs weekly crawls. One that changes daily needs daily. One that hasn't changed in 3 months can be checked monthly.

Model each dealer's update pattern as a Poisson process. Observe actual changes. Bayesian updating of the rate parameter λ. Next crawl scheduled at:

```
t_next = t_last + 1/λ̂  (with a minimum floor)
```

A dealer that changes inventory 3 times/day: λ=3 → re-crawl every 8 hours.
A dealer that changes monthly: λ=0.03 → re-crawl every 33 days.

Change-point detection (BOCPD) catches dealers that change behavior: seasonal inventory pushes, going out of business, switching DMS. The system adapts within days, not months.

#### Expected Information Gain as Priority Metric

The unified priority score for any crawl action:

```
priority = P(discovery) × info_gain + freshness_urgency + opic_score
```

Where:
- `P(discovery)` = probability this action discovers a new entity (from coverage estimation)
- `info_gain` = Shannon information of the expected discovery (rare entity type = high)
- `freshness_urgency` = staleness relative to expected update rate
- `opic_score` = network importance of the URL

This means: crawling an unexplored region where the coverage estimate says 1,800 dealers are missing takes priority over re-crawling a fully-covered region, even if the latter has "important" portals.

### 3.4 Entity Resolution — Beyond Deduplication

Deduplication (Section 5) handles vehicles. Entity resolution handles the harder problem: knowing that "Autohaus Schmidt GmbH" on mobile.de, "Schmidt Auto" on AutoScout24, and "Autohaus Schmidt Berlin" on Google Maps are the same dealer.

#### Probabilistic Record Linkage (Fellegi-Sunter Model)

For each pair of records, compute field-level agreement weights:

| Field | Agreement Weight | Disagreement Weight |
|-------|-----------------|-------------------|
| Normalized name | +4.2 | -2.1 |
| Street address | +5.8 | -3.4 |
| Phone number | +8.5 | -1.2 |
| VAT/tax ID | +12.0 | -0.5 |
| Geo (within 500m) | +3.1 | -4.6 |
| Brand affiliations | +1.8 | -0.3 |

Sum of weights → composite score. Above upper threshold → automatic match. Below lower threshold → automatic non-match. In between → candidate for review or additional evidence.

Weights learned from labeled examples (initial seed of manually verified matches) using EM algorithm (unsupervised Fellegi-Sunter). As the system accumulates verified matches, weights improve automatically.

#### Transitive Closure with Conflict Resolution

If A matches B and B matches C, then A matches C — but only if there are no contradictory signals. If A and C have conflicting addresses that are 50km apart, flag for investigation rather than blindly merging.

The system maintains a union-find structure with edge confidence scores. Merges below confidence threshold create "soft links" (probable same entity) rather than hard merges.

#### Dealer Identity Graph

The result is a unified dealer entity:

```
DealerEntity {
  dealer_ulid: "01DEF...",
  canonical_name: "Autohaus Schmidt GmbH",
  identities: [
    { source: "mobile.de", name: "Autohaus Schmidt", dealer_id: "DE-123456" },
    { source: "autoscout24.de", name: "Schmidt Auto Berlin", dealer_id: "AS-789" },
    { source: "google_maps", name: "Autohaus Schmidt Berlin", place_id: "ChIJ..." },
    { source: "sirene_fr", name: null, siren: null },  // not French
    { source: "kbo_be", name: null, enterprise_no: null }  // not Belgian
  ],
  locations: [{ lat: 52.52, lon: 13.405, address: "..." }],
  brands: ["BMW", "MINI"],
  estimated_stock: 120,
  dms: "Keyloop",
  portals: ["mobile.de", "autoscout24.de", "heycar.de"],
  confidence: 0.97,
  last_verified: "2026-04-05T10:30:00Z"
}
```

### 3.5 Self-Improving Source Discovery

The system doesn't wait for humans to add new data sources. It finds them.

#### Snowball Sampling

Every discovered dealer is a seed. From each dealer:
1. **Website backlinks** (via Common Crawl link graph): who links to this dealer? Often: portals we haven't indexed yet, directory sites, local business networks.
2. **Portal profiles**: dealer's mobile.de profile might link to their AutoScout24 profile, their own website, their DMS provider. Follow everything.
3. **Google My Business links**: dealer's GMB listing often contains website URL + links to portal listings.
4. **ads.txt / sellers.json**: If dealer website has ads.txt, it reveals their advertising network — and often their multiposting provider. If a multiposting provider serves 200 dealers, approaching them yields 200 feeds.

Each new discovery feeds back into the Knowledge Graph, which identifies more gaps, which triggers more discovery. Positive feedback loop.

#### Certificate Transparency Log Monitoring

New automotive businesses register SSL certificates. CT logs are public and real-time.

```
Monitor crt.sh for new certs matching:
  *autohaus*, *autobedrijf*, *garage*, *concessionnaire*,
  *concesionario*, *autohändler*, *cars*, *motors*, *voiture*,
  *automobil*, *fahrzeug*, *voertuig*, *coche*, *wagen*
Filter: EU TLDs (.de, .es, .fr, .nl, .be, .ch, .eu, .com)
```

Estimated yield: 500-2,000 new automotive domains/month across 6 countries. Each is a potential dealer not yet in any portal.

#### Search API Probing

For under-covered regions (from the coverage heat map):
1. Query HERE/TomTom Places API with `category=car_dealer` in grid cells where coverage < 70%
2. Cross-reference results against known dealer entities
3. New discoveries → validate → ingest

Budget: 75K req/month free per provider. Targeted at low-coverage cells, not blanket scanning.

#### Common Crawl Backlink Graph Analysis

1. Take all known dealer domains
2. Query Common Crawl index for pages linking TO these domains
3. Cluster referrer domains → identify portals, directories, and networks
4. Any referrer domain linking to 10+ known dealers that isn't in our source list → new source candidate

This has historically surfaced regional portals, niche directories, and B2B platforms invisible to manual research.

### 3.6 Adversarial Adaptation Engine

Portals don't want to be scraped. The system must adapt, not just resist.

#### Per-Source Health Monitoring

Each source has a health score computed from:
- **Success rate**: % of requests returning valid data (not blocks/captchas/empty)
- **Yield rate**: new/updated entities per request
- **Freshness**: time since last successful full crawl
- **Drift detection**: sudden drop in yield = possible block or site change

Health scores feed into the crawl frontier. Degraded source → reduce request rate, switch client fingerprint, try alternative extraction path.

#### Strategy Cascade

For each source, the system maintains an ordered list of strategies:

```
1. curl_cffi (Chrome TLS) + residential IP  →  cheapest, fastest
2. curl_cffi + Oracle Cloud IP              →  slightly degraded
3. Camoufox headless                        →  heavier but less detectable
4. Playwright + FlareSolverr cookies        →  for JS challenges
5. Camoufox with full rendering             →  last resort, expensive
6. Portal API (if partner)                  →  ideal, rate-limited
7. DMS feed (if available)                  →  best, push-based
```

If strategy 1 drops below 50% success → automatic escalation to 2. If all HTTP strategies fail → switch to browser. If browser fails → flag for human investigation (possible site redesign, legal block, or captcha wall).

The system logs every request-response pair's fingerprint outcome. Over time, it learns which strategy works for which portal at which time of day (some portals are more aggressive at night when bot traffic is higher).

#### Rate Adaptation

Not fixed rate limits — adaptive:
- Start at 1 req/5s per domain
- If 0 blocks after 1000 requests → increase to 1 req/3s
- If block rate > 5% → decrease to 1 req/10s with jitter ±50%
- If block rate > 20% → pause 1h, switch strategy
- Respect `Retry-After` and `Crawl-Delay` always

---

## 4. DATA ACQUISITION LAYERS

Seven layers, ordered by reliability and cost. The Autonomous Core (Section 3) orchestrates across all layers simultaneously.

### Layer 0 — Business Registries (Free, Bulk, Definitive)

Government registries provide the ground truth for formal dealer entities.

| Registry | Country | Quality | Access | Auto Filter | Est. Dealers |
|----------|---------|---------|--------|-------------|-------------|
| INSEE SIRENE | FR | GOLD | Bulk CSV (12 GB) + REST API | NAF 45.11Z, 45.19Z | ~40,000 |
| KBO/BCE | BE | GOLD | Monthly bulk CSV | NACE-BEL 45.110 | ~30,000 |
| Zefix | CH | GOOD | REST API + bulk at opendata.swiss | NOGA 45.11 + text | ~10,000 |
| KvK | NL | PARTIAL | Rate-limited API | SBI 45.11 | ~25,000 |
| OffeneRegister | DE | PARTIAL | Bulk JSON, no activity codes | Cross-ref needed | ~36,000 |
| Registro Mercantil | ES | NONE | Paid, no bulk | N/A | Rely on other layers |

### Layer 1 — Geospatial Discovery (Free/Low-Cost)

| Source | Coverage | Free Tier | Best For |
|--------|----------|-----------|----------|
| OpenStreetMap / Overpass | 50-70% of dealers | Unlimited | Bulk initial discovery |
| HERE Places API | Excellent (W. Europe) | 75K req/mo | Targeted gap-filling |
| TomTom Places API | Good (W. Europe) | 75K req/mo | Secondary validation |
| Foursquare Places | Good | Free tier | Most permissive ToS |
| Google Places | Best coverage | ~6,250 req/mo | Validation only (ToS) |
| CT Log monitoring (crt.sh) | New domains | Unlimited | Continuous new-source discovery |

### Layer 2 — Industry Directories & Associations

| Source | Country | Est. Members | Scrapable |
|--------|---------|-------------|-----------|
| ZDK Betriebssuche | DE | ~36,000 | Yes |
| BOVAG Leden | NL | ~8,000 | Yes (excellent) |
| TRAXIO Ledenzoeker | BE | ~3,500 | Yes |
| AGVS Garagensuche | CH | ~4,000 | Yes |
| GANVAM | ES | ~3,500 | Limited |
| CNPA | FR | ~20,000 | Limited |
| Yellow Pages (6 countries) | All | ~111,000 total | Yes |
| OEM Dealer Locators (all brands) | All | Every authorized dealer | Structured JSON/XML |
| OEM Certified Pre-Owned (Das WeltAuto, BMW PS, MB Certified...) | All | Clean inventory | Structured |

### Layer 3 — Portal Scraping (27+ portals)

| Country | Major Portals | Est. Gross Listings |
|---------|--------------|-------------------|
| DE | mobile.de, AutoScout24.de, Kleinanzeigen, AutoHero, pkw.de | ~2.5M |
| ES | Wallapop, Milanuncios, coches.net, AutoScout24.es, autocasion | ~1.5M |
| FR | LeBonCoin, La Centrale, AutoScout24.fr, ParuVendu, L'Argus | ~1.3M |
| NL | Marktplaats, AutoScout24.nl, AutoTrack, Gaspedaal, ViaBOVAG | ~600K |
| BE | 2dehands/2ememain, AutoScout24.be, AutoGids, GoCAR | ~300K |
| CH | AutoScout24.ch, Comparis, Tutti.ch, CarForYou, Autolina | ~150K |

**Technical stack**: curl_cffi (Chrome TLS), Camoufox (C++-level anti-detect), FlareSolverr (CF bypass), Playwright (SPA rendering). IP: residential + mobile + Oracle Cloud free tier = 6-10 IPs at zero cost.

### Layer 4 — DMS / Multiposting Feeds (The Leverage Point)

One DMS integration = thousands of dealers with clean, real-time, structured data. No scraping needed.

| DMS/Service | Dealers | API Status | Action |
|-------------|---------|-----------|--------|
| Keyloop | 15,000+ EU | developer.keyloop.io — documented partner program | Apply for certification |
| Nextlane | 10,000+ (14 countries) | REST APIs, 60+ OEM brands | Register as marketplace destination |
| MotorK / StockSparK | 5,000+ (8 countries) | Multiposting platform | Register as portal destination |
| incadea | 4,000+ | MS Dynamics 365 REST/OData | Partner integration |
| mobile.de Seller API | Direct | Ad Stream — real-time changes | Partner access |
| AutoScout24 Listing API | Direct | Listing Creation API | Partner access |
| Marktplaats API | Direct | REST API | Partner access |

**Strategy**: Build CARDEX Inbound API. Approach DMS/multiposters: "Add CARDEX as a free distribution channel." Zero cost to them. Net new reach for their dealers.

### Layer 5 — Open Data Enrichment

| Source | Data | Access | Use |
|--------|------|--------|-----|
| RDW (NL) | 15M+ vehicle records | Free, SODA API | Enrich, validate, detect anomalies |
| Common Crawl | Schema.org/Vehicle markup | ~$50-200 Athena | 8-25K dealer websites with structured data |
| Web Data Commons | Pre-extracted Schema.org | Free | Faster than raw Common Crawl |

### Layer 6 — Auction / Fleet / Wholesale

| Category | Platforms | Access |
|----------|-----------|--------|
| B2B Auctions | BCA (~3M/yr), Autorola (~1M/yr), CarOnSale, Openlane, Auto1 Group | B2B registration |
| Leasing Returns | Ayvens/CarNext, Arval, Alphabet, Athlon | Public portals |
| Rental Fleet | Sixt, Hertz, Enterprise | Public portals |
| Government | vebeg.de, zoll-auktion.de, encheres-domaine.gouv.fr, etc. | Public |

### Layer 7 — Niche & Specialty

Classic cars (Classic Trader, Classic Driver, Elferspot, Collecting Cars), subscription/flex (FINN, INSTADRIVE, ViveLaCar), cross-border (Reezocar, Carvago).

---

## 5. VEHICLE DEDUPLICATION

The same vehicle appears on 3-5 platforms. CARDEX shows it once, with links to all sources.

### Three-Stage Pipeline

```
Stage 1: VIN Match (exact)
  └─ ~65% of dealer listings include VIN → deterministic merge

Stage 2: Fingerprint Match
  └─ SHA256(normalize(make) + model + year + mileage_bucket + color + dealer_city)
  └─ mileage_bucket = floor(mileage / 1000) to absorb rounding differences
  └─ Handles listings without VIN. ~85% accuracy.

Stage 3: Perceptual Image Hash (tie-breaker)
  └─ pHash of main photo → hamming distance < 8 = match candidate
  └─ Only used when fingerprint is ambiguous (same make/model/year, close mileage)
```

### Result: Unified Vehicle Entity

```
VehicleEntity {
  vehicle_ulid: "01ABC...",
  vin: "WBA..." | null,
  make: "BMW", model: "3 Series", variant: "320d xDrive",
  year: 2022, mileage_km: 45000,
  sources: [
    { portal: "mobile.de", url: "...", price_eur: 35900, seen: "2026-04-05" },
    { portal: "autoscout24.de", url: "...", price_eur: 36200, seen: "2026-04-05" },
    { portal: "dealer-website.de", url: "...", price_eur: 35900, seen: "2026-04-04" }
  ],
  best_price: 35900,
  price_spread: 300,
  dealer: "01DEF..." (→ DealerEntity),
  thumbnail_url: "https://..." (hotlinked, never stored),
  listing_status: ACTIVE | SOLD | STALE,
  first_seen: "2026-03-15",
  days_on_market: 21
}
```

---

## 6. TEMPORAL INTELLIGENCE

The system doesn't just see the market now — it understands its dynamics.

### Vehicle Lifecycle Tracking

```
Listed → Price Change(s) → Sold/Removed
  │           │                  │
  ▼           ▼                  ▼
first_seen   price_history[]    last_seen + 48h grace → mark SOLD
```

- **Days on market** per vehicle, per dealer, per segment
- **Price decay curves**: average markdown trajectory per make/model/region
- **Inventory turnover**: dealer-level metric, reveals health and pricing strategy

### Adaptive Crawl Scheduling (from Section 3.3)

| Signal | Schedule |
|--------|----------|
| Dealer changes daily (λ ≥ 1) | Re-crawl every 6-12h |
| Dealer changes weekly (λ ≈ 0.14) | Re-crawl every 3-5 days |
| Dealer static for weeks (λ ≤ 0.03) | Re-crawl every 14-30 days |
| Portal with streaming API | Real-time push |
| DMS feed | Real-time push |

HTTP conditional requests (`If-Modified-Since`, `ETag`) minimize wasted bandwidth. Sitemap `lastmod` respected.

### Market Signals (Byproduct of Coverage)

The coverage estimation engine necessarily produces market intelligence:
- **Regional demand signals**: listing density × turnover speed
- **Price surface**: make/model/year/mileage/region → expected price (anomaly = opportunity or fraud)
- **Supply/demand imbalance**: regions where listings disappear fast = high demand
- **Seasonal patterns**: spring surge, December dip, bonus cycles

These are not bolt-on analytics — they emerge naturally from the system's core function. They become the basis of the SaaS product for dealers and the arbitrage detection for B2B customers.

---

## 7. LEGAL FRAMEWORK

| Activity | Status | Basis |
|----------|--------|-------|
| Indexing public listings | LEGAL | Standard search engine activity |
| Storing vehicle metadata | LEGAL | Not personal data (GDPR N/A) |
| Linking to original source | LEGAL | Google precedent |
| Automated access to public pages | LEGAL | EU Copyright Directive Art. 4 TDM exception |
| Respecting robots.txt | BEST PRACTICE | Art. 4 opt-out mechanism |
| Private seller names/phones | CAREFUL | GDPR applies — strip or legitimate interest |
| DMS/portal partner feeds | LEGAL | Contractual B2B relationship |

Key precedents: hiQ v. LinkedIn (US) — scraping public data ≠ unauthorized access. EU Copyright Directive Art. 4 — TDM allowed unless rightsholder explicitly opts out (robots.txt).

---

## 8. INFRASTRUCTURE

### Stack

| Component | Technology | Role |
|-----------|-----------|------|
| OLTP | PostgreSQL 16 | Dealers, vehicles, relationships, entity resolution |
| OLAP | ClickHouse | Analytics, price history, market signals |
| Cache/Streams | Redis 7.2 + RedisBloom | Crawl queue, dedup bloom filters, real-time streams |
| Search | MeiliSearch | <50ms faceted search for marketplace UI |
| Frontend | Next.js 14 | Marketplace web app |
| Services | Go | Gateway, Pipeline, API, Scheduler |
| Scrapers | Python | curl_cffi, Camoufox, Playwright, per-country modules |
| Monitoring | Prometheus + Grafana | System health, crawl metrics, coverage dashboards |
| Container | Docker Compose (dev), systemd (prod) | |
| Infrastructure | Hetzner bare-metal | 327€/mo, 3-node cluster |

### Data Flow

```
                    ┌──────────────────────────────────────────┐
                    │         AUTONOMOUS CORE                   │
                    │                                          │
                    │  Coverage Estimation  ◄──┐               │
                    │        │                 │               │
                    │        ▼                 │               │
                    │  Crawl Frontier ────────►│               │
                    │  (priority queue)        │               │
                    │        │                 │               │
                    │        ▼                 │               │
                    │  Source Discovery ───────┤               │
                    │                         │               │
                    │  Knowledge Graph ◄──────┘               │
                    │  (gap detection)                         │
                    └────────────┬─────────────────────────────┘
                                 │ crawl commands
                                 ▼
┌─────────┐  ┌─────────┐  ┌──────────┐  ┌──────────┐
│Registries│  │   Geo   │  │ Portals  │  │DMS/Feeds │
│(Layer 0) │  │(Layer 1)│  │(Layer 3) │  │(Layer 4) │
└────┬─────┘  └────┬────┘  └────┬─────┘  └────┬─────┘
     │             │            │              │
     └──────┬──────┴────────────┴──────┬───────┘
            │                          │
            ▼                          ▼
     ┌──────────┐              ┌──────────────┐
     │ Gateway  │              │   Inbound    │
     │(scraped) │              │  API (feeds) │
     └────┬─────┘              └──────┬───────┘
          │                           │
          └───────────┬───────────────┘
                      ▼
               ┌─────────────┐
               │  Pipeline   │
               │  (Redis     │
               │   Streams)  │
               └──────┬──────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
   ┌──────────┐ ┌──────────┐ ┌──────────┐
   │  Entity  │ │  Dedup   │ │Normalize │
   │Resolution│ │ (3-stage)│ │          │
   └────┬─────┘ └────┬─────┘ └────┬─────┘
        │             │            │
        └──────┬──────┴────────────┘
               ▼
        ┌─────────────┐     ┌──────────┐
        │ PostgreSQL  │────▶│ClickHouse│
        │  (entities) │     │(analytics)│
        └──────┬──────┘     └──────────┘
               │
          ┌────┴────┐
          ▼         ▼
   ┌──────────┐ ┌────────┐
   │MeiliSearch│ │  API   │──▶ Marketplace UI
   │ (search) │ │(Go REST)│──▶ Dealer SaaS
   └──────────┘ └────────┘──▶ B2B Data Products
```

The feedback loop is the key: Pipeline output feeds back into the Autonomous Core, which updates coverage estimates, detects new gaps, and generates new crawl commands. The system gets smarter with every piece of data it ingests.

---

## 9. EXECUTION ROADMAP

### Phase 1 — Foundation + First Coverage Estimate (Week 1-2)

1. Ingest bulk registries: SIRENE (FR), KBO (BE), Zefix (CH)
2. Query OSM Overpass for `shop=car` across all 6 countries
3. Crawl association directories: ZDK, BOVAG, TRAXIO, AGVS
4. Entity resolution across registry + geo + directory sources
5. **First capture-recapture estimate** — baseline coverage per region
6. Build coverage heat map dashboard (Grafana)

**Exit criteria**: Known entity count > 40,000 dealers. First coverage estimates with confidence intervals.

### Phase 2 — Portal Coverage + Gap-Directed Crawling (Week 3-5)

7. AutoScout24 Playwright scraper (1 scraper, 6 TLDs)
8. Major portals per country (mobile.de, LeBonCoin, Wallapop, Marktplaats, 2dehands)
9. Entity resolution: merge portal dealers with registry/geo entities
10. **Second capture-recapture** — dramatically improved estimates from portal overlap
11. Coverage heat map now shows portal-vs-registry gaps
12. Targeted geo API queries for low-coverage cells

**Exit criteria**: Known entity count > 80,000. Vehicle count > 500,000. Coverage estimates per region with meaningful confidence intervals.

### Phase 3 — Autonomous Core Online (Week 6-8)

13. OPIC-based crawl frontier replaces fixed schedules
14. Thompson Sampling source allocator online
15. Bayesian change-point detection for adaptive scheduling
16. Snowball sampling from discovered dealer websites
17. CT log monitoring for new automotive domains
18. Knowledge Graph gap detection running as batch job
19. Self-improving source discovery loop operational

**Exit criteria**: System generates its own crawl priorities. Discovery rate is accelerating, not plateauing. New sources being found without human input.

### Phase 4 — DMS Integration + Scale (Month 3+)

20. Apply to Keyloop Partner Programme
21. Contact Nextlane, MotorK, incadea
22. Build dealer onboarding portal
23. DMS feeds flowing → massive coverage jump with zero scraping cost
24. OEM locator + CPO inventory crawling
25. Common Crawl Schema.org mining
26. Auction/fleet/niche platforms

**Exit criteria**: 120,000+ dealer entities. 3M+ vehicles. DMS providing >30% of data. Coverage estimate >85% in all tier-1 regions.

---

## 10. SUCCESS METRICS

| Metric | 3 Months | 12 Months |
|--------|----------|-----------|
| Dealer entities (resolved) | 80,000+ | 130,000+ |
| Unique vehicles indexed | 500,000+ | 3,500,000+ |
| Estimated coverage (avg) | 60-70% | >90% |
| Coverage confidence interval width | ±15% | ±5% |
| Countries with >80% coverage | 2-3 | 6 |
| Active data sources | 20+ | 50+ |
| Autonomously discovered sources | 5+ | 30+ |
| DMS integrations | 1+ | 3+ |
| Data freshness (median) | <48h | <12h |
| Search latency (p99) | <100ms | <50ms |
| Entity resolution precision | >90% | >97% |
| Scraper health (avg success rate) | >70% | >85% |

**The north star metric is estimated coverage, not entity count.** Any system can claim millions of listings. Only CARDEX can prove what percentage of the actual market it sees — and that number should trend monotonically upward.
