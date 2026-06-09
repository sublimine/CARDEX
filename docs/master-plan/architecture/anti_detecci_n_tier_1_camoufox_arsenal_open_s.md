# Anti-Detección & Tier-1 (Camoufox + arsenal open-source)

## Resumen
El subsistema NO es greenfield: ya existe, maduro y testeado, en `scrapers/engine/` con 17 módulos puros (identity, antidetect, proxy, router, session, monitoring), el orquestador `scrapers/coordinator.py`, el doc maestro `docs/SCRAPING_ENGINE.md` y la guía operativa `docs/D2_ANTI_DETECTION_OPERATIONS.md`. La taxonomía de TIERS ya está definida (T0 API abierta / T1 curl_cffi / T2 Camoufox+_abck / T3 Camoufox+behavioral+residencial) y materializada en `router/domain_map.py` (registry de ~50 portales verificados) + `router/classifier.py` (detección WAF por firmas DataDome/PerimeterX/Akamai/Cloudflare). El stack vivo es: curl_cffi (JA3 Chrome/Firefox/Safari, http3/QUIC), Camoufox (parches C++ a nivel Firefox, geoip), capsolver, behavioral.py (Bézier + scroll humano), warming de 3 fases, identidades como activos financieros con trust_score, circuit breaker por (domain,tier), escalator T0→T3, proxy fleet con health/affinity, soft-block detector. Verificado en vivo: mobile.de (Akamai v3) se vence GRATIS con Camoufox; AS24-FR 92.759 coches; dacia-meaux.fr 230/230.

La FRONTERA REAL del estado actual (verificada el 2026-06-08 en `stealth/TASK2_BYPASS_AUDIT`): DataDome (lacentrale) y PerimeterX (milanuncios) NO caen gratis porque el bloqueo está en la capa de reputación de IP/ASN, no en el reto JS — desde IP datacenter, ni Camoufox ni sitemap ni RE de API rinden inventario. Requieren IP residencial/móvil del país. El módulo `identity/residential.py` ya cablea identidades residenciales por env var pero queda 0-provisionado por falta de proxies.

Lo que FALTA y este diseño aporta sin reinventar lo bueno: (1) cerrar los degraded-mode stubs honestos que ya están marcados en el código — `sensor.refresh_token` (hyper-sdk-go no cableado) y `tcp.apply_profile` (httpcloak no cableado); (2) formalizar el protocolo "NUNCA no se puede" como un WORKFLOW de agentes ejecutable (Breach Response: enumerador de vías → ejecutor multi-estrategia → agente de investigación web → verificador adversarial), con persistencia de recetas por entidad en repo; (3) ampliar el catálogo de herramientas open-source con estado verificado 2026 y receta de ataque por tipo de defensa; (4) un pool de proxies GRATIS (CT-logs/Proxifly/scrapeops-free) como primer escalón antes del pago, con health-gating; (5) un Solver Abstraction Layer que admita capsolver (pago) y solvers open-source (DataDome/PerimeterX reversers) tras una interfaz única; (6) verificación adversarial por vía independiente (RE de API móvil + sitemap + browser cruzados). El moat no está en el código (clonable en una semana) sino en el tiempo acumulado de _abck, historial de identidades y domain_tier_state aprendido — por eso el diseño protege la longevidad de la identidad por encima de la velocidad.

## Estrategias
- **E0 — Camino más barato primero: T0 RE de API / T1 curl_cffi**: Antes de tocar un browser, agotar las vías sin anti-bot: (1) sitemap-listing (oro: enumera deep-links sin cap ni rate-trigger — ya implementado en scrapers/portals/sitemap_listing_base.py, 19 portales migrados); (2) API interna JSON/REST/GraphQL (autohero GraphQL, heycar i15, autolina v2, marktplaats LRP); (3) RE de API móvil (mitmproxy + frida unpin, mapa en SCRAPING_ENGINE §A7) que bypasea el WAF web entero. curl_cffi con impersonate=chrome136 e http_version=3 (tls.make_session) resuelve Cloudflare-Free y rate-limit básico. Verificación WAF previa con router/classifier.classify().
- **E1 — Camoufox nativo (T2: Akamai/Cloudflare-Pro)**: Camoufox (Firefox con parches C++, no JS) vía pw_base.intercept_paginate/dom_paginate y antidetect/browser.CamoufoxPool. geoip=True alinea WebRTC+timezone+locale con la IP. Gestión _abck en sensor.py (cargar token previo = usuario recurrente). Warming de 3 fases OBLIGATORIO antes de extraer (warming.py): Fase 1 ambient 48h, Fase 2 portal familiarization 24h (primer _abck), Fase 3 active. Identidad coherente por arquetipo (profile._ARCHETYPES) validada por coherence.validate_creation. Sesión condicionada (conditioning.condition_session): homepage con Referer Google → dwell → scroll antes de extraer.
- **E2 — Camoufox + Behavioral + Residencial (T3: DataDome/PerimeterX)**: T2 + behavioral.py (movimiento Bézier con entropía, scroll con deceleración, dwell lognormal) + Solver Abstraction Layer + identidad PREMIUM (trust_score>=7.0, residential.py) con proxy RESIDENTIAL_ROTATING (nueva IP por SESIÓN, nunca por request — JA3/IP invariant). El reto DataDome/PerimeterX se resuelve por capa behavioral nativa o, si persiste, por solver (capsolver pago O reverser open-source tras la interfaz única).
- **E3 — Protocolo NUNCA-no-se-puede (Breach Response Workflow)**: Ante bloqueo persistente tras E0-E2: disparar el workflow de respuesta a brecha (ver spec_md §6). Agente Enumerador lista TODAS las vías restantes (subdominios api./ws./mobile., endpoints /graphql /lrp/api, sitemaps gzip, ficha directa, RE móvil, Tor, proxy free/residencial/móvil, repos bypass GitHub 2025-26). Agente Ejecutor las prueba TODAS en orden coste-ascendente, registrando resultado por vía. Si se agotan → Agente Investigación Web (WebSearch/WebFetch sobre GitHub/Reddit/foros) cataloga herramientas nuevas vivas en 2026. Cada hallazgo se persiste como receta en el repo.
- **E4 — Spoofing de capa de red (TCP + JA3 hardening)**: Cerrar el degraded-mode honesto ya marcado en el código: cablear httpcloak (tcp.apply_profile) para spoof del SYN packet (TTL/Window/options coherentes con el OS del UA) y hyper-sdk-go (sensor.refresh_token) para refrescar _abck sin browser. Mantiene la coherencia OS↔UA↔TCP↔TLS que enforce coherence.py. Rotación de fingerprint por identidad (determinista por seed), JA3 fijo intra-sesión.

## Spec completa
# Subsistema ANTI-DETECCIÓN & TIER-1 — Especificación de Ejecución

> Source of truth de diseño: `docs/SCRAPING_ENGINE.md` (§A3 Anti-Detection Stack, §A6 Tier Router).
> Source of truth operativo: `docs/D2_ANTI_DETECTION_OPERATIONS.md`.
> Implementación viva: `scrapers/engine/`. Este documento NO duplica el código: lo cita, corrige y extiende.
> Principio rector heredado: "Una identidad digital es un activo financiero. Se construye, se protege, se envejece y se jubila. Nunca se descarta."

---

## 1. Estado real verificado (reconocimiento, no asunción)

Todo lo de esta sección está `[VERIFICADO]` por lectura directa de los archivos citados.

### 1.1 Lo que YA existe y funciona
| Capa | Archivo | Estado |
|---|---|---|
| TLS/JA3 (curl_cffi, http3) | `scrapers/engine/antidetect/tls.py` | Vivo. impersonate por `identity.tls_profile`. JA3 fijo intra-sesión. |
| Browser anti-detect (Camoufox) | `scrapers/engine/antidetect/browser.py`, `scrapers/common/pw_base.py` | Vivo. Pool por identidad, geoip, fallback Chromium+stealth_js. |
| Stealth JS (fallback Chromium) | `scrapers/engine/antidetect/stealth_js.py` | Vivo. 10 señales cubiertas. |
| Behavioral (T3) | `scrapers/engine/antidetect/behavioral.py` | Vivo. Bézier mouse, scroll decelerado, dwell lognormal. |
| Sensor Akamai `_abck` | `scrapers/engine/antidetect/sensor.py` | Vivo PERO `refresh_token` en degraded-mode honesto (hyper-sdk-go no cableado → cae a Fase 2 warming). |
| TCP fingerprint | `scrapers/engine/antidetect/tcp.py` | Vivo PERO `apply_profile` en degraded-mode honesto (httpcloak no cableado → log y sigue). |
| Identidad coherente | `scrapers/engine/identity/{profile,coherence,aging,store,direct,residential}.py` | Vivo. Arquetipos coherentes, trust lifecycle, store SQLite. |
| Proxy fleet | `scrapers/engine/proxy/{pool,tiers,health,affinity}.py` | Vivo. 3 pools, health EWMA, affinity domain↔proxy. |
| Router de tiers | `scrapers/engine/router/{domain_map,classifier,escalator,circuit}.py` | Vivo. Registry ~50 portales, WAF classifier, circuit breaker, escalator. |
| Sesión | `scrapers/engine/session/{warming,intent,conditioning,state}.py` | Vivo. Warming 3 fases, 20 personas/país, conditioning. |
| Soft-block | `scrapers/engine/monitoring/softblock.py` | Vivo. NullFieldTracker + ZeroUrlTracker. |
| Métricas | `scrapers/engine/monitoring/metrics.py`, `alerts.yml` | Vivo. Prometheus, 5 alertas. |
| Orquestador | `scrapers/coordinator.py` | Vivo. work_queue, seams testeables, circuit outcome. |
| WAF probe en vivo | `scrapers/intelligence/waf.py`, `scrapers/discovery/sources/as24_curl_cffi.py` | Vivo. |
| RE de API móvil | `scrapers/mobile_re/client.py` (esqueleto) | Parcial (mobile.de WSS hecho, AS24 viable). |

### 1.2 Hechos de arquitectura que NO deben confundirse
- **Dos stores distintos** `[VERIFICADO]`: el ESTADO del engine (identidades, proxy_health, domain_tier_state, work_queue, warming_schedule) vive en **SQLite WAL** `engine.db` (`store.py`, `circuit.py`, `pool.py` usan `sqlite3.Connection`). El INVENTARIO de vehículos + discovery vive en **PostgreSQL** (`as24_curl_cffi.py` usa asyncpg `discovery_candidates`). La nota de MEMORY "store REAL = PostgreSQL" aplica al inventario, NO al estado del engine. **No migrar engine.db a PG sin orden explícita**: la testabilidad in-memory del coordinator depende de SQLite.
- **Taxonomía de TIERS** `[VERIFICADO]` en `router/domain_map.py`: `T0` API abierta/móvil (sin anti-bot) · `T1` curl_cffi sin browser · `T2` Camoufox+storageState+`_abck` · `T3` Camoufox+behavioral+solver+residencial. `WAF` enum: none, cf_free, cf_pro, cf_business, akamai_v3, datadome, perimeter_x, unknown.
- **JA3/IP invariants** `[VERIFICADO]`: `tls.py` crea la sesión UNA vez por sesión (JA3 fijo p1→pN); `affinity.py` mantiene la misma IP por dominio durante toda la sesión; residencial rota por SESIÓN, nunca por request.

### 1.3 La FRONTERA real gratis/pago `[VERIFICADO]` (`stealth/TASK2_BYPASS_AUDIT_2026-06-08.md`)
- **Akamai v3 (mobile.de): GRATIS** con Camoufox. Warm pasa, ~99% del catálogo por faceteo.
- **DataDome (lacentrale) y PerimeterX (milanuncios): NO gratis** desde IP datacenter. El bloqueo es de reputación IP/ASN, no sólo reto JS. Requieren residencial/móvil del país. `identity/residential.py` ya lo cablea por env var `RESIDENTIAL_PROXY_<CC>` pero está 0-provisionado.

---

## 2. Arquitectura objetivo (qué se construye sobre lo real)

```
                         ┌──────────────────────────────────────────────┐
                         │  LEAD AGENT (Anti-Detect Commander)           │
                         │  decide tier, presupuesto, escalado, brecha   │
                         └───────────────┬──────────────────────────────┘
                                         │ orquesta
      ┌──────────────┬──────────────┬────┴─────────┬───────────────┬──────────────┐
      ▼              ▼              ▼               ▼               ▼              ▼
 ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌───────────┐   ┌──────────┐  ┌──────────────┐
 │ WAF     │   │ Identity │   │ Engage   │   │ Breach    │   │ Adversar.│  │ Research     │
 │ Recon   │   │ Forge +  │   │ Engine   │   │ Response  │   │ Verifier │  │ Scout (web)  │
 │ (probe) │   │ Warming  │   │ E0→E1→E2 │   │ (NUNCA-no)│   │ (co-igual)│ │ GitHub/Reddit│
 └─────────┘   └──────────┘   └──────────┘   └───────────┘   └──────────┘  └──────────────┘
      │              │              │               │               │              │
      └──────────────┴──────────────┴───────────────┴───────────────┴──────────────┘
                                         │ persiste
        ┌────────────────────────────────┴─────────────────────────────────┐
        │ engine.db (SQLite)  · recipes/<country>/<entity>.json (repo)        │
        │ proxy pools (free→ISP→residential→mobile) · Solver Abstraction Layer│
        └────────────────────────────────────────────────────────────────────┘
```

Componentes NUEVOS a crear (todo lo demás se reutiliza):
1. `scrapers/engine/antidetect/solver.py` — Solver Abstraction Layer (interfaz única; backends capsolver + open-source).
2. `scrapers/engine/proxy/free_pool.py` — pool de proxies gratis con health-gating + promoción a pago.
3. `scrapers/engine/router/breach.py` — máquina de estados del protocolo NUNCA-no-se-puede (vías + resultados).
4. `recipes/` — recetas de extracción por entidad, portables (formato §7.3).
5. `tools/CATALOG.md` (o `docs/ANTIDETECT_TOOL_CATALOG.md`) — catálogo de herramientas con estado verificado (§4).
6. Cierre de degraded-modes: cablear `tcp.py` (httpcloak) y `sensor.py` (hyper-sdk-go).
7. `.claude/agents/` o `scrapers/agents/` — definiciones de los 7 agentes (§5).

---

## 3. Taxonomía de TIERS y receta de ataque por tipo de defensa

> Decisión pura en `router/classifier.classify_signals(status, headers, body)`. Persistida en `domain_tier_state`.

| Defensa detectada | Firma (classifier) | Tier asignado | Receta de ataque (orden) |
|---|---|---|---|
| Ninguna | sin marcadores, 200 | T0/T1 | sitemap-listing → API interna → curl_cffi SSR |
| Cloudflare-Free | `cf-ray`/`__cf_bm`, sin challenge | T1 | curl_cffi chrome136 (JA3 real pasa Turnstile pasivo) |
| Cloudflare-Pro | challenge body / 403+cf | T2 | Camoufox warm; si Turnstile activo → solver layer |
| Cloudflare-Business | (registry: gocar.be) | T2 | Camoufox + ISP-sticky + behavioral si insiste |
| Cloudflare AI Labyrinth | poison signals (texto/código>0.8, <15KB, @type≠Vehicle) | T2 + poison gate | NO detectar sino EVITAR (trust alto); quality gate descarta batch |
| Akamai Bot Manager v3 | `ak_bmsc`/`bm_sz`/`_abck` | T2 | Camoufox + `_abck` (cargar previo=usuario recurrente) + warming Fase 2; refresh hyper-sdk-go |
| DataDome | `x-datadome`/`datadome=`/`captcha-delivery` | T3 | RE API móvil PRIMERO (bypass total); si no → residencial país + Camoufox behavioral + solver DataDome |
| PerimeterX/HUMAN | `_px*`/`px-captcha`/`perimeterx` | T3 | RE API móvil; si no → residencial país + behavioral (press&hold biométrico) + solver PX |
| Desconocida + block status | 403/429/503 sin firma | T2 (conservador) | Camoufox + re-clasificar; nunca asumir camino barato |

**Engagement por tier (coste ascendente, regla D2 §7):** un job entra siempre por el tier más barato viable; el `escalator` sube sólo cuando el circuit breaker del tier actual abre. T1→T3 multiplica coste ~80x: el escalado debe estar justificado, no ser reflejo. T3 requiere identidad premium o el job ESPERA (no degrada).

---

## 4. Catálogo de herramientas open-source (estado a verificar en vivo por el Research Scout)

> El Lead Agent debe disparar el Research Scout (WebSearch/WebFetch) para CONFIRMAR el estado 2026 de cada una antes de adoptar. Lo que sigue es el catálogo base con su para-qué; el `[ESTADO]` se rellena en `docs/ANTIDETECT_TOOL_CATALOG.md` tras verificación.

### 4.1 Ya en el repo (pinneadas en `scrapers/requirements.txt`) `[VERIFICADO]`
- **curl_cffi >=0.15.1** — cliente HTTP que impersona JA3/JA4 + HTTP2 SETTINGS de Chrome/Firefox/Safari. Núcleo de T1 y de todos los probes. http_version=3 (QUIC).
- **camoufox[geoip] >=0.4.11** — Firefox con parches a nivel C++ (canvas/audio/webgl/fonts/webdriver). Núcleo de T2/T3. geoip alinea WebRTC+TZ+locale. Riesgo conocido (D2 §11): mantenedor daijro en hiato; fork @coryking Firefox 142; pinnear build known-good.
- **playwright >=1.49** — sólo motor de fallback Chromium (con `stealth_js.py`). playwright-stealth BANEADO por CI desde 2026-05-16.
- **capsolver >=1.1.0** — solver de pago (Turnstile, reCAPTCHA, DataDome slider). Detrás del Solver Layer; usar sólo cuando aporte valor.

### 4.2 Diseñadas pero NO cableadas (cerrar en este subsistema)
- **httpcloak** (Go, CAP_NET_RAW + npcap/libpcap) — spoof del TCP SYN (TTL/Window/options) coherente con OS del UA. Stub honesto en `tcp.py`. Cablear contrato de invocación.
- **hyper-sdk-go** (Go) — habla el protocolo sensor Akamai; regenera `_abck` sin browser. Stub honesto en `sensor.py`. Cablear.

### 4.3 Candidatas a evaluar (Research Scout debe verificar vivacidad 2026)
- **nodriver** (sucesor de undetected-chromedriver, ultrafunk) — Chrome CDP sin webdriver; alternativa a Camoufox para sitios Chrome-only. `[ESTADO: verificar]`
- **patchright** (drop-in de Playwright parcheado) — para CSR-XHR donde Camoufox no rinde. Nota D2: parches JS son más detectables que C++ de Camoufox; usar con cautela. `[ESTADO: verificar]`
- **botasaurus** — framework anti-detect con bypass CF integrado y gestión de perfiles. `[ESTADO: verificar]`
- **hrequests** — requests + impersonación TLS + render headless; alternativa ligera a Camoufox para T2 bajo. `[ESTADO: verificar]`
- **tls-client** (Go/Python bindings, bogdanfinn) — alternativa a curl_cffi para JA3; útil si curl_cffi rompe en un portal. `[ESTADO: verificar]`
- **FlareSolverr** — proxy que resuelve retos Cloudflare con browser; pesado, pero útil como último recurso T2 batch. `[ESTADO: verificar]`
- **Camoufox-captcha / solvers DataDome/PerimeterX open-source** (repos 2025-26) — reversers para el Solver Layer evitando capsolver pago. El audit 2026-06-08 los evaluó: requieren residencial igualmente. `[ESTADO: verificar por entidad]`
- **mitmproxy + frida (unpin universal) + mitmproxy2swagger** — RE de API móvil (T0 bypass total, SCRAPING_ENGINE §A7). Confirmado parcial (mobile.de, AS24).
- **Oxymouse / trayectorias humanas** — generación de movimiento de ratón para T3; `behavioral.py` ya implementa Bézier propio (no depende de Oxymouse, pero puede importarlo).

### 4.4 Fuentes de proxy GRATIS (primer escalón antes del pago)
- **CT logs / Common Crawl** — ya en `discovery/sources/{ct_logs,common_crawl}.py` (para descubrimiento, no proxy).
- **Proxifly / listas free datacenter** — evaluadas en audit: mayormente muertas y ASN-flagged; útiles sólo para portales sin reputación-IP.
- **ScrapeOps residential free (100MB)** — requiere API key; primer test gratis de residencial real (mencionado en audit como vía de adaptación).
- **Tor** — evaluado: no resuelve reputación IP en DataDome/PX, pero válido para T0/T1 sin anti-bot.

---

## 5. Agentes del subsistema (rol, responsabilidad, tools, criterio de calidad)

> Encajan en el orquestador `scrapers/coordinator.py` (los agentes deciden; el coordinator ejecuta el run mecánico). El AGENTE-LÍDER es la capa de decisión por encima del bucle `run()`.

### 5.1 Lead Agent — "Anti-Detect Commander" (orquestador)
- **Rol:** dueño táctico de CÓMO se ataca cada entidad. Decide tier inicial (vía classifier), presupuesto de proxy, cuándo escalar, cuándo disparar Breach Response.
- **Responsabilidad:** mantener `premium_identity_count>=3`; no exceder 60% presupuesto en proxies; garantizar que ningún job se queda en "no se puede" sin pasar por Breach Response.
- **Tools:** lectura de `domain_tier_state`/`proxy_health`/métricas; invocación de los sub-agentes; escritura de decisiones en recetas.
- **Criterio de calidad:** cada entidad termina en uno de tres estados explícitos: `SOLVED` (rinde inventario verificado), `BLOCKED_BY_PAID` (sólo falta proxy de pago justificado, documentado), `OPEN_RESEARCH` (Breach Response activo). Prohibido cerrar como "imposible".

### 5.2 WAF Recon Agent
- **Rol:** clasificar la defensa de un dominio nuevo o re-clasificar uno stale.
- **Tools:** `router/classifier.classify()` (curl_cffi probe, SSRF-guard `net_guard.is_safe_public_url`).
- **Criterio:** WAF y tier persistidos con `verified_at`; nunca optimista en incertidumbre (UNKNOWN→T2). Re-probar si `is_stale` (>7 días).

### 5.3 Identity Forge + Warming Agent
- **Rol:** acuñar identidades coherentes y envejecerlas; nunca extraer antes de Fase 2.
- **Tools:** `identity/profile.generate`, `coherence.validate_creation`, `session/warming.run_phase1/2`, `aging`.
- **Criterio:** 0 incoherencias (coherence pasa); 0 extracciones pre-warming (regla dura: identidad quemada si no); pool warming nunca <5.

### 5.4 Engage Engine Agent
- **Rol:** ejecutar la extracción por el tier asignado (E0→E1→E2), aplicando conditioning + behavioral según tier.
- **Tools:** `pw_base`, `conditioning`, `behavioral`, `sensor`, `tls`, `solver.py`(nuevo).
- **Criterio:** JA3 fijo intra-sesión; IP estable por dominio; soft-block detectado (`softblock.py`) dispara rotación, no persistencia ciega.

### 5.5 Breach Response Agent (protocolo NUNCA-no-se-puede)
- **Rol:** ante bloqueo persistente, enumerar y probar TODAS las vías. Es la materialización de `feedback_never_default_cant.md`.
- **Tools:** `router/breach.py`(nuevo), curl_cffi multi-endpoint, mitmproxy/frida (RE móvil), `free_pool`, `solver`.
- **Criterio:** registra resultado por cada vía probada (tabla §6); no devuelve control hasta agotar la lista o conseguir inventario; al agotar, invoca Research Scout.

### 5.6 Research Scout Agent
- **Rol:** cuando las vías conocidas se agotan, investigar Internet (GitHub/Reddit/foros) por herramientas/vías nuevas vivas en 2026.
- **Tools:** WebSearch/WebFetch (cargar con ToolSearch si hace falta), lectura de repos.
- **Criterio:** entrega candidatos con `[ESTADO verificado]` (vivo/muerto, última release, dependencia de pago) en `docs/ANTIDETECT_TOOL_CATALOG.md`; nada de "asumido".

### 5.7 Adversarial Verifier Agent (CO-IGUAL, no subordinado)
- **Rol:** desconfiar de la PRIMERA respuesta de cualquier agente y verificar por vía INDEPENDIENTE de la que usó la extracción.
- **Tools:** segunda vía (si extracción fue browser → verificar por sitemap/API móvil y viceversa); `drift_gate` (volumen vs baseline), `softblock` (contenido), conteo cruzado.
- **Criterio:** verifica NÚMEROS Y CONTENIDO (completitud/frescura/correctness), no sólo conteos. Veredicto `PASS`/`FAIL` con evidencia; un FAIL re-abre el ciclo.

---

## 6. Workflow: Breach Response ("NUNCA no se puede")

Máquina de estados en `scrapers/engine/router/breach.py`, persistida en una tabla nueva `breach_attempts` (§7.2).

```
ENTER (un portal/entidad falla E0-E2)
  │
  ▼
[1] ENUMERATE  → Enumerador lista vías candidatas en orden coste-ascendente:
      v1  sitemap-listing (raíz, _index, gz, robots Sitemap:)
      v2  ficha de detalle directa
      v3  API interna (/api/v*, /lrp/api/search, /graphql, /ms/search, data-route)
      v4  subdominios (api. ws. mobile. app. bff. gateway. search. m. edge.)
      v5  RE de API móvil (mitmproxy+frida) — bypass total del WAF web
      v6  curl_cffi variando impersonate (chrome/firefox/safari) + http2/3
      v7  Camoufox warm + reload×N + locale país
      v8  free_pool (datacenter/Tor) — sólo si NO hay reputación-IP
      v9  residential free (ScrapeOps 100MB) — primer residencial gratis
      v10 residential/mobile de pago del país — frontera de pago
      v11 solver layer (open-source primero, capsolver después)
  │
  ▼
[2] EXECUTE    → Ejecutor prueba cada vía, registra (via, result, evidence, rows) en breach_attempts.
                 Para INMEDIATAMENTE en la primera que rinde inventario verificable.
  │ (todas fallan)
  ▼
[3] RESEARCH   → Research Scout busca GitHub/Reddit/foros herramientas/vías 2026.
                 Añade vías nuevas a la lista → vuelve a [2] con ellas.
  │ (research sin nuevas vías)
  ▼
[4] CLASSIFY   → estado terminal explícito:
      SOLVED            → persistir receta (§7.3) + Adversarial Verifier
      BLOCKED_BY_PAID   → documentar EXACTAMENTE qué proxy/solver de pago lo desbloquea (audit-style)
      OPEN_RESEARCH     → dejar abierto con la lista de vías agotadas (nunca "imposible")
```

Tabla de registro por vía (formato del audit 2026-06-08, ahora estructurado):
```
breach_attempts(entity, via, probed_at, result, http_status, rows_yielded, evidence_note)
```

---

## 7. Esquemas de datos y config concretos

### 7.1 Reutilizados (engine.db, SQLite) `[VERIFICADO]` — `docs/SCRAPING_ENGINE.md` DATA MODEL
`identities`, `domain_tier_state`, `proxy_health`, `work_queue`, `dlq`, `schema_registry`, `warming_schedule`, `proxy_affinity`. No tocar salvo añadir columnas vía migración.

### 7.2 Tablas NUEVAS (migración en `scrapers/db.py`)
```sql
-- Protocolo NUNCA-no-se-puede: registro por vía
CREATE TABLE breach_attempts (
    entity        TEXT NOT NULL,        -- domain o entity code
    via           TEXT NOT NULL,        -- v1..v11 o nombre de herramienta
    probed_at     INT  NOT NULL,
    result        TEXT NOT NULL,        -- solved|blocked|dns_fail|403|404|405|timeout|empty
    http_status   INT,
    rows_yielded  INT  DEFAULT 0,
    evidence_note TEXT,
    PRIMARY KEY (entity, via, probed_at)
);

-- Pool de proxies gratis con health-gating y promoción
CREATE TABLE free_proxy_pool (
    proxy_url     TEXT PRIMARY KEY,
    kind          TEXT NOT NULL,        -- datacenter|tor|residential_free
    country       CHAR(2),
    success_rate  REAL DEFAULT 1.0,
    last_alive_at INT,
    asn_flagged   INT  DEFAULT 0,       -- 1 si DataDome/PX lo marcó
    status        TEXT DEFAULT 'untested'
);
```

### 7.3 Receta de extracción por entidad (portable, en repo) — `recipes/<country>/<entity_code>.json`
> Portabilidad doctrinal: si mañana se usa Codex u otra herramienta, debe poder reproducir la extracción desde esta receta sin leer el código.
```json
{
  "entity_code": "FR-75-0001",
  "domain": "lacentrale.fr",
  "country": "FR",
  "tier": "T3",
  "waf": "datadome",
  "verified_at": "2026-06-08",
  "winning_via": "v10_residential_fr + camoufox_behavioral",
  "engine": {
    "tls_profile": "firefox147",
    "browser": "camoufox",
    "geoip": true,
    "behavioral": true,
    "proxy_tier": "residential_rotating",
    "proxy_country": "FR",
    "solver": {"layer": "datadome", "backend": "none|capsolver|oss:<repo>"}
  },
  "discovery": {
    "method": "browser_dom_paginate",
    "search_url_fn": "https://lacentrale.fr/listing?page={n}",
    "detail_re": "/auto-occasion-annonce-\\d+\\.html",
    "max_pages": 0
  },
  "exhausted_vias": [
    {"via": "v3_api", "result": "403_datadome"},
    {"via": "v5_mobile_re", "result": "not_attempted_pending"},
    {"via": "v8_free_proxy", "result": "asn_flagged"}
  ],
  "notes": "Bloqueo a nivel IP/ASN, no reto JS (audit 2026-06-08). Residencial FR necesario.",
  "verification": {"method": "cross_source", "independent_via": "v5_mobile_re|sitemap", "status": "PASS|FAIL"}
}
```

### 7.4 Catálogo de herramientas — `docs/ANTIDETECT_TOOL_CATALOG.md`
Tabla: `tool | role | tier | install | [ESTADO 2026: vivo/muerto] | última_release | dep_pago | repo | verificado_por_scout_at`.

### 7.5 Solver Abstraction Layer — `scrapers/engine/antidetect/solver.py`
```python
class SolverResult:  # token + cost + backend usado + latencia
class Solver(Protocol):
    async def solve(self, challenge: ChallengeSpec) -> SolverResult | None: ...
# Backends: CapsolverSolver (pago), OssDataDomeSolver, OssPerimeterXSolver, NullSolver.
# Selección: open-source primero; capsolver sólo si el Lead Agent autoriza presupuesto.
```

---

## 8. Verificación adversarial integrada

- **Co-igualdad:** el Adversarial Verifier no es un paso final opcional; corre tras CADA extracción declarada SOLVED y puede re-abrir el ciclo.
- **Vía independiente OBLIGATORIA:** si la extracción fue por browser (E1/E2), la verificación usa una vía distinta (RE de API móvil o sitemap-listing) y compara conteo + muestra de contenido. Si fue por API, se verifica por browser/sitemap.
- **Números Y contenido:** conteo vs `drift_gate` baseline (volumen), `softblock.NullFieldTracker` (campos críticos presentes), frescura (lastmod/precio reciente), correctness (precio∈rango, año válido, URL deep-link no root) — gates ya en `intelligence/`/`pipeline/`.
- **Desconfianza por defecto:** una primera respuesta "92.759 coches" no se acepta hasta segunda vía coincidente dentro de tolerancia (ej. AS24-FR verificado 98,8% por multi-pasada + sort estable).

---

## 9. Resiliencia, coste y trazabilidad (grado institucional)

- **Resiliencia:** circuit breaker por (domain,tier) (`circuit.py`) — un dealer caído NO tumba CARDEX; `coordinator._safe_process_item` aísla el crash de un portal del bucle. Matriz de fallos completa en SCRAPING_ENGINE §F.
- **Coste:** orden estricto gratis→pago (E0→E2); LLM LOCAL para clasificación/parsing/verificación determinista (Haiku/local), Opus sólo para decisión de arquitectura de ataque; regla 60% presupuesto proxy; T0/T1 maximizados antes de cualquier residencial.
- **Trazabilidad:** cada decisión persistida (domain_tier_state, breach_attempts, recipes), métricas Prometheus + 5 alertas (`alerts.yml`), recetas en repo portables.
- **Degradación elegante:** patrón ya presente (tcp/sensor/metrics no revientan si falta binario/dep) — mantener al cablear httpcloak/hyper-sdk-go.

---

## 10. Criterios de aceptación medibles

1. **WAF Recon:** 100% de dominios del registry con `domain_tier_state.waf` + `verified_at` no stale; clasificación reproducible por `classify_signals` (test unitario por firma).
2. **Engagement por tier:** ningún job escala de tier sin circuit breaker abierto (auditable en `domain_tier_state.effective_tier`); T3 nunca servido a identidad no-premium (`pick_for_portal require_proxy` + premium gate).
3. **Camoufox gratis:** mobile.de rinde ≥99% del catálogo por faceteo SIN proxy de pago (regresión del verificado).
4. **Breach Response:** todo portal que falla E0-E2 produce una fila terminal en `breach_attempts` con estado SOLVED/BLOCKED_BY_PAID/OPEN_RESEARCH; CERO entidades cerradas como "imposible".
5. **Verificación adversarial:** cada receta SOLVED tiene `verification.status=PASS` por vía independiente; un FAIL bloquea la ingesta.
6. **Catálogo:** `docs/ANTIDETECT_TOOL_CATALOG.md` con ≥10 herramientas y `[ESTADO 2026]` verificado por Research Scout (no asumido).
7. **Cierre de degraded-modes:** `tcp.is_available()` y `sensor.hyper_sdk_path()` True en el host de producción; tests de coherencia OS↔UA↔TCP↔TLS pasan.
8. **Identidad como activo:** 0 extracciones pre-warming; premium_identity_count≥3 mantenido; ninguna identidad borrada (sólo retired).
9. **Coste:** gasto de proxy ≤60% del presupuesto; ratio de requests T0/T1 vs T2/T3 ≥80/20 medido en Prometheus.
10. **Portabilidad:** una receta `recipes/*.json` permite a un agente nuevo reproducir la extracción sin leer el código fuente (test de reproducción).

## Decisiones clave
- NO es greenfield: construir sobre los 17 módulos vivos de scrapers/engine/, el coordinator y los docs maestros; reutilizar, corregir y extender — no reimplementar.
- Mantener engine.db en SQLite (estado del engine) separado de PostgreSQL (inventario+discovery): la testabilidad in-memory del coordinator depende de ello; la nota MEMORY 'store=PG' aplica al inventario, no al estado.
- Taxonomía de TIERS confirmada y reutilizada de router/domain_map.py: T0 API/móvil · T1 curl_cffi · T2 Camoufox+_abck · T3 Camoufox+behavioral+solver+residencial.
- Orden de ataque coste-ascendente FIJO (E0 sitemap/API/RE-móvil → E1 Camoufox nativo → E2 Camoufox+residencial+solver): nunca un browser cuando un sitemap-listing o API rinde; 80x más barato.
- La frontera real gratis/pago es la reputación de IP/ASN: Akamai (mobile.de) cae gratis con Camoufox; DataDome/PerimeterX requieren residencial del país (verificado 2026-06-08). Diseñar proxies como escalón gratis→ISP→residencial→móvil.
- Formalizar 'NUNCA no se puede' como workflow ejecutable (Breach Response: Enumerador→Ejecutor→Research Scout→Verifier) con estados terminales explícitos SOLVED/BLOCKED_BY_PAID/OPEN_RESEARCH; prohibido cerrar como 'imposible'.
- Verificación adversarial CO-IGUAL por vía independiente (browser vs API móvil vs sitemap), verificando números Y contenido (completitud/frescura/correctness), no sólo conteos.
- Cerrar los degraded-mode honestos ya marcados en el código: cablear httpcloak (tcp.py) y hyper-sdk-go (sensor.py) antes de escalar T2 a volumen.
- Solver Abstraction Layer único: open-source primero (reversers DataDome/PX), capsolver de pago sólo con autorización de presupuesto del Lead Agent.
- Recetas de extracción portables por entidad en recipes/<country>/<entity>.json: reproducibles por Codex u otra herramienta sin leer el código (doctrina de portabilidad).

## Riesgos
- Camoufox depende de un fork con mantenedor en hiato (daijro hospitalizado desde mar-2025; fork @coryking Firefox 142). Riesgo de quedar atrás de cambios de detección. Mitigación: pinnear build known-good + Research Scout monitorea upstream mensual + tener nodriver/patchright como alternativa evaluada.
- DataDome/PerimeterX bloquean por reputación IP/ASN, no sólo reto JS: sin residencial del país no hay vía gratis (verificado). Riesgo de presupuesto si muchos portales son T3. Mitigación: priorizar RE de API móvil (bypass total) antes de pagar residencial.
- Los stubs degraded-mode (tcp/sensor) significan que HOY no hay spoof TCP ni refresh _abck sin browser: CF Network Analytics puede detectar OS-mismatch en T2+ a volumen. Mitigación: cablear httpcloak/hyper-sdk-go antes de escalar.
- Firefox TLS (Camoufox) es distinguible de Chrome TLS; algunos WAF pueden separar Firefox-automation de Firefox real. Mitigación aceptada: Firefox está whitelisted en la mayoría de portales EU.
- curl_cffi y camoufox son dependencias nativas (no se importan en CI sin red): un cambio de versión de Chrome (~6 semanas) puede romper la impersonación JA3. Mitigación: cadencia D2 §10 de actualización de perfiles TLS.
- Proxies gratis (datacenter/Tor) están mayormente muertos/ASN-flagged (audit): falso sentido de progreso si se usan contra portales con reputación-IP. Mitigación: free_pool con asn_flagged + health-gating, sólo para portales sin reputación-IP.
- Solvers open-source de DataDome/PerimeterX cambian/mueren rápido; depender de ellos es frágil. Mitigación: Solver Layer con fallback a capsolver + Research Scout re-verifica vivacidad.
- Riesgo legal/ToS del scraping: el fin último son acuerdos legales (XML/API directo). El scraping es puente. Mitigación: respetar robots donde sea posible (la migración a sitemap ya hizo robots-compliant a marktplaats/2dehands), rate-limiters desde el inicio, no tumbar dealers.