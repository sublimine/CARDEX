# moniteurautomobile.be — T1 (SSR HTML)

## Status: ALIVE, IMPLEMENTED

## Summary
Moniteur Automobile is the most visited automotive website in Belgium.
~114,628 used cars + 4,072 new vehicles. SSR HTML.

## Scraping Details
- Search: GET https://www.moniteurautomobile.be/marque--{brand}/acheter-auto/occasion.html?page={P}
- Listings: <a href="/voitures-occasion/{slug}.html">
- Pagination: ?page=N. SSR HTML.
- WAF: None detected

## Scraper: moniteur_auto_be (T1, partitioned by brand)
