---
name: project_p2hardening_audit_2026_06_07
description: "GUARDIAN audit of P2-hardening — GO (3-way clean), closes 5/5 accumulated P2 items incl. 2 GUARDIAN refuted earlier"
metadata: 
  node_type: memory
  type: project
  originSessionId: df38bd40-b67d-485b-a1cd-efc4dee5c973
---

GUARDIAN read-only audit of `feature/p2-hardening` @ `d331f49` (diverges 6/1 from main `7a03433`, merge-base `6219527`). Report: `GUARDIAN_REPORT_P2_2026-06-07.md`. This branch closes the accumulated P2 caveats GUARDIAN itself flagged across the prior 5 audits — the closure loop.

**Verdict: GO — 3-way merge CLEAN** (`git merge-tree` exit 0, 0 conflicts; p2 touches harvester/validate/enrich_worker/migrate_*.sql from dealer/domain-res/P1 already in main, but discovery-scale — main's only gain since merge-base — didn't touch them → disjoint). Suite **1366 green** (run by me). Post-merge ~1432 (validate exact).

**5/5 SOUND, including the 2 GUARDIAN REFUTED earlier:**
1. **Remediation trigger NOW WIRED** [V]: real call-site `harvester.py:259-264` `if not drift.ok and remediator is not None: await remediator(domain,country)`; injectable callback (no import cycle, no recursion); production caller `run_dealer_scraping.py` via make_remediator; tests fire-on-drift (`remediator.calls==[(...)]`) / no-fire-on-healthy. **My prior "dead code" refutation CLOSED.**
2. **Anti-FP word-boundary** [V deterministic]: `name_tokens("Artcar")=['artcar']`; `\bartcar\b` in 'bmwartcarcollection' = False (vs naive substring True) → FP won't recur. **CAVEAT (P2): historical Artcar row STILL in discovery_candidates (forward-only fix); re-run revalidate.py to purge it.**
3. **Worker tests** [V]: SKIP-LOCKED = REAL PG (throwaway `_p2_claim_probe`, 3 concurrent claimers, disjoint+exactly-once range(1,61)); collision-merge = faithful FAKE (logic-level, honestly labeled in docstring).
4. **Reclaim cap/DLQ + migration** [V]: `MAX_DELIVERIES=5` via XPENDING times_delivered → DLQ (xadd+xack, leaves PEL) kills poison-livelock; A6 per-message try/except (parity with A7, A6 now exceeds A7 which has no cap). Migration wrapped `BEGIN;`(L19)…`COMMIT;`(L82) with RAISE inside → self-contained abort-safety (no longer needs --single-transaction). **My P1 findings (no cap, SQL not self-enforcing) CLOSED.** Caveat: migration rollback test proves the pattern (synthetic throwaway script), not the real file end-to-end (correctly never run against prod).
5. **Docs honest** [V]: 3 docs annotated with dated point-in-time corrections (preserve original numbers + add current state + commit anchor); only the genuinely-stale "1 failed gate" corrected; historical mission-report counts not rewritten. No falsification.

**Closes the full GUARDIAN consolidation series — ALL MERGED.** main progression this session (all local, NOT pushed): 6e084a5(origin) → 830bf5d(p0-canon FF) → 6e0be32(fanout FF) → b980f90(e07 3way) → 72b31d5(dealer FF) → 6219527(domain-res 3way) → 7a03433(discovery-scale 3way) → **1ca158a(p2 3way, suite 1439 green)**. All 8 fronts (P0+P1+fanout+E07+dealer+domain-res+discovery-scale+P2) now in `main` @ `1ca158a`. **origin/main still 6e084a5 — NOT pushed (owner decision, pending).** Artcar FP purged (id=1138 → domain NULL, requeued) via targeted UPDATE mirroring revalidate._PURGE (1 row, no twin collision). Every merge done in a detached temp worktree with update-ref CAS (main never moved until suite green) — main never broken across the whole series. Continues [[project_dealerscraping_audit_2026_06_07]] / [[project_domainres_audit_2026_06_07]] / [[project_discoveryscale_audit_2026_06_07]].
