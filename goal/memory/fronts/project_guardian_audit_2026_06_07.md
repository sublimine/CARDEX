---
name: project-guardian-audit-2026-06-07
description: GUARDIAN consolidation audit verdict — validated skeleton (0% product data) but FF-merge-ready
metadata: 
  node_type: memory
  type: project
  originSessionId: df38bd40-b67d-485b-a1cd-efc4dee5c973
---

GUARDIAN audit of `feature/p0-rewiring-canon` (now @ `830bf5d`, not `49e082c` — the env auto-commit hook committed the resilience scaffolding mid-session). Report: `GUARDIAN_REPORT_2026-06-06.md`. Conducted 2026-06-06/07.

**Core verdict [VERIFIED against live PG/Redis/CH]: the system is a VALIDATED SKELETON, not a populated product.**
- `vehicle_index` = 508,339 URLs but **precio/titulo/anio/km/thumbnail = 100% NULL on every row** (bare pointers, sitemap-sourced).
- `vehicles` (L2, the product) = **30 rows, all `SEED_DEMO`** — 0 real scraped vehicles ever durably persisted. `vehicle_events`: 0 ENRICHED.
- The enrich seam (A6 `enrich_worker` + A7 `rich_consumer`) is **REAL and E2E-proven** (I re-ran it: 30→32, purged) but **DORMANT in prod**: on live redis `stream:enrich_pending` doesn't exist, `ingestion_raw` last-delivered `0-0`. E2E always used throwaway redis :56390.
- ClickHouse: 19 tables, **0 rows** (dead RAM cost).
- Discovery: 460,378 candidates, 6.2% with domain, **100% `sitemap_status=pending`** (dealer→inventory path never run). RDW=300 of ~24,700 capacity.
- Coverage: 26.7% of the 20 active portals' inventory; **51 of 71 configured portals = ZERO coverage** (mobile.de, AutoScout24×6, leboncoin… all anti-bot/proxy-gated, P3).

**Seam stability leaks found (P1 before running at scale):** (1) no XAUTOCLAIM reclaim → transient/error stranded in PEL forever; (2) `fx_eur` needs `FX_RATE_CHF` or CH (41.8%) rich rows get NULL eur; (3) `vehicle_index.moneda` default EUR mislabels CH; (4) autovacuum never ran (planner blind, estimates rows=1); (5) `vehicle_events` unpartitioned/no ts-index (unbounded). H3 refuted: NO PG triggers block UPDATE (the ADR-0006 hook is git/Go).

**Resilience (D7):** config-store + drift_gate BUILT and tested but **UNWIRED** — no production caller; only `EMPTY_SUSPECT` (harvest==0) fires live. The commit itself admits "execution migration is P1".

**Consolidation recommendation: GO — fast-forward merge to main.** Branch is 0-behind/7-ahead, suite **1246 green**, additive, no regressions, and fixes a data-corruption bug (P0-1 harvest-0 wipe) that main still has. P1 punch-list (§9 of report) is mandatory BEFORE activating the seam at scale, not before merge. Merge NOT executed — left for orchestrator. Block0 second-checkout hazard (`C:\Users\elias\CARDEX`@42dec67 with unique uncommitted frontend) still live — owner decision, NOT deleted.

Refines [[project_p0_execution_state]], [[project_nl_vertical]], [[project_storage_reality]]. Confirms [[project_discovery_free_source_ceiling]] (460K free ceiling) and [[project_audit_2026_06_06]] (giants at 0 by proxies).
