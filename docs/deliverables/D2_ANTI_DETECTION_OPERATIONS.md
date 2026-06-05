# CARDEX — Anti-Detection Operations Guide

**Version:** 1.0
**Date:** 2026-06-05
**Classification:** Internal — Operational (CONFIDENTIAL)
**Purpose:** Consolidated operational reference for CARDEX's scraping anti-detection systems
**Source of truth for engine design:** `docs/SCRAPING_ENGINE.md`

---

## 1. Threat Model — What We Face

CARDEX scrapes 84+ portals across 6 EU countries. The adversaries are anti-bot systems deployed by these portals. Each portal falls into one of four protection tiers:

| Tier | Protection | Example portals | Detection vectors |
|------|-----------|----------------|-------------------|
| T0 | None / Public API | 2dehands.be, mobile.de Ad-Stream (WSS) | N/A — public endpoints |
| T1 | Basic (IP rate limiting, UA checks) | kleinanzeigen.de, coches.net, tutti.ch, motor.es, marktplaats.nl | IP reputation, request rate, static UA analysis |
| T2 | Akamai Bot Manager v3 | autoscout24.* (×6 TLDs), wallapop.com, gocar.be, heycar.com, comparis.ch | TLS fingerprint (JA3/JA4), sensor JavaScript (_abck), cookie validation, behavioral signals |
| T3 | DataDome (behavioral) | leboncoin.fr, lacentrale.fr | All T2 vectors + mouse movement analysis, scroll patterns, interaction timing, device-check slider challenge |

**Key insight:** The dominant anti-bot on EU car portals is continuous trust scoring, not interactive CAPTCHA. DataDome and Akamai assign a trust score to each session based on cumulative signals. A single detection vector compromised (e.g., TLS mismatch) can cascade into a session ban even if all other signals are clean.

---

## 2. Approved Stack (Strategy B — effective 2026-05-16)

| Component | Role | Version/Config |
|-----------|------|---------------|
| `curl_cffi` | TLS-impersonating HTTP client | ≥0.15.1, Chrome 136+ fingerprint |
| Camoufox | Anti-detect Firefox fork (C++ patches) | Latest from daijro/camoufox, geoip=True |
| Decodo ISP proxies | Sticky IPs for T1/T2 portals | 4h sticky sessions per identity |
| Oxylabs residential | Rotating IPs for T3 portals | New IP per session, NOT per request |
| CapSolver | CAPTCHA fallback | Turnstile, reCAPTCHA, DataDome slider |
| httpcloak (future) | TCP/IP stack fingerprint spoofing | Go, CAP_NET_RAW — designed, not deployed |

**Superseded / banned tools (P0 purge, commit `ed5e54f`):**
- `playwright-stealth` → replaced by Camoufox
- `undetected-chromedriver` → replaced by Camoufox/nodriver
- `fake-useragent` library → UA managed by curl_cffi/Camoufox natively
- ScrapingBee, ScraperAPI → not in approved vendor list

CI enforcement: `illegal-pattern-scan.yml` blocks imports of superseded tools.

---

## 3. Detection Vectors — Comprehensive Reference

### 3.1 Network Layer

| Vector | What detectors check | CARDEX mitigation |
|--------|---------------------|-------------------|
| IP ASN classification | Datacenter IPs (Hetzner, AWS, etc.) are flagged immediately | All scrape traffic routes through residential/ISP proxies. VPS IP never hits target portals. |
| IP reputation | Shared IPs with abuse history score low | Decodo ISP (dedicated IPs, private history). Oxylabs residential (large pool, rotation). |
| IP–geo consistency | IP geolocation must match timezone, locale, WebRTC IP | Camoufox `geoip=True` auto-aligns WebRTC + timezone + locale with proxy IP country |
| Rate from single IP | Sustained high request rate from one IP = bot | 0.3 req/s per domain for curl_cffi. Camoufox: 1 req per browser instance with natural delays. |

### 3.2 TLS Layer

| Vector | What detectors check | CARDEX mitigation |
|--------|---------------------|-------------------|
| JA3/JA4 fingerprint | TLS ClientHello must match claimed browser | curl_cffi impersonates Chrome 136 TLS profile. JA3 hash matches real Chrome. |
| JA3 consistency | Same JA3 across all requests in a session | curl_cffi session created ONCE per session. JA3 invariant page 1→N. |
| HTTP/2 settings frame | SETTINGS frame order reveals automation libraries | curl_cffi matches Chrome's SETTINGS frame. |
| ALPN + cipher suite order | Must match claimed browser exactly | Handled by curl_cffi's impersonation engine. |

**Critical invariant:** `tcp_profile` + `tls_profile` + browser fingerprint are generated as a coherent set per identity. Never mix a Chrome TLS with Firefox UA or vice versa.

### 3.3 Browser Fingerprint Layer

| Vector | Camoufox (T2/T3) | curl_cffi (T1) |
|--------|-------------------|----------------|
| `navigator.webdriver` | Absent — patched at C++ level, not JS | N/A (no JS execution) |
| Canvas fingerprint | Deterministic noise per identity seed (C++) | N/A |
| AudioContext fingerprint | Deterministic noise per identity seed (C++) | N/A |
| WebGL vendor/renderer | Coherent with OS profile, C++ level | N/A |
| Font enumeration | Subset of real OS fonts | N/A |
| `navigator.plugins` | Real Firefox PluginArray | N/A |
| Screen geometry | outerWidth/innerWidth coherent with real Chrome/Firefox | N/A |
| `performance.now()` precision | Normal resolution, not reduced | N/A |

**Why Camoufox over Playwright/Patchright:** Camoufox patches at the C++ engine level. JS-level patches (Playwright stealth, Patchright) are detectable because canvas hash mismatch, `Object.getOwnPropertyDescriptor` checks, and prototype chain analysis can all reveal JS overrides. C++ patches produce outputs indistinguishable from real browser behavior.

**Known residual risk:** Camoufox's TLS is Firefox-shaped, not Chrome-shaped. Some anti-bot systems can distinguish Firefox automation from real Firefox via subtle TLS differences. Mitigation: Firefox is whitelisted on most EU car portals because real Firefox users exist. This is acceptable.

### 3.4 Behavioral Layer (T3 — DataDome/Akamai advanced)

| Vector | What detectors check | CARDEX mitigation |
|--------|---------------------|-------------------|
| Mouse movement | Bezier curves, acceleration, jitter | Camoufox T3 fleet uses behavioral simulation (planned: Oxymouse integration) |
| Scroll velocity | Constant-speed scroll = bot | Variable scroll with realistic deceleration |
| Click precision | Pixel-perfect clicks on elements = bot | Click coordinates randomized within element bounding box |
| Dwell time | Time spent on page before interaction | Intent Engine buyer personas: 15-90s per listing, 5-25s per results page |
| Navigation pattern | Direct URL access without referrer = bot | Entry via Google search referrer (70%) or direct (20%) or bookmark (10%) |
| Page sequence | Scraping all pages 1→N sequentially = bot | Buyer persona determines max_pages (2-9), with back-button behavior and comparison patterns |

---

## 4. Identity Lifecycle Management

Each scraping session operates under a persistent identity — a coherent bundle of proxy, TLS profile, browser fingerprint, and session state.

### 4.1 Identity States

```
new → warming (24-72h) → active → degraded → quarantine (48h) → retired
                          ↑                         ↓
                          └──── recovery (if score recovers) ───┘
```

### 4.2 Trust Score Mechanics

- **+0.05** per successful request
- **-1.0** per soft-block (HTTP 429, CAPTCHA challenge, content degradation)
- **-3.0** per hard-block (HTTP 403, IP ban, account suspension)
- **Score < 0** → quarantine 48h (no requests)
- **Score < -5.0** → retired permanently (identity burned)
- **Score ≥ 7.0** → PREMIUM status (eligible for T3 DataDome portals)

### 4.3 Warming Protocol

**Phase 1 — Ambient traffic (48h):** The identity browses general websites (news, search, YouTube) to establish organic ISP traffic patterns. No portal visits. Purpose: ISP/AS sees normal residential behavior.

**Phase 2 — Portal familiarization (24h):** First visits to target portal homepage + categories. No extraction. 1-2 listing views with 30-60s dwell. Purpose: Generate real cookies, initial _abck token. Akamai registers identity as "returning user level 1."

**Phase 3 — Active:** Extraction permitted. Trust score ≥ 3.0. Each session follows Intent Engine navigation plan.

**Invariant:** An identity that extracts before completing Phase 2 is burned. No recovery — retire immediately.

### 4.4 Akamai _abck Token Management

The _abck cookie is Akamai Bot Manager's sensor token. It encodes the browser's behavioral trust level.

- **Generation:** First portal visit → Akamai sensor JS runs → generates _abck → stored in identity's session state
- **Persistence:** Stored in `engine.db` per (identity, domain)
- **Refresh:** If _abck age > 1h → refresh via hyper-sdk-go (without browser)
- **Re-use:** Loading _abck from storage_state makes the identity appear as a returning user — significantly higher trust than first-visit

---

## 5. WAF Classification for New Domains

When a new portal is added to the fleet, determine its protection tier:

```
1. HEAD request without proxy → HTTP 403 immediate? → waf_active=true, level=high
2. GET with curl_cffi (Chrome 136 impersonation) → analyze response headers:
   - CF-Ray header → Cloudflare
   - x-datadome-* headers → DataDome
   - ak_bmsc cookie → Akamai confirmed
   - "Just a moment" in body → Cloudflare challenge page
3. Register result in domain_tier_state with verified_at timestamp
4. Verify with diag.py in verbose mode
```

**Tier assignment heuristic:**
- No protection detected → T0 (direct HTTP) or T1 (curl_cffi)
- Akamai detected → T2 (Camoufox + _abck management)
- DataDome detected → T3 (Camoufox + behavioral + residential proxies)
- Cloudflare basic → T1 (curl_cffi handles Turnstile via CapSolver)
- Cloudflare AI Labyrinth → special handling (poison detection in quality gates)

---

## 6. Soft-Block Detection

A soft-block is when the portal serves degraded content instead of a hard 403. This is harder to detect and more insidious than an outright ban.

**Indicators of soft-block:**
- Response body < 15 KB (normal listing page is 50-200 KB)
- JSON-LD `@type` is not Vehicle/Car/Product (poisoned content)
- Images point to Cloudflare CDN placeholder URLs
- Price field is absent or zero on all listings in a batch
- Text/code ratio > 0.8 (likely a challenge page, not a listing)
- HTTP 200 but body is a CAPTCHA or device-check page

**Response to soft-block detection:**
1. Mark identity as `degraded` (trust_score -= 1.0)
2. Discard the entire batch (do not ingest poisoned data)
3. Retry with different identity in 1h
4. If 3+ identities soft-blocked on same domain in 24h → circuit breaker OPEN (120s pause)
5. Escalate to next tier if pattern persists

---

## 7. Circuit Breaker Protocol

Per (tier, domain):

```
CLOSED → 3 failures in 60s → OPEN (pause 120s) → HALF_OPEN → 1 probe request → CLOSED (if success) / OPEN (if fail, +120s)
```

When a tier's circuit breaker opens:
1. Tier escalator activates: T1 → T2 → T3
2. Escalation is persisted in `engine.db` — not transient
3. De-escalation: manual only (operator reviews weekly)

**Cost implication:** Escalation from T1 to T3 increases cost ~80x per request (proxy GB cost + browser RAM + warming time). Escalation must be justified, not reflexive.

---

## 8. Proxy Fleet Operations

### 8.1 Pool Segregation

| Pool | Provider | Use case | Rotation policy |
|------|----------|----------|-----------------|
| ISP_STICKY | Decodo | AS24 ×6, kleinanzeigen, coches.net | Sticky 4h per session — NEVER rotate mid-session |
| RESIDENTIAL_ROTATING | Oxylabs | leboncoin, lacentrale (DataDome) | New IP per session, NOT per request |
| MOBILE | Decodo Mobile | Last-resort for datacenter-ASN-blocked targets | On demand only |

### 8.2 Proxy Health Monitoring

- `success_rate < 0.7` → soft_degraded (reduce assignment priority)
- `success_rate < 0.5` → quarantine_24h (no assignments)
- Quarantined proxies never assigned to premium identities (trust ≥ 7.0)

### 8.3 Budget Management

At €300/month total CARDEX budget, proxy costs are the dominant variable:

| Scenario | Monthly proxy cost |
|----------|-------------------|
| Light (mostly T1, ~10 GB residential) | ~€50 |
| Medium (T1+T2, ~25 GB residential) | ~€100 |
| Heavy (T1+T2+T3, ~50 GB residential) | ~€200 |

**Rule:** Never exceed 60% of total budget on proxies. If proxy costs approach €180/month, reduce T3 scraping frequency and maximize T0/T1 coverage.

---

## 9. Cloudflare AI Labyrinth — Specific Countermeasure

Cloudflare's AI Labyrinth (deployed 2025-2026) generates fake content pages designed to waste scraper resources and poison data. This is a distinct threat from traditional blocking.

**Detection (implemented in Quality Gate 2):**
- JSON-LD `@type` is not a valid vehicle schema type
- HTML < 15 KB (labyrinth pages are thin)
- Text/code ratio anomaly
- Images reference Cloudflare CDN placeholders
- 2+ flags → POISON_DETECTED → discard entire page

**Prevention:** The best defense is not detection but avoidance — identities with high trust scores on Cloudflare-protected portals should not trigger the labyrinth redirect. Maintain trust through proper warming and behavioral patterns.

---

## 10. Operational Cadence

| Task | Frequency | Method |
|------|-----------|--------|
| Review domain_tier_state for drift | Weekly | Check diag.py output against expected tiers |
| Rotate ISP proxy IPs approaching ban threshold | Monthly | Monitor proxy health dashboard in Grafana |
| Audit identity pool health | Weekly | Query engine.db for identities in degraded/quarantine |
| Re-warm retired identities | As needed | New identity creation, not resurrection of retired ones |
| Update curl_cffi TLS profiles | On Chrome major release (~6 weeks) | Pin new version in requirements.txt |
| Check Camoufox upstream status | Monthly | github.com/daijro/camoufox — maintainer status, fork updates |
| Review CI illegal-pattern-scan | On scraper code changes | Ensure no superseded tools re-introduced |

---

## 11. Known Limitations and Accepted Risks

| Risk | Severity | Mitigation | Status |
|------|----------|------------|--------|
| Camoufox maintainer hiatus (daijro hospitalized since Mar 2025) | Medium | @coryking maintains Firefox 142 fork. Pin known-good build. | Accepted |
| Firefox TLS distinguishable from Chrome TLS | Low | Firefox is whitelisted on most EU portals. Acceptable. | Accepted |
| Behavioral entropy (mouse, scroll) not fully simulated | Medium | Planned: Oxymouse integration for T3. Currently manual patterns. | In progress |
| CSS media query fingerprinting | Low | Variance is low, risk is low. | Accepted |
| Mobile API reverse engineering requires per-portal effort | Medium | ~4h per portal. ROI positive after first week of production use. | Partial (mobile.de done, AS24 viable, others pending) |

---

*This document consolidates anti-detection knowledge from `docs/SCRAPING_ENGINE.md` and operational experience into an actionable guide. It reflects the actual deployed stack (Strategy B, 2026-05-16) and does not describe aspirational capabilities. All tier assignments are based on verified WAF classification, not assumptions.*
