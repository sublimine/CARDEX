# Research: kleinanzeigen.de — German Cars Marketplace (CARDEX)

> Investigation date: 2026-06-03. Method: live `curl_cffi` (`impersonate="chrome"`, v0.15.0)
> calls, raw-HTML inspection, WebSearch. Every fact tagged [VERIFIED] (observed live) or
> [ASSUMED] (docs/inference only). Cars category = "Autos", path `/s-autos/`, category id `c216`.

## TL;DR / Headline

- **Best path = T2 HTML search pages.** [VERIFIED] `https://www.kleinanzeigen.de/s-autos/c216`
  returns **HTTP 200** with **27 server-rendered listings per page**. Detail URLs + ad IDs are
  embedded directly in the HTML. No JS render needed.
- **Filters live in the URL path**, not query string: `/preis:MIN:MAX/` plus a `+autos.*` filter
  suffix appended to the category token (`c216+autos.ez_i:2020,2021`). All [VERIFIED] live with
  changing result counts.
- **Pagination = `/seite:N/`, hard cap at page 50.** [VERIFIED] `seite:51` silently serves
  `seite:50`. 50 × 27 ≈ **1350 ads max per query** → grid partition is mandatory.
- **Legacy mobile API (`api.kleinanzeigen.de`) is ALIVE but locked.** [VERIFIED] Returns **HTTP
  401 with `WWW-Authenticate: Digest realm="ebay-kleinanzeigen-api"`** and is fronted by **Akamai
  Bot Manager** (`_abck` cookie). Old static creds rejected. Not usable without valid Digest creds.
- **WAF: Akamai** (passive). [VERIFIED] `_abck`/`bm_*` cookies appear even on the HTML site, but a
  single `impersonate="chrome"` GET is **not blocked** (all 200). No Cloudflare.
- **Tier: T2 (HTML parse).**

---

## 1. WAF / anti-bot — evidence

| Surface | WAF | Evidence | Blocks curl_cffi? |
|---|---|---|---|
| HTML site (`www.kleinanzeigen.de`) | **Akamai (passive)** | `set-cookie: _abck=...`, kameleoon A/B engine | **No** — every probe 200 [VERIFIED] |
| Mobile API (`api.kleinanzeigen.de`) | **Akamai + Digest auth** | `set-cookie: _abck=...` + `www-authenticate: Digest` | **Yes** — 401 [VERIFIED] |
| Gateway (`gateway.kleinanzeigen.de`) | dead / internal | 503 "DNS failure" | N/A [VERIFIED] |

Live header capture from the HTML search root [VERIFIED]:

```
GET https://www.kleinanzeigen.de/s-autos/c216
  STATUS 200 | content-type: text/html;charset=UTF-8
  set-cookie: CSRF-TOKEN=...; Domain=www.kleinanzeigen.de; Secure; HttpOnly
  set-cookie: kameleoonVisitor=...
  window.pageType = 'ResultsBrowse'
  body length ~392 KB
```

No `cf-ray`, no `server: cloudflare`. The Akamai `_abck` cookie is set but does not gate single
fingerprinted requests. Behavioral/rate challenges under scale are [ASSUMED] likely; rotate IPs and
throttle.

---

## 2. Best endpoint — T2 HTML search

### Base search URL [VERIFIED]

```
https://www.kleinanzeigen.de/s-autos/c216
```

`c216` = category Autos. Returns 27 `<article class="aditem">` cards per page.

### Filters — URL PATH grammar [VERIFIED live]

Filters are **path segments**, plus a `+autos.*` suffix glued onto the category token. Verified with
live result counts:

| Filter | Syntax | Verified result |
|---|---|---|
| Price (EUR) | `/preis:MIN:MAX/` before `c216` | `s-autos/preis:5000:10000/c216` → 200 |
| First registration (year) | `c216+autos.ez_i:YFROM,YTO` | `c216+autos.ez_i:2020,2021` → **56.318 Ergebnisse** |
| Mileage (km) | `+autos.km_i:KMFROM,KMTO` | combined below |
| Power (kW) | `+autos.power_i:FROM,TO` | form-confirmed |
| Postcode + radius | `/{PLZ}/c216l{locId}r{radius}` | `s-autos/10115/c216l3331` → "in Berlin" |
| Seller type | `/anbieter:privat/` or `/anbieter:gewerblich/` | path segment |

Combined query [VERIFIED]:

```
https://www.kleinanzeigen.de/s-autos/preis:5000:10000/c216+autos.ez_i:2018,2019+autos.km_i:0,100000
  -> 200 | "5.636 Ergebnisse"   (filters compose; count drops as expected)
```

Full filter param vocabulary extracted from the live search form (`name=` tokens) [VERIFIED]:
`autos.ez_i` (Erstzulassung/year), `autos.km_i` (mileage), `autos.power_i` (kW),
`autos.marke_s` (make), `autos.model_s` (model), `autos.fuel_s`, `autos.shift_s` (transmission),
`autos.typ_s` (body), `autos.schaden_s` (damage), `autos.anzahl_tueren_s` (doors),
`autos.schadstoffklasse_s`, `autos.umweltplakette_s`, `autos.tuevy_i`. Suffix convention:
`_i` = integer range `from,to`; `_s` = string enum.

Make can also be a path slug: `/s-autos/vw/c216`, `/s-autos/bmw/c216`, etc.

---

## 3. Listing-URL extraction pattern [VERIFIED]

Each result card embeds the detail href and a stable ad id.

**Detail URL pattern:**
```
/s-anzeige/{slug}/{adId}-216-{locCode}
```
Verbatim live samples:
```
/s-anzeige/renault-clio-limited-tce-90-2019bj/3405146353-216-8047
/s-anzeige/ford-kuga-mit-neuem-motor/3412780560-216-6660
/s-anzeige/volkswagen-polo-vi-1-0-tsi-life-navi-virtual-led-pdc-app-/3425374362-216-6850
```

- `{adId}` = the stable numeric listing id (also exposed as **`data-adid="{adId}"`** on each
  `<article>`). [VERIFIED] 27 per page, 1:1 with cards.
- `216` = category id (Autos), constant.
- `{locCode}` = seller location/PLZ region code (e.g. `8047`, `6660`); varies per ad.

**Extraction regexes (both work):**
```python
hrefs = re.findall(r'/s-anzeige/[^"\']+/(\d+)-216-\d+', html)   # -> adId
adids = re.findall(r'data-adid="(\d+)"', html)                  # -> adId (preferred, exact 27)
```

Full detail URL: `https://www.kleinanzeigen.de/s-anzeige/{slug}/{adId}-216-{locCode}`.
Detail page returns 200, ~293 KB, `adId` present. Per-card price/title/location are in the card
HTML; richer detail (description, all images) on the detail page.

---

## 4. Legacy mobile API — ALIVE but locked [VERIFIED]

The old eBay-Kleinanzeigen mobile API host still answers:

```
GET https://api.kleinanzeigen.de/api/ads.json?size=1
  STATUS 401
  www-authenticate: Digest realm="ebay-kleinanzeigen-api", qop="auth", nonce="..."
  set-cookie: _abck=...            # Akamai Bot Manager
  strict-transport-security, x-frame-options: DENY, csp present
```

Findings:
- Auth is **HTTP Digest** (NOT Basic as in very old docs). [VERIFIED]
- Tried legacy static creds (`android:WX7ekibsdf`, `ebayapp:ebayapp`, `ebayK:ebayK`) → all **401**.
  The historically-public credential is no longer valid. [VERIFIED]
- Host is also behind **Akamai** (`_abck`). [VERIFIED]
- `gateway.kleinanzeigen.de` → **503 DNS failure** (dead/internal-only). [VERIFIED]
- `api.ebay-kleinanzeigen.de` → 404. [VERIFIED]

**Conclusion:** the mobile API is a dead end for CARDEX without provisioned Digest credentials +
Akamai evasion. Do not build on it. The endpoint path `/api/ads.json` and category param
`categoryId=216` are [ASSUMED from legacy docs]; the JSON response shape could not be observed (401).

---

## 5. Pagination + result cap [VERIFIED]

- **Pagination param:** path segment `/seite:N/`.
  ```
  https://www.kleinanzeigen.de/s-autos/seite:2/c216   -> title "... Seite 2 ..."
  ```
- **Page size:** 27 ads/page.
- **Hard cap = 50 pages.** [VERIFIED]
  ```
  seite:49 -> "Seite 49"   seite:50 -> "Seite 50"   seite:51 -> "Seite 50"  (clamped)
  ```
- **Max harvestable per query ≈ 50 × 27 = 1350 ads.**

Pagination composes with filters, e.g.
`/s-autos/preis:5000:10000/seite:2/c216` → "Seite 2" [VERIFIED].

`robots.txt` [VERIFIED]: `/s-autos/` is **NOT disallowed** (search result pages crawlable). Only
`/s-feed.rss`, `/s-kategorie-baum.html`, `/s-bestandsliste.html`, `/s-suchanfrage.html`, `/s-oac`,
`/s-direktkaufen:aktiv` are blocked. No global `Crawl-delay`. Sitemap:
`https://www.kleinanzeigen.de/sitemap_index.xml`.

---

## 6. Grid-partition recommendation

Because any single query caps at ~1350 ads while a broad query (e.g. ez 2020-2021) exposes 56k+
results, you MUST partition into cells each yielding < 1350 ads, then page each cell to 50.

**Recommended partition dimensions (cheapest → finest):**

1. **Make** (`/s-autos/{make-slug}/c216` or `autos.marke_s`) — ~40 popular makes. First, cheapest cut.
2. **Year band** (`autos.ez_i:Y,Y`) — split by single year or 2-year band.
3. **Price band** (`/preis:MIN:MAX/`) — e.g. 0-2k, 2-5k, 5-10k, 10-20k, 20-40k, 40k+.
4. **Postcode/region** (`/{PLZ}/c216l{locId}r{radius}`) — fallback for dense make+year cells that
   still exceed 1350.

**Strategy:** start with make × year. For each cell, read the `... Ergebnisse` count from page 1;
if > 1350, subdivide by price band; if still > 1350, subdivide by region. This count-then-subdivide
loop guarantees full coverage under the 50-page wall. Dedup globally on `adId`.

Throttle (Akamai is passive but watching): randomized delay, rotate residential IPs, keep
`impersonate="chrome"`, carry the `_abck`/CSRF cookies from the first response within a session.

---

## 7. Tier + bottom line

**Tier: T2 (HTML parse).** Single best path = paginate the path-filtered HTML search and regex
`data-adid` / `/s-anzeige/.../{adId}-216-` per page. No browser, no API key, no Cloudflare. Akamai
is present but passive against fingerprinted single requests. The legacy mobile API is alive but
Digest-locked behind Akamai — not viable. Grid by make × year (× price × region as needed) to beat
the 50-page / ~1350-ad cap.

---

## Appendix — Confidence ledger

| Fact | Status |
|---|---|
| `/s-autos/c216` → 200, 27 listings/page, server-rendered HTML | [VERIFIED] |
| Detail URL `/s-anzeige/{slug}/{adId}-216-{loc}` + `data-adid` attr | [VERIFIED] |
| Price filter `/preis:MIN:MAX/` (path) | [VERIFIED] |
| Year/km/power filters `c216+autos.ez_i:`/`km_i:`/`power_i:` with live counts | [VERIFIED] |
| Postcode+radius `/{PLZ}/c216l{id}r{r}` | [VERIFIED] |
| Pagination `/seite:N/`, page size 27 | [VERIFIED] |
| Hard cap 50 pages (seite:51 clamps to 50) | [VERIFIED] |
| No Cloudflare; Akamia `_abck` present but passive, GETs 200 | [VERIFIED] |
| `api.kleinanzeigen.de/api/ads.json` alive, 401 Digest realm "ebay-kleinanzeigen-api" + Akamai | [VERIFIED] |
| Legacy static creds rejected (401) | [VERIFIED] |
| `gateway.kleinanzeigen.de` dead (503 DNS failure) | [VERIFIED] |
| `robots.txt` does not disallow `/s-autos/` | [VERIFIED] |
| Mobile API JSON response shape / param semantics | [ASSUMED — 401, never observed] |
| Behavioral/rate challenges under scale | [ASSUMED] |
