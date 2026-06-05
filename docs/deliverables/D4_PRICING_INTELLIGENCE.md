# CARDEX — European Vehicle Pricing Intelligence

**Version:** 1.0
**Date:** 2026-06-05
**Classification:** Product Documentation (B2B-facing)
**Purpose:** Defines the CARDEX Pricing Intelligence product — what it delivers, how it works, and what it costs
**Data foundation:** 1.55M+ vehicle listings indexed across DE, ES, FR, NL, BE, CH (snapshot 2026-04-10)

---

## 1. What CARDEX Pricing Intelligence Is

CARDEX Pricing Intelligence is a data product that provides real-time and historical pricing analytics for the European used-vehicle market. It answers a single question that every dealer, fleet manager, and remarketer needs answered daily:

**"What is vehicle X worth in market Y right now, and how has that changed?"**

It is not a valuation tool (like DAT/Schwacke or Eurotax). It is a market observation tool: it shows what comparable vehicles are actually listed for across 84+ portals in 6 countries. The distinction matters — valuations are opinions; market observations are facts.

---

## 2. Data Foundation

### 2.1 Coverage

| Country | Portals scraped | Example portals | Estimated active listings indexed |
|---------|----------------|-----------------|-----------------------------------|
| DE | ~25 | mobile.de, AutoScout24.de, heycar.com, kleinanzeigen.de, autohero.com, auto.de | ~600K |
| FR | ~20 | leboncoin.fr, lacentrale.fr, aramisauto.fr, leparking.fr, automobile.fr, largus.fr | ~350K |
| ES | ~12 | coches.net, autocasion.com, motor.es, wallapop.com, flexicar.es, milanuncios.com | ~200K |
| NL | ~10 | marktplaats.nl, autotrack.nl, autoweek.nl, autowereld.nl, gaspedaal.nl, autokopen.nl | ~150K |
| BE | ~10 | 2dehands.be, gocar.be, cardoen.be, moniteurautomobile.be, vroom.be, kapaza.be | ~120K |
| CH | ~7 | comparis.ch, autolina.ch, tutti.ch, carforyou.ch, anibis.ch, gowago.ch | ~80K |
| **Total** | **84+** | | **~1.55M** |

### 2.2 Update Frequency

- T0/T1 portals (public APIs, basic protection): inventory refreshed every 6-12 hours
- T2 portals (Akamai-protected): inventory refreshed every 24-48 hours
- T3 portals (DataDome-protected): inventory refreshed every 48-72 hours
- Price changes detected within one refresh cycle of the source portal

### 2.3 Data Quality

Every listing passes through 20 validators (V01–V20) before entering the index:

- VIN validation (Luhn checksum) where VIN is available
- Price plausibility per make/model/year (V07) — catches listing errors and scams
- Cross-source deduplication (V12) — same vehicle on 3 portals counts once
- Freshness enforcement (V14) — listings older than 30 days without re-confirmation are flagged
- Composite quality score (V20) — only PUBLISH-grade listings enter the pricing analytics

---

## 3. Core Analytics Capabilities

### 3.1 Market Price by Segment

For any vehicle segment (defined by make, model, year range, country), CARDEX provides:

| Metric | Description |
|--------|-------------|
| **Median asking price** | 50th percentile of current listings — the best single-number answer to "what is it worth?" |
| **P25 / P75 price range** | Interquartile range — defines the "normal" price band |
| **Mean asking price** | Average, useful but distorted by outliers |
| **Listing count** | Number of active listings matching the segment — measures market liquidity |
| **Days on market (DOM)** | Average time from first-seen to sold/removed — measures how quickly the segment sells |
| **Price per km** | Price divided by mileage — normalized comparison metric |

**Example output:**

```
Segment: BMW 3 Series, 2019-2021, Diesel, Germany
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Active listings:    1,247
Median price:       €23,800
P25–P75 range:      €20,500 – €27,200
Mean mileage:       68,400 km
Avg days on market: 34 days
Price/km:           €0.348
```

### 3.2 Cross-Border Price Arbitrage

The core differentiator of CARDEX versus single-country tools. For each vehicle segment, compare prices across countries:

```
BMW 320d, 2020, 40-60K km — Cross-Border Comparison (June 2026)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Country    Median Price    Listings    Arbitrage vs DE
DE         €22,500         312         baseline
ES         €24,800         87          +€2,300 (+10.2%)
FR         €23,100         143         +€600 (+2.7%)
NL         €23,900         64          +€1,400 (+6.2%)
BE         €22,800         52          +€300 (+1.3%)
CH         CHF 25,200      41          +€1,850 (+8.2%) [at ECB rate]

Opportunity: Buy in DE, sell in ES — gross margin ~€2,300/unit
Transport DE→ES estimate: €400-800 depending on method
Net arbitrage: ~€1,500-1,900/unit before taxes and registration
```

**This is the product.** A dealer in Spain who sees this data can immediately source cheaper inventory from Germany. A fleet manager liquidating vehicles in the Netherlands can identify which country offers the best resale price.

### 3.3 Price Trend Analysis

Historical price data (retained for 90 days post-delist) enables trend detection:

- Weekly/monthly price movement per segment
- Seasonal patterns (summer spike for convertibles, winter demand for AWD)
- Depreciation curves by model and country
- Market event impact (new model launch → used model price drop)

**Future capability (Chronos forecasting, experimental):** The `innovation/chronos_forecasting/` service (port :8503) can generate 30-day price forecasts using Chronos-2/AutoETS models per (country, make, model, year_range). Currently experimental, not production-deployed. When validated, this adds predictive pricing to the product.

### 3.4 Dealer-Level Analytics

Because CARDEX identifies dealers across portals, it can provide:

- **Inventory composition:** What makes/models does a specific dealer carry? How has their mix changed?
- **Pricing strategy:** Is this dealer consistently above or below market median?
- **Inventory velocity:** How quickly does this dealer turn their stock?
- **Multi-portal presence:** Where does this dealer list? (mobile.de + AutoScout24 + heycar = high marketing spend)

---

## 4. Delivery Mechanisms

### 4.1 API (Primary — planned)

RESTful JSON API with the following endpoint structure:

```
GET /v1/market/price
  ?make=BMW&model=3+Series&year_min=2019&year_max=2021
  &fuel=diesel&country=DE
  → Returns: median, P25, P75, count, DOM, trend

GET /v1/market/arbitrage
  ?make=BMW&model=3+Series&year_min=2019&year_max=2021
  &fuel=diesel
  → Returns: per-country pricing comparison

GET /v1/listings/search
  ?make=BMW&model=3+Series&price_max=25000&country=DE,ES
  &sort=price_asc&limit=50
  → Returns: individual listings matching criteria

GET /v1/listings/{listing_id}
  → Returns: full listing detail with price history

GET /v1/market/trend
  ?make=BMW&model=3+Series&country=DE&period=90d
  → Returns: weekly price points, volume, DOM over period
```

**Authentication:** API key (header `X-Api-Key`). One key per customer. Rate limiting per key.

**Status:** Endpoint design defined. Implementation pending (Go HTTP handlers wrapping SQLite queries). The data is ready — the delivery layer is the remaining work.

### 4.2 Sample Reports (Immediate — for sales demos)

Automated PDF reports for specific segments. Purpose: demonstrate value to prospective customers before the API is built.

**Report template:**
1. Executive summary: segment definition, key metrics
2. Cross-border comparison table
3. Price distribution chart (histogram)
4. 90-day price trend chart
5. Top 10 arbitrage opportunities with specific listings

**Generation:** Python script querying SQLite → matplotlib charts → reportlab PDF. Cost: €0 per report. Time: ~30 minutes to build the generator, then automated.

**Use case:** Send a sample report to 20 target dealers by email. Subject: "BMW 3 Series pricing intelligence — your market vs. 5 other EU countries." This is the first sales test. If 2 dealers respond, there is a product.

### 4.3 Webhook Alerts (Future)

Push notifications when pricing conditions are met:

- "BMW 320d in DE dropped below €20,000 — 3 new listings match your criteria"
- "Arbitrage opportunity: VW Golf 8, ES→DE spread exceeded €2,000"
- "Your watchlist vehicle (VIN: xxx) had a price change: €24,500 → €22,900"

---

## 5. Pricing Model

### 5.1 Proposed Tiers

| Tier | Price | Includes | Target customer |
|------|-------|----------|-----------------|
| **Free** | €0/month | 10 API calls/day. 1 country. No export. | Evaluation / small dealer curiosity |
| **Starter** | €99/month | 1,000 API calls/day. 3 countries. CSV export. | Single-location dealer doing occasional cross-border sourcing |
| **Professional** | €249/month | 10,000 API calls/day. All 6 countries. Webhook alerts. | Multi-location dealer group or fleet manager |
| **Enterprise** | Custom | Unlimited calls. Raw data feeds. Custom segments. SLA. | Remarketing companies, OEM captives, large fleet operators |

### 5.2 Pricing Rationale

- **Indicata (Autorola)** charges €300-600/month for their Market Watch dashboard. CARDEX Starter undercuts at €99/month with comparable cross-border data.
- **DAT/Schwacke** charges per-valuation (€2-5 per lookup). CARDEX is not a valuation tool but offers complementary market intelligence at a flat monthly rate.
- **Break-even analysis:** At €99/month Starter tier, CARDEX needs 4 paying customers to cover the €300/month operating budget (VPS + proxies + domain). At €249/month Professional tier, 2 customers cover costs.

### 5.3 Implementation

**Payment:** Stripe metered billing (API call counting) or simple subscription. Stripe setup cost: €0 (pay-as-you-go 1.4% + €0.25 per transaction in EU).

**Billing integration effort:** ~8 hours (Stripe Checkout + webhook for subscription events + API key provisioning).

---

## 6. Competitive Positioning

| Capability | CARDEX | Indicata (Autorola) | DAT/Schwacke | Eurotax |
|------------|--------|---------------------|--------------|---------|
| Cross-border pricing | 6 countries, real-time | 18 countries (larger but less granular) | DE-focused | EU-wide |
| Data source | 84+ portal listings (market observation) | Auction transaction data + OEM feeds | Expert valuation model | Insurance claims + trade data |
| Update frequency | 6-72h depending on portal | Weekly (auction cycles) | On-demand valuations | Monthly reports |
| Individual listing access | Yes (deep links to source) | No (aggregated data only) | No | No |
| API access | Yes (planned) | Dashboard only (no public API) | API available (per-call pricing) | API available |
| Minimum price | €99/month | ~€300/month | Per-valuation (€2-5) | Enterprise licensing |
| Arbitrage analysis | Native (cross-border is core) | Available but not primary focus | Not available | Not available |

**CARDEX's moat:** Nobody else offers real-time cross-border asking price comparison at the individual listing level with links to the source listing. Indicata has broader coverage but shows aggregated data. DAT/Schwacke gives valuations, not market observations. CARDEX shows what is actually for sale, right now, at what price, where.

---

## 7. Data Limitations — Honest Disclosure

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| Asking price ≠ transaction price | CARDEX shows what dealers ask, not what they actually close at. Typical discount: 5-15%. | Disclose clearly. Position as "market asking intelligence" not "transaction data." |
| Coverage gaps in CH and BE | Smaller portal ecosystems, fewer listings. | State coverage honestly per country. Improve over time. |
| T3 portals may have stale data | DataDome-protected portals refresh slower (48-72h). | Show `last_updated` per listing. Don't claim real-time for T3 sources. |
| No private seller data | CARDEX indexes dealer listings only. Private sales (~40% of market) are excluded. | Position as B2B/dealer intelligence tool. Private seller data is a separate product. |
| Currency conversion fluctuation | CHF prices converted at ECB daily rate — not real-time. | Show original price + conversion rate used. |

---

## 8. Go-To-Market — First 10 Customers

This is not a marketing strategy (that was correctly rejected in the audit). This is a tactical list.

**Target segment:** Multi-brand used-car dealers in NRW (Nordrhein-Westfalen), Germany — the densest used-car market in Europe.

**Approach:**
1. Generate 5 sample PDF reports: one per major segment (BMW 3 Series, VW Golf, Mercedes C-Class, Audi A4, Peugeot 308) with DE + 3 neighboring countries pricing comparison
2. Identify 20 multi-brand dealers in NRW via the CARDEX discovery pipeline (Family A: Handelsregister, Family H: OEM locators)
3. Send cold email with sample report attached. Subject: "[Make] Pricing Intelligence — Germany vs. France, Spain, Netherlands"
4. Follow up once. If interested → demo call → free trial API access → paid subscription
5. If 0 of 20 respond: the product hypothesis is wrong. Pivot or die.

**Cost of this test: €0.** The data exists. The reports can be generated. The emails can be sent. The only cost is time.

---

*This document defines CARDEX Pricing Intelligence as a product, not as a technical capability. The data foundation (1.55M listings, 84+ portals, 20 validators) exists. The delivery layer (API, reports) requires implementation. The market hypothesis (dealers will pay €99-249/month for cross-border pricing intelligence) requires validation with real prospects. Everything described here is achievable by a single operator with €300/month budget.*
