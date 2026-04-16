# 00 — Incident Triage

**First action every time:** `ssh cardex-prod` → confirm you are on the right host.

## Symptom → Runbook

| Symptom | Runbook |
|---|---|
| Service returns 502 / health endpoint dead | [01 — Service Down](01_service_down.md) |
| `systemctl status` shows `failed` or restart loop | [01 — Service Down](01_service_down.md) |
| `df -h` shows partition ≥ 90 % full | [02 — Disk Full](02_disk_full.md) |
| Journald or Caddy logs mention `no space left on device` | [02 — Disk Full](02_disk_full.md) |
| `PRAGMA integrity_check` returns errors / SQLite journal log errors | [03 — DB Corruption](03_db_corruption.md) |
| Service crashes with `database disk image is malformed` | [03 — DB Corruption](03_db_corruption.md) |
| SSH key or API token suspected leaked / repo exposure | [04 — Secret Leak](04_secret_leak.md) |
| Unusual logins in `/var/log/auth.log` | [04 — Secret Leak](04_secret_leak.md) |
| HTTPS returns certificate error in browser | [05 — TLS Cert Failure](05_tls_cert_failure.md) |
| Caddy logs show ACME / Let's Encrypt failure | [05 — TLS Cert Failure](05_tls_cert_failure.md) |
| Operator Salman unreachable for > 4 h during incident | [06 — Operator Unavailable](06_operator_unavailable.md) |
| healthchecks.io alert email received, no recent backup | [01 — Service Down](01_service_down.md) + [03 — DB Corruption](03_db_corruption.md) |

## Quick health check (run first)

```bash
systemctl is-active cardex-discovery cardex-extraction cardex-quality
curl -sf http://localhost:8081/health && echo "discovery OK"
curl -sf http://localhost:8082/health && echo "extraction OK"
curl -sf http://localhost:8083/health && echo "quality OK"
df -h /srv/cardex
```

## Severity levels

| Level | Definition | Action |
|---|---|---|
| P1 | All services down, data at risk | Wake operator immediately |
| P2 | One service down, degraded | Fix within 1 h |
| P3 | Monitoring gap, no user impact | Fix within 24 h |
