<!-- Working plan for the scraping-engine completion. Operational doc, not architecture. -->
# Scraping Engine — Implementation Plan

Source of truth for design: `docs/SCRAPING_ENGINE.md`. This file tracks execution only.

## Scope boundary (honesty)
Deterministic, unit-testable logic is implemented and verified in-session:
identity generation/coherence/aging, SQLite state store, tier router + circuit
breaker, proxy pool/health, partition strategy, delta/quality/dlq pipeline,
intelligence (pricing/anomaly/waf/poison/schema), Prometheus metrics, scheduler.

Parts requiring live external resources (real Decodo/Oxylabs auth, Camoufox
runtime, hyper-sdk-go _abck generation, live portal HTML) are implemented against
documented interfaces with conservative, real logic and clear seams — never faked
as "working" end-to-end without the live dependency.

## Blocks
1. Foundation — `db.py` WAL + DDL (7 tables)            [tests]
2. Identity — profile/store/coherence/aging             [tests]
3. Router — domain_map/classifier/escalator/circuit     [tests]
4. Proxy — pool/tiers/affinity/health                    [tests]
5. Antidetect + Session — tls/sensor/warming/intent/state/conditioning
6. Monitoring — metrics/softblock/alerts                 [tests]
7. Portals — base.run() + 6-country AS24 (verified pattern) + T1 portals
8. Pipeline — delta/enrich/quality/dlq                   [tests]
9. Intelligence — pricing/anomaly/waf/poison/schema      [tests]
10. Coordinator + Scheduler

## Verification
`pytest scrapers/tests/ -q` green after each block. No regression to
`common/autoscout24.py` + `common/indexer.py` (real, untouched contract).
