# Dealer Scraping System — PLAN / PROGRESO

> Branch `feature/dealer-scraping-system` (worktree, from main `b980f90`). NO push, NO main,
> NO `discovery_candidates` writes (read-only), NO Docker restart, NO schema migration.
> Frente C: dealers WITH website → real inventory. ~30.389 dealers with domain (verified live:
> DE 17859 · FR 5275 · NL 2925 · ES 1606 · CH 1491 · BE 1243).

## Reuse surface (verified, do NOT rewrite)
- `scrapers/portals/config.py` — versioned per-domain ExtractionConfig store (7 strategies incl. E07).
- `scrapers/pipeline/generic_extractor.py` — `discover_listing_urls` (sitemap+WP, SSRF-guarded) + `extract_listing` (static cascade) + `extract_dealer`.
- `scrapers/pipeline/playwright_extractor.py` — E07: `extract_listing_rendered`, `record_from_rendered`, `PlaywrightFetcher` (1 browser reused).
- `scrapers/enrich_worker.py` (A6) — `enrich_one` routes by config (E07 vs static); `run(limit, concurrency, e07_fetcher)`.
- `scrapers/rich_consumer.py` (A7) — ingestion_raw → `vehicles` (FX, fingerprint, vin_history).
- `scrapers/intelligence/drift_gate.py` — `evaluate(cfg, HarvestStats)` / `evaluate_volume`.
- `scripts/verify_seam_e07.py` — validate-with-limit-and-purge harness pattern (throwaway redis :56390).

## Build blocks
- [ ] B1 — Dealer config store: extend `config.py` (configs/dealers/, load fallback) so the seam routes dealer configs natively. +test.
- [ ] B2 — Detector `scrapers/dealer_scraping/detector.py`: domain → web-type (sitemap/wp/jsonld/SPA-E07/static) + catalog location → ExtractionConfig. +test.
- [ ] B3 — Harvester `scrapers/dealer_scraping/harvester.py`: RAM-safe id-paged cursor over discovery_candidates → per-dealer detect→discover(limited)→seam(A6 E07 conc 2-4 + A7)→measure→purge. +test.
- [ ] B4 — Drift + remediation `scrapers/dealer_scraping/remediation.py`: drift alert → re-detect → regenerate (version++) → revalidate. +test.
- [ ] B5 — CLI `scripts/run_dealer_scraping.py` + LIVE validation on real multi-country batch + measure + `DEALER_SCRAPING_REPORT.md`.
- [ ] B6 — Full suite green; commit on branch (NO push); final audit.

## RAM-safety invariants (non-negotiable)
- E07/Playwright concurrency MAX 2-4; ONE browser per batch, closed between batches.
- Cursor over DB (id-paged batches), never fetchall.
- Free memory between batches (drop refs + gc.collect()).
- validate-with-limit-and-purge in tests; full dump is VPS-only.
