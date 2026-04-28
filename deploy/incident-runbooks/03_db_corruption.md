# 03 — DB Corruption

DB path: `/srv/cardex/db/discovery.db`
Backup location: Hetzner Storage Box, age-encrypted.

---

## 1. Confirm corruption

```bash
sqlite3 /srv/cardex/db/discovery.db "PRAGMA integrity_check;" 2>&1 | head -20
# Healthy output: "ok"
# Corrupt output: "*** in database ... row ... missing from index ..." etc.
```

## 2. Stop all services

```bash
systemctl stop cardex-discovery cardex-extraction cardex-quality
# Confirm they are stopped:
systemctl is-active cardex-discovery cardex-extraction cardex-quality
```

## 3. Copy corrupt DB aside

```bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
cp /srv/cardex/db/discovery.db /srv/cardex/db/discovery.db.corrupt_${TIMESTAMP}
cp /srv/cardex/db/discovery.db-wal /srv/cardex/db/discovery.db-wal.corrupt_${TIMESTAMP} 2>/dev/null || true
cp /srv/cardex/db/discovery.db-shm /srv/cardex/db/discovery.db-shm.corrupt_${TIMESTAMP} 2>/dev/null || true
ls -lh /srv/cardex/db/
```

## 4. Identify the latest good backup

```bash
# Storage Box is mounted (or accessible via SFTP):
ls -lt /mnt/storagebox/cardex/backups/ | head -10
# Files are named: discovery_YYYYMMDD_HHMMSS.db.age
LATEST=$(ls -t /mnt/storagebox/cardex/backups/*.db.age | head -1)
echo "Restoring from: $LATEST"
```

## 5. Restore from age-encrypted backup

```bash
# Age key is in: /etc/cardex/backup.key  (chmod 400, owned by root)
age --decrypt -i /etc/cardex/backup.key -o /srv/cardex/db/discovery_restored.db "$LATEST"

# Verify the restored file:
sqlite3 /srv/cardex/db/discovery_restored.db "PRAGMA integrity_check;"
# Must output: ok
```

## 6. Replace the live DB

```bash
mv /srv/cardex/db/discovery_restored.db /srv/cardex/db/discovery.db
rm -f /srv/cardex/db/discovery.db-wal /srv/cardex/db/discovery.db-shm
chown cardex:cardex /srv/cardex/db/discovery.db
chmod 640 /srv/cardex/db/discovery.db
```

## 7. Restart services and validate

```bash
systemctl start cardex-discovery cardex-extraction cardex-quality
sleep 5
systemctl is-active cardex-discovery cardex-extraction cardex-quality
curl -sf http://localhost:8081/health && echo "discovery OK"
sqlite3 /srv/cardex/db/discovery.db "SELECT count(*) FROM companies;" 2>&1
```

## 8. Determine data loss window

```bash
# Check backup timestamp vs now:
stat "$LATEST"
# Any records after that timestamp are lost and must be re-crawled.
# Trigger a manual discovery run if needed:
systemctl start cardex-discovery
journalctl -u cardex-discovery -f
```
