# wallapop.com — T2→T0 BYPASS via Mobile API

> Research date: 2026-06-04. Method: WebSearch + GitHub survey + Apify actor analysis. Result: wallapop.com's web frontend is protected by PerimeterX, but the mobile API at `api.wallapop.com` is an entirely separate service used by the mobile apps (Android/iOS) and returns clean JSON with no challenge, no token, no WAF. The portal is downgraded from T2 to T0.

---

## Verdict: T0 (mobile API bypass — implemented)

Wallapop is an Adevinta marketplace (Spain). The web frontend at `es.wallapop.com` runs PerimeterX Bot Defender — standard curl/curl_cffi is challenged immediately. However, the mobile API at `api.wallapop.com` is a separate backend that serves the Android/iOS apps and is **not** protected by PerimeterX. A simple GET with a mobile User-Agent returns paginated JSON results.

Multiple open-source scrapers on GitHub have been using this API successfully for years (davertor/wallapop-scraper, Tatuck/wallapop-scraper, toniprada/wallapopy, Neufal777/wallapop-go, josemamira/uapop).

---

## API Details [VERIFIED 2026-06-04]

### Search Endpoint

```
GET https://api.wallapop.com/api/v3/general/search
    ?category_ids=100
    &latitude={lat}&longitude={lon}&distance_in_km=100
    &min_sale_price={Pf}&max_sale_price={Pt}
    &order_by=newest
```

- **Category 100** = Cars
- **Geo-centric**: latitude + longitude + distance_in_km required
- **Mobile User-Agent**: Android Chrome UA required
- **Auth**: None. No cookies, no tokens, no X-Signature currently enforced on this endpoint.

### Pagination

- Cursor-based: response includes `next_page` (opaque base64 token)
- Pass as `?start={next_page}` for the next window
- 40 items per response (fixed, server-controlled)
- When `next_page` is absent or null, the segment is exhausted

### Response Schema

```json
{
  "search_objects": [
    {
      "id": "qzmykegqqxzv",
      "title": "BMW Serie 3 320d",
      "web_slug": "bmw-serie-3-320d-i909411232",
      "price": {"amount": 15000, "currency": "EUR"},
      "images": [{"original": "...", "small": "..."}],
      "location": {"latitude": 40.41, "longitude": -3.70, "city": "Madrid"},
      "flags": {"bumped": false, "highlighted": false}
    }
  ],
  "next_page": "eyJmaWx0ZXJzIjp7..."
}
```

### Detail URL

`https://es.wallapop.com/item/{web_slug}`

---

## X-Signature (HMAC-SHA256)

Wallapop's API has an `X-Signature` header mechanism (HMAC-SHA256, secret extracted from the mobile app binary by `rmonvfer/wallapop_secret`). Currently NOT enforced on the general search endpoint, but may be enforced in the future. The signature formula is:

```
HMAC-SHA256(
  key = base64_decode(SECRET_KEY),
  message = "/api/v3/{ENDPOINT}+#+{METHOD}+#+{TIMESTAMP}+#+"
)
```

If the API starts requiring it, the `WallapopComScraper` can be updated to generate signatures per-request.

---

## Engine Classification (updated)

```python
PortalSpec(
    "wallapop.com", Tier.T0, WAF.PERIMETER_X,
    countries=["ES"],
    notes="T2→T0 bypass: mobile API api.wallapop.com/api/v3 bypasses PerimeterX [VERIFIED 2026-06-04]",
)
```

---

## Implementation

- `scrapers/portals/wallapop_com/__init__.py` — `WallapopComScraper`
- Geographic partitioning: 8 Spanish cities × 100 km radius × 8 price bands = 64 segments
- Cursor pagination override: `_paginate()` tracks `next_page` token
- Detail URLs: `https://es.wallapop.com/item/{web_slug}`
