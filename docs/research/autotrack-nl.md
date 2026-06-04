# autotrack.nl — Scraping Research (CARDEX engine)

> Research date: 2026-06-03. Method: live `curl_cffi` 0.15.0 (`impersonate="chrome"`) probes against the production site. Total inventory: ~220,054 cars (JSON-LD `ItemList.numberOfItems` confirms 220,051; SSR counter shows 220.049 — same number within page-update jitter).

---

## 1. Anti-bot stack — **Cloudflare with TLS gating, no JS challenge** [VERIFIED]

`robots.txt` mentions `/cdn-cgi/` (Cloudflare's worker path) but no `cf-ray` or `cf-cache-status` headers were observed on the listing path itself. The TLS gate is real, though:

| Client | Result |
|---|---|
| `curl_cffi impersonate="chrome"` | **200** with the full SSR HTML |
| Plain `python-requests` (no impersonation) | **403** |

So Cloudflare enforces JA3 fingerprinting on this property but does **not** present a JS challenge for chrome-fingerprinted clients. Datacenter IP throughout, no proxy. Tier.T1 in `domain_map.py`.

---

## 2. Search endpoint — `/aanbod?pageNumber=N` [VERIFIED]

```
GET https://www.autotrack.nl/aanbod?pageNumber=N
```

Discovered via the `pageNumber=N` pager links rendered in the SSR HTML and confirmed by the `robots.txt` allow rule `Allow: /autobedrijf*?pageNumber=*`. The brief's candidate filter params (`priceMin/priceMax`, `priceFrom/priceTo`, `minPrice/maxPrice`, `constructionYearMin/Max`, `yearMin/Max`, `buildYearFrom/To`) **all returned the unfiltered baseline counter** — the query-string filter vocabulary is not honoured by this surface. Filters are encoded as URL **segments** instead:

| Path | Effect |
|---|---|
| `/aanbod/merk/audi/` | 12,349 Audi |
| `/aanbod/prijs/5000-10000/` | (server treats as 404-equivalent: returns base counter) |
| `/aanbod/bouwjaar/2018-2020/` | (same — segment grammar unverified) |

Critically, the year/price URL-segment grammars I probed didn't drop the counter, so the only verified filter dimension is `merk` (by name). However, **partitioning is not needed** here — see §4.

---

## 3. Listing layout & detail URL [VERIFIED]

Each listing card carries `data-vehicle-id="<NID>"` and an inner `<a href="/a/<slug>-<NID>?from_srp=true">`. The slug encodes brand/model/fuel/year (e.g. `seat-leon-benzine-2020`). The detail URL has the shape:

```
/a/<brand>-<model>-[<extra-keywords>-]<year>-<NID>?from_srp=true
```

Verified examples (live):

```
/a/seat-leon-benzine-2020-59439031?from_srp=true
/a/peugeot-5008-benzine-2018-59436164?from_srp=true
/a/hyundai-tucson-benzine-2016-59442854?from_srp=true
```

`NID` matches `\d+` (numeric vehicle id; the JSON-LD `Product.image` and the CDN URL `cdn.autotrack.nl/<NID>/0-*.jpg` both reference the same number — confirming `NID` is the canonical ad id). The host is fixed at `https://www.autotrack.nl`. The scraper strips `?from_srp=true` from the canonical URL because it is a referrer-tracking query, not part of identity.

### Card duplication on consecutive pages

Live overlap test: `pageNumber=1` and `pageNumber=2` share 2/30 IDs (a sponsored-slot duplicate sticky across the first few pages). `pageNumber=100` overlap with `pageNumber=1` = 0. The base scraper's `seen` set absorbs these duplicates, so PAGE_SIZE=30 is the right threshold for "page exhausted".

---

## 4. No partitioning — the pager covers the entire inventory [VERIFIED]

The pager is **not** capped at a sub-inventory ceiling. Live binary probe:

| `pageNumber=N` | Status | Ad count |
|---|---|---|
| 1 | 200 | 30 |
| 100 | 200 | 30 |
| **7336** | **200** | **4** ← last partial page |
| 7337 | 200 | 0 |

That gives `7,335 × 30 + 4 ≈ 220,054` ads — matching the counter. The whole inventory is reachable with no filter partition. The scraper uses a single empty segment and lets the base template paginate until the short page.

This is unusual — most NL/FR portals cap deep pagination at 100–500 pages. autotrack.nl exposes the full pager. The cost is volume: at 1.5–2s/page jittered, a full pass is ≈ 3–4 hours. The discovery scheduler should run this portal less often than the smaller ones.

---

## 5. Block signals

Cloudflare returns 403 for non-impersonated clients but does **not** issue a JS challenge body for `chrome`-impersonated ones during the research run. The only structural signals observed:

| Status | Treatment |
|---|---|
| 200 | parse, extract |
| 403/429/503 | retry with exponential backoff (3 attempts) — typically a TLS / rate-limit signal |
| other 4xx/5xx | terminal — return empty (this is how the cap manifests when `pageNumber` overruns) |
