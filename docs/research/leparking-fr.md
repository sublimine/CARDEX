# leparking.fr — T1 (SSR HTML Meta-Aggregator)

## Status: ALIVE, IMPLEMENTED

## Summary
Le Parking is the largest French car aggregator, indexing ~14.8 million
listings from 926 referenced sites across Europe.

## Scraping Details
- Search URL: GET https://www.leparking.fr/voiture-occasion/{marque}.html?p={PAGE}
- Listings: HTML <a class="linkAd" href="/voiture-occasion/{slug}.html">
- Detail URL: https://www.leparking.fr/voiture-occasion/{slug}.html
- Pagination: ?p=1, ?p=2, ... SSR HTML. Empty page = end.
- ~20 ads per page

## Technical Stack
- Frontend: SSR HTML + jQuery
- Consent: Sibdata
- Ads: Google AdSense, DoubleClick (very ad-heavy)
- WAF: None

## Scraper: leparking_fr (T1, partitioned by brand)
