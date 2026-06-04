# Phase 6 — Blocked, Dead & Non-Viable Portals (DE/CH)

> Research date: 2026-06-04 | Branch: `phase6-de-ch`
>
> Catalogues every DE/CH portal evaluated for Phase 6 that cannot be scraped,
> is dead, or is otherwise excluded from implementation.
> Implemented portals: autoboerse.de, carvago.com — documented in their scraper modules.

---

## Summary Table

| #  | Domain                 | Country | Status      | WAF / Blocker    | Tier | Est. Listings | Reason                                        |
|----|------------------------|---------|-------------|------------------|------|---------------|------------------------------------------------|
| 1  | heycar.de              | DE      | DEAD        | N/A              | --   | 0             | Shut down 2025 ("heycar sagt Tschüss")        |
| 2  | auto24.de              | DE      | DEAD        | N/A              | --   | 0             | Domain parked, empty response                  |
| 3  | auto.ch                | CH      | DEAD        | N/A              | --   | 0             | Domain for sale                                |
| 4  | autoricardo.ch         | CH      | DEAD        | N/A              | --   | 0             | Shutting down ("verabschiedet sich")           |
| 5  | autogalerie.ch         | CH      | DEAD        | N/A              | --   | 0             | No web presence detectable                     |
| 6  | classictrader.com      | DE      | BLOCKED     | CF + reCAPTCHA   | T2   | ~8.5k         | Cloudflare WAF + reCAPTCHA, niche classic cars |
| 7  | comparis.ch            | CH      | BLOCKED     | CF Business      | T2   | 175k (agg)    | Cloudflare Business, meta-search aggregator    |
| 8  | autobid.ch             | CH      | B2B-ONLY    | Auth required    | --   | Unknown       | B2B auction for salvage/lease returns          |
| 9  | autouncle.de           | DE      | META-SEARCH | None             | --   | 1.89M (agg)   | Aggregator of autoscout24/mobile.de            |
| 10 | 12gebrauchtwagen.de    | DE      | META-SEARCH | None             | --   | 1.02M (agg)   | Rails aggregator of autoscout24/mobile.de      |
| 11 | gebrauchtwagen.de      | DE      | META-SEARCH | None             | --   | 1.02M (agg)   | Domain alias for 12gebrauchtwagen.de           |
| 12 | automarkt.de           | DE      | META-SEARCH | None             | --   | 1M+ (agg)     | Legacy PHP aggregator                          |
| 13 | autoplenum.de          | DE      | META-SEARCH | Unknown          | --   | None           | Content/review site, sister of #10             |
| 14 | check24.de/auto        | DE      | SKIP        | Likely strong    | --   | None           | Insurance/financing comparison, not listings   |
| 15 | wirkaufendeinauto.de   | DE      | SKIP        | Likely strong    | --   | None           | Buy-only service (consumers sell to platform)  |
| 16 | scout24.ch/auto        | CH      | META-SEARCH | N/A              | --   | N/A            | Corporate parent, redirects to autoscout24.ch  |
| 17 | auto.de                | DE      | DEFERRED    | None             | T1?  | Unknown        | WordPress dealer portal, needs deeper probe    |
| 18 | autohaus24.de          | DE      | DEFERRED    | Unknown          | T1?  | ~10k+          | Neuwagen-focused, WAF unknown                  |

---

## DEAD PORTALS

### 1. heycar.de

| Field            | Value                                                  |
|------------------|--------------------------------------------------------|
| **Domain**       | heycar.de                                              |
| **Country**      | DE                                                     |
| **Status**       | DEAD — shut down 2025                                  |
| **Prev. WAF**    | Cloudflare Pro (was in domain_map as T2/CF_PRO)        |
| **Listings**     | 0 (service terminated)                                 |

**Description:** heycar was a Volkswagen Financial Services-backed used car marketplace.
The main domain now displays a farewell page: "heycar sagt Tschüss" (heycar says goodbye).
Only the help portal at portal.heycar.de remains active. The marketplace is permanently closed.

**Action:** Removed from `domain_map.py` REGISTRY. Replaced with comment:
```python
# heycar.com DEAD — shut down 2025 ("heycar sagt Tschüss") [VERIFIED 2026-06-04]
```

---

### 2. auto24.de

| Field            | Value                                                  |
|------------------|--------------------------------------------------------|
| **Domain**       | auto24.de                                              |
| **Country**      | DE                                                     |
| **Status**       | DEAD — domain parked                                   |
| **WAF**          | N/A (empty response)                                   |
| **Listings**     | 0                                                      |

**Description:** Returns empty response (no HTML, no redirects). Domain appears parked or
inactive. No functional website detectable via WebSearch or direct probe.

---

### 3. auto.ch

| Field            | Value                                                  |
|------------------|--------------------------------------------------------|
| **Domain**       | auto.ch                                                |
| **Country**      | CH                                                     |
| **Status**       | DEAD — domain for sale                                 |
| **WAF**          | N/A                                                    |
| **Listings**     | 0                                                      |

**Description:** WebSearch confirms: "Der Domainname auto.ch steht zum Verkauf" (domain
is for sale). Premium .ch domain with no active portal behind it.

---

### 4. autoricardo.ch / auto.ricardo.ch

| Field            | Value                                                  |
|------------------|--------------------------------------------------------|
| **Domain**       | autoricardo.ch / auto.ricardo.ch                       |
| **Country**      | CH                                                     |
| **Status**       | DEAD — shutting down                                   |
| **WAF**          | Unknown (main ricardo.ch likely Cloudflare)             |
| **Listings**     | Declining, migrating to ricardo.ch                     |

**Description:** WebSearch shows "Autoricardo verabschiedet sich!" (Autoricardo says
goodbye!). The standalone auto platform is being shut down. Remaining vehicle listings
are migrating to the parent ricardo.ch auction platform at `/de/c/autos-69957/`.
Not worth building a scraper for a dying platform whose remnants will merge into a
general auction site with strong WAF.

---

### 5. autogalerie.ch

| Field            | Value                                                  |
|------------------|--------------------------------------------------------|
| **Domain**       | autogalerie.ch                                         |
| **Country**      | CH                                                     |
| **Status**       | DEAD — no web presence                                 |
| **WAF**          | Unknown                                                |
| **Listings**     | Unknown (likely zero or very small)                    |

**Description:** WebSearch returned zero indexed results for this domain. Either the site
is offline, has no SEO footprint, or is a small local dealer with no public web presence.

---

## BLOCKED PORTALS

### 6. classictrader.com

| Field            | Value                                                  |
|------------------|--------------------------------------------------------|
| **Domain**       | classictrader.com                                      |
| **Country**      | DE                                                     |
| **Status**       | BLOCKED                                                |
| **WAF**          | Cloudflare + reCAPTCHA + Cookiebot                     |
| **Tier**         | T2                                                     |
| **Listings**     | ~8,458 classic/vintage vehicles                        |
| **Tech stack**   | PHP, 35 technologies (AddThis, GTM, Hotjar, etc.)      |

**Description:** Niche marketplace for classic cars (30+ years old). Cloudflare WAF combined
with Google reCAPTCHA makes automated access impractical. Even if bypassed, the inventory
is very small (8.5K) and highly niche — not cost-effective for Cardex's mainstream focus.

**domain_map entry:** Not added (T2 + reCAPTCHA + niche = not worth the effort).

---

### 7. comparis.ch/carfinder

| Field            | Value                                                  |
|------------------|--------------------------------------------------------|
| **Domain**       | comparis.ch                                            |
| **Country**      | CH                                                     |
| **Status**       | BLOCKED                                                |
| **WAF**          | Cloudflare Business                                    |
| **Tier**         | T2                                                     |
| **Listings**     | ~175K (aggregated from autoscout24.ch, autoricardo.ch) |
| **Tech stack**   | Modern SPA, Comparis corporate platform                |

**Description:** Switzerland's largest comparison platform. The carfinder section aggregates
from autoscout24.ch and other sources we already scrape. Cloudflare Business WAF blocks
automated access. Even if accessible, it's a meta-search with no first-party inventory.

**domain_map entry:** Already registered as `T2/CF_BUSINESS`.

---

## B2B / AUTH-REQUIRED

### 8. autobid.ch

| Field            | Value                                                  |
|------------------|--------------------------------------------------------|
| **Domain**       | autobid.ch                                             |
| **Country**      | CH                                                     |
| **Status**       | B2B-ONLY                                               |
| **WAF**          | Unknown (auth-gated)                                   |
| **Listings**     | Unknown (described as "largest industry exchange in CH")|
| **Tech stack**   | C3 Restwertbörse AG platform                           |

**Description:** B2B-only auction platform for damaged vehicles, salvage, and lease returns.
Not consumer-facing. Requires dealer/industry credentials to access listings. Not suitable
for Cardex consumer-facing vehicle data collection.

---

## META-SEARCH / AGGREGATORS (No First-Party Data)

### 9. autouncle.de

React SPA aggregating 1.89M listings from autoscout24, mobile.de, heycar (now dead),
and 2,639+ partner websites. Danish company (AutoUncle ApS). No first-party inventory.

### 10. 12gebrauchtwagen.de

Ruby on Rails SSR app aggregating 1.02M listings from AutoScout24, mobile.de, BMW, MINI,
Autohero, Carwow, Leasingmarkt, LeasingTime. No WAF. Easy to scrape technically but
100% aggregated data we already collect from source portals.

### 11. gebrauchtwagen.de

Domain alias that redirects to 12gebrauchtwagen.de. Same company, same data.

### 12. automarkt.de

Legacy PHP site claiming 1M+ listings from partner exchanges (mobile.de, AutoScout24,
MeinAuto.de). ISO-8859-1 encoding. Trivially scrapeable but zero unique data.

### 13. autoplenum.de

Content/review companion site to 12gebrauchtwagen.de. Focuses on car tests, TÜV reports,
dealer reviews. Not a listings portal. Links to 12gebrauchtwagen.de for actual car search.

### 14–16. check24.de/auto, wirkaufendeinauto.de, scout24.ch/auto

check24.de: Insurance/financing comparison, not a car listings portal.
wirkaufendeinauto.de: Car-buying service (consumers sell TO the platform). No searchable inventory.
scout24.ch/auto: Corporate parent of AutoScout24.ch (already scraped). Redirects to autoscout24.ch.

---

## DEFERRED (Possible Future Phase)

### 17. auto.de

| Field            | Value                                                  |
|------------------|--------------------------------------------------------|
| **Domain**       | auto.de                                                |
| **Country**      | DE                                                     |
| **Status**       | DEFERRED — needs deeper investigation                  |
| **WAF**          | None detected                                          |
| **Tier**         | T1 (tentative)                                         |
| **Listings**     | Unknown (real dealer inventory)                        |
| **Tech stack**   | WordPress + custom frontend, UUID-based vehicle IDs    |

**Description:** Dealer portal with Santander Consumer Bank financing integration.
Vehicle detail URLs use UUID format (`/search/vehicle/{uuid}`). No WAF detected.
The WordPress REST API at `/wp-json/` may expose vehicle data. Lower priority because
inventory size is unconfirmed and WordPress sites can change structure frequently.

### 18. autohaus24.de

| Field            | Value                                                  |
|------------------|--------------------------------------------------------|
| **Domain**       | autohaus24.de                                          |
| **Country**      | DE                                                     |
| **Status**       | DEFERRED — WAF unknown, primarily neuwagen             |
| **WAF**          | Unknown                                                |
| **Tier**         | T1 (tentative)                                         |
| **Listings**     | ~10K+ (mix new and used)                               |
| **Tech stack**   | Modern web platform, Allane Group                      |

**Description:** Primarily neuwagen (new car) configurator/dealer platform. Has a
gebrauchtwagen section at `/gebrauchtwagen` and separate subdomain. ADAC test winner.
WAF status unconfirmed — needs direct browser probe to confirm accessibility.
Lower priority since Cardex focuses on Gebrauchtwagen (used cars).
