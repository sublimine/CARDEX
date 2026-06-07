---
name: project-stealth-giants-free
description: "Los gigantes Tier-1 NO son \"de pago\" — Camoufox + IP residencial CH los crackea gratis"
metadata: 
  node_type: memory
  type: project
  originSessionId: 407ff08f-21d5-47a2-8f14-958c42950f27
---

Frente stealth (rama `feature/stealth-camoufox` desde main, worktree `cardex-stealth/`, commit f414fb3, NO push). Corrige el supuesto de [[project_audit_2026_06_06]] y [[project_blueprint_target_arch]] de que los gigantes T2/T3 necesitan proxies de pago (P3): **4 caen GRATIS**.

**Enabler clave:** la IP de salida del host es **RESIDENCIAL Swisscom CH** (83.77.233.252, AS3303) — trust anti-bot positivo nativo, no datacenter. Por eso no hacen falta proxies para el score (sí para geo en sitios ES/DE estrictos).

**Camoufox arranca en Windows** tras `stealth/fix_camoufox_sxs.py`: el manifiesto PE de `camoufox.exe` declara dependencia SxS al assembly `mozglue` que Windows no resuelve → `spawn UNKNOWN`. Fix = byte-patch que neutraliza ese `<dependency>` (mismo tamaño, reversible vía `camoufox.exe.orig`). NO era Application Control.

**Crackeados (evidencia dura, HTTP 200 + datos reales en `stealth/RESULTS.md`):**
- mobile.de (Akamai Bot Mgr v2, ~4,4M): warm-up homepage + settle/reload → `window.__INITIAL_STATE__` → `search.srp.data.searchResults.items`.
- autoscout24.de (Akamai): `__NEXT_DATA__` → `props.pageProps.listings`.
- leboncoin.fr (DataDome): `__NEXT_DATA__` → `props.pageProps.searchData.ads`; **+ sitemap `auto-main.xml` = ~900.000 URLs de anuncios reales** (`/ad/voitures/{id}`, cosechable directo por red sin bloqueo) → detalle validado E2E.
- coches.net (DataDome): `__INITIAL_PROPS__` → `initialResults.items` (sitemap 405-bloqueado, usar SSR).

**Patrón general:** Camoufox (headless, humanize, geoip) navega → estado SSR embebido (`__NEXT_DATA__`/`__INITIAL_PROPS__`/`__INITIAL_STATE__`, a veces `JSON.parse("…")`) → `extract_state.py`. Akamai duro necesita warm-up+settle. Sitemaps: solo leboncoin publica anuncios; mobile.de/AS24 publican SEO/facetas → escala por search-API + facetas.

**10 GIGANTES CAEN (ambos lotes, commits f414fb3 + 0339211):** coches.net, mobile.de, leboncoin, autoscout24 ×5 (.de/.fr/.es/.nl/.ch), kleinanzeigen (DOM data-adid 27/pág), gumtree (DOM /p/{make}/.../{id} 12/pág). AS24.ch usa Nuxt+DOM `/de/d/`; AS24.be solo necesita URL con prefijo locale `/nl/`o`/fr/` (misma plataforma que .de).

**Bloqueados (requieren proxy residencial del PAÍS, única dependencia de pago real):** milanuncios (PerimeterX + geo ES; proxies ES libres mueren en minutos/datacenter), lacentrale (DataDome captcha + geo FR).

**WORKER de volcado+delta `dump_worker.py`:** pagina/facetea → extrae SSR → normaliza al contrato seam (vehicle_index L1 + ricos) → DELTA SEEN/GONE. Probado E2E leboncoin: 60/60 schema-válido; delta detecta altas Y bajas (unit determinista + run1→run2 vivo). Local validar-con-límite-y-purgar (`--limit`/`--purge`); volcado íntegro = VPS. Para delta estable usar `sort=time` (leboncoin rota resultados).

**MOTOR DE FACETEO RECURSIVO `facet_engine.py` (commits b2878ca/86860a6):** cobertura TOTAL por conteo. mobile.de API interna `m.mobile.de/svc/s/?vc=Car&…&p` = **count+preview** (total EXACTO + top-20, NO pagina por ningún param) → in-page tras Akamai. Total real vivo = **1.586.022** (no 4,4M). Refdata marcas `m.mobile.de/svc/r/makes/Car` (178). Ejes: `ms`(make)/`fr`(año)/`ml`(km). **COBERTURA PROBADA 100%**: Σ(conteos 178 marcas)=1.586.026 ≈ root. VW×año reconcilia 92,5% (gap=listings sin año→cierre con bucket fr-unknown/ml). Enumeración real = ruta desktop `search.html?pageNumber=N`→`__INITIAL_STATE__` (svc no pagina); faceteo mantiene hojas bajo el cap desktop. Patrón genérico para los ~73 tier-1.

**CABLEADO AL SEAM `seam_writer.py` (commit 56c03fd):** delta stealth → seam vivo, idempotente + inyección-seguro (`\copy` CSV). SEEN→`vehicle_index`(ON CONFLICT)+`vehicle_events SEEN`+`XADD stream:enrich_pending {h,u,s,c}`(C5); GONE→DELETE+`vehicle_events GONE`. PROBADO E2E leboncoin: 60 altas/10 bajas, mensaje=C5 exacto, purgado (`sitemap_source='stealth'`). PG/Redis vía docker exec (sin driver host).

**TABLERO `TIER1_COVERAGE.md` (`make_dashboard.py`):** 71 portales (70 work_queue + gumtree). GOBERNANZA: nada verde por mi cuenta, máx «pendiente de verificación» → Guardian audita con conteo independiente. Estado: 2 pend-verif (mobile.de 100%, leboncoin sitemap), 8 parcial (coches/AS24×5/kleinanzeigen/gumtree crackeados, falta perfil count+faceteo), 2 bloqueado (milanuncios/lacentrale, proxy país), 58 pendiente. Los 73 son campaña multi-sesión: motor+cableado listos, cada portal restante = un ciclo de reconocimiento de su API.

**SUPERVISOR-DAEMON `supervisor/` (commit 9744868):** daemon Python 24/7 que gobierna todos los workers sin depender de sesión de chat. Tarea Windows `CARDEX Supervisor` (Interactive + healthcheck 5 min vía `ensure.py`; S4U/AtStartup/survive-logout exigen admin → no disponibles sin elevación). `supervisor.py` (singleton, pid-liveness ctypes sin deps, heartbeat, backoff exponencial, log rotation, supervisor_state.json), `tier1_runner.py` (avanza cola 73: ingiere coberturas→tier1_progress.json, gobierna/relanza profilers por portal), `demo_worker.py` (canario), `config.json` (registro workers: tier1_runner+demo activos; conversion_rest_fr/discovery/inventory_scraper stubs disabled). PROBADO: matar demo_worker→supervisor lo reinició solo (pid nuevo, restarts=2, en log). coches.net total oficial medido=249.963 (worker SSR brand-facet, ~94%; lista de slugs incluye body-types→sobre-cuenta, limpiar a partición). Arranque/parada: `supervisor/register_supervisor.ps1`/`unregister_supervisor.ps1`.

**CONFIG POR PORTAL `configs/portals/<source_key>.json` (commit 8f249fb):** esquema YA EXISTÍA en el repo (autotrack.nl/viabovag.nl/autolina.ch: source_key/strategy/endpoints/pagination/extraction.field_map/drift_baseline) — NO inventar paralelo, EXTENDER con stealth (anti_bot/access/count/facet_axes/leaf_cap/coverage/estado). Escritas con evidencia: mobile.de(faceted_api,1.586.022,100%), leboncoin.fr(sitemap,900K), coches.net(faceted_ssr,249.963,95.38%), autoscout24.de(faceted_ssr,831.463,cap 4.000/query, make-param PENDIENTE). `_SCHEMA.md` documenta el contrato. `facet_engine.load_config(source_key)` lee la config (config-driven). `tier1_runner.ingest_configs()` → ledger desde configs (fuente de verdad). 7 configuradas, 63 pendientes. Monitor dual-stack IPv6 fix (localhost fallaba por ::1): `monitor_server.py` bind `::`. Supervisor singleton con lock msvcrt.

Herramientas en `stealth/`: harness.py, batch_attack.py, dump_worker.py, facet_engine.py, seam_writer.py, make_dashboard.py, coches_coverage.py, extract_state.py, sitemap_recon.py, fix_camoufox_sxs.py, mobilede_probe*.py. `configs/portals/` configs versionadas. `supervisor/` daemon 24/7. Evidencia: stealth/RESULTS.md + TIER1_COVERAGE.md.
