# annonces-automobile.com — T1 (SSR HTML)

## Status: ALIVE, IMPLEMENTED

## Summary
Annonces-Automobile is a French premium car classifieds portal with ~43,900
listings from professional dealers. Includes some Belgian dealer ads.

## Scraping Details
- Search URL: GET https://www.annonces-automobile.com/l-s/occasion?pg={PAGE}
- Listings: <a href="https://www.annonces-automobile.com/acheter/{slug}">
- Detail URL: https://www.annonces-automobile.com/acheter/{slug}
- Pagination: ?pg=N, 1-based. ~20 per page.

## Technical Stack
- Frontend: SSR HTML + jQuery
- WAF: None

## Scraper: annonces_automobile_com (T1)
