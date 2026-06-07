# PLAN — Domain resolution at scale (maximize yield)

Branch `feature/domain-resolution`. No push. UPDATE-only `domain`. Coordinate via the
native `ddg_attempts` queue (multi-session safe, `FOR UPDATE SKIP LOCKED`).

## Recon verdict (empirical, 2026-06-07)
- Pool no-web: FR 557K, DE 30.8K, CH 13K, ES 12.1K, NL 3.1K, BE 3.0K (~619K).
- Reuse existing infra: `ddg_worker.py` (queue claim + collision-merge), `ct_logs.py`
  (crt.sh), `common_crawl.py`, `ddg_resolver.py`. `ddg_attempts=0` everywhere (virgin queue).
- Vias that WORK from this IP: email-domain (free), DDG/Mojeek, PagesJaunes (FR, site in
  href), local.ch (CH, email in JSON). gelbeseiten=2-step (defer), crt.sh=slow
  (best-effort), Common Crawl=CDX has no substring host search (NOT viable — documented).
- OEM web already captured for audi/vw/hyundai; skoda/toyota/kia/bmw have none → no cross-fill.

## Build blocks (each verified before next)
1. **email-domain via** + freemail/ISP/portal exclusion set + tests.
2. **directories.py** — PagesJaunes (FR) site-href, local.ch (CH) email-in-json + tests.
3. **per-via validation** — `confirms_dealer(strict|lenient)`; email/dir lenient, search strict.
4. **worker.py** — queue-claim batch (reuse ddg_worker CTE) → multi-via candidate gen
   (email → directory → search) → validate → promote/collision-merge → mark fail. RAM-safe
   (low conc, gc, RSS watchdog, jitter). Per-via/-country stats. CLI `--countries --limit`.
5. **validate-with-limit + purge** per via per country (live, small caps); kill any FP.
6. **scale**: background runs DE/ES/CH/NL/BE → then FR. Idempotent, resumable.
7. **report**: update DOMAIN_RESOLUTION_REPORT.md — net domains by country & by via, hit
   rate, honest no_results-real vs not-attempted. Commit (no push).

## Invariants
- Nothing unvalidated persisted. Validation gate universal (per-via strictness).
- RAM-safe always: batch ≤ claim size in memory, gc between, RSS throttle, conc ≤ 4.
- Idempotent: queue cooldown + `WHERE domain IS NULL`; dup → collision-merge, not crash.
