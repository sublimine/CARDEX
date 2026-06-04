# aramisauto.com — T1 (Next.js SSR + CF CDN)

## Status: ALIVE, IMPLEMENTED

## Summary
Aramis Auto is the European leader in online used car reconditioning/sales.
~2,900 used vehicles. Next.js with Cloudflare CDN for images but no WAF challenge.

## Scraping Details
- Search URL: GET https://www.aramisauto.com/achat/occasion/?page={PAGE}
- Listings: <a href="/achat/{brand}/{model}/details/{ID}">
- Pagination: ?page=N. ~24 per page.
- WAF: CF CDN (images only), no challenge

## Scraper: aramisauto_fr (T1)
