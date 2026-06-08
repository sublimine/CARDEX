---
name: project_fanout_audit_2026_06_07
description: "GUARDIAN audit of fan-out 5-countries branch — honest pattern-proof, FF-merge ready, tiny yield"
metadata: 
  node_type: memory
  type: project
  originSessionId: df38bd40-b67d-485b-a1cd-efc4dee5c973
---

GUARDIAN read-only audit of `feature/fanout-5countries` @ `6e0be32` (FF on main `a980b3f`). Report: `GUARDIAN_REPORT_FANOUT_2026-06-07.md`. Single additive commit (8 files, +987/−0), no core/seam changes.

**Verdict: GO, FF-merge ready.** All 5 items HONEST/SOUND, nothing refuted, suite **1274 green**, does NOT touch inventory (`vehicles`/`vehicle_index`) → safe vs the parallel E07 session.

**Verified [V]:** discovery_candidates 460,378→460,930 (Δ552 exact). New orthogonal sources: `recherche_entreprises`=518 (FR, **0 registry_id overlap with sirene** → genuinely new), `openmercantil`=17 (ES), `zefix_bs`=17 (CH, **Basel-Stadt only**). 100% correct country, real names (not fabricated), all domain-NULL (registries → need A2/OEM resolution to be scrapeable). DE (`de_offeneregister`) + BE (`be_kbo`) = **0 rows, blocked honestly**: run() returns 0 + WARNING `BLOCKED:` before any insert (DE SQL API 502, BE CSV needs registration); tests use an insert-trap pool proving no fabrication. dealer_terms = per-country/lang dict (BE bilingual, CH trilingual); bare "auto" EXCLUDED (verified by execution — was a false-positive source on CH Zefix). Seam untouched (git diff: enrich_worker/rich_consumer/coordinator/generic_extractor/indexer all unmodified).

**It's a pattern-proof, NOT coverage:** only 552 real dealers added, 2/5 countries blocked, all domain-NULL. Gap vs national census stays ~97-100% per country.

**Merge-sequencing note (important):** `feature/fanout-5countries` AND `feature/e07-playwright-xhr` both branch from main `a980b3f`. After FF-merging one, the other is no longer pure FF (needs rebase). Recommended order: merge fan-out first (additive, doesn't touch inventory), then rebase + re-audit E07. As of this audit the working tree is checked out on `feature/e07-playwright-xhr` (parallel session developing E07 inventory extractor — the P0/P1 gap for JS-SPA portals incl. CH which lacks JSON-LD).

P2 caveats: DE/BE need alternate source; CH expand Basel-Stadt→26 cantons; ES tighten CNAE (4519 includes trucks/campers, low volume 17); resolve domains for the 552 domain-NULL rows. Refines [[project_nl_vertical]] (country-agnostic fan-out claim now partially proven: discovery fan-out IS config-shaped per source, but each country still needs a hand-written connector). Continues [[project_p1_hardening]].
