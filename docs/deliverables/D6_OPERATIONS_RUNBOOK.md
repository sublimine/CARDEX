# CARDEX — Operations Runbook

**Version:** 1.0
**Date:** 2026-06-05
**Classification:** Internal — Operations
**Operator:** Single operator + AI assistance
**Infrastructure:** 1x Hetzner CX42 (cardex-prod), Debian 12, systemd + Docker Compose
**Complements:** `deploy/runbook.md` (VPS provisioning), `deploy/incident-runbooks/` (incident response)

---

## 1. Daily Operations Checklist

These are the tasks a single operator should perform or verify daily. Total time: ~15 minutes.

### 1.1 Morning Check (Priority: do this first)

```bash
# SSH into production
ssh -i deploy/secrets/id_ed25519 cardex@cardex.eu

# 1. Are all services running?
sudo systemctl is-active cardex-discovery cardex-extraction cardex-quality caddy
# Expected: active active active active

# 2. Any alerts fired overnight?
# Check email for Alertmanager notifications
# Or query Alertmanager directly:
curl -s http://localhost:9093/api/v2/alerts | python3 -m json.tool | grep '"status"'
# Expected: empty or all resolved

# 3. Backup completed?
ls -lh /srv/cardex/backups/ | head -3
# Expected: today's date on latest backup file

# 4. Disk space
df -h /srv
# Expected: >60% available (240 GB total, DB + WAL + backups should be <80 GB)

# 5. Quick health check
curl -s https://cardex.eu/health
# Expected: "OK"
```

### 1.2 Weekly Check (Friday)

```bash
# 1. SQLite WAL size (should be < 500 MB normally)
ls -lh /srv/cardex/db/*.db-wal
# If > 500 MB: run checkpoint
sqlite3 /srv/cardex/db/discovery.db "PRAGMA wal_checkpoint(TRUNCATE);"

# 2. Service logs — scan for recurring errors
journalctl -u cardex-discovery --since "7 days ago" -p err --no-pager | tail -30
journalctl -u cardex-extraction --since "7 days ago" -p err --no-pager | tail -30
journalctl -u cardex-quality --since "7 days ago" -p err --no-pager | tail -30

# 3. Scraper fleet health — check for portal-level failures
# Review Grafana dashboard (via SSH tunnel)
ssh -L 3001:localhost:3001 cardex@cardex.eu
# Open http://localhost:3001, check "Scraper Fleet" dashboard

# 4. Proxy health
# Review proxy success rates in Grafana or check provider dashboards:
# - Decodo: dashboard.decodo.com
# - Oxylabs: dashboard.oxylabs.io

# 5. Database integrity (monthly, but included here as reminder)
sqlite3 /srv/cardex/db/discovery.db "PRAGMA integrity_check;"
# Expected: "ok"
```

---

## 2. Service Management

### 2.1 Restart a Service

```bash
# Restart discovery (example — same pattern for extraction, quality)
sudo systemctl restart cardex-discovery

# Verify it came back
sudo systemctl status cardex-discovery
# Check logs for startup errors
journalctl -u cardex-discovery -n 50 --no-pager
```

### 2.2 Stop All Services (Maintenance Window)

```bash
# Stop in reverse dependency order
sudo systemctl stop cardex-quality
sudo systemctl stop cardex-extraction
sudo systemctl stop cardex-discovery

# Verify
sudo systemctl is-active cardex-discovery cardex-extraction cardex-quality
# Expected: inactive inactive inactive

# Restart in order
sudo systemctl start cardex-discovery
sudo systemctl start cardex-extraction
sudo systemctl start cardex-quality
```

### 2.3 View Real-Time Logs

```bash
# Follow discovery logs live
journalctl -u cardex-discovery -f

# Follow all CARDEX services
journalctl -u 'cardex-*' -f

# Search for specific error pattern
journalctl -u cardex-extraction --since "1 hour ago" | grep -i "error\|panic\|fatal"
```

### 2.4 Check Service Configuration

```bash
# View environment variables for a service
sudo systemctl show cardex-discovery --property=Environment

# View full unit file
cat /etc/systemd/system/cardex-discovery.service
```

---

## 3. Database Operations

### 3.1 Manual Backup

```bash
# Trigger immediate backup
sudo systemctl start cardex-backup

# Watch it complete
sudo journalctl -u cardex-backup -f

# Verify backup file
ls -lh /srv/cardex/backups/ | head -1
```

### 3.2 Restore from Backup

**When:** Database corruption, accidental data loss, or post-incident recovery.

```bash
# 1. Stop all services
sudo systemctl stop cardex-quality cardex-extraction cardex-discovery

# 2. Download latest backup from Storage Box (if local copy unavailable)
scp -i /home/cardex/.ssh/storage-box \
    u123456@u123456.your-storagebox.de:backups/cardex-2026-06-05.db.age \
    /tmp/restore.db.age

# 3. Decrypt (requires age private key from KeePassXC — transfer to VPS temporarily)
age --decrypt -i /tmp/age-key.txt /tmp/restore.db.age > /tmp/restore.db

# 4. Integrity check BEFORE replacing production
sqlite3 /tmp/restore.db "PRAGMA integrity_check;"
# MUST return "ok" — if not, try previous day's backup

# 5. Replace production database
mv /srv/cardex/db/discovery.db /srv/cardex/db/discovery.db.corrupted
mv /tmp/restore.db /srv/cardex/db/discovery.db
chown cardex:cardex /srv/cardex/db/discovery.db

# 6. Restart services
sudo systemctl start cardex-discovery cardex-extraction cardex-quality

# 7. Verify
curl -s https://cardex.eu/health

# 8. Clean up temporary key
rm -f /tmp/age-key.txt /tmp/restore.db.age
```

### 3.3 WAL Checkpoint (When WAL Grows Large)

```bash
# Check WAL size
ls -lh /srv/cardex/db/*.db-wal

# If > 500 MB (alert SQLiteWALSizeHigh fires at this threshold):
sqlite3 /srv/cardex/db/discovery.db "PRAGMA wal_checkpoint(TRUNCATE);"

# Verify WAL shrunk
ls -lh /srv/cardex/db/*.db-wal
```

### 3.4 Database Size Check

```bash
# Main database file
ls -lh /srv/cardex/db/discovery.db

# Total DB directory
du -sh /srv/cardex/db/

# Record count
sqlite3 /srv/cardex/db/discovery.db "SELECT COUNT(*) FROM vehicles;"
```

---

## 4. Scraper Fleet Operations

### 4.1 Run a Specific Portal Scraper

```bash
# Activate Python virtual environment (if using venv)
cd /opt/cardex/scrapers
source .venv/bin/activate  # if exists

# Run a specific portal
python -m scrapers.portals.mobile_de

# Run with verbose logging
LOGLEVEL=DEBUG python -m scrapers.portals.mobile_de

# Run all portals for a country
python -m scrapers.portals.de
```

### 4.2 Check Scraper Status

```bash
# View last run results (if logged to file)
tail -100 /var/log/cardex/scraper-*.log

# Check for recent scraper errors
grep -r "ERROR\|BLOCKED\|SOFTBLOCK" /var/log/cardex/scraper-*.log | tail -20
```

### 4.3 When a Scraper Fails Repeatedly

Diagnosis flowchart:

```
Scraper for portal X fails
    │
    ├── HTTP 403 on all requests?
    │   └── Portal may have changed WAF → Run diag.py to re-classify tier
    │       └── Tier changed? → Update domain_tier_state, switch to appropriate fleet
    │
    ├── HTTP 429 (rate limited)?
    │   └── Reduce request rate for this portal
    │       └── Check: are multiple identities hitting same portal simultaneously?
    │
    ├── Soft-block detected (200 but degraded content)?
    │   └── All identities affected?
    │       ├── Yes → Portal-wide change. Pause 24h, then retry with fresh identities.
    │       └── No → Specific identities burned. Rotate to healthy identities.
    │
    ├── Parse error (HTML structure changed)?
    │   └── Portal redesigned their listing page
    │       └── Update scraper's CSS selectors / XPath / JSON-LD parser
    │
    └── Connection timeout / DNS failure?
        └── Portal is down (not our problem). Retry in 1h.
```

### 4.4 Proxy Rotation

```bash
# Check current proxy configuration
cat /opt/cardex/scrapers/.env | grep -i proxy

# Rotate Decodo ISP proxies (via Decodo dashboard)
# 1. Log in to dashboard.decodo.com
# 2. Release old IPs
# 3. Provision new IPs in target countries
# 4. Update .env with new proxy URLs
# 5. Restart affected scrapers

# Test proxy connectivity
curl -x socks5://user:pass@proxy-host:port https://httpbin.org/ip
```

---

## 5. Observability Stack Operations

### 5.1 Access Grafana

```bash
# From local machine — create SSH tunnel
ssh -L 3001:localhost:3001 cardex@cardex.eu

# Open browser: http://localhost:3001
# Login: admin / <GRAFANA_ADMIN_PASSWORD from KeePassXC>
```

### 5.2 Access Prometheus

```bash
# SSH tunnel
ssh -L 9090:localhost:9090 cardex@cardex.eu

# Open browser: http://localhost:9090
# Useful queries:
#   up{job=~"cardex_.*"}                          → service health
#   rate(cardex_discovery_scrape_errors_total[1h]) → discovery error rate
#   cardex_extraction_queue_depth                  → extraction backlog
#   node_filesystem_avail_bytes{mountpoint="/srv"} → disk free
```

### 5.3 Restart Observability Stack

```bash
cd /opt/cardex
docker compose -f deploy/docker/docker-compose.yml -f deploy/docker/docker-compose.prod.yml restart

# Or individual services
docker compose -f deploy/docker/docker-compose.yml restart prometheus
docker compose -f deploy/docker/docker-compose.yml restart grafana
```

### 5.4 Check Alert Status

```bash
# Query Alertmanager API
curl -s http://localhost:9093/api/v2/alerts | python3 -m json.tool

# Silence an alert (e.g., during planned maintenance)
# Use Alertmanager UI: SSH tunnel to :9093, then browser
```

---

## 6. Alertmanager Response Guide

When an alert email arrives, follow this response protocol:

| Alert | Immediate action | If that doesn't fix it |
|-------|-----------------|----------------------|
| **ServiceDown** | `sudo systemctl restart cardex-<service>`. Check `journalctl -u cardex-<service> -n 100`. | Check disk space. Check if OOM killed: `dmesg \| grep -i kill`. Rebuild binary. |
| **ServiceRestartingFrequently** | Read logs: `journalctl -u cardex-<service> --since "1 hour ago"`. Look for panic traces. | Pin to previous working commit. Rollback deploy. |
| **DiscoveryErrorRateHigh** | Check which discovery families are failing. Network issue? DNS resolution? | Temporarily disable failing families via env var. |
| **ExtractionErrorRateHigh** | Check which portals are failing. Portal redesign? WAF change? | Disable failing portal scrapers. Update parsers. |
| **QualityValidationCriticalSpike** | Check V07 (price) and V08 (mileage) — likely a data source poisoning or format change. | Review recent extraction output for anomalies. |
| **ExtractionQueueUnbounded** | Increase `EXTRACTION_WORKERS` env var. Restart extraction service. | Check if discovery is producing faster than extraction can consume. Throttle discovery. |
| **QualityQueueUnbounded** | Increase `QUALITY_WORKERS` or `QUALITY_BATCH_SIZE`. Restart quality. | Same as above but for quality pipeline. |
| **DiskSpaceLow** | `du -sh /srv/cardex/*` — find what's growing. Purge old logs. Run WAL checkpoint. | Delete old backups: `find /srv/cardex/backups -mtime +7 -delete` |
| **DiskSpaceCritical** | Emergency: stop extraction (reduces write pressure). Clean immediately. | If can't free space: migrate to larger VPS (CX52). |
| **SQLiteWALSizeHigh** | `sqlite3 /srv/cardex/db/discovery.db "PRAGMA wal_checkpoint(TRUNCATE);"` | Check if a long-running query is holding a read transaction open. |
| **BackupStale** | `sudo systemctl start cardex-backup`. Check timer: `systemctl status cardex-backup.timer`. | Check Storage Box connectivity: `ssh -i /home/cardex/.ssh/storage-box u123456@...`. |

---

## 7. Deployment Procedures

### 7.1 Standard Deploy (Code Update)

```bash
# From local machine
./deploy/scripts/deploy.sh cardex@cardex.eu production

# The script:
# 1. SSH to VPS
# 2. git pull
# 3. Rebuild Go binaries (GOWORK=off)
# 4. Restart systemd units
# 5. Health check
# 6. Auto-rollback if health check fails
```

### 7.2 Python Scraper Update

```bash
ssh cardex@cardex.eu
cd /opt/cardex/scrapers
git pull
pip install -r requirements.txt  # if dependencies changed
# No restart needed — scrapers run on-demand, not as daemons
```

### 7.3 Observability Config Update

```bash
ssh cardex@cardex.eu
cd /opt/cardex

# Update Prometheus rules
vim deploy/observability/alertmanager/rules.yml
docker compose -f deploy/docker/docker-compose.yml restart prometheus

# Update Grafana dashboards
# Import via Grafana UI (SSH tunnel to :3001)
```

---

## 8. Emergency Procedures

### 8.1 VPS Completely Down (Unreachable)

1. Check Hetzner Cloud Console — is the server in "Running" state?
2. If server is running but SSH fails: use Hetzner console (web VNC) to diagnose
3. If server crashed: reboot from Hetzner Cloud Console
4. If data is lost: restore from Storage Box backup (§3.2)
5. If Hetzner is down (extremely rare): provision new VPS at Netcup (backup plan) and restore

### 8.2 Hetzner Account Closure (Worst Case)

If Hetzner terminates the account (e.g., abuse complaint from a scraped portal):

1. Backups are on Hetzner Storage Box — may also be at risk. Download immediately from last known backup.
2. Provision replacement VPS at Netcup RS 1000 G12 (€8.74/month, pre-identified backup provider)
3. Follow `deploy/runbook.md` provisioning steps on new VPS
4. Restore database from backup
5. Update DNS: `A cardex.eu → <new IP>`
6. **Time to recovery: ~2 hours if prepared, ~6 hours if not**

### 8.3 Cease & Desist Received from Portal

See `D1_GDPR_COMPLIANCE.md` §9 for full protocol. Summary:
1. Stop scraping the portal within 24h
2. Add to blocklist
3. Respond within 5 business days
4. Assess data impact
5. DO NOT fight it — not viable at this scale

### 8.4 Mass Proxy Ban

If multiple portals block the proxy fleet simultaneously:

1. Stop all scrapers immediately (`kill` or Ctrl-C)
2. Do NOT retry with same proxies — this burns trust further
3. Wait 24-48h for IP reputation to recover
4. Provision fresh proxies from alternative provider pool
5. Warm new identities through Phase 1+2 before resuming extraction
6. Investigate: was this a correlated ban (same ASN detected) or coincidence?

---

## 9. Maintenance Windows

There is no formal maintenance window — CARDEX runs 24/7 and scraping is asynchronous, so brief downtime (minutes) during deploys is acceptable.

**For planned maintenance (VPS reboot, kernel upgrade):**
1. Announce in `STATUS.md`: maintenance window with expected duration
2. Run manual backup before maintenance
3. Stop services, perform maintenance, restart
4. Verify all services healthy
5. Update `STATUS.md`

---

## 10. Contacts and Credentials

| Resource | Access method | Where are credentials |
|----------|--------------|----------------------|
| Hetzner Cloud Console | https://console.hetzner.cloud/ | KeePassXC |
| Hetzner Storage Box | SCP with Ed25519 key | Key on VPS at /home/cardex/.ssh/storage-box |
| Grafana | http://localhost:3001 (via SSH tunnel) | KeePassXC |
| Decodo dashboard | https://dashboard.decodo.com | KeePassXC |
| Oxylabs dashboard | https://dashboard.oxylabs.io | KeePassXC |
| CapSolver dashboard | https://dashboard.capsolver.com | KeePassXC |
| VPS SSH | ssh cardex@cardex.eu | Ed25519 key in deploy/secrets/ |
| Database backup decryption | age CLI tool | Private key in KeePassXC (NEVER on server) |

---

*This runbook is designed for a single operator managing CARDEX with AI assistance. Every procedure is a concrete command sequence, not a process diagram. It complements the existing `deploy/runbook.md` (provisioning) and `deploy/incident-runbooks/` (incident response) with day-to-day operational procedures.*
