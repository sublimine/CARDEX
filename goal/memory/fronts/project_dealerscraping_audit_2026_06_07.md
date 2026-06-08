---
name: project_dealerscraping_audit_2026_06_07
description: "GUARDIAN audit of per-dealer scraping system (frente C) — GO, security sound, remediation trigger unwired"
metadata: 
  node_type: memory
  type: project
  originSessionId: df38bd40-b67d-485b-a1cd-efc4dee5c973
---

GUARDIAN read-only audit of `feature/dealer-scraping-system` @ `72b31d5` (FF-able on main `b980f90`). Report: `GUARDIAN_REPORT_DEALERSCRAPING_2026-06-07.md`. System: per-dealer config-driven scraping reusing the seam (`scrapers/dealer_scraping/` + `configs/dealers/*.json` + scripts), additive `config.py` only.

**Verdict: GO (merge to main).** Currently FF (0/1, main ancestor); 3-way clean if other branches merge first (in-flight branches don't touch config.py). Suite **1325 green**.

**Verified [V]:** E2E re-run (dacia-meaux/nissan-epernay/mercedes-compiegne → 15 cars @limit5, vehicles 30→30 purge_restored). Config additive, seam NOT rewritten (enrich_worker/rich_consumer absent from diff; native `portal_config.load()` resolves dealer configs). **4/4 HIGH security fixes SOUND**: SSRF expand_catalogs (`is_safe_public_url` blocks private/metadata IPs + non-http schemes, re-checked at call site), path-traversal config store (`_dealer_path` resolve+is_relative_to, caught `..\..\windows`→ValueError), browser cleanup (finally in both scripts), memory-per-batch (bounded LIMIT no fetchall, E07 conc=2, gc per batch). RAM-safe confirmed.

**Yield ~3% is HONEST [V]:** sweep_random.json = 90 dealers, 3 yielders = 3.3%; 77% (69/90) had discovered=0 (extractor never reached = OSM non-car noise/unreachable), NOT extractor failure; 3 yielders 100% success; `details_no_fields` (19%, JS/XHR) openly declared as playwright_xhr backlog. OSM is 92% of the 30,389-domain census and ~half the random sample aren't car dealers. Many real dealers embed inventory via 3rd-party DMS widgets (Modix/mobile.de) → off-domain.

**REFUTED (P2, non-blocking): drift→remediation trigger NOT wired.** `remediation.py` is REAL (re-detect→regenerate version++ →revalidate, persists, honest escalation; 4 real tests) but the harvester computes `drift_ok` and NEVER calls `remediate()` — `git grep` confirms only tests invoke it. Drift DETECTION wired per-dealer; ACTION dead. Report's "auto-remediación cableada" overstates. Fix: `if not drift.ok: remediate(...)` in harvester. Also report minor: suite 1324 claimed vs 1325 actual, "36 new" vs ~41.

**Worktree topology at audit time:** main working tree on `feature/domain-resolution` (b037a07); worktrees `cardex-dealer-scraping` (72b31d5) + `cardex-discovery-scale` (e6b9fa0). domain-resolution + discovery-scale are the two sessions writing discovery_candidates. Merge order so far: fanout→e07→(dealer recommended). Continues [[project_e07_playwright]] / [[project_fanout_5countries]].
