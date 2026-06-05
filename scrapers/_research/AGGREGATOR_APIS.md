# Aggregator APIs — Published Specifications

Captured from official docs/SDK only. Every concrete fact is tagged
`[VERIFIED from docs]` (read directly from an official source) or
`[not documented publicly]`. Nothing here was invented; where the public
sources disagree with each other, the conflict is flagged explicitly.

> Research date: 2026-06-03. APIs may change; re-verify before implementing.

---

## IMPORTANT: carapis.com publishes THREE inconsistent API surfaces

The single biggest risk for an implementer. carapis.com's own documentation
describes at least three different, mutually inconsistent request shapes. They
cannot all be literally true simultaneously. Do **not** assume one canonical
surface — pick based on which doc page your API key/plan actually targets, and
confirm against a live `401`/`200` before building. The three surfaces:

1. **v2 "unified listings" API** — `GET https://api.carapis.com/v2/listings?source=<slug>`
   Source: `https://carapis.com/api/intro` (marketing-site getting-started).
2. **v1 per-parser "search" API** — `POST https://api.carapis.com/v1/parsers/<platform>/search`
   Source: `https://docs.carapis.com/parsers/<platform>/api-reference`.
3. **v1 per-parser "vehicles" API** — `GET https://api.carapis.com/v1/<parser>/vehicles`
   Source: `https://docs.carapis.com/api/endpoints` and `/api/authentication`.

All three are documented below verbatim. `[VERIFIED from docs]` means "this is
what that page literally says," not "this is confirmed to run."

---

# 1. carapis.com

Official docs read:
- `https://carapis.com/api/intro` (marketing-site getting-started)
- `https://docs.carapis.com/` , `https://docs.carapis.com/api/intro`
- `https://docs.carapis.com/api/authentication`
- `https://docs.carapis.com/api/endpoints`
- `https://docs.carapis.com/api/rate-limits`
- `https://docs.carapis.com/parsers/autoscout24.com/api-reference`
- `https://docs.carapis.com/parsers/mobile.de/api-reference`
- `https://docs.carapis.com/parsers/encar.com/api-reference`
- `https://carapis.com/pricing`

## Base URL(s)

- `https://api.carapis.com/v2` — for the v2 unified listings surface.
  `[VERIFIED from docs]` (carapis.com/api/intro: `requests.get("https://api.carapis.com/v2/listings", ...)`)
- `https://api.carapis.com/v1` — for the v1 per-parser surface.
  `[VERIFIED from docs]` (docs.carapis.com/api/authentication: base URL `https://api.carapis.com/v1/`;
  docs.carapis.com/api/endpoints: base URL `https://api.carapis.com/v1`)
- `https://api.carapis.com/v1/parsers/<platform>` — base for the per-parser
  "search" reference pages, e.g. `.../v1/parsers/autoscout24`,
  `.../v1/parsers/mobile.de`. `[VERIFIED from docs]` (per-parser api-reference pages)

> Conflict: the marketing docs use `/v2`; the developer docs (`docs.carapis.com`)
> use `/v1`. Both are published as current. `[VERIFIED from docs]`

## Auth

- Scheme: HTTP `Authorization` header, Bearer token.
  Header: `Authorization: Bearer <API_KEY>`. `[VERIFIED from docs]`
  (carapis.com/api/intro; docs.carapis.com/api/authentication)
- Alternative (v1 only): API key as query parameter `api_key=<API_KEY>`.
  `[VERIFIED from docs]` (docs.carapis.com/api/authentication:
  `curl "https://api.carapis.com/v1/encar/vehicles?api_key=YOUR_API_KEY"`)
- Example API-key format for the autoscout24 parser:
  `autoscout24_parser_sk_1234567890abcdef1234567890abcdef`. `[VERIFIED from docs]`
  (docs.carapis.com/parsers/autoscout24.com/api-reference)
- Keys obtained at `my.carapis.com`. `[VERIFIED from docs]` (carapis.com/api/intro)
- Failed-auth response: `401 Unauthorized`, message `"Invalid API key"`.
  `[VERIFIED from docs]` (docs.carapis.com/api/authentication)

## Endpoints

### Surface A — v2 unified listings (marketing docs)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/v2/listings` | List/search vehicles across a chosen `source` |

`[VERIFIED from docs]` (carapis.com/api/intro). No other v2 paths documented on
that page beyond nav links to Authentication / Listings / Pagination / Rate
limits / Errors. `[not documented publicly]` for v2 detail-by-id, dealers, etc.

### Surface B — v1 per-parser "search" (e.g. autoscout24, mobile.de)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/search` | Search vehicle listings |
| GET | `/extract/{vehicle_id}` | Extract single vehicle details (autoscout24) |
| GET | `/vehicle/{id}` | Single vehicle details (mobile.de) |
| POST | `/statistics` | Market statistics |
| POST | `/dealers/search` | Search dealers (autoscout24) |
| POST | `/batch-search` | Multiple searches in one call (autoscout24) |
| POST | `/monitor` | Real-time monitoring + webhook (autoscout24) |

Paths are relative to `https://api.carapis.com/v1/parsers/<platform>`.
`[VERIFIED from docs]` (autoscout24.com/api-reference, mobile.de/api-reference).
Note `mobile.de` documents `GET /vehicle/{id}` while autoscout24 documents
`GET /extract/{vehicle_id}` — the per-parser pages are not uniform. `[VERIFIED from docs]`

### Surface C — v1 per-parser "vehicles" (api/endpoints)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/encar/vehicles` | List Encar vehicles |
| GET | `/encar/vehicles/{id}` | Encar vehicle details |
| GET | `/che168/vehicles` | List Che168 vehicles |
| GET | `/che168/vehicles/{id}` | Che168 vehicle details |

Relative to `https://api.carapis.com/v1`. `[VERIFIED from docs]`
(docs.carapis.com/api/endpoints). The encar.com/api-reference page additionally
lists (base URL `[not documented publicly]` on that page):
`GET /vehicles`, `GET /vehicle/{id}`, `GET /dealers`, `GET /dealer/{id}`,
`GET /brands`, `GET /models/{brand}`, `GET /price-history/{id}`,
`GET /market-stats`. `[VERIFIED from docs]` (encar.com/api-reference)

## Request params

### Surface A (`GET /v2/listings`)
- `source` (required): platform slug. Documented example slugs: `encar`,
  `mobile-de`, `auto-ria`. `[VERIFIED from docs]` (carapis.com/api/intro)
- `limit` (optional): results per page. `[VERIFIED from docs]`
- Verbatim cURL: `curl "https://api.carapis.com/v2/listings?source=encar&limit=20" -H "Authorization: Bearer $CARAPIS_API_KEY"` `[VERIFIED from docs]`
- Other filters (make/model/year/price) for v2: `[not documented publicly]`
  (the dedicated `/api/listings` doc path returns 404; only `source`+`limit` shown).

### Surface B `POST /search` (autoscout24)
Body/params: `query`, `country`, `year_from`, `year_to`, `price_min`,
`price_max`, `fuel_type`, `transmission`, `body_type`, `location`,
`mileage_max`, `limit`, `page`. `[VERIFIED from docs]`
(autoscout24.com/api-reference)
- `POST /statistics` params: `country`, `make`, `model`, `year_from`,
  `year_to`, `metrics` (allowed: `price_distribution`, `market_share`,
  `trends`, `regional_analysis`, `seasonal_patterns`). `[VERIFIED from docs]`
- `POST /dealers/search` params: `country`, `city`, `brand`, `rating_min`,
  `limit`. `[VERIFIED from docs]`

### Surface B `POST /search` (mobile.de)
Params: `query`, `max_price`, `min_price`, `location`, `fuel_type`,
`transmission`, `year_from`, `year_to`, `mileage_max`, `mileage_min`, `limit`,
`offset`, `sort_by`, `sort_order`. `[VERIFIED from docs]`
(mobile.de/api-reference). (Note: mobile.de uses `min_price/max_price` +
`offset`, while autoscout24 uses `price_min/price_max` + `page` — not uniform.)

### Surface C (`GET /encar/vehicles`)
Params: `make`, `model`, `year`, `price_min`, `price_max`, `limit`
(default 50, max 100). Che168 variant uses `brand`, `series`, `year`,
`price_min`, `price_max`, `limit`. All endpoints also accept
`format` (`json`|`xml`) and `language` (`en`|`ko`|`zh`). `[VERIFIED from docs]`
(docs.carapis.com/api/endpoints)
- encar.com/api-reference variant params: `brand`, `model`, `year_min`,
  `year_max`, `price_min`, `price_max`, `location`, `limit` (max 100),
  `offset`. `[VERIFIED from docs]` (encar.com/api-reference)

## Response shape (vehicle)

### Surface A envelope (`/v2/listings`)
Paginated envelope; `results` is an array of listing objects. Documented top-level
fields: `count`, `page`, `limit`, `results`. Per-listing fields named in the docs:
`id`, `source`, `make`, `model`, `year`, `mileage`, `price`, `currency`,
`location`, `fuel_type`, `transmission`, `photos`, `dealer`, `url`.
`[VERIFIED from docs]` (carapis.com/api/intro — text names these fields and the
Python example iterates `data["results"]` reading `make`,`model`,`year`,`price`).
Note: `docs.carapis.com/api/intro` shows the source value under the key `parser`
(`"parser": "encar"`) rather than `source` — naming differs between the two
intro pages. `[VERIFIED from docs]`

### Surface C / per-parser vehicle fields
- Encar (api/endpoints): `id`, `make`, `model`, `year`, `price`, `mileage`,
  `location`, `seller`, `specifications` (nested: `engine`, `transmission`,
  `fuel_type`, `color`), `images`, `description`, `url`. `[VERIFIED from docs]`
- Encar (encar.com/api-reference): `id`, `title`, `brand`, `model`, `year`,
  `price`, `mileage`, `location`, `dealer_id`, `images`, `features`,
  `created_at`, `fuel_type`, `transmission`, `engine_size`, `color`,
  `original_price`, `description`, `history`. `[VERIFIED from docs]`
- mobile.de: `id`, `title`, `price` (nested: `amount`, `currency`, `formatted`,
  `negotiable`), `specifications` (nested: `year`, `mileage`, `fuel_type`,
  `transmission`, `engine_size`, `power`, `torque`, `emission_class`,
  `co2_emissions`, `fuel_consumption`, `doors`, `seats`, `color`, `body_type`),
  `location` (nested: `city`, `state`, `country`, `postal_code`, `coordinates`),
  `seller` (nested: `name`, `type`, `rating`, `reviews_count`, `certified`,
  `contact`), `features`, `images`, `url`, `extracted_at`, `last_updated`.
  `[VERIFIED from docs]` (mobile.de/api-reference)

> The per-parser response shapes differ substantially from each other and from
> the v2 envelope. Treat each parser's schema as parser-specific.

## Pagination

- Surface A envelope carries `count`, `page`, `limit`; request params `page`,
  `limit`. `[VERIFIED from docs]` (carapis.com/api/intro; docs.carapis.com/api/intro)
- Per-parser / v1 envelope carries `total`, `page`, `limit`, `pages`.
  `[VERIFIED from docs]` (docs.carapis.com/api/endpoints). Webmotors parser
  variant: `page`, `limit`, `total`, `total_pages`. `[VERIFIED from docs]`
- mobile.de search uses `limit` + `offset`. `[VERIFIED from docs]`
- Cursor-based pagination: `[not documented publicly]` (the `/api/pagination`
  doc path returns 404; no cursor token documented).

## Rate limits

From `docs.carapis.com/api/rate-limits` `[VERIFIED from docs]`:
| Tier | req/min | req/hour | req/day |
|------|---------|----------|---------|
| Free | 60 | 1,000 | 10,000 |
| Pro | 300 | 10,000 | 100,000 |
| Enterprise | 1,000 | 50,000 | 500,000 |

- Response headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`,
  `X-RateLimit-Reset`. `[VERIFIED from docs]`
- Over-limit response: `429 Too Many Requests`. `[VERIFIED from docs]`
- The autoscout24 parser page lists different per-plan limits (Free 10/min,
  100/hr, 2 concurrent; Basic 60/min, 1,000/hr, 5 concurrent; Pro 300/min,
  10,000/hr, 20 concurrent; Enterprise custom). `[VERIFIED from docs]`
  (autoscout24.com/api-reference). mobile.de page states "100-2000 requests
  per minute depending on plan". `[VERIFIED from docs]` — these conflict with
  the central rate-limits table.

## Pricing

From `https://carapis.com/pricing` `[VERIFIED from docs]`:
- Starter: $99/mo (or $950/yr) — 10,000 API calls/mo, 5 marketplaces, 48h freshness.
- Professional: $299/mo (or $2,870/yr) — 100,000 calls/mo, all 200+ marketplaces, <5min freshness.
- Enterprise: custom — unlimited calls, all 200+ marketplaces + custom, 24/7 phone.
- Free trial: 14 days, no credit card. `[VERIFIED from docs]`
- Overage: $25 per 1,000 extra calls. Add-ons: +10k $20/mo, +50k $90/mo,
  +100k $170/mo. `[VERIFIED from docs]`

## AutoScout24 / European market data

- Exposed: **yes**. Dedicated parser at base
  `https://api.carapis.com/v1/parsers/autoscout24`. `[VERIFIED from docs]`
  (autoscout24.com/api-reference)
- European platforms also covered: Mobile.de (Germany, base
  `https://api.carapis.com/v1/parsers/mobile.de`), plus AutoScout24, listed
  among 200+ marketplaces. `[VERIFIED from docs]`
- How an AutoScout24 request is shaped (per the parser page):
  `POST https://api.carapis.com/v1/parsers/autoscout24/search`
  with header `Authorization: Bearer <key>` and a body using `country`,
  `year_from`, `year_to`, `price_min`, `price_max`, `fuel_type`,
  `transmission`, `body_type`, `location`, `mileage_max`, `limit`, `page`.
  `[VERIFIED from docs]`
- Alternatively, under the v2 unified surface, AutoScout24 would be selected via
  `GET /v2/listings?source=autoscout24` — but the exact v2 slug for AutoScout24
  is **not explicitly shown** on the v2 page (documented v2 slugs were `encar`,
  `mobile-de`, `auto-ria`). `[not documented publicly]`

## Sources (carapis.com)

- https://carapis.com/api/intro
- https://docs.carapis.com/
- https://docs.carapis.com/api/intro
- https://docs.carapis.com/api/authentication
- https://docs.carapis.com/api/endpoints
- https://docs.carapis.com/api/rate-limits
- https://docs.carapis.com/parsers/autoscout24.com/api-reference
- https://docs.carapis.com/parsers/mobile.de/api-reference
- https://docs.carapis.com/parsers/encar.com/api-reference
- https://carapis.com/pricing

---

# 2. auto-api.com

Primary ground truth is the official Go SDK source (read line-by-line), which is
more authoritative than the prose docs page. Sources:
- `https://auto-api.com/` , `https://auto-api.com/documentation`
- Go SDK `github.com/autoapicom/auto-api-go`: `client.go`, `types.go`,
  `errors.go`, `README.md`, `llms.txt`, `examples/main.go`.

## Base URL

- **Default in the SDK: `https://api1.auto-api.com`** (the version segment
  `v2` is appended per-request). `[VERIFIED from docs]`
  (client.go `NewClient`: `baseURL: "https://api1.auto-api.com", apiVersion: "v2"`)
- Effective request URL = `https://api1.auto-api.com/api/v2/<source>/<endpoint>`.
  `[VERIFIED from docs]` (client.go builds `api/%s/%s/<endpoint>` from
  apiVersion + source)
- The prose docs page instead shows a templated host
  `https://{access_name}.auto-api.com/api/v2/{platform}`, i.e. each customer
  gets a dedicated `access_name` subdomain. `[VERIFIED from docs]`
  (auto-api.com/documentation). The SDK ships `api1` as the concrete default and
  exposes `SetBaseURL(...)` to override. `[VERIFIED from docs]` (client.go)
- Base URL is overridable via `client.SetBaseURL(...)` and version via
  `client.SetAPIVersion(...)` (default `"v2"`). `[VERIFIED from docs]` (client.go)

## Auth

- **GET endpoints: API key as `api_key` query parameter.** `[VERIFIED from docs]`
  (client.go `get`: `query.Set("api_key", c.apiKey)`; README "Auth"; llms.txt)
- **POST `/api/v1/offer/info`: API key as `x-api-key` HTTP header.**
  `[VERIFIED from docs]` (client.go `post`: `req.Header.Set("x-api-key", c.apiKey)`)
- No Bearer/Authorization scheme. `[VERIFIED from docs]` (only the two above appear)
- Auth failure surfaces as 401/403 → SDK `AuthError`. `[VERIFIED from docs]`
  (client.go `handleError`; errors.go)

## Endpoints

All GET paths are relative to `https://api1.auto-api.com` and interpolate the
api version and the `<source>` slug: pattern `api/{version}/{source}/<name>`.
`[VERIFIED from docs]` (client.go)

| Method | Path (concrete, v2) | SDK method | Purpose |
|--------|---------------------|------------|---------|
| GET | `/api/v2/{source}/filters` | `GetFilters` | Available filter values (brands, models, body types) |
| GET | `/api/v2/{source}/offers` | `GetOffers` | Paginated listings with filters |
| GET | `/api/v2/{source}/offer` | `GetOffer` | Single listing by `inner_id` |
| GET | `/api/v2/{source}/change_id` | `GetChangeID` | Resolve a `change_id` from a date |
| GET | `/api/v2/{source}/changes` | `GetChanges` | Added/changed/removed feed from a `change_id` |
| POST | `/api/v1/offer/info` | `GetOfferByURL` | Listing data by marketplace URL (note: hardcoded `v1`) |

`[VERIFIED from docs]` (client.go function bodies)

## Request params

### `GET /offers` (the search/listing endpoint) — `OffersParams`
Exact query parameter names (Go struct `url:` tags in types.go):
- `page` (int, always sent) `[VERIFIED from docs]`
- `brand` (string) — note SDK field `Brand` maps to query param `brand`
- `model` (string)
- `configuration` (string)
- `complectation` (string)
- `transmission` (string)
- `color` (string)
- `body_type` (string)
- `engine_type` (string)
- `year_from` (int)
- `year_to` (int)
- `mileage_from` (int)
- `mileage_to` (int)
- `price_from` (int)
- `price_to` (int)

`[VERIFIED from docs]` (types.go `OffersParams`). All except `page` are
`omitempty` (omitted when empty/zero). `[VERIFIED from docs]` (encodeParams)

> Naming note: the prose docs page lists `mark`, `km_age_from`, `km_age_to`,
> `transmission_type`, etc. as `/offers` filters. The SDK source instead sends
> `brand`, `mileage_from`, `mileage_to`, `transmission`. `[VERIFIED from docs]`
> (auto-api.com/documentation vs types.go). The SDK is the implemented contract;
> the docs-page filter names may be stale or describe the `/filters` response
> rather than `/offers` query keys. Prefer the SDK names.

### Other endpoints
- `GET /offer`: query param `inner_id` (string). `[VERIFIED from docs]` (client.go)
- `GET /change_id`: query param `date` (string, `yyyy-mm-dd`). `[VERIFIED from docs]`
- `GET /changes`: query param `change_id` (int). `[VERIFIED from docs]`
- `GET /filters`: no params besides `api_key`. `[VERIFIED from docs]`
- `POST /api/v1/offer/info`: JSON body `{"url": "<listing URL>"}`,
  `Content-Type: application/json`, `x-api-key` header. `[VERIFIED from docs]`

## Response shape

### `/offers` and `/offer` envelope — `OffersResponse`
```json
{
  "result": [
    {
      "id": 0,
      "inner_id": "string",
      "change_type": "string",
      "created_at": "string",
      "data": { /* source-specific object (json.RawMessage) */ }
    }
  ],
  "meta": { "page": 0, "next_page": 0, "limit": 0 }
}
```
`[VERIFIED from docs]` (types.go `OffersResponse`, `OfferItem`, `Meta`)

### Per-listing `data` object — `OfferData` (common fields across sources)
Exact JSON field names: `inner_id`, `url`, `mark`, `model`, `generation`,
`configuration`, `complectation`, `year`, `color`, `price`, `km_age`,
`engine_type`, `transmission_type`, `body_type`, `address`, `seller_type`,
`is_dealer` (bool), `displacement`, `offer_created`, `images` (string array).
`[VERIFIED from docs]` (types.go `OfferData`)

> The SDK comment states each source may add extra fields, so `data` is delivered
> as raw JSON (`json.RawMessage`) and `OfferData` is only the documented common
> subset. Inside `data`, the make/brand field is `mark` (not `brand`) and mileage
> is `km_age` — different from the `/offers` query param names. `[VERIFIED from docs]`

### `/changes` envelope — `ChangesResponse`
```json
{
  "result": [ { "id": 0, "inner_id": "string", "change_type": "string", "created_at": "string", "data": {} } ],
  "meta": { "cur_change_id": 0, "next_change_id": 0, "limit": 0 }
}
```
`change_type` distinguishes added/changed/removed. `[VERIFIED from docs]`
(types.go `ChangesResponse`, `ChangeItem`, `ChangesMeta`; README)

### `/change_id` response
`{ "change_id": 0 }`. `[VERIFIED from docs]` (types.go `ChangeIDResponse`)

### `/filters` and `POST /offer/info` responses
Returned as untyped `map[string]interface{}` (free-form JSON). The
`offer/info` map is read by key e.g. `info["mark"]`, `info["model"]`,
`info["price"]`. `[VERIFIED from docs]` (client.go; examples/main.go)

## Pagination

- **Page-based.** Request: `page` (int) on `/offers`. Response `meta` carries
  `page`, `next_page`, `limit`. Iterate by sending `meta.next_page` until it is
  `0` / absent. `[VERIFIED from docs]` (types.go `Meta`; examples/main.go loops on
  `offers.Meta.NextPage > 0`)
- **Change-feed cursor.** For `/changes`, the cursor is the integer
  `change_id`; `meta.next_change_id` is the cursor for the next batch
  (`0` when exhausted). Seed it via `GET /change_id?date=yyyy-mm-dd`.
  `[VERIFIED from docs]` (types.go `ChangesMeta`; examples/main.go)
- Default/max page size numbers: `[not documented publicly]` (the SDK only
  echoes the server-provided `limit`; no documented default/cap).

## Source / platform selection

The `<source>` slug is a path segment (function arg `source` in every SDK
method), e.g. `GetOffers(ctx, "encar", ...)` →
`/api/v2/encar/offers`. `[VERIFIED from docs]` (client.go, README, examples)

Documented source slugs (SDK README "Supported sources" table):
| Slug | Platform | Region |
|------|----------|--------|
| `encar` | encar.com | South Korea |
| `mobilede` | mobile.de | Germany |
| `autoscout24` | autoscout24.com | Europe |
| `che168` | che168.com | China |
| `dongchedi` | dongchedi.com | China |
| `guazi` | guazi.com | China |
| `dubicars` | dubicars.com | UAE |
| `dubizzle` | dubizzle.com | UAE |

`[VERIFIED from docs]` (README). The README example also uses `"mobilede"`
verbatim in code. The prose docs page instead spells it `mobile-de` (with
hyphen). `[VERIFIED from docs]` (auto-api.com/documentation). **Use the SDK
slug `mobilede`** as the implemented value; confirm before relying on the hyphen
form. To request AutoScout24 / European data: pass `source="autoscout24"` (or
`"mobilede"`) into any method, e.g.
`GET /api/v2/autoscout24/offers?api_key=...&page=1&brand=BMW&year_from=2020`.
`[VERIFIED from docs]`

## Daily exports (bulk, non-REST)

Pre-generated files at
`https://{access_name}.auto-api.com/{date}/{file_name}` in CSV / JSON / Excel,
filenames like `all_active.csv`, `new_daily.json`, `removed_daily.xlsx`; files
"stored for 3+ days minimum". `[VERIFIED from docs]` (auto-api.com/documentation)

## Rate limits

`[not documented publicly]`. The site states "No usage limits" / does not list
numeric quotas, concurrency, or rate-limit headers. `[VERIFIED from docs]` that no
numbers are published (auto-api.com, auto-api.com/documentation).

## Pricing

`[not documented publicly]`. No pricing table or free-tier numbers on the site or
docs; acquisition is via contact (`access@auto-api.com`, Telegram
`@autodatabase`). `[VERIFIED from docs]` (auto-api.com)

## Other facts

- 8 marketplaces supported per the SDK/README; the marketing page claims
  "100M+ listings, 15+ platforms, 50+ data fields" and "<200ms response time" —
  marketing figures, not a schema. `[VERIFIED from docs]`
- Official SDKs: Go, PHP, TypeScript/Node, Python, C#/.NET, Java, Ruby, Rust.
  `[VERIFIED from docs]` (README "Other languages")
- SDK error types: `AuthError` (401/403) and `ApiError` (other non-2xx, carries
  `StatusCode`, `Message`, raw `Body`); server error messages parsed from a
  JSON `message` field. `[VERIFIED from docs]` (errors.go, client.go)

## Sources (auto-api.com)

- https://auto-api.com/
- https://auto-api.com/documentation
- https://github.com/autoapicom/auto-api-go (client.go, types.go, errors.go, README.md, llms.txt, examples/main.go)
- Sibling SDKs: auto-api-php, auto-api-node, auto-api-python, auto-api-dotnet, auto-api-java, auto-api-ruby, auto-api-rust (under github.com/autoapicom)
