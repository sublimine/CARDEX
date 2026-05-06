# CARDEX — BACKLOG
<!-- Generado 2026-05-06. Orden: impacto en producto > deuda técnica > operacional -->
<!-- Para ejecutar en sesión larga con Claude Max ×20 -->

---

## BLOQUE 1 — Scrapers: diagnóstico y reparación (prioridad máxima)

- [ ] **Diagnosticar AS24 ×6** — ¿cambio de patrón JSON o CF escalado?
  - Ejecutar `py -m scrapers.diag` y leer output real
  - Si es patrón: actualizar regex en `common/autoscout24.py`
  - Si es CF: evaluar curl_cffi chrome124 → chrome130, o Playwright fallback
  - AS24 es el portal más grande de Europa — sin esto el producto no tiene DE/ES/FR/NL/BE/CH cubiertos

- [ ] **Verificar Playwright SPAs en producción** (~15 scrapers sin confirmar)
  - `py -m scrapers.diag_all` + `py -m scrapers.diag_pw`
  - Clasificar cada portal: funciona / bloqueado / patrón incorrecto
  - Reparar los que sean fixables (patrón o selector)
  - Portales objetivo: heycar, autohero, pkw, automobile (DE), coches.net, wallapop, autocasion (ES), largus, ouestfrance (FR), gocar (BE), comparis (CH)

- [ ] **Reemplazar DDG worker** — DDG HTML está anomaly-blocked, resolver no funcional
  - Integrar Brave Search API (gratis hasta 2k/mes) o Bing Web Search
  - Sin esto: miles de dealers BMW STOLO + SIRENE + Zefix + OSM sin website nunca se indexan
  - Archivo: `scrapers/discovery/sources/ddg_resolver.py` + `scrapers/discovery/ddg_worker.py`

- [ ] **Fix XADD hang Spoticar** — documentado en session 2026-04-10, nunca aplicado
  - `scrapers/sitemap_indexer.py` líneas ~235-240: chunking 10k por batch
  - Sin fix: cualquier sitemap >500k URLs cuelga el bridge indefinidamente

- [ ] **Integrar auto-api.com** (si trial aprobado)
  - Consumer Go: poll `/changes` cada 60s → normalizar → XADD stream:mobile_de_events
  - Mapear campos al schema de vehicle_index
  - ~150-200 líneas de Go idiomático

---

## BLOQUE 2 — Backend: gaps de producto

- [ ] **Price change detection** — crítico para arbitraje
  - `vehicle_events` necesita tipo `PRICE_CHANGE`
  - enrich_worker debe comparar precio actual vs. `vehicle_index.precio` antes de UPDATE
  - Si delta > umbral configurable → emitir PRICE_CHANGE event
  - Conectar con tabla `price_alerts` ya definida en schema

- [ ] **Staleness monitoring por dealer**
  - Vista o query: `SELECT source_domain, MAX(last_seen) FROM vehicle_index GROUP BY source_domain ORDER BY MAX(last_seen) ASC`
  - Alerta si algún dealer lleva >24h sin re-crawl
  - Exponer en Grafana dashboard (prometheus + grafana ya montados)

- [ ] **Migraciones numeradas**
  - Toda evolución futura de schema via `migrations/000N_descripcion.sql`
  - El `init-pg.sql` solo para entornos frescos
  - Crítico antes de cualquier deploy con datos reales persistentes

---

## BLOQUE 3 — Scrapers: cobertura adicional

- [ ] **Tier 1 bloqueados — evaluar consumer APIs directas**
  - `milanuncios.es`: ¿tiene API interna como mobile.de? Recon con `tools/recon_oem.py`
  - `leboncoin.fr`: DataDome — difícil, valorar proxy residencial cuando haya revenue
  - `lacentrale.fr`: DataDome — ídem

- [ ] **Discovery pipeline — ampliar cobertura**
  - Verificar BOVAG NL (`scrapers/discovery/sources/bovag.py`) — nuevo desde 04-10
  - Verificar CT logs (`scrapers/discovery/sources/ct_logs.py`) — nuevo desde 04-10
  - Añadir BORME ES, OffeneRegister DE cuando volumen justifique

- [ ] **Wallapop ES** — `py -m playwright install chromium` + verificar en producción

---

## BLOQUE 4 — Infraestructura y operaciones

- [ ] **BUG-001**: `e2e/go.mod` replace path → ajustar a `=> ../services/alpha`
- [ ] **BUG-002**: Import `"fmt"` sin uso en `services/pipeline/cmd/pipeline/main.go:12`
- [ ] **BUG-003**: Drop silencioso de payloads OEM en pipeline Go — verificar y fix
- [ ] **ADRs pendientes** (8 decisiones tomadas sin documentar) — `docs/adr/`
- [ ] **slog audit** — `grep -r "log/slog" ./cmd ./pkg` — cada consumer sin slog es deuda
- [ ] **go vet + golangci-lint** limpio en todos los módulos

---

## BLOQUE 5 — Producto (cuando scrapers estén estables)

- [ ] **API pública para traders** — `/api/v1/search?country=DE&make=BMW&price_max=20000`
- [ ] **Alertas de precio** — tabla `price_alerts` ya existe, conectar con PRICE_CHANGE events
- [ ] **Coverage matrix** — tabla `coverage_matrix` ya existe, poblarla con estado real por país/fuente
- [ ] **Frontend** — React/Vite montado, conectar con datos reales

---

## BLOQUE 6 — Arquitectura del fleet de scraping (rediseño completo)

### Decisión: NO 1 scraper por país. Fleet por tipo de tecnología.

**Por qué no por país:**
- AS24 es la misma tecnología en 6 países — si lo arreglas, lo arreglas una vez para todos
- Playwright es caro (browser pool) — no quieres 6 procesos cada uno con su propio Chromium
- Si el scraper-DE se cae, pierdes mobile.de + AS24 + kleinanzeigen + heycar al mismo tiempo

**Por qué por tipo de tecnología:**
- Los portales se agrupan naturalmente por su stack anti-bot, no por su geografía
- Un agente que conoce curl_cffi maneja AS24 DE + ES + FR + NL + BE + CH con el mismo motor
- Un pool de 4 Chromium stealth sirve a todos los Playwright SPAs de los 6 países
- Cuando un tipo de bypass deja de funcionar, lo parcheas en un solo lugar

---

### Arquitectura objetivo

```
┌─────────────────────────────────────────────────────────────┐
│                    COORDINATOR (scheduler Go)                │
│  Despacha trabajos, monitoriza salud, gestiona backpressure │
└──────────┬──────────────┬──────────────┬────────────────────┘
           │              │              │
    ┌──────▼──────┐ ┌─────▼──────┐ ┌────▼──────────────────┐
    │ SITEMAP     │ │ CURL FLEET │ │  PLAYWRIGHT FLEET      │
    │ FLEET       │ │            │ │                        │
    │ N workers   │ │ M workers  │ │  Pool 4 Chromium       │
    │ ya existe   │ │ por portal │ │  stealth compartido    │
    └──────┬──────┘ └─────┬──────┘ └────┬───────────────────┘
           │              │              │
           └──────────────┴──────────────┘
                          │
                   ┌──────▼──────┐
                   │ vehicle_    │
                   │ index (PG)  │
                   │ + events    │
                   │ + streams   │
                   └─────────────┘
```

---

### SITEMAP FLEET (ya existe, escalar)
**Qué maneja:** renew×4, toyota×2, marktplaats, 2dehands, autotrack + toda la long tail de dealers vía discovery pipeline
**Cómo:** `sitemap_indexer.py` + `sitemap_bridge.py` como daemons
**Concurrencia:** hasta 20 sitemaps en paralelo (ya implementado)
**Delta:** INSERT new + DELETE stale nativo — el mejor delta posible
**Acción pendiente:**
- [ ] Fix XADD chunking 10k para sitemaps >500k URLs (Spoticar)
- [ ] Escalar N workers cuando el backlog de discovery_candidates crezca

---

### CURL FLEET (nuevo diseño)
**Qué maneja:**
```
AS24 × 6         DE/ES/FR/NL/BE/CH    curl_cffi chrome124  segmentado
mobile.de        DE                   consumer API /search/srp (si no auto-api)
kleinanzeigen    DE                   curl_cffi chrome124
tutti            CH                   httpx básico
```
**Concurrencia:** 1 AsyncSession por portal, portales en paralelo entre sí
**JA3:** un solo `AsyncSession(impersonate="chrome124")` por sesión de portal — nunca mezclar
**Rate limiting:** 1.2s entre requests dentro de un portal, portales distintos en paralelo
**Adaptive segmentation para AS24:**
```python
# Si un segmento devuelve exactamente 400 URLs (cap hit):
# → split automático añadiendo dimensión 'make' o 'region'
# → re-query los sub-segmentos hasta que ninguno toque el cap
# Garantiza cobertura completa sin pérdida silenciosa
```
**Health check:** si portal devuelve 0 URLs en 3 ciclos consecutivos → alerta + pausa automática
**Acción pendiente:**
- [ ] Diagnosticar AS24 y reparar
- [ ] Implementar adaptive segmentation en `common/autoscout24.py`
- [ ] Añadir health check 0-URL por portal con alerta a Grafana
- [ ] Crear `scrapers/common/curl_fleet.py` — runner que despacha todos los portales curl en paralelo con backpressure

---

### PLAYWRIGHT FLEET (nuevo diseño)
**Qué maneja:**
```
heycar           DE    intercept XHR
autohero         DE    intercept XHR
pkw_de           DE    DOM extraction
automobile_de    DE    DOM extraction
coches_net       ES    intercept XHR
coches_com       ES    intercept XHR
wallapop         ES    intercept XHR
autocasion       ES    DOM
flexicar         ES    DOM
largus           FR    intercept XHR (CF Turnstile)
ouestfrance      FR    iframe + DOM
gocar            BE    intercept XHR
comparis         CH    intercept XHR
mobile_de        DE    intercept XHR (fallback si consumer API no funciona)
```
**Pool de browsers:** 4 instancias Chromium stealth compartidas (playwright-stealth v2.0.3)
**Por qué 4 y no 14:** CF y anti-bots detectan cuando el mismo IP tiene 10 browsers concurrentes. 4 es el balance entre throughput y perfil de ruido aceptable.
**Queue:** los portales entran en cola, se asignan a la primera instancia libre
**Sesión por portal:** cada portal usa su propia sesión con cookies y fingerprint independiente. No reutilizar sesión entre portales distintos.
**Rate:** 1 portal activo por instancia Chromium. Sin paralelismo dentro de un mismo portal.
**Acción pendiente:**
- [ ] Crear `scrapers/common/pw_fleet.py` — pool manager con asyncio.Queue
- [ ] Verificar cada portal con `py -m scrapers.diag_pw` y clasificar
- [ ] Para los que fallen: determinar si es patrón de extracción o anti-bot
- [ ] Implementar session warmup (visita homepage antes de buscar listings)

---

### API CONSUMERS (Go, nuevo)
**Qué maneja:** auto-api.com `/changes` y futuros data providers
**Arquitectura:**
```go
// Poll /changes cada 60s
// Normalizar payload → vehicle_index schema
// XADD stream:mobile_de_events
// enrich_worker consume el stream
```
**Acción pendiente:**
- [ ] Implementar cuando trial auto-api.com confirmado
- [ ] Archivo: `services/pipeline/cmd/mobile_de_consumer/main.go`

---

### COORDINATOR (Go scheduler — ya existe como `scheduler` service)
**Responsabilidades:**
- Despachar ciclos por portal con CYCLE_WAIT_SECONDS configurable por portal
- Health checks: si portal lleva >2 ciclos con 0 URLs → alerta Grafana + pausa
- Staleness: si dealer lleva >24h sin last_seen → re-encolar
- Backpressure: si Redis stream:enrich_pending > 1M items → pausar nuevos ciclos
**Acción pendiente:**
- [ ] Auditar `services/scheduler` — qué hace hoy vs. qué debería hacer
- [ ] Añadir health check de portales con métricas a Prometheus

---

### Tabla resumen: cobertura objetivo con fleet completo

| Portal | Fleet | País | Volumen est. | Estado actual |
|---|---|---|---|---|
| AS24 ×6 | curl | todos | 500k+ | Roto — prioridad |
| mobile.de | api consumer / curl | DE | 1.5M | Pendiente auto-api |
| kleinanzeigen | curl | DE | 50k | Verificar |
| tutti | curl | CH | 10k | Verificar |
| renew×4 | sitemap | DE/FR/ES/BE | 35k | ✅ Funciona |
| toyota×2 | sitemap | DE/FR | 1k | ✅ Funciona |
| marktplaats | sitemap | NL | 200k | ✅ Funciona |
| autotrack | sitemap | NL | 50k | ✅ Funciona |
| 2dehands | sitemap | BE | variable | ✅ Funciona |
| Long tail dealers | sitemap | todos | millones | ✅ Funciona |
| heycar, autohero, pkw | playwright | DE | 30k | Sin verificar |
| coches.net, wallapop | playwright | ES | 200k | Sin verificar |
| largus, ouestfrance | playwright | FR | 50k | Sin verificar |
| gocar, comparis | playwright | BE/CH | 30k | Sin verificar |
| leboncoin | — | FR | 1M | Bloqueado DataDome |
| lacentrale | — | FR | 300k | Bloqueado DataDome |
| milanuncios | — | ES | 500k | Bloqueado Akamai |
| gaspedaal | — | NL | 200k | Bloqueado DPG WAF |

---

## Estrategia de ejecución para sesión larga

```
Orden recomendado:
1. diag AS24 → fix o decisión → AS24 resuelto o descartado
2. diag Playwright SPAs → clasificar → reparar los fixables
3. DDG worker replacement → Brave API
4. XADD chunking fix
5. Price change detection
6. Implementar curl_fleet.py + pw_fleet.py
7. auto-api.com integration (si trial OK)
8. Coordinator health checks + Grafana alerts
9. Resto del backlog
```
