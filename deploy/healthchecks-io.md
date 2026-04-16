# Healthchecks.io — Dead-Man's Switch

Sends an email to salmankarrouch777@gmail.com if no successful discovery cycle or backup runs for 28 h (24 h period + 4 h grace).

---

## 1. Create the check on healthchecks.io

1. Sign up at https://healthchecks.io (free tier: 20 checks)
2. Click **Add Check**
3. Set:
   - **Name:** `cardex-discovery`
   - **Period:** `24 hours`
   - **Grace:** `4 hours`
   - **Tags:** `cardex prod`
4. Copy the ping URL — it looks like: `https://hc-ping.com/<uuid>`
5. In **Notifications**, confirm email `salmankarrouch777@gmail.com` is set

---

## 2. Store the ping URL in the systemd unit

Edit `/etc/systemd/system/cardex-discovery.service` — add to the `[Service]` block:

```ini
Environment="HEALTHCHECKS_URL=https://hc-ping.com/<uuid>"
```

Replace `<uuid>` with the actual UUID from step 1.

Then reload:
```bash
systemctl daemon-reload
```

---

## 3. Ping from the discovery service (Go code)

In the discovery service, after each successful full crawl cycle, add a ping call.
Suggested location: end of the main crawl loop in `internal/discovery/crawler.go` (or equivalent).

```go
if hcURL := os.Getenv("HEALTHCHECKS_URL"); hcURL != "" {
    resp, err := http.Get(hcURL)
    if err == nil {
        resp.Body.Close()
    }
}
```

---

## 4. Ping from backup.sh (alternative / belt-and-suspenders)

At the end of `deploy/scripts/backup.sh`, after a successful backup:

```bash
# Ping healthchecks.io dead-man switch
if [ -n "${HEALTHCHECKS_URL:-}" ]; then
    curl -fsS --retry 3 "$HEALTHCHECKS_URL" > /dev/null
fi
```

The `HEALTHCHECKS_URL` variable must be exported in the environment where the backup cron runs.
Add it to `/etc/systemd/system/cardex-backup.service` or `/etc/cron.d/cardex-backup`:

```ini
# systemd service variant:
Environment="HEALTHCHECKS_URL=https://hc-ping.com/<uuid>"
```

```cron
# cron variant — /etc/cron.d/cardex-backup:
HEALTHCHECKS_URL=https://hc-ping.com/<uuid>
0 3 * * * root /srv/cardex/scripts/backup.sh
```

---

## 5. Signal start and failure (optional, recommended)

Healthchecks.io supports start + failure pings for precise duration tracking:

```bash
# Signal run START (prevents false alarms from slow runs):
curl -fsS --retry 3 "${HEALTHCHECKS_URL}/start" > /dev/null

# ... do the work ...

# Signal SUCCESS:
curl -fsS --retry 3 "${HEALTHCHECKS_URL}" > /dev/null

# Signal FAILURE (call on error exit):
curl -fsS --retry 3 "${HEALTHCHECKS_URL}/fail" > /dev/null
```

---

## 6. Verify the check works

```bash
# Manually send a ping to confirm the URL is correct:
curl -fsS https://hc-ping.com/<uuid> && echo "ping sent"
# Check https://healthchecks.io dashboard — status should show "up" with last ping timestamp
```

To test the alert: do NOT ping for 28 h, or use the **Pause** button in the dashboard to simulate a missed check and verify email delivery.
