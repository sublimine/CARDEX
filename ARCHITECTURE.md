# CARDEX — Architecture

> **READ THIS FIRST (reconciled 2026-06-12).** The body of this document (§1–§8)
> describes the **Phase 2–5 Go MVP** (discovery/extraction/quality over SQLite on a
> single CX42). That stack is **DORMANT scaffold**: it compiles and tests, produces
> nothing, has zero production consumers, and **is not deployed**. It is NOT the
> production path. The **LIVE system** is the **Python fleet** (`scrapers/`) writing
> to **PostgreSQL 16** (Docker `cardex-pg`, the system of record) with **Redis
> Streams** as transport. See [`README.md`](README.md) and [`STATUS.md`](STATUS.md);
> code in `main` always wins over this document.

---

## 0. System reality — live vs dormant vs absent (read before §1)

### LIVE (the production path, verified 2026-06-12)

- **Python scraper fleet** (`scrapers/`) — portal + dealer scrapers, sitemap/listing
  indexers, coordinator, anti-OOM supervisor, enrichment seam
  (`enrich_worker` → `rich_consumer`).
- **PostgreSQL 16** (Docker `cardex-pg`) — **the live system of record**. Schema
  `migrations/0001`–`0007`; the `entity_inventory` view serves ~1.27M cars
  (1,270,369 on 2026-06-12). Doctrine: INSERT-new + DELETE-stale, never UPDATE
  non-mutated rows.
- **Redis Streams** — transport only; holding inventory state in Redis is prohibited.
- **`services/entity_api/`** — FastAPI per-entity live inventory API (`127.0.0.1:8088`).
- **`services/api/`** — Go REST price-intelligence API; runs on demand.
- **`scrapers/engine.db`** — SQLite for **engine state only**, by design (work queue,
  identities, circuits). This is the only SQLite in the live path; do not migrate it to PG.
- **Ollama `qwen2.5:3b`** — fuzzy-decision layer, fail-open.

### DORMANT (the Go scaffold this document describes)

`discovery/`, `extraction/`, `quality/` (plus `frontend/terminal/`, `innovation/`,
`internal/shared/`, `workspace/`, `tests/e2e/`) — they build and test with
`GOWORK=off`, write to their own SQLite (`discovery.db`), and produce nothing in
production. Do not "reactivate" them assuming they are prod.

### What does NOT exist (in either layer)

- ClickHouse OLAP; multi-node cluster (3× AX102)
- The CX42 VPS deployment described in §2 (`deploy/` infra is not currently deployed)
- Full microservices stack (gateway, pipeline, forensics, alpha, legal) — purged; see `docs/GRAVEYARD.md`
- Next.js marketplace frontend; Chrome extension
- B2B webhook ingestion; financial engine (tax classification, FX, SDI)
- MeiliSearch as a product surface (an optional mirror bridge exists,
  `scrapers/discovery/meili_bridge.py`; container currently stopped)

Everything below documents the **dormant Go scaffold as designed**, kept as design
history for that scaffold.

---

## 1. System overview (dormant Go scaffold)

The dormant Go engine is a three-stage pipeline: **Discover** dealers → **Extract** their listings → **Validate** listing quality.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          CARDEX Pipeline                                │
│                                                                         │
│  Discovery Service        Extraction Service       Quality Service      │
│  ─────────────────        ─────────────────        ───────────────      │
│  15 families:             13 strategies:           20 validators:       │
│  A. Business registries   E01 JSON-LD              V01 VIN checksum     │
│  B. OSM Overpass          E02 CMS REST             V02 NHTSA recall     │
│  C. Wayback/crt.sh        E03 Sitemap XML          V03 DAT lookup       │
│  D. CMS fingerprint       E04 RSS/Atom             V04 NLP make/model   │
│  E. DMS infrastructure    E05 DMS API              V05 Image quality    │
│  F. Marketplace listings  E06 Microdata/RDFa       V06 Photo count      │
│  G. Trade associations    E07 Playwright XHR        V07 Price range      │
│  H. OEM dealer locators   E08 PDF extraction       V08 Mileage range    │
│  I. Inspection networks   E09 Excel/CSV            V09 Year range       │
│  J. Sub-jurisdictions     E10 Email/EDI            V10 URL liveness     │
│  K. SearXNG meta-search   E11 Dead-letter queue    V11 NLG quality      │
│  L. Social profiles       E12 gRPC edge push       V12 Cross-source dedup│
│  M. VAT/UID registries    E13 VLM vision (opt-in)  V13 Completeness     │
│  N. Infra intel                                    V14 Freshness        │
│  O. Press archives                                 V15 Dealer trust     │
│                                                    V16 Photo phash dedup│
│                                                    V17 Sold status      │
│                                                    V18 Language check   │
│                                                    V19 Currency/price   │
│                                                    V20 Composite score  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                         SQLite (discovery.db, WAL)
                                    │
                    /srv/cardex/db/discovery.db
```

---

## 2. Deployment topology (designed target — not deployed)

> **Reality check (2026-06-12):** this VPS topology was designed but never became
> the production path; `deploy/` is not currently deployed. The live system runs on
> the operator host (see §0).

Single Hetzner CX42 (4 vCPU AMD EPYC, 16 GB RAM, 240 GB NVMe). ~€22/month total.

```
Internet (HTTPS)
     │
     ▼
 Caddy :443/:80
 TLS 1.3, auto Let's Encrypt, HSTS
     │
     ├─→ /api/discovery/*  → discovery-service  :8080 (systemd)
     ├─→ /api/extraction/* → extraction-service :8081 (systemd)
     ├─→ /api/quality/*    → quality-service    :8082 (systemd)
     └─→ /health           → 200 OK

Observability (loopback, SSH tunnel for external access):
  Prometheus  :9090 ← scrapes :9101 (discovery), :9102 (extraction), :9103 (quality)
  Grafana     :3001 ← reads from Prometheus
  Alertmanager:9093 ← receives alerts, routes to operator

Storage:
  /srv/cardex/db/discovery.db   — SQLite WAL, shared across all 3 services
  /srv/cardex/backups/          — age-encrypted .tar.gz files (30-day retention)

Backup:
  Daily 03:00 UTC → WAL checkpoint → age-encrypt → rsync → Hetzner Storage Box

Innovation services (experimental, CPU-only, loopback):
  GNN inference     :8501  POST /predict-links  (GraphSAGE dealer link prediction)
  RAG search        :8502  POST /search         (nomic-embed-text + FAISS + Llama 3.2)
  Chronos forecast  :8503  POST /forecast       (Chronos-2 / AutoETS price forecasting)

Edge push:
  gRPC edge server  :50051  PushListings RPC (TLS 1.3, API key auth)
                            Dealer CLI: extraction/cmd/cardex-dealer/
                            Desktop client: clients/edge-tauri/ (Rust+Tauri)
```

---

## 3. Service interfaces

### Discovery service

- **Port:** :8080 (HTTP API) + :9101 (Prometheus metrics)
- **Input:** Discovery jobs queued in SQLite
- **Output:** Dealer URLs written to `dealer` table in discovery.db
- **Config:** `DISCOVERY_*` env vars; all 15 families can be individually disabled via `DISCOVERY_SKIP_FAMILIA_*=true`

### Extraction service

- **Port:** :8081 (HTTP API) + :9102 (Prometheus metrics)
- **Input:** Dealer URLs from discovery.db
- **Output:** Raw vehicle listings written to `vehicle` table in discovery.db
- **Config:** `EXTRACTION_*` env vars; strategies can be disabled via `EXTRACTION_SKIP_E*=true`

### Quality service

- **Port:** :8082 (HTTP API) + :9103 (Prometheus metrics)
- **Input:** Vehicle listings from discovery.db
- **Output:** Validation results written to `validation_result` table; composite V20 decision (PUBLISH / MANUAL_REVIEW / REJECT)
- **Config:** `QUALITY_*` env vars; validators can be disabled via `QUALITY_SKIP_V*=true`

---

## 4. Data model (scaffold SQLite — NOT the live store)

> **Reality check (2026-06-12):** `discovery.db` is the dormant Go scaffold's own
> SQLite. **PostgreSQL 16 is the live store** (`migrations/0001`–`0007`); the only
> SQLite in the live path is `scrapers/engine.db` (engine state, by design).

Core tables in `discovery.db`:

```sql
-- Discovered dealer entities
dealer (
  id TEXT PRIMARY KEY,           -- ULID
  url TEXT NOT NULL UNIQUE,
  country TEXT NOT NULL,         -- ISO 3166-1 alpha-2
  name TEXT,
  source_family TEXT,            -- which discovery family found this
  created_at DATETIME,
  last_crawled_at DATETIME
)

-- Extracted vehicle listings
vehicle (
  id TEXT PRIMARY KEY,           -- ULID
  dealer_id TEXT REFERENCES dealer(id),
  vin TEXT,
  make TEXT, model TEXT, variant TEXT,
  year INTEGER,
  mileage_km INTEGER,
  price_eur REAL,
  source_country TEXT,
  source_url TEXT UNIQUE,
  photo_urls TEXT,               -- JSON array
  description TEXT,
  listing_status TEXT,           -- ACTIVE, SOLD, EXPIRED
  created_at DATETIME,
  updated_at DATETIME
)

-- Quality validation results
validation_result (
  id TEXT PRIMARY KEY,
  vehicle_id TEXT REFERENCES vehicle(id),
  validator_id TEXT NOT NULL,    -- V01..V20
  pass INTEGER NOT NULL,         -- 1=pass, 0=fail
  severity TEXT,                 -- INFO, WARNING, CRITICAL
  issue TEXT,
  confidence REAL,
  evidence TEXT,                 -- JSON key-value pairs
  created_at DATETIME
)
```

---

## 5. Quality pipeline decision logic (V20)

V20 (composite scorer) runs LAST, reads all V01–V19 results for a vehicle, and produces a final decision:

```
earned_pts / max_pts ≥ 0.80  AND  critical_count == 0  →  PUBLISH
earned_pts / max_pts ≥ 0.60  OR   critical_count == 1  →  MANUAL_REVIEW
                                   (whichever is worse)
otherwise                                               →  REJECT
```

Validator weights (total: 176 pts): V01=15, V02=12, V03=10, V04=10, V05=10, V06=8, V07=12, V08=10, V09=10, V10=8, V11=8, V12=12, V13=10, V14=8, V15=10, V16=5, V17=8, V18=4, V19=6. (Source: quality/internal/validator/v20_composite/v20.go)

---

## 6. Security model

- All HTTP clients identify as `CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)`.
- `extraction/internal/robots.Checker` verifies robots.txt compliance in HTML-crawling strategies (E01, E03, E04). TTL-cached per host (24 h). Fails open on transient errors.
- Rate limiting: configurable token bucket per domain (default 0.3 req/s).
- Caddy terminates TLS (TLS 1.3 only, HSTS 6 months).
- Secrets: `systemd-creds` encrypted at rest on VPS; `age` for backup encryption.
- CI: Forgejo workflow `illegal-pattern-scan.yml` blocks commits with banned UA strings, stealth patterns, or blacklisted dependencies.

---

## 7. Key technology decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Database | SQLite WAL (modernc.org/sqlite) — *scaffold only; superseded: the live system of record is PostgreSQL 16* | Pure Go, no CGO, distroless compatible; sufficient for MVP scale |
| Reverse proxy | Caddy | Auto TLS, zero certbot maintenance |
| Service management | systemd | Lower overhead than Docker for core services |
| Observability | Docker Compose | Prometheus/Grafana change often; Docker simplifies upgrades |
| Backup encryption | age | Modern, composable, no GPG key management |
| Container images | gcr.io/distroless/static-debian12 | ~15MB per image, minimal attack surface |
| Build | GOWORK=off per module | Avoids workspace conflicts; each module is independently deployable |

---

## 8. What is NOT in this architecture

Moved to **§0 "System reality"** at the top of this document (and corrected there:
the original list here claimed PostgreSQL 16 and Redis Streams were not implemented —
both are **LIVE** today via the Python fleet, not via this Go architecture). For the
remaining genuinely absent components, see §0. Historical roadmap pointers:
`planning/07_ROADMAP/` and `planning/02_MARKET_INTELLIGENCE/06_INNOVATION_ROADMAP.md`
(superseded vision-era planning).
