---
name: project-discovery-scraping-runtime
description: "How to actually run CARDEX discovery + scraping on the feature/docker-hardening branch (PG-backed, not the SQLite-only MVP in CONTEXT_FOR_AI.md)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 56c8b1ee-32a9-42dc-8d5d-abad91498fd1
---

On branch `feature/docker-hardening` the stack evolved past `CONTEXT_FOR_AI.md` (dated 2026-04-15, which says PG/CH/Redis/Meili are NOT implemented). Reality observed 2026-06-05: full Docker infra runs healthy (cardex-pg, cardex-ch, cardex-redis, cardex-meili, grafana, prometheus, web, api) and the Python scrapers are PG-backed. Code wins over the doc here. See [[project-docker-compose-hardening-caps]].

**Network**: only PG is host-exposed (`127.0.0.1:5432`). Redis/CH/Meili have NO host ports — reachable only inside the docker `data` network. `.env` is written for in-docker hostnames (`@postgres:5432`, `redis://redis:6379`), so running scrapers FROM THE HOST requires overriding `DATABASE_URL=postgres://cardex:<REDACTED-dev-password>@localhost:5432/cardex`. PG/Redis password = `<REDACTED-dev-password>`.

**Discovery orchestrator** (`python -m scrapers.discovery.orchestrator`): WORKS from host (PG-only, no Redis/proxies). Fan-out → upsert into `discovery_candidates` (schema + the two partial unique indexes `ux_disc_cand_domain_country` / `ux_disc_cand_identity` already exist — NO migration needed). Sources: oem_bmw (~607, reliable), osm/Overpass (~1500 CH, often fails endpoints per-country, fail-soft), sirene FR (rate-limited 429), common_crawl (404 on CC-MAIN-2026-12 snapshot), zefix/portal (0). Run gave ~2000+ real candidates.

**Coordinator** (`python -m scrapers.coordinator`): bootstrap first with `python -m scrapers.cli.bootstrap --seed-queue` (creates SQLite `scrapers/engine.db` v2, seeds 71 portals into PG `portal_cadence`, ensures `vehicle_index`/`vehicle_events`, enqueues 71 jobs into the SQLite `work_queue` — note work_queue is SQLite, NOT PG). work_queue is SQLite, NOT PG. Set `prometheus_port=0` when running ad-hoc (host 9090 is taken by the prometheus container). The sink needs Redis (enrich-stream xadd); host redis is NOT published on 6379 — spin a throwaway (`docker run -d --rm -p 56390:6379 redis/redis-stack-server:7.4.0-v1`) and pass `REDIS_URL=redis://127.0.0.1:56390`. The ephemeral `cardex-api-redis` on host 56379 fails the redis-py handshake (EINVAL) — don't use it.

**T0/T1 NOW SCRAPE DIRECT (no proxy) — fixed 2026-06-05.** Prior blocker (every job → `no_identity` because all proxy tiers needed Decodo/Oxylabs creds, which V6 prohibits) is resolved. `scrapers/cli/bootstrap.py` now calls `ensure_direct_identities` (`scrapers/engine/identity/direct.py`): 3 active+warmed `ProxyTier.DIRECT` identities per country (18 total), `proxy_ip=""` so `tls.make_session` connects direct with UA rotation only. `proxy/tiers.py` `allows_direct`/`requires_proxy`: T0/T1 accept direct, T2/T3 still require proxy. `store.pick_for_portal(require_proxy=...)` excludes direct for T2/T3 → those stay `no_identity` (correct — no proxy budget). Direct rate limits live in `base.py` (`_DIRECT_MIN_INTERVAL_S`): 1 req/s T0, 0.5 req/s T1. Reproduce end-to-end: `python -m scrapers.cli.verify_direct_live` (bounded). Verified live 2026-06-05: marktplaats.nl(T0)+autotrack.nl(T1) → `done`, 60+60 real vehicles in PG `vehicle_index`; mobile.de(T2)+leboncoin.fr(T3) → `pending`/`no_identity`/+1800s backoff. All 5 probed T1 portals (autotrack/largus/motor/gaspedaal/paruvendu) return real listings via direct curl_cffi.
