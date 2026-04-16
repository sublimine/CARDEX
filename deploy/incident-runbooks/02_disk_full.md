# 02 — Disk Full

---

## 1. Locate the culprit

```bash
df -h /srv/cardex /var/log / /tmp
du -sh /var/log/* | sort -rh | head -10
du -sh /srv/cardex/* | sort -rh | head -10
journalctl --disk-usage
```

## 2. Trim journald logs

```bash
journalctl --vacuum-size=200M
journalctl --vacuum-time=14d
# Persist the limit:
sed -i 's/^#SystemMaxUse=.*/SystemMaxUse=200M/' /etc/systemd/journald.conf
systemctl restart systemd-journald
```

## 3. Rotate Caddy access logs

```bash
ls -lh /var/log/caddy/
# Force logrotate now:
logrotate -f /etc/logrotate.d/caddy
# If no logrotate config exists, manually truncate (safe while running):
truncate -s 0 /var/log/caddy/access.log
```

## 4. SQLite WAL checkpoint (reclaims WAL file space)

```bash
systemctl stop cardex-discovery cardex-extraction cardex-quality
sqlite3 /srv/cardex/db/discovery.db "PRAGMA wal_checkpoint(TRUNCATE);"
ls -lh /srv/cardex/db/
systemctl start cardex-discovery cardex-extraction cardex-quality
```

## 5. Emergency cleanup

```bash
# Remove tmp / build artefacts:
find /tmp -mtime +1 -delete 2>/dev/null
find /srv/cardex -name "*.tmp" -mtime +1 -delete

# Remove old Go build cache (if present):
du -sh /root/.cache/go-build/
go clean -cache   # only if Go toolchain installed on server

# Identify largest files anywhere:
find / -xdev -size +100M -printf '%s %p\n' 2>/dev/null | sort -rn | head -20
```

## 6. Resize Hetzner volume via API

Only if none of the above frees enough space.

```bash
# Get your API token from Bitwarden: cardex-hetzner-api-token
export HCLOUD_TOKEN="<token>"
export SERVER_ID="<server-id>"   # from hcloud server list

# Check current disk size first:
hcloud server describe $SERVER_ID | grep -i disk

# Resize root disk (requires server power-off):
hcloud server poweroff $SERVER_ID
hcloud server rebuild $SERVER_ID --image debian-12
# NOTE: rebuild wipes the server — use only for a fresh reprovisioning path.
# Preferred: attach a new Hetzner Volume instead:
hcloud volume create --size 50 --server $SERVER_ID --name cardex-extra
# Then mount and symlink /srv/cardex to the new volume.
```

## 7. Validate

```bash
df -h /srv/cardex /var/log /
systemctl is-active cardex-discovery cardex-extraction cardex-quality
```
