# gocar.be — STAYS T2 (CF Business, no bypass found)

> Research date: 2026-06-04. Method: WebSearch + Apify actor analysis + bash curl probe. Result: gocar.be (formerly autovlan.be) is protected by Cloudflare Business. Curl returns empty responses (HTTP 000). Third-party scrapers on Apify exist but use browser-based approaches. No public API, no accessible sitemap, no bypass found. Stays at T2/CF_BUSINESS.

---

## Verdict: STAYS T2 (no bypass, Camoufox required)

GoCar.be (launched 2007 as AutoVlan.be) is Belgium's largest automotive classifieds platform, operated jointly by Roularta Media Group and Rossel. The site is an SPA protected by Cloudflare Business — datacenter curl is rejected at the edge.

---

## Technical Details [VERIFIED 2026-06-04]

- **Owner:** Roularta Media Group + Rossel (Belgian media JV)
- **Domains:** gocar.be (NL/FR/EN), autovlan.be (legacy redirect)
- **Frontend:** SPA (Angular or React, exact framework unconfirmed)
- **Search URL pattern:** `https://gocar.be/en/search?gbrands=BMW&gmodels=...&fuel=...`
- **WAF:** Cloudflare Business — returns HTTP 000 (connection drop) to datacenter curl
- **No public API:** No documented JSON endpoints found
- **No sitemap access:** Blocked by Cloudflare

## Probing Results

```
$ curl -sk -o /dev/null -w "HTTP %{http_code} size=%{size_download}" \
    -A "Mozilla/5.0 ... Chrome/136.0" "https://www.gocar.be/"
HTTP 000 size=0

$ curl -sk -o /dev/null -w "HTTP %{http_code} size=%{size_download}" \
    "https://www.gocar.be/sitemap.xml"
HTTP 000 size=0
```

## Third-Party Scrapers

Two Apify actors exist:
1. `lexis-solutions/gocar-be-scraper` — browser-based, extracts 50+ fields per listing
2. `studio-amba/autovlan-scraper` — supports sitemap-based full catalog scraping via browser

Both use headless browser approaches, confirming that direct HTTP access is not viable.

---

## Engine Classification (unchanged)

```python
PortalSpec("gocar.be", Tier.T2, WAF.CF_BUSINESS, countries=["BE"])
```

---

## Action

- ❌ No `scrapers/portals/gocar_be/` module at T0/T1
- Keep T2/CF_BUSINESS classification
- When Camoufox is available, implement via browser automation
- The SPA likely has XHR/fetch calls to a backend API that could be intercepted and replayed once a valid Cloudflare session is established via browser
- The Apify sitemap approach suggests gocar.be does have a sitemap.xml accessible to real browsers — that could be a useful discovery surface once Camoufox sessions are available
