# Discovery Strategy Audit Report — Families A–O
**Date:** 2026-04-14  
**Scope:** Implemented families (A, B, C, F) + unimplemented families (D, E, G–O),
base weight defensibility, cross-overlap, saturation protocol  
**Reference:** `planning/03_DISCOVERY_SYSTEM/families/`, `kg/confidence.go`,
`planning/02_MARKET_INTELLIGENCE/`  
**Severity scale:** CRITICAL > HIGH > MEDIUM > LOW

---

## Executive Summary

4 of 15 planned discovery families are implemented. The implemented families
(A, B, C, F) cover the highest-confidence and most accessible sources. However,
11 families remain entirely absent, leaving significant discovery blind spots.
The confidence model is conceptually sound but has three concrete flaws:
weights are not empirically calibrated, the clamping to 1.0 masks source
disagreement, and the "Bayesian combination" promised for Sprint 3 was never
built. F.2 and F.3 (AutoScout24, Autocasion) — covering the dominant EU
marketplace — are deferred to Sprint 6.

---

## CRITICAL

### D-C1 — 11 of 15 families are completely unimplemented
**Finding:**  
| Family | Name | Status |
|--------|------|--------|
| A | Registros mercantiles | Implemented (Sprint 2) |
| B | Geocartografía (OSM + Wikidata) | Implemented (Sprint 3) |
| C | Cartografía web (Wayback + CT + DNS) | Implemented (Sprint 4) |
| **D** | CMS Fingerprinting | **ABSENT** |
| **E** | DMS hosted APIs | **ABSENT** |
| F | Aggregator directories (partial) | Sprint 5 (F.1, F.4 only) |
| **G** | Asociaciones sectoriales | **ABSENT** |
| **H** | Redes OEM | **ABSENT** |
| **I** | Redes de inspección | **ABSENT** |
| **J** | Sub-jurisdicciones | **ABSENT** |
| **K** | Buscadores alternativos | **ABSENT** |
| **L** | Plataformas sociales | **ABSENT** |
| **M** | Señales fiscales | **ABSENT** |
| **N** | Infra intelligence | **ABSENT** |
| **O** | Prensa históricos | **ABSENT** |

Phase 2 exit criterion CS-2-1 requires "15/15 families with ≥80% test coverage."
Current state: **4/15 (26.7%)**.

Maximum achievable `confidence_score` with current implementation:
A(0.35) + B(0.15) + C(0.10) + F(0.20) = **0.80**.

Missing high-value families by estimated confidence weight:
- G (sector associations, e.g., ZDK, CNPA): +0.15 estimated — authoritative membership lists
- H (OEM dealer networks): +0.25 estimated — manufacturer-sourced, highest reliability
- L (social profiles, Google Maps): +0.10 estimated — signals active operation

A dealer confirmed by only A+B has confidence 0.50 — **below the minimum threshold
for active listing** in many B2B contexts. Without G and H, the confidence
ceiling for the majority of dealers will remain stuck at 0.50.

---

### D-C2 — F.2 (AutoScout24) and F.3 (Autocasion) absent from highest-traffic markets
**Finding:**  
AutoScout24 is the #1 used car platform in 6 of 6 target countries by traffic
(Similarweb 2025 data). Its dealer directory (`/haendler/` DE, `/garages/` FR,
etc.) covers virtually all professional dealers in the target market. Deferring
F.2 to Sprint 6 means:

- German dealers who exclusively use AutoScout24 but not mobile.de are missed
  by Family F (estimated 15-20% of the market)
- French dealers on AutoScout24 who don't list on La Centrale are missed
- ES/BE/NL/CH have no Family F coverage at all (F.2 is the only planned source
  for those countries)

The deferral reason (SPA requiring Playwright) is legitimate and the robots.txt
analysis is correct. However, the strategic impact of F.2's absence should be
explicitly acknowledged in the Phase 2 scope: **Family F provides partial
coverage for DE and FR only**, with zero aggregator-directory coverage for
ES/BE/NL/CH.

Autocasion (F.3, ES) sits behind Cloudflare WARP challenge. Attempting to
bypass this would violate Principle R1. The correct path is to contact
Autocasion directly for a structured data export or partnership — this option
is not documented in the planning spec.

---

## HIGH

### D-H1 — Base weights are internal judgments without empirical calibration
**Finding:**  
```go
// confidence.go
"A": 0.35, // Registros mercantiles — legal-fiscal, high reliability
"B": 0.15, // Geocartografía — medium reliability
"C": 0.10, // Cartografía web — low-medium reliability
"F": 0.20, // Aggregator dealer directories — marketplace-verified
```

These weights are presented as "high/medium/low reliability" assessments but
have no empirical grounding:

1. **Family A false-positive rate is unquantified.** The NACE/SBI code filter
   (45.x — wholesale/retail motor vehicles) casts a wide net. It includes:
   parts manufacturers (NACE 45.31), motorcycle dealers (45.40), and recently
   dissolved companies that haven't been deregistered. Estimated false-positive
   rate: 20–40% of A records are not active B2B car dealers.

2. **Family F (0.20) vs Family A (0.35) weight ordering is debatable.** A
   dealer listed in mobile.de's directory has passed mobile.de's commercial
   onboarding (identity verification, business legitimacy check). This is more
   reliable than a BORME announcement which includes new registrations that may
   never trade. For established active dealers, F should arguably outweigh A.

3. **No cross-validation has been run.** The weights were not computed from
   a ground-truth dataset. "Correct" weight ratios require a labeled dataset
   of confirmed active dealers to measure each family's precision and recall.

**Fix:** After 3 months of data collection, perform a calibration run against a
ground-truth set (e.g., KBA registered dealers in DE, RDW in NL). Adjust
weights empirically. Document the calibration methodology.

---

### D-H2 — ComputeConfidence is addition, not Bayesian combination
**Finding:**  
```go
// confidence.go:22-37
func ComputeConfidence(confirmedByFamilies []string) float64 {
    // ... sums base weights, clamps to 1.0
}
```

The comment says "Sprint 3 will replace with Bayesian combination that accounts
for source dependency." Sprint 5 has been delivered with no change to this
function. Additive weights have two problems:

1. **Source dependency is ignored.** A dealer in mobile.de (F) and in an
   OffeneRegister record (A) is likely the same entity because OffeneRegister
   sources data that was also used to create a mobile.de account. They are not
   independent evidence. Adding 0.35 + 0.20 = 0.55 overstates confidence.

2. **Score clamping masks disagreement.** If 6 families all agree the dealer
   exists, score = 1.0. If 5 families agree and 1 says the dealer is dissolved,
   score is still clamped to 1.0 — the disagreement is invisible.

**Fix:** Implement at minimum: `confidence = 1 - product(1 - w_i) for i in families`.
This Noisy-OR model gives partial independence. True Bayesian would require
per-pair covariance terms (complex; defer to Phase 4). Document that current
implementation is Sprint 1 approximation.

---

### D-H3 — No deduplication beyond exact identifier match
**Finding:**  
The KG deduplication strategy relies on identical `(identifier_type, identifier_value)`
pairs in `dealer_identifier`. Two separate entities that are physically the
same dealer are treated as distinct if they have different identifiers.

Real-world scenario: "BMW München GmbH" in OffeneRegister (SIREN: DE-123456)
and "BMW-Niederlassung München" in mobile.de (slug: bmw-niederlassung-munchen-78901)
are the same physical dealership but will become two separate `dealer_entity` rows.

The confidence score for each will be 0.35 (A only) and 0.20 (F only) when
they should merge to 0.55. More importantly, two entries for the same dealer
in the B2B buyer UI would show duplicate listings.

The architecture spec describes an entity resolution module but it is not
implemented. No fuzzy name matching or address geomatching exists.

---

### D-H4 — Saturation protocol is not implemented
**Finding:**  
`planning/03_DISCOVERY_SYSTEM/SATURATION_PROTOCOL.md` defines four saturation
levels with the key criterion: "3 consecutive cycles with zero new dealers =
saturated." The code has no:

- Cycle counter per family+country
- Zero-new-in-N-cycles detection
- Saturation state persisted in the DB
- Log/metric signal when a family reaches saturation

`main.go` runs exactly one cycle and either exits (DISCOVERY_ONE_SHOT=true) or
blocks waiting for SIGTERM. There is no scheduler for recurring cycles, no
comparison to previous cycle results, and no saturation check.

**Fix:** Add `discovery_cycle` table tracking `(family, country, cycle_num, new_entities)`.
Add saturation check in `main.go` daemon loop: if last 3 cycles all have
`new_entities = 0`, set `saturation_status = SATURATED` and reduce cycle frequency.

---

## MEDIUM

### D-M1 — Family C's `RunKeywordScan` is implemented but never called
**Finding:**  
`crtsh.go` implements `RunKeywordScan(ctx, pattern)` for proactive domain
discovery. This is the "proactive" mode: query crt.sh with patterns like
`%.autohaus.de` to find dealers whose domains contain automotive keywords,
creating new `dealer_entity` rows for previously-unknown dealers.

`familia_c/family.go` only calls `RunEnumerationForCountry` (the "enrichment"
mode that operates on existing KG entries). The proactive keyword scan mode
is dead code at the family orchestration level.

**Impact:** Family C only enriches known dealers. It never discovers new dealers
independently. Its actual discovery contribution is zero — it only adds subdomains
to already-known entities.

**Fix:** Define a keyword list per country (e.g., `["autohaus", "concessionnaire",
"autodealer"]`) and call `RunKeywordScan` in `FamilyC.Run` to discover dealers
not yet in the KG.

---

### D-M2 — OSM/Wikidata coverage gaps not quantified
**Finding:**  
Family B (Overpass + Wikidata) has coverage that varies wildly by country:
- DE: High OSM coverage (large active contributor community)
- NL: Very high OSM coverage (NL has the most detailed OSM in the world)
- BE: Moderate OSM coverage
- FR: Low-moderate OSM coverage (less mapping activity outside Paris)
- ES: Low OSM coverage for dealers
- CH: Low OSM coverage

No coverage calibration has been performed against the official denominators
in `02_MARKET_INTELLIGENCE/01_MARKET_CENSUS.md`. Family B's 0.15 weight is
applied uniformly regardless of country-specific coverage gaps.

---

### D-M3 — `discovered_by_families` accumulation has no dedup logic
**Finding:**  
```go
// webpresence.go:19-21
ON CONFLICT(domain) DO UPDATE SET
  discovered_by_families = excluded.discovered_by_families
```

If a domain is first discovered by Family C ("C") and then re-encountered by
Family F ("F"), the conflict clause sets `discovered_by_families = "F"`,
overwriting "C". The multi-family attribution is lost. A dealer that has been
independently validated by 3 families will show `discovered_by_families = "X"`
where X is the last family to touch it.

This bug means the cross-fertilization matrix (CROSS_FERTILIZATION.md) is
unmeasurable from the `dealer_web_presence` table.

---

### D-M4 — Rate limit table shared between KvK (A.NL.1) and Hackertarget (C.4)
**Finding:**  
The `rate_limit_state` table schema was created by hackertarget.go but the
original comment says it is "shared with the KvK sub-technique." Looking at
`nl_kvk/kvk.go`, it also uses a `rate_limit_state` table. If hackertarget runs
BEFORE kvk in a given cycle, the table exists. If kvk runs first (or if
hackertarget is skipped), the table may not exist and kvk will fail.

This is an undocumented boot-order dependency between two sub-techniques in
different families.

**Fix:** Each sub-technique that uses `rate_limit_state` must call
`ensureRateLimitTable` (or better, move the table to a migration — see S-C1).

---

## LOW

### D-L1 — No automated keyword generation for CT log scans
**Finding:**  
The keyword list for `crtsh.RunKeywordScan` is not defined anywhere. The
implementation is ready but the inputs (keywords per country × automotive
vocabulary) have not been researched or documented. Without a keyword corpus,
Family C's proactive mode cannot be activated.

---

### D-L2 — `BaseWeights` for families D–E, G–O are absent
**Finding:**  
```go
// confidence.go:13-14
// D–E, G–O: registered when implemented
```
Placeholder comment. When these families are implemented, their base weights
must be set. The current sum ceiling of 0.80 means a dealer confirmed by all
4 implemented families has confidence 0.80 — already high. Adding weights for
11 more families without adjusting existing weights would push sums above 1.0
for any dealer found by 3+ families (clamped to 1.0, hiding the true
multi-source richness).

**Recommendation:** Switch to the Noisy-OR model (see D-H2) before registering
additional weights, to avoid the cliff where score == 1.0 becomes meaningless.

---

### D-L3 — No country-specific NACE code filtering documented in Family A code
**Finding:**  
The planning docs specify filtering on NACE/SBI code 45.x (motor vehicle retail
and wholesale). The BORME, KBO, and KvK sub-techniques are supposed to filter
entities by industry code. Whether each sub-technique correctly applies this
filter requires individual code review (not done in this audit pass). A failure
to filter would ingest all businesses in a country, not just dealers.

---

## Summary Table

| Family | Status | Key Risk |
|--------|--------|----------|
| A | Implemented | 20-40% false-positive rate unquantified |
| B | Implemented | Coverage not calibrated vs. official denominators |
| C | Implemented | Proactive scan mode never called; enrichment only |
| D | Absent | CMS fingerprinting = high-precision source (WordPress dealers) |
| E | Absent | DMS APIs = highest-quality vehicle data source |
| F | Partial (F.1+F.4) | AutoScout24 (F.2) absent; ES/BE/NL/CH have zero F coverage |
| G | Absent | Sector associations = authoritative membership validation |
| H | Absent | OEM networks = highest-confidence dealer confirmation signal |
| I | Absent | Inspection networks = active operation signal |
| J | Absent | City/regional registries = additional coverage |
| K | Absent | Alternative search engines = long-tail discovery |
| L | Absent | Social profiles = activity signal + review data |
| M | Absent | Fiscal signals = VAT registration cross-check |
| N | Absent | TLS/BGP intelligence = independent domain-to-dealer mapping |
| O | Absent | Press/historical = closed dealer detection signal |
