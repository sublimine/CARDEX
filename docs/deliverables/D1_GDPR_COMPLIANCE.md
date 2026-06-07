# CARDEX — GDPR Compliance Framework for Vehicle Data Scraping

**Version:** 1.0
**Date:** 2026-06-05
**Classification:** Internal — Legal & Compliance
**Applicable regulation:** Regulation (EU) 2016/679 (GDPR / RGPD)
**Scope:** Processing of data scraped from 84+ vehicle listing portals across DE, ES, FR, NL, BE, CH

---

## 1. Nature of the Data CARDEX Processes

CARDEX is a vehicle intelligence platform that indexes publicly listed used-car advertisements from dealer websites and marketplace portals. It is critical to distinguish what CARDEX processes:

**Primary data (core business):**
- Vehicle attributes: make, model, year, mileage, price, fuel type, transmission, color, VIN (when publicly listed)
- Listing metadata: URL, first-seen date, last-seen date, listing status, source portal
- Vehicle images: URLs to publicly hosted photos

**Incidental personal data (unavoidable byproduct of scraping):**
- Dealer business name, commercial address, phone number, email (published on listing pages)
- Dealer VAT/trade registration numbers (publicly available in business registries)
- Occasionally: salesperson first name embedded in listing contact sections

**What CARDEX does NOT collect:**
- End-consumer/buyer personal data — CARDEX has no users, no accounts, no B2C interface
- Private seller personal data — listings from private individuals are excluded at extraction time (filter: dealer-only)
- Browsing behavior, cookies, or tracking data of any person
- Financial data, payment information, health data, biometric data

---

## 2. Legal Basis for Processing

### 2.1 Vehicle Data

Vehicle attributes (make, model, price, mileage, etc.) are **not personal data** under GDPR Art. 4(1). A car listing for "BMW 320d, 2020, 45.000 km, €22.500" does not identify or relate to a natural person. No legal basis required.

### 2.2 Dealer Business Data

Dealer data (company name, commercial address, business phone, VAT number) falls under a grey zone:

- **Sole traders / Einzelunternehmer (DE) / Auto-entrepreneur (FR):** The business name may be the natural person's name. This IS personal data.
- **Limited companies (GmbH, SL, SARL, BV):** Corporate data is generally NOT personal data, but contact persons named on listings may be.

**Legal basis chosen: Legitimate Interest (Art. 6(1)(f))**

Justification per three-part test:

| Element | Assessment |
|---------|------------|
| **Legitimate interest** | CARDEX provides market intelligence to the automotive trade sector. Understanding which dealers sell which vehicles at which prices is a legitimate commercial intelligence function, comparable to established players (Indicata/Autorola, DAT/Schwacke, Eurotax). |
| **Necessity** | Dealer identification is necessary to: (a) deduplicate listings across portals, (b) validate listing authenticity, (c) provide dealer-level analytics. No less-intrusive means achieves the same result. |
| **Balancing test** | Dealer data is already published by the dealers themselves on commercial websites for the express purpose of attracting buyers. The reasonable expectation of a dealer who publishes their inventory online is that it will be found, indexed, and compared — this is the entire purpose of listing on a portal. The additional processing by CARDEX does not exceed that expectation. |

### 2.3 robots.txt Compliance

CARDEX respects robots.txt on all scraped domains as a technical and legal safeguard. This is enforced at the scraper level (non-negotiable constraint). robots.txt compliance supports the legitimate interest balancing test by demonstrating that CARDEX honors publisher preferences.

### 2.4 Swiss Data (CH — non-EU)

Switzerland is not in the EU but has GDPR adequacy under the Federal Act on Data Protection (nFADG/nDSG, effective 2023-09-01). CARDEX applies identical protections to CH data. No additional transfer mechanism is needed for CH↔EU data flows since the EU Commission recognizes Swiss adequacy.

---

## 3. Data Minimization (Art. 5(1)(c))

CARDEX implements data minimization at three levels:

**At collection (scraper level):**
- Only vehicle listing data is extracted. No scraping of dealer "About Us" pages, social media profiles, or employee directories.
- Private seller listings are filtered out at extraction time — the extraction strategies (E01–E13) target dealer inventory pages specifically.
- No collection of data beyond what is visible on the public listing page.

**At storage (quality pipeline):**
- Validator V12 (cross-source dedup) ensures each listing is stored once, not duplicated across portals.
- Validator V17 (sold status detection) removes stale listings, preventing indefinite retention of obsolete data.
- Validator V14 (freshness) flags listings not re-confirmed within 30 days for automatic GONE status.

**At enrichment:**
- No enrichment with external personal data sources. No social media cross-referencing. No credit checks. No reverse phone lookups.

---

## 4. Data Retention Policy (Art. 5(1)(e))

| Data category | Retention period | Justification | Deletion mechanism |
|--------------|-----------------|---------------|-------------------|
| Active vehicle listings | While listing is live + 90 days after last-seen | Historical pricing requires short post-delist retention for trend analysis | V17 sold detection → GONE event → 90-day grace → hard delete |
| Dealer business data | While dealer has active listings + 90 days | Tied to listing lifecycle | Cascading delete when last listing expires |
| Vehicle images (URLs only) | Same as listing | CARDEX stores URLs, not images. URL becomes dead on portal delist. | Deleted with listing record |
| Scraper logs | 30 days rolling | Operational debugging only | Prometheus retention: 30d (configured in docker-compose) |
| Backup archives | 90 days | Disaster recovery | age-encrypted, stored on Hetzner Storage Box, rotated by `backup.sh` |

**No indefinite retention.** Every data record has a defined expiry trigger.

---

## 5. Data Subject Rights — Operational Procedures

### 5.1 Right of Access (Art. 15)

**Trigger:** Dealer or person contacts CARDEX requesting what data is held about them.

**Procedure:**
1. Verify identity of requester (email from business domain, or official request with ID)
2. Query SQLite database: `SELECT * FROM vehicle_index WHERE dealer_name LIKE '%<name>%' OR dealer_url LIKE '%<domain>%'`
3. Export results as CSV
4. Respond within 30 days (Art. 12(3))
5. Log the request in `compliance/access_requests.log`

**Realistic note:** With zero customers and zero public-facing interface, the probability of receiving an Art. 15 request in the next 12 months is near zero. But the procedure exists and is executable.

### 5.2 Right to Erasure (Art. 17)

**Trigger:** Dealer requests deletion of their data from CARDEX index.

**Procedure:**
1. Verify identity
2. Execute: `DELETE FROM vehicle_index WHERE dealer_id = <id>` (cascading to all listings)
3. Add dealer domain to `compliance/blocklist.txt` — scrapers check this before extraction
4. Confirm deletion to requester within 30 days
5. Ensure next backup cycle does not contain deleted records (backup.sh runs post-deletion)

**Grounds for refusal (Art. 17(3)):** None applicable to CARDEX's use case. If a dealer asks for deletion, comply.

### 5.3 Right to Object (Art. 21)

**Trigger:** Dealer objects to processing of their data under legitimate interest.

**Procedure:** Same as erasure — there is no "compelling legitimate ground" that overrides a dealer's objection when the data is their own business listings. Comply and blocklist.

### 5.4 Right to Rectification (Art. 16)

**Trigger:** Dealer claims data is inaccurate.

**Procedure:** CARDEX data is a snapshot of what was publicly listed. If the listing has changed, the next scrape cycle will pick up the correction automatically. For immediate correction: update the record manually and log it.

---

## 6. Record of Processing Activities (Art. 30)

Required because CARDEX processes data systematically and at scale (1.55M+ vehicle records).

| Field | Value |
|-------|-------|
| **Controller name** | CARDEX (Elias Karrouch, sole operator) |
| **Contact** | privacy@cardex.eu |
| **Purposes of processing** | Vehicle market intelligence: indexing, normalization, pricing analysis, and market trend detection for the European used-car trade sector |
| **Categories of data subjects** | Vehicle dealers (commercial entities, some sole traders) |
| **Categories of personal data** | Business name, commercial address, business phone, business email, VAT number (all publicly published by the data subjects) |
| **Categories of recipients** | Future: B2B API consumers (dealers, fleet managers). Current: none (pre-revenue) |
| **Transfers to third countries** | CH data processed on DE server — CH has EU adequacy. No other third-country transfers. |
| **Retention periods** | See §4 above |
| **Technical & organizational measures** | See §7 below |

---

## 7. Technical and Organizational Measures (Art. 32)

### 7.1 Infrastructure Security

| Measure | Implementation |
|---------|----------------|
| Encryption in transit | TLS 1.3 via Caddy (HSTS enforced). All service-to-service communication on localhost. |
| Encryption at rest | Backups encrypted with age (age-keygen). SQLite database on encrypted NVMe (Hetzner full-disk encryption on CX42). |
| Access control | SSH key-only authentication (Ed25519). No password auth. Fail2ban active. UFW firewall (ports 22, 80, 443 only). |
| Secret management | No secrets in git. Credentials in systemd-creds encrypted store. KeePassXC for operator secrets. |
| Monitoring | Prometheus + Grafana + Alertmanager with 10 alert rules. Service-level metrics. Disk space monitoring. |
| Backup | Daily automated backup to Hetzner Storage Box. age-encrypted. 90-day retention. Integrity checks (PRAGMA integrity_check) on restore. |

### 7.2 Organizational Measures

| Measure | Implementation |
|---------|----------------|
| Data access | Single operator (founder). No shared credentials. No employee access (no employees). |
| Incident response | Documented in `deploy/incident-runbooks/` (7 runbooks: triage, service down, disk full, DB corruption, secret leak, TLS failure, operator unavailable). |
| Vendor assessment | Hetzner (DE-based, ISO 27001). Proxy providers (Decodo, Oxylabs) — data passes through but is not stored by proxies. |
| Code review | All changes through git. No direct production edits. |

---

## 8. Data Protection Impact Assessment (DPIA) — Summary

A DPIA is required under Art. 35(3) when processing involves "systematic monitoring of a publicly accessible area" — which web scraping arguably constitutes.

### 8.1 Assessment

| Factor | Evaluation |
|--------|------------|
| **Nature of processing** | Systematic, automated collection of publicly available commercial vehicle listings |
| **Scope** | 84+ portals, 6 countries, 1.55M+ listings |
| **Context** | B2B market intelligence. No profiling of natural persons. No automated decision-making affecting individuals. |
| **Risk to data subjects** | LOW. Data is already public. No sensitive categories. Worst case: a dealer discovers their public listings are indexed — which is the explicit purpose of listing on a portal. |
| **Mitigations** | robots.txt compliance, rate limiting (0.3 req/s), deletion on request, 90-day retention cap, no enrichment with external personal data |

### 8.2 Conclusion

Risk level: **LOW**. The processing is analogous to what Google, Bing, and every marketplace aggregator does with publicly listed commercial data. The mitigations (robots.txt compliance, rate limiting, erasure on request) are proportionate to the risk.

**No DPO appointment required** (Art. 37): CARDEX is not a public authority, does not carry out large-scale systematic monitoring as core activity (vehicle indexing is the core, not person monitoring), and does not process special categories of data.

---

## 9. Cease & Desist Response Protocol

Because CARDEX scrapes third-party portals, the most probable legal scenario is not a GDPR complaint from a data subject, but a cease-and-desist from a portal operator.

**Response protocol:**

1. **Receive C&D.** Log it immediately in `compliance/cd_log.md` with date, sender, portal, demands.
2. **Stop scraping the portal within 24h.** Add domain to `compliance/blocklist.txt`. This is non-negotiable — fighting a C&D is not viable at €300/month.
3. **Respond to sender** within 5 business days acknowledging receipt and confirming cessation.
4. **Purge historical data** from that portal within 30 days if demanded.
5. **Assess impact:** How many listings came from that portal? Can alternative sources cover the gap?

**Prevention:** robots.txt compliance, respectful rate limiting, and use of a clearly identified bot UA for Go services (`CardexBot/1.0`) reduce C&D probability. The Python scraper fleet uses browser-mimicking UAs (Strategy B) — this is a calculated trade-off documented in `docs/PYTHON_SCRAPER_AUDIT_2026-06.md`.

---

## 10. Cookie and Consent Compliance

CARDEX's scrapers interact with portal cookie consent mechanisms:

- **curl_cffi fleet (T1):** Does not execute JavaScript. Does not interact with consent banners. Receives only server-set cookies (session IDs, Cloudflare tokens). No consent-wall bypass.
- **Camoufox fleet (T2/T3):** Executes JavaScript. Cookie banners may appear. Scrapers do NOT click "accept all" — they navigate without interacting with the banner. If a portal requires cookie consent to display content, that portal's listings may be incomplete. This is an accepted trade-off.

CARDEX itself has no frontend, no cookies set on users, no tracking pixels, no analytics. When a B2B API is deployed, it will serve data via authenticated API calls with no cookies.

---

## 11. Annual Review Cadence

| Action | Frequency | Responsible |
|--------|-----------|-------------|
| Review this document for accuracy | Every 6 months or on major pipeline change | Operator |
| Update Record of Processing Activities | On new data source addition or removal | Operator |
| Review blocklist for expired C&Ds | Every 6 months | Operator |
| Test Art. 17 deletion procedure | Annually (dry run) | Operator |
| Review retention policy effectiveness | Annually | Operator |

---

*This document reflects CARDEX's actual operational state as of 2026-06-05. It does not describe aspirational compliance measures. Every procedure described here is executable by a single operator with the current infrastructure (1x Hetzner CX42, SQLite, 3 Go services, Python scraper fleet).*
