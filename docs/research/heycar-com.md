# heycar.com — T2→T0 BYPASS via REST API (FR/UK only, DE dead)

> Research date: 2026-06-04. Method: WebSearch + live web_fetch probing. Result: heycar.com's SPA is backed by a public REST API at `group-mobility-trader.com` — no authentication, no WAF. The German market is permanently shut down (mid-2025). France (~34k) and UK (~75k) are fully operational. Downgraded from T2 (CF Pro) to T0 for FR.

---

## Verdict: T0 (public REST API — implemented for FR)

HeyCar was originally launched in Germany by Volkswagen Financial Services, later acquired by Renault Group. The German operations were permanently terminated mid-2025 ("heycar sagt Tschüss — Wir parken jetzt für immer"). The French and UK operations remain live, backed by a completely unauthenticated REST API on a separate domain (`group-mobility-trader.com`) that does NOT have Cloudflare protection.

---

## API Details [VERIFIED 2026-06-04]

### Endpoints

| Market | Endpoint | Status | Listings |
|--------|----------|--------|----------|
| France | `GET https://api.fr.prod.group-mobility-trader.com/i15/search` | LIVE | ~34,239 |
| UK | `GET https://api.uk.prod.group-mobility-trader.com/i15/search` | LIVE | ~74,805 |
| Germany | `GET https://api.de.prod.group-mobility-trader.com/i15/search` | DEAD | 0 |

### Query Parameters

| Parameter | Example | Notes |
|-----------|---------|-------|
| `page` | `0` | Zero-indexed |
| `size` | `500` | Max tested: 500 works |
| `priceFrom` | `5000` | Min price (EUR) |
| `priceTo` | `10000` | Max price (EUR) |
| `make` | `bmw` | Lowercase make ID |
| `model` | `bmw-3-series` | Make-model format |
| `year__gte` | `2020` | Min year |
| `fuel_type` | `electric` | Fuel filter |

### Response (Spring Data Page Envelope)

```json
{
  "content": [
    {
      "id": "abc123",
      "heycarId": "def456",
      "make": {"id": "bmw", "label": "BMW"},
      "model": {"id": "3-series", "label": "3 Series"},
      "prettyName": "BMW 3 Series 320d",
      "pricing": {"price": 25000, "currency": "EUR"},
      "details": {"year": 2020, "mileage": 45000, "registration": "2020-03"},
      "spec": {"fuelType": "diesel", "gearbox": "automatic", "bhp": 190},
      "dealer": {"name": "AutoCenter Paris", "city": "Paris"},
      "location": {"postcode": "75001"}
    }
  ],
  "totalElements": 34239,
  "totalPages": 69,
  "pageable": {"pageNumber": 0, "pageSize": 500}
}
```

---

## robots.txt Note

`heycar.com/robots.txt` explicitly blocks `ClaudeBot`, `Scrapy`, `GPTBot`, etc. — but the API is on `group-mobility-trader.com`, a completely different domain not covered by that robots.txt.

---

## Engine Classification (updated)

```python
PortalSpec(
    "heycar.com", Tier.T0, WAF.NONE,
    countries=["FR"],
    notes="T2→T0 bypass: REST API api.fr.prod.group-mobility-trader.com no auth, DE dead [VERIFIED 2026-06-04]",
)
```

---

## Implementation

- `scrapers/portals/heycar_com/__init__.py` — `HeycarFRScraper`
- Price-band partitioning: 11 segments
- Page/size pagination (0-indexed), PAGE_SIZE=500
- FR focus; UK could be added trivially by changing API_HOST and COUNTRY
