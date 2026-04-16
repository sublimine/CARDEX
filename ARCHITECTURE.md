# CARDEX — Architecture (Phase 2–5 MVP)

> **Note:** This document describes the current implemented architecture (Phases 2–5).
> The original ambitious vision (3-node AX102 cluster, PostgreSQL, ClickHouse, full-stack) is documented in `SPEC.md` and `planning/06_ARCHITECTURE/`. That vision remains the long-term target; this document reflects what is actually deployed.

---

## 1. System overview

CARDEX is a three-stage pipeline: **Discover** dealers → **Extract** their listings → **Validate** listing quality.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          CARDEX Pipeline                                │
│                                                                         │
│  Discovery Service        Extraction Service       Quality Service      │
│  ─────────────────        ─────────────────        ───────────────      │
│  15 families:             12 strategies:           20 validators:       │
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
│  K. SearXNG meta-search   E11 Manual queue         V11 NLG quality      │
│  L. Social profiles       E12 Edge stub            V12 Cross-source dedup│
│  M. VAT/UID registries                             V13 Completeness     │
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

## 2. Deployment topology (production)

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

## 4. Data model (SQLite)

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

Validator weights (total: 176 pts): V01=20, V12=15, V17=15, V05=15, V07=10, V08=10, V06=10, V02=10, V14=10, V15=12, V03=5, V04=5, V13=8, V09=8, V10=8, V11=8, V16=5, V18=5, V19=8, V20=0.

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
| Database | SQLite WAL (modernc.org/sqlite) | Pure Go, no CGO, distroless compatible; sufficient for MVP scale |
| Reverse proxy | Caddy | Auto TLS, zero certbot maintenance |
| Service management | systemd | Lower overhead than Docker for core services |
| Observability | Docker Compose | Prometheus/Grafana change often; Docker simplifies upgrades |
| Backup encryption | age | Modern, composable, no GPG key management |
| Container images | gcr.io/distroless/static-debian12 | ~15MB per image, minimal attack surface |
| Build | GOWORK=off per module | Avoids workspace conflicts; each module is independently deployable |

---

## 8. What is NOT in this architecture (yet)

The following components from the full CARDEX vision (`SPEC.md`) are not currently implemented:

- PostgreSQL 16 + ClickHouse OLAP
- Redis streams / Bloom filters
- MeiliSearch faceted search
- Full microservices stack (gateway, pipeline, forensics, alpha, legal)
- Next.js marketplace frontend
- Chrome extension
- B2B webhook ingestion
- Financial engine (tax classification, FX, SDI)
- Multi-node cluster (3× AX102)

These are future phases. See `planning/07_ROADMAP/` and `planning/02_MARKET_INTELLIGENCE/06_INNOVATION_ROADMAP.md`.
