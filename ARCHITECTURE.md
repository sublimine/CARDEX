# CARDEX — Arquitectura Completa del Sistema

## Vision General

CARDEX es una plataforma de inteligencia vehicular pan-europea que indexa **cada vehiculo en venta** en DE, ES, FR, NL, BE y CH. No es un agregador (AutoUncle indexa 2.600 webs pasivamente) — CARDEX construye un **censo activo** con ground truth gubernamental, priorizacion inteligente de crawl, entity resolution cross-platform, y analytics de grado institucional.

**Stack**: Go (microservicios) + Python (scrapers) + Next.js 15 (frontend) + PostgreSQL 16 (OLTP) + ClickHouse (OLAP) + Redis 7.2+RedisBloom (streams/cache/bloom) + MeiliSearch (busqueda facetada) + Nginx (reverse proxy/TLS) + Prometheus/Grafana (monitoring).

**Servidor objetivo**: Hetzner AX102 (Ryzen 9 7950X3D, 128GB RAM, 2xNVMe).

---

## 1. Capa de Datos

### 1.1 PostgreSQL 16 (OLTP) — Puerto 5432

El sistema de registro principal. WAL logical habilitado para replicacion a ClickHouse. Extensiones: `uuid-ossp`, `pgcrypto`, `pg_trgm`, `btree_gist`, `hstore`.

**Tablas core (34 tablas en total):**

| Tabla | Proposito | PK | Filas estimadas |
|-------|-----------|-----|-----------------|
| `vehicles` | Inventario marketplace activo. Cada listing scrapeado/ingestado | ULID | 10M+ |
| `entities` | Dealers, flotas, instituciones. KYC, karma, suscripcion | ULID | 150K |
| `users` | Usuarios marketplace + dealers. Auth, email verificado | ULID | 500K |
| `user_roles` | RBAC: OWNER, MANAGER, SELLER, MECHANIC, VIEWER | (entity, user) | — |
| `dealer_inventory` | Stock propio del dealer (separado de scraping) | ULID | 1M |
| `crm_vehicles` | Lifecycle completo del vehiculo en CRM dealer (DealCar.io level) | ULID | 500K |
| `crm_contacts` | Clientes/compradores del dealer. GDPR consent, vault_dek_id | ULID | 2M |
| `crm_deals` | Contacto x Vehiculo x Stage pipeline | ULID | 1M |
| `crm_pipeline_stages` | Stages personalizables por dealer | ULID | — |
| `crm_communications` | Log de emails, llamadas, WhatsApp, SMS, visitas | ULID | 5M |
| `crm_documents` | Contratos, facturas, informes (S3/GCS/MinIO) | ULID | 2M |
| `crm_transactions` | P&L por vehiculo (compra, reconditioning, venta, impuestos) | ULID | 3M |
| `crm_recon_jobs` | Tracking taller: mecanica, carroceria, ITV, etc. | ULID | 500K |
| `crm_goals` | KPIs mensuales por dealer | ULID | — |
| `price_alerts` | Busquedas guardadas con notificacion (criteria JSONB) | ULID | 1M |
| `mandates` | Requests B2B dealer (criteria JSONB, target quantity) | ULID | 100K |
| `reservations` | Mutex de compra con GIST exclude constraint (no doble-lock) | ULID | — |
| `subscriptions` | Tiers: FREE, PRO, CROSS_BORDER, INSTITUTIONAL (Stripe) | ULID | — |
| `compute_credits` | Anti-MiCA: TTL 90 dias, non-transferable | ULID | — |
| `fleet_census` | Estadisticas gubernamentales (KBA, RDW, DGT, SDES, DIV, ASTRA) | BIGSERIAL | 500K |
| `coverage_matrix` | Cobertura computada: fleet x turnover x avg_dom vs. observed | BIGSERIAL | 100K |
| `crawl_frontier` | Estado Thompson Sampling por (platform, country, make, year) | BIGSERIAL | 50K |
| `entity_matches` | Cross-source matching: VIN exact + Fellegi-Sunter fuzzy | BIGSERIAL | 5M |
| `source_overlap_matrix` | Capture-recapture Lincoln-Petersen + Chapman correction | BIGSERIAL | — |
| `dealers` | Registro fisico de dealers (Google Places, registros oficiales) | BIGSERIAL | 150K |
| `scrape_jobs` | Tracking por-run de cada scraper | ULID | — |
| `vin_history_cache` | Cache denormalizado de eventos VIN | BIGSERIAL | 10M |
| `leads` | Inquiries de compradores (CRM inbound) | ULID | — |
| `publish_jobs` | Multiposting a plataformas externas | ULID | — |
| `publishing_listings` | Estado por plataforma de cada CRM vehicle | ULID | — |
| `marketing_audits` | Informes AI de mejora (scores + recomendaciones JSONB) | ULID | — |
| `audit_log` | Append-only inmutable (fillfactor=100) | ULID | — |
| `notifications` | In-app notifications por tipo (PRICE_ALERT, ARBITRAGE, etc.) | ULID | — |

**Esquema `vehicles` en detalle** (la tabla mas importante):

```sql
vehicle_ulid            TEXT PK
fingerprint_sha256      TEXT UNIQUE        -- dedup key
vin                     TEXT               -- 17-char si disponible
source_id               TEXT               -- ID original del portal
source_platform         TEXT               -- autoscout24_de, mobile_de, etc.
ingestion_channel       TEXT               -- SCRAPER, B2B_WEBHOOK, EDGE_FLEET
source_url              TEXT
source_country          TEXT               -- ISO 3166-1 alpha-2
photo_urls              TEXT[]
listing_status          TEXT               -- ACTIVE, SOLD, EXPIRED, REMOVED
thumb_url               TEXT               -- /thumb/{ulid}.webp (generado async)

-- Vehicle data
make, model, variant    TEXT
year                    INT
mileage_km              INT
color, fuel_type        TEXT
transmission            TEXT               -- MANUAL, AUTOMATIC, SEMI_AUTO
co2_gkm, power_kw      INT
doors                   INT

-- Pricing (Phases 4-6 del pipeline)
price_raw               NUMERIC
currency_raw            TEXT
gross_physical_cost_eur NUMERIC            -- Phase 4: FX-converted
net_landed_cost_eur     NUMERIC            -- Phase 5: +logistics+tax
logistics_cost_eur      NUMERIC
tax_amount_eur          NUMERIC
tax_status              TEXT               -- Phase 5 result
tax_confidence          NUMERIC

-- Scoring
legal_status            TEXT
risk_score              NUMERIC
liquidity_score         NUMERIC
cardex_score            NUMERIC
sdi_alert               TEXT               -- Seller Desperation Index zone
sdi_zone                TEXT

-- Geospatial
latitude, longitude     DOUBLE PRECISION
h3_index_res4           TEXT               -- H3 hex (~1,770 km2)
h3_index_res7           TEXT               -- H3 hex (~5.16 km2)

-- Lifecycle
lifecycle_status        TEXT               -- INGESTED->ENRICHED->CLASSIFIED->QUOTED->MARKET_READY->SOLD/EXPIRED
days_on_market          INT
first_seen_at           TIMESTAMPTZ
last_updated_at         TIMESTAMPTZ
sold_at                 TIMESTAMPTZ

-- Price tracking
price_drop_count        INT DEFAULT 0
last_price_eur          NUMERIC
re_listed               BOOLEAN

-- Quote (Phase 6)
current_quote_id        TEXT
quote_generated_at      TIMESTAMPTZ
quote_expires_at        TIMESTAMPTZ
target_country          TEXT

-- OCR
extracted_vin           TEXT
ocr_confidence          NUMERIC
```

16 indices cubriendo fingerprint, VIN, source, lifecycle, H3, NLC, score, make/model, tax, URL, listing_status, meili sync.

**Publicacion para ClickHouse**: `cardex_analytics_pub` replica todo menos PII (vin, raw_description, source_id, thumb_url excluidos).

**RLS habilitado** en: vehicles (lectura global), dealer_inventory, publishing_listings, leads, mandates (aislamiento por entity).

---

### 1.2 ClickHouse (OLAP) — Puertos 8123 (HTTP), 9000 (Native)

Analytics de alto rendimiento. Dos databases: `cardex` (analytics) y `cardex_forensics` (VIN history).

**Database `cardex`:**

| Tabla | Engine | Proposito | Particion | TTL |
|-------|--------|-----------|-----------|-----|
| `vehicle_inventory` | ReplacingMergeTree | Mirror OLAP de vehicles | toYYYYMM(first_seen_at) | 2 anos |
| `price_history` | MergeTree | Cada cambio de precio por vehiculo | toYYYYMM(event_date) | 3 anos |
| `price_index` | ReplacingMergeTree | Percentiles por segmento (p5-p95, mediana, media, DOM) | toYYYYMM(index_date) | 5 anos |
| `price_candles` | ReplacingMergeTree | OHLCV estilo TradingView (open=p10, high=p90, low=p5, close=mediana) | toYYYYMM(period_start) | 10 anos |
| `ticker_stats` | ReplacingMergeTree | Resumen por ticker (e.g. "BMW_3-Series_2020_DE_Gasoline") | — | — |
| `market_depth` | ReplacingMergeTree | Order book: listings por tier de precio (EUR 1K buckets) | toYYYYMM(snapshot_date) | 2 anos |
| `dom_distribution` | ReplacingMergeTree | Percentiles Days-on-Market | toYYYYMM(snapshot_date) | 2 anos |
| `demand_signals` | SummingMergeTree | Senales: SEARCH, ALERT_CREATED, DETAIL_VIEW, SHARE | toYYYYMM(signal_date) | 1 ano |
| `arbitrage_opportunities` | ReplacingMergeTree | Oportunidades cross-border (PRICE_DIFF, BPM_EXPORT, EV_SUBSIDY...) | toYYYYMM(scanned_at) | 90 dias |
| `arbitrage_route_stats` | ReplacingMergeTree | Estadisticas por ruta (DE->ES, NL->BE, etc.) | — | — |
| `coverage_snapshots` | ReplacingMergeTree | Snapshots diarios de cobertura por segmento | toYYYYMM(snapshot_date) | 3 anos |
| `crawl_efficiency` | MergeTree | Eficiencia de crawl: listings encontrados vs. nuevos, duracion | toYYYYMM(crawl_date) | 1 ano |

**Materialized Views:**

- `mv_daily_volume` (SummingMergeTree): volumen diario por plataforma/pais
- `mv_tax_distribution` (SummingMergeTree): distribucion por tax_status/pais
- `mv_platform_coverage` (SummingMergeTree): cobertura por plataforma/marca
- `mv_price_volatility` (ReplacingMergeTree): coeficiente de variacion semanal

**Database `cardex_forensics`:**

- `mileage_history`: Timeline de odometro por VIN
- `salvage_ledger`: Eventos de salvage/accidente por VIN

---

### 1.3 Redis 7.2 + RedisBloom — Puerto 6379

Configuracion: `maxmemory 2gb`, `maxmemory-policy volatile-lru`, `appendonly yes`, `appendfsync everysec`.

**Streams (14):**

| Stream | Consumer Group | Producer | Consumidor |
|--------|---------------|----------|------------|
| `stream:ingestion_raw` | cg_pipeline | Gateway | Pipeline |
| `stream:db_write` | cg_forensics | Pipeline | Forensics |
| `stream:classified` | cg_alpha | Pipeline | Alpha engine |
| `stream:forensic_updates` | cg_forensics | — | Forensics |
| `stream:meili_sync` | cg_meili_indexer | Pipeline + Thumbgen | Meili-Sync |
| `stream:publish_jobs` | cg_multipost | API | Publish workers |
| `stream:lead_events` | cg_crm | API | CRM |
| `stream:google_maps_raw` | cg_pipeline | Discovery | Pipeline |
| `stream:price_events` | cg_price_index | Pipeline | ClickHouse |
| `stream:demand_signals` | cg_analytics | API | Analytics |
| `stream:legal_audit_pending` | cg_gov | — | Legal |
| `stream:operator_events` | cg_karma | — | Karma |
| `stream:crawl_results` | cg_frontier | Scrapers | Frontier |
| `stream:thumb_requests` | cg_thumbgen | Pipeline + Backfill | Thumbgen |

**Bloom Filters:**

| Key | Capacidad | False Positive | Tamano | Proposito |
|-----|-----------|----------------|--------|-----------|
| `bloom:vehicles` | 50M | 0.01% | ~60MB | Dedup VIN/fingerprint |
| `bloom:listing_urls` | 100M | 0.01% | ~120MB | Dedup URLs (evita re-scrape) |
| `bloom:dealer_place_ids` | 5M | 0.1% | ~6MB | Dedup Google Places |
| `bloom:census_vins` | 20M | 0.1% | — | Dedup VINs censo |

**Hash Maps:**

- `fx_buffer`: 12 pares EUR (GBP, CHF, SEK, NOK, DKK, PLN, CZK, HUF, RON, BGN, HRK)
- `logistics:worst_case`: 12 paises -> coste transporte worst-case EUR
- `scraper:rate_limits`: 14 dominios -> RPS (0.2-0.3)
- `frontier:results:{platform}:{country}`: Resultados de crawl para Thompson

**Sorted Sets:**

- `frontier:priorities:{platform}`: Prioridades de crawl por plataforma (member=`{make}:{year}`, score=priority)
- `demand:top_models`: Top N modelos por demanda

**Sets:**

- `thumbgen:known_ulids`: ULIDs de thumbnails generados (para GC Phase 2)
- `proxy:pool`: Pool de proxies activos

**Lua Scripts:**

- `quote_mutex`: Lock atomico HMAC para cotizaciones (Phase 6)
- `credit_consume`: Consumo de creditos Anti-MiCA (TTL 90 dias)
- `rate_limiter`: Token bucket por dominio

---

### 1.4 MeiliSearch — Puerto 7700

Indice `vehicles` con respuestas <50ms.

```
Primary Key:    vehicle_ulid
Searchable:     make, model, variant, color, fuel_type, transmission
Filterable:     make, model, year, mileage_km, price_eur, source_country,
                fuel_type, transmission, listing_status, h3_res4
Sortable:       price_eur, mileage_km, year
```

Documentos incluyen: vehicle_ulid, make, model, variant, year, mileage_km, fuel_type, transmission, color, price_eur, source_country, source_platform, source_url, thumbnail_url, thumb_url, h3_res4, listing_status.

---

## 2. Servicios (Go)

### 2.1 Gateway — Puerto 8080 (container) -> 8090 (host)

**Funcion**: Punto de entrada para scraper data y webhooks B2B. Valida HMAC-SHA256, publica a `stream:ingestion_raw`.

**Protocolos**:

- **HTTP POST `/v1/ingest`**: Headers requeridos: `X-Partner-ID` (o `X-Scraper-Source`), `X-Cardex-Signature`. Firma: `HMAC(secret, "timestamp.body")`.
- **QUIC UDP:4433**: Edge fleet ingestion con Ed25519 signature verification. TLS obligatorio, ventana de timestamp +/-60s.
- **GET `/healthz`**: Health check para Docker.

**Seguridad**: Fail-closed — si HMAC secret no existe, el servicio no arranca. Si la firma es invalida, 401.

---

### 2.2 Pipeline — Consumer de `stream:ingestion_raw`

**Funcion**: Procesa cada vehiculo ingestado: dedup -> FX conversion -> H3 -> DB upsert -> publish downstream.

**Flujo por mensaje**:

1. **JSON decode** del payload vehicular
2. **Fingerprinting**: SHA256 de `vin:VIN:color:mileage` (o `url:sourceURL`, o `attr:color:0:mileage`)
3. **Bloom filter check**: `bloom:vehicles` — skip si existe
4. **FX conversion**: precio raw -> EUR via `fx_buffer` (fail-closed si FX falla o precio <EUR500 / >EUR2M)
5. **H3 geospatial**: lat/lng -> res4 + res7
6. **PostgreSQL upsert**: INSERT con ON CONFLICT en `fingerprint_sha256`. Trackea price drops.
7. **Publish a 4 streams**:
   - `stream:meili_sync` — **CRITICO**: si falla, no se ACK el mensaje (retry automatico)
   - `stream:db_write` — best-effort (forensics)
   - `stream:price_events` — best-effort (ClickHouse)
   - `stream:thumb_requests` — best-effort (si hay fotos)
8. **ACK** solo si meili_sync publico correctamente

**Backpressure**: Si `stream:db_write` tiene >50K mensajes pendientes, el pipeline se pausa 1s.

**Graceful shutdown**: WaitGroup + 30s drain en SIGTERM.

---

### 2.3 Meili-Sync — Consumer de `stream:meili_sync`

**Funcion**: Batch-indexa documentos en MeiliSearch. Soporta upsert y delete.

**Proteccion de thumbnails**: Si un documento llega con `thumb_url: null`, se elimina ese campo del map antes de enviarlo a MeiliSearch — asi no sobrescribe un thumb_url valido que ya exista.

**Batch**: 100 documentos o 5 segundos, lo que ocurra primero.

---

### 2.4 Scheduler — Orquestador de Jobs Periodicos

11 jobs con **advisory locks PostgreSQL** (previene ejecucion concurrente):

| Job | Schedule | Lock ID | Funcion |
|-----|----------|---------|---------|
| Materialize Price Index | Cada 4h | 100001 | Computa percentiles por segmento -> ClickHouse |
| Refresh FX Rates | Cada 6h | 100002 | Actualiza fx_buffer en Redis |
| Expire Stale Listings | Diario 03:00 | 100003 | ACTIVE -> EXPIRED si `last_updated_at` > 14 dias |
| Dispatch Scrape Jobs | — | 100004 | Orquesta scrapers |
| Prune VIN Cache | Semanal Dom 02:00 | 100005 | Limpia vin_history_cache viejo |
| Optimize ClickHouse | Semanal Dom 04:00 | 100006 | OPTIMIZE TABLE en todas las tablas |
| Materialize Price Candles | Cada 4h | 100007 | OHLCV candles -> ClickHouse |
| Compute Ticker Stats | Cada 4h | 100008 | Estadisticas por ticker |
| Compute Arbitrage | Cada 4h | 100009 | Oportunidades cross-border |
| Entity Resolution | Diario 06:00 | 100010 | VIN exact + Fellegi-Sunter fuzzy matching |
| Source Overlap | Diario 05:00 | 100011 | Lincoln-Petersen + Chapman capture-recapture |

**Entity Resolution** (2 fases):

1. **VIN Exact**: Self-join en vehicles con VIN=17 chars, `DISTINCT ON (vin, source_platform)` para evitar duplicados intra-plataforma. Confidence 1.0.
2. **Fellegi-Sunter**: Bucketing por (make, model, year), comparacion cross-platform. Scoring: make+model+year (+2.0) + mileage <=500km (+1.5) + price <=5% (+1.0) + H3 res7 (+1.5) + color (+0.5) + mileage >5000km penalty (-1.0). Threshold: 5.0/6.5. Max bucket: 500 candidatos.

**Source Overlap** (Chapman-corrected):

```
Chapman N = ((n1+1)(n2+1)) / (m2+1) - 1
Varianza  = ((n1+1)(n2+1)(n1-m2)(n2-m2)) / ((m2+1)^2 * (m2+2))
IC 95%    = N +/- 1.96 x sqrt(Var)
```

---

### 2.5 Census — Ingestor de Censo de Flotas Gubernamentales

**6 fuentes implementadas**:

| Fuente | Pais | API/URL |
|--------|------|---------|
| KBA (Kraftfahrt-Bundesamt) | DE | GENESIS API (direct CSV stub) |
| RDW | NL | Open Data API (requiere token) |
| DGT (Direccion General de Trafico) | ES | sedeapl.dgt.gob.es |
| SDES | FR | data.gouv.fr |
| DIV (Statbel) | BE | statbel.fgov.be |
| ASTRA (BFS) | CH | dam-api.bfs.admin.ch + PxWeb JSON |

**Flujo**: Fetch con retry (3 intentos, backoff exponencial 1s/2s/4s + jitter +/-25%) -> upsert a `fleet_census` -> compute `coverage_matrix` cada 6h -> publish a Redis -> replicate a ClickHouse.

**Formula de cobertura**:

```
expected_for_sale = fleet_count x turnover_rate(0.12) x avg_dom(45) / 365
coverage          = observed_count / expected_for_sale
economic_value    = (expected - observed) x median_price_eur
```

**Logging de descarte**: Si >10% de filas CSV son malformadas, warning con tasa exacta.

---

### 2.6 Frontier — Motor de Priorizacion de Crawl

**Composite Scoring** (5 senales, pesos suman 1.0):

```
priority = 0.30 x InfoGain + 0.25 x EconValue + 0.20 x Freshness + 0.15 x Demand + 0.10 x Thompson

InfoGain   = -log2(coverage), normalizado [0,1], cap en log2(0.10)
EconValue  = economic_value / max_economic_value
Freshness  = 1 - exp(-0.05 x hours_since_crawl)    // half-life ~14h
Demand     = log1p(alert_count) / log1p(max_alerts) // de price_alerts activos
Thompson   = Beta(alpha, beta) sample               // Marsaglia-Tsang gamma method
```

**Warm start**: Al arrancar, seed 5000 prioridades iniciales desde `coverage_matrix` (segmentos con coverage <50%, ordenados por economic_value).

**Publicacion**: Redis sorted sets `frontier:priorities:{platform}` con TTL 2h. 32 plataformas cubiertas.

**Plataformas cubiertas**:

- **DE (7)**: autoscout24_de, mobile_de, kleinanzeigen_de, heycar_de, pkw_de, automobile_de, autohero_de
- **ES (8)**: autoscout24_es, coches_net, milanuncios, wallapop, autocasion, motor_es, coches_com, flexicar
- **FR (7)**: autoscout24_fr, leboncoin, lacentrale, paruvendu, largus_fr, caradisiac_fr, ouestfrance_auto
- **NL (4)**: autoscout24_nl, marktplaats, autotrack, gaspedaal
- **BE (3)**: autoscout24_be, 2dehands, gocar
- **CH (3)**: autoscout24_ch, tutti, comparis

**Thompson learning loop**: Scrapers reportan resultados a `frontier:results:{platform}:{country}`. Frontier actualiza alpha/beta cada hora. Estado persistido a `crawl_frontier` cada 2h.

---

### 2.7 Thumbgen — Generador de Thumbnails Legales

**Base legal**: BGH I ZR 69/08 "Vorschaubilder" — thumbnails de motor de busqueda son uso legitimo.

**Flujo**:

1. Consume de `stream:thumb_requests` (vehicle_ulid, image_url)
2. **SSRF check**: Rechaza URLs internas (RFC1918, loopback, link-local, metadata)
3. **Download**: Headers de Chrome (no CardexBot), max 5MB, timeout 15s
4. **Content-type validation**: Solo acepta image/jpeg, image/png, image/webp
5. **Decode + Resize**: CatmullRom a 400px ancho, mantiene aspect ratio
6. **Encode**: Semaforo limita a CPU/4 encoders concurrentes. cwebp via stdin pipe (sin temp file) con timeout 30s. Fallback a JPEG Q75.
7. **Store**: `/data/thumbs/{ulid[:2]}/{ulid}.webp`
8. **DB update**: `vehicles.thumb_url = /thumb/{ulid}.webp` (con error check — si PG falla, borra el archivo)
9. **MeiliSearch notify**: Publica partial update a `stream:meili_sync`
10. **Track**: SADD a `thumbgen:known_ulids`

**Backfill**: Cada 6h, encuentra hasta 10K vehiculos ACTIVE sin thumb_url y los encola.

**GC** (cada 24h):

- Phase 1: Borra thumbs de vehiculos SOLD/EXPIRED/REMOVED (DB-driven)
- Phase 2: Sample 2000 ULIDs de `thumbgen:known_ulids`, verifica existencia en DB, borra huerfanos

**Optimizaciones**: Connection pooling (MaxIdleConns:64, MaxConnsPerHost:16), stdin pipe a cwebp (elimina 2 disk I/Os).

---

### 2.8 API — Puerto 8080

**73+ endpoints** organizados en:

**Marketplace (publico, 120 req/min)**:

- `GET /api/v1/marketplace/search` — MeiliSearch con facets (make, model, fuel, country, tx, year)
- `GET /api/v1/marketplace/listing/{ulid}` — Detalle completo + demand signal async
- `POST/GET/DELETE /api/v1/marketplace/alerts` — Price alerts

**Analytics (publico, ClickHouse)**:

- `price-index` — OHLCV candles (day/week/month, 2 anos)
- `market-depth` — Order book por tier EUR 1K
- `demand` — Time series busquedas/views/alerts
- `heatmap` — H3 hexagonos con count + avg price
- `dom` — Days-on-market percentiles
- `volatility` — Coeficiente de variacion 30d rolling
- `mds` — Market Days Supply
- `turn-time` — Prediccion de dias hasta venta

**TradingCar (publico)**:

- `candles`, `tickers`, `scanner`, `compare` — Datos financieros de vehiculos

**Arbitrage (publico reads, JWT books)**:

- `opportunities` — Diferenciales cross-border
- `routes` — Estadisticas por ruta origen->destino
- `nlc/{ticker}/{origin}/{dest}` — Breakdown NLC
- `book/{opportunity_id}` — Reservar oportunidad

**Census Intelligence (publico)**:

- `coverage-matrix` — Cobertura por segmento
- `gaps` — Gaps ordenados por economic_value
- `population-estimate` — Chapman capture-recapture + IC 95%
- `coverage-heatmap` — H3 coverage map

**VIN History (publico)**:

- `GET /api/v1/vin/{vin}` — OSINT + mileage forensics

**Dealer SaaS (JWT, 600 req/min)**:

- Inventory CRUD + import URL
- Publishing/multiposting (AutoScout24 XML feed, CSV export)
- Leads management
- Pricing intelligence (posicion vs. mercado)
- SDI (Seller Desperation Index)
- NLC Calculator (ES, FR, NL)
- Marketing audit trigger

**CRM completo (JWT)**:

- Dashboard, Vehicles CRUD, Contacts CRUD, Deals CRUD
- Pipeline Kanban view
- Communications log (email, phone, WhatsApp, SMS, visit)
- Reconditioning jobs
- Financial P&L por vehiculo
- Goals/KPIs mensuales
- Documents (contratos, facturas, etc.)

**Auth (5 req/min)**:

- Register, Login (JWT RS256), Refresh, Forgot/Reset password, Email verify

**Admin (JWT + RequireAdmin)**:

- Stats dashboard, Entity/User management, Scraper status

**Middleware**: RequestID -> Logger -> CORS -> Recover -> Auth (JWT RS256 con fallback HS256 dev)

**Rate limiting**: Redis sliding window (sorted sets por IP o entity).

---

## 3. Scrapers (Python 3.12 Async)

### 3.1 Arquitectura

6 contenedores Docker, uno por territorio. Cada uno ejecuta `run_all.py` con `SCRAPER_TARGETS` configurado.

| Container | Targets |
|-----------|---------|
| scraper-de | autoscout24_de, mobile_de, kleinanzeigen_de, heycar_de, pkw_de |
| scraper-es | autoscout24_es, coches_net, wallapop, milanuncios, autocasion |
| scraper-fr | autoscout24_fr, leboncoin, lacentrale, paruvendu |
| scraper-nl | autoscout24_nl, marktplaats, autotrack, gaspedaal |
| scraper-be | autoscout24_be, 2dehands, gocar |
| scraper-ch | autoscout24_ch, comparis, tutti |

### 3.2 Estrategia de Crawl (3 niveles)

1. **Sitemap mode** (100% cobertura): Parse robots.txt -> discover sitemaps -> filtrar por listing patterns -> crawl cada URL
2. **Frontier-directed**: Lee `frontier:priorities:{platform}` de Redis -> crawl high-priority shards primero
3. **Blind fallback**: Iterar ALL_MAKES (70+ marcas) x YEARS (2000-2025)

**Descomposicion make x year**: Rompe el cap de paginacion de los portales (tipicamente 20-50 paginas x 50 resultados). Para cada shard, pagina hasta que el portal devuelve menos items que page_size.

### 3.3 Componentes

- **BaseScraper**: Clase abstracta. Maneja cursores (Redis), deteccion de ban (3 consecutivos = pausa 1h), Bloom filter dedup, heartbeat, rate limiting
- **FrontierClient**: Lee prioridades de Redis sorted sets, reporta resultados para Thompson learning
- **GatewayClient**: Envia listings al Gateway con HMAC-SHA256. Bloom pre-check. PII stripping. Retry 4x con backoff exponencial
- **HTTPClient**: httpx async, HTTP/2, User-Agent `CardexBot/1.0`, rate limiting token bucket por dominio, proxy support, backoff en 429/503
- **ProxyManager**: Pool en Redis (`proxy:pool` SET), afinidad geografica, dead proxy exclusion 30min
- **RobotsChecker**: Respeta robots.txt, crawl-delay, Allow/Disallow
- **SitemapParser**: Recursive sitemap index, .xml.gz support, depth limit 5
- **PlaywrightClient**: Para portales JS-heavy. Headless, bloquea images/fonts/media
- **Normalizer**: Canonicalizacion multi-idioma de fuel, transmission, price, mileage, power, CO2

### 3.4 Modelo de Datos

`RawListing`: source_platform, source_country, source_url, source_listing_id, make, model, variant, year, mileage_km, fuel_type, transmission, body_type, color, vin, power_kw, co2_gkm, doors, seats, price_raw, currency_raw, city, region, latitude, longitude, seller_type, photo_urls, thumbnail_url, listing_status, description_snippet.

---

## 4. Frontend (Next.js 15)

### 4.1 Stack

Next.js 15 App Router, Server Components, Tailwind CSS dark theme, MeiliSearch client-side search (<50ms), lucide-react icons.

### 4.2 Rutas

**Marketplace publico**:

- `/` — Landing con 4 pilares
- `/search` — Busqueda facetada con filtros (country, fuel, year, price, mileage, tx), sort (relevance, price, mileage, year), paginacion 24/page
- `/listing/{ulid}` — Detalle con galeria, specs, SDI badge, precio, "View on [source]" CTA

**Analytics**:

- `/analytics` — Price charts, market depth, heatmaps
- `/analytics/tradingcar` — Trading car view

**VIN**:

- `/vin` — Formulario de lookup (gratis, sin registro)
- `/vin/{vin}` — Informe completo

**Dealer Portal** (JWT):

- `/dashboard` — Hub principal
- `/dashboard/login`, `/register`, `/forgot-password`, `/reset-password`
- `/dashboard/inventory`, `/inventory/new`
- `/dashboard/crm`, `/crm/contacts`, `/crm/inventory`, `/crm/pipeline`, `/crm/vehicles/{ulid}`
- `/dashboard/pricing/{ulid}`, `/leads`, `/audit`, `/notifications`, `/publish`, `/vin-valuation`

**Arbitrage**:

- `/arbitrage` — Analisis de spreads cross-border

### 4.3 Componentes clave

- **VehicleImage**: Usa `thumbUrl` del API (no hardcoded). Fallback a SVG silueta CARDEX. Legal: BGH Vorschaubilder, zero third-party requests.
- **ListingCard**: Thumbnail, titulo, precio, specs, SDI badge, country flag, CTAs
- **SearchBar/FilterSidebar/SortSelect**: Client components que manipulan URL params

---

## 5. Nginx — Puerto 443

**Funciones**: TLS termination, rate limiting, reverse proxy, static caching.

**Upstreams**: `cardex_api` (api:8080, keepalive 32), `cardex_web` (web:3000, keepalive 16).

**Rate limiting zones**:

- `api_global`: 60 req/min + burst 20
- `api_search`: 120 req/min + burst 30
- `api_auth`: 5 req/min + burst 3

**Locations**:

- `/thumb/` -> `/data/thumbs/` (30d cache, immutable, fallback a placeholder.svg)
- `/api/` -> `cardex_api` (rate limited, proxy headers, 30s timeout)
- `/api/v1/auth/` -> strict rate limit
- `/api/v1/marketplace/search` -> relaxed limit + 10s cache
- `/_next/static/` -> `cardex_web` (365d cache, immutable)
- `/` -> `cardex_web` (Next.js SSR)
- `/healthz` -> API health (no logging, no rate limit)
- `/robots.txt` -> inline (Allow /, Disallow /api/ + /dashboard/)

**Security headers**: HSTS (2 anos, preload), X-Frame-Options SAMEORIGIN, X-Content-Type-Options nosniff, Referrer-Policy strict-origin-when-cross-origin, Permissions-Policy (no camera/mic).

**TLS**: TLSv1.2+1.3, ECDHE+AES-GCM ciphers, OCSP stapling, session cache 10m.

---

## 6. Monitoring

**Prometheus** (puerto 9090): Scrape 15s. Targets: gateway, pipeline, forensics, alpha, legal (todos :9091), ClickHouse (:9363), nodo01-03 node exporters (:9100).

**Grafana** (puerto 3000): Dashboards de pipeline throughput, scraper coverage, price index lag.

**Pendiente**: AlertManager, Redis exporter, PG exporter (referencias comentadas en prometheus.yml).

---

## 7. Docker Compose — 30 servicios

| Servicio | Imagen/Build | Puerto | Health Check | Resources |
|----------|-------------|--------|-------------|-----------|
| postgres | postgres:16-bookworm | 5432 | pg_isready | 4 CPU, 2GB |
| clickhouse | clickhouse-server:latest | 8123, 9000 | SELECT 1 | 4 CPU, 2GB |
| redis | redis-stack-server:latest | 6379 | redis-cli ping | 2 CPU, 2GB |
| meilisearch | meilisearch:latest | 7700 | curl /health | 2 CPU, 1GB |
| redis-init | alpine/curl | — | one-shot | — |
| pg-seed | postgres:16-alpine | — | one-shot | — |
| meili-seed | alpine/curl | — | one-shot | — |
| api | services/api/Dockerfile | 8080 | depends | — |
| pipeline | services/pipeline/Dockerfile | — | depends | — |
| meili-sync | services/pipeline/Dockerfile (CMD: meili-sync) | — | depends | — |
| gateway | services/gateway/Dockerfile | 8090->8080 | wget /healthz | — |
| scheduler | services/scheduler/Dockerfile | — | depends | — |
| census | services/census/Dockerfile | — | depends | — |
| frontier | services/frontier/Dockerfile | — | depends | — |
| thumbgen | services/imgproxy/Dockerfile | — | depends | — |
| scraper-de/es/fr/nl/be/ch | scrapers/Dockerfile | — | depends (gateway healthy) | — |
| web | apps/web/Dockerfile | 3001->3000 | depends | — |
| prometheus | prom/prometheus:latest | 9090 | — | — |
| grafana | grafana/grafana:latest | 3000 | — | — |

**Volumes**: pg_data, ch_data, redis_data, meili_data, grafana_data, thumbs.

**Orden de arranque**: postgres/clickhouse/redis -> redis-init -> pg-seed/meili-seed -> pipeline/api/scheduler/census/frontier/thumbgen/meili-sync -> gateway -> scrapers -> web.

---

## 8. Flujo de Datos End-to-End

```
                    +---------------------------------------------+
                    |           GOVERNMENT APIs                    |
                    |  KBA . RDW . DGT . SDES . DIV . ASTRA      |
                    +-----------------------+---------------------+
                                            |
                                            | fleet_census (PG)
                                            v
                    +--------------------------+
                    |       CENSUS SERVICE      |
                    |  coverage_matrix (PG)     |----------> ClickHouse
                    |  publish to Redis         |            coverage_snapshots
                    +-------------+------------+
                                  |
                                  | coverage data
                                  v
+-------------+    +--------------------------+
|  SCRAPERS   |<---|     FRONTIER SERVICE      |
| 27 portals  |read| Thompson + InfoGain +     |
| 6 paises    |pri | EconValue + Freshness +   |
+------+------+ori | Demand                    |
       |       ties+-----------^--------------+
       |                       |
       | report results        | Thompson update
       | HMAC-signed           |
       v                       |
+-------------+                |
|   GATEWAY   |                |
|  HTTP/QUIC  |                |
+------+------+                |
       |                       |
       | stream:ingestion_raw  |
       v                       |
+-----------------------------+|
|        PIPELINE             ||
| Dedup -> FX -> H3 -> DB    ||
+-----------------------------+|
| +-> stream:meili_sync ------> MEILI-SYNC -> MeiliSearch
| +-> stream:db_write --------> Forensics
| +-> stream:price_events ----> ClickHouse price_history
| +-> stream:thumb_requests --> THUMBGEN -> /data/thumbs/ -> Nginx
|           |                  |
|       PostgreSQL             |
|       (vehicles)             |
+-----------------------------+
       |
       v
+-----------------------------+
|        SCHEDULER            |
| Price Index -> ClickHouse   |
| Entity Resolution -> PG    |----> (feeds frontier via coverage)
| Source Overlap -> PG        |
| FX Rates -> Redis           |
| Stale Listing Expiry        |
+-----------------------------+
       |
       v
+-----------------------------+
|            API              |
| 73+ endpoints               |
| Marketplace + Analytics     |
| VIN + Dealer SaaS + CRM    |
| Arbitrage + TradingCar      |
| Census Intelligence         |
+--------------+--------------+
               |
               v
+-----------------------------+    +-------------------+
|          NGINX              |<-->|   NEXT.JS WEB     |
| TLS + Rate Limit + Cache   |    | SSR + Client      |
| /thumb/ static serve        |    | Dark Theme        |
+-----------------------------+    +-------------------+
               |
               v
       Users / Dealers / B2B Partners
```

---

## 9. Seguridad

| Capa | Mecanismo |
|------|-----------|
| **Ingesta** | HMAC-SHA256 fail-closed (Gateway), Ed25519 para QUIC |
| **Auth** | JWT RS256 (prod) / HS256 (dev fallback) |
| **RBAC** | user_roles: OWNER, MANAGER, SELLER, MECHANIC, VIEWER |
| **RLS** | PostgreSQL Row Level Security en 5 tablas (entity isolation) |
| **Rate limiting** | Nginx zones (3 tiers) + Redis sliding window (IP/entity) |
| **SSRF** | Thumbgen rechaza RFC1918, loopback, link-local, metadata |
| **Content validation** | Solo image/jpeg, image/png, image/webp en thumbgen |
| **TLS** | TLSv1.2+1.3, HSTS 2 anos preload, OCSP stapling |
| **Headers** | X-Frame-Options, X-Content-Type-Options, CSP implicito, Referrer-Policy |
| **PII** | Scrapers strip seller_phone/address. ClickHouse pub excluye VIN/description |
| **GDPR** | Privacy by Design: thumbnails propios (zero third-party IP leaks), consent tracking en CRM |
| **Encryption** | vault_dek_id en entities/users/contacts para field-level encryption |
| **Anti-MiCA** | Compute credits con TTL 90 dias, non-transferable |
| **Advisory locks** | pg_try_advisory_lock en los 11 scheduler jobs |
| **Legal** | BGH I ZR 69/08 para thumbnails, Database Directive 96/9/EC compliance |

---

## 10. Resumen Numerico

| Metrica | Valor |
|---------|-------|
| Tablas PostgreSQL | 34 |
| Tablas ClickHouse | 16 (+ 4 materialized views) |
| Redis Streams | 14 |
| Bloom Filters | 4 |
| Servicios Go | 8 (api, gateway, pipeline, meili-sync, scheduler, census, frontier, thumbgen) |
| Scrapers Python | 27 portales en 6 contenedores |
| API Endpoints | 73+ |
| Docker Services | 30 |
| Paises cubiertos | 6 (DE, ES, FR, NL, BE, CH) |
| Plataformas indexadas | 32 |
| Entidades dealer objetivo | ~150,000 |
