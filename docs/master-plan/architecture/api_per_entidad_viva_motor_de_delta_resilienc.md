# API per-entidad VIVA + Motor de Delta + Resiliencia + Alertas + Ingestión Legal (XML/API)

## Resumen
El subsistema NO es greenfield: existe y está parcialmente probado E2E (2026-06-08). Lo verifiqué leyendo el código real, no asumiendo. Piezas vivas: (1) services/entity_api/app.py — FastAPI read-only, 8 endpoints /v1, paginación keyset, sobre la VIEW entity_inventory (sin copia de datos); (2) motor de delta always-on scrapers/delta/delta_worker.py (consume stream:harvest_batches, at-least-once con XAUTOCLAIM+DLQ, SEEN ~1.9s / GONE ~0.3s probado); (3) primitivas SEEN/GONE en scrapers/common/indexer.py (INSERT-only + DELETE-stale, particiones mensuales de vehicle_events, auto-link entity_ulid='se_'||md5(domain)); (4) detección de cambio de PRECIO/MILEAGE/LISTING en rich_consumer.py hacia vin_history_cache con CTE prior que captura el precio previo correctamente; (5) delta puro unit-testable scrapers/pipeline/delta.py con price_hash; (6) alerting de fallo de scraping scrapers/delta/operator_events.py (3 sinks: Redis stream + PG operator_alerts + JSONL) y auto-remediación remediation_dispatcher.py (call-site real de remediate(), anti-churn cap); (7) circuit-breaker por (domain,tier) en scrapers/engine/router/circuit.py; (8) DLQ con política §C4 en scrapers/pipeline/dlq.py; (9) cadencia/frescura adaptativa en scrapers/scheduler_pg.py + portal_cadence; (10) un SEGUNDO sistema de alertas en Go (services/api/internal/alerts/) orientado a CLIENTE (arbitraje cross-border) con webhook+email SSRF-hardened. El diseño consolida, cierra gaps reales y proyecta. GAPS VERIFICADOS que esta spec ataca: (a) la detección de cambio de FOTO no existe como evento de primera clase (sólo se hace COALESCE de photo_urls en el upsert, sin emitir PHOTO_CHANGE); (b) el entity_api Python no tiene autenticación ni versionado per-entidad (no hay API keys, sólo en el Go); (c) no hay endpoint de snapshot/fingerprint consultable ni historial de versión de inventario por entidad; (d) la ingestión LEGAL (XML/API directo de dealer) está en la visión pero NO tiene tabla, adaptador ni convivencia con scraping diseñada; (e) entity_delta no surfacea PRICE_CHANGE ni PHOTO_CHANGE en el mismo feed (están en /price-changes separado, foto ausente); (f) la cadencia (portal_cadence) cubre portales, no dealers individuales; (g) la DLQ vive en SQLite mientras el delta vive en PG+Redis — dos almacenes de cola. El subsistema es sólido; el trabajo es consolidar a un modelo de evento unificado, añadir auth/versionado, cerrar foto e ingestión legal, y unificar la resiliencia.

## Estrategias
- **S1 — Delta event-driven always-on (PRIMARIA)**: Consolidar sobre lo existente: delta_worker.py consume stream:harvest_batches; indexer.insert_batch/delete_stale aplican SEEN/GONE a vehicle_index+vehicle_events (particionado mensual). Cada harvester publica su set de URLs al stream con complete=1 (set completo: SEEN+GONE) o complete=0 (incremental: solo SEEN). Event-driven, no batch nocturno. Extender: emitir PHOTO_CHANGE y unificar PRICE_CHANGE en vehicle_events con nuevos event_type para que /delta devuelva un feed unico.
- **S2 — Snapshot+fingerprint diff (FALLBACK para fuentes sin stream)**: Para una fuente que no puede publicar al stream en vivo (receta nueva, sitemap pesado, re-scrape de verificacion), usar scrapers/pipeline/delta.compute_delta(previous,current) puro: construir cycle_from_records/cycle_from_urls (mapa url_hash->price_hash), diffear contra el snapshot PG, materializar new/gone/price_changed. Persistir un inventory_snapshot por entidad+ciclo (fingerprint del set completo: sha256 ordenado de url_hashes) para detectar drift de volumen y permitir replay.
- **S3 — Ingestion LEGAL XML/API directa (FUTURO, convive con scraping)**: Disenar un ingest_adapter por entidad con channel en {scraper, legal_xml, legal_api, dual}. Un dealer que firma entrega un feed (XML estandar tipo standvirtual/mobile.de, o endpoint JSON). Un nuevo worker legal_feed_worker.py normaliza ese feed al MISMO contrato C7 (el que consume rich_consumer) y lo publica a stream:ingestion_raw + stream:harvest_batches. La entidad pasa ingest_channel='legal_api', su defense_tier se vuelve irrelevante y el scraping se desactiva (portal_cadence.enabled=false). El delta, la API y las alertas funcionan IDENTICO porque el formato downstream es el mismo. Verificacion adversarial: comparar el feed legal contra un scrape sombra periodico hasta confiar (trust_score).
- **S4 — Protocolo 'agotar todas las vias' ante muro de extraccion**: Cuando una entidad cae (volume_drift/parse_fail/waf_block/timeout repetido y remediate() no recupera tras MAX_REMEDIATIONS), NO se acepta el 'no se puede': el alert escala a status=needs_research y dispara un agente de investigacion que (1) busca en GitHub/Reddit/foros herramientas open-source nuevas (Camoufox ya instalado, tambien flaresolverr, scrapling, undetected variants), (2) prueba vias alternativas de descubrimiento del inventario (sitemap, WP-REST, API interna in-page, RSS, dumps), (3) propone una receta nueva versionada en configs/. La entidad nunca se marca 'muerta' sin que este agente haya agotado el universo.

## Spec completa
# CARDEX — Subsistema: API VIVA + Delta + Resiliencia + Alertas + Ingestión Legal

> Especificación de ejecución. Construye sobre el código REAL verificado (citas de archivo
> a lo largo del documento). No reescribe lo que funciona: consolida, cierra gaps y proyecta.

---

## 0. Principio rector

CARDEX encapsula **cada entidad (plataforma o dealer) como un producto vendible aislado**:
su propia API de inventario vivo, su propio feed de delta, su propia receta versionada, su
propio perfil de defensa y su propia frescura. El **global index** es el producto agregado;
los endpoints per-entidad son los desagregados. La fuente de verdad es **PostgreSQL 16**
(asyncpg); **Redis Streams** es transporte; la API es una **VIEW read-only sin copia de datos**
(`entity_inventory`, definida en `scripts/migrations/0001_source_entities.up.sql`).

Invariantes no negociables (verificadas en `STATUS.md` y el código):
- **MVCC PG**: sólo `INSERT` nuevo + `DELETE` stale. `UPDATE` de filas no mutadas prohibido.
  (`indexer.insert_batch`/`delete_stale` lo respetan; `rich_consumer` hace UPDATE sólo sobre
  campos mutables: precio, status, fotos, mileage.)
- **Redis**: sólo Streams. Estado de inventario en Redis prohibido.
- **`vehicle_events`** es append-only particionado por mes (RANGE on `ts`).
- **`entity_ulid`** es determinista: `'se_' || md5(source_key)`. Cualquier listing nuevo
  enlaza con cero lookups. Verificado en `indexer._ensure_entity` y `operator_events.entity_ulid_for`.

---

## 1. Arquitectura del subsistema (componentes reales + nuevos)

```
                         +------------------------------------------------------+
   harvesters/portals    |              REDIS STREAMS (transporte)              |
   dealers / legal feeds |  stream:harvest_batches   stream:ingestion_raw       |
        |                |  stream:enrich_pending    stream:operator_events     |
        |  XADD          |  stream:meili_sync        stream:price_events        |
        v                |  stream:dlq                                          |
 +--------------+        +------------------------------------------------------+
 | legal_feed_  |             |                    |                  |
 | worker (NEW) |-------------+                    |                  |
 +--------------+    +----------------+   +-----------------+  +----------------------+
                     | delta_worker   |   | rich_consumer   |  | remediation_dispatcher|
                     | (always-on)    |   | (L1->L2 +price) |  | (auto-recover)        |
                     | SEEN/GONE      |   | PRICE/MILEAGE/  |  | calls remediate()     |
                     | +PHOTO (NEW)   |   | LISTING +PHOTO  |  | anti-churn cap        |
                     +-------+--------+   +--------+--------+  +----------+-----------+
                             v                     v                       |
        +----------------------------------------------------------------+--------+
        |                       PostgreSQL 16  (source of truth)         |        |
        |  source_entities   vehicle_index   vehicles   vehicle_events   |        |
        |  vin_history_cache portal_cadence  operator_alerts             |        |
        |  inventory_snapshot(NEW)  ingest_adapter(NEW)  api_keys(NEW)   |        |
        |  VIEW entity_inventory                                         |        |
        +---------------------------------+-----------------------------+         |
                                          v                                       v
                          +----------------------------+          +----------------------+
                          | services/entity_api(FastAPI)|          | dashboard / operator |
                          | /v1 read-only VIEW          |<---------| tails operator_alerts|
                          | +auth +versioning +snapshots|          | + JSONL              |
                          +----------------------------+          +----------------------+
```

**Dos planos de alerta — NO confundir (verificado en código):**
- **Plano OPERADOR (interno, salud del pipeline):** `scrapers/delta/operator_events.py` +
  tabla `operator_alerts` + `GET /v1/alerts`. Señales: `waf_block`, `volume_drift`,
  `parse_fail`, `timeout`, `dead`. Es el "qué se rompió y dónde".
- **Plano CLIENTE (externo, oportunidad de negocio):** `services/api/internal/alerts/` (Go) —
  arbitraje cross-border, dispatch webhook+email con cliente HTTP SSRF-hardened
  (`notify.go:ssrfSafeClient`). Es el "qué le interesa al comprador".

Ambos coexisten y se mantienen separados. Esta spec añade un tercer carril ligero de
**alerta de DRIFT/FRESCURA per-entidad** que vive en el plano operador.

---

## 2. Modelo de datos (esquemas concretos)

### 2.1 Existente (verificado, no se toca el shape, se EXTIENDE)

`source_entities` (de `0001_source_entities.up.sql`):
```sql
source_entities(
  entity_ulid TEXT PK,            -- 'se_'||md5(source_key)
  source_key  TEXT UNIQUE,
  kind        TEXT CHECK (kind IN ('platform','dealer')),
  domain TEXT, country CHAR(2),
  defense_tier TEXT CHECK (... IN ('T1','T2','T3')),
  waf TEXT, config_ref TEXT,
  first_seen TIMESTAMPTZ, updated_at TIMESTAMPTZ )
```

`vehicle_events` (de `indexer.ensure_schema`): append-only, PARTITION BY RANGE(ts),
`event_type CHECK IN ('SEEN','ENRICHED','GONE')`.

`operator_alerts` (de `0002_operator_alerts.up.sql`): `(alert_id, entity_ulid FK, source_key,
stage CHECK 6 valores, signal CHECK 6 valores, severity, evidence JSONB, status CHECK 5 valores,
remediation_action, remediation_result, attempts, created_at, updated_at)`.

`portal_cadence` (de `002_portal_cadence.sql`): `(portal, country) PK, current_interval_h,
last_change_at, last_scrape_at, next_scrape_at, listings_delta, enabled)`.

### 2.2 Migración `0004_event_type_extend.up.sql` (NUEVO — cerrar foto y unificar feed)

Hoy `/delta` (entity_api `app.py:145`) sólo devuelve SEEN/GONE; PRICE_CHANGE vive aparte en
`/price-changes` (sobre `vin_history_cache`) y PHOTO_CHANGE **no existe**. Unificar:
```sql
BEGIN;
-- Extender el dominio de event_type para que vehicle_events sea el feed canonico unico.
ALTER TABLE vehicle_events DROP CONSTRAINT IF EXISTS vehicle_events_event_type_check;
ALTER TABLE vehicle_events ADD CONSTRAINT vehicle_events_event_type_check
  CHECK (event_type IN ('SEEN','ENRICHED','GONE','PRICE_CHANGE','PHOTO_CHANGE','MILEAGE_CHANGE'));
-- Columna detail para llevar prev/new sin abusar de las columnas de precio escalares.
ALTER TABLE vehicle_events ADD COLUMN IF NOT EXISTS detail JSONB;  -- {prev,new,direction,...}
CREATE INDEX IF NOT EXISTS idx_ve_type_ts ON vehicle_events(event_type, ts);
COMMIT;
```
`rich_consumer._write_vin_history` ya calcula prev/new/direction para precio: AÑADIR ahí (y en
`persist_one`) un `INSERT INTO vehicle_events(... 'PRICE_CHANGE', detail)`; y, comparando
`photo_urls` previas vs nuevas (el COALESCE actual descarta la señal), emitir `PHOTO_CHANGE`
con `detail={added:[...],removed:[...],count_prev,count_new}`. Así `/delta` devuelve el feed
completo: altas, bajas, precio, foto, mileage — todo por entidad, en un solo recurso.
Nota de ejecución: el DROP/ADD CONSTRAINT sobre tabla particionada toma lock; ejecutar en
ventana, idealmente patrón NOT VALID + VALIDATE como hizo 0001 con las FKs.

### 2.3 Tabla `inventory_snapshot` (NUEVO — fingerprint/versionado/replay) — S2

```sql
CREATE TABLE inventory_snapshot(
  snapshot_id     BIGSERIAL PRIMARY KEY,
  entity_ulid     TEXT NOT NULL REFERENCES source_entities(entity_ulid) ON DELETE CASCADE,
  cycle_ts        TIMESTAMPTZ NOT NULL DEFAULT now(),
  n_listings      INT NOT NULL,
  set_fingerprint TEXT NOT NULL,   -- sha256 de los url_hash ordenados (set completo)
  price_set_fp    TEXT,            -- sha256 de (url_hash:price_hash) ordenados
  source_channel  TEXT NOT NULL,   -- scraper|legal_xml|legal_api
  ingest_run_id   TEXT,            -- correlacion con el harvest run
  UNIQUE(entity_ulid, cycle_ts) );
CREATE INDEX idx_snap_entity_ts ON inventory_snapshot(entity_ulid, cycle_ts DESC);
```
Cada cierre de ciclo completo (`StreamingDeltaSink.finalize` o el `legal_feed_worker`) escribe
una fila. Da: (1) **versionado** consultable del inventario por entidad; (2) **detección de
drift de volumen** comparando `n_listings` contra el baseline (`drift_baseline.expected_min_volume`
de la receta); (3) **verificación adversarial** (re-derivar el set por otra vía y comparar
`set_fingerprint`); (4) **replay** tras incidente. En entidades gigantes (AS24 ~92K) el set se
construye por streaming/chunking para no romper el host RAM-light (~780MB).

### 2.4 Tabla `ingest_adapter` (NUEVO — ingestión legal conviviendo con scraping) — S3

```sql
CREATE TABLE ingest_adapter(
  entity_ulid   TEXT PRIMARY KEY REFERENCES source_entities(entity_ulid) ON DELETE CASCADE,
  channel       TEXT NOT NULL DEFAULT 'scraper'
                CHECK (channel IN ('scraper','legal_xml','legal_api','dual')),
  feed_url      TEXT,            -- endpoint del feed legal
  feed_format   TEXT,           -- 'standvirtual_xml'|'mobile_bmd'|'cardex_json'|...
  feed_auth_ref TEXT,           -- ref a secreto (NUNCA el secreto en claro)
  poll_interval_h DOUBLE PRECISION DEFAULT 1.0,
  shadow_scrape BOOLEAN DEFAULT TRUE,  -- mantener scrape sombra hasta confiar
  trust_score   DOUBLE PRECISION DEFAULT 0.0,  -- sube cuando feed~scrape (verif. adversarial)
  agreement_signed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now() );
```
`channel='dual'` = periodo de transición: corre feed legal Y scrape sombra; el verificador
adversarial compara `set_fingerprint` de ambos; cuando `trust_score>=0.99` durante N ciclos,
flip a `legal_api` y `portal_cadence.enabled=false` para esa entidad.

### 2.5 Tabla `api_keys` per-tenant (NUEVO — auth/cuota en entity_api Python)

El entity_api Python (`services/entity_api/app.py`) hoy NO autentica (sólo el Go tiene
`internal/apikeys/keys.go`). Para vender inventario per-entidad hace falta auth + scope + cuota:
```sql
CREATE TABLE api_keys(
  key_id      TEXT PRIMARY KEY,        -- 'ak_'||...
  key_hash    TEXT NOT NULL,          -- sha256(secret); nunca el secreto
  tenant      TEXT NOT NULL,
  scope       JSONB NOT NULL DEFAULT '{}',  -- {entities:[...]|"*", endpoints:[...], rate_per_min}
  active      BOOLEAN NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ DEFAULT now(), expires_at TIMESTAMPTZ );
CREATE INDEX idx_apikeys_hash ON api_keys(key_hash) WHERE active;
```
Un comprador de "inventario de mobile.de" recibe una key con `scope.entities=['se_<md5(mobile.de)>']`;
el middleware rechaza cualquier otro `ulid`. Defensa: rate-limit por key (Redis token-bucket),
`429` con `Retry-After`.

---

## 3. La API VIVA — esquema completo

Base actual verificada en `app.py` (envelope `{success,data,error,meta}`, paginación keyset,
pool max 4). Se MANTIENE y se amplía. Versionado: prefijo `/v1` ya presente; introducir
`/v2` sólo ante cambio breaking, sirviendo ambos en paralelo (deprecación con header
`Sunset`). Contrato de versión documentado en `services/api/internal/docs/openapi.yaml`
(extender) y un nuevo `services/entity_api/openapi.yaml`.

### 3.1 Recursos (existentes + nuevos marcados NEW)

| Método · Path | Devuelve | Estado |
|---|---|---|
| `GET /v1/health` | liveness + entity count | existe |
| `GET /v1/entities?country=&kind=&tier=&limit=&cursor=` | catálogo + `inventory_count` vivo | existe |
| `GET /v1/entities/{ulid}` | fiche: metadata + count + `delta_24h` | existe |
| `GET /v1/entities/{ulid}/inventory?limit=&cursor=` | inventario vivo de UNA entidad (vendible) | existe |
| `GET /v1/entities/{ulid}/delta?since=&limit=&types=` | feed UNIFICADO SEEN/GONE/PRICE/PHOTO/MILEAGE | EXTENDER (hoy sólo SEEN/GONE) |
| `GET /v1/entities/{ulid}/price-changes?since=` | feed de precio | existe (queda como vista filtrada de /delta?types=PRICE_CHANGE) |
| `GET /v1/entities/{ulid}/snapshots?limit=` | historial de versiones de inventario (fingerprints) | NEW (S2) |
| `GET /v1/entities/{ulid}/freshness` | `last_cycle_at`, `next_due_at`, `staleness_s`, SLA del tier | NEW |
| `GET /v1/inventory?country=&make=&limit=&cursor=` | índice global | existe |
| `GET /v1/alerts?status=&signal=&entity_ulid=` | feed de alertas operador | existe |
| `GET /v1/feed/{ulid}.xml` | export XML del inventario (formato estándar de feed) | NEW (puente legal inverso) |

### 3.2 Paginación, auth, errores
- **Paginación**: keyset (cursor = último `source_url`/`source_key`), nunca OFFSET. Ya
  implementado correctamente; el `LIMIT {limit}` se inyecta como int validado por
  `Query(..., le=MAX_LIMIT)` — seguro (no es input string). Mantener.
- **Auth**: middleware nuevo en `app.py` — `Authorization: Bearer ak_...` -> hash -> `api_keys`
  -> enforce `scope`. Health queda público. Rate-limit token-bucket en Redis.
- **Errores**: envelope ya uniforme (`_http_exc`). Añadir códigos: `401` (sin key), `403`
  (scope), `429` (cuota), `503` (PG pool agotado -> degradación elegante, no crash).

### 3.3 Frescura garantizada (SLA por tier)
La cadencia ya existe en `portal_cadence` + `scheduler_pg.py` (interval adaptativo:
T0/T1=6h, T2=12h, T3=24h inicial; se relaja si estático, se acelera si cambia —
`scheduler.plan_cycle`). GAP: cubre **portales**, no dealers individuales. Diseño:
`portal_cadence` se generaliza a `entity_cadence` (misma forma, PK `entity_ulid`) o se
añade tabla paralela para dealers. SLA publicado por `/v1/entities/{ulid}/freshness`:

| Tier | Re-extracción objetivo | Tope de staleness antes de alerta |
|---|---|---|
| T1 (gigantes/plataformas) | 6h (acelera a 1-2h si delta alto) | 12h -> volume_drift/dead alert |
| T2 (dealers activos, curl_cffi) | 12h | 24h |
| T3 (cola larga, dealers pequeños) | 24-72h | 96h |
| legal_api / legal_xml | poll `ingest_adapter.poll_interval_h` (def 1h) | 2x interval |

Un watcher (`freshness_sentinel.py`, NEW) corre cada 15min: entidades cuyo
`now - last_scrape_at > tope_tier` -> `emit_alert(stage='extract', signal='dead', ...)`.

---

## 4. Motor de delta — diseño de detección de cambios

### 4.1 Camino vivo (S1, primario) — VERIFICADO funcionando
`delta_worker.run()` (`scrapers/delta/delta_worker.py`) consume `stream:harvest_batches`.
Cada mensaje = un set de URLs de una entidad. `complete=1` -> `insert_batch` (SEEN) +
`delete_stale` (GONE); `complete=0` -> sólo SEEN. At-least-once: XACK al éxito; fallo
transitorio -> PEL -> XAUTOCLAIM tras 60s; >5 entregas -> `stream:dlq` + alert
`parse_fail`/seam. Probado E2E: SEEN ~1.9s, GONE ~0.3s (`scrapers/delta/run_proofs.py`).

### 4.2 Fingerprints / snapshots (S2)
- **Por listing**: `url_hash = sha256(url)[:32]` (identidad) y `price_hash` (mutabilidad) —
  `scrapers/pipeline/delta.py`. `compute_delta(previous, current)` es PURO y unit-testable:
  devuelve `new/gone/price_changed/unchanged`. Regla fina ya implementada: un cambio sólo se
  asevera si AMBOS lados tienen precio conocido (un recheck que no leyó precio no dispara
  falso positivo — `PRICE_UNKNOWN`).
- **Por entidad (set)**: `set_fingerprint = sha256(sorted(url_hashes))`. Detecta drift de
  volumen y permite verificación cruzada. Se persiste en `inventory_snapshot` (§2.3).
- **Foto**: comparar `photo_urls` array (orden-insensible) -> set de URLs de imagen; diff ->
  `PHOTO_CHANGE` con `added/removed`. Hoy `rich_consumer` hace
  `photo_urls = COALESCE(EXCLUDED.photo_urls, vehicles.photo_urls)` (línea ~83) que PIERDE la
  señal. Fix: leer el array previo en la CTE `prior` (como ya hace con precio) y emitir evento.

### 4.3 Cambio de precio — VERIFICADO correcto
`rich_consumer._INSERT_VEHICLE_SQL` usa CTE `prior` para capturar `last_price_eur` ANTES del
UPDATE, evitando el bug clásico de comparar contra el valor ya sobrescrito (comentario
explícito en líneas 92-102). `price_changed` dispara en CUALQUIER cambio (drop O rise);
`_write_vin_history` escribe `PRICE_CHANGE` a `vin_history_cache` con
`{prev,new,delta,direction}`. AÑADIR el espejo a `vehicle_events` (§2.2) para feed unificado.

### 4.4 Historial actualizado
- `vin_history_cache` (cuando hay VIN): LISTING / PRICE_CHANGE / MILEAGE — VERIFICADO.
- `vehicle_events` (siempre, con o sin VIN): el log append-only por listing.
- `inventory_snapshot` (por entidad por ciclo): la línea temporal de versiones.
Triple capa: evento atómico, historial VIN, snapshot de set. Suficiente para reconstruir
"qué tenía el dealer X el día D".

---

## 5. Resiliencia — un dealer caído NO tumba CARDEX

Aislamiento en capas (todas existen, se consolidan):

1. **Aislamiento por entidad**: cada harvest es un mensaje independiente en
   `stream:harvest_batches`. Un dealer que falla deja SU mensaje en PEL; los demás siguen.
   `delta_worker._handle` captura toda excepción por mensaje (decisión ack/reclaim/dlq) — un
   payload veneno nunca mata el worker.
2. **Circuit-breaker por (domain,tier)**: `scrapers/engine/router/circuit.py`. CLOSED->OPEN
   (3 fallos/60s -> open 120s) -> HALF_OPEN (1 probe) -> CLOSED|OPEN. El escalator usa
   `force_open` para "este tier está quemado, sube al siguiente". EWMA de success_rate.
3. **DLQ con política de recuperación**: `scrapers/pipeline/dlq.py` (§C4):
   `fetch_error`->retry 1h, `soft_block`->retry 24h identidad premium, `rate_limited`->honra
   `Retry-After`, `parse_error`->humano (no auto), `poison`->descarta. GAP: vive en SQLite
   mientras el delta vive en PG+Redis. **Decisión**: mantener `stream:dlq` (Redis) como DLQ
   operacional del pipeline vivo y `dlq` (SQLite) como cola de re-trabajo de URLs; documentar
   la frontera. No fusionar a la fuerza (YAGNI) — son dominios distintos.
4. **At-least-once + idempotencia**: `insert_batch` es `ON CONFLICT DO NOTHING RETURNING`
   (SEEN exactamente una vez); `rich_consumer` es `ON CONFLICT (fingerprint) DO UPDATE`
   (reproceso no duplica). Reclaim de PEL en ambos.
5. **Anti-churn en remediación**: `remediation_dispatcher` capea reintentos por entidad
   (`MAX_REMEDIATIONS=3` en `WINDOW=6h`); pasado el cap -> `stream:dlq` + `status=dlq`.
   Una entidad rota permanentemente NO puede hacer livelock al remediador (bug ya corregido:
   contar por `source_key` además de `entity_ulid` porque éste es NULL para dealers nuevos).
6. **Degradación de la API**: pool `max_size=4`; bajo presión devolver `503` con `Retry-After`
   en vez de colgar. La VIEW nunca bloquea escrituras (read-only).

---

## 6. Alertas — qué, cómo, a dónde

### 6.1 Plano operador (salud) — VERIFICADO
`operator_events.emit_alert(source_key, stage, signal, evidence, severity)` ->
3 sinks: (1) `stream:operator_events` (dispara remediación), (2) `operator_alerts` PG
(consultable, `/v1/alerts`), (3) JSONL `logs/operator_alerts.jsonl` (dashboard tail).
Validación de dominio en Python ANTES de SQL (stage/signal/severity contra tuplas) — falla
ruidoso, no error SQL opaco. **`stage`** localiza el punto EXACTO:
`discovery|resolve|classify|extract|seam|api`. **`signal`**:
`waf_block|volume_drift|parse_fail|timeout|dead|other`.

### 6.2 Mapa señal->acción (remediación) — VERIFICADO
| señal | acción |
|---|---|
| `volume_drift` | `remediate()` — re-detectar config, re-scrape sample, revalidar (call-site real) |
| `parse_fail` | `status=escalated`, `config_review` |
| `waf_block` | `status=escalated`, `mark_requires_proxy` (escalar tier / proxy residencial) |
| `timeout`/`dead` | retry-with-backoff (`status=open`) |
| (NEW) tras cap | `status=needs_research` -> S4 agente de investigación open-source |

### 6.3 A dónde (canales)
- **Hoy (interno)**: dashboard tail + `/v1/alerts`. Elias gestiona.
- **Diseño de salida externa** (reusar `services/api/internal/alerts/notify.go`): el notifier
  Go ya tiene webhook (SSRF-hardened, sin redirects, bloquea IPs privadas/metadata) + email
  SMTP (anti header-injection). Para alertas operador críticas, un puente
  `operator_alert -> notify` (severity=critical) entrega a webhook/email del operador.
  **No reinventar**: el notifier seguro ya existe; se reutiliza.
- **Drift de frescura** (NEW §3.3): `freshness_sentinel` emite `dead` cuando una entidad
  supera su tope de staleness.

---

## 7. Verificación adversarial (CO-IGUAL, integrada)

Desconfiar de la PRIMERA respuesta de cualquier workflow. Vías INDEPENDIENTES de las de
extracción:
1. **Snapshot cross-check**: re-derivar el set de una entidad por una vía DISTINTA a la que lo
   produjo (si scrapeó por API interna, re-contar por sitemap; si por sitemap, por paginación
   SSR) y comparar `set_fingerprint`. Divergencia >eps -> alerta `volume_drift` + `needs_research`.
2. **Feed legal vs scrape sombra** (S3, `channel='dual'`): mientras `trust_score<0.99`, el feed
   legal NO se confía a ciegas; se compara contra el scrape. El `trust_score` sube sólo cuando
   coinciden N ciclos.
3. **Conteo Y contenido**: no basta el número. El verificador muestrea M listings por entidad y
   valida campos (make/model no vacíos, year 1920-2027, precio en rango, URL deep-link) — las
   mismas gates de `rich_consumer.validate_payload`, pero aplicadas como auditoría a posteriori
   sobre una muestra aleatoria, no sólo en ingestión.
4. **Frescura real**: comparar `last_seen` del inventario contra `last_scrape_at` de cadencia;
   si el inventario no se mueve pero la cadencia dice que se scrapeó -> selector roto silencioso
   (under-harvest) -> `volume_drift`.
5. **El verificador es un AGENTE SEPARADO** del que extrae (sección 8), nunca el mismo proceso.

---

## 8. Workflows + Agentes

### WF-1 — Delta always-on (continuo)
- Agente **delta-applier** (worker, no LLM): `delta_worker.run()`. Responsabilidad: aplicar
  SEEN/GONE/PRICE/PHOTO en vivo. Tools: PG pool, Redis Streams. Calidad: latencia<2s,
  at-least-once, cero pérdida (PEL+DLQ).
- Agente **rich-persister** (worker): `rich_consumer.run()`. L1->L2 + price/photo/mileage.

### WF-2 — Resiliencia + auto-remediación (reactivo)
- Agente **remediator** (worker + `remediate()`): consume `stream:operator_events`, recupera.
  Anti-churn. Tools: harvester sample, seam throwaway, purger, PG.
- Agente **circuit-guardian** (lógica en coordinator): abre/cierra breakers, escala tiers.

### WF-3 — Frescura (programado)
- Agente **scheduler** (`scheduler_pg.main`): decide qué entidad re-extraer según cadencia.
- Agente **freshness-sentinel** (NEW, 15min): alerta staleness.

### WF-4 — Verificación adversarial (programado + on-alert)
- Agente **verifier** (LLM ligero/Haiku donde aplique + workers): re-deriva sets por vía
  alterna, compara fingerprints, muestrea contenido. SEPARADO del extractor.
  Criterio: nada se marca "verde" sin su auditoría (doctrina Guardian del `_SCHEMA.md`).

### WF-5 — Ingestión legal (futuro)
- Agente **legal-feed-normalizer** (`legal_feed_worker.py`): mapea XML/API del dealer al
  contrato C7 -> streams. Un normalizador por `feed_format`.

### Orquestación
- **AGENTE-LÍDER (Opus)**: supervisa los workflows, prioriza entidades (gigantes primero por
  volumen, cola larga por cobertura), decide flips de canal legal, lanza el agente de
  investigación S4 ante muros. Modelo Opus por las decisiones irreversibles (desactivar
  scraping de una entidad, confiar en un feed legal).
- **AGENTE VERIFICADOR/MOTIVADOR (co-igual)**: NO subordinado al líder; su trabajo es
  desconfiar de los entregables del líder y de cada worker, exigir prueba (fingerprints,
  muestras), y reabrir lo que se cerró sin evidencia. Reporta divergencias como alertas.
- **AGENTE DE INVESTIGACIÓN (S4, on-demand)**: ante entidad que la auto-remediación no
  recupera, busca en GitHub/Reddit/foros herramientas open-source nuevas y vías alternas,
  propone receta versionada. Nunca se acepta "no se puede" sin que este agente agote el universo.

---

## 9. Coste (grado institucional, presupuesto cero operativo)

- **LLMs locales** (ya desplegados, `STATUS.md`): llama.cpp Qwen2.5-Coder-7B :8081
  (clasificación), nomic-embed :8082 (embeddings). El verifier y el clasificador de evidencia
  usan estos, NO API de pago.
- **Workers en Python/asyncpg/redis** — sin coste por evento. Pools pequeños (RAM-light,
  host ~780MB libre).
- **Proxies de pago SÓLO** cuando `waf_block` lo exige (señal explícita -> `mark_requires_proxy`);
  por defecto curl_cffi/Camoufox gratis.
- **Anti-detección Tier-1**: Camoufox + curl_cffi (instalados), JA3 coherente página 1->N
  (invariante `STATUS.md`), rate-limiters desde el inicio (lección SIRENE: usar dumps, no APIs
  rate-limitadas).

---

## 10. Criterios de aceptación (medibles)

1. **Delta latencia**: push de listing nuevo visible en `/v1/entities/{ulid}/delta` < 2s (SEEN);
   baja < 1s (GONE). [Probado: 1.9s / 0.3s — mantener bajo carga].
2. **Feed unificado**: `/v1/entities/{ulid}/delta?types=PRICE_CHANGE,PHOTO_CHANGE,SEEN,GONE`
   devuelve los 4+ tipos. PHOTO_CHANGE emitido cuando cambia `photo_urls` (gap actual cerrado).
3. **Aislamiento**: matar el harvest de una entidad NO afecta el inventario ni el delta de las
   demás (test: inyectar payload veneno -> DLQ, resto sigue, worker vivo).
4. **Auth/scope**: una key con `scope.entities=[X]` recibe 403 al pedir `/entities/Y/inventory`.
5. **Frescura**: toda entidad activa tiene `next_due_at`; superar el tope del tier emite alerta
   `dead` en < 15min.
6. **Snapshot/fingerprint**: cada ciclo completo escribe `inventory_snapshot`; re-derivar el set
   por vía alterna produce el MISMO `set_fingerprint` (mas/menos eps justificado).
7. **Remediación**: `volume_drift` -> `remediate()` -> `status=resolved` cuando recupera;
   tras `MAX_REMEDIATIONS` -> `dlq` (no livelock). [Probado].
8. **Verificación adversarial**: el verifier reabre >=1 entidad marcada "ok" por el extractor con
   evidencia de divergencia (prueba de que desconfía de verdad).
9. **Ingestión legal**: una entidad con `channel='legal_api'` sirve inventario/delta IDÉNTICO
   por la misma API, con scraping desactivado, sin cambio en endpoints.
10. **Reversibilidad**: toda migración tiene `.down.sql` no destructivo del inventario
    (patrón ya seguido en `0001`/`0002`).
11. **Trazabilidad**: toda alerta lleva `(entity, stage, signal, evidence)`; todo evento de
    delta lleva `url_original` (qué coche), `ts`, y `detail` (prev/new). Cobertura de tests
    >=80% en módulos nuevos; los existentes ya tienen tests
    (`test_entity_api_price_changes.py`, `test_remediation_dispatcher.py`, `test_rich_consumer.py`).

---

## 11. Archivos a tocar / crear (mapa de ejecución)

**Tocar (extensión reversible):**
- `services/entity_api/app.py` — añadir auth middleware, `/snapshots`, `/freshness`,
  `/feed/{ulid}.xml`, extender `/delta` con `types=` sobre `vehicle_events`.
- `scrapers/rich_consumer.py` — emitir `PRICE_CHANGE`/`PHOTO_CHANGE`/`MILEAGE_CHANGE` a
  `vehicle_events`; capturar `photo_urls` previo en la CTE `prior`.
- `scrapers/common/indexer.py` — `delete_stale`/`insert_batch` ya llevan `url_original`; añadir
  escritura de `inventory_snapshot` en `StreamingDeltaSink.finalize`.
- `scrapers/scheduler_pg.py` — generalizar cadencia a dealers (entity_cadence).
- `scrapers/delta/remediation_dispatcher.py` — añadir `needs_research` post-cap (S4).

**Crear:**
- `scripts/migrations/0004_event_type_extend.{up,down}.sql`
- `scripts/migrations/0005_inventory_snapshot.{up,down}.sql`
- `scripts/migrations/0006_ingest_adapter.{up,down}.sql`
- `scripts/migrations/0007_api_keys.{up,down}.sql`
- `scrapers/delta/freshness_sentinel.py`
- `scrapers/ingest/legal_feed_worker.py` + `scrapers/ingest/normalizers/<format>.py`
- `services/entity_api/auth.py` (middleware + token-bucket)
- `services/entity_api/openapi.yaml`
- Tests: `test_freshness_sentinel.py`, `test_photo_change.py`, `test_inventory_snapshot.py`,
  `test_legal_feed_worker.py`, `test_entity_api_auth.py`.

## Decisiones clave
- MANTENER la API como VIEW read-only sin copia de datos (entity_inventory): la frescura viene del delta que escribe en PG, no de un rebuild. Ya es asi y es correcto, no introducir copia.
- UNIFICAR el feed de cambios en vehicle_events (extender event_type a PRICE_CHANGE/PHOTO_CHANGE/MILEAGE_CHANGE con columna detail JSONB) para que /delta sea el recurso canonico unico por entidad, manteniendo /price-changes como vista filtrada por compatibilidad.
- CERRAR el gap de PHOTO_CHANGE: hoy rich_consumer hace COALESCE de photo_urls y PIERDE la senal de cambio de foto. Capturar el array previo en la CTE prior (como ya hace con precio) y emitir el evento.
- SEPARAR explicitamente los dos planos de alerta ya existentes: operador (salud pipeline, Python, operator_alerts) vs cliente (arbitraje, Go, notify SSRF-hardened). No fusionarlos; reutilizar el notifier Go seguro como canal de salida externo para alertas operador criticas.
- ANADIR inventory_snapshot (fingerprint del set por entidad/ciclo) como base de versionado, deteccion de drift de volumen, verificacion adversarial cruzada y replay tras incidente.
- DISENAR la ingestion legal (XML/API) como un FLIP de canal (ingest_adapter.channel) que normaliza al MISMO contrato C7 y reusa todo el backbone: el delta, la API y las alertas no cambian. Periodo dual con scrape sombra y trust_score antes de confiar en el feed.
- ANADIR auth/scope/cuota al entity_api Python (hoy sin autenticacion) con tabla api_keys y scope per-entidad, para vender inventario aislado sin fugas entre entidades.
- NO forzar la fusion de las dos DLQ (Redis stream:dlq operacional vs SQLite dlq de URLs): son dominios distintos; documentar la frontera (YAGNI) en vez de un refactor especulativo.
- Verificacion adversarial por AGENTE SEPARADO del extractor, comparando por vias independientes (sitemap vs API vs SSR) y validando contenido sobre muestra, no solo conteos.
- Protocolo anti-'no se puede': tras agotar la auto-remediacion (MAX_REMEDIATIONS), estado needs_research dispara un agente de investigacion open-source antes de marcar una entidad como perdida.

## Riesgos
- GAP REAL: PHOTO_CHANGE no existe; el COALESCE de photo_urls en rich_consumer descarta la senal. Sin el fix, 'cambios de foto' del mandato no se cumple.
- GAP REAL: entity_api Python no tiene autenticacion (solo el Go). Vender inventario per-entidad sin auth/scope expone fuga de datos entre tenants - riesgo comercial y de seguridad.
- Dos sistemas de alerta paralelos (Python operador / Go cliente) pueden confundirse en operacion; el riesgo es duplicar logica o enviar al canal equivocado. Mitigado documentando la separacion.
- Dos DLQ (Redis stream:dlq vs SQLite dlq) y dos almacenes de cadencia/estado pueden divergir; sin documentacion de frontera, un incidente es dificil de diagnosticar.
- BUG-001/BUG-003 de STATUS.md (go.mod replace ambiguo, drop silencioso de payloads OEM en el pipeline Go) tocan el seam; el rich_consumer Python ya cubre el path pero el Go sigue como drop-in roto - riesgo si alguien lo reactiva.
- La cadencia (portal_cadence) cubre portales, no dealers individuales: ~49K dealers sin SLA de frescura explicito hasta generalizar a entity_cadence; cola larga puede quedar stale sin alerta.
- Ingestion legal: cada feed_format requiere un normalizador; sin verificacion adversarial (dual + trust_score) un feed legal erroneo o desactualizado contaminaria el inventario con apariencia de fuente confiable.
- Snapshot fingerprint por ciclo en entidades gigantes (AS24 ~92K coches) tiene coste de memoria en el worker al construir el set; necesita streaming/chunking para no romper el host RAM-light (~780MB).
- Extender event_type de vehicle_events con DROP/ADD CONSTRAINT sobre una tabla particionada grande puede tomar lock; ejecutar en ventana y validar NOT VALID->VALIDATE como ya hizo 0001 con las FKs.
- XAUTOCLAIM/PEL: si un worker crashea con muchos mensajes pendientes, el reclaim a 60s puede acumular backlog; bajo pico de descubrimiento masivo el delta podria retrasarse del objetivo sub-2s.