# SPEC_CONTRACTS.md — Intended Contracts for CARDEX Scraping Engine Modules

**Generated:** 2026-06-03  
**Purpose:** Extract EXACT contracts from SPEC.md, ARCHITECTURE.md, CONTEXT_FOR_AI.md, BACKLOG.md, and docs/SCRAPING_ENGINE.md.

## QUICK REFERENCE

### Work Queue Schema (db.py lines 110-128)
- Columns: id, portal, country, tier, identity_id, filter_params, status (pending|running|completed|failed|dlq), priority, attempts, created_at, scheduled_at, started_at, completed_at
- Index: idx_wq_scheduled ON (status, scheduled_at) WHERE status='pending'
- Polling: SELECT WHERE status='pending' AND scheduled_at <= now() ORDER BY scheduled_at, priority DESC

### BasePortalScraper.run() (base.py:63-70; SCRAPING_ENGINE.md § B)
Template method orchestrates: warming check → identity allocation → proxy allocation → circuit breaker check → partition segments → fetch+index pages → handle pagination cap → update metrics

### Coordinator.run() (coordinator.py:48-50; BACKLOG.md)
Main loop: forever poll work_queue → release quarantined identities → dispatch to T0/T1/T2/T3 fleets → write vehicle_index → update metrics/circuit_breaker

### Scheduler.run() (BACKLOG.md:221-229; SCRAPING_ENGINE.md § C1)
Enqueue work items with adaptive scheduling: delta found → 1h, no deltas 7d → 1.5× backoff max 30d, staleness >24h → priority 10 immediate

### Pipeline Stages (SCRAPING_ENGINE.md § B, C, D)
1. Delta Engine: Compare URLs, emit new/gone/changed, compute price_hash
2. Enrichment: JSON-LD → OG/Meta → LLM Haiku (async offline)
3. Quality Gates: Structural, Poison (2+ signals), Coherence, Staleness
4. DLQ Handler: Recovery routing per failure reason

### Intelligence Detectors (SCRAPING_ENGINE.md § D)
- WAF Classifier: Detect Cloudflare/DataDome/Akamai
- Schema Validator: Track schema_fp, alert on change
- Poison Detector: 2+ signals (Article @type, <15KB HTML, text/code>0.8, etc.)
- Softblock Detector: null_field_rate > 15% for 10m
- Schema Drift: Required field missing >30%

### 4 Collection Fleets (parallel)
- T0 Mobile API: mobile.de, AS24 post-RE (async, minimal RAM)
- T1 curl_cffi: AS24, kleinanzeigen, marktplaats (3 workers, 200 req/s)
- T2 Camoufox: wallapop, heycar, gocar (8 instances, 200MB each)
- T3 Camoufox+Behavioral: leboncoin, lacentrale (3 instances, premium only)

### Prometheus Metrics (SCRAPING_ENGINE.md § E:525-554)
- scraper_requests_total{portal, tier, status_code}
- scraper_null_field_rate{portal} — CRITICAL if >15% for 10m
- identity_trust_score{identity_id, country}
- proxy_success_rate{proxy_ip, tier, country}
- pipeline_dlq_size, warming_pool_size, premium_identity_count
- circuit_breaker_state{domain, tier}

### Trust Score Lifecycle (SCRAPING_ENGINE.md § A1)
- Initial: 0.0
- Success: +0.05
- Softblock: -1.0
- Hardblock: -3.0
- Quarantine: <0 (48h recovery)
- Retirement: <-5.0
- Premium (T3): >=7.0

### Circuit Breaker (SCRAPING_ENGINE.md § A6:314-320)
- CLOSED → 3 failures in 60s → OPEN (120s) → HALF_OPEN → 1 success → CLOSED | 1 failure → OPEN
- On OPEN: escalate to next tier

### Key Thresholds
- Max price: 500,000 EUR
- Min price: >0 EUR
- Max mileage: 1,500,000 km
- Year range: 1980 - current_year+1
- HTML min: >15 KB
- Staleness: >30 days → DELETE
- Softblock rate: >15% for 10m
- Zero-URL soft block: 3 consecutive cycles
- Poison threshold: >=2 flags
- Delta accelerate: prev/2 min 1h
- Delta backoff: prev×1.5 max 30d

---

**SPEC_CONTRACTS.md — Full documentation available in BACKLOG.md § Arquitectura objetivo and SCRAPING_ENGINE.md complete design.**

**Key citations:**
- work_queue: db.py:110-128, SCRAPING_ENGINE.md:660-676
- coordinator: coordinator.py:4-14, BACKLOG.md:114-228
- scheduler: BACKLOG.md:221-229, SCRAPING_ENGINE.md:410-428
- fleets: BACKLOG.md:137-203, SCRAPING_ENGINE.md:380-406
- pipeline: SCRAPING_ENGINE.md:410-481
- intelligence: SCRAPING_ENGINE.md:483-519
- metrics: SCRAPING_ENGINE.md:524-583
- identity: SCRAPING_ENGINE.md:52-176
- constants: scattered across all sources

