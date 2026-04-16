# 01 — Service Down

Applies to: `cardex-discovery`, `cardex-extraction`, `cardex-quality`

---

## 1. Detect

```bash
systemctl status cardex-discovery cardex-extraction cardex-quality
journalctl -u cardex-discovery -n 50 --no-pager
journalctl -u cardex-extraction -n 50 --no-pager
journalctl -u cardex-quality -n 50 --no-pager
```

Note the exit code and last log lines before proceeding.

## 2. Quick restart

```bash
systemctl restart cardex-discovery   # replace with failing service
sleep 5
systemctl is-active cardex-discovery
```

If active → validate (step 6). If still failing → continue.

## 3. Diagnose restart loop

Run these three checks in order:

**Disk full?**
```bash
df -h /srv/cardex /var/log /
```
If any partition ≥ 95 % → **go to [02_disk_full.md](02_disk_full.md)**.

**OOM kill?**
```bash
dmesg | grep -i "oom\|killed process" | tail -20
journalctl -k | grep -i oom | tail -20
```
If found → increase swap or reduce service memory limits in the unit file.

**Port conflict?**
```bash
ss -tlnp | grep -E '808[123]'
```
If port is held by another process: `kill <pid>` then restart.

## 4. DB error in logs?

If journal shows `database disk image is malformed` or `SQLITE_CORRUPT`:
**Go to [03_db_corruption.md](03_db_corruption.md).**

## 5. Add temporary swap if OOM

```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile
mkswap /swapfile && swapon /swapfile
# Add to /etc/fstab for persistence: /swapfile none swap sw 0 0
```

## 6. Validate after restart

```bash
curl -sf http://localhost:8081/health && echo "discovery OK"
curl -sf http://localhost:8082/health && echo "extraction OK"
curl -sf http://localhost:8083/health && echo "quality OK"
curl -sf http://localhost:9090/metrics | grep cardex_ | head -10
```

Check Grafana: `http://localhost:3000` (via SSH tunnel if remote).

## 7. Escalation — Hetzner console

If SSH is unreachable:
1. Log in to https://console.hetzner.cloud
2. Select server → **Console** tab → browser-based terminal
3. Use root credentials from Bitwarden vault entry `cardex-prod-root`
4. Run the same commands above

If server is completely frozen: use **Restart** (soft) or **Reset** (hard) from the Actions menu. Hard reset risks WAL corruption — see [03_db_corruption.md](03_db_corruption.md) afterward.
