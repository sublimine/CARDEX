# Execution Realism Audit Report — Roadmap vs. Reality
**Date:** 2026-04-14  
**Scope:** Phase 2 exit criteria (CS-2-x), Phase 3-5 blockers, sprint velocity,
timeline defensibility  
**Reference:** `planning/07_ROADMAP/`, `planning/02_SUCCESS_CRITERIA.md`,
`planning/07_ROADMAP/DEFINITION_OF_DONE.md`  
**Severity scale:** CRITICAL > HIGH > MEDIUM > LOW

---

## Executive Summary

Phase 2 cannot be formally closed. Of the six CS-2-x exit criteria, at least
four are currently UNMET. The underlying causes are: 11 of 15 families are
unimplemented (structural), the AddLocation dedup bug means the KG has dirty
data from cycle 2 onward (data), and the saturation protocol is not implemented
(protocol). Phase 3 and Phase 4 are fully blocked on Phase 2 completion. At
the current sprint velocity (1-2 families per sprint), reaching Phase 3 entry
requires approximately 6-10 additional sprints.

---

## CRITICAL

### E-C1 — CS-2-1 UNMET: 4/15 families implemented (target: 15/15)
**Finding:**  
```
CS-2-1: 15/15 discovery families with ≥80% test coverage, measured by:
  SELECT COUNT(*) FROM family_status WHERE tests_passing >= 0.80;
```

Current state: A ✓, B ✓, C ✓, F (partial: F.1+F.4 only) ≈ 0.5. Families
D, E, G, H, I, J, K, L, M, N, O: absent.

Implementing 11 remaining families is a minimum 11-sprint effort at current
velocity (1 family per sprint). Some families are significantly more complex
than A/B/C/F:

- **Family H (OEM networks):** Requires scraping 6 manufacturer portals
  (BMW/VW/Daimler/Stellantis/Renault/Toyota) in 6 countries × 6 brands = 36
  individual source implementations
- **Family D (CMS fingerprinting):** Requires HTTP probing + fingerprint
  database + Playwright for JavaScript-rendered sites
- **Family E (DMS APIs):** Requires business development contact with DMS
  vendors (Autoproff, DealerSocket, CDK); cannot be fully automated

**True estimate for CS-2-1:** 6-18 months from 2026-04-14 (high uncertainty
on D, E, H).

---

### E-C2 — CS-2-2 PARTIAL: ≥3 independent sources for ≥80% of NL dealers
**Finding:**  
```
CS-2-2: SELECT COUNT(*) / (SELECT COUNT(*) FROM dealer_entity WHERE country_code = 'NL')
  FROM (
    SELECT dealer_id, COUNT(DISTINCT family) as fam_count
    FROM discovery_record WHERE country_code = 'NL'
    GROUP BY dealer_id HAVING fam_count >= 3
  );
  Target: ≥ 0.80
```

For NL, current active families: A (KvK — A.NL.1), B (OSM + Wikidata — 2
sub-techniques = 1 family), C (web cartography — enrichment only).

That is **A + B + C = 3 families**. The criterion is borderline satisfiable
only if "sources" means sub-techniques (A.NL.1 + B.1 + B.2 = 3), not families.

Critical problem: **Family C for NL will discover almost nothing.** C.2 (Wayback),
C.3 (crt.sh), and C.4 (Hackertarget) all operate on *existing* `dealer_web_presence`
entries. If Dutch dealers don't yet have web presences in the KG (possible, since
A.NL.1 doesn't populate web presences — only identifiers and locations), Family C
has nothing to enumerate. CS-2-2 for NL depends on the execution order and
whether A.NL.1 populates `dealer_web_presence`.

Furthermore: **Family F has zero NL coverage** (F.1 = DE only, F.4 = FR only,
F.2 and F.3 deferred). The 4th source for NL dealers does not exist.

**Assessment:** CS-2-2 for NL is BORDERLINE at best, UNMET at worst. NL was
chosen as the pilot country specifically because RDW provides a ground-truth
denominator. Without at least 3 genuinely independent families contributing
to NL, the pilot cannot validate the multi-source confidence model.

---

### E-C3 — Data integrity violation: AddLocation dedup bug invalidates CS-2-6
**Finding:**  
```
CS-2-6: No duplicate dealer entities (verified by identity check across families)
```

The `AddLocation` dedup bug (code audit C-1, schema audit S-C2) means that
every discovery cycle creates additional `dealer_location` rows for each dealer.
A dealer discovered in cycle 1 and re-encountered in cycle 2 has 2 location rows
with identical data. CS-2-6 cannot be verified clean while this bug exists.

This bug affects all currently implemented families (A, B, C, F) since all call
`graph.AddLocation`. Every cycle since Sprint 1 has been accumulating duplicate
location rows. The KG is currently dirty if any test runs have been executed
against a persistent database.

**Fix:** Must be resolved before any Phase 2 exit criterion verification. Requires:
1. Schema migration adding UNIQUE constraint on `(dealer_id, address_line1, country_code)`
2. Code fix in `AddLocation` to use `ON CONFLICT DO UPDATE`
3. Data cleanup SQL: `DELETE FROM dealer_location WHERE location_id NOT IN (SELECT MIN(location_id) FROM dealer_location GROUP BY dealer_id, address_line1)`

---

## HIGH

### E-H1 — CS-4-2 (error_rate < 0.5%) is unmeasurable with current metrics
**Finding:**  
```
CS-4-2: error_rate < 0.5% on 30-day rolling window
  Measured by: rate(cardex_quality_errors_total[30d]) / rate(cardex_quality_processed_total[30d])
```

There is no `cardex_quality_errors_total` or `cardex_quality_processed_total`
metric. The discovery service exports `cardex_discovery_dealers_total` and
`cardex_discovery_subtechnique_requests_total`, neither of which tracks
extraction or quality errors.

Phase 4 (quality pipeline) is not yet built, so this metric set is Phase 4
scope. However, the success criterion text cites "30-day rolling window" which
requires a running system for at least 30 days before the criterion can be
evaluated. This means Phase 4 entry requires Phase 2+3 to be complete AND
running stably for ≥30 days before Phase 4 exit can be assessed.

**Timeline implication:** Phase 4 exit evaluation cannot start until at least
30 days after Phase 3 deployment. This is an undocumented lead time.

---

### E-H2 — "20-minute freshness HOT" SLA is mathematically impossible with current architecture
**Finding:**  
From `planning/02_SUCCESS_CRITERIA.md`:
> "Freshness SLA: HOT tier ≤ 20 minutes — vehicle data refreshed within 20
> minutes of a price or status change at the source."

The discovery service runs a complete 6-country cycle which at 1 req/3s for
50k dealers takes **42+ hours**. Even if parallelized to 6 concurrent country
workers, a single country cycle takes 7+ hours. A 20-minute freshness SLA
requires near-real-time webhooks or push notifications from source platforms —
none of which are implemented or planned.

The 20-minute SLA applies to the *extraction pipeline* (Phase 3), not discovery.
But the planning docs conflate freshness for discovery and for vehicle listings.
For vehicle prices (the HOT tier), 20 minutes is plausible only with:
- Platform webhooks (mobile.de/AutoScout24 partner API push events) — not planned
- Frequent sub-cycle re-extractions of changed listings — requires change detection infrastructure

The current architecture doesn't have a mechanism to detect which listings
changed since the last cycle. Full re-crawl at every cycle is the only
implemented strategy.

**Assessment:** 20-minute HOT freshness SLA is **unreachable** without platform
partnership or aggressive near-real-time polling (which would violate rate limits
for >99% of sources). Recommend revising SLA to "24-hour WARM" for Phase 3 MVP,
with HOT tier explicitly gated on platform webhook agreements.

---

### E-H3 — Sprint velocity is 1-2 families per sprint; 11 remaining families = 6-11 more sprints minimum
**Finding:**  
Sprint history (reconstructed from commit messages):

| Sprint | Deliverable | Complexity |
|--------|-------------|-----------|
| 1 | KG schema + migration framework | MEDIUM |
| 2 | Family A (6 sub-techniques: FR/DE/ES/NL/BE/CH) | HIGH |
| 3 | Family B (2 sub-techniques: OSM + Wikidata) | MEDIUM |
| 4 | Family C (3 sub-techniques: Wayback/crt.sh/DNS) | MEDIUM |
| 5 | Family F partial (2 sub-techniques: mobile.de/La Centrale) | MEDIUM |

Average: ~2.5 sub-techniques per sprint. Remaining work:

- D (CMS fingerprinting): 3-4 sub-techniques, requires Playwright
- E (DMS APIs): 5-6 sub-techniques, requires business development
- F.2+F.3 (Sprint 6 planned): 2 sub-techniques, requires Playwright
- G (sector associations): 5-6 per country, likely static HTML
- H (OEM networks): 36 combinations (6 brands × 6 countries), HIGH complexity
- I (inspection networks): 3-4 sub-techniques
- J (sub-jurisdictions): 5-6 sub-techniques
- K (alt search engines): 3 sub-techniques
- L (social profiles): 4-5 sub-techniques
- M (fiscal signals): 4-5 sub-techniques, overlaps with Family A
- N (infra intelligence): 3-4 sub-techniques
- O (press/historical): 2-3 sub-techniques

Estimated sub-techniques remaining: ~60. At 2.5/sprint: **24 more sprints**.
At 2 weeks per sprint: **48 weeks (almost 1 year)** to reach CS-2-1.

This estimate assumes no rework (which is unrealistic given the bugs found in
this audit). A more realistic estimate with 20% rework overhead: **14-18 months**.

---

### E-H4 — Phase 3 and Phase 4 are blocked on Phase 2 completion
**Finding:**  
The roadmap dependency graph (`07_ROADMAP/DEPENDENCIES_GRAPH.md`) states:
```
P2 → P3 → P4 → P6 → P7 → P8
```
Phase 3 (extraction pipeline) requires the knowledge graph from Phase 2 to
contain a representative set of dealers with populated `dealer_web_presence`
rows. The cascade extractor (E01-E12) needs URLs to extract from.

With only 4/15 families implemented, the KG contains:
- Full coverage for business-registry dealers (Family A)
- OSM/Wikidata geocoded dealers (Family B)  
- Domain-enriched dealers (Family C, enrichment only)
- DE and FR aggregator-directory dealers (Family F, partial)

Missing: dealers visible only in platforms (AutoScout24, leboncoin, etc.),
OEM-network dealers, inspection-certified dealers, social-media-only dealers,
and any country other than DE/FR for aggregator data.

Phase 3 extractions against this partial KG will produce a biased sample.
The extraction pipeline's performance metrics (CS-3-1 through CS-3-7) will
appear worse than reality because the KG underrepresents long-tail dealers
who are harder to extract from.

**Recommendation:** Explicitly define a "minimum viable Phase 2" scope —
e.g., "A, B, C, F-complete (with F.2), plus G (sector associations)" — as the
minimum Phase 2 state before Phase 3 can begin. Do not wait for all 15 families.

---

## MEDIUM

### E-M1 — No sprint tracking document; velocity is estimated not measured
**Finding:**  
No `planning/07_ROADMAP/SPRINT_LOG.md` or equivalent exists. Sprint boundaries,
story points, actuals vs. estimates, and retrospective notes are absent. The
velocity estimate in this report is reconstructed from commit history, which
is an unreliable proxy (no distinction between research, re-work, and fresh
implementation).

Without formal velocity tracking, the roadmap is not a plan — it is a wish list.

---

### E-M2 — CS-2-3 (health > 95%) has an ambiguous measurement definition
**Finding:**  
```
CS-2-3: Service health > 95% measured by cardex_discovery_health_check_status
```

`cardex_discovery_health_check_status` is set reactively by family runners —
1 if the cycle completed without errors, 0 if there were errors. This gauge
is reset on each cycle. For a service that runs once per day, a single failed
cycle sets the gauge to 0 for 24 hours, creating a 100% unhealthy reading
even though the previous 29 cycles were successful.

The 95% threshold implies a time-series measurement, not a point-in-time gauge.
A proper health metric would be:
```
sum_over_time(cardex_discovery_health_check_status[30d]) / count_over_time(...[30d])
```
But `HealthCheck()` is never called in production (see architecture audit A-M5),
making this metric effectively unmeasured.

---

### E-M3 — Phase 5 infrastructure cannot start until code is deployable
**Finding:**  
Phase 5 (infrastructure provisioning) exit criterion CS-5-1 requires "7 days
running without manual intervention." Without a Dockerfile, systemd unit, or
deployment scripts, Phase 5 cannot be attempted. Historically, infrastructure
work (CI/CD, monitoring, backup) has been scoped as a single sprint but the
discovery codebase has grown to 41 Go files with dependencies that may not
build cleanly in a minimal container environment.

---

### E-M4 — Definition of Done criteria (D-1 through D-10) not verifiable
**Finding:**  
`planning/07_ROADMAP/DEFINITION_OF_DONE.md` defines 10 MVP gates. None are
currently verifiable:

| Gate | Verifiable? | Blocker |
|------|------------|---------|
| D-1 (6 countries, 90 days, coverage ≥threshold) | No | Phase 2-6 incomplete |
| D-2 (KG auditable vs. denominators) | No | Only 4/15 families |
| D-3 (error rate < 0.3% for 60 days) | No | No error rate metric |
| D-4 (NPS ≥ T_NPS for 3 months) | No | No users yet |
| D-5 (0 open legal incidents) | No | No legal audit done |
| D-6 (CI/CD, no manual interventions, 30 days) | No | No CI/CD exists |
| D-7 (runbook tested, 2 simulations) | No | No runbook exists |
| D-8 (6 Grafana dashboards with data) | No | No dashboards exist |
| D-9 (legal audit, 0 BLOCKING) | No | No audit done |
| D-10 (scaling path documented, triggers monitored) | Partial | Scaling path documented, not monitored |

**Assessment:** Definition of Done is ~3-5 years away from being verifiable
at current velocity. The criteria are correctly defined but the resource
allocation (single developer, 1 sprint per family) suggests this is a
multi-year project.

---

## LOW

### E-L1 — "No absolute dates" roadmap principle creates scope creep risk
**Finding:**  
The roadmap explicitly rejects absolute dates: "No absolute dates — only
quantitative exit criteria." This principle is sound for quality gates but
makes external stakeholder communication impossible. Without dates, there is
no mechanism to detect if the project is "on track" vs. "indefinitely stalled."

A minimal complement: track sprint start dates and publish a burn-down chart
of remaining families vs. calendar time. The data exists in commit history.

---

### E-L2 — Phase 6 (country rollout) blocks before NL pilot is fully validated
**Finding:**  
Phase 6 rolls out 6 countries sequentially starting with NL (pilot). The NL
pilot requires CS-2-2 (≥3 sources for ≥80% of NL dealers) to be satisfied.
As noted in E-C2, this criterion is borderline. Rolling out DE and FR before
NL is fully validated would skip the most measurable validation step (RDW
ground truth for NL) and undermine the quality-first principle.

---

## Summary: Phase 2 Exit Criteria Status

| Criterion | Status | Blocker |
|-----------|--------|---------|
| CS-2-1: 15/15 families ≥80% coverage | UNMET | 4/15 implemented |
| CS-2-2: ≥3 sources for ≥80% of NL dealers | BORDERLINE | Family F has no NL coverage |
| CS-2-3: Health > 95% | UNMEASURABLE | HealthCheck not called in production |
| CS-2-4: Coverage ≥ threshold vs. RDW | UNMEASURABLE | RDW comparison not implemented |
| CS-2-5: Saturation protocol operational | UNMET | Not implemented |
| CS-2-6: No duplicates | UNMET | AddLocation dedup bug |
