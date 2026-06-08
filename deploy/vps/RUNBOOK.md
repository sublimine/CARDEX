# CARDEX VPS — Runbook

From a clean VPS to inventory flowing in the API, then unblocking the defended giants.

## 0. Provision
A VPS per [SIZING.md](./SIZING.md) (recommended: Hetzner CPX51, Ubuntu 22.04/24.04).
Install Docker Engine + Compose v2:
```bash
curl -fsSL https://get.docker.com | sh
```

## 1. Boot the stack (one command)
```bash
git clone --branch feature/vps-deploy https://github.com/cardex/cardex.git
bash cardex/deploy/vps/bootstrap.sh
```
First run creates `deploy/vps/.env` from the template and brings everything up. The
`bootstrap.sh` waits until the entity API is healthy and prints its URL.

What happens, in order (driven by `depends_on` conditions):
1. `postgres` boots, runs `scripts/init-pg.sql` (full schema) on first boot.
2. `pg-migrate` applies migrations 0001–0003 (source_entities, operator_alerts, index).
3. `identity-provision` mints DIRECT identities (T0/T1) + RESIDENTIAL ones from any
   `RESIDENTIAL_PROXY_<CC>` already set.
4. `entity-api`, the seam workers (delta/enrich/rich/dispatcher), the 6 country
   coordinators, and discovery all start.

## 2. Set secrets
Edit `deploy/vps/.env`: set `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, and how the API is
exposed (`ENTITY_API_BIND` / `ENTITY_API_PORT`). Re-run `bootstrap.sh` to apply.

## 3. Watch inventory flow
```bash
API=http://127.0.0.1:8088        # or your ENTITY_API_BIND:PORT (SSH-tunnel if loopback)
curl $API/v1/health
curl "$API/v1/entities?limit=10"                 # catalog grows as discovery + harvest run
curl "$API/v1/inventory?country=DE&limit=5"       # global index
# pick an entity ulid from /v1/entities, then watch its live altas/bajas:
curl "$API/v1/entities/<ulid>/delta"
curl $API/v1/alerts                               # operator alerts (drift/waf/parse)
```
The free T0/T1/T2 portals (autolina, tutti, marktplaats, gaspedaal, autotrack, …) start
filling `vehicle_index` within the first cycles — visible immediately per entity.

## 4. Unblock the defended giants (residential proxies)
The 4 blocked T1 giants and their slot:
| Portal | WAF | Slot |
|---|---|---|
| lacentrale.fr | DataDome | `RESIDENTIAL_PROXY_FR` |
| promoneuve.fr | DataDome | `RESIDENTIAL_PROXY_FR` |
| milanuncios.com | DataDome | `RESIDENTIAL_PROXY_ES` |
| nederlandmobiel.nl | Cloudflare | `RESIDENTIAL_PROXY_NL` |

Fill the slot in `.env` (`http://USER:PASS@HOST:PORT`) and re-run `bootstrap.sh`. The
identity bootstrap provisions a premium-trust RESIDENTIAL identity for that country and the
coordinator picks it automatically — the giants leave `NO_IDENTITY` and begin harvesting.
Confirm: `curl "$API/v1/entities/<giant-ulid>"` → `inventory_count` climbs.

## 5. Operate
- Logs: `docker compose -f deploy/vps/docker-compose.vps.yml logs -f scraper-fr`
- Stop: `docker compose -f deploy/vps/docker-compose.vps.yml down` (keeps volumes)
- Reset data: `… down -v` (drops pg_data, redis_data, engine_db)
- Scale Camoufox: raise `SCRAPER_MEM` / add coordinators (see SIZING.md).

---

## Validated locally vs. tested on the VPS
**Validated locally (this machine, real evidence):**
- The Python services themselves — entity API, delta_worker, remediation_dispatcher,
  enrich_worker, rich_consumer, coordinator — are the exact modules already run and proven
  this session (API live, delta in 390 ms, remediation resolved, 56 area-tests green).
- `compose config` lints clean; every service maps to a verified entry point
  (`python -m scrapers.<module>` / `uvicorn services.entity_api.app:app`).
- The residential-proxy provisioner (`scrapers/engine/identity/residential.py` +
  `scrapers.bootstrap_identities`) was run: `direct_created=18, residential_provisioned=2`
  against a temp engine.db — env→identity wiring works.
- The migrations (0001–0003) were applied to the live canonical Postgres earlier.

**Tested only on first VPS boot (cannot be done without the VPS):**
- The `docker build` of the scrapers image (Camoufox/Playwright fetch) on Linux — built
  locally never on this Windows host (Application Control blocks it); the Dockerfile is the
  repo's existing, reviewed one.
- The containerized seam wiring against the in-network canonical Redis
  (`redis://:pw@cardex-redis:6379`) — locally we used the host-reachable throwaway (:56390).
- The actual T3 (DataDome) crack once a real residential proxy is supplied — a residential
  IP is necessary but the runtime Camoufox warming still has to solve the challenge; proven
  for Akamai (mobile.de) on the stealth front, DataDome is harder and is the live unknown.
- Throughput/sizing under real concurrency — the 6.4 h/4-browser figure is the baseline;
  per-VPS numbers confirm on boot.

**Not deployed** — no VPS exists yet. This package is code+config, lint-validated, ready to `bootstrap.sh`.
