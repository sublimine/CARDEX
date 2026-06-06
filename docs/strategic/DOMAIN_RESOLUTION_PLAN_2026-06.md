# Domain Resolution Plan — June 2026

**Objective:** Resolve domains for the 7,176 identity-only candidates in `discovery_candidates` (rows with `registry_id IS NOT NULL` and `domain IS NULL`).

**Date:** 2026-06-05
**Author:** AI Strategic Analysis
**Status:** Proposed

---

## 1. Current State

The `discovery_candidates` table contains 9,625 records. Of these, 2,449 have a resolved domain. The remaining 7,176 are identity-only rows — they carry business name, address, city, and a registry identifier, but no website.

### 1.1 Identity-Only Source Breakdown (estimated)

| Source | Country | Yields domain? | Approx. rows |
|--------|---------|---------------|--------------|
| `sirene_v311` | FR | Never — INSEE API does not expose websites | ~4,500–5,500 |
| `sirene` (legacy) | FR | Never | ~200–500 |
| `oem:bmw` | DE/FR/ES/NL/BE/CH | Rarely — STOLO only exposes website when dealer self-reports | ~500–800 |
| `zefix` | CH | Never — Zefix has no website field | ~300–500 |
| `osm` (no website tag) | All | When OSM contributors omit `website=*` tag | ~200–400 |

The dominant cohort is French SIRENE registrants (NAF codes 45.11Z, 45.19Z, 45.20A, 45.20B). These are legally registered car dealers with SIRET numbers, trade names, and physical addresses, but the INSEE database architecturally does not store URLs.

---

## 2. Existing Resolution Modules — Technical Analysis

### 2.1 `name_to_domain.py` — crt.sh Certificate Transparency Resolver

**Mechanism:** Queries the public PostgreSQL read replica at `crt.sh:5432/certwatch` (no authentication required). For each identity row, it tokenizes the business name, strips legal form suffixes (SAS, GMBH, BV, etc.) and generic automotive terms, selects the 2 longest distinctive tokens, then issues a full-text search + ILIKE query against the `certificate_and_identities` table filtering by country TLD.

**API/Source:** crt.sh Postgres (`postgresql://guest@crt.sh:5432/certwatch`). Free, public, no rate limit except connection concurrency. The data source is all SSL/TLS certificates ever issued — every website that has obtained a cert from any public CA appears here.

**Query pattern:**
```sql
SELECT DISTINCT lower(ci.NAME_VALUE) AS d
FROM certificate_and_identities ci
WHERE plainto_tsquery('certwatch', $1) @@ identities(ci.CERTIFICATE)
AND ci.NAME_VALUE ILIKE $2
LIMIT 1000
```

**Concurrency:** 2 simultaneous connections (configurable via `N2D_CONC`).

**Result selection:** Extracts apex domains from certificate SAN fields. Filters by country TLD (`.fr`, `.de`, `.es`, `.nl`, `.be`, `.ch`). Requires both tokens present in the apex domain. Selects shortest matching domain (tightest to business name).

**Output:** Inserts a NEW domain-ful row (`source='name2dom'`, `source_layer=5`) rather than updating the identity row. Uses `ON CONFLICT (domain, country) DO NOTHING` to avoid duplicating existing domain candidates.

**Current source filter:** Only processes `source IN ('sirene_v311', 'sirene', 'oem:bmw')`. **Does not cover `zefix` or `osm` sources.**

**Estimated resolution rate:** 15–25% of candidates with sufficiently distinctive names. French automotive businesses with names like "Automobiles Martin" will match `martinautomobiles.fr` if such a certificate exists. Generic names ("Garage du Centre") will fail because the tokens are too common. The crt.sh database coverage is excellent for active websites but misses businesses that never obtained an SSL certificate (rare in 2026 but possible for micro-dealers).

**Cost:** Zero. crt.sh is a free public service maintained by Sectigo.

**Limitations:**
- Depends on business name appearing in the registered domain name (not always the case).
- Only works with country-code TLDs; misses `.com`, `.eu`, `.net` registrations.
- crt.sh Postgres can be slow under load (90s timeout configured).
- Does not verify the resolved domain is actually a car dealer's website.

---

### 2.2 `ddg_worker.py` + `sources/ddg_resolver.py` — DuckDuckGo Web Search Resolver

**Mechanism:** Long-running worker that claims batches of identity-only rows from PG via atomic CTE (`FOR UPDATE SKIP LOCKED`). For each row, constructs a search query `"{name} {city} {country_name} {automotive_keyword}"` and POSTs to `html.duckduckgo.com/html/` — the server-rendered HTML endpoint of DuckDuckGo.

**API/Source:** DuckDuckGo HTML search. No API key. No explicit rate limit. Jitter of 2–6 seconds between queries built into the resolver. Country-specific keywords (e.g., `autohaus` for DE, `concessionnaire automobile` for FR).

**Search flow:**
1. Build localized query: `"{name} {city} {country} {car_dealer_keyword}"`
2. POST to DDG HTML endpoint with matching `Accept-Language` headers
3. Parse organic results — extract up to 10 URLs from `result__a` class anchors
4. Filter out 30+ known portal/platform domains (autoscout24, mobile.de, leboncoin, facebook, etc.)
5. Normalize the first non-portal result
6. HTTP HEAD/GET to verify the domain is alive (< 400 status code)
7. On success: `UPDATE SET domain, url, sitemap_status='pending'` (promotes the row into the sitemap resolver queue)

**Outcome routing:**
- **Resolved:** Domain is set, row enters sitemap pipeline. If domain already exists for same country → merge `external_refs` into incumbent and delete identity row.
- **Failed:** `ddg_attempts++`, `ddg_error` logged. After 5 failures, row permanently exits queue.

**Concurrency:** 5 parallel resolves per batch, batches of 25, 24-hour cooldown between retries per row.

**Estimated resolution rate:** 40–55% of candidates with city data. This is the strongest resolver because it leverages full web search rather than relying on domain-name string matching. Businesses that appear anywhere on the web — even if their domain name doesn't contain their trade name — can be found. The portal filter is critical to avoid false positives.

**Cost:** Zero. DuckDuckGo HTML endpoint is free, no API key required.

**Limitations:**
- 2–6s jitter per query → ~7,176 candidates × 4s avg = ~8 hours for a single pass at concurrency 5.
- DDG may block/throttle after sustained volume (no observed limit documented, but possible).
- Candidates without `city` field yield lower precision (country-level search is too broad).
- The HEAD/GET verification ensures liveness but does not confirm the site is actually a car dealer.

---

### 2.3 `sitemap_resolver.py` — Sitemap Probe Worker

**Role:** This module does NOT resolve identities to domains. It operates downstream — once a domain is known, it probes for sitemap availability. Included here because it is the immediate next step after DDG/crt.sh resolution.

**Mechanism:** For each `discovery_candidates` row where `domain IS NOT NULL AND sitemap_status='pending'`:
1. GET `https://{domain}/robots.txt` — extract `Sitemap:` directives
2. Probe fallback paths: `/sitemap.xml`, `/sitemap_index.xml`, `/sitemap-index.xml`, `/sitemap.xml.gz`
3. Validate: fetch first 64 KiB, check for `<urlset>` or `<sitemapindex>` root elements
4. Mark row: `found` (with `sitemap_url`), `none`, or `error`

**Concurrency:** 20 parallel probes, batches of 50, 30s idle sleep.

**Cost:** Zero. Direct HTTP to dealer websites.

**Relevance:** Every domain resolved by `name_to_domain.py` or `ddg_worker.py` is automatically queued for sitemap probing (`sitemap_status='pending'`). This converts a resolved domain into an actionable extraction target.

---

### 2.4 `sources/ct_logs.py` — Certificate Transparency Keyword Miner

**Role:** Discovery-phase tool that finds NEW domains (not identity resolution). Queries crt.sh Postgres with automotive keywords per country/TLD combination and inserts new domain-ful candidates.

**Mechanism:** Same crt.sh Postgres backend as `name_to_domain.py`, but searches by industry keyword rather than business name. 12 keywords for DE, 9 for FR, 8 for ES, 6 for NL, 5 for BE, 7 for CH.

**Relevance to identity resolution:** Indirect. CT log mining may discover domains that belong to identity-only candidates, enabling collision-merge when DDG later resolves the same domain. Running `ct_logs.py` before `ddg_worker.py` increases the probability that DDG resolution triggers a merge rather than an isolated update.

**Cost:** Zero.

---

### 2.5 Additional Supporting Modules

| Module | Relevance |
|--------|-----------|
| `dealer_classifier.py` | Classifies resolved domains (CMS, inventory URLs, tier). Runs downstream of resolution. |
| `frontier_runner.py` | Crawls classified dealers for vehicle listings. Runs downstream. |
| `head_classifier.py` | Pre-filters listing URLs by Content-Length. Downstream. |
| `repair_pass.py` | Re-fetches incomplete Meili docs. Downstream. |
| `meili_enricher.py` | Extracts vehicle data from HTML. Downstream. |
| `sources/trustpilot.py` | Mines Trustpilot `/review/{domain}` pages — yields domains directly, not identities. Potential crossref source. |
| `sources/bovag.py` | BOVAG member directory (NL) — yields domains directly with website field. |

---

## 3. Viability Assessment Against 7,176 Candidates

### 3.1 Can the existing modules be executed against all 7,176?

**`ddg_worker.py`:** Yes. The worker's claim SQL targets ALL rows where `domain IS NULL AND ddg_attempts < 5 AND name IS NOT NULL`. It is source-agnostic — every identity-only row regardless of origin enters the queue. **No code changes needed.** Simply run:
```bash
DDG_WORKER_ONESHOT=1 python -m scrapers.discovery.ddg_worker
```

**`name_to_domain.py`:** Partially. Current filter restricts to `source IN ('sirene_v311', 'sirene', 'oem:bmw')`. To cover all 7,176 candidates, the filter must be expanded to include `'zefix'` and `'osm'`. This is a one-line SQL change.

### 3.2 Resolution Rate Projection

| Resolver | Target cohort | Expected hit rate | Expected resolved |
|----------|---------------|-------------------|-------------------|
| `ddg_worker` (Phase 1) | All 7,176 with `name IS NOT NULL` | 40–55% | 2,870–3,947 |
| `name_to_domain` (Phase 2) | Remaining ~3,200–4,300 unresolved | 10–20% incremental (name must appear in domain) | 320–860 |
| `ct_logs` crossref (Phase 0, pre-seed) | Entire table | Indirect — increases DDG collision-merge rate | +100–300 net new |

**Aggregate projection:** 3,290–5,107 domains resolved out of 7,176 candidates.
**Expected resolution rate: 46–71%.**

The unresolvable ~29–54% will consist of:
- Micro-dealers with no web presence whatsoever
- Businesses with generic names that produce false-positive search results (filtered out by portal/liveness checks)
- Ceased businesses still in SIRENE/Zefix registries
- Dealers whose website is hosted on a marketplace subdomain (e.g., `dealer123.autoscout24.de`) — filtered as portal

---

## 4. Execution Plan — Zero Additional Cost

### Phase 0: Pre-seed (CT Log Keyword Sweep)
**Duration:** 30–60 minutes
**Action:** Run `ct_logs.py` to inject new domain-ful candidates from certificate data. This increases the domain pool and ensures that when DDG resolves a domain already known from CT logs, the merge path correctly consolidates provenance.

```bash
python -m scrapers.discovery.sources.ct_logs
```

**Prerequisites:** PostgreSQL running, crt.sh reachable.

### Phase 1: DDG Batch Resolution (Primary)
**Duration:** 6–12 hours (7,176 × 4s avg jitter / 5 concurrency = ~5,741s theoretical + overhead)
**Action:** Run `ddg_worker` in oneshot mode. This is the highest-yield resolver.

```bash
DDG_WORKER_ONESHOT=1 \
DDG_WORKER_BATCH=50 \
DDG_WORKER_CONCURRENCY=5 \
DDG_WORKER_MIN_INTERVAL='1 hour' \
python -m scrapers.discovery.ddg_worker
```

**Tuning notes:**
- Increasing `DDG_WORKER_CONCURRENCY` above 5 risks DDG throttling. Monitor for 429/503 responses.
- Reducing `DDG_WORKER_MIN_INTERVAL` to `'1 hour'` allows faster retries within the same session.
- Multiple runs may be needed — rows that fail on first attempt get a second chance after cooldown.

**Output:** Each resolved row gets `domain` set and `sitemap_status='pending'`, entering the sitemap pipeline automatically.

### Phase 2: crt.sh Name Resolution (Supplementary)
**Duration:** 1–3 hours
**Action:** Expand `name_to_domain.py` source filter and run against remaining unresolved candidates.

**Required code change** (line 158 of `name_to_domain.py`):
```python
# BEFORE:
AND source IN ('sirene_v311','sirene','oem:bmw')

# AFTER:
AND source IN ('sirene_v311','sirene','oem:bmw','zefix','osm')
```

Then run:
```bash
python -m scrapers.discovery.name_to_domain
```

**Note:** This resolver only targets rows still missing a domain after Phase 1.

### Phase 3: Sitemap Resolution (Downstream)
**Duration:** 1–2 hours
**Action:** Run sitemap resolver to probe all newly domain-ful candidates.

```bash
SITEMAP_RESOLVER_ONESHOT=1 python -m scrapers.discovery.sitemap_resolver
```

This converts resolved domains into actionable extraction targets by finding their sitemaps.

### Phase 4: Classification (Downstream)
**Duration:** 1–2 hours
**Action:** Run dealer classifier on new domain-ful candidates.

```bash
python -m scrapers.discovery.dealer_classifier
```

This profiles each resolved domain: CMS detection, inventory URL discovery, listing count estimation, tier assignment (T0–T3).

### Phase 5: Retry Pass
**Duration:** 6–12 hours
**Action:** Re-run DDG worker to retry candidates that failed on first pass (candidates with `ddg_attempts < 5`). Network conditions, DDG index freshness, and stochastic search ranking may yield different results.

```bash
DDG_WORKER_ONESHOT=1 python -m scrapers.discovery.ddg_worker
```

Repeat until queue is exhausted (all candidates either resolved or at `ddg_attempts >= 5`).

---

## 5. Enhancement Opportunities (Zero-Cost)

### 5.1 Expand crt.sh to `.com`/`.eu` TLDs

Current `name_to_domain.py` only checks country-code TLDs (`.fr`, `.de`, etc.). Many European car dealers register `.com` or `.eu` domains. Adding these TLDs to `_COUNTRY_TLD` mapping would increase coverage:

```python
_COUNTRY_TLD = {
    "FR": ["fr", "com", "eu"],
    "DE": ["de", "com", "eu"],
    "ES": ["es", "com", "eu"],
    "NL": ["nl", "com", "eu"],
    "BE": ["be", "com", "eu"],
    "CH": ["ch", "com", "eu"],
}
```

**Estimated incremental yield:** 5–10% of previously unresolved candidates.

### 5.2 Trustpilot Cross-Reference

`sources/trustpilot.py` already mines Trustpilot category pages where the URL structure is `/review/{domain}`. Running Trustpilot and cross-referencing by business name against unresolved identity rows could yield matches without any search engine dependency.

### 5.3 Google Maps / OSM Enrichment

Many identity-only candidates from SIRENE have lat/lng coordinates (via geocoding from address). Cross-referencing these coordinates against OSM nodes that DO have a `website` tag could resolve identities purely from spatial proximity matching.

### 5.4 Common Crawl Reverse Lookup

The `common_crawl.py` source already fetches automotive-keyword domains. A reverse approach — searching Common Crawl for pages that mention the SIRET number or exact business name — could yield the domain directly from archived web content.

### 5.5 Geocode Backfill

`geocode.py` exists in the discovery directory. For SIRENE candidates with address but no lat/lng, geocoding first and then running spatial cross-reference against OSM would increase the resolution surface.

---

## 6. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| DDG throttles sustained volume | Medium | Delays Phase 1 | Built-in jitter + cooldown. Reduce concurrency if 429s appear. |
| crt.sh Postgres unavailable | Low | Blocks Phase 2 | Phase 2 is supplementary; Phase 1 (DDG) provides primary yield. |
| False domain assignment (wrong business) | Medium | Incorrect dealer profile | DDG resolver includes liveness check + portal filter. Downstream `dealer_classifier` will detect non-automotive sites. |
| Resolved domains are parked/dead | Low | Wasted sitemap probes | Sitemap resolver handles this gracefully (marks as `error` or `none`). |
| SIRENE data staleness (closed businesses) | Medium | Resolution attempts on non-existent dealers | DDG will fail naturally (no web presence). 5-attempt limit prevents infinite retries. |

---

## 7. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Domains resolved | ≥3,500 of 7,176 (≥49%) | `SELECT COUNT(*) FROM discovery_candidates WHERE domain IS NOT NULL` delta |
| Sitemaps found | ≥40% of newly resolved domains | `SELECT COUNT(*) WHERE sitemap_status='found'` among new domain rows |
| Dealers classified T0–T2 | ≥60% of sitemap-found | `SELECT COUNT(*) FROM dealer_profile WHERE tier IN ('T0','T1','T2')` delta |
| False positive rate | <5% | Manual sample audit of 100 random resolved domains |
| Execution cost | €0 additional | No paid APIs, no proxy usage required for resolution phase |

---

## 8. Recommended Execution Order

```
ct_logs.py (30 min)
    ↓
ddg_worker.py ONESHOT (6–12 h)
    ↓
name_to_domain.py [expanded filter] (1–3 h)
    ↓
sitemap_resolver.py ONESHOT (1–2 h)
    ↓
dealer_classifier.py (1–2 h)
    ↓
ddg_worker.py retry pass (6–12 h)
    ↓
Metrics collection + manual audit sample
```

**Total estimated wall time:** 16–32 hours (can run overnight as a pipeline).
**Total cost:** €0 — all resolvers use free public APIs (crt.sh, DDG HTML, direct HTTP probes).

---

## 9. Post-Resolution Pipeline Impact

Resolving ~3,500–5,100 additional domains means:

- **Sitemap resolver queue grows by 3,500–5,100 candidates** — each with a pending sitemap probe.
- **Assuming 40% sitemap discovery rate:** 1,400–2,040 new domains with sitemaps enter the extraction pipeline.
- **Assuming T0–T2 classification for 60%:** 840–1,224 high-value dealer websites become actionable for vehicle listing extraction.
- **Conservative listing estimate (50 listings/domain avg for T1–T2):** 42,000–61,200 additional vehicle listings entering the index.

This represents a **40–60% increase in the extractable dealer surface** from the current 2,449 domain-ful candidates.
