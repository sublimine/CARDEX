# Phase-2 Portals — Research & Provenance

<!-- v1.0.0 | 2026-06-03 | Owner: Elias Karrouch -->
<!-- Resumen de investigación para los 6 scrapers de la fase 2. -->
<!-- La verdad de tier vive en scrapers/engine/router/domain_map.py; -->
<!-- la implementación vive en scrapers/portals/*.py. Este doc no los duplica: -->
<!-- registra QUÉ se verificó, QUÉ se asumió, y POR QUÉ cada portal toma su camino. -->

## Alcance

Seis portales onboardeados en la fase 2, cada uno con su scraper 360°
(`partition_params` + `subdivide_segment` + `fetch_segment`) sobre la base
`HttpPortalScraper`, registrados en `domain_map.py` y `portals/__init__.py`, y
cubiertos por `scrapers/tests/test_portals_phase2.py` (44 tests, mocked).

| Portal              | País | Tier        | WAF          | Método de acceso            | Shape de listing                         |
|---------------------|------|-------------|--------------|-----------------------------|------------------------------------------|
| `suchen.mobile.de`  | DE   | T2          | Akamai v3    | GET HTML (SRP fallback)     | `/fahrzeuge/details.html?id={id}`        |
| `leboncoin.fr`      | FR   | T3          | DataDome     | POST JSON (finder API)      | `ads[].url`                              |
| `kleinanzeigen.de`  | DE   | T1          | Cloudflare   | GET HTML (SRP)              | `/s-anzeige/{slug}/{id}`                 |
| `coches.net`        | ES   | T1 → T2     | Cloudflare   | POST JSON (Adevinta ms-mt)  | `items[].url`                            |
| `marktplaats.nl`    | NL   | T1          | Cloudflare   | GET → JSON (lrp API)        | `listings[].vipUrl`                      |
| `lacentrale.fr`     | FR   | T3          | DataDome     | GET HTML (listing page)     | `/auto-occasion-annonce-{id}.html`       |

## Leyenda de procedencia

- **[VERIFIED]** — leído de fuente real (contrato, diag, código) este ciclo o un
  artefacto estable de larga vida (path de detalle, código de categoría histórico).
- **[ASSUMED]** — inferido del patrón conocido del portal pero NO re-verificado
  contra HTML/JSON en vivo este ciclo. Marcado como tal en el docstring del módulo
  y aquí, para que el primer run de `diag.py` lo confirme o lo corrija.

El esqueleto de cada scraper (retry/backoff, detección estructural de cap,
subdivisión por precio, dedupe, clasificación WAF) es **[VERIFIED]**: deriva del
patrón probado de `autoscout24_base.py` y se ejercita en los tests. Lo que se marca
`[ASSUMED]` es siempre el *gold nugget* de cada portal: nombres exactos de
parámetros y endpoints que solo una petición en vivo puede sellar.

---

## mobile.de (`suchen.mobile.de`) — T2, Akamai v3

**Por qué dos entradas de registro.** mobile.de expone dos caminos disjuntos:
- `mobile.de` → **T0**, el consumer Ad-Stream WSS de la mobile-API (otro pipeline).
- `suchen.mobile.de` → **T2**, ESTE scraper: la SRP pública
  (`suchen.mobile.de/fahrzeuge/search.html`) tras Akamai v3, fallback de tier
  browser cuando la API no está disponible.

La entrada `suchen.mobile.de` T2 se inserta **primero** en `REGISTRY` porque
`get()` es first-match-wins y el patrón `mobile.de` también casa el subdominio
`suchen.`. El `DOMAIN` del scraper es `suchen.mobile.de` exactamente para que
enrute a T2/Akamai, nunca al T0. **[VERIFIED]** vía smoke test:
`suchen.mobile.de→T2`, `mobile.de→T0`, `www.mobile.de→T0`.

- **Request** [ASSUMED]: `GET /fahrzeuge/search.html?vc=Car&isSearchRequest=true&ref=srp&sb=rel&od=up&dam=false&fr={yf}:{yt}&p={pf}:{pt|''}&pageNumber={n}`. Los nombres de parámetro (`fr`, `p`, `pageNumber`) se infieren del query-string clásico de la SRP; el path y el shape del deep link son la parte estable.
- **Extracción** [VERIFIED como patrón]: regex `/fahrzeuge/details\.html\?id=(\d+)` sobre el body, deduped por página.
- **Paginación / cap**: `PAGE_SIZE=20`, `MAX_PAGES=50`. Akamai capa la paginación profunda mucho antes de agotar inventario → ventana de precio cap-eada se subdivide por mitades disjuntas.
- **Soft-block** [VERIFIED]: Akamai a veces sirve un 200 "Access Denied" en vez de 403. `_is_soft_block` hace OR del veredicto base con marcadores propios (`access denied`, `you don't have permission to access`, `reference #`, `errors.edgesuite.net`) — un 200-challenge se reintenta, nunca se parsea. Necesario porque "Access Denied" NO es un `_CHALLENGE_MARKER` del clasificador base (la señal de Akamai es la cookie `_abck`).

---

## leboncoin.fr — T3, DataDome

**Por qué JSON.** Los front-ends web/mobile de LeBonCoin leen de una API de
búsqueda JSON en vez de renderizar server-side, así que el camino correcto más
barato es POSTear la misma query que el sitio y leer los deep links del JSON.
DataDome obliga a T3 (behavioral + residential): el request debe parecer humano,
pero el *parsing* es JSON trivial.

- **Request** [ASSUMED]: `POST https://api.leboncoin.fr/finder/search`, headers `api_key` (`ba0c2dad52b3ec`, key pública del front web) + `Content-Type` + `Origin/Referer`. Body: `filters.category.id="2"` (Voitures), `filters.ranges.regdate={min,max}`, `filters.ranges.price={min[,max]}` (open-ended → `max` omitido), `limit=35`, `offset=(n-1)*35`, `sort_by=time desc`. La categoría `"2"` es valor histórico estable de LeBonCoin.
- **Extracción** [VERIFIED como patrón]: `ads[].url` con guards dict/list/str, deduped.
- **Paginación / cap**: `PAGE_SIZE=35`, `MAX_PAGES=100`. Subdivisión por precio al tocar cap.
- **Soft-block** [VERIFIED]: 403 (base `BLOCK_STATUSES`) o body con `captcha-delivery.com` (ya marcado por el clasificador base). Sin override.

---

## kleinanzeigen.de — T1, Cloudflare Pro

**Por qué HTML.** kleinanzeigen.de (ex eBay Kleinanzeigen) renderiza sus
clasificados de coches server-side, así que basta un GET a la SRP de autos y un
regex sobre el HTML. T1 (curl_cffi chrome impersonation, sin browser) tras
Cloudflare Pro — el challenge es el interstitial CF estándar que el clasificador
base ya marca, sin override.

- **Request** [ASSUMED]: `GET /s-autos/preis:{pf}:{pt|''}/seite:{n}/c216+autos.ez_i:{yf},{yt}`. Los segmentos de path (`c216`=Autos, filtros `preis:`/`seite:`, sufijo `c216+autos.ez_i:` para el rango de matriculación) se infieren de la gramática de URL estable de kleinanzeigen.
- **Extracción** [VERIFIED como patrón]: regex `/s-anzeige/[a-zA-Z0-9-]+/\d+-\d+-\d+` (group(0)), prefijado con base, deduped.
- **Paginación / cap**: `PAGE_SIZE=25`, `MAX_PAGES=50`. Subdivisión por precio.
- **Soft-block** [VERIFIED]: CF estándar, sin override.

---

## coches.net — T1 → T2, Cloudflare Pro

**Por qué JSON.** coches.net es propiedad Adevinta/Schibsted; su front-end web
lee de un servicio de búsqueda JSON (`ms-mt`). Camino: POSTear la misma query y
leer del JSON. T1 (curl_cffi) con techo de escalada a T2 (Camoufox) tras CF Pro.

- **Request** [ASSUMED — shape completo]: `POST https://ms-mt--api-web.spain.advgo.net/search`, headers `Content-Type` + `X-Adevinta-Channel:web` + `X-Schibsted-Tenant:coches` + `Origin/Referer`. Body: `pagination{page,size}`, `sort{order:desc,term:publishedDate}`, `filters{categoryId:2, price{from[,to]}, year{from,to}}` (open-ended → `to` omitido). Endpoint, payload y headers se infieren del contrato "ms-mt" compartido entre marketplaces Schibsted; el shape `items[].url`/`.aspx` es la parte más estable.
- **Extracción** [VERIFIED como patrón]: `items[].url` con guards, deduped.
- **Paginación / cap**: `PAGE_SIZE=30`, `MAX_PAGES=50`. Subdivisión por precio.
- **Soft-block** [VERIFIED]: CF estándar, sin override.

---

## marktplaats.nl — T1, Cloudflare Pro

**Por qué GET-que-devuelve-JSON.** marktplaats.nl expone un endpoint "listing
results page" (lrp) JSON que su propio front-end consume. Aunque devuelve JSON,
es un GET con filtros en query-string, así que usa el camino GET base y parsea el
JSON en `_extract`. T1 (curl_cffi) tras CF Pro, sin override.

- **Request** [ASSUMED]: `GET /lrp/api/search?l1CategoryId=91&offset={(n-1)*30}&limit=30&attributesByKey[]=PriceCents:{pf*100}:{pt*100|''}&attributesByKey[]=constructionYear:{yf}:{yt}`. Categoría L1 `91` (Auto's), precio denominado en céntimos, rangos `offset/limit`. Nombres inferidos del contrato lrp; el shape `listings[].vipUrl` es la parte estable.
- **Extracción** [VERIFIED como patrón]: `listings[].vipUrl` (`/v/auto-s/…`), prefijado con origen si es relativo (se mantiene si ya es `http`), deduped.
- **Paginación / cap**: `PAGE_SIZE=30`, `MAX_PAGES=30`. Subdivisión por precio.
- **Soft-block** [VERIFIED]: CF estándar, sin override.

---

## lacentrale.fr — T3, DataDome

**Por qué HTML.** lacentrale.fr renderiza su listado de ocasión server-side, así
que el camino correcto más barato es un GET a la página de búsqueda y un regex
sobre el HTML por deep links de detalle. DataDome obliga a T3 (behavioral +
residential): el request debe parecer humano, pero el *parsing* es HTML trivial.

- **Request** [ASSUMED]: `GET /listing?priceMin={pf}[&priceMax={pt}]&yearMin={yf}&yearMax={yt}&page={n}` (`priceMax` omitido cuando open-ended). Nombres de parámetro inferidos de la gramática de URL del listado; el shape `/auto-occasion-annonce-{id}.html` es la parte estable.
- **Extracción** [VERIFIED como patrón]: regex `/auto-occasion-annonce-(\d+)\.html`, reconstruido a URL absoluta, deduped.
- **Paginación / cap**: `PAGE_SIZE=16`, `MAX_PAGES=100`. Subdivisión por precio.
- **Soft-block** [VERIFIED]: 403 (base) o body con `captcha-delivery.com` (clasificador base). Sin override.

---

## Estrategia común (HttpPortalScraper) — [VERIFIED]

- **Grid de partición**: producto cartesiano de `YEAR_BANDS` (11 bandas) × `PRICE_RANGES` (8 ventanas disjuntas `[from,to)`) = **88 segmentos** por portal. Verificado por test parametrizado sobre los 6.
- **Detección de cap estructural**: en `_paginate`, `if len(page_urls) < PAGE_SIZE: break`; luego `if page == MAX_PAGES: hit_ceiling=True; break`. Sin contar resultados totales — puro shape de respuesta.
- **Recuperación de cap**: subdivisión de un nivel vía `split_price` (mitades de la ventana). Devuelve `[]` para ventanas open-ended (`price_to=None`) o de ancho ≤ `_MIN_SPLIT_WIDTH` (500) — no se subdivide lo indivisible.
- **Retry/backoff**: `RETRY_ATTEMPTS=3`, `RETRY_BACKOFF_BASE=2.0`, `REQUEST_TIMEOUT=20`, `BLOCK_STATUSES={403,429,503}`, `SOFTBLOCK_BACKOFF_FACTOR=2.0`. Error de transporte → `None` → reintento. 404 → sin reintento (terminal no-block).
- **Trust**: +0.05 por éxito, −1.0 por soft-block (heredado de la base).

## Pendiente de sellar en el primer `diag.py`

Todo lo `[ASSUMED]` arriba: nombres exactos de parámetros de query, endpoints de
API (`ms-mt--api-web.spain.advgo.net`, `api.leboncoin.fr/finder/search`),
`api_key` del front de LeBonCoin, y códigos de categoría (`c216`, `"2"`, `2`,
`91`). El esqueleto no cambia; solo se confirman o ajustan estos valores contra
respuestas reales. Cualquier divergencia se corrige en el módulo del portal y se
reetiqueta a `[VERIFIED]` aquí.
