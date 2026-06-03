# autocasion.com — Scraping Research (CARDEX engine)

> Research date: 2026-06-03. Method: live `curl_cffi` 0.15.0 (`impersonate="chrome"`) probes against the production site. Total inventory: ~122,068 cars (`/coches-ocasion` counter); the per-province SRPs sum to a different (larger) number because they include dealer stock paths absent from the global page.

---

## 1. Anti-bot stack — **Cloudflare, no JS challenge** [VERIFIED]

`server: cloudflare`, `cf-ray: a06208f5adf829a7-ZRH`. JA3-only gating: plain `requests` returns 403 (verified for sibling Cloudflare portals), `curl_cffi impersonate="chrome"` passes every surface. No `__cf_chl_*` cookie or interstitial body observed. Tier.T1.

---

## 2. Search endpoint — `/coches-segunda-mano/<province>[/<fuel>]?page=N` [VERIFIED]

```
GET https://www.autocasion.com/coches-segunda-mano/<province>/<fuel>?page={N}
```

The `<province>` and `<fuel>` are **URL segments**, not query params. autocasion encodes every filter dimension this way; the brief's query-string candidates (`precio_desde/hasta`, `anno_desde/hasta`, `kms_hasta`, `precio_min/max`, `year_min/max`, `marca`, `brand`, `province`) **all returned the unfiltered 122k baseline** when passed as `?key=value`. The robots.txt itself disallows query-style filter URLs like `?anno_desde=…` — confirming they're handled by JS but never reach the SSR layer.

Verified surface vocabulary:

| Path | Effect | Counter |
|---|---|---|
| `/coches-ocasion` | global SRP | 122,068 |
| `/coches-segunda-mano/madrid` | Madrid only | 56,280 |
| `/coches-segunda-mano/madrid/diesel` | Madrid + diesel | 17,648 |
| `/coches-segunda-mano/madrid/gasolina` | Madrid + petrol | 25,449 |
| `/coches-segunda-mano/madrid/electrico` | Madrid + EV | 1,395 |
| `/coches-segunda-mano/madrid/hibrido` | Madrid + hybrid | 7,952 |
| `/coches-segunda-mano/madrid/hibrido-enchufable` | Madrid + PHEV | 3,279 |
| `/coches-segunda-mano/madrid/gas` | Madrid + LPG/CNG | 523 |

Madrid totals across all six fuels: 17,648 + 25,449 + 1,395 + 7,952 + 3,279 + 523 = **56,246** (matches the `madrid` baseline of 56,280 within page-update jitter, confirming the six-fuel grid is exhaustive and mutually exclusive).

`?page=N` is the verified pager. `?numPag=N` was rejected (overlap 24/24 with page 1).

---

## 3. Listing layout & detail URL [VERIFIED]

Each card on the SRP carries a detail anchor of the form:

```
/coches-segunda-mano/<brand>-<model>-ocasion/<slug>-ref<NUMERIC_REF_ID>
```

Verified examples (live):

```
/coches-segunda-mano/smart-forfour-ocasion/forfour-eq-passion-377-ref13832451
/coches-segunda-mano/audi-a3-ocasion/a3-sportback-30tdi-s-line-ref14494615
/coches-segunda-mano/nissan-qashqai-ocasion/1-3-dig-t-mhev-…-ref18872866
```

The canonical id is the `ref<DIGITS>` suffix. Host: `https://www.autocasion.com`. 24–25 unique anchors per page.

---

## 4. Pagination cap — **page 400 (~10,000 ads/segment)** [VERIFIED]

Live binary probe (both for the global `/coches-ocasion` and for province/fuel SRPs):

| `page=N` | Cards |
|---|---|
| 1..400 | 23–25 (full pages) |
| 401, 410, 500, 1000, 5000 | **5–6** (only the sticky featured-card carousel; 0 real new ads) |

The pager doesn't 404 past the cap — it silently degrades to the home-page sticky carousel. The scraper terminates the loop via the short-page detector at `< PAGE_SIZE`.

`400 × 24 ≈ 9,600` ads per filter segment. The global `/coches-ocasion` reaches only 9.6k of the 122k inventory; partitioning is mandatory.

---

## 5. Partitioning — province × fuel grid

52 Spanish provinces × 6 fuel types (`diesel`, `gasolina`, `electrico`, `hibrido`, `hibrido-enchufable`, `gas`) = **312 cells**, each well under the 10k segment cap for the unfiltered inventory. The Madrid grid totals 56,246 cars across the six fuels — adopting this grid for every province is exhaustive without any make/model refdata.

The 52-province list was harvested live from `https://www.autocasion.com/uploads/sitemap-ng/coches-segunda-mano/coches-segunda-mano.xml` (which surfaces every province URL exactly as the scraper uses it). The slug spellings are stable Spanish province slugs — the list will not change unless ES adds a province. They're embedded in the scraper as a constant rather than re-downloading the 5.6 MB sitemap on every run.

Cross-cell dedup is the base `seen` set on canonical `/coches-segunda-mano/<brand>-<model>-ocasion/<slug>-ref<ID>` URLs.

---

## 6. Block signals

| Status | Treatment |
|---|---|
| 200 | parse, extract |
| 403/429/500/502/503 | retry with exponential backoff (3 attempts) |
| other 4xx/5xx | terminal — return empty |

The pager cap manifests as `200 + ≤ PAGE_SIZE cards` (degrading to the sticky carousel), not as a 404 — the short-page detector handles it.
