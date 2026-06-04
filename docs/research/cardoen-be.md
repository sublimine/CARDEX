# cardoen.be — T1 (SSR + CF CDN)

## Status: ALIVE, IMPLEMENTED

## Summary
Cardoen is a major Belgian multi-brand car dealer. ~850 used vehicles with
discounts up to -40%. Part of larger automotive group.

## Scraping Details
- Search URL: GET https://www.cardoen.be/fr/achat/occasions/?page={PAGE}
- Listings: <a href="/fr/achat/{brand}-{model}-{id}/">
- Pagination: ?page=N. SSR HTML.
- WAF: Cloudflare free/CDN

## Scraper: cardoen_be (T1)
