---
name: project-docker-compose-hardening-caps
description: "CARDEX docker-compose full-vision stack — hardening cap_drop crash-loops PG/CH, and over-deleted seed scripts"
metadata: 
  node_type: memory
  type: project
  originSessionId: 48b7d33d-fe52-44fc-bef5-d21cd9abada2
---

The full-vision `docker-compose.yml` (root, project name `cardex`) shares an
`x-hardening: &hardening` anchor (`cap_drop: [ALL]` + `security_opt:
no-new-privileges:true`) across all datastores.

**Red herring:** when `cardex-pg` / `cardex-ch` crash-loop with `chmod ...
Operation not permitted` / `failed switching to 'postgres'` / `Cannot do
'setgid'`, it is NOT volume corruption — the error persists on a brand-new
empty volume. Root cause is `cap_drop: [ALL]` stripping the caps the official
postgres/clickhouse entrypoints need (start as root → chown data dir → drop to
service user via gosu/setuid). Fix = `cap_add: [CHOWN, DAC_OVERRIDE, FOWNER,
SETGID, SETUID]` (ClickHouse also needs `KILL` to stop its temp init server).
Redis/Meili survive the same hardening because they never switch users.

**Why:** deleting `cardex_pg_data`/`cardex_ch_data` (even the runbook in this
repo suggested it) wastes time and data; it only ever fixed Meili (genuine
v1.41-data-vs-v1.12-engine incompatibility).

**How to apply:** verify caps in `docker-compose.yml` before touching volumes
when a hardened official-image container crash-loops on permission errors.

Commit `5a4d59a` ("delete remaining basura") over-deleted `scripts/` files still
referenced by the compose: `seed-demo.sql`, `init-meili.sh`, `init-redis.sh`
(restored from `5a4d59a^`). `init-redis.sh` also needed `REDISCLI_AUTH` env
because redis runs with `--requirepass` and the script's `redis-cli` calls had
no `-a`. Seeds live behind `--profile seed` (pg-seed, meili-seed); `redis-init`
runs in the default profile. See [[feedback-execute-dont-ask]].
