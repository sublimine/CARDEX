# CARDEX — Automotive Data Intelligence: Market Knowledge Base

**Version:** 1.0
**Date:** 2026-06-05
**Classification:** Internal — Strategic
**Purpose:** Consolidated knowledge base of the European automotive data intelligence market. Who buys vehicle data, why, how much they pay, and where CARDEX fits.

---

## 1. The European Used-Vehicle Market — Scale

The European used-car market is one of the largest and most fragmented B2B markets on the continent. Key numbers:

| Metric | Value | Source context |
|--------|-------|---------------|
| Used cars sold in EU annually | ~30 million units | Pre-owned transactions across EU-27 |
| Used car market value (EU) | ~€300-400 billion annually | Average transaction price ~€12,000-15,000 |
| Cross-border used car transactions | ~3-4 million/year | Primarily DE→ES, DE→PL, NL→BE, FR→BE corridors |
| Active dealers in CARDEX's 6 countries | ~150,000-200,000 estimated | Including multi-brand, franchise, independent |
| Vehicles listed online at any given time | ~8-12 million across major portals | CARDEX indexes ~1.55M (partial but growing) |

**The data layer that sits on top of this market — vehicle data intelligence — is a separate industry.** Companies that provide pricing, valuation, market analytics, vehicle history, and risk scoring collectively generate billions in revenue across Europe.

---

## 2. Who Buys Vehicle Data (and How Much They Pay)

### 2.1 Buyer Segments

| Segment | What they need | How they use it | Willingness to pay |
|---------|---------------|-----------------|---------------------|
| **Used-car dealers** (independent) | Market pricing, sourcing intelligence, competitive monitoring | Price their inventory, find underpriced sourcing opportunities, track competitors | €50-300/month per location |
| **Dealer groups** (multi-location) | All of the above + portfolio analytics, inventory optimization | Centralized pricing decisions, stock rebalancing across locations | €500-5,000/month depending on scale |
| **Remarketing / auction houses** | Real-time market benchmarks, liquidation pricing | Set reserve prices, advise consignors, predict auction outcomes | €2,000-20,000/month (enterprise contracts) |
| **Fleet managers** | Residual value forecasting, optimal disposal timing | Decide when to delist vehicles, which channel to sell through | €1,000-10,000/month per fleet |
| **OEM captive finance** | Residual value models for leasing | Set lease terms, manage end-of-lease exposure | €10,000-100,000/year (enterprise) |
| **Insurance companies** | Total loss valuation, replacement value | Settle claims, assess risk | €10,000-50,000/year (data feeds) |
| **Banks / auto lenders** | Collateral valuation, LTV calculation | Approve loans, assess risk | €5,000-50,000/year |
| **Government / regulators** | Market monitoring, tax assessment, emissions compliance | Policy, taxation, environmental regulation | Public procurement budgets |

### 2.2 Revenue Concentration

The automotive data intelligence market in Europe is concentrated. A small number of players capture the majority of revenue:

| Player | Revenue estimate | Primary product | Pricing model |
|--------|-----------------|-----------------|---------------|
| **Eurotax (Autovista Group)** | ~€200-300M/year (group) | Vehicle valuation, market analytics | Enterprise licensing, per-query |
| **DAT Group** | ~€100-150M/year | Schwacke valuations (DE standard), repair cost data | Per-valuation (€2-5), enterprise contracts |
| **Indicata (Autorola)** | Part of Autorola (~€500M group revenue) | Market Watch dashboard, stock management | €300-600/month per dealer |
| **TecAlliance** | ~€400M/year (group) | Technical data (parts, repair info), vehicle identification | Enterprise licensing |
| **carVertical / CARFAX Europe** | ~€30-50M/year | Vehicle history reports | Per-report (€10-30 consumer, volume B2B) |

**CARDEX's addressable niche:** The gap between Indicata (aggregated analytics, €300-600/month) and nothing. Dealers who want market pricing intelligence but can't justify €300+/month, or who want cross-border arbitrage data that Indicata doesn't emphasize.

---

## 3. The Data Value Chain

Vehicle data flows through a value chain from raw sources to actionable intelligence:

```
RAW SOURCES                    AGGREGATION              ANALYTICS                VALUE DELIVERY
─────────────                  ───────────              ─────────                ──────────────
Portal listings ──┐
                  │
Auction results ──┤
                  ├──→ Data collection ──→ Normalization ──→ Pricing models ──→ Dealer dashboards
OEM feeds ────────┤    & dedup            & enrichment      & forecasting       API feeds
                  │                                                              Reports
Registration data ┤                                                              Alerts
                  │
Vehicle history ──┘
```

**Where CARDEX sits:** Stages 1-3 (raw sources → aggregation → partial analytics). The raw data from 84+ portals is collected and normalized. The pricing analytics capability is built but not yet productized. The delivery layer (API, dashboards, reports) is the remaining work.

**What CARDEX does NOT have (and doesn't need for MVP):**
- Auction transaction data (would require partnerships with BCA, ADESA, Manheim)
- OEM registration feeds (would require OEM relationships)
- Vehicle history data (would require access to TÜV/DEKRA/MOT databases)
- Repair cost data (TecAlliance's domain)

---

## 4. Competitive Landscape — Detailed

### 4.1 Direct Competitors (Pricing Intelligence)

**Indicata (Autorola subsidiary)**
- **What they do:** Real-time used-vehicle market analytics. The "Market Watch" dashboard shows pricing trends by make/model/age across 18 European markets.
- **Pricing:** €300-600/month per dealer location. Enterprise custom pricing.
- **Strengths:** 18-country coverage, backed by Autorola's auction transaction data (not just asking prices), established relationships with OEMs and large dealer groups, 15+ years in market.
- **Weaknesses:** Dashboard-only (no public API). Aggregated data (cannot see individual listings). Expensive for small independent dealers. Data is largely auction-based, which lags retail market by 2-4 weeks.
- **CARDEX positioning vs Indicata:** CARDEX offers real-time retail asking prices (not auction data), individual listing visibility with source links, and cross-border arbitrage as a primary feature — at 1/3 to 1/2 the price. CARDEX is weaker on country coverage (6 vs 18) and lacks auction data depth.

**DAT/Schwacke (DE market standard)**
- **What they do:** Vehicle valuations ("Schwacke-Wert" is the standard in German automotive trade). Per-vehicle valuation based on proprietary models calibrated with dealer/auction data.
- **Pricing:** Per-valuation (€2-5 for standard, more for detailed). Monthly subscriptions for high-volume users.
- **Strengths:** DE market standard — banks, insurers, and dealers all use Schwacke as reference. Deep historical data. Expert-calibrated models.
- **Weaknesses:** Per-valuation pricing is expensive at volume. Focused on DE, limited cross-border. Valuation model ≠ market observation (the model says what a car "should" be worth, not what it's actually listed at).
- **CARDEX positioning vs DAT:** Complementary, not competitive. DAT tells you the theoretical value; CARDEX tells you the actual market. A dealer checking a Schwacke valuation of €22,000 also wants to know that 15 comparable cars are currently listed at €20,500-24,000.

**Eurotax (Autovista Group)**
- **What they do:** Pan-European vehicle valuation and market intelligence. Used by OEMs, fleet companies, insurers, and banks across EU.
- **Pricing:** Enterprise licensing. Typically €10,000-100,000/year depending on data access level.
- **Strengths:** Broadest coverage (30+ countries). Used by major OEMs for residual value setting. Trusted by financial institutions.
- **Weaknesses:** Enterprise pricing excludes small dealers entirely. Slow update cycles (monthly/quarterly). Not accessible to the SME dealer market.
- **CARDEX positioning vs Eurotax:** Different market segment entirely. Eurotax serves enterprises; CARDEX can serve the SME dealer that Eurotax prices out.

### 4.2 Adjacent Players

**OPENLANE (formerly KAR Global/ADESA Europe)**
- B2B vehicle remarketing platform (digital auctions). Post-acquisition of TradePlace, they operate the largest B2B wholesale channel in Europe.
- Not a data intelligence company, but their transaction data is a valuable dataset for market pricing.
- CARDEX opportunity: OPENLANE's data is captive to their platform. CARDEX provides open-market intelligence from retail listings — a different data perspective.

**AUTO1 Group (wirkaufendeinauto.de, Autohero)**
- Europe's largest digital automotive platform (public company, market cap >€2B). Processes ~600K vehicles/year.
- Their internal data team has world-class pricing intelligence — but it's proprietary and captive.
- CARDEX opportunity: AUTO1's publicly listed inventory on Autohero is one of CARDEX's data sources. Their market behavior (pricing, inventory mix) is observable signal.

**CarOnSale**
- B2B auction startup (DE, NL, BE). Series A/B funded. Commission-per-transaction model.
- Relevant as benchmark: investors have validated that B2B vehicle marketplace + data is a fundable thesis.
- CARDEX opportunity: CarOnSale participants may want independent market pricing to assess whether auction prices are fair.

### 4.3 Indirect Competitors / Infrastructure Players

| Player | What they do | Relationship to CARDEX |
|--------|-------------|----------------------|
| **TecAlliance** | Technical vehicle data (parts catalogs, repair info) | No overlap. Different data domain. |
| **FleetLogistics** | Fleet management, procurement | Potential customer for CARDEX data |
| **Jato Dynamics** | New car pricing and specification data | Adjacent — CARDEX focuses on used |
| **Glass's (Autovista)** | UK vehicle valuations | Geographic overlap with CH/BE but primarily UK |
| **CAP HPI (Solera)** | UK vehicle data, history checks | Minimal overlap with CARDEX's EU focus |

---

## 5. Market Sizing — Realistic TAM for CARDEX

### 5.1 Bottom-Up TAM

| Segment | Estimated target count in CARDEX's 6 countries | ARPA (annual) | Segment TAM |
|---------|------------------------------------------------|---------------|-------------|
| Independent dealers (€99/mo tier) | ~100,000 addressable, 1% penetration realistic | €1,188 | €119M potential, €1.2M at 1% |
| Dealer groups (€249/mo tier) | ~5,000, 2% penetration | €2,988 | €14.9M potential, €300K at 2% |
| Fleet managers (€249/mo tier) | ~2,000, 1% penetration | €2,988 | €6M potential, €60K at 1% |
| Remarketing/auctions (enterprise) | ~50, 5% | €24,000 | €1.2M potential, €60K at 5% |

**Realistic year-1 target:** €5K-20K ARR (4-15 paying customers). Not €1M. Not €100K. Find 10 customers who pay €99-249/month. That's the entire goal.

### 5.2 Why This TAM is Realistic

- The market exists and is validated by Indicata, DAT, and Eurotax collectively generating hundreds of millions in revenue
- The underserved segment is small independent dealers who cannot afford €300+/month for Indicata or per-query DAT pricing
- Cross-border arbitrage is a real, daily pain point — dealers in ES, NL, and BE actively source from DE because price differentials are 5-15% on popular models
- No existing product offers individual-listing-level cross-border comparison at €99/month

### 5.3 Why This TAM Might Be Wrong

- Small independent dealers may not pay for data at all (they rely on intuition, mobile.de browsing, and word-of-mouth)
- The value proposition may not be strong enough vs. simply browsing AutoScout24 manually
- Cross-border sourcing involves logistics, paperwork, and risk that data alone doesn't solve
- CARDEX's data quality on some portals may not meet professional-grade requirements

**The only way to know: test with 20 dealers.** See D4_PRICING_INTELLIGENCE.md §8.

---

## 6. Data Acquisition Landscape

Understanding how competitors acquire their data:

| Data type | How incumbents get it | How CARDEX gets it | CARDEX advantage/disadvantage |
|-----------|----------------------|-------------------|-------------------------------|
| Retail asking prices | Portal partnerships (Indicata), manual surveys (DAT) | Web scraping of 84+ portals | Advantage: broader portal coverage, more real-time. Disadvantage: asking ≠ transaction, legal risk of scraping |
| Auction transaction prices | Own auction platforms (Autorola, OPENLANE) | Not available | Major gap — CARDEX has no auction data |
| OEM registration data | Direct OEM contracts (Eurotax, Jato) | Not available | Major gap — registration data shows actual transactions |
| Vehicle history | Government databases (TÜV, DEKRA, MOT) | Not available | Not needed for pricing intelligence |
| Technical specs | TecDoc, manufacturer feeds | Not primary focus | Not needed for pricing intelligence |

**CARDEX's data advantage is narrow but real:** Real-time retail asking prices from 84+ portals, cross-border, at individual listing granularity. No competitor offers this combination at CARDEX's price point.

**CARDEX's data disadvantage:** No transaction data. Asking prices are a proxy for market value, not the actual price a vehicle sells for. This must be disclosed honestly to customers.

---

## 7. Regulatory and Legal Environment

### 7.1 Web Scraping Legality in the EU

- **No EU-wide prohibition on web scraping of publicly available data.** The CJEU and national courts have generally allowed scraping of public data for competitive intelligence purposes, subject to GDPR compliance and respect for website terms.
- **Key precedent:** hiQ Labs v. LinkedIn (US, but influential in EU thinking) — scraping of public profiles is not unauthorized access.
- **Risk factors:** Terms of service prohibitions (enforceable via contract law, not criminal law), GDPR for any personal data encountered, database directive (sui generis right for database creators in some EU states).
- **CARDEX mitigation:** robots.txt compliance, rate limiting, GDPR framework (D1), C&D response protocol. See D1_GDPR_COMPLIANCE.md for full analysis.

### 7.2 Data Act (EU, effective 2025-09-12)

The EU Data Act may affect how vehicle data is shared and accessed. Key provisions:
- Users (vehicle owners/operators) have the right to access data generated by their connected vehicles
- Third parties can access vehicle data with user consent
- **Impact on CARDEX:** Minimal in the short term — CARDEX scrapes publicly listed sales data, not connected vehicle data. In the long term, the Data Act may create new data sources (OEM-shared data) that CARDEX could leverage.

### 7.3 Digital Markets Act (DMA)

Large portal operators designated as "gatekeepers" (potentially AutoScout24 parent, mobile.de parent Scout24) may face data portability obligations. This could create legal pathways for accessing portal data that currently requires scraping.

---

## 8. Technology Trends Affecting the Market

| Trend | Timeline | Impact on CARDEX |
|-------|----------|------------------|
| **AI-powered valuation** | Now | Competitors integrating ML for price prediction. CARDEX has Chronos forecasting (experimental). |
| **Connected vehicle data** | 2-5 years | OEMs sharing vehicle telemetry could create richer datasets. New data source, not threat. |
| **EV transition** | Ongoing | Changes depreciation patterns. EV battery health becomes critical data point CARDEX doesn't have. |
| **Consolidation of portals** | Ongoing | Adevinta (owner of mobile.de, leboncoin, marktplaats) consolidating. Fewer portals = easier scraping but higher C&D risk. |
| **Anti-bot arms race** | Continuous | Increasing sophistication of detection. CARDEX's anti-detection stack (D2) must evolve. |
| **Open banking / PSD2 in automotive** | 2-4 years | May create transparent financing data. Not directly relevant yet. |

---

## 9. Strategic Implications for CARDEX

### 9.1 Where CARDEX Should Compete

**Market segment:** SME dealers and cross-border traders who need market pricing intelligence but are priced out by Indicata/DAT/Eurotax.

**Geography:** Start with DE (largest market, most data) + one comparison country (ES or NL — largest price differentials). Expand from there.

**Product form:** API-first (for integrators and tech-savvy dealers) + sample PDF reports (for sales demos and non-technical dealers).

### 9.2 Where CARDEX Should NOT Compete

- **Enterprise valuations** (Eurotax/DAT territory) — requires regulatory trust, auditor acceptance, and decades of calibration data
- **Vehicle history** (carVertical/CARFAX territory) — requires government database access
- **Auction platforms** (OPENLANE/CarOnSale territory) — requires marketplace network effects and dealer relationships
- **New car pricing** (Jato Dynamics territory) — requires OEM relationships

### 9.3 The Path to First Revenue

```
Current state:   1.55M listings indexed, 20 validators, pricing analytics capability
                 Revenue: €0. Customers: 0. API: not deployed.

Step 1 (week 1):  Generate 5 sample PDF reports for popular segments
Step 2 (week 2):  Identify 20 target dealers in NRW (Germany)
Step 3 (week 2):  Send cold emails with sample reports
Step 4 (week 3):  Follow up. If interest: demo call.
Step 5 (week 4):  Deploy minimal API (Go HTTP handlers + Stripe billing)
Step 6 (month 2): Onboard first 2-3 paying customers
Step 7 (month 3): Iterate based on customer feedback

Total cost: €0 additional (existing infrastructure handles everything)
Decision point: If 0 of 20 dealers respond → product hypothesis is wrong → pivot
```

---

*This document consolidates automotive data market intelligence for CARDEX strategic decision-making. All market size estimates are order-of-magnitude approximations based on public information and industry analysis, not proprietary data. Competitive pricing and feature comparisons are based on publicly available information and may be outdated — verify before using in external communications.*
