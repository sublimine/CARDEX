# coches.net — Scraping Research (CARDEX engine)

> Research date: 2026-06-03. Method: `curl_cffi` 0.15.0 (`impersonate="chrome"`) via Bash + Playwright (real Chromium) for in-browser fetch/DOM capture + raw JS-bundle and SSR-HTML inspection + WebSearch/WebFetch for corroboration. The internal Adevinta API host was hit directly; the request/response **schema was recovered from the server-side-rendered (SSR) search response embedded in the page**, because the API itself is geo/origin-restricted from the research egress (details below). Third-party scraper claims (Apify/cochista) were treated as leads only.

---

## 1. Anti-bot / reachability — AWS CloudFront; API origin geo/network-restricted [VERIFIED]

coches.net is an **Adevinta Spain** property fronted by **AWS CloudFront**. There is **NO Cloudflare** (no `cf-ray`/`cf-cache-status`). No DataDome challenge was observed on the listing path (only analytics cookies `ajs_anonymous_id` set).

### Evidence — main site (reachable)

`GET https://www.coches.net/` and `GET https://www.coches.net/segunda-mano/` via `curl_cffi impersonate=chrome`:
```
STATUS 200
via: 1.1 <hash>.cloudfront.net (CloudFront)
x-cache: Miss from cloudfront
x-amz-cf-id: IXmbQ3JGWrr6jTcGs13ou8seOrEpkYxMfFtr-5jfK2xbWEJk9iKUKQ==
x-frame-options: SAMEORIGIN
set-cookie: ajs_anonymous_id=<uuid>; Domain=.coches.net
```
The HTML is **server-rendered** and already contains the full first-page search results as embedded JSON (see §3). This is the durable scraping surface from any region.

### Evidence — internal API host (geo/origin-blocked from research egress)

`POST https://ms-mt--api-web.spain.advgo.net/search` (and `/v2/search`), all methods, with documented headers + warmed session cookies:
```
STATUS 502
server: CloudFront
x-cache: Error from cloudfront
x-amz-cf-id: zfkGKh-rAe8p5aajJAbGp7DiYz0afdz0JHIRulA3A1Pw9TYhLOqB2g==
<title>ERROR: The request could not be satisfied</title>
502 ERROR ... "CloudFront wasn't able to resolve the origin domain name."
Request ID: zfkGKh-rAe8p5aajJAbGp7DiYz0afdz0JHIRulA3A1Pw9TYhLOqB2g==
```
And from a **real Chromium page** on `www.coches.net` calling the API via in-page `fetch()`: `TypeError: Failed to fetch` (CORS/preflight rejected at the edge).

**Interpretation [VERIFIED]:**
- The host **is real**: DNS resolves `ms-mt--api-web.spain.advgo.net` → `143.204.55.x` (AWS CloudFront edge IPs, same range as coches.net itself). The brief's candidate host is **structurally correct**, not invented.
- The `502` carries a CloudFront `Request ID` and `x-cache: Error from cloudfront` with the message *"wasn't able to resolve the origin domain name"* — this is an **origin-resolution failure at the CloudFront distribution**, i.e. the distribution's backend origin is not served to this edge/region. It is **not** a bot block (no 403, no challenge page, no JS/captcha) and **not** TLS-fingerprint related (it fails identically with full Chrome impersonation and from a real browser).
- Most probable cause: the API's origin is **geo-restricted to Spain / Adevinta internal network** (the host literally contains `.spain.advgo.net`). The site's own front-end never calls it from the browser — the Next.js **SSR backend** (server-to-server, inside the allowed network) calls it and inlines the result into the HTML. That is why the browser `fetch` is CORS-blocked and the public egress gets a 502.

> **Consequence for CARDEX:** to call the JSON API directly you need **Spanish (or Adevinta-allowed) egress** — a Spain residential/datacenter proxy. Without it, scrape the **SSR HTML**, which already contains the identical structured payload (§3) and is reachable from anywhere.

---

## 2. Endpoint — internal Adevinta search API [VERIFIED host / ASSUMED exact body]

```
POST https://ms-mt--api-web.spain.advgo.net/search
Content-Type: application/json
```

- **Method:** POST, JSON body. The brief's `/search` candidate is the right host+path family; a `/v2/search` variant resolves to the same distribution (both 502 from this egress, so neither could be exercised to 200 here).
- **Required headers (from brief + Adevinta convention; NOT exercised to a 200 from this egress):**
  ```
  x-adevinta-channel: web-desktop
  x-schibsted-tenant: coches
  Content-Type: application/json
  Origin:  https://www.coches.net
  Referer: https://www.coches.net/
  Accept:  application/json, text/plain, */*
  ```
  These header names are confirmed as the brief's candidates and consistent with Adevinta's `/api-web` gateway convention seen in the site bundle (`SECURED_API_ROUTE: "/api-web"`), but because every call from this egress 502'd at the origin, the **exact body schema below is reconstructed from the SSR response + brief**, marked ASSUMED for the request, VERIFIED for the response.

- **Request body (candidate, ASSUMED — mirrors brief and SSR filter state):**
  ```json
  {
    "pagination": { "page": 1, "size": 30 },
    "sort": { "order": "desc", "term": "relevance" },
    "filters": {
      "categoryType": "Car",
      "isFinanced": false,
      "offerTypeIds": [0],
      "price": { "from": null, "to": null },
      "year":  { "from": null, "to": null }
    }
  }
  ```
  The SSR hydration state exposes the **filter vocabulary the API consumes** (VERIFIED present in page): `price:{from,to}`, `year:{from,to}`, `sortBy:"relevance"`, `sortOrder:"DESC"`, `page:1`, `provinceIds:[]`, `make/model` objects, `offerType`. So year/price are **`{from,to}` range objects** and sort is `sortBy`+`sortOrder` — map these into the POST `filters`/`sort`.

---

## 3. Response shape + listing-URL extraction [VERIFIED via SSR]

The SSR HTML for `/segunda-mano/` inlines the search response as escaped JSON. The ad list array key is **`items`**, e.g.:
```
...}],"items":[{"bodyTypeId":6,"creationDate":"2023-05-23T14:35:23Z","hp":150,
"fuelType":"Diésel","fuelTypeId":1,"hasReservation":true,"hasWarranty":true,
"id":"55146498","img":"https://a.ccdn.es/cnet/vehicles/13447986/<uuid>.jpg",
"isFinanced":false,"isProfessional":true,"isUrlSemantic":true,"km":103100,
"location":{"provinceIds":[20],"regionId":18,"regionLiteral":"País Vasco",
            "mainProvince":"Guipúzcoa","mainProvinceId":20},
"make":"LAND-ROVER","makeId":24,"model":"Discovery Sport","modelId":1134,
"pack":{"legacyId":30,"type":"expert"},"price":18800,
"url":"/land-rover-discovery-sport-20l-ed4-110kw-150cv-4x2-pure-5p-diesel-2018-en-guipuzcoa-55146498-covo.aspx",
"offerType":{"id":0,"literal":"Ocasión"},"phone":"943380403","photos":[...]}]
```

Per-ad fields (VERIFIED): `id`, `url`, `make/makeId`, `model/modelId`, `price`, `km`, `hp`, `fuelType/fuelTypeId`, `bodyTypeId`, `offerType{id,literal}`, `location{provinceIds,mainProvince,...}`, `isProfessional`, `isFinanced`, `hasWarranty`, `creationDate`, `img/imgUrl`, `photos[]`, `phone`.

**Listing-URL field = `url`** (relative `.aspx` path provided directly by the API — do NOT hand-build a slug). Build the detail URL by prefixing the host:
```
url:        /land-rover-discovery-sport-...-2018-en-guipuzcoa-55146498-covo.aspx
Detail URL: https://www.coches.net/land-rover-discovery-sport-...-55146498-covo.aspx
ID field:   id  (numeric, e.g. "55146498")
Pattern:    /{make}-{model}-{specs}-{year}-en-{province}-{id}-{dealer}.aspx
```
The brief's guessed pattern `{slug}-{id}.aspx` is essentially right — the slug+id is supplied verbatim in `url`, so just concatenate `https://www.coches.net` + `url`.

Faceted totals are embedded too (`"totalResults":N` per facet bucket); the page meta reports **~249,700** total cars.

---

## 4. Pagination + result cap [VERIFIED schema / ASSUMED cap]

- **Page param:** `pagination.page` in the POST body; SSR mirrors it as `page` and via URL `?pagina=N`.
- **Page size:** `pagination.size` (site default 30). SSR `items` array carries the page of ads.
- **Pagination is SSR:** navigating `/segunda-mano/?pagina=2` reloads the full HTML server-side (no client XHR) — so for the HTML path, enumerate by incrementing `?pagina=N` and parsing `items` from each rendered page.
- **Result cap:** Adevinta marketplaces (incl. coches.net) historically cap deep pagination around **~100 pages** (the pager does not expose links beyond it). Exact cap could not be exercised from this egress (API 502) — **ASSUMED ~100 pages**; with size 30 that is **~3,000 listings/query** against ~249k total → **search-grid partitioning is mandatory**.

---

## 5. Recommended search-grid partition

Each cell must resolve under the deep-pagination cap (~3k assumed). Use the per-facet `totalResults` already returned in every response to size cells cheaply.

Algorithm:
1. Issue a broad search; read facet `totalResults` (makes, provinces, price buckets all come back as facets).
2. Split by **make** (`makeId`) → re-read each make's `totalResults`.
3. If a make cell exceeds the cap, split by **year** (`filters.year.from/to`, per-year).
4. If a (make × year) cell still exceeds the cap, split by **price** bucket (`filters.price.from/to`).
5. Optionally split by **province** (`filters.provinceIds` / facet `provinceIds`) for the highest-volume makes.
6. Enumerate `pagination.page = 1..ceil(count/size)` capped at the deep-pagination limit per cell; dedupe globally on `id`.

Facets are returned inline, so adaptive sizing needs no extra endpoint.

---

## 6. Recommended tier

**Tier depends on egress:**

- **From Spanish/Adevinta-allowed egress → Tier T1–T2 (JSON API).** The POST `/search` API is a clean JSON endpoint (no Cloudflare/Akamai/DataDome seen). With a **Spain proxy** it should answer 200 to `curl_cffi impersonate="chrome"` + the `x-adevinta-channel`/`x-schibsted-tenant` headers. Classed T1 (TLS impersonation likely sufficient) trending T2 if Adevinta enforces sensor/session validation at scale. **This path must be validated once from Spanish egress to upgrade the request body from ASSUMED → VERIFIED.**

- **From any egress → Tier T1 (SSR HTML).** `GET /segunda-mano/?pagina=N` returns 200 server-rendered HTML containing the identical `items` payload (price, year, km, make/model, `url`, `id`, photos). `curl_cffi impersonate="chrome"` reaches it cleanly; no browser strictly required for parsing the inlined JSON. This is the **reliable fallback** that sidesteps the geo-restricted API entirely.

Tier summary:
- SSR-HTML listing enumeration + core fields (`items` blob) → **T1** (curl_cffi, any region). **Recommended default.**
- Internal JSON `/search` API → **T1/T2, Spain egress required** (502 origin-block without it).
- Detail-page (`.aspx`) enrichment → **T1** (HTML, same CloudFront; not separately exercised).

---

## Confidence ledger

| Finding | Status |
|---|---|
| CloudFront front, NO Cloudflare/DataDome on listing path | **VERIFIED** (headers/cookies) |
| API host `ms-mt--api-web.spain.advgo.net` is real (DNS → CloudFront 143.204.55.x) | **VERIFIED** |
| API 502 = CloudFront origin-resolution/geo failure, NOT bot block | **VERIFIED** (502 + `x-cache: Error from cloudfront` + CF Request ID; identical under full impersonation & real browser) |
| Browser in-page `fetch` to API → CORS `Failed to fetch` (front-end never calls it directly) | **VERIFIED** |
| Listing array key = `items`; URL field = `url` (`.aspx`); id = `id` | **VERIFIED** (SSR sample) |
| Detail URL = `https://www.coches.net` + `url`; pattern `...-{id}-{dealer}.aspx` | **VERIFIED** (real sample) |
| Per-ad fields (make/model/price/km/hp/fuel/location/offerType/photos) | **VERIFIED** (SSR sample) |
| Filter vocabulary: `price{from,to}`, `year{from,to}`, `sortBy`/`sortOrder`, `provinceIds`, `make/model`, `categoryType:"Car"`, `offerTypeIds` | **VERIFIED present in SSR state** |
| SSR HTML reachable + carries full first-page payload | **VERIFIED** |
| Pagination is SSR via `?pagina=N`; body `pagination.page/size` | **VERIFIED** (HTML) / schema mirrors brief |
| Exact POST request body (`/search`) returns 200 with given headers | **ASSUMED** (host 502s from this egress; needs Spain proxy to confirm) |
| `/v2/search` variant existence/shape | **ASSUMED** (same host, both 502 here) |
| Required headers `x-adevinta-channel` / `x-schibsted-tenant` enforced | **ASSUMED** (brief + Adevinta `/api-web` convention; not exercised to 200) |
| Deep-pagination cap ~100 pages (~3k/query) | **ASSUMED** (Adevinta norm; not exercised) |
