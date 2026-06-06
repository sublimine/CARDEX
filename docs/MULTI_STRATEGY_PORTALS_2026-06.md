# Multi-Strategy Portal Extraction — T0/T1 (2026-06)

> Investigación de TODAS las vías de descubrimiento de deep-links para cada portal
> T0/T1 del registry, no solo paginación HTML. Para cada uno: sitemap.xml
> (listing / segment / index), robots.txt (Sitemap: + Disallow), API interna
> (JSON/REST/GraphQL/data-route). Recomendación de la vía óptima + implementación
> donde existía un sitemap-listing o API interna sin usar.

**Recordatorio arquitectónico [VERIFICADO]:** el scraper produce **URLs de detalle**
(deep-links) para un sink; NO extrae datos del vehículo (eso es la stage Go de
extraction). Por eso un **sitemap a nivel de listing** —que enumera cada URL de
detalle— es la fuente IDEAL: lista directa, sin cap de paginación, sin gatillar el
heurístico de rate del WAF, y la ruta más datacenter-IP-friendly que ofrece un sitio.

Evidencia: 8 agentes de investigación en vivo (curl robots/sitemap + lectura de
código) + verificación propia de las 20 estructuras de sitemap contra contenido
real (gunzip incluido) el 2026-06-06. Conectividad y conteos confirmados con
`curl`/`urllib` desde el host.

## Leyenda
- **Sitemap?**: `LISTING` = enumera URLs de detalle (oro) · `SEGMENT` = páginas
  marca/modelo/SRP · `INDEX→…` = índice que recursa a un hijo · `NONE` = no existe ·
  `403-GATED` = tras WAF/JA3 (necesita curl_cffi para confirmar).
- **API interna?**: `usada` = ya la usa el scraper · `YES <endpoint>` = existe sin usar · `NO`.
- **Estado**: `✅ MIGRADO` = cambié el scraper · `= ÓPTIMO` = ya era la mejor vía ·
  `⚠ ROTO` = scraper extrae 0 (bug, ver §Hallazgos) · `🌐 curl_cffi` = requiere
  browser/JA3 (fuera de alcance sitemap/API) · `💀 MUERTO` = portal cerrado/redirigido.

---

## Tabla maestra (57 portales)

| Portal | País | Vía actual (antes) | Sitemap? | API interna? | Vía óptima recomendada | Estado |
|---|---|---|---|---|---|---|
| marktplaats.nl | NL | API LRP `/lrp/api/search` (cap 5k, robots-disallow) | INDEX→LISTING (`l2.auto-s.*.gz`, ~200k) | usada (LRP, robots-disallow) | sitemap-listing | ✅ MIGRADO |
| 2dehands.be | BE | API LRP (cap 5k, robots-disallow) | INDEX→LISTING (`l2.auto-s.*.gz`, ~102k) | usada (robots-disallow) | sitemap-listing | ✅ MIGRADO |
| 2ememain.be | BE | API LRP (cap 5k, robots-disallow) | INDEX→LISTING (`l2.autos.*.gz`) | usada (robots-disallow) | sitemap-listing | ✅ MIGRADO |
| autokopen.nl | NL | Next.js data-route (buildId + campos [ASSUMED]) | LISTING (`100/101/102.xml`, 108k `/auto/detail/`) | usada (frágil) | sitemap-listing | ✅ MIGRADO |
| cardoen.be | BE | SSR `/fr/achat/?page` (regex 0 hits) | LISTING (`sitemap-product.xml`, 1.2k `/fr/auto/`) | NO | sitemap-listing | ✅ MIGRADO (arregla roto) |
| vroom.be | BE | SSR brand-pager (base 410, regex mal) | INDEX→LISTING (`listings-fr-*`, ~22k) | NO | sitemap-listing | ✅ MIGRADO (arregla roto) |
| gowago.ch | CH | SSR `/explore/used?page` (423 págs) | INDEX→LISTING (`products-sitemap-*`, ~5k) | NO | sitemap-listing | ✅ MIGRADO |
| aramisauto.com | FR | SSR `/achat/occasion?page` (regex stale) | LISTING (`sitemap-product.xml`, 2.9k `/voitures/…/rv{id}/`) | NO | sitemap-listing | ✅ MIGRADO |
| annonces-automobile.com | FR | SSR `/l-s/occasion?pg` (`/acheter/`) | INDEX→LISTING (`sitemap_detail.xml`, 44k `/d/{id}`) | NO | sitemap-listing | ✅ MIGRADO |
| carizy.com | FR | Nuxt SSR `?page` (regex no matchea) | INDEX→LISTING (`/voiture-occasion/sitemap.xml`, ~1k `/annonce/`) | NO | sitemap-listing | ✅ MIGRADO |
| capcar.fr | FR | SSR `/voiture-occasion?page` | LISTING (`/sitemap/products.xml`, 1k `…-r{id}`) | NO | sitemap-listing | ✅ MIGRADO |
| occasions.jeanlain.com | FR | SSR price-grid `?page` | INDEX→LISTING (`vehicle-sitemap.xml`, 2.5k) | NO | sitemap-listing | ✅ MIGRADO |
| gueudet.fr | FR | SSR 34-brand `?marque&page` (robots-disallow `?page`) | INDEX→LISTING (`storage/sitemap-vehicles.xml`, 5.3k) | NO | sitemap-listing | ✅ MIGRADO |
| distinxion.fr | FR | SSR 32-brand `?page` (Symfony) | INDEX→LISTING (`sitemap.catalog.xml`, 4.7k `/voitures/…/{id}`) | NO | sitemap-listing | ✅ MIGRADO |
| ocasionplus.com | ES | Next.js data-route ([ASSUMED]) | INDEX→LISTING (`sitemap.fichas-coches.xml`, 13.5k) | usada (frágil) | sitemap-listing | ✅ MIGRADO |
| autoboerse.de | DE | SSR 115-brand×precio | INDEX×2→LISTING (`Sitemap-Autoboerse-N`, ~250k `/fahrzeugsuche/{slug}/{id}`) | NO | sitemap-listing | ✅ MIGRADO |
| truckscout24.com | DE/EU | SSR `/{cat}/used?page` (cap 1k/cat) | INDEX→LISTING gz (`sitemap_listing_{1,2}.gz`, 80-120k `/tsp/ts-`) | NO | sitemap-listing | ✅ MIGRADO |
| classic-trader.com | DE/EU | SSR `/suche?page` (`/angebote/` → 0 hits) | INDEX→LISTING CDN (`sitemap.de.car.listing*`, 8.5k `/inserat/`) | NO | sitemap-listing | ✅ MIGRADO (arregla roto) |
| simplicicar.com | FR/BE | SSR `/occasions?page` (404, 0 hits) | LISTING (`/sitemap.xml`, ~6k `*.html`) | NO | sitemap-listing | ✅ MIGRADO (arregla roto) |
| caravenue.com | FR/BE/LU/CH | `__NEXT_DATA__` (App Router → 0 hits) | SEGMENT (sin URLs de detalle) | **YES** `/api/search-results` (JSON, ~2.9k) | API interna | ✅ MIGRADO (arregla roto) |
| autolina.ch | CH | API `m.autolina.ch/api/v2/searchcars` (sin cap) | INDEX→SEGMENT (SEO landing, no detalle) | usada | API actual | = ÓPTIMO |
| tutti.ch | CH | Next.js data-route + msgpack tokens | NONE (SPA fallback) | usada (data-route) | data-route actual | = ÓPTIMO |
| anibis.ch | CH | Next.js data-route (clon FR de tutti) | NONE | usada (data-route) | data-route actual | = ÓPTIMO |
| autosphere.fr | FR | API REST `/api/stock/vehicles` (sin cap) | INDEX→LISTING (`sitemap-fiche.xml`, fallback `/fiche/…`) | usada | API actual (sitemap = fallback válido) | = ÓPTIMO |
| heycar.com | FR | API REST `i15/search` (sin auth) | INDEX→NONE (sin VLP) | usada | API actual | = ÓPTIMO |
| wallapop.com | ES | API móvil `api.wallapop.com/api/v3` (bypass PerimeterX) | NONE | usada | API móvil actual | = ÓPTIMO |
| motor.es | ES | SSR `?pagina` año×precio | SEGMENT (`sitemap_vo.xml`, 0 `/anuncio/`) | NO (`/api/` disallow) | SSR actual | = ÓPTIMO |
| autocasion.com | ES | SSR provincia×combustible SRP | INDEX→SEGMENT (0 `-ref{id}`) | NO | SSR actual | = ÓPTIMO |
| coches.net | ES | API JSON `advgo.net/search` (egress ES) | 403-GATED (DataDome desde DC) | usada | API actual (sin ventaja en sitemap) | = ÓPTIMO |
| largus.fr | FR | SSR `occasion.largus.fr/auto/?currentpage` | INDEX→SEGMENT (solo SRP) | NO | SSR actual | = ÓPTIMO |
| viabovag.nl | NL | Next.js data-route `srp.json` | SEGMENT (`auto.xml` = 299 SRP) | usada (robots `*pagina-*` conflict) | data-route actual | = ÓPTIMO |
| autotrack.nl | NL | SSR `/aanbod?pageNumber` global | INDEX→SEGMENT (50k facet, 0 detalle) | NO | SSR actual (robots `/*?` conflict) | = ÓPTIMO |
| gaspedaal.nl | NL | SSR + JSON-LD ItemList `/zoeken?page` | SEGMENT (índice anidado, 0 detalle) | NO | SSR+JSON-LD actual | = ÓPTIMO |
| autohero.com | DE/IT/FR/ES/AT/PL/NL/SE | GraphQL `searchAdV9AdsV2` (~74 POST/país) | LISTING per-país (`{cc}/sitemap_search.xml`) | usada | sitemap per-país (optimización; cambia forma de URL — **no migrado**, ver §Hallazgos) | = ÓPTIMO* |
| paruvendu.fr | FR | SSR `/auto-moto/listefo/` (robots-disallow) | NONE (404) | NO (ruta SEO `/voiture-occasion/` robots-OK, paginación sin confirmar) | re-probar `/voiture-occasion/` con curl_cffi | 🌐 curl_cffi |
| spoticar.fr | FR | SSR `/voitures-occasion?page` (Stellantis) | 403-GATED (Akamai) | ? | re-probar sitemap con curl_cffi | 🌐 curl_cffi |
| leparking.fr | FR | SSR `/voiture-occasion/{brand}.html` ("sin WAF") | 403-GATED (Cloudflare managed) | ? | re-tier + curl_cffi (docstring "T1/no WAF" es FALSO) | 🌐 curl_cffi |
| comparis.ch | CH | SSR grid `/carfinder/marktplatz?page` | 403-GATED (DataDome; deep-links robots-disallow) | NO (`/carfinder/api/` disallow) | re-probar sitemap con curl_cffi | 🌐 curl_cffi |
| auto-selection.com | FR | Meilisearch `multi-search` (cap 1000/query) | INDEX→LISTING per-brand (`sitemap-annonce-liste-{brand}.xml`) | usada (capada) | sitemap per-brand (sin cap) — candidato, requiere confirmar índice de marcas | = ÓPTIMO* |
| carvago.com | DE/EU | Next.js data-route (paths 404) | SEGMENT (`sitemap-listed-cars` = 100 URLs) | YES `POST /api/listedcars` (capturar body) | capturar XHR `/api/listedcars` con curl_cffi | 🌐 curl_cffi (⚠ roto) |
| pkw.de | DE | SSR `www.pkw.de/autokatalog` (host equivocado, 0) | NONE (suche subdomain SPA) | XHR de `suche.pkw.de` (SPA) | mover a `suche.pkw.de` + capturar XHR | 🌐 curl_cffi (⚠ roto) |
| autohus.de | DE | SSR `/de/fahrzeugsuche/` (CSR, 0 hits) | NONE (detalle `*/vehicles/*` robots-disallow) | XHR Shopware (capturar) | capturar XHR de listings | 🌐 curl_cffi (⚠ roto) |
| clicars.com | ES | SSR brand SRP (JS-hydrated, ~0) | SEGMENT (`versions.xml` = catálogo, no stock) | descubrir API de stock | confirmar bajo curl_cffi o seed `versions.xml` | 🌐 curl_cffi (⚠ roto) |
| youcar.be | BE | SSR `/nl/search?page` (CSR, 0) | SEGMENT (índice malformado, HTML) | XHR de listings (capturar) | capturar XHR/headless | 🌐 curl_cffi (⚠ roto) |
| myway.be | BE | SSR `/fr/offre-voitures-occasion/` (CSR, 0) | SEGMENT (9.3k facet, 0 detalle) | XHR de listings (capturar) | capturar XHR/headless | 🌐 curl_cffi (⚠ roto) |
| nederlandmobiel.nl | NL | PHP SSR `?pagina` ("T0/sin WAF") | 403-GATED (Cloudflare managed JS) | NO | requiere solver JS (curl_cffi NO pasa) | 🌐 curl_cffi (⚠ roto) |
| autowereld.nl | NL | SSR brand pages ([ASSUMED], 0 hits) | NONE | NO (API deprecada) | consent-gate DPG + regex `/{brand}/{model}/{slug}-{id}/details.html` | ⚠ ROTO (ver §Hallazgos) |
| moniteurautomobile.be | BE | SSR `?page` (regex + param mal) | SEGMENT (solo marca/modelo) | NO | fijar regex `/detail-id--{id}--{slug}/…` + param `?p=` | ⚠ ROTO (ver §Hallazgos) |
| flexicar.es | ES | SSR `/coches-segunda-mano/?pagina` (regex mal) | SEGMENT (11k facet, 0 detalle) | NO | fijar regex `/coches-ocasion/{slug}_{id}/` | ⚠ ROTO (ver §Hallazgos) |
| buscocoches.com | ES | SSR brand `?pagina` (regex + filtro mal) | SEGMENT (gz brand SRP) | NO | fijar regex `…-ref{id}.html` (comilla simple, sin skip `segunda-mano-en-`) | ⚠ ROTO (ver §Hallazgos) |
| belgiemobiel.be | BE | PHP SSR brand-id (regex relativo vs hrefs absolutos) | NONE | NO (`/api/` `/json/` robots-disallow) | fijar regex para hrefs absolutos | ⚠ ROTO (ver §Hallazgos) |
| reezocar.com | FR | SSR año×precio | NONE (404) | NO | — portal cerrado 2024-11-04 | 💀 MUERTO |
| carforyou.ch | CH | SSR brand-pager ([ASSUMED]) | NONE (TLS fail) | NO | — dominio redirige a globalipaction.ch | 💀 MUERTO |

\* `= ÓPTIMO*`: el scraper actual funciona; el sitemap es una optimización documentada
no aplicada para no romper el contrato de URL del extractor (autohero) o por requerir
confirmación adicional (auto-selection). Ver §Optimizaciones documentadas.

---

## Implementación realizada

### Base nueva: `scrapers/portals/sitemap_listing_base.py`
`SitemapListingScraper(BasePortalScraper)` — descubre deep-links directamente desde
un sitemap de listings. Reutilizable; cada portal declara solo `SITEMAP_URL`
(o `SITEMAP_URLS`), `DETAIL_RE` y opcional `CHILD_RE`. Maneja:
- Recursión de `<sitemapindex>` anidado (hasta `MAX_SITEMAP_DEPTH=4`).
- Gunzip transparente de hijos `.gz` (detección por magic bytes `1f 8b`).
- Unescape de entidades XML, dedup, `CHILD_RE` para descartar shards no-vehículo.
- Politeness entre fetches (`SITEMAP_FETCH_DELAY` ± jitter).
- Todo dentro de `fetch_segment` (la session solo está disponible ahí); importa y
  testea sin red.

Encaja en el template `BasePortalScraper.run()` que el coordinator ya invoca
(`partition_params`→1 segmento, harvest en page 1) — **sin tocar el coordinator**.

### Switches a sitemap-listing (19 scrapers)
marktplaats.nl · 2dehands.be · 2ememain.be · autokopen.nl · cardoen.be · vroom.be ·
gowago.ch · aramisauto.com · annonces-automobile.com · carizy.com · capcar.fr ·
occasions.jeanlain.com · gueudet.fr · distinxion.fr · ocasionplus.com · autoboerse.de ·
truckscout24.com · classic-trader.com · simplicicar.com.

De ellos, **5 estaban rotos** (extraían 0 URLs) y el switch además los arregla:
cardoen, vroom, classic-trader, simplicicar, (+ aramisauto/carizy con regex stale).

### Switch a API interna (1 scraper)
caravenue.com → `GET /api/search-results?page=N` (JSON), reemplaza la extracción
`__NEXT_DATA__` muerta (App Router no expone ese blob).

### Tests
- `scrapers/tests/test_sitemap_listing.py` (NUEVO): 31 tests del base (recursión,
  gzip por magic bytes, `CHILD_RE`/`DETAIL_RE`, multi-entry, dedup, anti-loop,
  `_validate`), `_extract` del API de caravenue, config parametrizada de los 19
  migrados, y un `run()` smoke de marktplaats (harvest gz + exclusión `admarkt`).
- Tests de fase (`test_portals_phase{2,5,6_*,7,8,9,12,13}.py`) actualizados al nuevo
  contrato sitemap/API, preservando los portales NO migrados y el wiring
  (registry + domain_map) de cada uno.
- **Suite: 1185 passed, 1 failed (pre-existente, ajeno — ver §Nota).**

---

## Hallazgos colaterales (fuera del alcance sitemap/API, declarados)

### Scrapers rotos sin sitemap-listing alternativo (bug de extracción, extraen ~0)
Estos NO se migraron porque no hay sitemap de detalle ni API limpia; son **bugs de
regex/parámetro** que requieren verificación contra HTML en vivo (curl_cffi):
- **moniteurautomobile.be** — detalle real `/detail-id--{id}--{slug}/occasion.html`
  (regex actual matchea 0); paginación es `?p=` no `?page=`.
- **flexicar.es** — detalle `/coches-ocasion/{slug}_{id}/` (no `/coches-segunda-mano/…-{dig}`).
- **buscocoches.com** — detalle `…-ref{id}.html` con `href='…'` (comilla simple); el
  filtro `skip segunda-mano-en-` descarta justo las URLs válidas.
- **belgiemobiel.be** — la página emite hrefs ABSOLUTOS; el regex ancla en `/` relativo.
- **autowereld.nl** — doble gate (DPG consent + Akamai) + regex inválido; necesita
  handshake `/privacygate-confirm` y nuevo regex.

### Portales que requieren curl_cffi / browser (CSR-XHR o WAF/JA3-gated)
carvago.com (`POST /api/listedcars`) · pkw.de (`suche.pkw.de` SPA XHR) · autohus.de
(Shopware XHR) · clicars.com (SRP JS-hydrated) · youcar.be · myway.be · comparis.ch
(DataDome) · leparking.fr (Cloudflare managed — **docstring miente "T1/no WAF"**) ·
spoticar.fr (Akamai) · paruvendu.fr (ruta actual robots-disallow) · nederlandmobiel.nl
(Cloudflare managed JS, curl_cffi NO pasa — **scraper muerto como está escrito**).

### Portales muertos / redirigidos (candidatos a retirar del registry)
- **reezocar.com** — cierre permanente desde 2024-11-04 (página de cierre, rutas 404).
- **carforyou.ch** — dominio repurposed: TLS falla y redirige a globalipaction.ch.

### Optimizaciones documentadas (no aplicadas, declaradas)
- **autohero.com** — el `{cc}/sitemap_search.xml` per-país es estrictamente menos
  requests que ~74 POST GraphQL/país, PERO la forma de URL difiere
  (`/{make-model}/id/{uuid}/` vs API `/buy/{slug}-{id}/`). No migrado para no romper
  el contrato de URL del extractor; verificar que el sink acepta la forma `/id/{uuid}/`
  antes de cambiar.
- **auto-selection.com** — los `sitemap-annonce-liste-{brand}.xml` per-marca evitan el
  cap de 1000 hits del Meilisearch actual; migrar requiere enumerar el índice de marcas
  y la nueva forma `/voiture-occasion/{brand}/{model}/{slug}-{id}`.

### Conflictos robots.txt notados (cumplimiento)
Varias rutas actuales están técnicamente robots-disallow aunque devuelvan datos: las
APIs LRP de marktplaats/2dehands/2ememain (`/lrp/api/search*`) — **el switch a sitemap
las hace robots-compliant**; autotrack/gaspedaal/viabovag (`/*?` o `*pagina-*`);
paruvendu (`/listefo/`); comparis (`details/show`); caravenue (`/api/`).

### Código muerto detectado
Los flat files `scrapers/portals/{marktplaats,leboncoin,lacentrale,kleinanzeigen,
mobile_de,cochesnet}.py` y `nl/autotrack.py`, `es/autocasion.py` NO están en
`PORTAL_REGISTRY` (el registry usa los paquetes `<dir>/__init__.py`). Son duplicados
legacy basados en `HtmlSearchScraper`/`HttpPortalScraper`, que el coordinator nunca
siembra (`load_segments_from_sitemap` jamás se llama). Candidatos a eliminación.

## Nota — fallo de test pre-existente
`test_t1_portals.py::test_t1_registry_resolves_both_portals` falla porque espera que
`get_scraper("autotrack.nl")` sea la clase legacy `AutotrackNL` (de `nl/autotrack.py`,
dead code) cuando el registry resuelve `AutoTrackNLScraper` (paquete activo). **No fue
tocado por este trabajo** (git confirma: `autotrack_nl`, `test_t1_portals.py`,
`portals/__init__.py` sin cambios). Es deuda pre-existente del test stale; se corrige
junto con la eliminación del código muerto legacy.
