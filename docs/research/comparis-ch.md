# comparis.ch — T2→T1 BYPASS via SSR HTML (no WAF)

> Research date: 2026-06-04. Method: live web_fetch probing. Result: comparis.ch's car marketplace at `/carfinder/marktplatz` serves server-rendered HTML with NO Cloudflare WAF. Standard curl/curl_cffi requests return full listing pages with detail links. Downgraded from T2 (CF Business) to T1.

---

## Verdict: T1 (SSR HTML scraping — implemented)

comparis.ch is Switzerland's largest comparison portal. The Carfinder section aggregates vehicle listings from autoscout24.ch, autolina.ch, carmarket.ch, drive-in.ch, carweb.ch, and other Swiss dealer platforms — ~214,259 listings total. Despite being originally classified as CF Business (T2), the Carfinder surface does NOT trigger any Cloudflare challenge. The `meta-next-head-count` header indicates a Next.js SSR backend.

---

## Site Details [VERIFIED 2026-06-04]

### Search URL

```
GET https://www.comparis.ch/carfinder/marktplatz
    ?sort=2&page={N}
    &yearfrom={Y1}&yearto={Y2}
    &pricefrom={P1}&priceto={P2}
    &condition=occasion
```

- **Pages are 0-indexed** (page=0 is first)
- **~10 listings per page** (SSR HTML cards)
- **~214k total listings** across aggregated sources

### Available Filters

| Parameter | Example | Notes |
|-----------|---------|-------|
| `sort` | `2` | Sort order |
| `page` | `0` | 0-indexed |
| `yearfrom` / `yearto` | `2020` / `2024` | Year range |
| `pricefrom` / `priceto` | `10000` / `20000` | Price range (CHF) |
| `condition` | `occasion` / `neuwagen` | Used / New |
| `make` | brand name | Vehicle make |
| `bodytype` | body type | Vehicle body |
| `fuel` | fuel type | Fuel filter |

### Detail URLs

Extracted from SSR HTML via `href="/carfinder/marktplatz/details/show/{ID}"` where ID is a numeric listing identifier (e.g., 32911044).

Canonical: `https://www.comparis.ch/carfinder/marktplatz/details/show/{ID}`

### Aggregated Sources

autoscout24.ch, autolina.ch, carmarket.ch, drive-in.ch, carweb.ch (visible in portal logos on the search page).

---

## WAF Analysis

No Cloudflare challenge, no DataDome, no Akamai observed. The HTML response is returned immediately with status 200. The original T2/CF_BUSINESS classification was incorrect — possibly based on Cloudflare CDN headers rather than active WAF challenge. The Carfinder surface is unprotected.

---

## Engine Classification (updated)

```python
PortalSpec(
    "comparis.ch", Tier.T1, WAF.NONE,
    countries=["CH"],
    notes="T2→T1 bypass: SSR HTML no WAF, meta-aggregator ~214k listings [VERIFIED 2026-06-04]",
)
```

---

## Implementation

- `scrapers/portals/comparis_ch/__init__.py` — `ComparisCHScraper`
- Year × price grid partitioning: 11 year bands × 10 price bands (CHF) = 110 segments
- Regex-based HTML extraction: `/carfinder/marktplatz/details/show/(\d+)`
- 0-indexed pages (page_num - 1 conversion)
