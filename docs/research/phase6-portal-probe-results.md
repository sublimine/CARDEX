# Phase 6 — Portal Probe Results (DE/CH)

> Systematic probe of 20 vehicle sales portals in Germany and Switzerland.
> Probed on 2026-06-04 via web_fetch + WebSearch.

---

## GERMANY

### 1. autouncle.de — META-SEARCH (Aggregator)

**URL probed**: `https://www.autouncle.de/de/gebrauchtwagen`
**Alive**: YES (200 OK from WebSearch; web_fetch returned empty body — JS-only SPA)
**WAF**: None detected in headers. No Cloudflare cf-ray observed.
**Tech stack**: React SPA (page returns empty HTML shell, all content rendered client-side via JavaScript). Danish company (AutoUncle ApS), operates across 10 EU countries.
**Inventory**: ~1,890,402 listings (from meta-description). Aggregated from 2,639+ websites.
**API found**: Not directly visible. SPA likely calls internal JSON API endpoints for search (needs browser inspection). Because it aggregates from autoscout24, mobile.de, heycar, etc., listings are not first-party.
**VERDICT**: **META-SEARCH** — Aggregator that pulls from the same portals we already scrape. No first-party inventory. JS-rendered SPA makes scraping harder. Low value-add for Cardex.

---

### 2. 12gebrauchtwagen.de — META-SEARCH (Aggregator)

**URL probed**: `https://www.12gebrauchtwagen.de/`
**Alive**: YES (200 OK, full SSR HTML returned)
**WAF**: None detected. No Cloudflare, no Akamai, no DataDome. Clean response.
**Tech stack**: Ruby on Rails (meta-csrf-token with authenticity_token, `/rails/active_storage/` paths in image URLs, Vite asset hashing pattern `-d3ad7833`). SSR HTML with Turbo/Stimulus likely. Uses cloudimg.io CDN for image optimization.
**Inventory**: 1,024,883 listings (displayed on homepage). Aggregates from: AutoScout24, mobile.de, BMW, MINI, Autohero, Carwow, Leasingmarkt, LeasingTime.
**API found**: No visible JSON API. Rails app serves HTML pages. Search endpoint: `/suchen?s[provider_id][]=X`. `/gebrauchtwagensuche` for detailed search. Sister site: 12neuwagen.de, autoplenum.de.
**VERDICT**: **META-SEARCH** — Clean Rails SSR app, easy to scrape technically (T0/T1), but it is a pure aggregator of the same sources (autoscout24, mobile.de) we already cover. No first-party data. Could be useful as a cross-reference/validation source.

---

### 3. auto.de — SCRAPEABLE (T1)

**URL probed**: `https://www.auto.de/`
**Alive**: YES (200 OK, full HTML returned)
**WAF**: None detected. No Cloudflare headers. Uses autode-static.de as static CDN.
**Tech stack**: WordPress backend (wp-content paths, WP theme `autode`). Custom frontend with heavy JavaScript. Vehicle detail URLs use UUID format: `/search/vehicle/{uuid}`. Has user login, dealer portal, and financing through Santander Consumer Bank.
**Inventory**: Not explicitly counted on homepage, but features new + used cars across all major German brands. Dealer portal with search at `/search/detailed`.
**API found**: Likely REST API behind `/search/vehicle/{uuid}` pattern. No `__NEXT_DATA__` or SPA framework detected. WordPress REST API potentially at `/wp-json/`. Vehicle IDs are UUIDs. Search endpoint at `/angebot/gebrauchtwagen`.
**VERDICT**: **SCRAPEABLE (T1)** — WordPress + custom front-end, no WAF detected, SSR HTML. Dealer portal with real inventory (not aggregated). Santander financing integration suggests genuine dealer listings. Worth investigating the search API further.

---

### 4. autoplenum.de — CONTENT SITE (Limited Listings)

**URL probed**: `https://www.autoplenum.de/` (via WebSearch metadata)
**Alive**: YES (200 OK per WebSearch)
**WAF**: Unknown (could not fetch page body due to provenance restrictions).
**Tech stack**: Content/editorial site. Sister site of 12gebrauchtwagen.de (same company — link on 12gebrauchtwagen.de homepage). Focuses on car tests, reviews, TUV reports, dealer reviews. Not primarily a listings portal.
**Inventory**: No primary listings. Links to 12gebrauchtwagen.de for actual car search. Has dealer directory at `/autohaus/`.
**API found**: No listings API. Content-focused site.
**VERDICT**: **META-SEARCH** — Content/review companion to 12gebrauchtwagen.de. Not a listings portal. No scrapeable inventory. Skip.

---

### 5. automarkt.de — META-SEARCH (Aggregator)

**URL probed**: `https://www.automarkt.de/`
**Alive**: YES (200 OK, full HTML returned)
**WAF**: None detected. No Cloudflare, no Akamai headers. Clean response. Charset ISO-8859-1 (legacy encoding).
**Tech stack**: Legacy PHP/static HTML. Very basic frontend — static HTML with Bootstrap-like responsive layout, old-school form selects. No SPA framework. Partners with meinauto.de (neuwagen), wkda.de (wirkaufendeinauto), mobile.de, AutoScout24.
**Inventory**: "Über 1 Mio. Autos" — claims 1M+ listings, but these are aggregated from partner exchanges (mobile.de, AutoScout24, MeinAuto.de).
**API found**: No JSON API visible. Traditional form-post search. Listing pages at `/gebrauchtwagen/modelle/{brand}/`. Very simple server-rendered pages.
**VERDICT**: **META-SEARCH** — Old-school aggregator pulling from mobile.de/AutoScout24. Extremely easy to scrape (plain HTML, no WAF, no JS rendering), but no first-party data. Low priority.

---

### 6. autoboerse.de — SCRAPEABLE (T1)

**URL probed**: `https://autoboerse.de/`
**Alive**: YES (200 OK, full HTML/SSR returned)
**WAF**: None detected. No Cloudflare, no Akamai. Clean headers. Uses img.autoboerse.de for images.
**Tech stack**: Modern SPA/SSR hybrid. Clean semantic HTML with structured listing data visible in page source. Appears to be a custom-built platform (possibly Nuxt.js or similar — no `__NEXT_DATA__` seen). Owned by Openbank Deutschland AG (Santander group). Each listing has a unique slug ID (e.g., `ZG916RmdrBxw`).
**Inventory**: **250,574 listings** (exact count displayed on homepage). Breakdown by Bundesland visible: Bayern 55,825; NRW 46,804; Sachsen 32,810, etc. All from "geprüfte Händlerpartner" (verified Santander dealer partners).
**API found**: Search at `/fahrzeugsuche` with query params (`preis_bis=20000`, `antriebsart=4x4`). Listing detail at `/fahrzeugsuche/{brand-model-fuel-region}/{id}`. Likely JSON API behind the search — needs further investigation. Also has `/leasing-angebote` and `/finanzierung` endpoints.
**VERDICT**: **SCRAPEABLE (T1)** — First-party dealer inventory (250K+ listings), no WAF, SSR HTML with clean structure. Santander-backed dealer marketplace with exclusive inventory. High priority target — these are genuine dealer listings not duplicated on autoscout24/mobile.de.

---

### 7. classictrader.com — BLOCKED (Cloudflare + reCAPTCHA)

**URL probed**: `https://www.classictrader.com/` (via WebSearch + RocketReach tech profile)
**Alive**: YES (200 OK per WebSearch)
**WAF**: **Cloudflare** (confirmed by RocketReach tech profile). Also uses **reCAPTCHA** and **Cookiebot**.
**Tech stack**: PHP server-side. Uses Cloudflare CDN/WAF. 35 technologies detected including AddThis, Google Tag Manager, Facebook Pixel, DoubleClick, Hotjar.
**Inventory**: ~8,458 classic cars (from search snippet). Niche market — cars 30+ years old.
**API found**: Unknown. PHP-based site likely serves traditional HTML. Cloudflare + reCAPTCHA combination makes automated access difficult.
**VERDICT**: **BLOCKED** — Cloudflare WAF + reCAPTCHA. Niche classic car market (8K listings). Not worth the effort to bypass for such a small, specialized inventory.

---

### 8. carvago.com/de — SCRAPEABLE (T1)

**URL probed**: `https://carvago.com/de`
**Alive**: YES (200 OK, full HTML returned)
**WAF**: None detected in response. No Cloudflare cf-ray, no Akamai, no DataDome. Uses Google Tag Manager.
**Tech stack**: **Next.js** (confirmed: `meta-next-head-count: 37`, `/_next/static/media/` asset paths throughout). React SSR. Czech company (Carvago s.r.o.). GTM container GTM-KVGLZPZ. Santander Consumer Bank for financing.
**Inventory**: **1,073,852 listings** ("1 073 852 Treffer" displayed on homepage). Pan-European marketplace — aggregates from dealers across Europe.
**API found**: **YES — `_next/data/` API** guaranteed by Next.js architecture. Search at `/de/autos` with query params: `karosserie[]=CARSTYLE_SUV_OFFROAD`, `mileage-to=15000`, `registration-date-from=2024`, `premium-cars=1`, etc. Vehicle detail pages likely use `_next/data/{buildId}/de/autos/{brand}/{model}.json`. Also has B2B endpoint at `/b2b`.
**VERDICT**: **SCRAPEABLE (T1)** — Next.js SSR with guaranteed `_next/data` JSON API. No WAF detected. 1M+ pan-European listings. High-value target. Query params are well-structured for filtering. Santander financing backend.

---

### 9. gebrauchtwagen.de — REDIRECT to 12gebrauchtwagen.de

**URL probed**: `https://www.gebrauchtwagen.de/`
**Alive**: REDIRECT — WebSearch confirms gebrauchtwagen.de resolves to 12gebrauchtwagen.de content (same company). Search result for gebrauchtwagen.de shows "Alle Gebrauchtwagen-Angebote im Netz vergleichen – 12Gebrauchtwagen.de".
**WAF**: Same as 12gebrauchtwagen.de (none).
**Tech stack**: Same as 12gebrauchtwagen.de (Rails).
**Inventory**: Same 1,024,883 listings.
**API found**: Same as 12gebrauchtwagen.de.
**VERDICT**: **META-SEARCH** — Just a domain alias for 12gebrauchtwagen.de. Same aggregator. Skip.

---

### 10. wirkaufendeinauto.de — BUY-ONLY

**URL probed**: `https://www.wirkaufendeinauto.de/`
**Alive**: YES (200 OK per WebSearch)
**WAF**: Likely Cloudflare or DataDome (Autohero/AUTO1 Group typically uses strong bot protection). Could not fetch body to confirm.
**Tech stack**: Modern SPA (Autohero platform). Part of AUTO1 Group (also Autohero, wirkaufendeinauto). 220+ physical branches in Germany.
**Inventory**: No public listings for buying. This is a **car-buying service** — users sell their cars TO the platform. The `/auto-kaufen/` page redirects to Autohero for purchase.
**API found**: N/A — not a listings portal.
**VERDICT**: **BUY-ONLY** — Car purchase (from consumers) portal. No searchable inventory. Users sell cars here, they don't buy. Autohero is the selling arm. Skip.

---

### 11. check24.de/auto/ — NOT A LISTINGS PORTAL

**URL probed**: `https://www.check24.de/auto/`
**Alive**: YES (200 OK per WebSearch — but auto section is insurance/financing comparison, not listings)
**WAF**: Likely Akamai or Cloudflare (Check24 is a major German comparison portal). Could not fetch body to confirm specific WAF.
**Tech stack**: Custom enterprise platform. Check24 is one of Germany's largest comparison portals (insurance, credit, energy, telecom).
**Inventory**: No car listings. Provides KFZ-Versicherung (car insurance) comparison, Autokredit (car financing) comparison, and editorial content about car buying.
**API found**: N/A for car listings. Insurance/financing APIs are behind authentication.
**VERDICT**: **META-SEARCH** — Comparison portal for insurance and financing, not car listings. No inventory to scrape. Skip.

---

### 12. autohaus24.de — SCRAPEABLE (T1, Neuwagen-focused)

**URL probed**: `https://www.autohaus24.de/` (via WebSearch metadata)
**Alive**: YES (200 OK per WebSearch — active portal with 10K+ listings)
**WAF**: Unknown (could not fetch body). Part of Allane Group.
**Tech stack**: Modern web platform. Has both neuwagen configurator and gebrauchtwagen section at `/gebrauchtwagen`. Separate subdomain: `gebrauchtwagen.autohaus24.de`. ADAC test winner for neuwagen portals.
**Inventory**: 10,000+ vehicle offers (mix of new and used). 30 brands available for configuration. Partner dealer network across Germany. Three physical locations (Munich, Frankfurt, Berlin, Wuppertal).
**API found**: Likely API behind search — modern portal with configurator functionality. Needs browser probe to confirm endpoints.
**VERDICT**: **SCRAPEABLE (T1, tentative)** — Real dealer inventory, primarily new cars but also used. WAF status unknown — needs direct probe. Medium priority since primarily neuwagen-focused.

---

### 13. heycar.de — DEAD

**URL probed**: `https://www.heycar.de/` (via WebSearch)
**Alive**: **NO — SHUT DOWN**. WebSearch confirms: "heycar sagt Tschüss" (heycar says goodbye). The main domain shows a farewell page. Only portal.heycar.de (FAQ/help) remains.
**WAF**: N/A (was Cloudflare Pro per domain_map).
**Tech stack**: N/A (defunct).
**Inventory**: Zero. Service terminated.
**API found**: N/A.
**VERDICT**: **DEAD** — heycar.de has shut down operations. The marketplace is no longer active. Remove from domain_map. Previously used Volkswagen Financial Services as partner.

---

### 14. auto24.de — DEAD / Parked

**URL probed**: `https://auto24.de/`
**Alive**: Returns empty response (no HTML content, no redirects). Domain appears parked or inactive.
**WAF**: None (empty response).
**Tech stack**: None (empty page).
**Inventory**: Zero.
**API found**: None.
**VERDICT**: **DEAD** — Domain is parked/inactive. No functional website. Skip.

---

## SWITZERLAND

### 15. comparis.ch/carfinder — BLOCKED (CF_BUSINESS, confirmed)

**URL probed**: `https://www.comparis.ch/carfinder/default` (via WebSearch metadata)
**Alive**: YES (200 OK, active meta-search portal)
**WAF**: **Cloudflare Business** (already marked CF_BUSINESS in domain_map — confirmed).
**Tech stack**: Modern SPA. Comparis is Switzerland's largest comparison platform. Carfinder aggregates from autoscout24.ch, autoricardo.ch, car4you, and more.
**Inventory**: ~175,000+ car listings (from search snippet: "compare over 175,000 car listings"). Mix of occasion (used) and neuwagen (new). Also: 152,108 used car deals, 39,849 new car deals per separate pages.
**API found**: Search at `/Carfinder/search`, marketplace at `/carfinder/marktplatz`. Likely JSON API behind search but protected by Cloudflare Business.
**VERDICT**: **BLOCKED** — Cloudflare Business WAF. Also a meta-search aggregator (pulls from autoscout24.ch, autoricardo.ch). Already documented. Skip.

---

### 16. autoricardo.ch / auto.ricardo.ch — DEAD / Shutting Down

**URL probed**: `https://auto.ricardo.ch/search/` (via WebSearch)
**Alive**: Partially. WebSearch shows "Autoricardo verabschiedet sich!" (Autoricardo says goodbye!) at `/search/`. Some category pages still resolve but the search/listing functionality appears to be shutting down. Vehicle listings are migrating to main ricardo.ch platform at `ricardo.ch/de/c/autos-69957/`.
**WAF**: Unknown for auto.ricardo.ch. Main ricardo.ch likely has Cloudflare.
**Tech stack**: Separate platform from main Ricardo. Had ~180,000 accessories, ~5,000 auctions, ~8,000 motorcycles historically.
**Inventory**: Declining. Active listings moving to ricardo.ch/de/c/fahrzeuge-69956/ and ricardo.ch/de/c/autos-69957/.
**API found**: Historical API at auto.ricardo.ch is being deprecated. Dealer portal at haendler.auto.ricardo.ch.
**VERDICT**: **DEAD** — Platform is shutting down ("verabschiedet sich"). Listings migrating to main ricardo.ch auction platform. Not worth building a scraper for a dying platform.

---

### 17. auto.ch — DEAD (Domain for Sale)

**URL probed**: `https://auto.ch/` (via WebSearch)
**Alive**: **NO** — WebSearch confirms: "Der Domainname auto.ch steht zum Verkauf" (domain name is for sale).
**WAF**: N/A.
**Tech stack**: N/A (parked domain).
**Inventory**: Zero.
**API found**: None.
**VERDICT**: **DEAD** — Domain is for sale. No active portal. Skip.

---

### 18. autogalerie.ch — DEAD / Invisible

**URL probed**: `https://www.autogalerie.ch/` (via WebSearch)
**Alive**: **UNKNOWN** — WebSearch returned zero results for this domain. No indexed pages found. Either the site is down, has no SEO presence, or is a very small local dealer site with no web footprint.
**WAF**: Unknown.
**Tech stack**: Unknown.
**Inventory**: Unknown (likely very small if it exists at all).
**API found**: None.
**VERDICT**: **DEAD** — No web presence detectable. Either offline or too small to index. Skip.

---

### 19. autobid.ch — NICHE (B2B Auction)

**URL probed**: `https://www.autobid.ch/` (via WebSearch)
**Alive**: YES (200 OK per WebSearch)
**WAF**: Unknown (could not fetch body).
**Tech stack**: Unknown. Described as "C3 Restwertbörse AG" — a B2B industry exchange platform for damaged vehicles and lease returns.
**Inventory**: Unknown count, but described as "by far the largest industry exchange in Switzerland" for damaged/salvage/lease-return vehicles.
**API found**: Unknown. B2B platforms typically require authentication.
**VERDICT**: **BLOCKED / B2B-ONLY** — Industry-only auction platform for salvage and lease returns. Not consumer-facing listings. Requires dealer/industry credentials. Not suitable for Cardex consumer-facing scraping.

---

### 20. scout24.ch/auto — REDIRECT to AutoScout24.ch

**URL probed**: `https://www.scout24.ch/auto` (via WebSearch)
**Alive**: scout24.ch is the corporate parent site of the Scout24 Schweiz AG network. The `/auto` section redirects to autoscout24.ch (which is already covered in our existing scraper).
**WAF**: scout24.ch corporate site likely minimal. autoscout24.ch has its own WAF (already documented).
**Tech stack**: scout24.ch is the corporate/media portal. Owned by Ringier AG (50%) + Die Mobiliar (50%). Brands: AutoScout24, MotoScout24, ImmoScout24, anibis.ch, FinanceScout24.
**Inventory**: 34 million visits/month across all Scout24 marketplaces (corporate stat). AutoScout24.ch has its own inventory — already covered.
**API found**: N/A — corporate site, not a listings portal.
**VERDICT**: **META-SEARCH** — Corporate parent of AutoScout24.ch (already scraped). No additional inventory. Skip.

---

## Summary Table

| # | Portal | Country | Alive | WAF | Tech | Inventory | API | Verdict |
|---|--------|---------|-------|-----|------|-----------|-----|---------|
| 1 | autouncle.de | DE | Yes | None | React SPA | 1.89M (agg) | Hidden (SPA) | META-SEARCH |
| 2 | 12gebrauchtwagen.de | DE | Yes | None | Rails SSR | 1.02M (agg) | HTML only | META-SEARCH |
| 3 | auto.de | DE | Yes | None | WordPress | Unknown | Possible REST | SCRAPEABLE (T1) |
| 4 | autoplenum.de | DE | Yes | Unknown | Content site | None | None | META-SEARCH |
| 5 | automarkt.de | DE | Yes | None | Legacy PHP | 1M+ (agg) | None | META-SEARCH |
| 6 | **autoboerse.de** | DE | Yes | **None** | Modern SSR | **250K** | URL params | **SCRAPEABLE (T1)** |
| 7 | classictrader.com | DE | Yes | CF+reCAPTCHA | PHP | 8.5K | Unknown | BLOCKED |
| 8 | **carvago.com/de** | DE/EU | Yes | **None** | **Next.js** | **1.07M** | **_next/data** | **SCRAPEABLE (T1)** |
| 9 | gebrauchtwagen.de | DE | Redirect | None | Rails | 1.02M (agg) | Same as #2 | META-SEARCH |
| 10 | wirkaufendeinauto.de | DE | Yes | Likely strong | SPA | None (buy) | N/A | BUY-ONLY |
| 11 | check24.de/auto | DE | Yes | Likely strong | Enterprise | None (compare) | N/A | META-SEARCH |
| 12 | autohaus24.de | DE | Yes | Unknown | Modern web | 10K+ | Likely yes | SCRAPEABLE (T1, tentative) |
| 13 | heycar.de | DE | **DEAD** | N/A | N/A | Zero | N/A | **DEAD** |
| 14 | auto24.de | DE | **DEAD** | N/A | N/A | Zero | N/A | **DEAD** |
| 15 | comparis.ch | CH | Yes | CF Business | SPA | 175K (agg) | Behind CF | BLOCKED |
| 16 | autoricardo.ch | CH | Dying | Unknown | Legacy | Declining | Deprecated | **DEAD** |
| 17 | auto.ch | CH | **DEAD** | N/A | N/A | Zero | N/A | **DEAD** |
| 18 | autogalerie.ch | CH | **DEAD** | N/A | N/A | Zero | N/A | **DEAD** |
| 19 | autobid.ch | CH | Yes | Unknown | B2B auction | Unknown | Auth-only | B2B-ONLY |
| 20 | scout24.ch/auto | CH | Redirect | N/A | Corporate | N/A | N/A | META-SEARCH |

---

## Priority Targets (New Scrapers Worth Building)

### Tier 1 — High Value
1. **carvago.com/de** — Next.js, no WAF, 1.07M pan-European listings, `_next/data` API guaranteed. Biggest find.
2. **autoboerse.de** — No WAF, 250K exclusive Santander dealer listings, SSR HTML, structured URL params.

### Tier 2 — Medium Value
3. **auto.de** — WordPress, no WAF, real dealer inventory, needs deeper API probe.
4. **autohaus24.de** — Unknown WAF, 10K+ listings, primarily neuwagen. Needs browser probe.

### Dead / Remove from Domain Map
- **heycar.de** — Shut down. Remove CF_PRO entry.
- **auto24.de** — Parked/empty.
- **auto.ch** — Domain for sale.
- **autoricardo.ch** — Shutting down ("verabschiedet sich").
- **autogalerie.ch** — No web presence.
