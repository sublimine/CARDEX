# gaspedaal.nl — Scraping Research (CARDEX engine)

> Research date: 2026-06-03. Method: live `curl_cffi` 0.15.0 (`impersonate="chrome"`) probes against the production site. Total inventory: **338,817 cars** (the JSON-LD `ItemList.numberOfItems` on `/zoeken`; the SSR pager runs to page 3,389 of 100, last page partial — exact match).

---

## 1. Anti-bot stack — **bare Next.js, no WAF** [VERIFIED]

`robots.txt` mentions `/cdn-cgi/` (Cloudflare worker path) but no `cf-ray`, `cf-cache-status` or Akamai pixel appear on the search path. Naked `curl_cffi` `impersonate="chrome"` passes every surface tested (home, `/zoeken`, deep pagination, detail). Tier.T1.

---

## 2. Search endpoint — `/zoeken?page=N` [VERIFIED]

```
GET https://www.gaspedaal.nl/zoeken?page=N
```

The `/auto` landing page is brand/model navigation (no listings). The cars marketplace lives at `/zoeken`. The robots `Allow: /*?utm` + the `?page=N` pager pattern (verified in the SSR HTML) confirm query-string usage. Brief candidate filter params (`priceTo`, `priceFrom`, `priceMin/Max`, `min_price/max_price`) **all returned the unfiltered baseline counter** (`numberOfItems":338817`) — query-string filtering is not honoured on `/zoeken`. Filters are encoded as URL **segments** (`/auto/audi`, `/auto/audi/a3`), not query params. Since the global pager covers the full inventory (§4), no filter is needed.

---

## 3. Listing data — JSON-LD `ItemList` embedded in SSR HTML [VERIFIED]

The SSR HTML contains a `<script type="application/ld+json">` carrying schema.org `ItemList` with **100 items/page**. Each item is a `Car` / `Product` with the verified shape (truncated for brevity):

```json
{
  "@type": "ListItem",
  "position": 1,
  "item": {
    "@type": ["Car", "Product"],
    "@id": "https://www.gaspedaal.nl/zoeken#136923530",
    "name": "Renault Captur - 1.0 TCe 90 R.S. Line",
    "brand": "Renault",
    "model": "Captur",
    "productionDate": 2022,
    "offers": { "price": 17750, "priceCurrency": "EUR" }
  }
}
```

### The canonical detail URL — built from `brand` + `model` + ID

The `@id` `https://www.gaspedaal.nl/zoeken#136923530` is a *fragment*, not a usable URL. The canonical detail page lives at:

```
/auto/<brand-slug>/<model-slug>/<ID>
```

verified live: `/auto/renault/captur/136923530` → 200, `/auto/mercedes-benz/c-klasse/132248498` → 200, `/auto/ds/ds-4/122829592` → 200, `/auto/bmw/3-serie/130645536` → 200.

### Slug normalisation — ASCII fold required

`/auto/citroën/c3/132504667` → **404**, but `/auto/citroen/c3/132504667` → **200**. The slug requires NFKD decomposition + accent stripping (Citroën → citroen). The transform applied:

1. NFKD normalise.
2. Drop combining marks (`unicodedata.category(c).startswith('M')`).
3. Lowercase.
4. Replace spaces with hyphens.

No further transliteration is required for the brand/model vocabulary observed in the wild.

### Page-N JSON-LD echoes the page query in `@id`

On page 2+ the `@id` becomes `https://www.gaspedaal.nl/zoeken?page=2#<ID>` — the regex must allow the optional `?page=N` suffix. Verified across `page=1, 2, 100`.

---

## 4. Pagination cap — covers the entire inventory [VERIFIED]

Live binary probe:

| `page=N` | items in JSON-LD |
|---|---|
| 1, 2, 100, 200, 333, 500, 1000, 2000, 3000, **3388** | **100** (full page) |
| **3389** | **17** (last partial page) |
| 3500, 4000, 5000 | 0 (past cap) |

Exact accounting: `3,388 × 100 + 17 = 338,817` — matches the counter to the unit. The global pager covers the full inventory; no partition / filtering required. (Same pattern as `autotrack.nl`.)

At 1.5–2s/page jittered, a full pass is ≈ 1.5–2 hours (faster than autotrack thanks to the 100-item page).

---

## 5. Block signals

No challenge body was ever observed in the research run.

| Status | Treatment |
|---|---|
| 200 | parse JSON-LD, extract |
| 403/429/503 | retry with exponential backoff (3 attempts) |
| other 4xx/5xx | terminal — return empty |
