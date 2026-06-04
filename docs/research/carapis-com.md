# Carapis.com — Vehicle Listings API Research (CARDEX)

> Research date: 2026-06-03. All probes done with `curl_cffi impersonate="chrome"` against the
> live origin and with GitHub `gh api` reads of the vendor's official client source.
> Confidence is marked per-fact: **[VERIFIED]** = observed in a live HTTP response or in
> vendor-published source code; **[ASSUMED]** = documented only (vendor docs / marketing),
> not reproducible without a paid key.

---

## 1. What carapis.com is

A **commercial automotive-data API / scraping-as-a-service** ("Professional Automotive Data
Parsers"). It scrapes 200+ car marketplaces and exposes them behind **one unified REST API**.
You do not scrape the portals yourself — Carapis scrapes them and sells structured access,
plus anti-detection infrastructure. Operated by **markolofsen** (Reforms.ai, `hello@reforms.ai`).

- Primary focus historically: **Asian car market** (dashboard title: "CarAPIS – Asian Car Market Data"). **[VERIFIED]**
- Covered sources (platform "slugs") include: **Encar** (Korea), **Che168 / Autohome / Dongchedi** (China),
  **Auto.ru / Avito** (Russia), **Mobile.de** (Germany), **AutoScout24 / Standvirtual** (Europe),
  **Cars.com / CarGurus / AutoTrader** (USA), **Goo-net / Carsensor / 8891 / USS Auction** (Japan/Asia), and more. **[VERIFIED in docs]**
- Marketing claims: "200+ marketplaces" / "60+ platforms" (the two numbers are used inconsistently across pages). **[ASSUMED]**

Infrastructure: origin is **Django** ("UnrealOn Django") behind **Cloudflare**. **[VERIFIED]**
DNS: `api.carapis.com -> 188.114.96.12`, `carapis.com -> 188.114.97.12`,
`my.carapis.com -> 188.114.96.12`, `docs.carapis.com -> 216.198.79.65` (Vercel/Nextra). **[VERIFIED]**

---

## 2. THE CURRENT CONTRACT (what to implement against)

Source of truth = the live product docs at `https://carapis.com/api/*` (Nextra site, all HTTP 200,
last updated for the v2 API). These supersede everything on `docs.carapis.com` and the legacy
GitHub clients (see §6 "Conflicting/stale info").

### Base URL & version
```
https://api.carapis.com/v2
```
"All requests go to" this base. **[VERIFIED — string present verbatim in live docs]**

### Authentication
- Scheme: **HTTP Bearer**. Header on **every** request:
  ```
  Authorization: Bearer <CARAPIS_API_KEY>
  ```
- No OAuth, no session cookies. **[VERIFIED in docs]**
- Get the key at **https://my.carapis.com** (the dashboard; live, HTTP 200). **[VERIFIED]**
- 14-day free trial, **all features unlocked, no credit card required** to start. **[ASSUMED — marketing]**
- (Legacy `/apix` API used `Authorization: ApiKey <key>` and a no-key free tier — do NOT use; see §6.)

### Main endpoint — listings (THE one we need)
```
GET https://api.carapis.com/v2/listings
```
Documented query parameters **[VERIFIED in docs]**:

| Param         | Type   | Notes |
|---------------|--------|-------|
| `source`      | string | Platform slug, e.g. `encar`, `che168`, `cars.com`. Selects which marketplace. |
| `make`        | string | Filter by manufacturer. |
| `model`       | string | Filter by model. |
| `year`        | int    | Filter by year (min/max variants implied; exact min/max param names not shown on this page). |
| `price`       | int    | Filter by price (min/max implied). |
| `page`        | int    | Pagination, 1-based. |
| `limit`       | int    | Page size (example uses `limit=20`). |

Documented exact calls (copy verbatim from live docs) **[VERIFIED]**:
```bash
curl "https://api.carapis.com/v2/listings?source=encar&limit=20" \
  -H "Authorization: Bearer $CARAPIS_API_KEY"
```
```python
import os, requests
resp = requests.get(
    "https://api.carapis.com/v2/listings",
    params={"source": "encar", "limit": 20},
    headers={"Authorization": f"Bearer {API_KEY}"},
)
data = resp.json()
for car in data["results"]:
    print(car["make"], car["model"], car["year"], car["price"])
```

### Response shape — paginated envelope **[VERIFIED — documented example]**
```json
{
  "total": 820,
  "page": 1,
  "limit": 20,
  "results": [
    {
      "id": "encar_38217645",
      "source": "encar",
      "make": "Hyundai",
      "model": "Grandeur",
      "trim": "2.5 GDi Premium",
      "year": 2022,
      "mileage": 31500,
      "price": 28500000,
      "currency": "KRW",
      "location": "Seoul",
      "fuel_type": "gasoline",
      "transmission": "automatic",
      "photos": ["https://.../1.jpg", "https://.../2.jpg"],
      "dealer": "Encar Certified Dealer",
      "url": "https://www.encar.com/dc/dc_cardetailview.do?carid=38217645"
    }
  ]
}
```
- **Stable field schema across all platforms.** When a platform exposes richer data, the object
  *also* carries `inspection_sheet`, `accident_history`, or `price_history`. **[VERIFIED in docs]**
- **Unique ID field:** `id` — formatted `<source>_<portalId>` (e.g. `encar_38217645`). **[VERIFIED]**
- **Listing URL field:** `url` — the canonical detail-page URL on the origin portal. **[VERIFIED]**
- Pagination wrapper: `total` (sometimes referred to as `count` in the pagination doc), `page`, `limit`. **[VERIFIED]**

### Pagination **[VERIFIED in docs]**
- Strategy: **page + limit** (offset-style page numbers, 1-based). NOT cursor-based.
- Read `total`/`count` to size the result set; loop incrementing `page` until you have collected
  every match (`page * limit >= total`).

### Other documented routes (from the docs nav / client examples)
- `GET /v2/listings/{id}` (vehicle detail) — implied by docs ("Look up a listing by ID");
  exact path templated as `/v2/listings?...&id=38217645` appears in one example, and a by-ID
  detail route is referenced. **[ASSUMED — not pinned to an exact path string]**
- Doc pages exist for: Authentication, Listings, Pagination, Rate Limits, Errors, and
  Clients (curl / Python / JavaScript) at `https://carapis.com/api/...`. **[VERIFIED routes exist]**
- No VIN-decode endpoint was documented on the v2 pages reviewed. **[ASSUMED absent]**

---

## 3. Pricing & rate limits **[ASSUMED — from /pricing marketing page]**

- **Free trial:** 14 days, full features, no credit card. Sign up at my.carapis.com.
- **Starter Plan:** **$99/month** or **$950/year** (save $238). Includes **5 marketplace access**
  (choose from 200+), 48-hour data freshness tier. For individuals / small teams.
- **Professional Plan** (MOST POPULAR): higher tier, "$2,870/year (save $718)" annual example,
  "fresh data from all" marketplaces. Monthly price not cleanly captured.
- **Enterprise Plan:** custom; account manager, white-label, custom integration, up to 10-year history.
- **Overage:** **$25 per 1,000 additional API calls**; or set a hard limit to cap at 100% (no overage).
- **Rate limits:** plan-dependent throughput. Exceeding returns **HTTP 429** — handle with backoff. **[VERIFIED that 429 is the documented signal]**

---

## 4. Anti-bot / access reality **[VERIFIED]**

- Origin sits behind **Cloudflare** (server header `cloudflare`, `cf-ray` present).
- The API itself is the anti-bot layer **for us** — Carapis does the scraping; we just call REST.
- **Every documented endpoint returns a genuine origin 404 to unauthenticated traffic.**
  Evidence: `GET /v2/listings`, `/v2/listings?source=encar&limit=1`, `/v2`, and the same with a
  bogus `Authorization: Bearer test_invalid_key_123`, ALL returned **HTTP 404** with the Django
  "Not Found" body (1098 bytes).
- This is NOT a Cloudflare block and NOT a malformed-path issue: `GET /admin/` on the same origin
  returns a clean **HTTP 401 Unauthorized** (17 bytes), proving (a) our requests reach Django fine,
  (b) real routes respond with real status codes. The `/v2/listings` route simply does not serve
  unauthenticated requests — it is gated such that without a valid key you cannot observe even a
  401/403. **A live 200 is therefore impossible to produce without a paid/trial key.**

---

## 5. Evidence log (live probes)

| Request | Result | Meaning |
|---|---|---|
| `GET https://carapis.com/` | 200, Nextra docs, title "Carapis Documentation" | site live |
| `GET https://api.carapis.com/` | 200, HTML "UnrealOn Django - Nothing Here Yet" | Django origin live |
| `GET https://api.carapis.com/admin/` | **401 Unauthorized** (17 bytes) | origin routes work; baseline for "real but protected" |
| `GET https://api.carapis.com/v2/listings` | **404** Django Not Found (1098 B) | no unauth surface |
| `GET .../v2/listings?source=encar&limit=1` (no key) | **404** | same |
| `GET .../v2/listings?source=encar&limit=1` + bogus Bearer | **404** | key-gated, not 401-on-bad-key |
| `GET .../v2` | **404** | |
| `GET .../apix/encar/v2/vehicles/` (legacy SDK path) | **404** | legacy API retired |
| `GET .../v1/parsers/cars.com/search` (docs.carapis.com path) | **404** | stale doc path |
| `GET https://my.carapis.com/` | 200, "CarAPIS – Asian Car Market Data" | dashboard / key issuance live |
| npm `@carapis/api`, `@carapis/encar`, PyPI `carapis-encar` | **404** | official clients NOT published to registries |

---

## 6. Conflicting / stale information (DO NOT trust these)

Carapis has **three mutually contradictory documented contracts**. Only the v2 one (§2) is current.

1. **`docs.carapis.com` (legacy Docusaurus docs)** — describes per-parser paths like
   `GET /encar/vehicles`, `POST /v1/parsers/cars.com/search`, `POST /auth` returning a `token`,
   `Authorization: Bearer`. **All these paths 404 on the live origin.** Largely AI-generated
   marketing content; field/path details there are unreliable. **[VERIFIED 404]**
2. **Official GitHub clients** `markolofsen/carapis-encar-pypi` & `carapis-encar-npm` — real code,
   base `https://api.carapis.com`, api-base-path **`/apix/encar/v2`**, auth **`ApiKey <key>`**,
   DRF endpoints (`encar_v2_vehicles_list` → `GET /apix/encar/v2/vehicles/` with
   `manufacturer_slug, model_slug, min_year, max_year, min_price, max_price, fuel_type,
   transmission, body_type, color, min_mileage, max_mileage, page, limit, ordering, search`).
   A bundled `schema.yaml` (real OpenAPI 3) ships inside the package. **This `/apix` API is retired
   — every path 404s live, and the packages were never published to npm/PyPI.** Useful only as a
   reference for the richer Encar filter vocabulary, which likely maps onto v2's `make/model/year/price`. **[VERIFIED]**
3. **`api2.carapis.com`** appears in `carapis-nextjs-demo/.env.example` — **does not resolve (NXDOMAIN).** Dead staging host. **[VERIFIED]**

There is **no publicly reachable OpenAPI/Swagger** on the live origin (`/api/schema/`, `/openapi.json`,
`/swagger.json`, `/api/docs/` all 404). The only real OpenAPI artifact found is the `schema.yaml`
bundled in the (retired) PyPI client repo, describing the old `/apix/encar/v2` surface.

---

## 7. Recommended scraper strategy for CARDEX

**Tier: paid third-party API client (NOT a DIY scraper).** Carapis is a managed data vendor; the
correct integration is a thin REST client, gated on having a key.

1. **Acquire a key first.** Without a trial/paid key from my.carapis.com you cannot get a single
   200 — the endpoint is fully key-gated (confirmed: even a bad Bearer yields 404, not 401).
   Action item for a human: start the 14-day free trial, generate key, drop into `CARAPIS_API_KEY` env.

2. **Implement against the v2 contract (§2):**
   - Single client: `GET https://api.carapis.com/v2/listings` with `Authorization: Bearer <key>`.
   - Required selector: `source=<platform slug>` (e.g. `encar`). Iterate over the sources CARDEX cares about.
   - Filters: `make`, `model`, `year`, `price` (+ richer Encar filters per §6.2 if needed; verify names against a live response once you have a key).
   - Paginate with `page` + `limit`; loop `page` from 1 until `page*limit >= total`.
   - Map to CARDEX model: `id` (globally unique, `<source>_<id>`), `url` (detail link),
     `make`/`model`/`trim`/`year`/`mileage`/`price`/`currency`/`fuel_type`/`transmission`/`location`/`photos`/`dealer`.

3. **Resilience:** respect **429** with exponential backoff (rate limit is plan-bound). Watch the
   overage model ($25/1k calls) — page sizes should be maxed (`limit` up to the documented cap;
   legacy schema capped at 100, re-verify for v2) to minimize call count. Cap spend with the
   dashboard hard-limit toggle.

4. **First action once a key exists (verification gate before building):**
   ```bash
   curl "https://api.carapis.com/v2/listings?source=encar&limit=1" -H "Authorization: Bearer $CARAPIS_API_KEY"
   ```
   Confirm 200 + the `results[]` envelope, snapshot the exact field set per source (fields vary —
   "stable schema" plus optional `inspection_sheet`/`accident_history`/`price_history`), then
   freeze the response model. Do not hardcode the legacy `/apix` filter names without re-checking.

**Honest bottom line:** carapis.com is **unusable without payment** — no scrapeable free endpoint,
no public sample response, fully key-gated. The documented contract (base, endpoint, params, auth,
envelope, ID/URL fields, pagination) is solid and **[VERIFIED]** as *documentation*, but **no live
200 response was obtainable** in this research because every call requires a valid key.
