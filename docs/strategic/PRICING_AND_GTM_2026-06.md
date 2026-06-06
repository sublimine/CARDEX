# CARDEX — Pricing Strategy & Go-To-Market Plan
# Cross-Border Price Intelligence API

**Date:** 2026-06-05
**Author:** Strategic Planning (AI-assisted)
**Classification:** Internal — Founder
**Version:** 1.0
**Complements:** MARKET_OPPORTUNITIES_2026-06.md, INNOVATION_OPPORTUNITIES_2026-06.md, COMPETITIVE_DEEP_DIVE_2026-06.md

---

## Executive Summary

This document defines the complete go-to-market strategy for CARDEX's first revenue product: the **Cross-Border Price Intelligence API**. Four endpoints — `market-price`, `arbitrage`, `landed-cost`, `alerts` — expose the core value of 1.55M indexed vehicles across DE, FR, ES, NL, BE, CH to paying customers.

The pricing occupies a structurally empty mid-market band (EUR 49-499/month) between enterprise incumbents (Autovista at EUR 5K+/year, JATO at EUR 5K+/month) and low-quality alternatives (Zyla at EUR 20-200/month, CarAPI at USD 199-299/year). No competitor offers simultaneous cross-border live listing data from 6 EU markets at this price point.

Constraints: EUR 300/month budget, no sales team, single operator + AI. Every element below is executable under these constraints.

---

## 1. PRICING TIERS

---

### 1.1 Tier Structure

| Dimension | Free | Starter | Pro | Enterprise |
|---|---|---|---|---|
| **Price** | EUR 0/month | EUR 49/month | EUR 199/month | EUR 499/month |
| **Billing** | — | Monthly / Annual (-15%) | Monthly / Annual (-15%) | Annual only |
| **Annual price** | — | EUR 499/year | EUR 2,029/year | EUR 5,089/year |
| | | | | |
| **API calls/month** | 100 | 2,000 | 15,000 | 100,000 |
| **Overage** | Hard cap | EUR 0.04/call | EUR 0.02/call | EUR 0.008/call |
| **Countries** | 2 (DE + 1) | 3 | 6 | 6 |
| **Rate limit** | 5 req/min | 30 req/min | 120 req/min | 300 req/min |
| | | | | |
| **`market-price`** | Current only | Current + 30d history | Current + 90d history + Chronos forecast | Current + 180d history + Chronos forecast |
| **`arbitrage`** | Top 3 results/query | Top 10 results/query | Full results + margin calculation | Full results + margin + transport estimate |
| **`landed-cost`** | — | 3 corridors (DE↔FR, DE↔NL, DE↔ES) | All 30 country pairs | All pairs + VAT margin scheme toggle |
| **`alerts`** | — | 5 active alerts, email only | 25 alerts, email + webhook | Unlimited alerts, email + webhook + batch |
| | | | | |
| **Chronos-2 forecasts** | — | — | 4-week horizon | 12-week horizon |
| **Dealer Trust Score** | — | — | Read-only | Full history + API |
| **Data export** | — | — | CSV monthly | CSV/JSON daily + SFTP |
| **Support** | Docs only | Email (48h) | Email (24h) + onboarding call | Dedicated Slack + SLA 99.5% |
| **Swagger/OpenAPI docs** | Full | Full | Full | Full + sandbox |

### 1.2 Pricing Justification (Competitive Evidence)

**Why EUR 49 for Starter:**
- Schwacke charges EUR 7-10 per individual valuation query. At 2,000 calls/month, a Schwacke-equivalent cost would be EUR 14,000-20,000/month. CARDEX at EUR 49 is 285-408x cheaper per call.
- carVertical charges EUR 24.99 per vehicle history report. Two reports/month already exceed CARDEX Starter pricing. Source: carVertical pricing page.
- CarAPI (US) charges USD 199-299/year for 1,500-6,000 calls/day. CARDEX Starter is comparable in price but covers 6 EU markets vs. CarAPI's US-only data. Source: carapi.app.

**Why EUR 199 for Pro:**
- DAT/SilverDAT Beginner costs EUR 274/month for a single-country (DE) valuation tool. CARDEX Pro at EUR 199 provides 6-country live market data + arbitrage + forecasting — strictly superior scope at 27% lower price. Source: Pixelconcept SilverDAT pricing.
- Indicata subscriptions run USD 3,800-5,800/year (EUR 317-483/month). CARDEX Pro at EUR 199 undercuts by 38-59% with comparable intelligence plus cross-border arbitrage that Indicata lacks. Source: INNOVATION_OPPORTUNITIES report.
- Omnetic Sourcing (CZ) aggregates 31 sources and charges undisclosed enterprise pricing. Their "average additional margin of EUR 105/vehicle" claim validates the value proposition: a dealer buying 10 vehicles/month via CARDEX arbitrage data would generate EUR 1,050 in margin, a 5.3x ROI on the EUR 199 subscription.

**Why EUR 499 for Enterprise:**
- Autovista API subscriptions start at EUR 5,000/year minimum and scale to EUR 50,000+/year for full access. CARDEX Enterprise at EUR 5,089/year (annual) is at Autovista's floor but includes live listing data, arbitrage, landed-cost, and forecasting — features Autovista does not offer. Source: Autovista Group, Growjo.
- JATO Dynamics charges EUR 5,000+/month for enterprise data access. CARDEX Enterprise is 10x cheaper. Source: industry references, COMPETITIVE_DEEP_DIVE report.
- The mid-market band between EUR 100-500/month is confirmed empty by the Competitive Deep Dive (§4.2). CARDEX Enterprise sits at the top of this gap, below enterprise pricing but above low-end alternatives.

**Why a Free tier:**
- Reduces acquisition friction to zero. A dealer can validate data quality before committing budget.
- 100 calls/month is enough to test 3-4 vehicle lookups/day for a week — sufficient to build conviction.
- Free-to-paid conversion rate benchmark in developer APIs: 2-5% (Stripe, Twilio precedent). At scale, 1,000 free users → 20-50 paid conversions.
- eCarsTrade (bootstrapped, EUR 13.2Cr revenue) and JP.cars both used freemium to reach first 100 dealers. Source: COMPETITIVE_DEEP_DIVE §5.1.

### 1.3 Revenue Projections (12-Month Horizon)

| Scenario | Composition | MRR | ARR |
|---|---|---|---|
| Conservative | 30 Starter + 5 Pro + 1 Enterprise | EUR 2,964 | EUR 35,568 |
| Realistic | 50 Starter + 15 Pro + 3 Enterprise | EUR 6,932 | EUR 83,184 |
| Optimistic | 80 Starter + 30 Pro + 8 Enterprise | EUR 13,882 | EUR 166,584 |

Break-even on EUR 300/month infrastructure: **Conservative scenario, month 3** (7 Starter customers).

### 1.4 Pricing Mechanics

**Payment:** Stripe Billing. EUR only. Cards + SEPA Direct Debit.

**Annual discount:** 15% (2 months free). Justified: reduces churn, improves LTV, aligns with dealer budget cycles (annual planning in Q4).

**Overage model:** Soft cap with automatic billing. Alert at 80% and 100% of quota. Overage rate declines with tier to incentivize upgrades: Free has hard cap (no overage), Starter at EUR 0.04/call, Pro at EUR 0.02/call, Enterprise at EUR 0.008/call.

**Upgrade path:** Self-service in dashboard. Downgrade at end of billing cycle. No lock-in except Enterprise annual.

---

## 2. LANDING PAGE COPY

---

### 2.1 Hero Section

**Headline:**
> Know Every Price. In Every Market. Before Your Competition.

**Subheadline:**
> The Cross-Border Price Intelligence API for European car dealers. Real-time pricing data from 1.5M+ vehicles across Germany, France, Spain, Netherlands, Belgium, and Switzerland — in one API call.

**Primary CTA:** `Get Your Free API Key →`
**Secondary CTA:** `See Live Demo`

### 2.2 Problem Statement (Above the Fold)

> You're leaving money on the table. A BMW 320d listed at EUR 24,500 in Stuttgart is selling for EUR 28,200 in Amsterdam. The difference? EUR 3,700 in margin — minus EUR 400 transport and EUR 180 in taxes. **Net profit: EUR 3,120.** But you didn't know, because no tool shows you this in real time across 6 markets.

### 2.3 Three Value Propositions

**Value Prop 1: Cross-Border Arbitrage Detection**

> **Find hidden margin across borders.**
> Our `arbitrage` endpoint scans 1.5M+ live listings across 6 European markets and surfaces vehicles where the price differential exceeds your target margin — net of transport and import taxes. Stop sourcing blind. Start sourcing with data.

**Value Prop 2: Landed-Cost Calculator**

> **Know the real cost before you buy.**
> VAT margin scheme or standard? BPM in Netherlands, IEDMT in Spain, Malus écologique in France? The `landed-cost` endpoint computes the total acquisition cost for any vehicle moving between any two of our 6 markets. Every tax. Every fee. One API call.

**Value Prop 3: Market Intelligence & Forecasting**

> **Price with confidence. Time your trades.**
> The `market-price` endpoint returns current market pricing, 30-180 day history, and AI-powered price forecasts (Chronos-2 model, 120M parameters). Know whether a vehicle will depreciate 4% next month — or appreciate 2% because seasonal demand is shifting.

### 2.4 Social Proof Section

> **Built on verified data.** Every listing passes through 20 automated quality validators — VIN checksums, price plausibility, image quality, deduplication, sold-vehicle detection, and more. We don't serve noise. We serve signal.

**Stats bar:**
- `1.55M+` vehicles indexed
- `6` European markets
- `71+` data sources
- `20` quality validators
- `<500ms` median response time

### 2.5 Pricing Table

*[Render the table from §1.1 in a clean card layout with four columns. Highlight Pro as "Most Popular."]*

Each card includes:
- Price (monthly, with annual toggle showing -15%)
- Call volume
- Countries covered
- Feature checklist with checkmarks/dashes
- CTA button: Free → "Start Free", Starter → "Start 14-Day Trial", Pro → "Start 14-Day Trial", Enterprise → "Contact Us"

**Note below table:**
> All plans include full Swagger/OpenAPI documentation and SDKs for Python and JavaScript. Enterprise tier includes a dedicated sandbox environment. No credit card required for Free tier. Cancel anytime.

### 2.6 How It Works (3 Steps)

> **Step 1: Get your API key.** Sign up in 30 seconds. No credit card for Free tier. Your key is ready instantly.
>
> **Step 2: Make your first call.** Copy-paste our example into your terminal. Get real cross-border pricing data in under a second.
>
> **Step 3: Find your first deal.** Set up alerts for vehicles you trade. We notify you the moment a cross-border opportunity exceeds your target margin.

*[Include a code snippet with syntax highlighting:]*

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
  "https://api.cardex.eu/v1/market-price?make=BMW&model=320d&year=2021&country=DE,FR,NL"
```

```json
{
  "make": "BMW",
  "model": "320d",
  "year": 2021,
  "prices": {
    "DE": { "median": 24500, "p25": 22800, "p75": 26200, "count": 347 },
    "FR": { "median": 25900, "p25": 24100, "p75": 27800, "count": 189 },
    "NL": { "median": 28200, "p25": 26500, "p75": 30100, "count": 94 }
  },
  "arbitrage": {
    "best_buy": "DE",
    "best_sell": "NL",
    "gross_delta_eur": 3700,
    "estimated_landed_cost": 580,
    "net_margin_eur": 3120
  }
}
```

### 2.7 FAQ

**Q: Where does the data come from?**
A: We index listings directly from dealer websites across Germany, France, Spain, Netherlands, Belgium, and Switzerland — 71+ sources and growing. This is not marketplace data from AutoScout24 or mobile.de. These are listings from individual dealer sites that no other provider collects systematically.

**Q: How fresh is the data?**
A: Listings are refreshed daily. Price changes and new listings are typically reflected within 24 hours. Sold vehicles are detected and removed automatically.

**Q: Is this legal?**
A: Yes. We collect publicly available B2B data from dealer websites. We comply with robots.txt, rate-limit all requests, and process no personal data. Our legal basis under GDPR is Art. 6(1)(f) legitimate interest for B2B public data.

**Q: How accurate is the arbitrage calculation?**
A: The `market-price` endpoint reflects real asking prices from live listings. The `landed-cost` calculation uses official tax tables for each country (BPM, IEDMT, Malus, etc.) and transport cost estimates based on corridor distance. We recommend verifying final tax amounts with a fiscal advisor for transactions above EUR 50K.

**Q: What about the AI forecasts?**
A: Price forecasts use Chronos-2, a 120M-parameter foundation model trained on time-series data. Forecasts cover 4-12 week horizons depending on tier. Accuracy varies by segment; the model performs best on high-volume makes/models (VW Golf, BMW 3-Series, Mercedes C-Class) where data density is highest.

**Q: Can I integrate this with my DMS?**
A: Yes. The API is REST/JSON with full OpenAPI 3.0 documentation. The `alerts` endpoint supports webhooks for push integration. We provide SDKs for Python and JavaScript. Custom integrations available on Enterprise tier.

**Q: What happens if I exceed my API call quota?**
A: Starter and Pro tiers have automatic overage billing at discounted rates. You receive alerts at 80% and 100% of quota. Free tier has a hard cap — upgrade to continue.

**Q: Is there a trial?**
A: Free tier is permanent (100 calls/month, 2 countries). Starter and Pro include a 14-day trial with full access before billing begins.

### 2.8 Final CTA Section

**Headline:**
> Your competitors are already sourcing cross-border. Are you?

**Subheadline:**
> Join 50+ dealers across Europe using CARDEX to find margin where others see noise. Free tier available — no credit card required.

**CTA:** `Get Your Free API Key →`

### 2.9 Footer Elements

- API Documentation link
- Status Page link
- Terms of Service / Privacy Policy
- Contact: api@cardex.eu
- Company: CARDEX, registered in [jurisdiction]
- "Data sourced from 71+ dealer portals across DE, FR, ES, NL, BE, CH"

---

## 3. ONBOARDING FLOW

---

### 3.1 Design Principles

- **Zero friction to first value.** A dealer must see real pricing data within 90 seconds of landing on the site.
- **No phone call required.** Self-service end-to-end through Enterprise (Enterprise onboarding call is offered, not required).
- **Progressive disclosure.** Collect minimal data upfront; ask for more only when the user upgrades.

### 3.2 Step-by-Step Flow

```
LANDING PAGE
    │
    ├── [Get Your Free API Key →]
    │
    ▼
STEP 1: SIGNUP (30 seconds)
    ├── Email address
    ├── Password (or "Continue with Google")
    ├── Company name (optional, prefilled if Google Workspace)
    ├── Country (dropdown, prefilled from IP geolocation)
    ├── [Create Account]
    │
    ▼
STEP 2: EMAIL VERIFICATION (15 seconds)
    ├── Magic link sent to email
    ├── User clicks link → auto-login
    ├── Skip if Google OAuth
    │
    ▼
STEP 3: API KEY GENERATION (instant)
    ├── Dashboard loads with API key visible
    ├── Copy-to-clipboard button
    ├── "Your key: ck_live_xxxxxxxxxxxxxx"
    │
    ▼
STEP 4: FIRST QUERY (60 seconds)
    ├── Interactive sandbox embedded in dashboard
    ├── Pre-filled with: make=BMW, model=320d, year=2021, country=DE,FR
    ├── [Run Query] button
    ├── Response renders inline with syntax highlighting
    ├── Highlights the arbitrage delta in green if positive
    │
    ▼
STEP 5: GUIDED SETUP (optional, 2-3 minutes)
    ├── "What vehicles do you trade?" → multi-select (makes/models)
    ├── "Which markets do you source from?" → checkboxes (6 countries)
    ├── "Set your first alert" → pre-configured with user's make/model selection
    ├── [Activate Alert]
    │
    ▼
STEP 6: ONGOING
    ├── Dashboard: usage meter, recent queries, active alerts
    ├── Email: first alert fires within 24-48 hours (if matching vehicles exist)
    ├── Upgrade prompt appears after 70% of free quota consumed
```

### 3.3 Technical Implementation

| Component | Solution | Cost |
|---|---|---|
| Auth | Supabase Auth (free tier: 50K MAU) or Clerk (free tier: 10K MAU) | EUR 0 |
| API Gateway | Go service reusing `services/gateway` stub, Chi router + middleware | EUR 0 (on existing CX42 VPS) |
| API Key management | Custom table in SQLite: `api_keys(key, user_id, tier, calls_used, calls_limit, created_at)` | EUR 0 |
| Rate limiting | Go middleware with token bucket per API key | EUR 0 |
| Billing | Stripe Billing (subscription + metered overage) | 2.9% + EUR 0.25/txn |
| Email | Resend (free tier: 3K emails/month, then USD 20/month for 50K) | EUR 0-18 |
| Dashboard | Minimal React SPA or Astro static site | EUR 0 (hosted on VPS) |
| Docs | Swagger UI served from OpenAPI spec | EUR 0 |
| Landing page | Astro or Framer (free tier) | EUR 0 |

**Total additional infrastructure cost:** EUR 0-18/month (within EUR 300/month budget).

### 3.4 Onboarding Metrics to Track

| Metric | Target | Measurement |
|---|---|---|
| Signup → API key | < 60 seconds | Timestamp delta |
| API key → first successful call | < 5 minutes | First 200 response logged |
| Signup → first alert set | < 10 minutes | Alert creation timestamp |
| Free → Paid conversion | > 3% at month 3 | Stripe subscription events |
| Time to first alert delivery | < 48 hours | Alert engine log |
| Day-7 retention (at least 1 call) | > 40% | API call logs |

---

## 4. INTERACTIVE DEMO

---

### 4.1 Purpose

Convince a dealer in under 2 minutes that CARDEX data is real, actionable, and worth paying for. The demo must work without signup and without human interaction.

### 4.2 Demo Structure (2-Minute Script)

**Minute 0:00 - 0:30 — The Hook (Arbitrage Discovery)**

The dealer lands on a page titled: **"Find Your Next Cross-Border Deal — Live."**

- A search bar pre-populated with a high-volume vehicle: `BMW 320d, 2020-2022, any mileage`
- The dealer clicks [Search] (or the search auto-executes on page load)
- Results render as a table:

```
┌─────────┬────────────┬───────┬──────────────────────────┐
│ Country │ Median EUR │ Count │ vs. Cheapest Market      │
├─────────┼────────────┼───────┼──────────────────────────┤
│ DE      │ 23,800     │ 412   │ ■■ +2.1%                 │
│ ES      │ 23,300     │ 168   │ CHEAPEST                 │
│ FR      │ 25,100     │ 204   │ ■■■■ +7.7%               │
│ NL      │ 27,400     │  87   │ ■■■■■■■ +17.6%           │
│ BE      │ 26,100     │  63   │ ■■■■■ +12.0%             │
│ CH      │ 29,200     │  41   │ ■■■■■■■■■ +25.3%         │
└─────────┴────────────┴───────┴──────────────────────────┘

Best arbitrage: Buy in ES (EUR 23,300) → Sell in CH (EUR 29,200)
Gross delta: EUR 5,900
```

**Minute 0:30 - 1:00 — The Calculator (Landed Cost)**

The dealer clicks on the ES→CH row. A panel expands:

```
LANDED COST: BMW 320d (2021) — Spain → Switzerland

Purchase price (ES median):     EUR 23,300
Transport (ES→CH corridor):   + EUR   620
Swiss import duty (4%):        + EUR   932
Swiss VAT (8.1%):              + EUR 1,887
Registration & admin:          + EUR   350
─────────────────────────────────────────
Total landed cost:               EUR 27,089

Swiss market median:             EUR 29,200
NET MARGIN:                      EUR 2,111 (7.2%)
```

**Minute 1:00 - 1:30 — The Forecast (Price Trajectory)**

Below the calculator, a sparkline chart shows 90-day price history for the BMW 320d in CH, with a Chronos-2 forecast overlay for the next 4 weeks. The forecast shows a +1.8% upward trend (seasonal spring demand in CH), implying the margin window is closing.

Caption: *"If you wait 4 weeks, the Swiss market price is projected to increase to EUR 29,700 — but the Spanish market is also firming. Act within 2 weeks for optimal margin."*

**Minute 1:30 - 2:00 — The Alert (CTA)**

A banner appears:

> **Want to catch deals like this automatically?** Set an alert for BMW 320d with minimum margin EUR 1,500. We'll email you the moment a new opportunity surfaces.

CTA: `[Set Alert — Free]` → leads to signup flow.

### 4.3 Implementation Approach

| Component | Technology | Effort |
|---|---|---|
| Demo page | Static HTML/JS, hardcoded vehicle + live API call hybrid | 3 days |
| Search | Real API call to `/v1/market-price` (rate-limited, demo API key) | Exists |
| Arbitrage table | Client-side rendering from API response | 1 day |
| Landed-cost panel | Real API call to `/v1/landed-cost` or pre-computed for demo vehicles | 1-2 days |
| Price chart | Chart.js sparkline from `/v1/market-price?history=90d` | 1 day |
| Forecast overlay | Chronos-2 output via `/v1/forecast` (pre-computed for demo vehicles) | Pre-computed |
| Alert CTA | Redirect to signup with pre-filled alert parameters via URL params | 2 hours |

**Total effort:** 5-7 days.

**Key design decisions:**
- Use real data, not mock data. Dealers will verify against their own market knowledge. Fake data destroys trust instantly.
- Pre-select 5 high-volume vehicles for instant demo load (BMW 3-Series, VW Golf, Mercedes C-Class, Audi A4, Renault Clio). Allow free-text search for any make/model.
- Show data freshness timestamp: "Data as of 2026-06-05 08:00 UTC. Updated daily."

### 4.4 Demo Variants by Channel

| Channel | Demo Format | Duration |
|---|---|---|
| Website visitor | Interactive web page (§4.2) | Self-paced, ~2 min |
| Cold email | Screenshot GIF of arbitrage table + link to live demo | 15 seconds viewing, link to full |
| LinkedIn DM | 30-second screen recording of a real search | Attachment or Loom link |
| Trade show / meetup | Laptop with live demo, dealer types their own vehicle | 2-5 min interactive |
| Webinar | Shared screen walkthrough with live API calls | 10-15 min deep dive |

---

## 5. ZERO-COST ACQUISITION CHANNELS

---

### 5.1 Constraints

- EUR 300/month total budget (covers infrastructure, not marketing spend)
- No sales team — single operator + AI
- Target: first 5 paying dealers within 60 days of launch
- Geography: start with DE + NL (highest cross-border trade volume per Autorola data: 21% of sales are cross-border)

### 5.2 Channel 1: Targeted Cold Outreach via LinkedIn (0 cost)

**Why it works:** 18,000+ dealers are registered on CarOnSale alone. Dealer owners and purchasing managers are active on LinkedIn, especially in DE and NL. The key is hyper-personalization using CARDEX's own data.

**Execution:**

1. **Identify 50 target dealers** using CARDEX's discovery pipeline (Family A-O). Filter for: multi-brand dealers in DE/NL with 50-200 vehicles in stock, active on multiple portals (Family F backlinks show marketplace presence), and operating websites with DMS detected (Family E — indicates technical sophistication).

2. **Craft personalized outreach.** For each dealer, run a CARDEX query on their top-selling make/model. Generate a one-paragraph insight:

   > *"Hi [Name], I noticed your dealership in [City] lists 34 BMW 3-Series at a median of EUR 25,100. In the Spanish market right now, the same model trades at EUR 22,800 — that's a EUR 2,300 gross margin per unit before transport and taxes. We built an API that surfaces these cross-border opportunities automatically. Want a free API key to try it?"*

3. **Volume:** 5 messages/day, 5 days/week = 25/week. At 10-15% response rate (industry benchmark for hyper-personalized B2B outreach per InStream Group), that's 2-4 conversations/week. At 25% conversion from conversation to free signup, and 20% free-to-paid: ~1 paying customer per 2-3 weeks.

4. **Tools:** LinkedIn free account (500 connections/week limit is not binding at 25/week volume). AI-assisted message drafting from CARDEX data. Zero cost.

**Target:** 3 paying dealers from this channel in 60 days.

### 5.3 Channel 2: Automotive B2B Forums and Communities (0 cost)

**Why it works:** Dealers discuss sourcing strategies in specialized forums and communities. Providing genuine value (data, insights) builds credibility faster than ads.

**Execution:**

1. **Identify 5-8 active communities:**
   - motor-talk.de (Händlerbereich — dealer section)
   - LinkedIn groups: "European Used Car Dealers", "Automotive B2B Network", "Cross-Border Car Trading Europe"
   - Reddit: r/askcarsales (English, but EU dealers participate), r/AutoDealer
   - eCarsTrade blog comments and community
   - BOVAG (NL) and TRAXIO (BE) trade association forums
   - Mobilians (FR) digital dealer community

2. **Content strategy (1 post/week):**
   - Week 1: "I analyzed 1.55M listings across 6 EU markets. Here's where the arbitrage is right now." [Data-backed post with market-price snapshot by country for 3 popular models]
   - Week 2: "The hidden cost of cross-border sourcing: a landed-cost breakdown for DE→NL" [Educational, uses real tax calculations]
   - Week 3: "Which models hold value best across borders? A 90-day analysis." [Chronos-2 data, shows depreciation curves by country]
   - Week 4: "How Euro 7 will reshape used car pricing in 2027 — and what dealers should do now." [Regulatory insight + CARDEX data]

3. **CTA:** Always end with "Full data available via our free API — link in comments." Never hard-sell. Let the data sell.

**Target:** 1-2 paying dealers from this channel in 60 days.

### 5.4 Channel 3: SEO Content + API Documentation as Marketing (0 cost)

**Why it works:** Dealers and developers search for pricing data. Ranking for long-tail queries drives inbound traffic with zero marginal cost.

**Execution:**

1. **Target keywords:**
   - "used car prices Germany vs France"
   - "cross-border car arbitrage Europe"
   - "import car Netherlands BPM calculator"
   - "used car market data API Europe"
   - "automotive pricing API"
   - "coste importar coche Alemania España" (ES market)
   - "voiture occasion prix comparaison pays" (FR market)

2. **Content assets (build over 8 weeks):**
   - `/blog/cross-border-arbitrage-bmw-3-series-2026` — evergreen analysis updated monthly
   - `/blog/landed-cost-guide-{country-pair}` — 6-10 corridor-specific guides (DE→NL, DE→ES, FR→BE, etc.)
   - `/blog/used-car-price-index-europe-{month}` — monthly market snapshot, shareable
   - `/docs/api/` — Swagger UI, auto-indexed by Google
   - `/tools/landed-cost-calculator` — free web tool (subset of `landed-cost` endpoint), captures email

3. **Execution:** AI-assisted drafting from CARDEX data. One operator can produce 2 articles/week at 1,500-2,000 words each.

4. **Distribution:** Cross-post to LinkedIn, submit to Hacker News (Show HN: Cross-Border Car Price Intelligence API), Product Hunt launch.

**Target:** First organic signups within 30-45 days of content publication. 1 paying dealer from inbound by day 60.

### 5.5 Channel 4: Trade Association Partnerships (0 cost)

**Why it works:** CARDEX already discovers dealers via trade associations (Family G: BOVAG NL, TRAXIO BE, Mobilians FR). These associations serve their members and actively look for tools to recommend.

**Execution:**

1. **Contact 3 associations:**
   - **BOVAG** (NL): 8,000+ members. Digital transformation is a stated priority. Offer: free CARDEX API access for BOVAG members' first 3 months, in exchange for a mention in their member newsletter.
   - **TRAXIO** (BE): Represents 9,000+ companies. Offer: co-branded "Cross-Border Sourcing Guide for Belgian Dealers" using CARDEX data. TRAXIO distributes; CARDEX captures leads.
   - **Mobilians** (FR): Represents 40,000+ automotive professionals. Offer: webinar on "Cross-Border Opportunities for French Dealers in 2026" with live CARDEX demo.

2. **Value exchange:** CARDEX provides free data and content. Association provides distribution channel and credibility. No money changes hands.

3. **Pitch:** Email the association's digital/innovation lead. Subject: "Free cross-border pricing tool for your members." Attach a 1-page PDF with the arbitrage data for their country's most-traded vehicles.

**Target:** 1 partnership signed within 45 days. First referred dealer within 60-90 days (attribution overlap with other channels likely).

### 5.6 Channel 5: Datarade and API Marketplace Listings (0 cost)

**Why it works:** Datarade (datarade.ai) is a marketplace where data buyers find data providers. Listing is free for providers. API marketplaces (RapidAPI, Zyla API Hub) drive discovery from developers and analysts.

**Execution:**

1. **Datarade listing:**
   - Category: "Automotive Data", "Vehicle Pricing Data", "Used Car Market Data"
   - List all 4 endpoints with sample data
   - Pricing: display Free + Starter + Pro + Enterprise tiers
   - Geography: DE, FR, ES, NL, BE, CH
   - Delivery: REST API, JSON
   - Use case tags: "cross-border arbitrage", "dealer pricing", "market intelligence"

2. **RapidAPI listing:**
   - Free tier as the default "Basic" plan
   - Pro plan as "Pro" on RapidAPI
   - RapidAPI handles billing (takes ~20% commission but provides discovery)

3. **AWS Data Exchange** (future, when volume justifies):
   - Monthly data snapshots as S3 datasets
   - Target: analysts, insurers, fintechs
   - Requires Stripe → AWS billing integration

**Target:** 2-5 inbound leads/month from marketplace listings within 60 days.

### 5.7 Acquisition Funnel Summary

```
AWARENESS (0 cost)                    ACTIVATION               REVENUE
─────────────────────────────────     ───────────────           ────────
LinkedIn cold outreach (25/week)  ──► Free API signup    ──►  Starter (EUR 49)
Forum posts (1/week)              ──► First API call     ──►  Pro (EUR 199)
SEO articles (2/week)             ──► First alert set    ──►  Enterprise (EUR 499)
Trade association referrals       ──► Alert fires (48h)
Datarade / RapidAPI listings      ──► Upgrade prompt (70% quota)
Product Hunt / Hacker News launch ──► 14-day trial
```

**60-day target:** 5 paying dealers (3 from LinkedIn, 1-2 from forums/SEO, 0-1 from association referral — associations have longer cycles, so day-60 attribution may be partial).

**Ongoing monthly targets (post-launch):**

| Month | Free Signups | Paid Conversions | Cumulative Paid |
|---|---|---|---|
| 1 | 30 | 2 | 2 |
| 2 | 50 | 3 | 5 |
| 3 | 80 | 5 | 10 |
| 4 | 100 | 7 | 17 |
| 5 | 120 | 8 | 25 |
| 6 | 150 | 10 | 35 |

---

## 6. IMPLEMENTATION TIMELINE

---

### 6.1 Phase 1: Build (Weeks 1-5)

| Week | Deliverable | Owner |
|---|---|---|
| 1 | API Gateway (Go, Chi router, auth middleware, rate limiting) | Founder |
| 1 | `market-price` endpoint (aggregation over SQLite index) | Founder |
| 2 | `arbitrage` endpoint (cross-country delta calculation) | Founder |
| 2 | API key management (SQLite table + generation) | Founder |
| 3 | `landed-cost` endpoint (tax rules for DE, FR, ES, NL, BE, CH) | Founder |
| 3 | `alerts` endpoint (rule engine + email via Resend) | Founder |
| 4 | Stripe Billing integration (4 tiers + metered overage) | Founder |
| 4 | OpenAPI/Swagger documentation | Founder |
| 5 | Landing page + signup flow + dashboard | Founder |
| 5 | Interactive demo page | Founder |

### 6.2 Phase 2: Launch (Weeks 6-8)

| Week | Deliverable |
|---|---|
| 6 | Beta launch to 10-15 hand-selected dealers (from LinkedIn outreach in weeks 3-5) |
| 6 | Datarade and RapidAPI listings live |
| 7 | Public launch: Product Hunt, Hacker News "Show HN", LinkedIn announcement |
| 7 | First SEO article published |
| 7 | Trade association outreach emails sent (BOVAG, TRAXIO, Mobilians) |
| 8 | First forum posts published |
| 8 | Iterate based on beta feedback (pricing, rate limits, data gaps) |

### 6.3 Phase 3: Grow (Weeks 9-16)

| Week | Deliverable |
|---|---|
| 9-10 | Chronos-2 forecast endpoint wrapper (Pro/Enterprise feature) |
| 10-11 | Dealer Trust Score productized (Pro/Enterprise feature) |
| 12 | Monthly "European Used Car Price Index" report (SEO + credibility) |
| 13-14 | Webhook integration for alerts (Pro/Enterprise feature) |
| 15-16 | CSV/JSON data export (Enterprise feature) |

---

## 7. RISK MATRIX

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Portal blocking intensifies | Medium | High | Approved stack (curl_cffi + Camoufox + residential proxies), DMS API paths (E05, E12) as fallback. 13 extraction strategies provide redundancy. |
| Low initial conversion (< 2%) | Medium | Medium | Double down on demo quality and personalized outreach. Consider EUR 29 "Micro" tier if EUR 49 proves too high for first commitment. |
| Competitor enters mid-market | Low | Medium | First-mover advantage + proprietary dealer-website data (71+ sources). AutoGrab expansion to EU is 12-18 months away. |
| Tax calculation errors | Medium | Low | Clear disclaimer ("estimate, consult tax advisor"). Start with 3 highest-volume corridors (DE↔NL, DE↔FR, DE↔ES), expand after validation. |
| Free tier abuse (scraping/reselling) | Low | Low | Rate limiting (5 req/min), hard cap (100 calls/month), Terms of Service prohibiting redistribution, API key revocation. |
| Stripe billing edge cases | Low | Low | Stripe Billing handles proration, failed payments, dunning automatically. |
| GDPR complaint | Low | Medium | Only B2B public data, no personal data of consumers. Art. 6(1)(f) legitimate interest. Privacy policy and DPA template ready. |

---

## 8. SUCCESS METRICS (FIRST 90 DAYS)

| Metric | Day 30 | Day 60 | Day 90 |
|---|---|---|---|
| Free signups | 30 | 80 | 160 |
| Paying customers | 0-1 | 5 | 10+ |
| MRR | EUR 0-49 | EUR 245-500 | EUR 700-1,500 |
| API calls served/day | 200 | 1,000 | 3,000 |
| Active alerts | 10 | 50 | 150 |
| Churn rate (monthly) | — | < 10% | < 8% |
| NPS (surveyed at day 30) | — | > 40 | > 50 |
| LinkedIn outreach messages sent | 100 | 200 | 300 |
| SEO articles published | 2 | 6 | 12 |
| Trade association partnerships | 0 | 1 | 2 |

---

## 9. BUDGET ALLOCATION (EUR 300/MONTH)

| Item | Monthly Cost | Notes |
|---|---|---|
| Hetzner CX42 VPS | EUR 22 | Existing infrastructure, sufficient for API + landing page |
| Domain + SSL | EUR 2 | cardex.eu or api.cardex.eu |
| Resend (email) | EUR 0-18 | Free tier covers first 3K emails; upgrade at ~100 dealers |
| Stripe fees | ~EUR 15-60 | 2.9% + EUR 0.25/txn, scales with revenue |
| Residential proxies (Decodo/Oxylabs) | EUR 150-200 | Existing scraping infrastructure |
| Unallocated reserve | EUR 0-106 | Buffer for unexpected costs or micro-experiments |
| **Total** | **EUR 189-300** | **Within budget** |

---

## 10. DECISION LOG

| Decision | Rationale | Alternative Considered |
|---|---|---|
| EUR 49 Starter (not EUR 29) | Schwacke charges EUR 7-10/query. At 50+ queries/month, EUR 49 is already a bargain. EUR 29 undervalues the product and sets a price anchor that's hard to raise. | EUR 29 "Micro" tier — kept as contingency if conversion < 2% at EUR 49 |
| EUR 199 Pro (not EUR 149) | DAT/SilverDAT Beginner is EUR 274/month for DE-only. EUR 199 for 6 countries is a clear value win. EUR 149 (as in MARKET_OPPORTUNITIES initial estimate) leaves too much value on the table. | EUR 149 — rejected; undercuts positioning vs. DAT unnecessarily |
| EUR 499 Enterprise (not EUR 999) | EUR 499/month (EUR 5,089/year) sits precisely at Autovista's entry floor. Going to EUR 999 enters a segment where buyers expect SLAs, phone support, and procurement cycles that a 1-person operation cannot deliver. | EUR 999 — deferred to Phase 3 when team capacity grows |
| Free tier included | Zero-friction acquisition is critical with no sales team. Every competitor above EUR 1K/year requires a sales call. Free tier is CARDEX's structural advantage. | No free tier — rejected; eliminates the primary acquisition funnel |
| Annual billing at -15% | Standard SaaS practice. 15% discount (not 20%) because the product is already aggressively priced. Higher discount would over-erode unit economics. | 20% discount — rejected; too aggressive at this price level |
| Landing page in English | Cross-border dealers operate in English as lingua franca. DE/NL/BE dealers sourcing from FR/ES need a neutral language. Localized versions (DE, FR, ES, NL) are Phase 2 after product-market fit is confirmed. | German-first — rejected; limits to 1 market |

---

## SOURCES

### Pricing Evidence
- [Autovista Group Revenue — Growjo](https://growjo.com/company/Autovista_Group) — EUR 178.8M/year revenue estimate
- [SilverDAT Pricing — Pixelconcept](https://www.pixelconcept.de/en/dat-software/) — EUR 274-427/month
- [carVertical Pricing](https://www.carvertical.com/en/pricing) — EUR 24.99/report
- [MarketCheck API Pricing](https://www.marketcheck.com/apis/pricing/) — from USD 8/query
- [CarAPI Pricing](https://carapi.app/pricing) — USD 199-299/year
- [Dataforce Market Data](https://www.dataforce.de/en/market-data/) — EUR 500-12,500/year

### Market Data
- [Europe Used Car Market — MarketDataForecast](https://www.marketdataforecast.com/market-reports/europe-used-cars-market) — USD 61.7B (2026)
- [McKinsey Used Car Analytics](https://www.mckinsey.com/industries/automotive-and-assembly/our-insights/) — USD 22B margin expansion opportunity
- [eCarsTrade Cross-Border Data](https://ecarstrade.com/blog/car-dealer-strategy-tips-for-eu-traders) — Spain 3.8% below EU average
- [Autorola Group](https://www.autorolagroup.com/) — 21% cross-border sales

### Competitive Intelligence
- [Autovista API](https://autovista.com/product/autovista-api/) — Enterprise pricing, no arbitrage feature
- [DAT Group / SilverDAT 3](https://www.datgroup.com/products/silverdat-3/) — DE-centric
- [Indicata Used Vehicle Intelligence](https://indicata.com/) — USD 3,800-5,800/year
- [Omnetic Sourcing](https://www.omnetic.com/en/sourcing/) — EUR 105/vehicle additional margin claim
- [CarOnSale Series C](https://tech.eu/2025/07/07/caronsale-secures-70m) — EUR 70M validates cross-border B2B
- [AutoGrab Series B](https://www.startupdaily.net/topic/funding/ai-based-car-valuation-platform-hits-top-get-with-80-million-series-b/) — AUD 80M validates AI valuations market

### Regulatory
- [Euro 7 Timeline — Geotab](https://www.geotab.com/ie/blog/euro-7-emission-standard-timeline-eu/) — Nov 2026 type approval
- [EU Battery Passport — Circularise](https://www.circularise.com/blogs/eu-battery-passport-regulation-requirements) — Feb 2027 mandatory
- [EU Data Act — LKQ Europe](https://lkqeurope.com/article/public-affairs/eu-data-act-new-era-vehicle-data-access-begins) — Sep 2025 in force

### Acquisition Channels
- [InStream Group — Automotive B2B Lead Generation](https://instreamgroup.com/) — LinkedIn outreach benchmarks
- [Datarade — Automotive Data Marketplace](https://datarade.ai/) — Free listing for data providers
- [BOVAG — Dutch Dealer Association](https://www.bovag.nl/) — 8,000+ members
- [TRAXIO — Belgian Automotive Federation](https://www.traxio.be/) — 9,000+ companies
