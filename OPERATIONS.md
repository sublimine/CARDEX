# CARDEX Operations

Generated: 2026-04-11 autonomous window.

## Pipeline overview

```
    ┌──────────────────────┐
    │  discovery sources   │  (orchestrator + specialised sources)
    │  • osm / osm_exp     │
    │  • sirene_v311 API   │
    │  • trustpilot        │
    │  • ct_logs           │
    │  • oem:bmw           │
    │  • name2dom (crt.sh) │
    └──────────┬───────────┘
               ▼
    discovery_candidates (Postgres)
               │
               ▼
    ┌──────────────────────┐
    │  sitemap_resolver    │  probes robots.txt / sitemap_index for each domain
    │  → sitemap_status    │
    └──────────┬───────────┘
               │ status=found
               ▼
    ┌──────────────────────┐
    │  sitemap_bridge      │  drains each <loc> into vehicle_index
    │  + delta detection   │
    └──────────┬───────────┘
               │
               ▼
    vehicle_index (Postgres)           ← source of truth (url_hash pk)
               │
               ▼
    ┌──────────────────────┐
    │  meili_enricher      │  fetch HTML → extract → push Meili
    │  (8 sharded workers) │  deletes sold/dead from vi + Meili
    └──────────┬───────────┘
               ▼
    ┌──────────────────────┐
    │  repair_pass         │  re-fetch incomplete Meili docs
    │  + multi-extractor   │  cascade (7+ strategies, no delete)
    └──────────┬───────────┘
               ▼
    Meilisearch `vehicles` index → Next.js portal
```

## How to start everything

```bash
# 1. ensure docker containers are up
docker compose up -d

# 2. fix network alias for non-compose restarts (idempotent)
docker network disconnect cardex_default cardex-api 2>/dev/null || true
docker network connect --alias api cardex_default cardex-api

# 3. launch the watchdog (auto-restarts dead workers)
nohup bash scripts/watchdog.sh > /tmp/cardex-logs/watchdog.log 2>&1 &
echo $! > /tmp/cardex-pids/watchdog.pid

# 4. one-shot discovery sources (non-continuous)
INSEE_API_KEY=<key> nohup python -u -m scrapers.discovery.sources.fr_sirene_v311 \
  > /tmp/cardex-logs/sirene-v311.log 2>&1 &
nohup python -u -m scrapers.discovery.sources.osm_expanded_run \
  > /tmp/cardex-logs/osm-exp.log 2>&1 &
nohup python -u -m scrapers.discovery.sources.trustpilot \
  > /tmp/cardex-logs/trustpilot.log 2>&1 &
nohup python -u -m scrapers.discovery.sources.ct_logs \
  > /tmp/cardex-logs/ct-logs.log 2>&1 &
nohup python -u -m scrapers.discovery.name_to_domain \
  > /tmp/cardex-logs/n2d.log 2>&1 &
```

## How to check status

```bash
bash scripts/dashboard.sh
```

Prints: running processes, candidates by source, vehicle_index by country,
Meili completeness, enricher shard progress, recent logs.

## How to stop cleanly

```bash
kill $(cat /tmp/cardex-pids/watchdog.pid)      # stop watchdog first so it doesn't restart workers
for f in /tmp/cardex-pids/*.pid; do kill $(cat "$f") 2>/dev/null; done
```

## Data model invariants

1. **vehicle_index** is the source of truth. Every listing's URL exists here or nowhere.
2. **source_country** must be set on EVERY Meili doc. Otherwise portal filters break.
3. **No UPDATE of non-mutated rows** (MVCC doctrine). Only INSERT new + DELETE stale.
4. **Deletes happen** on: URL 404/410, sold markers, scam prices (< 500€ or > 2M€).
5. **Do NOT delete incomplete docs.** Every listing is somebody's ideal car.

## Extractor cascade (in priority order)

1. JSON-LD (`<script type="application/ld+json">`)
2. `__NEXT_DATA__` embedded SSR state (Next.js)
3. `window.__NUXT__` embedded SSR state (Nuxt)
4. `schema.org/Vehicle` microdata (itemprop)
5. dealerk body-class (`voitures-occasion city-X make-Y model-Z fuel-A`)
6. Per-CMS CSS selectors (`.vehicle-price`, `.vehicle-mileage`, …)
7. OpenGraph / meta tags (`og:title`, `og:image`, `og:description`)
8. Body text regex (`_scrape_price`, `_scrape_mileage`, `_scrape_year`, `_scrape_vin`, `_scrape_power`)
9. Sitemap image extension (parsed earlier by `sitemap_image_harvester`)

Each lower strategy ONLY fills holes left by higher strategies. No overwrites.

## Tests

```bash
PYTHONPATH=. python tests/test_enricher_extractors.py  # 9 tests
PYTHONPATH=. python tests/test_parse_int.py            # 13 tests
PYTHONPATH=. python tests/test_normalizers.py          # 47 tests
```

All 69 unit tests must pass before deploying enricher changes.

## Known limits

| Limit | Cause | Workaround |
|---|---|---|
| ~52% enricher hit rate | Dead domains, anti-bot, 404s, HTML timeouts | Repair pass retries with curl_cffi chrome124 |
| ~1.8% docs with all 5 critical fields | Most sitemap-image stubs are unenriched | Let enricher finish pass 1, then pass 2 after new extractors |
| crt.sh FTS yields only token matches | PostgreSQL full-text search over cert data | Use broader keywords, accept ceiling ~300-500 per query |
| Sirene only yields identity rows | SIRENE doesn't expose websites | name_to_domain resolves ~5% via crt.sh fuzzy |
| 150k dealer target not yet reached | ~100k candidates current ceiling | Continue running all sources, identity resolution, and watchdog cycles |

## Abandoned paths (DO NOT retry)

See `memory/project_cardex_seal_2026_04_10.md`.
