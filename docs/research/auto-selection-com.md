# auto-selection.com — T0 (Meilisearch Public API)

## Status: ALIVE, IMPLEMENTED

## Summary
Auto-Selection is a French professional dealer aggregator with ~113,700
listings from 1,200+ professional dealers. Uses Meilisearch search engine
with publicly accessible API endpoint.

## API Details
- Endpoint: POST https://meilisearch.auto-selection.com/multi-search
- Auth: x-meilisearch-api-key (public search key in page source)
- Request body: {"queries":[{"indexUid":"vehicles","q":"","filter":"brand=BMW",
  "sort":["created_at:desc"],"limit":100,"offset":0}]}
- Response: {"results":[{"hits":[{id, slug, brand, model, ...}], "totalHits": N}]}
- Detail URL: https://www.auto-selection.com/acheter/{slug}
- Pagination: offset/limit in body. Meilisearch cap 1000 hits per query.

## Technical Stack
- Frontend: Custom (no standard framework)
- Search: Meilisearch (meilisearch.auto-selection.com)
- Images: medias.auto-selection.com (AWS S3 backed)
- WAF: None

## Scraper: auto_selection_com (T0, partitioned by brand)
