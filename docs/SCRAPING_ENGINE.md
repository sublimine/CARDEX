# CARDEX SCRAPING ENGINE — Diseño Definitivo 360°

<!-- v1.1.0 | 2026-05-19 | Owner: Elias Karrouch -->
<!-- Documento de arquitectura. No implementación. La implementación está en scrapers/engine/ (pendiente). -->

## Principio rector

> Una identidad digital es un activo financiero. Se construye, se protege, se envejece, y se jubila. Nunca se descarta.

Todo lo demás deriva de este principio.

---

## Vista general del sistema

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                        CARDEX SCRAPING ENGINE                               ║
╠══════════════╦══════════════╦═══════════════╦══════════════╦════════════════╣
║  ACQUISITION ║  COLLECTION  ║   PIPELINE    ║ INTELLIGENCE ║ OBSERVABILITY  ║
║              ║              ║               ║              ║                ║
║ Identity     ║ Sitemap      ║ Delta Engine  ║ WAF          ║ Prometheus     ║
║ Engine       ║ Fleet        ║               ║ Classifier   ║ + Grafana      ║
║              ║              ║               ║              ║                ║
║ Proxy        ║ curl_cffi    ║ Enrich        ║ Schema       ║ Softblock      ║
║ Fleet        ║ Fleet (T1)   ║ Pipeline      ║ Validator    ║ Detector       ║
║              ║              ║               ║              ║                ║
║ Anti-        ║ Browser      ║ Quality       ║ Poison       ║ Alerting       ║
║ Detect Stack ║ Fleet (T2)   ║ Gates         ║ Detector     ║ Rules          ║
║              ║              ║               ║              ║                ║
║ Session      ║ Behavioral   ║ DLQ           ║              ║                ║
║ Manager      ║ Fleet (T3)   ║ Handler       ║              ║                ║
║              ║              ║               ║              ║                ║
║ Intent       ║ Mobile       ║               ║              ║                ║
║ Engine       ║ API (T0)     ║               ║              ║                ║
║              ║              ║               ║              ║                ║
║ Tier Router  ║              ║               ║              ║                ║
╚══════════════╩══════════════╩═══════════════╩══════════════╩════════════════╝
                                      │
                    ╔═════════════════╧═══════════════════╗
                    ║            DATA STORES               ║
                    ║  engine.db (SQLite WAL) — estado     ║
                    ║  vehicle_index (PG) — inventario     ║
                    ║  Redis Streams — eventos             ║
                    ╚═════════════════════════════════════╝
```

---

## SUBSISTEMA A — ACQUISITION

### A1. Identity Engine

Una identidad es la unidad atómica del sistema. Todo request parte de una identidad.

**Anatomía de una identidad:**

```
Identity {
    id:               UUID permanente — nunca reutilizado
    country:          DE|ES|FR|NL|BE|CH
    status:           new → warming → active → degraded → quarantine → retired

    # Capa de red
    proxy_ip:         IP asignada (ISP/residential/mobile)
    proxy_tier:       isp_sticky | residential_rotating | mobile
    proxy_provider:   decodo | oxylabs | bright_data
    tcp_profile:      windows_11 | macos_14 | ubuntu_22

    # Capa TLS + HTTP
    tls_profile:      chrome136 | firefox147 | safari260
    http_version:     3

    # Capa browser
    fingerprint: {
        user_agent:           coherente con tls_profile
        screen:               {width, height, colorDepth, pixelRatio}
        webgl:                {vendor, renderer, extensions[]}
        canvas_noise:         float seed fijo por identidad
        audio_noise:          float seed fijo por identidad
        fonts:                subset real de Windows/macOS
        platform:             Win32 | MacIntel
        hardware_concurrency: 4|8|12|16
        device_memory:        4|8|16
        timezone:             Europe/Berlin | Europe/Paris | ...
        locale:               de-DE | fr-FR | es-ES | nl-NL | ...
        webrtc_ip:            IP coherente con proxy_ip (mismo país)
        do_not_track:         null
    }

    # Capa de sesión
    storage_state:    Playwright storageState (cookies + localStorage)
    abck_tokens: {
        "autoscout24.de": {token, expires, trust_level, request_count},
        "mobile.de":      {token, expires, trust_level, request_count},
    }
    browsing_history: []  # últimas 50 URLs visitadas

    # Métricas de vida
    trust_score:      0.0 → 10.0
    request_count:    int
    ban_count:        int
    warming_done:     bool
    created_at:       timestamp
    last_used:        timestamp
    retired_at:       timestamp | null
    retire_reason:    ban_cascade | trust_collapsed | ip_dead | manual | null
}
```

**Invariantes del Identity Engine:**

1. `tcp_profile` + `tls_profile` + `fingerprint` son generados como conjunto coherente. Nunca mezclados de fuentes distintas.
2. `fingerprint.webrtc_ip` siempre del mismo país que `proxy_ip`. Enforced en creación, re-validado antes de cada sesión.
3. `canvas_noise` y `audio_noise` son seeds fijos por identidad. Mismo seed = mismo hash siempre → hardware consistente entre visitas.
4. `trust_score` += 0.05 por request exitosa. -= 1.0 por soft-block. -= 3.0 por hard-block. < 0 → quarantine 48h. < -5.0 → retired.
5. Identidades con `trust_score ≥ 7.0` son **PREMIUM** — asignadas solo a portales con Akamai Enterprise o DataDome.

**Lifecycle:**

```
new → warming (24-72h tráfico orgánico) → active → degraded → quarantine → retired
                                            ↑                      ↓
                                            └──── recuperación ────┘
```

**Protocolo de warming — 3 fases:**

```
FASE 1 — Ambient (48h)
  Objetivo: que la IP parezca usuario residencial orgánico antes de tocar portales.
  Tráfico: 40-60 requests/día a news (spiegel.de, lemonde.fr, rtve.es...),
           búsquedas Google (no sobre coches), YouTube.
  Sin visitas a portales objetivo.
  Resultado: ISP/AS ve patrón de navegación orgánica. IP no "fresca".

FASE 2 — Portal familiarization (24h)
  Objetivo: generar cookies reales y primera _abck en el portal objetivo.
  Tráfico: homepage del portal + categorías (sin extracción).
           1 o 2 listings visitados (dwell 30-60s, scroll, salir).
  Resultado: storage_state con cookies reales. _abck generado y persistido.
             Akamai registra la identidad como "usuario recurrente nivel 1".

FASE 3 — Active (trust_score ≥ 3.0, warming_done = true)
  Extracción permitida vía Intent Engine.
  Cada sesión: entry point → homepage → search → extract → exit (§A5).
  _abck refreshed con hyper-sdk-go si age > 1h.

Regla de warming: una identidad que extrae antes de completar Fase 2 es quemada.
  No existe recovery — se retira directamente.
```

---

### A2. Proxy Fleet

Tres pools con propósito exclusivo. Nunca mezclados.

| Pool | Proveedor | Propósito | Rotación |
|---|---|---|---|
| ISP_STICKY | Decodo | AS24 ×6, kleinanzeigen, coches.net | Sticky 4h por sesión |
| RESIDENTIAL_ROTATING | Oxylabs | leboncoin, lacentrale (DataDome) | Nueva IP por sesión, NO por request |
| MOBILE | Decodo Mobile | Fallback ASN datacenter bloqueado | Bajo demanda |

**Proxy Health Monitor:**
- `success_rate` < 0.7 → `soft_degraded`
- `success_rate` < 0.5 → `quarantine_24h`
- Proxies en quarantine nunca asignados a identidades premium

---

### A3. Anti-Detection Stack — 4 capas simultáneas

```
CAPA 1 — TCP/IP (httpcloak, Go, CAP_NET_RAW)
  windows_11:  TTL=128, Window=65535, options=[MSS, NOP, WS=8, NOP, SACK]
  macos_14:    TTL=64,  Window=65535, options=[MSS, NOP, WS=6, SACK, TS, NOP, NOP]
  ubuntu_22:   TTL=64,  Window=29200, options=[MSS, SACK, TS, NOP, WS=7]
  Invariante:  tcp_profile DEBE ser coherente con user_agent. Chrome/Windows → windows_11.

CAPA 2 — TLS + HTTP (curl_cffi ≥ 0.15.1)
  session = AsyncSession(impersonate=identity.tls_profile, http_version=3, proxy=identity.proxy_url)
  Invariante: sesión creada UNA VEZ por sesión. JA3 coherente p1→pN.

CAPA 3 — Browser (Camoufox — patches C++, no JS)
  browser = AsyncCamoufox(os=..., fingerprint=..., proxy=..., geoip=True)
  geoip=True: alinea WebRTC + timezone + locale automáticamente con la IP del proxy.

  Señales cubiertas por Camoufox nativamente (C++, sin JS inyectado):
  ┌─────────────────────────────────────┬──────────────────────────────────────┐
  │ Señal                               │ Implementación                       │
  ├─────────────────────────────────────┼──────────────────────────────────────┤
  │ Canvas fingerprint                  │ Ruido determinista por identity seed  │
  │ Audio fingerprint (OfflineAudio)    │ Ruido determinista por identity seed  │
  │ Fonts disponibles                   │ Subset real Windows/macOS             │
  │ WebGL vendor/renderer               │ Coherente con tcp_profile             │
  │ navigator.webdriver                 │ Ausente — parchado a nivel C++        │
  │ navigator.plugins                   │ PluginArray real de Firefox           │
  │ Battery API                         │ Firefox no expone getBattery() → OK   │
  │ navigator.connection                │ Firefox no expone NetworkInfo → OK    │
  │ screen geometry coherencia          │ outerWidth/innerWidth con chrome real │
  │ performance.now() precision         │ Resolución normal, no reducida        │
  │ PointerEvent.pointerType            │ "mouse" coherente                     │
  └─────────────────────────────────────┴──────────────────────────────────────┘

  Señales adicionales SOLO para Chromium fallback (JS en pw_base.py):
  ┌─────────────────────────────────────┬──────────────────────────────────────┐
  │ Señal                               │ Solución aplicada                    │
  ├─────────────────────────────────────┼──────────────────────────────────────┤
  │ navigator.webdriver                 │ delete + Object.defineProperty       │
  │ navigator.plugins (PluginArray)     │ 3 PDF plugins con prototype correcto  │
  │ chrome.runtime completo             │ Objeto con connect/sendMessage/id    │
  │ permissions.query notifications     │ Devuelve Notification.permission      │
  │ WebGL vendor Intel                  │ getParameter override                 │
  │ iframe.contentWindow.webdriver      │ Override en cross-frame access        │
  │ hardwareConcurrency / deviceMemory  │ 8 / 8                                 │
  │ window.outerWidth/outerHeight       │ innerWidth+17 / innerHeight+74 (chrome bar) │
  │ Battery API (getBattery)            │ Promise resolve {level:0.95,charging:true}  │
  │ navigator.connection                │ undefined (no exponer NetworkInfo)    │
  └─────────────────────────────────────┴──────────────────────────────────────┘

  Señales NO cubiertas en ningún tier — aceptadas como riesgo residual:
  - Behavioral entropy (mouse movement, scroll velocity): cubierto en T3 por Oxymouse
  - CSS media query fingerprint (prefers-color-scheme): varianza baja, riesgo bajo
  - DNS-over-HTTPS coherencia: proxy maneja DNS, sin gap

CAPA 4 — Sensor (Akamai _abck)
  Si token previo existe → cargar en storageState → usuario recurrente para Akamai
  Si no existe → browser navega, sensor JS genera token → persistir
  Si token expirado → hyper-sdk-go refresh (sin browser)
```

---

### A4. Session Manager

```
SESSION_STATE per identity per domain {
    storage_state:  Playwright JSON (cookies + localStorage)
    abck:           {token, trust_level, expires}
    ak_bmsc:        {token, expires}   # corta vida, regenerar cada 4h
    bm_sz:          string             # seed para Akamai v3
    last_page_url:  string             # Referer coherente en próxima sesión
    visit_count:    int
    last_visit:     timestamp
}
```

**Protocolo de carga (antes de cada request):**
1. Cargar storage_state → browser context
2. Validar _abck expiry → si < 1h → refresh con hyper-sdk-go
3. Inyectar Referer = last_page_url
4. Verificar coherencia IP ↔ WebRTC ↔ timezone → abort si incoherente

**Protocolo de guardado (tras sesión exitosa):**
1. Extraer storage_state actualizado
2. Extraer _abck actualizada
3. Actualizar last_page_url + visit_count
4. Persistir en engine.db
5. trust_score += 0.05

---

### A5. Intent Engine

```
BuyerPersona {
    id:                   string
    country:              string
    search_params:        {make?, model?, year_min?, year_max?, budget?, fuel?}
    entry_point:          google_search(70%) | direct(20%) | bookmark(10%)
    max_pages:            randint(2, 9)
    click_through_rate:   0.15 - 0.35
    comparison_rate:      0.40
    back_button_rate:     0.60
    listing_dwell_s:      (15, 90)
    results_dwell_s:      (5, 25)
    between_page_s:       (3, 12)
    uses_filters:         bool
}

Session Navigation Plan:
  1. ENTRY:   URL con Referer de Google Search real
  2. LANDING: homepage + dwell + scroll orgánico
  3. SEARCH:  filtros del portal o URL directa con params
  4. BROWSE:  páginas con dwell, click-through, back button, comparison
             → EXTRACT URLs de paso (no secuencial obvio)
  5. EXIT:    navegar fuera del portal antes de cerrar
```

**20 buyer personas por país (100 total).** Cada sesión se asigna una persona aleatoria compatible con el portal.

---

### A6. Tier Router

```
DOMAIN_TIER_REGISTRY (ground truth verificado por diag.py):
  autoscout24.*:   T2 (Akamai Bot Manager v3) → escalate T3
  mobile.de:       T1 → escalate T2
  kleinanzeigen:   T1
  leboncoin.fr:    T3 (DataDome behavioral)
  lacentrale.fr:   T3 (DataDome behavioral)
  2dehands.be:     T0 (API pública)
  marktplaats.nl:  T1
  coches.net:      T1 → escalate T2
  wallapop.com:    T2 → escalate T3
  gocar.be:        T2
  comparis.ch:     T2
  tutti.ch:        T1
```

**Circuit Breaker por (tier, domain):**

```
CLOSED → 3 fallos en 60s → OPEN (120s) → HALF_OPEN → 1 probe → CLOSED|OPEN
```

Cuando tier entra en OPEN → escalator activa siguiente tier. Cambio persiste en engine.db.

---

---

## SUBSISTEMA A7 — MOBILE REVERSE ENGINEERING (T0 Bypass)

> T0 no tiene anti-bot porque no usa el web. Accede a la API interna de la app móvil.
> Un request de API es 50-200x más barato que un request de browser con Camoufox.

### Proceso de RE (una vez por portal, resultado permanente)

```
PASO 1 — Intercepción de tráfico
  Herramienta: mitmproxy con certificado instalado en emulador Android
  Bypass certificate pinning: frida-gadget + script unpinning universal
  Resultado: dump de todos los requests HTTP/2 de la app

PASO 2 — Spec generation
  mitmproxy2swagger → spec OpenAPI preliminar
  Revisión manual: identificar endpoints de búsqueda y listing
  Documentar: auth flow, headers requeridos, rate limits observados

PASO 3 — Client generado
  scrapers/mobile_re/portals/<portal>.py
  Auth: Bearer token (OAuth2 app) o API key embebida en la app
  Endpoint: búsqueda paginada → lista de IDs → detalle por ID

PASO 4 — Token refresh
  Tokens de app expiran (normalmente 24-72h)
  Refresh automático: scrapers/mobile_re/interceptor.py con frida headless
```

### Portales con RE confirmado / viable

```
mobile.de:     Ad-Stream WebSocket (WSS) — ya documentado en clients/mobile_de/
autoscout24:   App usa misma API que web pero con app-specific headers
               → mismo endpoint pero requiere X-AS24-App: ios/2.x.x header
               RE viable: bypassea Akamai completamente

Portales pendientes de RE:
  leboncoin.fr  — DataDome en web → RE móvil = bypass total
  lacentrale.fr — idem
  wallapop.com  — app muy activa, API bien documentada externamente
```

### Coste vs Browser

```
T0 Mobile API:   0.001 req/s proxy cost, 0 browser RAM, 0 Camoufox warming
T2 Camoufox:     0.08 req/s proxy cost, 200MB RAM, 24-72h warming
Ratio:           T0 es 80x más barato operacionalmente que T2

Inversión inicial RE: ~4h por portal (una vez)
ROI: amortizado en primera semana de producción
```

---

## SUBSISTEMA B — COLLECTION

### Las 4 flotas

| Tier | Herramienta | Portales | Concurrencia | RAM |
|---|---|---|---|---|
| T0 — Mobile API | HTTP directo | mobile.de Ad-Stream, AS24 post-RE | N/A | mínima |
| T1 — curl_cffi | AsyncSession chrome136 + httpcloak | kleinanzeigen, coches.net, autotrack, gaspedaal, paruvendu, largus, tutti, motor.es | 200 req/s por worker | ~150MB/worker |
| T2 — Camoufox | AsyncCamoufox + storageState + _abck | AS24 ×6, wallapop, gocar, heycar, autohero, comparis, ouestfrance | 8-10 instancias | ~200MB/instancia |
| T3 — Camoufox + Behavioral | T2 + Oxymouse + CapSolver + residential FR | leboncoin, lacentrale | 3-4 instancias | ~250MB/instancia |

**Regla de asignación:** solo identidades con `trust_score ≥ 7.0` son elegibles para T3.

### Sitemap Fleet (expandir de 7 a 50+ fuentes)

```
Estrategia: sitemap-first siempre que exista.
Sitemap bien parseado = inventario completo sin anti-bot.

Expandir SITEMAP_SOURCES a:
  - Todos los dealers individuales del discovery pipeline
  - Portales de marca (Spoticar, Selekt, Certified, Motorpoint)
  - Aggregadores regionales europeos

Delta con lastmod + ETag conditional (304 = cero bytes).
Costo: casi cero. Sin proxies, sin browsers.
```

---

## SUBSISTEMA C — PIPELINE

### C1. Delta Engine — mejoras sobre el existente

```
Añadir sobre la implementación actual:

1. price_hash = SHA256(precio || moneda || estado_venta)
   Cambio → emitir PRICE_CHANGE event (crítico para arbitraje)

2. ETag per listing URL (no solo por sitemap):
   HEAD con If-None-Match → 304 = skip completo
   Ahorro estimado: 60-70% de bandwidth en listings estáticos

3. Scheduling adaptativo:
   Con cambio reciente:    next_scrape = now + 1h
   Sin cambio 7 días:      next_scrape *= 1.5 (máx 30 días)
   Con cambio detectado:   next_scrape /= 2   (mínimo 1h)
```

### C2. Enrichment Pipeline — 3 etapas en cascada

```
STAGE 1 — JSON-LD (implementado, sólido)
  Éxito en ~60% de listings

STAGE 2 — OG/Meta tags (implementado, sólido)
  Fallback cuando JSON-LD ausente

STAGE 3 — LLM extraction (NUEVO)
  Cuando stage 1 y 2 fallan (~40% de listings)
  Model: Haiku 4.5 (coste mínimo, tarea determinista)
  Input: HTML limpio, primeros 2000 tokens
  Output: JSON estructurado {titulo, precio, km, año, carrocería, combustible}
  NO en el critical path — enrichment offline asíncrono
```

### C3. Quality Gates

```
GATE 1 — Structural validity
  precio ∈ (0, 500000) EUR
  año ∈ (1980, año_actual+1)
  kilometraje ∈ (0, 1500000)
  URL es deep-link (no root domain)

GATE 2 — Poison detection (Cloudflare AI Labyrinth)
  JSON-LD @type ≠ Vehicle/Car/Product → reject
  HTML < 15KB → flag
  Ratio texto/código > 0.8 → flag
  Imágenes apuntan a Cloudflare CDN → flag
  2+ flags activos → POISON_DETECTED → discard

GATE 3 — Cross-source coherence
  Mismo VIN, precio diferente en dos fuentes → PRICE_DISCREPANCY event

GATE 4 — Staleness
  last_seen > 30 días sin re-confirmación → GONE event automático
```

### C4. DLQ Handler

```
dlq_reason → recovery_action:
  fetch_error:     retry con nueva identidad en 1h
  parse_error:     alert humano → schema validation
  poison_detected: discard permanente
  soft_block:      retry con identidad premium en 24h
  rate_limited:    retry según Retry-After header
```

---

## SUBSISTEMA D — INTELLIGENCE

### D1. WAF Classifier (para dominios nuevos)

```
1. HEAD sin proxy → si 403 inmediato: waf_active=true, nivel=high
2. GET con curl_cffi → analizar headers:
   CF-Ray        → Cloudflare
   x-datadome-*  → DataDome
   ak_bmsc cookie → Akamai confirmado
   "Just a moment" en body → CF challenge
3. Registrar en domain_tier_state con verified_at=now()
4. Verificar con diag.py en modo verbose
```

### D2. Schema Validator

```
schema_fp = hash(regex_pattern + extraction_method + sample_count)

Tras cada ciclo:
  new_fp ≠ stored_fp → alert + pause portal + DLQ todos los pending
```

### D3. Poison Detector (Cloudflare AI Labyrinth)

```
SEÑALES DE POISON (2+ activas → reject):
  1. JSON-LD @type = Article|BlogPosting
  2. HTML < 15KB
  3. Ratio texto/código > 0.8
  4. Precio ausente en portal que siempre tiene precio
  5. Imágenes en CDN de Cloudflare en lugar del CDN del portal
  6. VIN ausente en portal que siempre lo incluye
  7. HTML response es idéntico para URLs diferentes (honeypot)
```

---

## SUBSISTEMA E — OBSERVABILITY

### Métricas Prometheus

```
# Por portal + tier
scraper_requests_total{portal, tier, status_code}
scraper_request_duration_seconds{portal, tier}     # histogram
scraper_urls_collected_total{portal, country}
scraper_null_field_rate{portal}                    # CRÍTICO: > 15% = soft block
scraper_poison_detected_total{portal}

# Por identidad
identity_trust_score{identity_id, country}
identity_ban_count{identity_id, country}
identity_status{identity_id, status}

# Por proxy
proxy_success_rate{proxy_ip, tier, country}
proxy_ban_count_24h{proxy_ip, provider}

# Pipeline
pipeline_delta_new_total{source, country}
pipeline_delta_gone_total{source, country}
pipeline_enrich_success_rate{source}
pipeline_dlq_size
pipeline_price_change_total{source, country}

# Sistema
warming_pool_size           # identidades listas (status=active, warming_done=true)
premium_identity_count      # trust_score ≥ 7.0
circuit_breaker_state{domain, tier}
```

### 5 Alertas que importan (sin ruido)

```yaml
- alert: SoftBlockCascade
  expr: scraper_null_field_rate > 0.15
  for: 10m
  severity: critical

- alert: PremiumPoolExhausted
  expr: premium_identity_count < 3
  for: 5m
  severity: warning

- alert: ScraperStale
  expr: time() - scraper_last_success_timestamp > 7200
  for: 5m
  severity: critical

- alert: DLQGrowing
  expr: rate(pipeline_dlq_size[1h]) > 100
  for: 15m
  severity: warning

- alert: SchemaChangeDetected
  expr: scraper_schema_change_total > 0
  for: 1m
  severity: critical
```

---

## SUBSISTEMA F — RESILIENCE

### Matriz de fallos completa

| Fallo | Detección | Respuesta automática |
|---|---|---|
| Soft block (200 sin datos) | null_field_rate > 15% en 10 requests | Quarantine identidad, rotar backup, retry |
| Hard block (403/429) | HTTP status | Quarantine 48h, ban_count++, trust_score -= 3.0 |
| IP ban permanente | Connection refused desde múltiples identidades con mismo proxy | Retire proxy + identidades asociadas |
| Schema change | schema_fp diverge | Pause portal, DLQ todos los pending, alert |
| Circuit breaker open | State machine | Escalate al siguiente tier automáticamente |
| Proxy pool degradado | success_rate < 0.7 en > 50% del pool | Alert + activar pool mobile emergencia |
| Warming pool vacío | warming_pool_size < 5 | Iniciar warming de nuevas identidades |
| Poison cascade | poison_detected spike en mismo portal | Pause portal, discard batch, alert |
| Proxy proveedor down | Timeout > 80% proxies del proveedor | Fail-over automático a proveedor secundario |

---

## DATA MODEL COMPLETO

### engine.db (SQLite WAL)

```sql
CREATE TABLE identities (
    id                TEXT PRIMARY KEY,
    country           CHAR(2) NOT NULL,
    status            TEXT NOT NULL DEFAULT 'new',
    proxy_ip          TEXT NOT NULL,
    proxy_tier        TEXT NOT NULL,
    proxy_provider    TEXT NOT NULL,
    tcp_profile       TEXT NOT NULL,
    tls_profile       TEXT NOT NULL,
    fingerprint       JSON NOT NULL,
    storage_state     BLOB,
    abck_tokens       JSON DEFAULT '{}',
    trust_score       REAL DEFAULT 0.0,
    request_count     INT DEFAULT 0,
    ban_count         INT DEFAULT 0,
    warming_done      INT DEFAULT 0,
    warming_started   INT,
    created_at        INT NOT NULL,
    last_used         INT,
    retired_at        INT,
    retire_reason     TEXT
);
CREATE INDEX idx_id_country_status ON identities(country, status, trust_score DESC);

CREATE TABLE domain_tier_state (
    domain            TEXT NOT NULL,
    tier              TEXT NOT NULL,
    waf               TEXT DEFAULT 'unknown',
    circuit_state     TEXT DEFAULT 'closed',
    fail_count        INT DEFAULT 0,
    success_rate      REAL DEFAULT 1.0,
    effective_tier    TEXT,
    verified_at       INT,
    last_fail         INT,
    last_success      INT,
    PRIMARY KEY (domain, tier)
);

CREATE TABLE proxy_health (
    proxy_ip          TEXT PRIMARY KEY,
    tier              TEXT NOT NULL,
    provider          TEXT NOT NULL,
    country           CHAR(2) NOT NULL,
    success_rate      REAL DEFAULT 1.0,
    ban_count_24h     INT DEFAULT 0,
    status            TEXT DEFAULT 'active',
    last_ban_at       INT,
    last_success_at   INT
);

CREATE TABLE work_queue (
    id                TEXT PRIMARY KEY,
    portal            TEXT NOT NULL,
    country           CHAR(2) NOT NULL,
    tier              TEXT,
    identity_id       TEXT,
    filter_params     JSON,
    status            TEXT DEFAULT 'pending',
    priority          INT DEFAULT 5,
    attempts          INT DEFAULT 0,
    last_error        TEXT,
    created_at        INT NOT NULL,
    scheduled_at      INT NOT NULL,
    started_at        INT,
    completed_at      INT
);
CREATE INDEX idx_wq_scheduled ON work_queue(status, scheduled_at) WHERE status = 'pending';

CREATE TABLE dlq (
    url_hash          TEXT PRIMARY KEY,
    url               TEXT NOT NULL,
    portal            TEXT NOT NULL,
    fail_count        INT DEFAULT 1,
    dlq_reason        TEXT NOT NULL,
    last_error        TEXT,
    first_fail        INT NOT NULL,
    last_fail         INT NOT NULL,
    retry_after       INT
);

CREATE TABLE schema_registry (
    portal            TEXT PRIMARY KEY,
    schema_fp         TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    sample_count      INT DEFAULT 0,
    verified_at       INT NOT NULL,
    last_change_at    INT
);

CREATE TABLE warming_schedule (
    identity_id       TEXT NOT NULL,
    target_domain     TEXT NOT NULL,
    phase             INT NOT NULL,
    requests_done     INT DEFAULT 0,
    requests_target   INT NOT NULL,
    started_at        INT,
    completed_at      INT,
    PRIMARY KEY (identity_id, target_domain, phase)
);
```

### Adiciones a vehicle_index (PG)

```sql
ALTER TABLE vehicle_index ADD COLUMN price_hash       TEXT;
ALTER TABLE vehicle_index ADD COLUMN prev_price        NUMERIC(12,2);
ALTER TABLE vehicle_index ADD COLUMN price_changed_at  TIMESTAMPTZ;
ALTER TABLE vehicle_index ADD COLUMN http_etag         TEXT;
ALTER TABLE vehicle_index ADD COLUMN next_scrape_at    TIMESTAMPTZ;
ALTER TABLE vehicle_index ADD COLUMN scrape_interval_h REAL DEFAULT 24.0;
ALTER TABLE vehicle_index ADD COLUMN enrichment_stage  INT DEFAULT 0;
ALTER TABLE vehicle_index ADD COLUMN poison_flag       BOOL DEFAULT FALSE;
```

---

## TOPOLOGÍA DE DESPLIEGUE (CX42 MVP)

```
Proceso 1:     coordinator (Go)             ~200MB
Proceso 2-4:   curl_cffi workers (Python)   3 × 150MB = 450MB
Proceso 5-12:  Camoufox pool (Python)       8 × 200MB = 1.6GB
Proceso 13:    sitemap_indexer (Python)     ~100MB
Proceso 14:    enrich_worker (Python)       ~150MB
Proceso 15:    warming_daemon (Python)      ~100MB
Proceso 16:    monitoring (Go)              ~50MB

Total RAM: ~2.7GB de 16GB
Buffer: 13.3GB libre para PG, Redis, picos, OS
```

---

## ESTRUCTURA DE DIRECTORIOS TARGET

```
scrapers/
├── engine/
│   ├── identity/
│   │   ├── profile.py       # BrowserForge — genera identidades coherentes
│   │   ├── store.py         # SQLite — identidades como activos
│   │   ├── coherence.py     # Enforcer: IP ↔ TZ ↔ locale ↔ WebRTC ↔ DNS
│   │   └── aging.py         # trust_score lifecycle
│   ├── proxy/
│   │   ├── pool.py          # Pool manager con health por proxy
│   │   ├── tiers.py         # ISP / Residential / Mobile
│   │   ├── affinity.py      # Mismo proxy por dominio por sesión
│   │   └── health.py        # Ban detector
│   ├── antidetect/
│   │   ├── tcp.py           # httpcloak: TCP SYN Windows/macOS fingerprint (npcap en Windows)
│   │   ├── tls.py           # curl_cffi session factory — impersonate por identity.tls_profile
│   │   ├── browser.py       # Camoufox instance pool — señales C++, no JS
│   │   ├── stealth_js.py    # Stealth JS Chromium fallback — outerWidth, battery, connection...
│   │   ├── sensor.py        # Akamai _abck store + hyper-sdk-go refresh sin browser
│   │   └── behavioral.py    # Oxymouse + dwell + scroll simulation para T3
│   ├── session/
│   │   ├── state.py         # storageState persistence
│   │   ├── warming.py       # Protocolo de warming 24-72h
│   │   ├── intent.py        # Buyer personas + navigation plans
│   │   └── conditioning.py  # homepage → search → browse antes de scrape
│   ├── router/
│   │   ├── classifier.py    # Dominio → tier requerido
│   │   ├── escalator.py     # T1 → T2 → T3 on failure
│   │   ├── circuit.py       # Circuit breaker por (tier, domain)
│   │   └── domain_map.py    # DOMAIN_TIER_REGISTRY
│   └── monitoring/
│       ├── metrics.py       # Prometheus metrics
│       ├── softblock.py     # Null field rate detector
│       └── alerts.py        # Alertmanager rules
├── portals/                 # Reemplaza scrapers/de/, es/, fr/, etc.
│   ├── base.py              # BasePortalScraper
│   ├── partition.py         # Estrategia filtros para superar cap de 2000
│   ├── de/{autoscout24,mobile_de,kleinanzeigen,heycar,autohero}.py
│   ├── es/{autoscout24,coches_net,milanuncios,wallapop,autocasion}.py
│   ├── fr/{autoscout24,leboncoin,lacentrale,paruvendu,largus}.py
│   ├── nl/{marktplaats,autotrack,gaspedaal}.py
│   ├── be/{tweedehands,gocar}.py
│   └── ch/{autoscout24,tutti}.py
├── mobile_re/               # Bypass total del web anti-bot
│   ├── interceptor.py       # mitmproxy wrapper
│   ├── mapper.py            # mitmproxy2swagger → OpenAPI spec
│   ├── client.py            # Cliente de API móvil mapeada
│   └── portals/
│       ├── autoscout24.py   # AS24 mobile API (post-RE)
│       └── mobile_de.py     # Ad-Stream WSS consumer
├── coordinator.py           # Orchestrator principal
├── scheduler.py             # Qué portal, cuándo, qué identidad
└── db.py                    # engine.db factory
```

---

## POR QUÉ ESTO NO SE PUEDE REPLICAR

No es ningún componente individual. Es la acumulación.

| Mes | Estado |
|---|---|
| Mes 1 | Sistema funcionando, identidades nuevas, trust_score = 0-3 |
| Mes 3 | Identidades con historial real, trust_score = 5-7, Akamai las trata como usuarios habituales |
| Mes 6 | Identidades premium (trust_score ≥ 8), pool warming continuo, schema registry calibrado |

Un competidor puede clonar el código en una semana. No puede clonar 6 meses de `_abck` acumulado, identidades con historial real en los portales, y el `domain_tier_state` aprendido en producción con miles de sesiones reales.

**El moat no está en el código. Está en el tiempo de operación.**
