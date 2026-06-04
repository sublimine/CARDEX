# leboncoin.fr — Car Listings (voitures) Scraping Research

**Source category:** `voitures` (cars), category id `"2"` under parent `"1"` (Véhicules).
**Date of live tests:** 2026-06-03 (UTC).
**Tooling:** Python `curl_cffi` 0.15.0, `impersonate="chrome"`.
**Tier:** **T3 — DataDome (hardest)**. Internal JSON API exists and is clean, but every endpoint sits behind DataDome with aggressive behavioral/rate scoring. Datacenter IP gets a brief honeymoon then a sticky block.

---

## 1. Anti-bot reality — DataDome [VERIFIED]

leboncoin fronts both the website and the API with **DataDome** (behind CloudFront). Confirmed live by direct fetch.

### WAF evidence (captured live)

Response headers on a blocked request (`POST api.leboncoin.fr/finder/search`, no api_key):

```
status: 403
content-type: application/json;charset=utf-8
x-datadome: protected
x-datadome-cid: AHrlqAAAAAMA-X43WukBHLAAU03p_A==
x-dd-b: 1
set-cookie: datadome=tzX9ieRUNKohdKNIqiVq6Hv2EG...; Max-Age=31536000; Domain=.leboncoin.fr; Secure; SameSite=Lax
access-control-expose-headers: x-dd-b, x-set-cookie
via: 1.1 ...cloudfront.net (CloudFront)
```

Blocked response **body** is a DataDome captcha-delivery redirect (the canonical signature):

```json
{"url":"https://geo.captcha-delivery.com/captcha/?initialCid=AHrlqAAAAAMA-X43WukBHLAAU03p_A==&cid=tzX9ie...&referer=https%3A%2F%2Fapi.leboncoin.fr%2Ffinder%2Fsearch&hash=05B30BD9055986BD2EE8F5A199D973&t=fe&s=7501&e=...&b=27373"}
```

**DataDome signature to detect in CARDEX:** HTTP 403 + header `x-datadome: protected` (or `x-dd-b: 1`) + JSON body containing `geo.captcha-delivery.com`. The `datadome` cookie is always set (even on 200s).

### Honeymoon-then-burn behavior [VERIFIED] — the critical operational fact

From a single residential-ish/datacenter IP with curl_cffi chrome impersonation:

1. First ~5–10 requests with the right headers (see §2) returned **HTTP 200 with real data**.
2. After ~10 rapid requests, **every** request — including `offset=0` and even the HTML page `GET /recherche` — flipped to **403 DataDome**.
3. An 8s cooldown did **not** clear it (block is sticky at IP/TLS-fingerprint level, not per-request).
4. Pre-fetching the HTML page to "earn" a good `datadome` cookie did **not** help once the IP was flagged — the GET itself was challenged.

**Conclusion:** curl_cffi alone is NOT viable for sustained enumeration. It works for a tiny burst then the IP burns. Production needs **rotating French residential proxies** + low per-IP request budget + human-like pacing/jitter. External corroboration (Scrapfly) confirms DataDome scores on **TLS/JA3 fingerprint, browser fingerprint (navigator/WebGL), and IP reputation (datacenter IPs face stricter checks; French residential IPs needed)**. curl_cffi solves only the TLS/JA3 axis — it does not solve IP reputation or behavioral scoring.

---

## 2. Internal search API [VERIFIED]

**Endpoint:** `POST https://api.leboncoin.fr/finder/search`
**Content-Type:** `application/json`

### Required headers [VERIFIED]

| Header | Value | Notes |
|---|---|---|
| `api_key` | `ba0c2dad52b3ec` | **REQUIRED.** Without it → instant 403 DataDome. Hardcoded public app key (also present in public repo `thomasync/leboncoin-api-search/src/constants.ts`). Not a secret/account key. |
| `Content-Type` | `application/json` | required |
| `Origin` | `https://www.leboncoin.fr` | recommended |
| `Referer` | `https://www.leboncoin.fr/` (or `/recherche?category=2`) | recommended |
| `Accept` | `*/*` | — |
| `Accept-Language` | `fr-FR,fr;q=0.9,en;q=0.8` | — |

> **Live proof:** identical request *without* `api_key` → 403 DataDome challenge; *with* `api_key` + the above → 200 + JSON. The `api_key` alone is insufficient (DataDome still scores TLS/IP/behavior), but it is a hard precondition.

### Request body schema [VERIFIED]

Minimal working body:

```json
{
  "filters": { "category": { "id": "2" }, "enums": {}, "ranges": {} },
  "limit": 35,
  "offset": 0,
  "sort_by": "time",
  "sort_order": "desc"
}
```

Full filtered body (all fields below tested live, returned 200 + correctly-filtered results):

```json
{
  "filters": {
    "category": { "id": "2" },
    "enums": { "u_car_brand": ["RENAULT"] },
    "ranges": {
      "regdate": { "min": 2018, "max": 2020 },
      "price":   { "min": 5000, "max": 15000 }
    },
    "location": {
      "locations": [
        { "locationType": "department", "department_id": "75" }
      ]
    }
  },
  "limit": 35,
  "offset": 0,
  "sort_by": "time",
  "sort_order": "desc"
}
```

Field reference:

| Field | Type | Verified | Notes |
|---|---|---|---|
| `filters.category.id` | string | [VERIFIED] | `"2"` = voitures |
| `filters.enums.u_car_brand` | string[] | [VERIFIED] | brand filter; uppercase make (e.g. `"RENAULT"`). Other car enums (`fuel`, `gearbox`, `vehicule_color`, `u_car_model`) [ASSUMED] from public repos — not individually tested here |
| `filters.ranges.regdate` | {min,max} int | [VERIFIED] | **registration YEAR** (e.g. 2018). This is the year-partition axis |
| `filters.ranges.price` | {min,max} int | [VERIFIED] | EUR |
| `filters.ranges.mileage` | {min,max} int | [ASSUMED] | from public repos; not tested |
| `filters.location.locations[]` | array | [VERIFIED] | `{locationType:"department", department_id:"75"}` worked. Also supports region/city/zipcode shapes [ASSUMED] |
| `limit` | int | [VERIFIED] | 35 used by site; larger values [ASSUMED] capped |
| `offset` | int | [VERIFIED] | see §3 |
| `sort_by` | string | [VERIFIED] | `"time"` worked; `"price"`/`"relevance"` [ASSUMED] from repos |
| `sort_order` | string | [VERIFIED] | `"desc"` worked; `"asc"` [ASSUMED] |

### Response schema [VERIFIED]

Top-level (live): 

```
total, total_all, total_pro, total_private, max_pages, referrer_id, pivot, ads[]
```

- `total` = match count (e.g. `782505` for all cars; `93` for the filtered query).
- `max_pages` = **server-computed page cap for THIS query** (e.g. `100` unfiltered, `3` for the 93-result query). See §3.
- `pivot` = stringified JSON with `ids_to_display`, `es_pivot`, `reranker_offset`, `page_number` — Elasticsearch cursor (alternative to offset paging).
- **`ads`** = the array of listings.

Per-ad keys (live):

```
list_id, first_publication_date, index_date, status, category_id, category_name,
subject, body, brand, ad_type, url, price, price_cents, images, attributes,
location, owner, options, has_phone, attributes_adview_positive,
attributes_characteristics, is_boosted, similar, counters
```

### Listing URL / ID — [VERIFIED]

- **`list_id`** (int) is the canonical ad ID, e.g. `3209868457`.
- **`url`** is returned directly, pre-built: `https://www.leboncoin.fr/ad/voitures/{list_id}`
  (live example: `https://www.leboncoin.fr/ad/voitures/3202993191`).
- Modern detail-URL pattern: **`https://www.leboncoin.fr/ad/voitures/{list_id}`** (no `.htm`).
- Legacy pattern `https://www.leboncoin.fr/voitures/{list_id}.htm` still resolves via redirect [ASSUMED — not re-tested live]. **Prefer the `url` field as-is**; it requires no construction.

> For pure URL/ID enumeration the search response is self-sufficient: each ad already carries both `list_id` and a ready `url`. No detail fetch is needed to build the ID set, and the search payload already includes price/brand/regdate/location for cheap pre-filtering.

---

## 3. Pagination + result cap [VERIFIED / partially ambiguous]

- Paging is `limit` + `offset` (site uses `limit=35`). A `pivot` cursor is also available for deep ES paging.
- The response field **`max_pages`** is the explicit per-query cap. Unfiltered cars → `max_pages: 100`. At `limit=35`, 100 pages = **~3,500 results max reachable per query**.
- Live test: `offset` 3465 / 3500 / 9999 all returned 403 — **but the same run also burned the IP** (subsequent `offset=0` also 403). So the high-offset 403 is confounded by DataDome rate-burn and does not cleanly isolate the hard cap value.
- **Best-supported conclusion:** the hard cap is **`max_pages` (≈100 pages → ~3,500 results)** per query, server-enforced. (Some public references cite a 1000-offset cap on other leboncoin categories; for cars the live `max_pages:100` field is the authoritative signal. Treat the practical reachable ceiling as **~3,500 results / query**.) [VERIFIED max_pages field; exact offset-cap value ASSUMED ≈ max_pages*limit]

### Grid-partitioning requirement

`total` for all cars ≈ **782,505**, but only ~3,500 are reachable per query. Full enumeration therefore **mandates partitioning** so every partition stays under the cap:

Recommended partition axes (all VERIFIED as working filters):

1. **Department** (`filters.location.locations[].department_id`) — ~96 metropolitan departments.
2. **regdate / year** (`filters.ranges.regdate`) — partition by single year or year-bucket.
3. **price** (`filters.ranges.price`) — fallback split when a (dept × year) cell still exceeds the cap.

Strategy: iterate department × year; for each cell read `total`; if `total > cap` (~3,500) recursively split by `price` (and, if still over, by `brand` via `enums.u_car_brand`). Page each leaf cell with `offset` 0…(min(total,cap)) at `limit=35`. Dedupe by `list_id` across overlapping cells.

This keeps each query under `max_pages` and gives near-complete coverage of the ~780k inventory.

---

## 4. CARDEX integration notes

- **Tier: T3 (DataDome).** Needs the residential-proxy + behavioral stack, not bare curl_cffi.
- **Required constant:** `api_key: ba0c2dad52b3ec` (public app key; monitor for rotation — if it changes, scrape it from the site's JS bundle or `__NEXT_DATA__`).
- **Block detector:** treat `403 + x-datadome:protected` / body containing `geo.captcha-delivery.com` as a DataDome block → rotate IP, back off, do NOT hammer.
- **Per-IP budget:** keep well under ~10 requests/IP/short-window based on observed burn; add jitter; rotate French residential IPs.
- **Enumeration is API-only and cheap:** the `/finder/search` response yields `list_id` + ready `url` + key attributes per ad; no per-ad detail fetch needed just to build the URL/ID universe.
- **Cap-driven crawl plan:** dept × regdate(year) grid, recursive price/brand split when `total` > ~3,500, page with limit=35/offset, dedupe on `list_id`.

---

## Confidence summary

| Claim | Confidence |
|---|---|
| DataDome on all endpoints; 403 + `x-datadome:protected` + `geo.captcha-delivery.com` body | [VERIFIED] |
| curl_cffi works briefly then IP burns; residential+behavioral required | [VERIFIED] |
| `POST api.leboncoin.fr/finder/search` returns 200 JSON with `api_key` header | [VERIFIED] |
| `api_key = ba0c2dad52b3ec` required; public key (repo-corroborated) | [VERIFIED] |
| category id `"2"`; body schema filters/enums/ranges/limit/offset/sort | [VERIFIED] (core fields), [ASSUMED] (extra enums) |
| `regdate`, `price`, `u_car_brand`, department location filters work | [VERIFIED] |
| ads array `ads[]`; per-ad `list_id` + ready `url` (`/ad/voitures/{id}`) | [VERIFIED] |
| `max_pages` cap (~100 pages → ~3,500 results/query) | [VERIFIED] (field), exact offset ceiling [ASSUMED] |
| Grid partition (dept × year × price/brand) mandatory for full coverage | [VERIFIED] (driven by total≈782k vs ~3.5k cap) |
