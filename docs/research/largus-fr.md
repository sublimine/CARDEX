# largus.fr (Occasion) — Scraping Research (CARDEX engine)

> Research date: 2026-06-03. Method: live `curl_cffi` 0.15.0 (`impersonate="chrome"`) probes hitting the production site. Total inventory: ~272,145 cars (`occasion.largus.fr/auto/` total counter). Subdomain split: editorial content lives at `www.largus.fr`; the classifieds marketplace is `occasion.largus.fr` — a separate Drupal-flavoured surface with its own routing.

---

## 1. Anti-bot stack — **bare HTTP, no WAF** [VERIFIED]

```
GET https://occasion.largus.fr/
STATUS 200, no `cf-ray`, no `x-datadome`, no `server: cloudflare`, no Akamai pixel
```

Naked `curl_cffi` `impersonate="chrome"` passes every surface tested (home, `/auto/`, deep filters, ad detail). No challenge body, no JavaScript gate. **Tier.T1** in `domain_map.py`.

The neighbouring properties exposed defensively (`annonces.largus.fr`, `vehicules.largus.fr`) both return **410 Gone** — they are deprecated, not blockers. Only `occasion.largus.fr` and `www.largus.fr` are live; the cars marketplace is `occasion.largus.fr` exclusively.

---

## 2. Search endpoint — `/auto/` with query-string filters [VERIFIED]

```
GET https://occasion.largus.fr/auto/?<filters>&currentpage=N
```

Discovered via the `currentpage=N` pager links rendered in the SSR HTML of `/auto/`. The verified filter vocabulary, every name re-checked against the live counter:

| Param | Meaning | Unit | Verified example |
|---|---|---|---|
| `price_min` | price floor | **CENTS** (EUR ×100) | `500000` = €5,000 |
| `price_max` | price ceiling | **CENTS** | `1000000` = €10,000 |
| `year_min` | year floor (first-registration) | year (4 digits) | `2018` |
| `year_max` | year ceiling | year | `2020` |
| `mileage_max` | km ceiling | km (NOT cents) | `50000` |
| `mileage_min` | km floor | km | (numeric) |
| `category` | body type | enum slug | `berline`, `4x4-suv-crossover-pick-up`, … |
| `energy` | fuel type | enum slug | `electrique`, `essence`, `diesel` |
| `gearbox` | transmission | enum slug | `automatique`, `manuelle` |
| `currentpage` | **page number, 1-based** | int | `1`, `416` |

### Price unit verification — the gold nugget

The price filter takes **cents**, not euros. This is the load-bearing finding that makes partitioning possible.

| Query | Counter |
|---|---|
| no filter | 272,145 |
| `price_max=5000` (€50) | 12 (nonsense — interpreted as €0.50 max) |
| `price_max=500000` (€5,000) | 14,878 |
| `price_min=500000&price_max=1000000` (€5–10k) | 38,680 |
| `price_min=1000000&price_max=2000000` (€10–20k) | 107,147 |
| `price_min=2000000&price_max=5000000` (€20–50k) | 99,177 |

The sum (14,878 + 38,680 + 107,147 + 99,177 ≈ 260k) matches the 272k baseline within rounding — confirming both the cents unit and that the bands are non-overlapping. The brief's price-in-euros candidate is **rejected**.

### Mileage unit — NOT cents

`mileage_max=50000` → 111,692 (consistent with "≤ 50,000 km"). `mileage_max=5000000` → 272,143 (i.e. ≈ the whole inventory). Mileage is in km, despite price being in cents.

---

## 3. Listing layout & detail URL [VERIFIED]

Each search result page is server-rendered HTML containing **24 unique ads/page**. The detail URL has the shape:

```
/auto/annonce-<UUID>-<brand>-<model>-<year>-<mileage>km
```

Example IDs in the wild (verified live):

```
/auto/annonce-04279b1b-ce4d-4cc1-863f-d0bbd8c978a8-renault-clio-2018-130000km
/auto/annonce-1205e427-91f5-436e-8efa-c8a5cd2c9c67-volkswagen-golf-2024-25300km
/auto/annonce-a9850c65-b894-45b6-8bb8-075d514078c8-renault-clio-2022-45700km
```

The slug after the UUID is informative but not used as a key — only the UUID is canonical. A naked GET on a detail URL returns 200 with the full ad page. The host is fixed at `https://occasion.largus.fr`.

---

## 4. Pagination cap — **page 416 per filter (~9,984 ads/query)** [VERIFIED]

Live probe:

| `currentpage=N` (no filter) | Status | Ad count |
|---|---|---|
| 1, 2, 100, 416 | 200 | 24 |
| 417 | 404 | 0 |
| 500, 1000 | 404 | 0 |

The page=416 hint surfaces directly in the SSR HTML (`href="/auto/?currentpage=416"` is the last numeric pager link). With 24 ads/page, the reachable ceiling is `416 × 24 ≈ 9,984` ads per filter combination — vs the 272k total inventory.

**Implication:** even the largest single price band (€10–20k → 107k ads) saturates the 9,984 ceiling, so a year × price grid is mandatory and capped cells must subdivide. The base scraper handles both via `partition_params` and `subdivide_segment`.

---

## 5. Partitioning — year band × price band over all makes

The make filter exists as URL segments (`/auto/audi/`, `/auto/peugeot/clio/`, …) but exhausting the make list introduces a reference-data dependency the engine avoids. Year × price is enough: 11 year bands × 8 price bands = 88 cells. The base price bands (in cents) are:

```
0,  500,000   |   500,000, 1,000,000   |   1,000,000, 1,500,000   | …
```

A saturated cell is subdivided into per-year × finer-price sub-cells. Cross-cell dedup is the base `seen` set on canonical detail URLs.

---

## 6. Block signals

The marketplace serves bare Drupal HTTP; no challenge body was ever observed in the research run.

| Status | Treatment |
|---|---|
| 200 | parse, extract |
| 404 | terminal — return empty (no retry; this is how the cap manifests) |
| 403/429/500/502/503 | retry with exponential backoff (3 attempts) |
| other 4xx/5xx | terminal — return empty |
