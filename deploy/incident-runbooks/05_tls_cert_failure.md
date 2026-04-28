# 05 — TLS Cert Failure

Caddy auto-manages Let's Encrypt certs. This runbook covers renewal failure.

---

## 1. Identify the error

```bash
journalctl -u caddy -n 80 --no-pager | grep -iE "acme|tls|cert|renew|error"
caddy validate --config /etc/caddy/Caddyfile
```

Common causes: port 80 blocked (ACME HTTP-01 challenge), rate-limit hit, DNS misconfigured.

## 2. Check port 80 is reachable

```bash
ss -tlnp | grep ':80'
# Should show caddy. If not:
systemctl restart caddy
# Test externally (from another host):
curl -I http://<your-domain>/
```

If a firewall blocks port 80:
```bash
ufw allow 80/tcp
# or if using hetzner firewall: add inbound TCP 80 rule in cloud console
```

## 3. Force Caddy to reload and retry ACME

```bash
systemctl reload caddy     # graceful reload, re-triggers cert checks
sleep 30
journalctl -u caddy -n 30 --no-pager | grep -iE "cert|acme|obtain|renew"
```

If cert is expired and Caddy is serving stale:
```bash
# Remove cached cert to force re-issuance:
find /var/lib/caddy/.local/share/caddy/certificates -name "*.crt" | head -5
# Caddy stores certs under: /var/lib/caddy/.local/share/caddy/certificates/
rm -rf /var/lib/caddy/.local/share/caddy/certificates/acme-v02.api.letsencrypt.org/
systemctl restart caddy
journalctl -u caddy -f   # watch for "certificate obtained"
```

## 4. Fallback: switch to Buypass ACME (alternative CA)

Edit `/etc/caddy/Caddyfile`, change the TLS block for affected domain:

```caddyfile
yourdomain.com {
    tls {
        ca https://api.buypass.com/acme/directory
    }
    reverse_proxy localhost:8081
}
```

```bash
systemctl restart caddy
journalctl -u caddy -f
```

Buypass issues 180-day certs and has separate rate limits from Let's Encrypt.

## 5. Emergency: self-signed cert for internal access only

Use only if external ACME is broken and internal access is needed immediately.

```bash
# Generate self-signed cert (valid 90 days):
openssl req -x509 -newkey rsa:4096 -keyout /etc/caddy/selfsigned.key \
  -out /etc/caddy/selfsigned.crt -days 90 -nodes \
  -subj "/CN=cardex-internal"

# Update Caddyfile to use it:
# tls /etc/caddy/selfsigned.crt /etc/caddy/selfsigned.key

systemctl restart caddy
# Access via: curl -k https://localhost/health
```

Remove self-signed config once real cert is restored.

## 6. Validate

```bash
echo | openssl s_client -connect yourdomain.com:443 2>/dev/null | openssl x509 -noout -dates
curl -sf https://yourdomain.com/health && echo "TLS OK"
```
