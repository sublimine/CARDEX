# Security Policy

## Reporting a vulnerability

Report security vulnerabilities privately to the operator. Do NOT open a public issue.

Contact: security@cardex.eu

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact assessment
- Any suggested mitigations

## What this project collects

CARDEX indexes **publicly available** vehicle listings from dealer and platform
websites. It does not:
- Collect or store personal data (names, emails, phone numbers) of individuals.
- Access any non-public systems.
- Use credentials to authenticate to dealer sites.

All crawled URLs are public-facing pages.

## Crawling policy — Strategy B (in force since 2026-05-16)

The crawling stack is an explicit, owner-approved decision. The previous "V6"
regime (blanket prohibition of TLS impersonation and proxies) is **superseded**;
this section reflects the policy actually enforced in code and CI definition.

**Approved stack (the only one):**
- `curl_cffi>=0.15.1` — TLS impersonation at **session** level only (same JA3
  fingerprint from page 1 to N; engine swap mid-session is forbidden). Targets a
  **current** Chrome build; fingerprints are refreshed as they rot (~6 weeks).
- `camoufox[geoip]` — hardened browser for browser-tier work.
- Playwright (strategy E07) where a full browser is required.
- Residential proxies (Decodo/Oxylabs) are approved **but gated behind a literal
  owner spending decision** — not in use by default.

**Two User-Agent layers, by design:**
- Go modules (dormant scaffold) identify honestly as
  `CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)` and wire a
  robots.txt checker in HTML-crawling strategies.
- The Python fleet's UA is managed by the TLS fingerprint engine (a hand-set UA
  contradicting the TLS fingerprint is itself a detectable inconsistency).

**Source survival rules:** jittered per-page delays (~1.2s ± 0.4s), per-domain
rate floors, exponential backoff on 429/503, shard pauses on sitemap sweeps.
Sources are an asset; burning them is a defect.

**Blocked patterns** (enforced by the CI definition
`.forgejo/workflows/illegal-pattern-scan.yml` — Forgejo workflow; note it is not
currently wired to GitHub Actions):
- playwright-stealth, puppeteer-stealth, undetected-chromedriver (outdated tooling)
- fake-useragent and literal UA spoofing in Go services
- scrapingbee / scraperapi / brightdata (not in the approved vendor list)
- Re-introduction of previously purged stealth files (purge guard)

## Secret management

- Secrets are never committed to git — enforced by `.gitignore` plus a gitleaks
  pre-commit hook (`.pre-commit-config.yaml`).
- **Development defaults are public knowledge:** this repository is public and the
  dev Docker stack uses obvious dev-only credentials (e.g. `cardex_dev_only`).
  They exist only for the local loopback stack and MUST be overridden via
  environment in any deployment. Nothing production-facing may reuse them.
- Real credentials (registry API keys, SMTP, proxy vendors) live in the local
  `.env` (gitignored) — see `.env.example` for the catalog.
- Deploy-time secret handling (systemd-creds, age-encrypted backups) is specified
  in `deploy/` for the VPS profile; no public VPS is currently deployed.

## Dependency scanning

`govulncheck` (Go) and `pip-audit` (Python) are defined in the Forgejo CI
workflows (`.forgejo/workflows/`). They run where a Forgejo runner is attached;
they are not wired to GitHub Actions. Treat them as runnable definitions, not as
a guarantee attached to every push on GitHub.

## Supported versions

| Version / Branch | Supported |
|-----------------|-----------|
| `main` | Yes |
| Feature branches | No |
