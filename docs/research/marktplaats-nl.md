# marktplaats.nl (cars / "Auto's") — Scraping Research (CARDEX engine)

> Research date: 2026-06-03. Method: `curl_cffi` 0.15.0 (`impersonate="chrome"`) via Bash — every endpoint below was actually hit and the JSON parsed. Candidate params from the brief were independently verified against the live `searchRequest` echo the API returns. This is the **easiest** target researched so far: the internal LRP JSON API is effectively open.

---

## 1. Anti-bot stack — AWS CloudFront, NO active WAF [VERIFIED]

marktplaats.nl fronts everything with **AWS CloudFront**. There is **NO Cloudflare**, no Akamai, no DataDome, and no bot challenge observed on the search API.

### Evidence (real fetches)

`GET https://www.marktplaats.nl/lrp/api/search?l1CategoryId=91&offset=0&limit=30`:

```
STATUS 200
content-type: application/json; charset=utf-8
via: 1.1 <hash>.cloudfront.net (CloudFront)
x-cache: Miss from cloudfront
x-amz-cf-id: 6yGow4A8jpAGtayYjWkBYH72kREHknaMUJLw-DICQCG4KDUdM_wWhg==
set-cookie: MpSession=<uuid>; Domain=.marktplaats.nl; Path=/; HttpOnly
set-cookie: luckynumber=<n>; Domain=.marktplaats.nl; Path=/; ...
```

The brief's hypothesis "WAF: Cloudflare? confirm" is **rejected**: headers show CloudFront, not Cloudflare (no `cf-ray`, no `cf-cache-status`, no `__cf_bm`).

### What passes [VERIFIED]

| Request mode | Result |
|---|---|
| `curl_cffi impersonate="chrome"` | **200 JSON** |
| Plain `python-requests` UA `python-requests/2.x`, **no impersonation** | **200 JSON** (full `listings` array) |

The API returned 200 with a naked `python-requests` user-agent and zero TLS impersonation. No JS challenge, no cookie pre-flight required. TLS fingerprinting is **not** enforced on this route. (Datacenter IP throughout, no proxy.) Treat as an open JSON API; the only realistic risk is volumetric IP rate-limiting at scale.

---

## 2. Endpoint — internal LRP search JSON [VERIFIED]

```
GET https://www.marktplaats.nl/lrp/api/search
```

Method **GET**, query-string params only. Returns `application/json`. `l1CategoryId=91` = **Auto's** (cars) — confirmed: the response `searchRequest.originalRequest.categories.l1Category` echoes `{"id":91,"key":"auto-s","fullName":"Auto's"}`. The brief's candidate id `91` is **correct**.

### Verified query params

All names below were confirmed by reading the `searchRequest` object the API echoes back (it parses and reflects every param), and by observing the result set actually change.

| Param | Meaning | Verified example |
|---|---|---|
| `l1CategoryId` | top-level category; `91` = Auto's | `91` |
| `l2CategoryId` | sub-category (make/segment); optional | (numeric; see note) |
| `offset` | pagination start index | `0`, `30`, `990` |
| `limit` | page size | `30` (default site uses 30) |
| `attributeRanges[]` | **range filters** — `key:from:to`. Repeatable. | `constructionYear:2018:2022`, `PriceCents:500000:1500000` |
| `attributesById[]` | discrete attribute-value id filter (e.g. fuel, make) | `10882` |
| `attributesByKey[]` | discrete attribute filter by key | (string) |
| `query` | free-text search | `bmw` |
| `searchInTitleAndDescription` | broaden free-text to body | `true` |
| `postcode` | NL postcode for distance filter | `1011AB` |
| `distanceMeters` | radius around postcode | `50000` |
| `sortBy` | sort field | `OPTIMIZED` / `SORT_INDEX` / `PRICE` / `ATTRIBUTE` |
| `sortOrder` | direction | `INCREASING` / `DECREASING` |

> **Year filter** = `attributeRanges[]=constructionYear:<from>:<to>` (NOT a `yearFrom`/`yearTo` param). **Price filter** = `attributeRanges[]=PriceCents:<fromCents>:<toCents>` — value is in **cents** (€15,000 = `1500000`). Both verified: with `constructionYear:2018:2022` every returned listing had `constructionYear` ∈ [2018,2022], and with `PriceCents:500000:1500000` every `priceInfo.priceCents` ≤ 1,500,000. Total dropped from 267,909 (unfiltered) to 5,268 (filtered), proving server-side application.

Verified live request (filters + distance + sort), returned 200:
```
GET /lrp/api/search?l1CategoryId=91&offset=0&limit=5
    &attributeRanges[]=constructionYear:2018:2022
    &attributeRanges[]=PriceCents:500000:1500000
    &sortBy=SORT_INDEX&sortOrder=DECREASING
    &postcode=1011AB&distanceMeters=50000
```

Available `sortOptions` (echoed by API): `OPTIMIZED/DECREASING`, `SORT_INDEX/DECREASING`, `SORT_INDEX/INCREASING`, `PRICE/INCREASING`, `PRICE/DECREASING`, `ATTRIBUTE/DECREASING`.

### Required headers [VERIFIED]

**None are strictly required.** A bare `User-Agent` suffices. For safety/politeness use a browser-like set:
```
Accept: application/json, text/plain, */*
Accept-Language: nl-NL,nl;q=0.9,en;q=0.8
Referer: https://www.marktplaats.nl/l/auto-s/
User-Agent: <chrome UA>
```
No auth token, no CSRF header, no `x-*` custom header needed.

---

## 3. Response shape + listing-URL extraction [VERIFIED]

Top-level JSON keys:
```
listings[], topBlock, facets[], totalResultCount, maxAllowedPageNumber,
correlationId, sortOptions, searchRequest, searchCategory, categoriesById, ...
```

The ad list is **`listings`** (array). Per-listing fields (verified):
```
itemId, title, description, categorySpecificDescription, priceInfo{priceCents,priceType},
location{cityName,countryName,latitude,longitude,distanceMeters}, date, imageUrls[],
sellerInformation{sellerId,sellerName,...}, categoryId, attributes[], extendedAttributes[],
pictures[], vipUrl, shortTitle, displayTitle
```

**Listing-URL field = `vipUrl`** (relative path). Build the detail URL by prefixing the host:
```
vipUrl:     /v/auto-s/bmw/m2406619523-bmw-5-serie-535i-executive-m-sport-alcantara-20-org-nl
Detail URL: https://www.marktplaats.nl/v/auto-s/bmw/m2406619523-bmw-5-serie-535i-...
ID field:   itemId  (e.g. "m2406619523" — "m" + numeric)
```

Year/mileage live in `attributes[]` as key/value objects:
```
{"key":"constructionYear","value":"2015","values":["2015"]}
{"key":"mileage","value":"119551","unit":"km","values":["119551"]}
{"key":"fuel",...}, {"key":"transmission",...}, {"key":"body",...}, {"key":"model",...}
```

---

## 4. Pagination + result cap [VERIFIED]

- **Page model:** `offset` + `limit` (not page numbers). Site default `limit=30`.
- **`totalResultCount`:** 267,909 for all cars unfiltered (verified).
- **`maxAllowedPageNumber`: 167** (returned in every response). At `limit=30` that is 167 × 30 = **~5,010 listings reachable per query**.
- **Offset behavior at the edge [VERIFIED]:** `offset=990`, `1000`, `1050` all return a full 30 listings with `hasErrors:false`. `offset=9990` returns an **empty `listings:[]`** (no error, no block) — the API silently yields nothing past the reachable window rather than throwing. So the effective ceiling per search is ~5,000 (the `maxAllowedPageNumber × limit` window), well below `totalResultCount`.
- **Implication:** classic deep-result cap → **search-grid partitioning is mandatory** for full inventory coverage (267k cars ≫ 5k window).

---

## 5. Recommended search-grid partition

Each cell must resolve to ≤ ~5,000 results (the `maxAllowedPageNumber × limit` window). `totalResultCount` is returned on every call, so cells can be sized adaptively with a single cheap probe.

Algorithm:
1. Probe `GET .../search?l1CategoryId=91&limit=1` → read `totalResultCount`.
2. Split by **make** (`attributesById[]` make-id, or `l2CategoryId`, or `query=<make>` as a coarse fallback) and re-probe each.
3. If a make cell > ~5,000, split by **year** (`attributeRanges[]=constructionYear:Y:Y`, per-year).
4. If a (make × year) cell still > ~5,000, split by **price** bucket (`attributeRanges[]=PriceCents:a:b`).
5. Enumerate each cell `offset=0,30,60,...` until `offset ≥ maxAllowedPageNumber×limit` OR `listings` is empty; dedupe on `itemId` globally.

Because `totalResultCount` is free on every request, adaptive recursion keeps each cell under the window with minimal waste.

---

## 6. Recommended tier

**Tier T0 (open JSON API — no browser, no stealth, no impersonation required).**

Rationale:
- The LRP search route returns 200 JSON to a naked `python-requests` client (verified). No Cloudflare, no JS challenge, no TLS fingerprint gate, no required auth/cookie.
- Both listing enumeration AND structured data (price, year, mileage, location, seller, images) come from the **same single JSON call** — no separate detail fetch needed for core fields; `vipUrl` gives the canonical detail URL for enrichment.
- Only scaling concern is volumetric per-IP rate limiting (CloudFront). Use modest concurrency + polite delays + IP rotation only if throughput demands it. `curl_cffi impersonate="chrome"` recommended purely as defensive hygiene, not because it is needed.

Tier summary:
- Listing enumeration + core fields via `/lrp/api/search` → **T0** (curl_cffi or plain requests).
- Detail enrichment via `https://www.marktplaats.nl{vipUrl}` → **T0/T1** (HTML, not exercised here; expected open behind same CloudFront).

---

## Confidence ledger

| Finding | Status |
|---|---|
| CloudFront front, NO Cloudflare/Akamai/DataDome | **VERIFIED** (response headers) |
| API returns 200 to plain `python-requests` (no impersonation) | **VERIFIED** |
| `GET /lrp/api/search`, `l1CategoryId=91` = Auto's (cars) | **VERIFIED** (echoed `searchRequest`) |
| `offset`/`limit` pagination | **VERIFIED** |
| Year filter `attributeRanges[]=constructionYear:from:to` | **VERIFIED** (results bounded) |
| Price filter `attributeRanges[]=PriceCents:from:to` (cents) | **VERIFIED** (results bounded) |
| `query` + `searchInTitleAndDescription`, `postcode`+`distanceMeters` | **VERIFIED** |
| `sortBy`/`sortOrder` option set | **VERIFIED** (echoed) |
| Listing array = `listings`; URL field = `vipUrl`; id = `itemId` | **VERIFIED** (real sample) |
| `totalResultCount` = 267,909; `maxAllowedPageNumber` = 167 | **VERIFIED** |
| Deep offset → empty `listings` (no error); ~5,010 window/query | **VERIFIED** (offset 990–9990 probes) |
| No required headers/auth | **VERIFIED** |
| Detail-page (`vipUrl`) HTML openness | **ASSUMED** (not exercised) |
| make-id values for `attributesById[]` / `l2CategoryId` map | **ASSUMED** (mechanism verified, full id table not enumerated) |
