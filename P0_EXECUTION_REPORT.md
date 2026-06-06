# P0 — EXECUTION REPORT

**Fecha:** 2026-06-06 · **Rama:** `feature/p0-rewiring` (NO `main`) · **Repo:** `C:\Users\elias\projects\cardex`
**Alcance:** Bloque 0 (hazard git) + fase P0 del `BLUEPRINT_CARDEX.md` (recablear lo roto).
**Disciplina:** trabajo en rama dedicada, validar-con-límite-y-purgar, suite verde, evidencia real.

> Cada afirmación es `[VERIFICADO]` (salida de comando citada) o `[ASUMIDO]` (declarado).
> Nada inventado. Lo no probado se marca. La terminal fue banco de pruebas: todo lo
> poblado para validar se purgó (PG queda en su estado de partida).

---

## 0. Resumen ejecutivo

| Ítem | Estado | Criterio de "hecho" | Resultado |
|---|---|---|---|
| **Bloque 0** git hazard | ✅ HECHO | diagnóstico + protección, dueño decide | `BLOCK0_GIT_HAZARD.md` + bundle de rescate |
| **P0-1** harvest-0 detector | ✅ HECHO | 0 portales `done`@0 | `EMPTY_SUSPECT` + 12 reseteados |
| **P0-2** cardex-api | ✅ HECHO | healthy, /healthz 200, /market-price responde | 200 con datos reales |
| **P0-3** enrich_worker (seam) | ✅ HECHO | `vehicles` crece desde NL real | 30→33 E2E, purgado |
| **P0-4** entity resolution | 🟡 PARCIAL (con plan) | entity_matches con pares | capa VIN hecha+verificada; fuzzy V21 → P1 |
| Suite de tests | ✅ VERDE | 1188 baseline + nuevos | **1232 passed, 0 failed** |

**Estado de la cadena tras P0:** el seam roto L1→L2 está tendido y **probado E2E vivo**
(`enrich_pending`→A6→`ingestion_raw`→A7→`vehicles`→`meili_sync`), la API sirve datos,
la señal de cobertura ya no se corrompe con harvest-0, y `entity_matches` se puebla con
un resolver determinista real. Lo de pago (proxies) queda en backlog (P3), fuera de alcance.

**Nota de procedencia:** Bloque 0 y P0-3 fueron iniciados por una corrida previa (commit
`527086b`, rama `feature/p0-rewiring`); esta sesión los **re-verificó de forma independiente**
y completó P0-1, P0-2, P0-4 y el cierre de calidad. Donde re-verifiqué, lo indico.

---

## 1. Estado de partida [VERIFICADO contra runtime vivo]

```
docker exec cardex-pg psql → vehicles=30, entities=0, entity_matches=0,
  vin_history_cache=0, vehicle_index=508339, vehicle_events=539259, discovery_candidates=460078
docker ps → cardex-{pg,ch,meili,redis,grafana,prometheus,web} healthy;
  cardex-api = Restarting (crash-loop)
find scrapers -name enrich_worker* → (al inicio histórico: ausente)
```
Coincide exactamente con el blueprint y el audit. La media-cadena (discovery→index de
punteros) funciona; se rompe en el salto puntero→vehículo rico.

---

## 2. BLOQUE 0 — Hazard git (proteger + documentar; NO borrar/mergear)

**Diagnóstico verificado** (detalle en `BLOCK0_GIT_HAZARD.md`):
- Segundo checkout `C:\Users\elias\CARDEX` = `main @ 42dec67`, **ancestro** de `6e084a5`
  (`merge-base = 42dec67`; `rev-list --left-right --count 6e084a5...42dec67 = 68  0`).
  → 68 commits por detrás, **0 commits únicos**: NO hay divergencia de historia.
- Trabajo único en riesgo (solo en el rezagado): 7 archivos frontend modificados
  (+351/−104), 5 `.md` (886 líneas), 1 stash. **NADA en origin.**
- `auto_commit_check.ps1` (untracked, solo en el autoritativo) hace `git push origin main`
  **desatendido**; `schtasks` no muestra tarea programada → gatillo manual `[VERIFICADO]`.

**Protección aplicada** (aditiva, reversible — el árbol del rezagado NO se tocó):
bundle de rescate en `C:\Users\elias\AUDIT_SCRATCH\block0_rescue\`
(`uncommitted_tracked.patch` 855 L + `stash_0.patch` 697 L + 5 `.md` + `PROVENANCE.txt`).
→ el frontend no se puede perder aunque alguien haga `reset --hard` antes de consolidar.

**Recomendación** (decide el dueño, §5 del doc): rescatar el frontend a una rama de
feature, declarar `projects/cardex` único autoritativo, neutralizar el push desatendido,
y solo entonces retirar el rezagado. **No ejecuté borrado/merge/push** (fuera del mandato).

---

## 3. P0-1 — Harvest-0 / soft-block detector

**Causa raíz [VERIFICADO `base.py:315-329`, `softblock.py:30`]:** un portal de 1 segmento
(`partition_params()==[{}]`, todos los `SitemapListingScraper`) que cosecha 0 URLs hace
`ZeroUrlTracker.record(0)` → 1 ciclo vacío < `ZERO_URL_CYCLES=3` → **nunca dispara soft-block**
→ status OK → `run()` ejecuta `_finalize_sink` → `delete_stale` **borraría TODO el inventario
previo del portal** como GONE. No es solo un "done" cosmético: es **corrupción de datos**
(un bloqueo transitorio borra el portal entero).

**Fix (raíz, mínimo):**
- `scrapers/portals/base.py`: nuevo `RunStatus.EMPTY_SUSPECT`. En `run()`, si el ciclo es
  completo y no soft-blocked pero `total == 0` → status `EMPTY_SUSPECT` → **se salta
  `_finalize_sink`** (nunca borrar con cosecha-0) y `_record_outcome` queda **neutral**
  (sin +0.05 reward ni −1.0 penalty: un portal genuinamente vacío no se castiga).
- `scrapers/coordinator.py`: `next_queue_state(EMPTY_SUSPECT)` → retry con backoff
  consumiendo intento, → `failed` con causa **`empty_harvest`** tras `MAX_ATTEMPTS` (nunca
  `done`). `circuit_action_for` lo deja en `"none"` (no escala el breaker; puede ser vacío real).

Elegido sobre el "muestrear ≥3 shards" del blueprint porque ataca **las dos** patologías
(falso-`done` **y** wipe del finalize) con cambio mínimo, sin red extra.

**Re-evaluación de los 12 afectados [VERIFICADO]:** cruce `work_queue.done` × `vehicle_index`
→ exactamente 12 portales `done`@0 (annonces-automobile, aramisauto, autosphere, capcar,
caravenue, cardoen, carizy, classic-trader, flexicar, myway, starterre, youcar) — coincide
con la predicción del blueprint. Reseteados `done→pending` por **igualdad EXACTA de portal**
(H2) con `last_error='reeval_empty_harvest_p0-1'`. Verificado: `done=16` (reales), `12` reeval.
El re-run vivo (producir datos o marcar `empty_harvest`) ocurre cuando el coordinator corra.

**Evidencia tests:** `test_run_empty_harvest_is_empty_suspect_not_ok`,
`test_run_empty_harvest_skips_finalize`, `test_next_queue_state_empty_suspect_*`,
`test_circuit_action_for_each_status` (EMPTY_SUSPECT→none). Suite de portals+coordinator+monitoring: **115 passed**.

---

## 4. P0-2 — cardex-api recableado

**Causa raíz (más profunda que el blueprint) [VERIFICADO]:** tres capas, no una.
1. Red: el contenedor vivo estaba solo en `cardex_default`; `cardex-pg` (alias DNS `postgres`)
   en `cardex_data` → `lookup postgres ... no such host`.
2. Env stale: el contenedor carecía de `REDIS_PASSWORD` (`docker inspect` lo confirmó) — había
   sido creado con un compose anterior a que se añadiera; el redis vivo exige
   `--requirepass cardex_dev_only` → `NOAUTH`.
3. **Imagen stale (raíz real):** los logs decían `"msg":"api: redis connect"` mientras el
   código actual (`main.go:65-66`) emite `"redis ping failed"` y trata el fallo como
   **`log.Warn` no-fatal**. El binario en ejecución era de una imagen vieja que trataba redis
   como **fatal** → crash-loop. Recrear sin rebuild reusaba el binario viejo.

**Fix:** (a) provisioné una clave RSA dev `secrets/jwt_private.pem` (gitignored, dev-only)
para que el bind-mount del JWT fuera un archivo válido; (b) `docker compose up -d --build api`
→ rebuild desde fuente actual (env fresco con `REDIS_PASSWORD` + redes `frontend/backend/data`
+ redis no-fatal).

**Evidencia [VERIFICADO]:**
```
docker ps → cardex-api Up (healthy)
curl http://127.0.0.1:8080/healthz → HTTP 200
curl -H "X-API-Key: <dev>" ".../api/v1/market-price?make=BMW&model=3 Series"
  → HTTP 200 {"countries":[{"country":"DE","count":1,"p50":28900,...}]}   (API→auth→PG→FX→resp)
```
La clave de prueba se sembró en redis y **se borró** tras verificar. Estado durable: la API
sirve datos reales de PG.

---

## 5. P0-3 — enrich_worker (A6) + rich persister (A7) — EL SEAM

**Hallazgo crítico [VERIFICADO]:** el consumidor rico A7 del blueprint (`services/pipeline`, Go)
es **código muerto que no compila**: sin `go.mod`, ausente de `go.work`, e importa
`pkg/{bloom,fx,h3}` (`main.go:22-24`) **borrados en `5a4d59a`** ("delete remaining basura").
El plan "REUSO services/pipeline" descansaba sobre una premisa falsa: ese módulo fue destripado.
(Esto era el `[ASUMIDO]` del Anexo C del blueprint — ahora verificado FALSO.)

**Decisión (muro → abanico → elegir + documentar):** construir el A7 en **Python** sobre el
mismo spine asyncpg que ya produjo 508K filas, **preservando el contrato C7** exacto. Honra el
principio "construir encima de lo que funciona": el Go nunca compiló; el Python→PG sí produce.

**Implementación (canónica, reusada de la corrida previa, re-verificada por mí):**
- `scrapers/enrich_worker.py` (A6): consume `stream:enrich_pending {h,u,s,c}`, fetch vía engine
  anti-detección (`make_engine_fetcher`: `pick_for_portal`+`tls.make_session`, sesión por
  (domain,country)), `generic_extractor.extract_listing` → `VehicleRecord`, `record_to_payload`
  (C6→C7) con **fix H1** (`source_listing_id ← url_hash`, nunca vacío → no viola `source_id NOT NULL`),
  XADD `ingestion_raw`. At-least-once (emit+ack / permanent→DLQ+ack / transient→no-ack).
- `scrapers/rich_consumer.py` (A7): consume `ingestion_raw` (grupo `cg_pipeline`, drop-in del Go),
  fingerprint VIN-priority (byte-idéntico a `computeFingerprint` Go), FX→EUR (`pipeline/fx_eur.py`,
  reemplaza el `pkg/fx` borrado), `INSERT … ON CONFLICT (fingerprint_sha256) DO UPDATE` (C8),
  `vin_history_cache` (LISTING/PRICE_CHANGE/MILEAGE), XADD `meili_sync`.
- `docker-compose.yml`: comando `enrich-worker` corregido a `["-m","scrapers.enrich_worker"]`
  (antes `["-m","enrich_worker"]`, irresoluble bajo `PYTHONPATH=/app`); servicio `pipeline`
  re-apuntado a `scrapers.rich_consumer`.

**Verificación E2E VIVA [VERIFICADO]** (`scripts/verify_seam_redis.py`, redis throwaway, autotrack.nl, limit 3):
```
seeded enrich_pending = 3
A6 emitted=3 dlq=0 transient=0 | ingestion_raw depth = 3
A7 persisted=3 rejected=0 errors=0 | meili_sync depth = 3
vehicles 30 -> 33 (delta=+3)
  row: Peugeot 2008 2020 eur=20700.00 source_id=ec811ac921cc… platform=autotrack.nl
  row: Mazda CX-3 2019 eur=19395.00 source_id=d0d29ea60e0d… platform=autotrack.nl
  row: SEAT Ateca 2019 eur=16950.00 source_id=b85eb5a10a5c… platform=autotrack.nl
PURGED 3; vehicles FINAL = 30 (restored)
```
→ `vehicles` **crece de verdad** desde listings NL reales, con make/model/year/EUR correctos,
source_id no-null (H1), meili_sync emitido; luego purgado (disco = banco de pruebas).

**Hallazgo 2 [VERIFICADO]:** `gaspedaal.nl` (piloto propuesto en el blueprint) da
`missing_critical:make,model,images` — es un **meta-agregador**, sus páginas de detalle no
llevan JSON-LD `Car`. El fetch del engine SÍ funciona (si no, sería `transient`, no `dlq`).
→ **El piloto NL del seam debe usar `autotrack.nl`/`viabovag.nl`, no `gaspedaal.nl`.**

**Continuidad en producción (pendiente operativo, no de código):** el seam se probó sembrando
`enrich_pending` desde `vehicle_index`. Para poblar los 508K históricos en continuo hace falta
el **backfill** del blueprint §6.1 (re-encolar punteros sin `vehicles`) + el contenedor
`enrich-worker` consumiendo lo que A5 produzca. El mecanismo está probado; el backfill a escala
es el siguiente paso operativo.

---

## 6. P0-4 — Entity resolution a PG (PARCIAL, con plan de cierre)

**Realidad verificada que cambia el plan [VERIFICADO]:**
- `discovery_candidates` ya está **exact-deduped** por las UNIQUE constraints `(domain,country)`
  y `(source,registry_id,country)`: 28498 dominios distintos de 28570; `dup_domains = 0`. → un
  resolver **determinista de dealers no produce nada** (las claves exactas ya son únicas).
- La resolución que hacen V21/V12 es por eso **fuzzy** (embeddings multilingües, V21) o por
  **VIN cross-source** (V12). V21 necesita el runtime de embeddings (BGE-M3/nomic vía ollama).
- `entities` exige `vault_dek_id TEXT NOT NULL` → acoplado al subsistema de cifrado/KYC/Stripe.

Coincide con la guía del propio blueprint (P0-4 es el ítem más pesado; **no gatea** el hito
L1→L2→Meili→API; deferible a P1). Per la autorización del encargo ("si no cabe entero sin
comprometer calidad, déjalo parcialmente cableado con plan claro, NO a medias en silencio").

**Entregado (real, testeado, verificado):** `scrapers/entity_resolver.py` — la capa **VIN
cross-source (V12)**, determinista, sin embedder ni vault, que escribe la tabla PG real
`entity_matches`. Cuando un VIN aparece en `vehicles` bajo ≥2 `source_platform`, son el mismo
coche en dos marketplaces → match exacto, confianza 1.0.

**Verificación E2E VIVA [VERIFICADO]** (2 vehículos sintéticos mismo VIN, distinta plataforma):
```
entity_resolver → "1 cross-source VIN matches inserted"
entity_matches: VEHICLE|DEMOULIDA|demo_a|DEMOULIDB|demo_b|1.000|vin_exact|{"vin":"ENTITYDEMOVIN00001"}
2ª corrida → inserted: 0   (idempotente, ON CONFLICT DO NOTHING)
PURGE → vehicles=30, entity_matches=0 (restaurado)
```
Produce 0 sobre datos vivos hoy **solo** porque `vehicles` aún no tiene solape VIN cross-source
(está en 30 seed): es un **gap de DATOS** (se cierra cuando A6→A7 corra a escala en producción),
no de código. Tests: `test_entity_resolver.py` (5, pure pairing).

**Plan de cierre P1 (estado exacto de lo diferido):**
1. **Capa fuzzy V21 (dealers multilingües):** portar el matching por embeddings coseno a un
   resolver que escriba `entity_matches(match_type='DEALER')` sobre `discovery_candidates`.
   Dependencia: runtime de embeddings (BGE-M3/nomic vía ollama, `[ASUMIDO]` :8082 en STATUS.md
   stale — verificar antes). Sin esto no hay dedup de dealers (las claves exactas ya son únicas).
2. **Tabla `entities`:** poblarla es un concern del subsistema KYC/billing (`vault_dek_id NOT NULL`,
   Stripe, kyc_status). Requiere el mecanismo de DEK/vault — no se debe falsear una tabla de
   seguridad con placeholders. Tarea P1 propia.
3. **Activación del resolver VIN:** correr `python -m scrapers.entity_resolver` (o el contenedor)
   tras el backfill de P0-3; empezará a producir `entity_matches` automáticamente.

---

## 7. Calidad y cierre

**Suite completa [VERIFICADO]:** `python -m pytest scrapers/tests/ -q` → **1232 passed, 0 failed**
(baseline 1188 + nuevos: P0-1 portals/coordinator, P0-4 entity_resolver, y los A6/A7/fx de P0-3).
Cero regresiones: los 1188 originales siguen verdes.

**Tests nuevos de esta sesión:** `test_entity_resolver.py` (5) + `test_run_empty_harvest_*` (2,
portals) + `test_next_queue_state_empty_suspect_*` + `EMPTY_SUSPECT` en `test_is_success`/
`test_circuit_action_for_each_status` (coordinator).

**Estado runtime al cierre [VERIFICADO]:** cardex-api `Up (healthy)` /healthz 200; PG restaurado
(`vehicles=30, entity_matches=0, vehicle_index=508339` intacto); 12 portales reseteados a
`pending`; redis throwaway parado; clave de prueba API borrada.

**Archivos tocados (en rama `feature/p0-rewiring`, NO `main`):**
- Modificados: `scrapers/portals/base.py`, `scrapers/coordinator.py`,
  `scrapers/tests/test_portals.py`, `scrapers/tests/test_coordinator.py`, `docker-compose.yml`,
  `P0_PROGRESO.md`, `BLOCK0_GIT_HAZARD.md`.
- Nuevos: `scrapers/enrich_worker.py`, `scrapers/rich_consumer.py`, `scrapers/pipeline/fx_eur.py`,
  `scrapers/entity_resolver.py`, sus tests, `scripts/verify_seam*.py`, este reporte.
- No-versionado (dev, gitignored): `secrets/jwt_private.pem`.

**Lo NO abordado (por diseño):** proxies/captcha/fuentes de pago (P3, backlog gobernado);
consolidación física del segundo checkout (decisión del dueño); backfill de los 508K y arranque
sostenido de la fleet (operativo, no de código P0).

**Autointerrogatorio de cierre:** ¿afirmé algo sin verificar? No — cada número tiene su comando.
¿Placeholders/huecos? El único parcial (P0-4 fuzzy/entities) está declarado con plan, no en
silencio. ¿Causa raíz o síntoma? Raíz en los cuatro (bajé hasta imagen-stale en P0-2, hasta el
módulo-muerto-Go en P0-3, hasta el finalize-wipe en P0-1). ¿Suite verde? 1232/1232. ¿Worktree
limpio? Cambios commiteados en la rama de feature, `main` intacto en `6e084a5`.

*Fin del reporte de ejecución P0.*
