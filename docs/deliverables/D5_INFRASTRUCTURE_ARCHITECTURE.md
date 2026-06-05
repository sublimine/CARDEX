# CARDEX — Infrastructure Architecture (As-Deployed)

**Version:** 1.0
**Date:** 2026-06-05
**Classification:** Internal — Technical
**Authority:** This document describes what IS deployed. Not what SPEC.md envisions. Not what the roadmap plans. What is real, right now.

---

## 1. Physical Infrastructure

### 1.1 Compute

| Resource | Specification | Cost | Purpose |
|----------|--------------|------|---------|
| **Hetzner CX42** | 4 vCPU AMD EPYC, 16 GB RAM, 240 GB NVMe | ~€18/month | All CARDEX services: 3 Go services + scraper fleet + observability stack |
| **Hetzner Storage Box** | BX11 (1 TB, SFTP/SCP) | ~€3/month | Encrypted daily backups (age-encrypted SQLite snapshots) |
| **Domain** | cardex.eu | ~€1.25/month (amortized) | Primary domain, TLS certificate via Caddy |
| **Total monthly OPEX** | | **~€22/month** (VPS + storage + domain) | Proxy costs (€50-200/month) are additional, variable |

**Location:** Nürnberg (NBG1), Germany. Selected for low latency to DE/AT/CH target portals and Hetzner's Frankfurt IX peering.

**What does NOT exist:**
- No PostgreSQL server (SQLite is the database)
- No Redis instance (no message queue, no caching layer)
- No ClickHouse instance (no OLAP warehouse)
- No multi-node cluster (no 3× AX102)
- No Kubernetes, no Nomad, no orchestration beyond systemd + Docker Compose
- No CDN, no load balancer, no auto-scaling

### 1.2 Network

```
Internet
    │
    ├── Port 443 (HTTPS) ──→ Caddy (reverse proxy, TLS 1.3)
    │                           ├── /discovery/*  → localhost:9101
    │                           ├── /extraction/* → localhost:9102
    │                           ├── /quality/*    → localhost:9103
    │                           └── /health       → health check endpoint
    │
    ├── Port 80 (HTTP) ───→ Caddy (ACME HTTP-01 challenge only, redirects to 443)
    │
    └── Port 22 (SSH) ────→ OpenSSH (Ed25519 key-only, fail2ban)
    
    All other ports: UFW DENY
    
    Internal (localhost only):
    ├── :9090  Prometheus
    ├── :3001  Grafana
    ├── :9093  Alertmanager
    ├── :9100  Node Exporter (host metrics)
    └── :9101/:9102/:9103  Go services (metrics endpoints)
```

---

## 2. Software Stack

### 2.1 Core Services (Go)

Three independently deployable Go services, each with its own `go.mod`. Built with `GOWORK=off` to prevent workspace interference.

| Service | Module | Port | Systemd unit | Purpose |
|---------|--------|------|-------------|---------|
| **Discovery** | `github.com/cardex/discovery` | 9101 | `cardex-discovery.service` | Finds dealer URLs via 15 intelligence families (A–O) |
| **Extraction** | `github.com/cardex/extraction` | 9102 | `cardex-extraction.service` | Extracts vehicle listings using 13 strategies (E01–E13) |
| **Quality** | `github.com/cardex/quality` | 9103 | `cardex-quality.service` | Validates and scores listings using 20 validators (V01–V20) |

**Runtime:** Go 1.25, compiled to native Linux binaries, deployed as systemd services (not containerized). Systemd provides restart-on-failure, journald logging, and resource limits.

**Configuration:** Environment variables per service (defined in systemd unit files). No config files, no config server, no Consul/etcd.

**Build:**
```bash
cd discovery  && GOWORK=off go build -o /usr/local/bin/cardex-discovery ./cmd/discovery-service/
cd extraction && GOWORK=off go build -o /usr/local/bin/cardex-extraction ./cmd/extraction-service/
cd quality    && GOWORK=off go build -o /usr/local/bin/cardex-quality ./cmd/quality-service/
```

### 2.2 Scraper Fleet (Python)

Parallel inventory acquisition layer. NOT wired to the Go pipeline — writes directly to `vehicle_index` SQLite database.

| Component | Version | Role |
|-----------|---------|------|
| Python | 3.11+ | Runtime |
| curl_cffi | ≥0.15.1 | TLS-impersonating HTTP client (Chrome 136+) |
| Camoufox | Latest | Anti-detect Firefox fork for JS-heavy portals |
| CapSolver SDK | Latest | CAPTCHA solving fallback |

**Portal coverage:** 84 portal directories in `scrapers/portals/`, each with a scraper class inheriting from `base.py`. Organized by country subdirectories (de/, fr/, es/, nl/, be/, ch/) and portal-specific directories.

**Execution:** Invoked manually or via cron. No orchestration daemon. No Celery, no RQ, no task queue.

### 2.3 Observability Stack (Docker Compose)

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| Prometheus | prom/prometheus | 9090 | Metrics collection, alerting rules evaluation |
| Grafana | grafana/grafana | 3001 | Dashboards (accessed via SSH tunnel) |
| Alertmanager | prom/alertmanager | 9093 | Alert routing (email to operator) |
| Node Exporter | prom/node-exporter | 9100 | Host-level metrics (CPU, RAM, disk, network) |

**Docker Compose files:**
- `deploy/docker/docker-compose.yml` — base configuration
- `deploy/docker/docker-compose.prod.yml` — production overlays (retention, resource limits)

**Prometheus retention:** 30 days (`--storage.tsdb.retention.time=30d`)
**Scrape interval:** 30s global, per-job overrides where needed

### 2.4 Reverse Proxy (Caddy)

Caddy v2.9+ installed via apt, managed by systemd (not Docker).

- **TLS:** Automatic Let's Encrypt certificates. TLS 1.3 enforced. HSTS enabled.
- **Routes:** Proxies to 3 Go services on localhost ports.
- **Configuration:** `/etc/caddy/Caddyfile`
- **Admin API:** Port 2019 (localhost only), exposes `/metrics` for Prometheus.

---

## 3. Data Storage

### 3.1 SQLite (Primary Database)

**Location:** `/srv/cardex/db/`
**Mode:** WAL (Write-Ahead Logging) — enables concurrent reads during writes
**Engine:** SQLite 3.x via Go `modernc.org/sqlite` (pure Go, no CGO)

**Key tables (in vehicle_index):**
- `vehicles` — normalized vehicle listings (the core data asset)
- `dealers` — dealer profiles (name, URL, country, trust score)
- `discovery_urls` — URLs discovered by the 15 intelligence families
- `scrape_state` — per-portal scraping state (last run, next scheduled, tier)

**Why SQLite:**
- Single-server deployment eliminates the need for client-server database
- WAL mode provides the concurrency needed (3 Go services + scraper fleet, but write volume is modest)
- Backup is trivial: `PRAGMA wal_checkpoint(FULL)` + copy the file
- No DBA needed. No connection pooling. No replication config.
- At 1.55M records, SQLite performs well within its design envelope

**Limitations accepted:**
- No concurrent writes from multiple processes (WAL allows one writer at a time)
- No full-text search (MeiliSearch not deployed — would require separate service)
- No horizontal scaling (single file on single disk)

### 3.2 Backup Strategy

**Tool:** `deploy/scripts/backup.sh`
**Schedule:** Daily via systemd timer (`cardex-backup.timer`)
**Process:**
1. `PRAGMA wal_checkpoint(FULL)` — flush WAL to main database file
2. Copy database file to `/srv/cardex/backups/`
3. Encrypt with `age` using backup public key (private key in KeePassXC, never on server)
4. Upload to Hetzner Storage Box via SCP (Ed25519 key auth)
5. Rotate local backups: keep last 7 days locally, 90 days on Storage Box

**Restore procedure:**
1. Download encrypted backup from Storage Box
2. Decrypt with age private key (from KeePassXC on local machine)
3. `PRAGMA integrity_check` on restored file
4. Replace production database, restart services

**Monitoring:** Alertmanager rule `BackupStale` fires if last backup is >25h old.

---

## 4. Alerting Rules (10 Rules)

All rules defined in `deploy/observability/alertmanager/rules.yml`:

| Alert | Condition | Severity | Response |
|-------|-----------|----------|----------|
| `ServiceDown` | Any cardex_* service unreachable for >5m | Critical | Check systemctl status, restart if needed |
| `ServiceRestartingFrequently` | >3 restarts in 1h for any service | Warning | Possible crash loop — check journald logs |
| `DiscoveryErrorRateHigh` | Discovery error rate >10% for 15m | Warning | Check which families are failing |
| `ExtractionErrorRateHigh` | Extraction error rate >10% for 15m | Warning | Check E-strategy logs for portal changes |
| `QualityValidationCriticalSpike` | >20% CRITICAL validation failures for 30m | Warning | Possible data source issue or schema change |
| `ExtractionQueueUnbounded` | Queue depth >10,000 for 30m | Warning | Extraction falling behind — increase workers |
| `QualityQueueUnbounded` | Quality backlog >5,000 for 30m | Warning | Increase QUALITY_WORKERS or QUALITY_BATCH_SIZE |
| `DiskSpaceLow` | /srv disk <20% | Warning | Check DB size, run cleanup |
| `DiskSpaceCritical` | /srv disk <10% | Critical | Immediate action — risk of service failure |
| `SQLiteWALSizeHigh` | WAL file >500 MB for 10m | Warning | Run PRAGMA wal_checkpoint(TRUNCATE) |
| `BackupStale` | Last backup >25h old | Warning | Check backup timer and Storage Box connectivity |

**Alert routing:** Alertmanager → email to operator. No PagerDuty, no Slack integration (single operator, email is sufficient).

---

## 5. Security Posture

### 5.1 Access Control

| Layer | Control |
|-------|---------|
| SSH | Ed25519 key-only. No password auth. No root login. AllowUsers: cardex only. LoginGraceTime: 30s. MaxAuthTries: 3. |
| Firewall | UFW: allow 22, 80, 443 only. Default deny incoming. |
| Brute force | fail2ban active on SSH |
| Secrets | systemd-creds encrypted storage. KeePassXC for offline secrets. No secrets in git (.gitignore enforced). |
| Monitoring access | Grafana/Prometheus on localhost only — accessed via SSH tunnel |

### 5.2 Kernel Hardening

Applied via `/etc/sysctl.d/99-cardex.conf`:
- TCP syncookies enabled
- ICMP broadcast ignore
- Address space randomization (ASLR) enabled
- Kernel pointer restriction
- dmesg restriction
- File descriptor limit: 200,000

### 5.3 Software Updates

- `unattended-upgrades` installed for automatic security patches
- Go services rebuilt from source on deploy (no pre-built binary distribution)
- Docker images pulled from official repositories (prom/*, grafana/*)

---

## 6. Innovation Services (Experimental — NOT Production)

Three Python services exist in `innovation/` but are NOT deployed on the CX42:

| Service | Port | Purpose | Status |
|---------|------|---------|--------|
| GNN Dealer Inference | 8501 | GraphSAGE link prediction for dealer networks | Experimental, CPU-only |
| RAG Search | 8502 | Local RAG with nomic-embed-text + FAISS | Experimental, CPU-only |
| Chronos Forecasting | 8503 | Price forecasting per (country, make, model, year) | Experimental, CPU-only |

**RAM requirement:** 200-800 MB each. The CX42 (16 GB) could run them alongside the core stack, but they have not been validated for production use.

**Dependency:** Require ollama for some features (E13/VLM extraction, RAG reranking). ollama is NOT installed on the CX42.

---

## 7. Deployment Process

### 7.1 Standard Deploy

```bash
./deploy/scripts/deploy.sh cardex@cardex.eu production
```

The script is idempotent with automatic rollback:
1. Git pull on VPS
2. Rebuild Go binaries with GOWORK=off
3. Restart systemd units
4. Health check (curl /health)
5. If health check fails → rollback to previous git commit → restart

### 7.2 Rollback (Manual)

```bash
ssh cardex@cardex.eu
cd /opt/cardex
git log --oneline -5           # find previous commit
git checkout <hash>
cd discovery && GOWORK=off go build -o /usr/local/bin/cardex-discovery ./cmd/discovery-service/
sudo systemctl restart cardex-discovery
# repeat for extraction, quality
```

### 7.3 What Deployment Does NOT Include

- No CI/CD pipeline (no GitHub Actions, no Jenkins). Deploy is manual via SSH.
- No blue-green deployment (single instance).
- No canary releases (no traffic splitting).
- No containerized service deployment (Go services are bare-metal systemd).
- No database migration framework (SQLite schema changes are manual).

---

## 8. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Hetzner CX42 (cardex-prod)                    │
│                    4 vCPU / 16 GB / 240 GB NVMe                  │
│                    Debian 12 / NBG1                               │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  Discovery    │  │  Extraction   │  │  Quality      │          │
│  │  (Go, :9101)  │  │  (Go, :9102)  │  │  (Go, :9103)  │          │
│  │  systemd      │  │  systemd      │  │  systemd      │          │
│  │  15 families  │  │  13 strategies│  │  20 validators │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘           │
│         │                  │                  │                    │
│         └──────────────────┼──────────────────┘                    │
│                            │                                       │
│                    ┌───────▼────────┐                              │
│                    │   SQLite WAL    │                              │
│                    │ /srv/cardex/db/ │                              │
│                    └───────┬────────┘                              │
│                            │                                       │
│  ┌─────────────────────────┼─────────────────────────────┐        │
│  │  Python Scraper Fleet   │  (writes directly to SQLite) │        │
│  │  84 portals / 6 countries                              │        │
│  │  curl_cffi + Camoufox + Decodo/Oxylabs proxies         │        │
│  └────────────────────────────────────────────────────────┘        │
│                                                                    │
│  ┌─────────────────────────────────────────────────────┐          │
│  │  Observability (Docker Compose)                      │          │
│  │  Prometheus :9090 │ Grafana :3001 │ Alertmanager :9093│         │
│  │  Node Exporter :9100                                  │          │
│  └─────────────────────────────────────────────────────┘          │
│                                                                    │
│  ┌────────────────────┐                                           │
│  │  Caddy (:443/:80)   │ ← TLS 1.3, HSTS, ACME auto-cert        │
│  │  Reverse proxy       │                                          │
│  └────────────────────┘                                           │
│                                                                    │
│  UFW: 22 + 80 + 443 only │ fail2ban │ Ed25519 SSH                 │
└─────────────────────────────────────────────────────────────────┘
         │
         │ Daily encrypted backup (age + SCP)
         ▼
┌────────────────────┐
│ Hetzner Storage Box │
│ BX11 (1 TB)         │
│ 90-day retention     │
└────────────────────┘
```

---

## 9. Scaling Path (When Needed)

The current architecture handles 1.55M listings on a single CX42. When (if) scaling becomes necessary:

| Trigger | Action | Cost delta |
|---------|--------|------------|
| SQLite write contention under load | Migrate to PostgreSQL on same VPS | ~€0 (software change) |
| CPU saturation from concurrent scrapers | Upgrade CX42 → CX52 (8 vCPU, 32 GB) | +€18/month |
| Need for full-text search | Deploy MeiliSearch as Docker service | +0 (RAM cost only, fits in 32 GB) |
| Need OLAP analytics at scale | Add ClickHouse Docker service | +0 (fits in 32 GB) or separate VPS |
| Multi-region scraping (reduce latency) | Add Netcup RS 1000 G12 in Vienna | +€8.74/month |

**Principle:** Scale vertically first (bigger VPS), then horizontally (second VPS). Do not add architectural complexity until a single machine is genuinely saturated.

---

*This document reflects the deployed state of CARDEX infrastructure as of 2026-06-05. It was written against `CONTEXT_FOR_AI.md` (ground truth), `deploy/` (deployment artifacts), and `deploy/observability/` (monitoring configuration). Any reference to PostgreSQL, Redis, ClickHouse, MeiliSearch, multi-node clusters, or Kubernetes in other documents describes future state, not current reality.*
