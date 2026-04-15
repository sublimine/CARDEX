# CARDEX — Deploy

Infrastructure-as-code for deploying CARDEX on a single Hetzner CX42 VPS (~€22/month total).

## Quick start

```bash
# 1. Generate secrets (local dev):
./scripts/secrets-generate.sh

# 2. Boot full local stack (Docker Compose):
docker compose -f docker/docker-compose.yml up -d

# 3. Smoke test:
./scripts/test-deploy-local.sh

# 4. Deploy to VPS (see runbook.md for full setup):
./scripts/deploy.sh cardex@cardex.io production
```

## Directory structure

```
deploy/
├── README.md                         # this file
├── runbook.md                        # step-by-step VPS provisioning (start here)
├── docker/
│   ├── Dockerfile.discovery          # Multi-stage Go build → distroless
│   ├── Dockerfile.extraction
│   ├── Dockerfile.quality
│   ├── docker-compose.yml            # Local dev (builds from source)
│   └── docker-compose.prod.yml       # Production overlay (pull from registry)
├── systemd/                          # Bare-metal alternative to Docker
│   ├── cardex-discovery.service
│   ├── cardex-extraction.service
│   ├── cardex-quality.service
│   ├── cardex-backup.service
│   └── cardex-backup.timer           # Triggers backup daily at 03:00 UTC
├── caddy/
│   ├── Caddyfile                     # Reverse proxy + auto Let's Encrypt TLS
│   └── README.md
├── observability/
│   ├── prometheus.yml                # Scrape configs (all 3 services + node)
│   ├── grafana/
│   │   ├── provisioning/             # Auto-provision datasources + dashboards
│   │   ├── dashboard-discovery.json  # Discovery dealer metrics
│   │   ├── dashboard-extraction.json # Extraction strategy metrics
│   │   └── dashboard-quality.json   # Quality V01-V20 + composite score
│   └── alertmanager/
│       └── rules.yml                 # Critical alerts (down, error rate, disk, backup)
├── scripts/
│   ├── deploy.sh                     # Idempotent deploy + rollback
│   ├── backup.sh                     # age-encrypted rsync to Storage Box
│   ├── restore.sh                    # Decrypt + restore + integrity check
│   ├── health-check.sh               # External monitor (cron every 5min)
│   ├── secrets-generate.sh           # age keypair + TLS certs + random secrets
│   ├── test-deploy-local.sh          # Docker Compose smoke test
│   └── test-backup-restore.sh        # End-to-end backup/restore test
├── secrets/
│   ├── README.md                     # What goes here and how to manage it
│   └── .gitignore                    # NEVER commits *.key, .env, *.crt
└── nginx/
    └── nginx.conf                    # Alternative to Caddy (requires certbot)
```

## Architecture

```
Internet → Caddy (TLS 1.3, auto Let's Encrypt) → Discovery / Extraction / Quality
                                                 ↓
                                          /srv/cardex/db/discovery.db (SQLite)

Observability (loopback only):
  Prometheus :9090 → scrapes :9101, :9102, :9103
  Grafana :3001    → access via SSH tunnel
  Alertmanager :9093

Backup: daily 03:00 UTC → age-encrypt → rsync → Hetzner Storage Box
```

## Monthly OPEX

| Resource | Cost |
|----------|------|
| Hetzner CX42 (4 vCPU, 16 GB, 240 GB NVMe, 20 TB) | ~€18 |
| Hetzner Storage Box 1 TB (backups) | ~€3 |
| Domain cardex.io | ~€1.25 |
| TLS certificate (Let's Encrypt) | €0 |
| Monitoring (UptimeRobot free tier) | €0 |
| **Total** | **~€22.25** |

## Key decisions

- **Caddy over nginx**: auto TLS with zero certbot maintenance
- **Systemd over Docker for core services**: simpler, lower overhead, better journald integration
- **Docker only for observability**: Prometheus/Grafana change frequently; Docker simplifies version management
- **modernc.org/sqlite**: pure Go SQLite avoids CGO complexity in distroless containers
- **age over gpg**: modern, simple, composable backup encryption
- **Distroless runtime images**: ~15 MB per service image, minimal attack surface

## Full provisioning

See [runbook.md](./runbook.md) for the complete step-by-step procedure (~45 min for a fresh VPS).
