# paruvendu.fr (voitures d'occasion) — Scraping Research (CARDEX engine)

> Research date: 2026-06-03. Method: live `curl_cffi` 0.15.0 (`impersonate="chrome"`) probes hitting the production site. Every endpoint, parameter, cap and ID structure below was verified against the real server (no proxy, datacenter IP). Total inventory: ~120,066 cars (`r=VVO00000` total counter).

---

## 1. Anti-bot stack — **Apache, no WAF** [VERIFIED]

`GET https://www.paruvendu.fr/robots.txt`:

```
STATUS 200
server: Apache
strict-transport-security: max-age=31536000
content-type: text/plain
```

No Cloudflare (`cf-ray`/`__cf_bm` absent), no Akamai, no DataDome. Naked `curl_cffi` `impersonate="chrome"` is sufficient for every surface tested (home, listing index, search endpoint, ad detail). Datacenter egress was tolerated for the entire research run — the only realistic risk is volumetric per-IP rate limiting at fleet scale. **Tier.T1** in `domain_map.py`.

---

## 2. Search endpoint — `/auto-moto/listefo/default/default` [VERIFIED]

The "Annonces auto" form on `https://www.paruvendu.fr/voiture-occasion/` posts as `GET` to:

```
GET https://www.paruvendu.fr/auto-moto/listefo/default/default?<filters>&p=N
```

Discovered from the markup: `<form id="search-auto" method="get" action="/auto-moto/listefo/default/default">`. The form's verified query vocabulary (every name pulled from the live HTML and re-verified by hitting the endpoint with the corresponding counter):

| Param | Meaning | Verified example |
|---|---|---|
| `r`   | top-level rubric. `VVO00000` is the cars rubric (voiture-occasion). | `VVO00000` |
| `p`   | **page number, 1-based** | `1`, `500` |
| `px0` | price floor (EUR) | `0` |
| `px1` | price ceiling (EUR) | `5000`, `10000` |
| `a0`  | year floor (first-registration) | `2020` |
| `a1`  | year ceiling | `2022` |
| `km0` | km floor | (numeric) |
| `km1` | km ceiling | `50000` |
| `tri` | sort key (default `indiceQualite`) | `indiceQualite` |
| `ord` | sort order (`desc`/`asc`) | `desc` |

Verified counter effect (the page contains `<N>annonces`):

```
r=VVO00000                            → 120 066 annonces
r=VVO00000&px0=0&px1=5000             →   5 844
r=VVO00000&px0=5000&px1=10000         →  13 125
r=VVO00000&km1=50000                  →  53 890
r=VVO00000&a0=2020&a1=2022            →  29 523
```

The brief's candidate names `pxmin/pxmax/anmin/anmax/kmmax` are **rejected** — they all returned the unfiltered 120,066 baseline. Only the `*0/*1` form is honoured.

### Sort parameter — irrelevant to discovery

`tri=indiceQualite` is the default; sorting changes the order of pages, not the set of ads ultimately reached. The scraper leaves it untouched.

---

## 3. Listing layout & detail URL [VERIFIED]

Each search result page is server-rendered HTML containing **25 unique ads** (the first card sometimes duplicates as a sponsored slot, giving 26 anchor occurrences — dedup is required within a page). Each detail link has the canonical shape:

```
/a/voiture-occasion/<brand-slug>/<model-slug>/<AD_ID>
```

Example IDs in the wild (verified live):

```
/a/voiture-occasion/citroen/c3/1291268067A1KVVOCIC3
/a/voiture-occasion/cupra/formentor/1291561002A1KVVOCUFOR
/a/voiture-occasion/peugeot/308/1291560917A1KVVOPE308
```

`AD_ID` is `^[A-Z0-9]+$` (digits + uppercase alphanumerics; the suffix encodes the rubric). The host is fixed at `https://www.paruvendu.fr`. A naked GET on a detail URL returns 200 with the full ad page.

---

## 4. Pagination cap — **500 pages (~12,500 ads/query)** [VERIFIED]

Live binary search confirms a hard cap. With `r=VVO00000`:

| Page | Behaviour |
|---|---|
| `p=1..500` | normal, disjoint result sets (0% overlap p1↔p2..p500) |
| `p=501..∞` | server silently **rewinds to page 1's result set** and serves it for every higher index |

Concretely, `p=501` shares 25/26 IDs with `p=1`; `p=510`, `p=1000`, `p=5000`, `p=9000` are all functionally identical to `p=1`. The pager UI tops out around 500 (≈12,500 effective ads/query against a 120,066 total). The brief's "go very wide" candidate must be rejected — past page 500 the portal feeds duplicates and the dedup `seen` set will silently absorb them.

**Implication:** the inventory is 120,066 but the cap reachable per query is ~12,500, so a year × price grid is mandatory. The scraper sets `PAGE_SIZE=25`, `MAX_PAGES=500`, and lets `BasePortalScraper` subdivide any cell that saturates.

### Why `PAGE_SIZE=25` not 26

Page bodies contain 25 unique IDs + 1 sponsored-slot duplicate of a previous-page ad. The base scraper detects "segment exhausted" via `len(page_urls) < PAGE_SIZE`, so PAGE_SIZE must be the count the page actually returns *after* dedup — that's 25 in the canonical run. (The dedup happens inside `_extract`.)

---

## 5. Partitioning — year band × price band over all makes

The make filter uses the `r` parameter with an opaque code (`VVOAU000` = Audi, `VVOBM000` = BMW, …). The full make table is in-page (`<li data-codeRub="VVO**000">`) but adopting it introduces a reference-data dependency the engine doesn't want. Year × price is enough: 11 year bands × 8 price bands = 88 cells, well below the 12,500/cell ceiling for a 120k inventory. A saturated cell is subdivided into per-year × finer-price sub-cells via the standard one-level `subdivide_segment`.

---

## 6. Block signals

Apache's plain 4xx/5xx are the only block signatures observed in the research run:

| Status | Treatment |
|---|---|
| 200 | parse, extract |
| 403/429/503 | retry with exponential backoff (3 attempts) |
| other 4xx/5xx | terminal — return empty (no retry) |

No JS challenge, no DataDome marker, no Cloudflare interstitial seen — there is nothing to body-sniff for. The scraper does not need a soft-block detector beyond the status-code path.
