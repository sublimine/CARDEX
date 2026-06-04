# autohero.com — T2→T0 BYPASS via GraphQL API

> Research date: 2026-06-04. Method: WebSearch + live web_fetch probing. Result: autohero.com's GraphQL API at `/v1/retail-customer-gateway/graphql/` returns full inventory with NO authentication, NO WAF, NO rate limiting observed. The `searchAdV9AdsV2` query accepts country, sort, offset/limit — returning complete car objects across 8 EU countries (~19k total). Downgraded from T2 (CF Pro) to T0.

---

## Verdict: T0 (public GraphQL API — implemented)

Autohero is Auto1 Group's consumer-facing B2C retail brand (Berlin). The frontend is a React SPA with Cloudflare on the web layer. However, the GraphQL gateway backing the SPA is directly accessible via POST with a JSON body — no cookies, no tokens, no CORS restrictions. Cloudflare does not intercept GraphQL requests at this endpoint.

---

## API Details [VERIFIED 2026-06-04]

### Endpoint

```
POST https://www.autohero.com/v1/retail-customer-gateway/graphql/
Content-Type: application/json
```

### Query

```graphql
{searchAdV9AdsV2(search:{
  filter:{field:"countryCode",op:"eq",value:"DE"},
  sort:"most_popular",
  limit:100,
  offset:0,
  properties:{
    filterByEligibleDate:true,
    firstPublishedDays:-30,
    includeProspective:true
  }
})}
```

- Return type is `RawJson` — no GraphQL sub-selection needed
- Max `limit`: 100 (200+ returns errors)
- Response: `{"data":{"searchAdV9AdsV2":{"total":7341,"data":[...]}}}`

### Car Object Fields (52 fields)

`id`, `stockNumber`, `manufacturer`, `model`, `subType`, `subTypeExtra`, `offerPrice`, `previousPrice`, `mileage`, `builtYear`, `countryCode`, `firstRegistrationYear`, `fuelType`, `driveTrain`, `gearType`, `kw`, `firstPublishedAt`, `publishedAt`, `mainImageUrl`, `ahMainImageUrl`, `fuelConsumption`, `co2Value`, `vatType`, `carUrlTitle`, `inShowroom`, `branchId`, `emissionSticker`, `emissionStandard`, `carPreownerCount`, `numberOfAccidents`, `numberOfDamages`, `hasFilledServiceBook`, `lastServiceOn`, `acceleration`, `ccm`, `monthlyPayment`, `downPriceMargin`

### Country Coverage

| Country | Code | Listings | Locale |
|---------|------|----------|--------|
| Germany | DE | ~7,341 | de |
| Italy | IT | ~3,445 | it |
| France | FR | ~3,344 | fr |
| Spain | ES | ~2,474 | es |
| Austria | AT | ~925 | at |
| Poland | PL | ~650 | pl |
| Netherlands | NL | ~628 | nl |
| Sweden | SE | ~481 | se |
| **Total** | | **~19,288** | |

### Detail URL

`https://www.autohero.com/{locale}/buy/{carUrlTitle}-{id}/`

---

## Engine Classification (updated)

```python
PortalSpec(
    "autohero.com", Tier.T0, WAF.NONE,
    countries=["DE","IT","FR","ES","AT","PL","NL","SE"],
    notes="T2→T0 bypass: GraphQL API /v1/retail-customer-gateway/graphql/ no auth [VERIFIED 2026-06-04]",
)
```

---

## Implementation

- `scrapers/portals/autohero_com/__init__.py` — `AutoheroCOMScraper`
- Country-based partitioning: 8 segments (one per country)
- Offset/limit pagination: `limit=100`, standard base class `_paginate`
- POST requests with JSON body (GraphQL)
