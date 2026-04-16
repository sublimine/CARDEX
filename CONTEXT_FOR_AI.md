# CONTEXT_FOR_AI.md — Authoritative AI/Developer Onboarding

**Read this before anything else.** This document is the ground truth about what CARDEX is, what is implemented, and what is not. It is designed to prevent an AI assistant from confusing the vision with the reality.

---

## What this project is

CARDEX is a pan-European vehicle intelligence platform that discovers used-car listings from individual dealer websites across DE, ES, FR, NL, BE, and CH. It is NOT a marketplace — it builds an index of what dealers have for sale, validated for quality.

---

## What IS implemented (as of 2026-04-15)

### Phase 2 — Discovery (`discovery/`)

Go module `github.com/cardex/discovery`. Finds dealer URLs via 15 intelligence families:

| Family | Source |
|--------|--------|
| A | Business registries (INSEE/Sirene FR, KvK NL, KBO BE, Handelsregister DE, UID-Register CH, AEOC ES) |
| B | OpenStreetMap Overpass + Wikidata SPARQL |
| C | Wayback Machine + crt.sh SSL certificates + passive DNS |
| D | CMS fingerprinting (WordPress, Drupal, Joomla, etc.) |
| E | DMS infrastructure detection (Incadea, MotorManager, Autentia) |
| F | Marketplace listing backlinks (mobile.de, AutoScout24, La Centrale) |
| G | Trade associations (BOVAG NL, TRAXIO BE, Mobilians FR) |
| H | OEM dealer locators (VWG, BMW, Mercedes, Stellantis, Toyota, Hyundai, Renault, Ford) |
| I | Inspection/certification networks (TÜV, DEKRA, Applus, AUTOVISTA) |
| J | Sub-jurisdictions (Pappers FR, province classifiers NL/BE) |
| K | SearXNG meta-search (multi-instance) |
| L | Social profiles (YouTube active, Google Maps/LinkedIn stubs) |
| M | VAT/UID validation (VIES EU, CH UID-Register) |
| N | Infrastructure intelligence (Censys, Shodan, DNS enum, reverse IP) |
| O | Press archives (GDELT, RSS feeds, Wayback stub) |

### Phase 3 — Extraction (`extraction/`)

Go module `github.com/cardex/extraction`. Extracts vehicle listings using 12 strategies:

| Strategy | Method |
|----------|--------|
| E01 | JSON-LD structured data parsing |
| E02 | CMS REST API (WordPress WP-JSON, custom REST) |
| E03 | Sitemap XML enumeration |
| E04 | RSS/Atom feed parsing |
| E05 | DMS API (Incadea, MotorManager, Autentia native APIs) |
| E06 | Microdata + RDFa parsing |
| E07 | Playwright XHR interception (JS-heavy sites) |
| E08 | PDF extraction (inventory sheets) |
| E09 | Excel/CSV extraction |
| E10 | Email/EDI ingestion |
| E11 | Edge push (Tauri client, Priority=1500 — Phase 4 gRPC wiring pending) |
| E12 | Manual review queue (Priority=0 — last resort, enqueues dealer for human review) |

### Phase 4 — Quality (`quality/`)

Go module `github.com/cardex/quality`. 20 validators:

| Validator | What it checks |
|-----------|---------------|
| V01 | VIN format + Luhn checksum (17-char NHTSA standard) |
| V02 | NHTSA recall lookup (US VINs via api.nhtsa.dot.gov) |
| V03 | DAT valuation database cross-reference |
| V04 | NLP make/model consistency check |
| V05 | Image quality (resolution, blur, NSFW) |
| V06 | Photo count (minimum threshold by vehicle type) |
| V07 | Price range plausibility (per make/model/year) |
| V08 | Mileage range plausibility |
| V09 | Year range plausibility |
| V10 | Source URL liveness (HTTP HEAD check) |
| V11 | NLG description quality (stopword ratio, length, boilerplate) |
| V12 | Cross-source deduplication (fingerprint_sha256 collision) |
| V13 | Completeness (required fields populated) |
| V14 | Freshness (listing age, last-seen delta) |
| V15 | Dealer trust score |
| V16 | Perceptual hash photo deduplication (goimagehash, distance ≤4) |
| V17 | Sold status detection (HTTP 410, body keywords in 6 languages, schema.org) |
| V18 | Language consistency (listing language vs. dealer country) |
| V19 | Currency/price validity (zero/negative/unreasonable) |
| V20 | Composite scorer — PUBLISH / MANUAL_REVIEW / REJECT |

### Phase 5 — Deploy (`deploy/`)

Single Hetzner CX42 VPS (~€22/month). Key files:

- `deploy/docker/Dockerfile.{discovery,extraction,quality}` — multi-stage Go builds → distroless
- `deploy/docker/docker-compose.yml` + `docker-compose.prod.yml` — dev + prod overlays
- `deploy/systemd/cardex-{discovery,extraction,quality}.service` — production systemd units
- `deploy/caddy/Caddyfile` — TLS 1.3, HSTS, routes to 3 services
- `deploy/observability/` — Prometheus + Grafana dashboards + Alertmanager rules (8 alerts)
- `deploy/scripts/deploy.sh` — idempotent deploy with automatic rollback
- `deploy/scripts/backup.sh` — age-encrypted daily backup to Hetzner Storage Box
- `deploy/runbook.md` — 12-step VPS provisioning guide

---

## What is NOT implemented

Do not assume any of the following exist in working code:

- **PostgreSQL / ClickHouse** — not present in MVP. Storage is SQLite.
- **Redis** — not present in MVP.
- **MeiliSearch** — not present in MVP.
- **Full microservices** (`services/gateway`, `services/pipeline`, `services/forensics`, `services/alpha`, `services/legal`) — stubs only, not deployed, not wired to discovery/extraction/quality.
- **Next.js frontend** (`apps/web/`) — present in repo, not deployed.
- **Chrome extension** (`extensions/chrome/`) — present in repo, not deployed.
- **B2B webhook ingestion** — not implemented.
- **Tax/FX engine** — not implemented. Quality module validates price in EUR but does not compute taxes.
- **Financial engine (SDI, NLC, quotes)** — not implemented.
- **Multi-node cluster** (3× AX102) — single CX42 is the deployed target.

---

## What is future (Innovation Roadmap)

`planning/02_MARKET_INTELLIGENCE/06_INNOVATION_ROADMAP.md` describes 5 future AI/ML enhancements:
1. GNN fraud detection
2. VLM computer vision for vehicle photos
3. RAG buying assistant
4. Chronos-2 price forecasting
5. BGE-M3 multilingual entity resolution

**These are a 12-month post-MVP roadmap. None are implemented.**

---

## Key architectural decisions to understand

**Why SQLite instead of PostgreSQL?**
The MVP needs to run on a single ~€22/month VPS. SQLite with WAL mode is sufficient for the discovery/extraction/quality pipeline. The full SPEC.md vision uses PostgreSQL 16 + ClickHouse, but that requires 3× AX102 nodes (~€327/month).

**Why GOWORK=off for builds?**
Each of the three modules (discovery, extraction, quality) is independently deployable. Using `GOWORK=off` prevents workspace interference and ensures each service's `go.mod` is self-sufficient.

**Why is there a go.work with services/* references?**
The `go.work` file predates the Phase 2–5 focus. It includes `services/alpha`, `services/gateway`, etc. These modules exist in the repo as the foundation for future full-stack development. They are NOT built or deployed by any current process. Workspace mode is never used for production builds.

**Why are there Python scrapers in `scrapers/`?**
These were the original data acquisition approach before Phase 3 (extraction/ Go module) was built. They were cleaned in Phase 0 (P0 purge: removed stealth UA, proxy rotation, TLS impersonation). They are now honest `CardexBot/1.0` scrapers but they are NOT wired to the current pipeline. They represent a parallel marketplace-scraping strategy that may be revisited.

**What was the P0 purge?**
Commit `ed5e54f cleanup(P0)`. Removed all techniques deemed illegal under CARDEX institutional regime: UA spoofing, TLS impersonation (`curl_cffi`), `playwright-stealth`, proxy rotation for WAF evasion, CAPTCHA solving. A Forgejo CI workflow (`illegal-pattern-scan.yml`) now blocks these patterns.

---

## Development workflow

```bash
# Always use GOWORK=off to build/test the three core modules
cd discovery  && GOWORK=off go test ./...
cd extraction && GOWORK=off go test ./...
cd quality    && GOWORK=off go test ./...

# Each module has config via env vars (see cmd/*/main.go)
# Each module exposes HTTP API + Prometheus metrics endpoint
# Integration: deploy/scripts/test-deploy-local.sh
```

---

## Non-negotiable constraints

1. **CardexBot UA only.** `CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)`. CI blocks anything else.
2. **robots.txt compliance.** Never crawl disallowed paths.
3. **Rate limiting.** Default 0.3 req/s per domain. Configurable via Redis (future) or env var.
4. **No secrets in git.** `.gitignore` covers all key/cert/env patterns. The `deploy/secrets/` directory is gitignored.
5. **SQLite integrity.** Always `PRAGMA wal_checkpoint(FULL)` before backup. Always `PRAGMA integrity_check` after restore.
6. **GOWORK=off for all three core module builds.** Never rely on workspace resolution.

---

## File trust hierarchy

When there is a contradiction between files, trust in this order:

1. **This file (CONTEXT_FOR_AI.md)** — ground truth for what is real
2. **The code itself** (`discovery/`, `extraction/`, `quality/`) — what actually runs
3. **`deploy/`** — what actually gets deployed
4. **`planning/`** — specifications (may describe future state)
5. **`SPEC.md`** — original vision (pre-implementation, partially superseded)
6. **Anything else** — treat as potentially outdated
