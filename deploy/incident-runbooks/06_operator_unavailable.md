# 06 — Operator Unavailable

Applies when: primary operator **Salman** is unreachable for > 4 h during an active incident.

---

## 1. Confirm unreachable (before escalating)

- Try: Signal, WhatsApp, email to salmankarrouch777@gmail.com
- Wait 15 min between each attempt. After 4 h total with no response → proceed.

## 2. Grant emergency SSH access to backup operator

On the server (via Hetzner web console if SSH is the problem):

```bash
# Add backup operator's public key:
echo "ssh-ed25519 AAAA... backup-operator@host" >> /root/.ssh/authorized_keys
# Verify:
cat /root/.ssh/authorized_keys
```

The backup operator public key should be stored in:
`/srv/cardex/ops/emergency-operator.pub` — add it there during normal ops, before an incident.

```bash
cat /srv/cardex/ops/emergency-operator.pub >> /root/.ssh/authorized_keys
```

Remove the key once Salman is back: edit `/root/.ssh/authorized_keys` and delete the line.

## 3. Safe auto-pause (crawler stops, data is safe)

These services can be stopped safely — no data loss, crawler will resume where it left off:

```bash
systemctl stop cardex-discovery    # stops crawling; DB remains consistent
systemctl stop cardex-extraction   # stops enrichment pipeline
```

This service should remain running (serves read queries, Grafana queries):
```bash
# cardex-quality: keep running unless it is the source of the problem
systemctl is-active cardex-quality
```

SQLite WAL will checkpoint cleanly on service stop.

## 4. Read Grafana via SSH tunnel (no firewall change needed)

From the backup operator's local machine:

```bash
ssh -L 3000:localhost:3000 root@<server-ip>
# Then open: http://localhost:3000 in local browser
# Grafana credentials in Bitwarden: "cardex-grafana-admin"
```

For Prometheus directly:
```bash
ssh -L 9090:localhost:9090 root@<server-ip>
# Then open: http://localhost:9090
```

## 5. What is safe to leave running vs must stop

| Component | Leave running? | Notes |
|---|---|---|
| `cardex-quality` | Yes | Read-only queries, no writes |
| `caddy` | Yes | Proxy only, no state |
| `grafana-server` | Yes | Monitoring, read-only |
| `prometheus` | Yes | Metrics scraping, safe |
| `cardex-discovery` | Stop if P1 | Stops new crawl, DB stable |
| `cardex-extraction` | Stop if P1 | Stops enrichment, no data loss |
| Backup cron | Leave enabled | Daily backup still runs |

## 6. Handoff checklist when Salman returns

- [ ] Review `journalctl -u cardex-discovery --since "4 hours ago"`
- [ ] Confirm `PRAGMA integrity_check` on DB is clean
- [ ] Remove emergency operator SSH key from `authorized_keys`
- [ ] Restart any paused services: `systemctl start cardex-discovery cardex-extraction`
- [ ] Check healthchecks.io dashboard for missed pings during outage
