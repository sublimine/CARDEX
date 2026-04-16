# 04 — Secret Leak

Applies to: SSH keys, INSEE token, KvK token, Pappers token, Grafana password, systemd-creds secrets.

---

## 1. Immediately revoke SSH access

```bash
# On the server — remove the suspected key from authorized_keys:
vi /root/.ssh/authorized_keys          # remove the compromised key line
vi /home/cardex/.ssh/authorized_keys   # if cardex user has SSH

# Verify remaining keys are expected:
cat /root/.ssh/authorized_keys
```

Add new key for legitimate operator before removing old one if sole access method.

## 2. Check for active unauthorized sessions

```bash
who
ss -tnp | grep :22
last -20
grep "Accepted" /var/log/auth.log | tail -30
grep "Invalid user\|Failed password" /var/log/auth.log | tail -20
```

Kill any suspicious session: `pkill -KILL -u <user>` or `kill -9 <pts-pid>`.

## 3. Revoke API tokens

**INSEE (Sirene API)**
- Log in to https://api.insee.fr → Applications → regenerate token
- Update on server: `systemd-creds encrypt --name=insee-token -`

**KvK (Kamer van Koophandel)**
- Log in to https://developers.kvk.nl → My Applications → rotate API key
- Update on server: `systemd-creds encrypt --name=kvk-token -`

**Pappers**
- Log in to https://www.pappers.fr/api → regenerate key
- Update on server: `systemd-creds encrypt --name=pappers-token -`

After each rotation, update the unit file credentials and restart the affected service:
```bash
systemctl daemon-reload
systemctl restart cardex-discovery cardex-extraction cardex-quality
```

## 4. Change Grafana admin password

```bash
grafana-cli admin reset-admin-password '<new-strong-password>'
systemctl restart grafana-server
```

## 5. Rotate systemd-creds secrets (all at once)

```bash
# List current credentials:
ls /etc/credstore/
# Re-encrypt each:
for cred in /etc/credstore/*; do
  name=$(basename "$cred")
  echo "Re-encrypting $name"
  systemd-creds encrypt --name="$name" --force -
done
systemctl daemon-reload
systemctl restart cardex-discovery cardex-extraction cardex-quality
```

## 6. Review auditd for unauthorized access timeline

```bash
ausearch -ts today -k secret-access 2>/dev/null | tail -40
ausearch -ts today --message USER_AUTH | tail -20
# Check which files were accessed:
ausearch -ts yesterday -f /etc/credstore | tail -30
ausearch -ts yesterday -f /srv/cardex | tail -30
```

## 7. Notify and document

- Record incident start time, suspected vector, and which secrets were rotated.
- Store in `/srv/cardex/incidents/YYYYMMDD_secret_leak.md`.
- If API providers require breach notification (e.g., INSEE ToS), follow their process.
