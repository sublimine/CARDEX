---
name: project_tier1_verify_2026_06_07
description: "GUARDIAN tier-1 governance audit — \"100% coverage\" = count-reconciliation, NOT harvested (0 rows in store)"
metadata: 
  node_type: memory
  type: project
  originSessionId: df38bd40-b67d-485b-a1cd-efc4dee5c973
---

GUARDIAN governance verify of supervisor's tier-1 claims (rama `feature/stealth-camoufox` @ `6a0b632`, Camoufox anti-bot work). Report: `GUARDIAN_TIER1_VERIFY.md`. Independent count.

**Core distinction GUARDIAN drew (durable):** the supervisor's "mobile.de 100% / leboncoin 100% / coches.net 95.4%" is **COUNT-RECONCILIATION / enumeration feasibility**, NOT harvested coverage. **`vehicle_index` (audited store) = 0 rows for all three** [V my count]; work_queue all `pending`; no `configs/portals/` for any tier-1 (only the prior 3 NL/CH); `seam_writer.py` is real (INSERT vehicle_index ON CONFLICT + XADD enrich_pending + DELETE/GONE) but has NOT flowed to the store.

**Per portal [V my recompute on stealth/evidence/*.json]:**
- **mobile.de:** root (numResultsTotal vc=Car, no filters) = 1,586,022; MY Σ of 178 makes = 1,586,026 → **count reconciles 100.00%** (delta +4 trivial). BUT: `mobilede_enum_snapshot.json` = only **20 URLs dumped**; deepdive shows VW make_count 258,494 vs sum_over_years 239,016 = **92.5%** → year-faceting leaves 7.5% on big makes that exceed the pagination CAP (need recursive year×km… not proven to close). Akamai blocks re-fetch from this IP, so I verified the INTERNAL reconciliation (Σ=root), not the live root. Verdict: count 100% ✅ / harvested coverage NO.
- **leboncoin.fr:** "~900K" = `listing_url_estimate` = 18 sitemaps × ~50K **extrapolated from one leaf's 50K sample** — NOT a counted Σ; snapshot = 60 URLs. Verdict: NOT verified.
- **coches.net:** `tier1_progress.json` = {total_oficial 249963, cobertura 238411, pct 95.38, makes_done 98/121, "worker vivo"} → 95.38% confirmed but IN-PROGRESS (23 of 121 makes pending). Verdict: not 100%, not ≥99%, 0 harvested.

**Mobile.de live universe correction (from RESULTS.md):** real total ~1.586M (the earlier "4.4M" was an assumption, corrected by the supervisor). Facet axes: ms=make, fr=year, ml=km (price doesn't filter).

**Verdict: nothing marked green.** Count-reconciliation verified only for mobile.de; all three have harvested coverage = 0 and unversioned configs. Supervisor's own board already says "pendiente de verificación" (aligned). To go green: prove recursive sub-faceting closes >CAP makes to ≥99%, flow delta via seam_writer to vehicle_index and count real rows, version configs/portals/. Tier-1 harvest at scale still needs proxies+storage (P3). Continues [[project_audit_2026_06_06]] (giants at 0 by proxies) — still true at the STORE level.
