# mobile.de — Scraping Research (CARDEX engine)

> Research date: 2026-06-03. Method: `curl_cffi` 0.15.0 (`impersonate="chrome"`) via Bash + Playwright (real Chromium) for in-browser network/DOM capture + WebSearch/WebFetch for corroboration. Every endpoint below was actually hit. Marketing claims from third-party scrapers (Apify/Carapis) were treated as leads only and independently verified or rejected.

---

## 1. Anti-bot stack — Akamai Bot Manager [VERIFIED]

mobile.de fronts its HTML/document surfaces with **Akamai (Akamai Bot Manager)**. No DataDome, no Cloudflare, no custom WAF observed.

### Evidence (real fetches)

`GET https://www.mobile.de/` and `GET https://suchen.mobile.de/fahrzeuge/search.html?...` via `curl_cffi impersonate=chrome`:

```
STATUS 403
server: AkamaiGHost
x-akamai-transformed: 0 - 0 -
akamai-request-bc: [a=...,c=g,n=IT_25_MILANO,...]
akamai-grn: 0.75f01202.1780502167.662ae8d
set-cookie: bm_ss=...; _abck=...~-1~...; bm_s=...; bm_so=...; bm_sz=...
<title>Zugriff verweigert / Access denied</title>
... "Reference: 0.75f01202.1780502188.662c01c"
```

### Block signature (record these)

- **HTTP 403** + `server: AkamaiGHost`.
- Response body ~7.8 KB, `<title>Zugriff verweigert / Access denied</title>`, contains an Akamai `Reference: 0.<hex>.<ts>.<hex>` number and a `mobile.de` logo header (custom-branded Akamai deny page, font `YouthBase`).
- Cookies set: `bm_ss`, `bm_s`, `bm_so`, `bm_sz`, and **`_abck`**. The `_abck` value ending in **`~-1~`** = sensor data **not** validated → request is blocked. A validated session shows `~0~` / `~N~` (N>0). This `~-1~` token is the single most reliable programmatic block indicator.
- Akamai cookie set (`bm_*` + `_abck`) is present on ALL responses, including the ones that return 200 JSON — it is set opportunistically; presence of the cookie does NOT mean blocked. **Use status code + body title + `_abck ~-1~`, not mere cookie presence.**

### What passes vs. what is blocked [VERIFIED]

| Surface | curl_cffi (no browser) | Real browser top-level nav |
|---|---|---|
| `www.mobile.de/` (doc) | 403 block | 200 |
| `suchen.mobile.de/.../search.html` (SRP doc) | 403 block | **200** |
| `m.mobile.de/.../search.html` | 403 block | 200 |
| `/consumer/api/search/srp` (JSON) | reaches SVC backend, 400 on bad params (NOT Akamai-blocked) | 200 (XHR has valid sensor) |
| `/consumer/api/search/hit-count` (JSON) | **200 `{"count":N}`** even with `_abck ~-1~` | 200 |
| In-page `fetch(location.href)` from a real browser | n/a | **403 block** (8.3 KB deny page) — secondary fetches lack the navigation sensor |

Key insight: Akamai gates **top-level HTML document navigations** and the SRP JSON route hard. It does **not** gate the lightweight `hit-count` JSON GET. Datacenter IP was used throughout (no proxy) and `hit-count` still returned 200, so that endpoint is effectively open.

---

## 2. Endpoints

### 2a. Public HTML search (SRP) — PRIMARY for URL enumeration [VERIFIED]

```
GET https://suchen.mobile.de/fahrzeuge/search.html
```

Server-rendered HTML. Listing detail links are embedded directly in the markup as `<a href="/fahrzeuge/details.html?id=...">` (24 per page in the rendered DOM). Also a pre-hydration `window.__INITIAL_STATE__` blob carries the structured results at `search.srp.data.searchResults` with `numResultsTotal` — but this object is **consumed/cleared during React hydration**, so for a headless scraper the durable surface is **the `<a>` hrefs in the HTML**, not the JS state.

#### Verified query params (captured from the live SRP request the site itself issued)

| Param | Meaning | Verified example |
|---|---|---|
| `vc` | vehicle class | `Car` |
| `s` | search class (mirrors vc) | `Car` |
| `ms` | make;model;modelDescription;variant (semicolon-delimited; make-id numeric) | `3500;;;` (3500 = BMW) |
| `fr` | first-registration year range `from:to` | `2020:2024` |
| `p` | price range `min:max` (EUR), open-ended allowed | `:30000` (≤30k), `5000:20000` |
| `dam` | direct-after-market / damaged flag | `false` |
| `sb` | sort field | `rel` (relevance) |
| `od` | order direction | `up` / `down` |
| `ref` | referrer context | `srp` |
| `isSearchRequest` | required flag | `true` |
| `pageNumber` | page (see pagination) | `1`..`50` |

> Year filter is **`fr=YYYY:YYYY`** (range), NOT `minFirstRegistrationDate`/`yearFrom` (those are official-API style, not the public-site style). Price is **`p=min:max`**, NOT `minPrice`/`maxPrice`. The `mnp/mxp` and standalone `ms/fr/ft` names quoted by Apify/Carapis pages are paraphrased/partly inaccurate — the verified live names are the table above.

#### Listing-URL extraction pattern [VERIFIED]

DOM: `a[href*="/fahrzeuge/details.html"]`. Raw-HTML regex:

```
/\/fahrzeuge\/details\.html\?id=(\d+)/g
```

Real sample hrefs captured:
```
/fahrzeuge/details.html?id=445897737&action=topOfPage&dam=false&fr=2020%3A2024&...&searchId=819b74d6-...&vc=Car
/fahrzeuge/details.html?id=456975742&dam=false&fr=2020%3A2024&...&vc=Car
/fahrzeuge/details.html?id=457003020&action=eyeCatcher&...
```

The canonical key is the numeric **`id`**. Canonicalize to:

```
https://suchen.mobile.de/fahrzeuge/details.html?id=<ID>
```

(strip all tracking params: `action`, `ref`, `refId`, `searchId`, `dam`, `fr`, `ms`, `p`, `s`, `sb`, `od`, `isSearchRequest`). The `id` is the stable mobile.de ad id (a.k.a. `mobileAdId`).

### 2b. Internal JSON API — `/consumer/api/search/` [VERIFIED, partial]

Host: `www.mobile.de` (also `m.mobile.de`, Akamai-gated). This is the site's own consumer backend that proxies to an internal "SVC API".

- `GET /consumer/api/search/srp` → returns SRP JSON. With wrong/guessed params returns **HTTP 400** `{"error":{"errors":[{"domain":"search/srp/getSrpData","reason":"ApiRequestFailed","message":"SVC API request failed"}],...}}`. Reaches the backend via curl_cffi (NOT Akamai-blocked at the edge), but the exact body/param schema the SVC layer expects could not be fully reconstructed from outside — the site fetches SRP via server-side render, not a clean documented XHR, so this route is **[ASSUMED-usable but schema-unconfirmed]**. Do not rely on it without first capturing a 200 call from devtools.
- `GET /consumer/api/search/hit-count?<same SRP params>` → **[VERIFIED]** `200 application/json` `{"count":14205}`. Open (returned 200 from datacenter IP via curl_cffi). Use for partition-size estimation.
- `GET /consumer/api/search/reference-data/makes/Car` → returns the SPA HTML shell (not JSON) when hit cold; reference data (make-id → name map, e.g. BMW=3500) is delivered inside the app bundle/state. **[ASSUMED]** for a clean JSON refdata route; not confirmed.

### 2c. Official Search API (services.mobile.de) — paid/credentialed [VERIFIED via docs]

```
GET https://services.mobile.de/search-api/search?<params>
HTTP Basic auth (username:password) — MANDATORY, requires an activated API account.
```
- make/model: `classification=refdata/classes/Car/makes/AUDI/models/A4`
- year: `firstRegistrationDate.min` / `.max` (gYearMonth `2007-01`)
- price: `price.min` / `price.max` (EUR)
- pagination: `page.number` (from 1), `page.size` (default 20, max 100)
- **hard cap: 2000 ads per query** (20 pages @ size 100)
- response fields: **`mobileAdId`** (id), **`detailPageUrl`** (full detail URL)

This is the cleanest data source IF a dealer/partner account is obtainable. It is gated behind a commercial agreement, so it is out of scope for an anonymous scraping tier but is the gold standard if access is acquired.

---

## 3. Pagination + result cap [VERIFIED]

- **Page param:** `pageNumber` (URL query on search.html).
- **Page size:** ~**20–24** listings per page (24 in initial relevance-sorted page incl. promoted ads; 20 on deeper pages). Treat as **20** for planning.
- **Hard cap:** pagination control tops out at **page 50** (`maxPageButton: 50` read from the live pager). Requesting `pageNumber=99` does NOT error — mobile.de clamps to the last accessible page and still serves listings, but no pager link beyond 50 exists.
- **Effective ceiling per search:** 50 pages × ~20 = **~1000 unique listings**, even when `numResultsTotal` / `hit-count` reports 14,205 (verified for BMW 2020–2024 ≤30k EUR). This is the classic AutoScout24-style cap → **search-grid partitioning is mandatory**.

---

## 4. Detail-page URL pattern [VERIFIED]

```
Raw:        /fahrzeuge/details.html?id=457003020&action=...&ref=srp&searchId=...
Canonical:  https://suchen.mobile.de/fahrzeuge/details.html?id=457003020
Regex id:   /\/fahrzeuge\/details\.html\?id=(\d+)/
ID field:   numeric mobileAdId
```

---

## 5. Recommended search-grid partition

Each (make[/model]) × (year-bucket) × (price-bucket) cell must resolve to ≤ ~1000 results. Use `hit-count` (open JSON) to size cells adaptively before enumerating.

Algorithm:
1. For each make-id (`ms=<makeId>;;;`), call `hit-count`.
2. If count > ~1000, split by `fr` year buckets (e.g. per-year `fr=2020:2020`).
3. If a (make × year) cell still > ~1000, split by `p` price buckets (e.g. `:5000`, `5000:10000`, `10000:20000`, `20000:40000`, `40000:`).
4. If still > ~1000 (high-volume make/year like VW Golf), add `model` into `ms` (`ms=25100;9;;`) and/or finer price/mileage (`ml=` mileage range) buckets.
5. Enumerate `pageNumber=1..ceil(count/20)` capped at 50 per cell; dedupe ids globally.

Adaptive recursion on `hit-count` keeps every cell under the cap with minimal wasted requests, and `hit-count` is unauthenticated/un-blocked so probing is cheap.

---

## 6. Recommended tier

**Tier T2 (headful/stealth browser required for the listing pages).**

Rationale:
- The SRP HTML document (the only surface that yields listing URLs in bulk) is hard-gated by Akamai Bot Manager. Plain `curl_cffi` is **403-blocked** on it — TLS impersonation alone is insufficient because Akamai requires a valid `_abck` sensor payload generated by real browser JS.
- A real Chromium top-level navigation passes cleanly (verified: 200, 24 links/page) with no proxy on a datacenter IP, but secondary in-page `fetch()` is blocked — so a headless/stealth **browser doing top-level navigations** (Playwright + stealth, or a hardened Camoufox/patchright) is the reliable engine. Rotate residential/mobile proxies if scaling triggers rate IP bans.
- `hit-count` JSON is open (T0-level) and should be used for grid sizing without a browser.
- If a commercial Search-API account is obtained, that path drops to **T0** (clean authenticated REST, `detailPageUrl` provided) but caps at 2000/query.

Tier summary:
- `hit-count` partition sizing → **T0** (curl_cffi, open).
- SRP listing-URL enumeration → **T2** (stealth browser, top-level nav, proxy rotation at scale).
- `/consumer/api/search/srp` JSON → **T2/T3** (reaches backend but schema unconfirmed; only via a real browser-captured 200 call).
- Official Search-API → **T0 if credentialed** (out of scope for anonymous scraping).

---

## Confidence ledger

| Finding | Status |
|---|---|
| Akamai Bot Manager (403, AkamaiGHost, `_abck ~-1~`, branded deny page) | **VERIFIED** |
| No DataDome/Cloudflare/custom | **VERIFIED** (headers) |
| SRP doc URL + params (`vc,s,ms,fr,p,dam,sb,od,ref,pageNumber`) | **VERIFIED** (live capture) |
| Listing-URL pattern `/fahrzeuge/details.html?id=\d+` (24/page) | **VERIFIED** (DOM) |
| `hit-count` open JSON `{"count":N}` | **VERIFIED** (curl_cffi 200) |
| Page size ~20, **page cap 50**, ~1000/search ceiling | **VERIFIED** (live pager) |
| `numResultsTotal` in `__INITIAL_STATE__` (cleared on hydration) | **VERIFIED** |
| `/consumer/api/search/srp` JSON usable schema | **ASSUMED** (reaches backend, schema unconfirmed) |
| Official Search-API params/caps/fields | **VERIFIED via docs** (not exercised — needs account) |
| curl_cffi blocked on SRP doc; browser nav passes | **VERIFIED** |
