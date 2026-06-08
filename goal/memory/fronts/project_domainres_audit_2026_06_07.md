---
name: project_domainres_audit_2026_06_07
description: "GUARDIAN audit of domain-resolution PART II — GO (3-way clean), anti-FP root fix sound, attribution honest"
metadata: 
  node_type: memory
  type: project
  originSessionId: df38bd40-b67d-485b-a1cd-efc4dee5c973
---

GUARDIAN read-only audit of `feature/domain-resolution` @ `2bd5cb5` (diverges 1/8 from main `72b31d5`, merge-base b980f90). Report: `GUARDIAN_REPORT_DOMAINRES_2026-06-07.md`. New module `scrapers/discovery/domain_resolution/` (8 commits, disjoint from dealer).

**Verdict: GO — 3-way merge CLEAN** (`git merge-tree` exit 0, 0 conflicts; domain_resolution/ disjoint from dealer_scraping/+config.py). Suite **1313 green**. Post-merge expected ~1349.

**Verified [V]:**
- **Anti-FP root fix SOUND:** `_text` strips script/style/noscript/svg/comments THEN all tags (attribute values can't leak → original CSS/JS "auto" FP cause closed); 2-tier signal (≥1 STRONG or ≥2 distinct WEAK, single "auto" can't pass); non-dealer title guard (fahrschule/museum/rental/airport, accent-normalized). Residual FP narrow & documented: `_NON_DEALER_RE` not exhaustive across 6 langs (missing NL rijschool, IT scuola guida, parts/body shops); widest door = generic-name dealer → name_tokens empty → city+auto fallback (a same-city carrosserie passes; carrosserie is STRONG, not in non-dealer list).
- **Empirical precision ~92% honest:** sampled 30 of ~104 resolved_via rows → ~26-27 real car dealers, residual = vehicle-adjacent (`Fendt→mcwit.ch`, `Premium-Cars→voyages-stevic.ch`) + 1 clear residual FP `Artcar→bmwartcarcollection.com` (art collection, via the generic-name door).
- **revalidate.py SOUND:** real UPDATE-only purge (domain=NULL, strips resolved_via, re-queues), reuses live gate, network-blip guard (no purge on transport fail); the 6 incident FPs (boucherie/swiss-optik/anwaltskanzlei/fahrschule/saurermuseum/gva) = 0 rows = purged.
- **worker.py SOUND:** atomic `FOR UPDATE SKIP LOCKED`+bump in one stmt (coordinates with barrido A), UPDATE-only (0 INSERT/fetchall), resumable (give-up MAX=5, _MIN_INTERVAL defer), collision-merge, RAM-bound (batch 40, sem 3, gc, RSS watchdog).
- **5/5 wired paths REAL-extract:** PagesJaunes/local.ch/GelbeSeiten-2step/DDG-Mojeek(curl_cffi impersonate=chrome confirmed)/email(freemail guard). ES paginasamarillas honest stub. CC CDX infeasibility SOUND (URL-prefix index, no substring name lookup — structural).
- **Attribution HONEST [V]:** 104-108 rows with external_refs.resolved_via (CH 102/BE 1/FR 1, grew from ~64); resolver claims ONLY these tagged, NOT the country with_web jump (DE→22K = barrido A; 0 DE/ES/NL resolved_via rows confirms).

**P2 caveats (non-blocking):** (1) extend _NON_DEALER_RE 6-lang + parts/body, harden generic-name fallback; (2) **worker queue-claim/collision-merge layer UNTESTED** (29 tests cover pure core only — gap on the concurrency-prone part); (3) doc stale (report says 19 tests/1303; actual 29/1313; "gelbeseiten deferred" Part-I prose contradicted by wired code); (4) DDG 1-IP throttle ceiling → directories are the robust path.

**Throughput honest:** ~1 dealer/s, draining 5 countries (~62K) is ~15-18h grind, FR (547K) days. Engine left running, resumable via ddg_attempts queue. Continues [[project_domain_resolution_runtime]]. Merge order: fanout→e07→dealer→(domain-res recommended); discovery-scale (barrido A) still active. Refines [[project_discovery_free_source_ceiling]] (DDG works via curl_cffi impersonate, not blocked as old memory said).
