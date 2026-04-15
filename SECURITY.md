# Security Policy

## Reporting a vulnerability

Report security vulnerabilities privately to the operator. Do NOT open a public issue.

Contact: security@cardex.eu (or via the operator contact in KeePassXC `CARDEX/` entry).

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact assessment
- Any suggested mitigations

## What this project collects

CARDEX indexes **publicly available** vehicle listings from dealer websites. It does not:
- Collect or store personal data (names, emails, phone numbers) of individuals.
- Access any non-public systems.
- Use credentials to authenticate to dealer sites.

All crawled URLs are public-facing pages. The system respects `robots.txt`.

## Crawling policy

- **User-Agent:** `CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)`. Identifies honestly.
- **robots.txt:** Checked before crawling any URL. `RobotsChecker` is wired in all HTTP clients.
- **Rate limiting:** Token bucket per domain, default 0.3 req/s (~18 req/min).
- **Backoff:** Exponential backoff on 429/503. Obeys `Retry-After` headers.

## Illegal techniques — permanent prohibition

The following techniques are **permanently prohibited** under the CARDEX institutional regime (V6 mandate) and enforced by CI:

- User-Agent spoofing (any browser UA, Googlebot, or other known bot impersonation)
- TLS fingerprint cloning / JA3/JA4 impersonation (curl_cffi, similar)
- Playwright-stealth / headless browser detection evasion
- Automated CAPTCHA solving (2captcha, hcaptcha, capsolver, etc.)
- Residential proxy rotation for WAF evasion
- Any technique whose declared purpose is to evade anti-bot controls

CI pipeline (`illegal-pattern-scan.yml`) blocks commits containing these patterns.

## Secret management

- Secrets are never committed to git (enforced by `.gitignore` + gitleaks pre-commit hook).
- Production secrets are encrypted at rest using `systemd-creds` on the VPS.
- Backup archives are encrypted with `age` before transmission.
- SSH private keys and age private keys are stored in KeePassXC and on offline USB.
- See `deploy/secrets/README.md` for the full secrets inventory.

## Dependency scanning

The CI pipeline runs `govulncheck` (Go) and `pip-audit` (Python) on every push. See `.forgejo/workflows/dependency-scan.yml`.

## Supported versions

| Version / Branch | Supported |
|-----------------|-----------|
| `main` | Yes |
| Feature branches | No |
