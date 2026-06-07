"""
Dealer scraping system (frente C) — turn dealers WITH a website into real inventory.

The GOAL is the ~30k dealers that have a domain (and growing). Where the portal
fleet knows a handful of marketplaces by hand, this subsystem is config-driven and
self-describing: for each dealer it DETECTS how the site exposes its inventory,
SAVES a versioned extraction recipe, and EXECUTES it through the existing L1→L2
seam (``enrich_worker`` A6 + ``rich_consumer`` A7), persisting to ``vehicles``.

Nothing here rewrites the seam or the extractors — it composes them:
  * ``detector``    — probe a domain → ExtractionConfig (sitemap / wp / jsonld / E07).
  * ``harvester``   — RAM-safe, id-paged batch runner over discovery_candidates.
  * ``remediation`` — drift alert → re-detect → regenerate config → revalidate.
"""
