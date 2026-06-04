# starterre.fr — T1 (SSR HTML)

## Status: ALIVE, IMPLEMENTED

## Summary
Starterre is a French car broker (mandataire) selling 0km and used vehicles.
~7,300 listings. SSR HTML with jQuery, Axeptio consent.

## Scraping Details
- Search URL: GET https://www.starterre.fr/recherche?page={PAGE}
- Listings: <a href="/vehicule/{slug}">
- Pagination: ?page=N. ~20 per page.
- WAF: None

## Scraper: starterre_fr (T1)
