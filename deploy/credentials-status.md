# CARDEX API Credentials Status

Last updated: 2026-04-18

This document tracks the integration status of each external API.  
**No secrets are stored here.** Store actual credentials in `.env` (gitignored).

---

## API Registry

| API | Provider | Auth Type | Env Var(s) | Required | Status | Notes |
|-----|----------|-----------|------------|----------|--------|-------|
| VIES VAT | EU Commission | None (public) | — | No | ✅ Active | `ec.europa.eu/taxation_customs/vies/rest-api` — 50 req/min |
| NHTSA vPIC | US DOT | None (public) | `NHTSA_BASE_URL` | No | ✅ Active | US VIN decode, no auth |
| RDW Open Data | Rijksdienst voor het Wegverkeer | None (public) | `RDW_BASE_URL` | No | ✅ Active | NL vehicle/APK registry, Socrata |
| OffeneRegister | Open data DE | None (public) | `OFFENEREGISTER_DB_PATH` | No | ✅ Active | Bulk SQLite download |
| INSEE Sirene | INSEE France | OAuth2 Bearer | `INSEE_TOKEN` | Yes (FR) | ⚠️ Configure | Register at portail.espace-collegue.insee.fr |
| YouTube Data API v3 | Google / GCP | API Key | `YOUTUBE_API_KEY` | No | ⚠️ Configure | GCP project: decision-iq-482214; skipped if absent |
| KvK Zoeken v2 | Kamer van Koophandel (NL) | API Key | `KVK_API_KEY` | No | ⚠️ Configure | Test env available; skipped if absent |
| KBO Open Data | Belgian CBE | Username/Password | `KBO_USER`, `KBO_PASS` | Yes (BE) | ⚠️ Configure | kbopub.economie.fgov.be/kbo-open-data |
| Pappers.fr | Pappers | API Key | `PAPPERS_API_KEY` | No | ⚠️ Configure | 50 req/h unauthenticated fallback |
| Censys v2 | Censys.io | ID + Secret | `CENSYS_API_ID`, `CENSYS_API_SECRET` | No | ⚠️ Configure | N.1; skipped if absent |
| Shodan | Shodan.io | API Key | `SHODAN_API_KEY` | No | ⚠️ Configure | N.2; skipped if absent |
| ViewDNS.info | ViewDNS | API Key | `VIEWDNS_API_KEY` | No | ⚠️ Configure | N.4; skipped if absent |
| SMTP (outbound) | Operator-provided | User/Pass | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` | No | ⚠️ Configure | Reply engine; inbox works without SMTP |
| JWT signing | Internal | HMAC-SHA256 | `CARDEX_JWT_SECRET` | Yes (prod) | ⚠️ Configure | Ephemeral random used if absent |

---

## Status Legend

- ✅ **Active** — Public API, no credentials needed, already integrated.
- ⚠️ **Configure** — Requires credentials in `.env` before use.
- 🔴 **Blocked** — Integration not yet implemented.

---

## Credential Acquisition Guide

### INSEE Sirene (INSEE_TOKEN)
1. Go to https://portail.espace-collegue.insee.fr/
2. Create an account and subscribe to the "Sirene" API
3. Generate an OAuth2 client credentials token
4. Set `INSEE_TOKEN=Bearer <token>` in `.env`

### YouTube Data API v3 (YOUTUBE_API_KEY)
1. Go to https://console.cloud.google.com — project `decision-iq-482214`
2. Navigate to APIs & Services → Credentials
3. Create an API Key, restrict it to YouTube Data API v3
4. Set `YOUTUBE_API_KEY=<key>` in `.env`

### KvK Zoeken v2 (KVK_API_KEY)
1. Register at https://developers.kvk.nl/
2. Subscribe to the Zoeken v2 API (test environment available)
3. Copy your API key
4. Set `KVK_API_KEY=<key>` in `.env`

### KBO Open Data (KBO_USER / KBO_PASS)
1. Register at https://kbopub.economie.fgov.be/kbo-open-data
2. Request bulk download access
3. Set `KBO_USER=<user>` and `KBO_PASS=<pass>` in `.env`

### Pappers.fr (PAPPERS_API_KEY)
1. Create an account at https://www.pappers.fr/api
2. Subscribe to a paid plan for higher limits
3. Set `PAPPERS_API_KEY=<token>` in `.env`

### Censys v2 (CENSYS_API_ID / CENSYS_API_SECRET)
1. Log in at https://censys.io
2. Navigate to Account → API Access
3. Set `CENSYS_API_ID=<id>` and `CENSYS_API_SECRET=<secret>` in `.env`

### Shodan (SHODAN_API_KEY)
1. Log in at https://account.shodan.io
2. Copy your API key from the dashboard
3. Set `SHODAN_API_KEY=<key>` in `.env`

### ViewDNS.info (VIEWDNS_API_KEY)
1. Register at https://viewdns.info/api/
2. Set `VIEWDNS_API_KEY=<key>` in `.env`

### SMTP
Configure your SMTP provider (e.g., SendGrid, Postmark, or a self-hosted relay):
```
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASS=<sendgrid-api-key>
SMTP_FROM=noreply@cardex.eu
```

### JWT Secret
Generate a secure 256-bit key:
```bash
openssl rand -hex 32
```
Set `CARDEX_JWT_SECRET=<output>` in `.env`.

---

## Security Notes

- All credentials are loaded exclusively from environment variables.
- `.env` and `.env.*` are excluded from git via `.gitignore`.
- Only `env.example` (with placeholder values) is committed.
- Run `grep -r "AIzaSy\|NMMos\|0d6022\|l7xx1f" --include="*.go" --include="*.ts" .` to verify no keys leaked into source.
