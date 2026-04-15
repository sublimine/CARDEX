# Caddy — Reverse Proxy & TLS Termination

Caddy handles all inbound HTTPS traffic for CARDEX, including automatic
TLS certificate provisioning via Let's Encrypt.

## Domain Setup

1. Buy/transfer domain to Namecheap (or any registrar).
2. Point A record to VPS IP: `cardex.io → 1.2.3.4`
3. Point CNAME for `www`: `www.cardex.io → cardex.io`
4. Set env var: `export CARDEX_DOMAIN=cardex.io`
5. Ensure port 80 is open in ufw for ACME HTTP-01 challenge:
   ```bash
   ufw allow 80/tcp
   ufw allow 443/tcp
   ```

## How TLS Works

Caddy automatically:
- Generates a certificate via Let's Encrypt ACME HTTP-01 challenge on first start
- Renews certificates before expiry (typically 30 days before 90-day expiry)
- Serves TLS 1.3 only with forward-secrecy ciphers

No manual `certbot` or cron required.

## Local Development

In local dev (`CARDEX_DOMAIN=localhost`), Caddy generates a self-signed
certificate trusted only by the local browser. Chrome/Firefox will show
a warning — click "Advanced → Proceed". To avoid this:

```bash
# Install Caddy's local CA into system trust store (once per machine):
caddy trust
```

## Exposed Endpoints

| Path | Upstream | Notes |
|------|----------|-------|
| `/health` | static "OK" | UptimeRobot monitor target |
| `/api/discovery/*` | `discovery:8080` | |
| `/api/extraction/*` | `extraction:8080` | |
| `/api/quality/*` | `quality:8080` | |
| `/grafana/*` | `grafana:3000` | Loopback only — use SSH tunnel |
| `/metrics*` | `prometheus:9090` | Loopback only |

## Grafana Access (Production)

Grafana is NOT exposed externally. Access via SSH tunnel:

```bash
ssh -L 3001:localhost:3001 cardex@cardex.io
# Then open http://localhost:3001 in browser
```

## Rate Limiting

Not yet configured in the Caddyfile (requires `caddy-ratelimit` plugin
or upstream rate limiting). For Phase 7 (public API), add:

```caddyfile
rate_limit {
    zone api_global {
        key {remote_host}
        events 100
        window 1m
    }
}
```

## Edge mTLS (Phase 6 — E12)

When E12 Edge Client is deployed, add client certificate verification:

```caddyfile
tls {
    client_auth {
        mode require_and_verify
        trusted_ca_certs_pem_file /etc/caddy/edge-ca.crt
    }
}
```
