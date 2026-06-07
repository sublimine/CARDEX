---
name: project_discoveryscale_audit_2026_06_07
description: "GUARDIAN audit of discovery-scale (barrido A) — GO, +17.3K with-web real, 8 connectors sound"
metadata: 
  node_type: memory
  type: project
  originSessionId: df38bd40-b67d-485b-a1cd-efc4dee5c973
---

GUARDIAN read-only audit of `feature/discovery-scale` @ `a2fa819` (barrido A, now closed). Report: `GUARDIAN_REPORT_DISCOVERYSCALE_2026-06-07.md`. Diverges 12/5 from main `6219527`, merge-base 6e0be32.

**Verdict: GO — 3-way merge CLEAN** (`git merge-tree` exit 0, 0 conflicts; shared `fr_recherche_entreprises.py` modified only on discovery-scale side, main untouched since base; other 7 connectors are new files). Suite **1347 green** (1274+73). Post-merge expected ~1427.

**Verified [V]:**
- **+17.294 with-web REAL:** live with_web by country DE 26676/NL 6898/FR 5293/CH 4026/ES 1747/BE 1247 = **45,887** (vs baseline 28,570 = +17,317; claim 45,864 +23 post-snapshot). From new connectors: gelbeseiten 7723, bovag 3933, agvs 2401, oem:renault/seat/dacia/vw/hyundai ~1654, osm re-fetch. Registries (recherche_entreprises 175K, zefix 9.8K, sirene 360K) expand census with domain NULL (need resolver). Real domains sampled (bovag/agvs/oem clean). **gelbeseiten FP tail ~0.4%** (28/7723 non-dealer names: opticians/audio; 75 go1a.de microsites; some name↔domain mismatch) — bovag=0, agvs=2/2401. Domains REAL not invented; quality caveat on gelbeseiten only.
- **Dedup: 0 duplicate (domain,country)** → OEM-with-web collapse vs OSM, no double-count.
- **8/8 connectors REAL-ENDPOINT** (subagent, endpoints cited): recherche_entreprises 101 depts, zefix 26 cantons, ch_agvs, nl_bovag, de_gelbeseiten, oem_locators (VW/Audi/Skoda/Toyota/Hyundai/Kia), oem_wave2 (Renault/Dacia/SEAT), osm_expanded_run. 73 tests; osm_expanded_run weakest (6 tests = env parsing only, insert-path untested).
- **Invariants SOUND:** INSERT + conditional heartbeat (`ON CONFLICT DO UPDATE SET last_seen=NOW() WHERE last_seen<NOW()-1h` — only last_seen, never data; or DO NOTHING); NO schema migration (diff has zero CREATE/ALTER TABLE, only a comment); RAM-safe (zefix CSV streamed to temp file + DictReader, Semaphore(8), throttles, pools max 4-6, no fetchall).
- **Backlog 8/8 honest:** 11880 Cloudflare+overlap→VPS, PagesJaunes 12% coverage→VPS, BE/ES Incapsula/Imperva, PSA DNS dead (wsrest.servicesgp.mpsa.com 502), Mercedes/Ford Akamai+paid-key, Fiat Java NPE, H3 discarded with data (~80-120 with-web at 18% noise = redundant).

**Census now ~685K** (FR 568K via recherche_entreprises full 175K + sirene; DE 70K; CH 17K) — free ceiling higher than the old ~460K estimate thanks to registry full-sweeps. Bottleneck remains: resolve domains of that domain-NULL census (worker.py merged) + giants anti-bot (P3 proxies).

**P2 caveats (non-blocking):** prune gelbeseiten FP tail via resolver validate.py gate; test osm_expanded_run insert-path; drain registry census with resolver worker.

**Worktree topology:** main on domain-resolution(2bd5cb5)/dealer-scraping(72b31d5)/discovery-scale(a2fa819)/p2-hardening(6219527). Merge order this session: fanout→e07→dealer→domain-res→(discovery-scale recommended); p2-hardening last (3-way). Continues [[project_domainres_audit_2026_06_07]] / [[project_fanout_5countries]].
