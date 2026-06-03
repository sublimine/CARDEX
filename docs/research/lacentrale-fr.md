# Research: lacentrale.fr — French Cars Marketplace (CARDEX)

> Investigation date: 2026-06-03. Method: live `curl_cffi` (`impersonate="chrome"`, v0.15.0)
> calls, real-browser capture via Playwright (DataDome solve + `__NEXT_DATA__` + network trace),
> WebSearch/WebFetch. Every fact tagged [VERIFIED] (observed live) or [ASSUMED] (inference only).

## TL;DR / Headline

- **WAF: DataDome (hard block).** [VERIFIED] Every `www.lacentrale.fr` request via plain
  `curl_cffi impersonate="chrome"` returns **HTTP 403** with `x-datadome: protected`,
  `set-cookie: datadome=...`, served via **CloudFront**. Block body loads
  `ct.captcha-delivery.com/i.js`. 100% coverage — even `/robots.txt` and `/sitemap.xml` are 403.
- **No separate API host.** [VERIFIED] `api.lacentrale.fr` = **NXDOMAIN**. No first-party
  `/api/`, `/graphql`, or search-XHR exists client-side — the network trace of a fully rendered
  page shows **only analytics/ad trackers**, no first-party data calls.
- **Architecture = Next.js SSR.** [VERIFIED in browser] Listings are rendered **server-side** and
  embedded as a **491 KB HTML string** inside `__NEXT_DATA__.props.pageProps.data.content`. The
  internal search API is server-only and never exposed to the client.
- **Best path = T3 headless browser** that solves DataDome, loads `/listing?...`, and parses the
  `vehicleCardV2` cards (or `data.content`). Optional optimization: harvest the `datadome` cookie
  in-browser, then replay `/listing?page=N` with `curl_cffi` + matching UA/TLS (hybrid).
- **Detail URL pattern:** `/auto-occasion-annonce-{id}.html`. [VERIFIED]
- **Pagination = `?page=N`; deep pages (≥120) still return fresh ads**, SEO pager exposes up to 200.
- **Tier: T3 (headless / anti-bot evasion).**

---

## 1. WAF / anti-bot — DataDome evidence [VERIFIED]

Plain `curl_cffi impersonate="chrome"` is blocked on **every** path:

```
GET https://www.lacentrale.fr/listing?makesModelsCommercialNames=RENAULT&priceMax=10000
  STATUS 403
  server: CloudFront
  x-datadome: protected
  x-dd-b: 3
  via: 1.1 ....cloudfront.net (CloudFront)
  set-cookie: datadome=~xkUwhJxXZLeCQX9...~; Max-Age=31536000; ...
  body (776 B):
    <html><head><title>lacentrale.fr</title>...</head><body>
    <p id="cmsg">Please enable JS and disable any ad blocker</p>
    <script>var dd={'rt':'i','cid':'AHrlqAAAAAMACBh011IxGhMAU03p_A==',
      'host':'geo.captcha-delivery.com', 'cookie':'~xkU...~'}</script>
    <script src="https://ct.captcha-delivery.com/i.js"></script></body></html>
```

Coverage probe (all 403, DataDome in body) [VERIFIED]:

| Path | Result |
|---|---|
| `/` (homepage) | 403 datadome |
| `/listing?...` | 403 datadome |
| `/auto-occasion-annonce-{id}.html` (detail) | 403 datadome |
| `/robots.txt` | 403 datadome |
| `/sitemap.xml` | 403 datadome |
| `/api/`, `/graphql`, `/_next/data/`, `/listing.json` | 403 datadome (ct `application/json`) |
| `api.lacentrale.fr` | **NXDOMAIN** (no such host) |
| `recherche.lacentrale.fr` | 404 `awselb/2.0` (AWS ELB, no content) |
| `m.lacentrale.fr` | NXDOMAIN |

DataDome classifies on TLS fingerprint + IP reputation + JS challenge, so curl-class clients are
rejected regardless of the `impersonate` profile. A real browser (or a solved `datadome` cookie)
is required.

---

## 2. Architecture — Next.js SSR (verified in a real browser)

A real Chromium (Playwright) **passes DataDome** and loads the listing page (title becomes
`"Voiture occasion - La Centrale"`). Key facts captured live [VERIFIED]:

- `__NEXT_DATA__` present: `buildId = "L4dJd4X-KgOciKT2IvLNs"` (rotates on deploy),
  `props.pageProps.data` = `{ content, scripts }`.
- `data.content` = **491 KB pre-rendered HTML** containing **24 listing cards** (server-rendered;
  it is HTML, not a JSON array of listing objects).
- **Network trace of the fully-loaded page = NO first-party data API.** Only third-party trackers
  fire: Sentry, Braze, Contentsquare, Kameleoon, Facebook Pixel, Google Ads/GTM, Amazon ads,
  DoubleClick, Trustpilot. There is **no XHR to a lacentrale search/GraphQL endpoint** — the search
  runs server-side inside `getServerSideProps`. [VERIFIED]

**Implication:** there is no clean internal JSON API to call. The data target is the rendered
listing markup (DOM cards or `data.content`).

---

## 3. Best endpoint — T3 HTML `/listing` (browser-rendered)

### Search URL [VERIFIED]

```
https://www.lacentrale.fr/listing?<filters>&page=N
```

### Filter params [VERIFIED — live URL + echoed in __NEXT_DATA__.query]

| Param | Meaning | Example |
|---|---|---|
| `makesModelsCommercialNames` | make[:model] (`::` also accepted) | `RENAULT:CLIO` / `RENAULT::CLIO` |
| `priceMin` / `priceMax` | price band (EUR) | `priceMax=15000` |
| `yearMin` / `yearMax` | first-registration year | `yearMin=2018` |
| `energies` | fuel | `energies=ess` (essence), `dies` (diesel), `elec` |
| `gearbox` | transmission | `gearbox=AUTO` |
| `vertical` | vehicle vertical | `vertical=carTruck` |
| `page` | page number (0-based seen in pager) | `page=2` |
| `mileageMin`/`mileageMax` | mileage band | [ASSUMED — common LC params] |
| `regions` / `departments` | geo filter | [ASSUMED — common LC params] |

Verified live request:
```
https://www.lacentrale.fr/listing?makesModelsCommercialNames=RENAULT%3ACLIO&priceMax=15000&yearMin=2018
  -> "6 842 annonces", 24 cards rendered
```

---

## 4. Listing-URL extraction pattern [VERIFIED in browser]

Each card is an `<a data-testid="vehicleCardV2" href="/auto-occasion-annonce-{id}.html">`.
Verbatim markup captured live:

```html
<a data-testid="vehicleCardV2" class="vehiclecardV2_vehicleCard__dIhwe ..."
   href="/auto-occasion-annonce-69119110240.html">
  ...
  <img alt="renault-clio-v-2023-manual-11068-km-essence"
       src="https://pictures.lacentrale.fr/classifieds/E119110240_STANDARD_0.jpg?format=webp&size=352x264&watermark=lc&signature=...">
  ...
```

- **Detail URL pattern:** `/auto-occasion-annonce-{id}.html` (id = stable numeric listing id, e.g.
  `69119110240`, `87103422055`). [VERIFIED]
- **Listing-id field:** the `{id}` in the href (also embedded in the image filename as
  `E{id-tail}_STANDARD_0.jpg`). [VERIFIED]
- Per-card data is readable from card text/attrs (captured live):
  `RENAULT CLIO V 1.0 TCE 91 EVOLUTION` · year `2023` · `Manuelle` · `11 068 km` · `Essence`
  · `14 490 €` · dealer `GARAGE BRIE DES NATIONS` · city `CHANTELOUP-EN-BRIE`. [VERIFIED]
- Image CDN: `https://pictures.lacentrale.fr/classifieds/E{...}_STANDARD_0.jpg`.

**Extraction (DOM or content-string):**
```js
[...document.querySelectorAll('a[data-testid="vehicleCardV2"]')].map(a => a.getAttribute('href'));
// or against data.content / raw HTML:
[...html.matchAll(/auto-occasion-annonce-(\d+)\.html/g)].map(m => m[1]);
```

---

## 5. Pagination + result cap [VERIFIED]

- **Pagination param:** `?page=N` query string. SSR pager links observed:
  ```
  /listing?...&page=1&...   /listing?...&page=2&...   ...
  ```
- **Page size:** 24 cards/page.
- **Depth:** `page=120` returns **24 fresh ads** (IDs disjoint from page 0) — deep paging works.
  [VERIFIED] SEO pager exposes page numbers up to **200**. For the verified query, 6841 annonces /
  24 ≈ 285 pages of logical results, but the navigable pager tops at ~200 → effective cap
  ≈ **200 × 24 ≈ 4800 ads/query**. [VERIFIED pager max = 200; exact server clamp beyond 200 not
  probed — ASSUMED ~200.]

---

## 6. DataDome handling + hybrid replay [VERIFIED feasibility]

After a successful in-browser solve, the cookie jar contains a **`datadome` cookie (137 chars)**
plus `access-token`, `visitor_id`, `search_id`. [VERIFIED present]

Two viable execution models:

1. **Pure T3 (simplest, robust):** drive a real/stealth headless browser per query; navigate
   `/listing?...&page=N`; read the cards from the DOM. Survives DataDome natively. Higher cost/page.
2. **Hybrid (T3 solve → T2 replay):** solve DataDome once in a browser, harvest the fresh
   `datadome` cookie + exact UA, then replay `/listing?...&page=N` with
   `curl_cffi(impersonate="chrome", cookies={"datadome": ...}, headers={"user-agent": <same UA>})`.
   The `datadome` cookie is **IP- and UA-bound and short-lived**, so the curl client must egress
   from the same IP and present the matching UA/TLS as the solver, and re-solve on the next 403.
   [Replay path is ASSUMED to work given the cookie is the gating token; not executed end-to-end in
   this pass — the cookie value is IP/session-bound and was not exfiltrated.]

Use a commercial DataDome-bypass/unblocker (ScrapingBee, Scrapfly, NetNut residential, etc.) if
in-house solving proves brittle — community threads confirm rotating datacenter proxies alone are
insufficient against DataDome here.

---

## 7. Grid-partition recommendation

Effective cap ≈ 4800 ads/query (200 pages × 24). Partition any query expected to exceed that.

**Recommended partition dimensions (cheapest → finest):**

1. **Make[:model]** (`makesModelsCommercialNames`) — primary, cheapest cut. ~40 makes, each model
   sub-splittable.
2. **Year band** (`yearMin`/`yearMax`) — single-year or 2-year bands.
3. **Price band** (`priceMin`/`priceMax`) — e.g. 0-5k, 5-10k, 10-20k, 20-40k, 40k+.
4. **Fuel / gearbox** (`energies`, `gearbox`) — final cut for dense make+year+price cells.
5. **Geo** (`regions`/`departments` [ASSUMED params]) — fallback.

**Strategy:** read the `"N annonces"` count on page 1 of each cell; if > ~4800, subdivide on the
next dimension. Page each cell up to the pager max. Dedup globally on the `{id}` from the detail
URL. Because every page costs a DataDome-passing request, minimize re-fetches: prefer wide cells
just under the cap over many tiny cells.

---

## 8. Tier + bottom line

**Tier: T3 (headless / anti-bot evasion).** lacentrale.fr is hard-blocked by DataDome on 100% of
surfaces; `curl_cffi` alone cannot fetch a single listing. There is no exploitable internal JSON
API — listings are SSR HTML in `__NEXT_DATA__.props.pageProps.data.content`. The single best path
is a DataDome-solving browser loading `/listing?<filters>&page=N` and parsing `vehicleCardV2` cards
for `/auto-occasion-annonce-{id}.html`. Optionally optimize with the hybrid cookie-replay once a
solve is in hand. Grid by make × year × price (× fuel/gearbox) to stay under the ~200-page pager
wall.

---

## Appendix — Confidence ledger

| Fact | Status |
|---|---|
| DataDome 403 on all `www.lacentrale.fr` paths via curl_cffi (incl. robots/sitemap) | [VERIFIED] |
| Block signature: `x-datadome: protected`, `datadome=` cookie, CloudFront, `ct.captcha-delivery.com/i.js` | [VERIFIED] |
| `api.lacentrale.fr` NXDOMAIN; no first-party API host | [VERIFIED] |
| Real browser passes DataDome; title "Voiture occasion - La Centrale" | [VERIFIED] |
| Next.js SSR; listings = HTML in `__NEXT_DATA__.props.pageProps.data.content` (491 KB, 24 cards) | [VERIFIED] |
| Network trace = only analytics/ad trackers, NO first-party search XHR/GraphQL | [VERIFIED] |
| Detail URL `/auto-occasion-annonce-{id}.html`; card `<a data-testid="vehicleCardV2">` | [VERIFIED] |
| Listing id = numeric in href; image `E{id}_STANDARD_0.jpg`; pic CDN pictures.lacentrale.fr | [VERIFIED] |
| Filter params makesModelsCommercialNames/price/year/energies/gearbox/page | [VERIFIED] |
| Pagination `?page=N`, 24/page, page=120 returns fresh ads, pager max 200 | [VERIFIED] |
| `datadome` cookie (137 ch) + access-token/visitor_id/search_id set after solve | [VERIFIED] |
| Hybrid curl_cffi cookie-replay works end-to-end | [ASSUMED — not executed] |
| Server clamp beyond page 200; mileage/region param names | [ASSUMED] |
