# autosphere.fr — T0 (Open REST API)

## Status: ALIVE, IMPLEMENTED

## Summary
Autosphere is the largest French car dealer network (Emil Frey group).
~15,600 used vehicles. Next.js App Router with an exposed REST API at
/api/stock/vehicles returning paginated JSON. No WAF.

## API Details
- Endpoint: GET https://www.autosphere.fr/api/stock/vehicles
- Params: voiture=occasion, sortField=popularity, sortDirection=asc,
          internal_type=vo,vd, size={N}, from={offset}
- Response: {results: [{slug, id, brand, model, ...}], total: N}
- Detail URL: https://www.autosphere.fr/recherche/{slug}
- Pagination: from/size (0-indexed), no server cap detected

## Technical Stack
- Frontend: Next.js App Router
- Images: AWS S3 (s3.eu-west-1.amazonaws.com/eff-afr-cms-prd/)
- WAF: None
- CDN: Standard (not Cloudflare)

## Scraper: autosphere_fr (T0)
