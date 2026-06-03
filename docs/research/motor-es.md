# motor.es (segunda-mano coches) — Scraping Research (CARDEX engine)

> Research date: 2026-06-03. Method: live `curl_cffi` 0.15.0 (`impersonate="chrome"`) probes against the production site. Total inventory: ~50,333 cars (reported on `/segunda-mano/`); the cars-only `/segunda-mano/coches/` filter view is the partition-capable surface.

---

## 1. Anti-bot stack — **Cloudflare, no JS challenge for impersonated chrome** [VERIFIED]

`robots.txt` reveals Cloudflare (`server: cloudflare`, `cf-ray: a061fcaf5886bc59-ZRH` on every response). The challenge is JA3-only: `curl_cffi impersonate="chrome"` passes every surface (sitemap, SRP, deep pagination, ad detail). No `__cf_chl_*` cookie or interstitial body was ever seen during the research run. Tier.T1.

---

## 2. Search endpoint — `/segunda-mano/coches/?pagina=N&<filters>` [VERIFIED]

```
GET https://www.motor.es/segunda-mano/coches/?pagina={N}&precio_min={Pf}&precio_max={Pt}&year_min={Yf}&year_max={Yt}
```

The site has a generic `/segunda-mano/` surface that mixes cars **and motorcycles** (sample data-goto links resolved to `/motos/segunda-mano/anuncio/<UUID>/`). Cars must be requested through `/segunda-mano/coches/`, which only emits `/segunda-mano/anuncio/<id>/` URLs (numeric ids, NOT UUIDs).

### Verified filter vocabulary

Discovered from form `name=` attributes (`<input>` and `<select>` together) and re-verified by sampling the result IDs:

| Param | Meaning | Verified example |
|---|---|---|
| `pagina` | **page number, 1-based** | `1`, `50` (cap) |
| `precio_min` / `precio_max` | EUR floor / ceiling | `5000` / `10000` |
| `year_min` / `year_max` | first-registration year | `2018` / `2020` |
| `km_min` / `km_max` | mileage in km | (numeric) |
| `marca` / `modelo` | make / model name | (slug; refdata-coupled — not used) |

The brief's candidate names `pmin`/`pmax` and `anyomin`/`anyomax` are **rejected** — they returned the unfiltered set. Spanish-style underscore names (`precio_min`, `year_min`, …) are the ones the form actually emits and the server actually honours.

### Filter actually narrows the set [VERIFIED]

Live overlap probe:

| Query | Cards | Overlap with base |
|---|---|---|
| base | 22 | — |
| `precio_min=0&precio_max=5000` | 22 | **0** |
| `precio_min=20000&precio_max=30000` | 22 | 9 |
| `precio_min=50000&precio_max=200000` | 22 | 1 |
| (cheap ∩ expensive) | — | **0** |

Filters partition the inventory cleanly; the year × price grid is safe.

---

## 3. Listing layout & detail URL — `data-goto` is base64-encoded [VERIFIED]

Each card on the SRP is an `<article class="elemento-segunda-mano …">` containing a `<span class="elemento-segunda-mano__link …" data-goto="<BASE64>" data-id="<UUID>">`. The `data-goto` value base64-decodes to the absolute detail URL.

The base64-decoded URLs come in two flavours:

| Decoded URL | Meaning | Used? |
|---|---|---|
| `https://www.motor.es/segunda-mano/anuncio/<NUMERIC_ID>/` | car ad | **yes** |
| `https://www.motor.es/motos/segunda-mano/anuncio/<UUID>/` | motorcycle ad | **no** (filtered out) |

On the cars-only `/segunda-mano/coches/` surface the decoded URLs are all car ads with numeric ids matching `\d+`. The scraper filters strictly on the `/segunda-mano/anuncio/<id>/` shape and ignores anything else (defensive against a future page rotation that re-introduces motorcycle cards into the cars view).

A naked GET on a decoded car URL returns 200 with the full ad page.

### Card count per page — 22, not 30 or 100

Verified: 22 unique ad anchors per page across `pagina=1, 2, 3, 10, 20, 30, 40, 50`. The base scraper's `PAGE_SIZE` is set to 22 so the short-page detector terminates the loop correctly on the last page of a segment.

---

## 4. Pagination cap — **page 50 (~1,100 ads/query)** [VERIFIED]

Live binary search confirms a hard cap:

| `pagina=N` | Status | Cards |
|---|---|---|
| 1..50 | 200 | 22 |
| 51, 55, 60, 99, 2000 | **404** | 0 |

`50 × 22 = 1,100` ads per filter combination — vs the ~50k total. So a year × price grid is **mandatory**; a single make would already exceed the cap (Audi alone reports 1,370 on `/segunda-mano/audi/` and Madrid 13,873).

---

## 5. Partitioning — year band × price band over all makes

Same shape as the rest of the fleet: 11 year bands × 8 price bands = 88 cells, each well under the 1,100 ceiling for the unfiltered inventory. A saturated cell is subdivided into per-year × finer-price sub-cells via the standard one-level `subdivide_segment`. Cross-cell dedup is the base `seen` set on canonical `/segunda-mano/anuncio/<id>/` URLs.

The make filter (`marca`) is honoured but exhausting the make list requires a refdata table; the year × price grid avoids that dependency.

---

## 6. Block signals

| Status | Treatment |
|---|---|
| 200 | parse, extract |
| 403/429/500/502/503 | retry with exponential backoff (3 attempts) |
| 404 | terminal — this is how the page-50 cap surfaces |
| other 4xx | terminal — return empty |
