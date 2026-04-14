# UX & Data Quality Audit Report — B2B Buyer Simulation
**Date:** 2026-04-14  
**Scope:** B2B buyer use-case simulation, merged data coherence across families,
NLG quality vs. competitors, critical B2B fields, filter/search UX requirements  
**Reference:** `planning/01_MASTER_BRIEF/00_MASTER_BRIEF.md`, `planning/05_QUALITY_PIPELINE/`,
`planning/03_DISCOVERY_SYSTEM/KNOWLEDGE_GRAPH_SCHEMA.md`  
**Severity scale:** CRITICAL > HIGH > MEDIUM > LOW

---

## Executive Summary

A B2B fleet buyer using the current system would be unable to complete a
basic supplier qualification workflow. The KG captures existence (dealer is
real, has a business registry entry) but lacks all commercially decisive
fields: OEM certification, fleet inventory count, opening hours, GDPR contact,
and meaningful trust signals. Data quality issues from multi-family merging
(conflicting names, inconsistent address formats, no entity resolution) further
degrade usability. NLG is not implemented at all. The gap vs. mobile.de's B2B
dealer profile page is wider than a single development phase can close.

---

## B2B Buyer Persona Simulation

**Persona:** Logistics manager at a 500-vehicle fleet operator in Germany.
**Task:** Identify 5 authorized BMW dealer partners in the Munich radius with:
- Official BMW fleet certification
- ≥50 used B2B vehicles in stock
- Fleet invoice terms (net 30, VAT invoice)
- German-language contact
- GDPR-compliant data processing agreement available

**Current KG capability for this query:**

| Need | KG Field | Populated by | Status |
|------|----------|-------------|--------|
| BMW certification | `dealer_oem_affiliation` | Family H (absent) | ABSENT |
| Stock count | `vehicle_record` count | Phase 3 extraction | NOT STARTED |
| Fleet invoice terms | No field exists in schema | Not designed | ABSENT |
| Language support | Not in schema | Not designed | ABSENT |
| GDPR contact | Not in schema | Not designed | ABSENT |
| Active operation signal | `dealer_entity.status` = UNVERIFIED | All families | ALL UNVERIFIED |
| Geographic proximity | `dealer_location.lat/lon` | Family B (OSM) | PARTIAL (OSM only) |
| Phone number | `dealer_location.phone` | Family F only | PARTIAL |
| Website | `dealer_web_presence.url_root` | Families C, F | PARTIAL |

**Verdict:** The B2B buyer query cannot be answered. 0 of 5 critical filter
fields are populated for the majority of dealers. The current KG supports only
"does this dealer exist?" — not "is this dealer suitable for my fleet?"

---

## CRITICAL

### U-C1 — `dealer_oem_affiliation` table is empty; Family H (OEM networks) not implemented
**Finding:**  
OEM brand certification is the primary B2B buying signal. A buyer qualifying
fleet partners needs to distinguish:
- **Authorized dealer** (sales network): new vehicles, warranty service
- **Authorized service center**: repairs only, may not have sales
- **Certified used vehicle dealer** (BMW Premium Selection, Mercedes-Benz Certified, etc.)
- **Multi-brand independent**: no OEM relationship

The `dealer_oem_affiliation` table exists in the schema but contains zero rows.
Family H (OEM dealer networks) is the only planned source for this data. Family H
is unimplemented with no planned sprint.

Without this data, CARDEX cannot differentiate a BMW dealer from a generic used
car lot. This is a fundamental B2B positioning gap vs. competitors:
- **mobile.de B2B:** Shows OEM badge, certification level, authorized brands
- **AutoScout24:** Shows OEM network membership
- **CARDEX current:** Shows only name and address (if scraped), confidence 0.35-0.80

**Fix:** Prioritize Family H implementation before Phase 3. OEM network scraping
is the highest-ROI single deliverable for B2B buyer trust.

---

### U-C2 — All dealer entities have `status = UNVERIFIED`; no graduation mechanism
**Finding:**  
```go
entity := &kg.DealerEntity{
    // ...
    Status: kg.StatusUnverified,  // every family sets this
}
```

Every family (A through F) sets `Status = StatusUnverified` on every upsert.
There is no mechanism to graduate a dealer to `StatusActive`. The `status`
field in `dealer_entity` is meaningless — all ~N dealers in the KG are
`UNVERIFIED` regardless of how many independent sources confirm them.

**Impact:**
1. A B2B buyer filter for "active dealers only" returns zero results (no active
   dealers exist)
2. The `confidence_score` is the only operability signal but is also problematic
   (see U-H2)
3. Closed/dissolved dealers cannot be distinguished from active ones

**Fix:** Define the graduation policy: e.g., `status = ACTIVE` when
`confidence_score > 0.5 AND found by at least 2 independent families AND not
found in any closure registry (Family M or O)`. Implement a post-cycle status
upgrade job.

---

### U-C3 — No vehicle inventory data exists; buyer cannot assess dealer stock
**Finding:**  
Phase 3 (extraction pipeline) is blocked on Phase 2. No vehicle records exist
in `vehicle_record`. A B2B buyer's first question — "how many suitable vehicles
does this dealer currently have?" — cannot be answered.

Fleet buyers specifically need:
- Count of vehicles matching criteria (make, type, age, mileage band)
- Price distribution (net EUR without VAT)
- Availability window (estimated days in stock, not a product feature but
  derivable from listing age)

These require Phase 3 extraction + Phase 4 quality validation. The gap is
structural and timeline-dependent, not a code bug. But it means the current
system cannot be used for any real B2B evaluation scenario.

---

## HIGH

### U-H1 — Phone numbers populated for ≤25% of dealers
**Finding:**  
Only Families F (mobile.de and La Centrale) populate `dealer_location.phone`.
Family A (business registries) doesn't provide phone numbers. Family B (OSM)
sometimes has contact information but the `overpass.go` implementation doesn't
extract it. Family C (web cartography) discovers domains but not contact details.

For a B2B buyer, phone numbers are essential for:
- Pre-qualification calls before site visits
- Fleet account manager contacts
- Emergency parts/service contacts

**Coverage estimate:** Family F covers DE (mobile.de) and FR (La Centrale),
contributing ~30% of discovered dealers. The remaining 70% (from A, B, C) have
no phone number.

**Fix:** Phase 3 extraction pipeline (E01-E07) should prioritize phone
extraction from dealer websites. Add `contact_phone` field to the contact
extraction target fields for each E-strategy.

---

### U-H2 — `confidence_score` uses additive sum; does not reflect data quality
**Finding:**  
A dealer with `confidence_score = 0.80` (confirmed by A + B + C + F) and a
dealer with `confidence_score = 0.35` (confirmed by A only) are displayed
with different scores, but both have `status = UNVERIFIED`, `phone = NULL`,
`dealer_oem_affiliation = empty`, and no vehicle records.

The confidence score measures "how many sources confirmed existence" not "how
complete and accurate is this dealer's data." For a B2B buyer, data completeness
matters more than source count. A dealer with 1 source but phone + website +
OEM certification is more actionable than a dealer with 4 sources but no
contact information.

**Recommendation:** Introduce a separate `completeness_score` that measures
field coverage (phone/website/address/oem_affiliation populated), distinct
from the discovery confidence score.

---

### U-H3 — Address formats are inconsistent across families
**Finding:**  
Each family uses its own address parsing:
- Family A (business registries): structured address from official API
  (`address_line1`, `postal_code`, `city` from registry fields)
- Family B (OSM): structured address from `addr:street`, `addr:housenumber`,
  `addr:city` OSM tags
- Family F mobile.de: `parseGermanAddress("Musterstraße 1, 12345 Berlin")` splits
  on last comma
- Family F La Centrale: `parseFrenchAddress("12 rue de la Paix, 75001 Paris")` splits
  on last comma

These parsers produce different field distributions. An OSM-sourced German address
might have `address_line1 = "Musterstraße 1"`, `postal_code = "12345"`, `city = "Berlin"`.
A mobile.de-sourced address might have `address_line1 = "Musterstraße 1"`,
`postal_code = "12345"`, `city = "Berlin"` — or might have `address_line1 = "Musterstraße 1, 12345 Berlin"`,
`postal_code = NULL`, `city = NULL` if the comma-split heuristic fails.

For a buyer filtering by city or postal code, inconsistent NULL patterns mean
queries return incomplete results.

**Fix:** Standardize address normalization through a single `normalizeAddress(country, raw)`
function that applies country-specific rules. Run a post-processing pass to
normalize existing rows.

---

### U-H4 — NLG is not implemented; dealer descriptions are absent
**Finding:**  
Phase 4 (quality pipeline) specifies V19: NLG description generation using
Llama 3 8B Q4_K_M in 6 languages. This is Phase 4 scope, which hasn't started.

In the current KG, `dealer_entity` has no description field. There is no
"About this dealer" content for any entry. A competitive comparison:

| Field | mobile.de dealer page | CARDEX current |
|-------|----------------------|----------------|
| Dealer description | ✓ (self-authored) | ABSENT |
| Specializations | ✓ (used, certified, fleet) | ABSENT |
| Opening hours | ✓ | ABSENT |
| Fleet contact | ✓ (separate B2B tab) | ABSENT |
| OEM badges | ✓ | ABSENT |
| Review score | ✓ (Google/Trustpilot) | ABSENT |
| Vehicle count | ✓ (live count) | ABSENT |
| NLG description (6 languages) | N/A (not their model) | NOT IMPLEMENTED |

The NLG specification in `05_QUALITY_PIPELINE/NLG_SPEC.md` is sound. The
competitive gap is accurately scoped as Phase 4 work. However, the gap is larger
than a "quality improvement" — it is a prerequisite for the product being
minimally usable.

---

### U-H5 — `dealer_web_presence.extraction_strategy` is never populated
**Finding:**  
`dealer_web_presence.extraction_strategy TEXT` column is never set by any
Family A-F sub-technique. The Phase 3 extraction cascade (E01-E12) needs this
column pre-populated with a strategy hint (e.g., "E02" for WordPress dealers
detected by Family D CMS fingerprinting).

Without a pre-assigned strategy, Phase 3 must run the full cascade (E01 → E12)
for every dealer, starting from E01 and falling through until one succeeds.
With 50k dealers, this means 600k+ extraction attempts just for the first cascade.

If Family D (CMS fingerprinting) were implemented and populated
`extraction_strategy = "E02"` for WordPress dealers, Phase 3 could skip E01
and go directly to E02 for ~35% of dealers (WordPress's market share in
dealer websites).

---

## MEDIUM

### U-M1 — `opening_hours_json` is always NULL
**Finding:**  
The `dealer_location.opening_hours_json` field is designed to store JSON-encoded
opening hours per OSM's `opening_hours` tag format. Family B (OSM) is the only
family that could populate this but the `overpass.go` implementation doesn't
extract it from Overpass results.

For a B2B buyer, calling a dealer or planning a visit requires knowing opening
hours. This is a standard field on every competitor platform.

---

### U-M2 — `dealer_social_profile` is empty for all dealers
**Finding:**  
`dealer_social_profile` stores Google Maps ratings, Facebook pages, LinkedIn
profiles, etc. No family populates this table. Family L (social profiles) is
unimplemented. Google review scores are a key B2B trust signal; a dealer with
500 reviews and 4.3/5.0 rating is significantly more trustworthy than an
anonymous business registry entry.

---

### U-M3 — `discovered_by_families` conflict clause erases multi-source attribution
**Finding:** (See also schema audit S-M5, discovery strategy audit D-M3)  
When a dealer is discovered by Family A and later by Family F, the
`dealer_web_presence.discovered_by_families` field ends up as `"F"` (the
last writer wins), not `"A,F"`. A B2B buyer viewing a dealer's source attribution
would see only the most recent discovery family.

This also means the cross-fertilization matrix is unmeasurable: "how many dealers
were confirmed by both A and F?" cannot be answered from `dealer_web_presence`.

---

### U-M4 — Confidence score ceiling of 0.80 with current families
**Finding:**  
With A(0.35) + B(0.15) + C(0.10) + F(0.20) = 0.80 maximum, no dealer can
reach confidence 1.0 until additional families are implemented. From a buyer's
perspective, a confidence score of 0.80 and a score of 0.35 look very different
but both map to `status = UNVERIFIED`. The `confidence_score` number is visible
in the schema but there's no defined buyer-facing interpretation:

> "What does 0.80 mean? Highly likely to be a real dealer? More reliable
> data? Lower risk of fraud?"

Without defined buyer-facing semantics, the confidence score is an internal
metric that shouldn't be exposed directly in the B2B UI.

---

### U-M5 — No GDPR contact / DPO information field
**Finding:**  
B2B buyers processing personal data through dealer relationships (fleet
customer data, driver records) need to know if the dealer has a GDPR DPO
and how to contact them. EU GDPR Article 37 requires DPO appointment for
certain processing activities. No field exists for DPO name, email, or
registration.

This is a compliance requirement for the "compliance-sensitive B2B buyers"
segment mentioned in the market brief.

---

### U-M6 — Multilingual dealer data not in schema
**Finding:**  
CARDEX targets 6 countries with 5 languages (DE, FR, ES, NL + EN). Dealer names
and addresses are stored in a single canonical form — whatever the scraper
captured first. A German dealer's name "Autohaus Schmidt GmbH" might be captured
as "Autohaus Schmidt" (mobile.de), "Schmidt GmbH" (OffeneRegister), or
"Autohaus Schmidt GmbH" (official) depending on which family runs first.

There is no multi-locale name normalization, no localized city/address storage,
and no language metadata on dealer names. The NLG spec generates descriptions
in 6 languages but the underlying dealer data is in a single-language form.

---

## LOW

### U-L1 — No fleet-specific data model
**Finding:**  
The vehicle schema (`vehicle_record`) was designed for B2C vehicle listings
(price, VIN, mileage, color, fuel type). B2B fleet-specific fields are absent:
- Fleet/wholesale price tier (vs. retail price)
- Minimum order quantity
- Remaining warranty / extended warranty options
- Fleet delivery lead time
- VAT invoice eligibility
- Lease/finance options for fleets

These could be added as columns in `vehicle_record` or as a
`vehicle_fleet_terms` child table. Without them, the Phase 3 extraction
pipeline has no place to store fleet-specific extracted data even if it finds it.

---

### U-L2 — No search ranking model
**Finding:**  
There is no score or ranking mechanism for dealer search results. A B2B buyer
searching "BMW dealer Munich" would receive results sorted by... what? The
`confidence_score` is the only available signal, which measures source count
not commercial relevance.

A minimal ranking model for Phase 7 (launch) needs:
- Geographic proximity to query location
- OEM certification match
- Confidence score
- Data completeness score
- Recent activity signal (last_confirmed_at recency)

None of these are combined into a search ranking score.

---

### U-L3 — `fingerprint_sha256` in `vehicle_record` is not defined
**Finding:**  
`vehicle_record.fingerprint_sha256 TEXT` is in the schema but no documentation
defines what it's a fingerprint of. Is it a hash of (VIN + dealer_id + source_url)?
A perceptual hash of the primary image? A hash of the entire record for
change detection? Without definition, Phase 3 cannot implement it consistently.

---

## Summary: B2B Buyer Journey vs. Current State

| Journey Step | Required Fields | Current State | Gap |
|-------------|----------------|--------------|-----|
| Discover dealers | Name, country | ✓ Available | — |
| Filter by brand | OEM affiliation | ABSENT (Family H) | Critical |
| Filter by location | Address, coordinates | PARTIAL (OSM, A) | Medium |
| Assess trust | Reviews, certification | ABSENT | Critical |
| Contact dealer | Phone, email | PARTIAL (Family F) | High |
| Check inventory | Vehicle count/types | ABSENT (Phase 3) | Critical |
| Verify business | VAT number, registry | PARTIAL (Family A) | Medium |
| Compliance check | GDPR contact | ABSENT | Medium |
| Get price quote | Fleet pricing | ABSENT | Critical |
| NLG description | 6-language summary | NOT IMPLEMENTED | High |
