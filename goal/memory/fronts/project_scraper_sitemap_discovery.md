---
name: project-scraper-sitemap-discovery
description: "CARDEX scraper fleet — sitemap-listing discovery base, which portals use it, and the dead-code/dead-portal map (2026-06)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 06225ebb-d4c7-4e2e-b02e-770d014f0d34
---

Multi-strategy investigation of all 57 T0/T1 portals (2026-06-06): a scraper's job is
**deep-link (detail-URL) discovery** for the sink, NOT data extraction (that's the Go
extraction stage) — so a **listing-level sitemap** is the ideal source.

**New base `scrapers/portals/sitemap_listing_base.py` → `SitemapListingScraper`**: walks
sitemap index→children, gunzips `.gz` by magic bytes, `CHILD_RE` filters shards,
`DETAIL_RE` emits detail `<loc>`s, all inside `fetch_segment` page 1. 19 portals migrated
to it: marktplaats.nl, 2dehands.be, 2ememain.be, autokopen.nl, cardoen.be, vroom.be,
gowago.ch, aramisauto.com, annonces-automobile.com, carizy.com, capcar.fr,
occasions.jeanlain.com, gueudet.fr, distinxion.fr, ocasionplus.com, autoboerse.de,
truckscout24.com, classic-trader.com, simplicicar.com. caravenue.com migrated to internal
API `/api/search-results`.

**Key architectural fact:** the coordinator calls `scraper.run()` directly and **NEVER
calls `load_segments_from_sitemap`** → `HtmlSearchScraper`/`HttpPortalScraper` and the
legacy flat files (`portals/{marktplaats,leboncoin,lacentrale,kleinanzeigen,mobile_de,
cochesnet}.py`, `nl/autotrack.py`, `es/autocasion.py`) are **dead code** (not in
PORTAL_REGISTRY, which keys on the package `<dir>/__init__.py`). [[project-storage-reality]]

**Dead/broken portals (do not trust as live):** reezocar.com (closed 2024-11-04),
carforyou.ch (redirects to globalipaction.ch), nederlandmobiel.nl (now Cloudflare managed
JS — curl_cffi does NOT pass). Broken regex scrapers (extract 0): moniteurautomobile.be,
flexicar.es, buscocoches.com, belgiemobiel.be, autowereld.nl. leparking.fr docstring lies
("T1/no WAF" — it's Cloudflare-managed).

Full table + evidence: `docs/MULTI_STRATEGY_PORTALS_2026-06.md`. Pre-existing failing test
`test_t1_portals.py::test_t1_registry_resolves_both_portals` (stale, references legacy
classes) — not caused by this work.
