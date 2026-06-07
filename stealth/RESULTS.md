# FRENTE STEALTH GRATIS — Resultados con evidencia dura

> Regla: nada se declara "cae" o "no cae" sin HTTP 200 + datos reales extraídos
> (o el bloqueo capturado). Host egress = **IP residencial Swisscom CH**
> (83.77.233.252, AS3303) — factor anti-bot de mayor peso, ya nativo.
> Stack: Camoufox v135.0.1-beta.24 (Firefox stealth) + curl_cffi 0.15.0.

## Pre-requisito resuelto: Camoufox no arrancaba (Application Control NO era la causa)
- Síntoma: `BrowserType.launch: spawn UNKNOWN`.
- Causa raíz (event log SxS): manifiesto embebido de `camoufox.exe` declara dependencia
  SxS al assembly `mozglue` que Windows no resuelve.
- Fix: `stealth/fix_camoufox_sxs.py` neutraliza ese bloque `<dependency>` en el PE
  (byte-patch, mismo tamaño, reversible vía `camoufox.exe.orig`). Evidencia: tras el
  patch, `camoufox.exe --version` → `Mozilla Firefox 135.0.1-beta.24` (exit 0); smoke
  test example.com → HTTP 200.

---

## Tabla de veredictos (gigantes Tier-1)

| Portal | País | Anti-bot | Vía | Veredicto | Evidencia |
|---|---|---|---|---|---|
| **coches.net** | ES | DataDome | Camoufox → `__INITIAL_PROPS__` | ✅ **CAE** | HTTP 200, 35 listings/pág reales (id/precio/km/año/modelo/URL) |
| **autoscout24.de** | DE | Akamai | Camoufox → `__NEXT_DATA__` | ✅ **CAE** | HTTP 200, 20 listings/pág `props.pageProps.listings` (Opel/Renault/Nissan, precios reales) |
| **mobile.de** | DE | Akamai Bot Mgr v2 | Camoufox + warm-up + settle → `__INITIAL_STATE__` | ✅ **CAE** (~4,4M) | HTTP 200, 28 listings/pág `search.srp.data.searchResults.items` (Ford Kuga 8.490€, VW Golf GTI 16.950€) |
| **leboncoin.fr** | FR | DataDome | Camoufox + warm-up → `__NEXT_DATA__` (+API `api.leboncoin.fr/.../v7/fdata`) | ✅ **CAE** | HTTP 200, 35 listings/pág `props.pageProps.searchData.ads` (Audi A3 22.490€, Renault Austral 25.799€) |
| **milanuncios.com** | ES | PerimeterX (HUMAN) | Camoufox + warm-up + settle×3 | ⛔ **BLOQUEA (por ahora)** | "Pardon Our Interruption" HTTP 405, 100KB, persiste 3 reloads — geo-mismatch (sitio ES / IP CH); pendiente proxy ES |
| **autoscout24.fr** | FR | Akamai | Camoufox → `__NEXT_DATA__` | ✅ **CAE** | HTTP 200, 20 listings `props.pageProps.listings` |
| **autoscout24.es** | ES | Akamai | Camoufox → `__NEXT_DATA__` | ✅ **CAE** | HTTP 200, 20 listings |
| **autoscout24.nl** | NL | Akamai | Camoufox → `__NEXT_DATA__` | ✅ **CAE** | HTTP 200, 20 listings |
| **autoscout24.ch** | CH | (Nuxt) | Camoufox → DOM `/de/d/` | ✅ **CAE** | HTTP 200, 20 anuncios (BMW 420d/540d/i4 M50) |
| **autoscout24.be** | BE | Akamai | Camoufox (URL locale) | 🔧 **URL fix** | `/lst`=404; usa prefijo `/nl/` o `/fr/` (misma plataforma que .de → extraerá) |
| **kleinanzeigen.de** | DE | Akamai | Camoufox → DOM `data-adid` | ✅ **CAE** | HTTP 200, 27 anuncios (Nissan Note, Volvo C30, BMW X1, Peugeot 3008) |
| **gumtree.com** | UK | Cloudflare | Camoufox → DOM `/p/{make}/…/{id}` | ✅ **CAE** | HTTP 200, 12 anuncios (SEAT Leon, Jaguar XF, Skoda Karoq, Honda Civic) |
| **lacentrale.fr** | FR | DataDome | Camoufox + settle×3 | ⛔ **BLOQUEA (por ahora)** | HTTP 403 `captcha-delivery`/`geo.captcha`; settle no limpia → requiere proxy FR / captcha |

**Marcador: 10 gigantes CAEN gratis** (coches.net, mobile.de, leboncoin, autoscout24 ×5 [de/fr/es/nl/ch], kleinanzeigen, gumtree). 2 bloqueados por geo (milanuncios PerimeterX, lacentrale DataDome) → proxy del país. as24.be = fix de URL trivial.

---

## ESCALA — Sitemap-first (medición del yacimiento, capa de red curl_cffi)

> Regla: el tamaño real del yacimiento se mide por el sitemap de anuncios, no
> paginando. Verificado que las URLs sean anuncios reales (no SEO/facetas).

| Portal | Sitemap anuncios | Nº URLs medido | Naturaleza (verificada) | Vía de escala |
|---|---|---|---|---|
| **leboncoin.fr** | `auto-main.xml` → 18× `auto-voitures-adview-N.xml` | **~900.000** | ✅ ANUNCIOS reales (`/ad/voitures/{id}`, 50.000/sitemap) | **Sitemap directo** (sin bloqueo en red) → fetch detalle |
| **mobile.de** | `/sitemap.xml` → 16× `carspecification-N` | ~80.000 | ⚠ páginas SEO de spec (`/auto/bmw-x6-...html`), NO anuncios | search-API `__INITIAL_STATE__` + facetas (los ~4,4M no están en sitemap) |
| **autoscout24.ch** | `/sitemap.xml` → `srp-N.xml` | ~8.163 | ⚠ páginas de búsqueda facetada (`/de/s/...`), NO anuncios | `__NEXT_DATA__` + facetas |
| **coches.net** | `sitemap-index.xml` | — | sitemap **405-bloqueado** en red | `__INITIAL_PROPS__` + facetas/paginación (camoufox) |
| **autoscout24.de/.fr/.es/.nl/.be** | ninguno declarado; `/sitemap.xml`=404 | — | sin sitemap público de anuncios | search-funnel `__NEXT_DATA__` + facetas |

**Conclusión de escala:** solo **leboncoin** publica el universo de anuncios en
sitemap (~900K, cosechable directo por red). Para los demás, el camino completo
es la **API/SSR interna ya crackeada + faceteo** (marca×región×precio) para
cubrir bajo cualquier cap. mobile.de (~4,4M) y AS24 (6 países) NO exponen sus
anuncios en sitemap — su sitemap son páginas SEO/facetas.

### Validación end-to-end leboncoin (sitemap → detalle)
Anuncio `3173575107` tomado del sitemap `auto-voitures-adview-1.xml` → fetch detalle
con Camoufox → HTTP 200 → `__NEXT_DATA__` (`props.pageProps.ad`):
- subject="Mercedes Classe A 200 d 150ch Progressive Line 8G-DCT" · **25.490 €**
- brand=Mercedes · model=Classe A · regdate=2021 · mileage=79.980 km · fuel=Diesel
- list_id, url, first_publication_date, location, images, owner, attributes completos.
**Pipeline coste-cero completo demostrado: sitemap (900K URLs) → detalle → registro rico.**

---

## WORKER de volcado por faceteo + DELTA (tarea 4) — `dump_worker.py`
Worker persistente RAM-safe (camoufox conc 1) que pagina el catálogo, extrae del
estado SSR ya crackeado, **normaliza al contrato seam** y calcula el DELTA.

**Prueba E2E leboncoin (límite local 60):**
- run1: page1=35 + page2=25 → **harvested=60, schema_valid=60/60** (100%).
- Registro normalizado real: `{source_url, url_hash, source_domain, country, title,
  price_eur=8990, make=Volkswagen, model=Golf, year=2017, mileage_km=175000,
  fuel=Diesel, city, region}` → mapea directo a `vehicle_index` (L1) + campos ricos.
- **DELTA detecta altas y bajas:**
  - Determinista (unit): prev=5, cur=5 → SEEN_new(altas)=2, GONE(bajas)=2, present=3. ✅
  - En vivo run1→run2: prev=60 cur=60 → SEEN_new=60, GONE=60 (leboncoin rota
    resultados entre cargas; para delta estable usar `sort=time`). ✅
- Local validar-con-límite-y-purgar: `--limit N` corta; `--purge` borra el harvest
  y deja snapshot+delta+sample (volcado íntegro = VPS, `--limit 0`).

**Escala accesible por portal (medida):** leboncoin ~900.000 (sitemap directo);
mobile.de/AS24/coches por faceteo marca×región×precio sobre la API/SSR interna
(35-20/página, sin cap observado en página 1-2). Faceteo = config, no código nuevo.

## milanuncios con proxy ES (tarea 3)
2 proxies ES libres validados (GIGAS Hosting, XTRA Telecom) **murieron en minutos**
(libres = efímeros + datacenter → PerimeterX los marca). Veredicto honesto:
milanuncios requiere **proxy residencial ES estable** (única dependencia de pago
real del set). lacentrale igual (DataDome + geo FR).

## MOTOR DE FACETEO RECURSIVO (`facet_engine.py`) — cobertura total por portal

**Inteligencia de API mobile.de (probada in-page tras Akamai, evidencia en `mobilede_probe*.json`):**
- Endpoint de faceteo: **`https://m.mobile.de/svc/s/?vc=Car&…&p=N`** → JSON `{numResultsTotal, items[]}`, sin clave.
- **Total vivo real = 1.586.008 coches** (la cifra "4,4M" era asumida; el universo vivo es ~1,58M).
- Items con `id, makeId, modelId, make, model, price, url, title, attr{fr,ml,ft,pw,cc,loc,z…}` → normalización directa.
- **Refdata marcas: `m.mobile.de/svc/r/makes/Car`** → `[{i:1900,n:"Audi"},…]` (lista completa con IDs).
- **Ejes de faceteo descubiertos** (cambian `numResultsTotal`): `ms`=marca (`1900;;;`=Audi→130.370), `fr`=año (`2018:2020`→195.348), `ml`=km (`0:50000`→620.091). Precio min/max no filtra (param distinto).
- **Sin cap bajo de paginación**: `p=1000` aún devuelve 20 items → paginación profunda; el faceteo es por eficiencia/rate, no por romper cap.

**Diseño del motor (config-driven, genérico para los ~73 tier-1):**
1. `count(filters)` = una llamada in-page `svc/s/…&p=1` → `numResultsTotal`.
2. Recursión: si `count > CAP` (2.000), subdivide en el siguiente eje (`ms→fr→ml`) hasta hoja `< CAP`.
3. **Prueba de cobertura por conteo**: `Σ(conteos de hojas) ≈ total root`. Partición por marca (cada coche tiene make) reconcilia contra 1,58M; deep-dive marca×año reconcilia contra el conteo de la marca.
4. Enumeración de hojas (validar-con-límite local) → normaliza al contrato seam → DELTA (SEEN/GONE) vs snapshot.
5. Una sola sesión Camoufox calienta Akamai; todo count/enumerate es `page.evaluate(fetch)` in-page (cookie/TLS válidos). RAM-safe, worker persistente desacoplado.

**Resultado de cobertura mobile.de** (ver `facet/mobilede_coverage.json`):
- ROOT (`vc=Car`) = **1.586.022** coches · 178 marcas en refdata.
- **Σ(conteos por marca) = 1.586.026 → cobertura = 100,0 %** (el +4 es churn vivo durante el escaneo de ~3 min). **El faceteo por marca cubre el catálogo entero por conteo.**
- Top marcas (>CAP, requieren subdivisión): VW 258.494, Mercedes 171.880, BMW 135.825, Audi 130.367, Ford 102.568, Opel 95.068.
- Deep-dive VW por año: make=258.494, Σ(años)=239.016 → **92,5 %**; el ~7,5 % restante son listings **sin año de matriculación** (escapan al filtro `fr`) → cierre con bucket `fr` desconocido o eje `ml`. Hallazgo honesto, no se oculta.

## Herramientas entregadas (en `stealth/`)
- `fix_camoufox_sxs.py` — repara el arranque de Camoufox en Windows (byte-patch SxS, reversible).
- `harness.py` — colector de evidencia Camoufox: navega, detecta bloqueo, warm-up + settle
  anti-Akamai/CF, captura XHR/API, extrae `__NEXT_DATA__`/`__INITIAL_PROPS__`, screenshot.
- `extract_state.py` — extrae el estado JS embebido (`JSON.parse("…")`, índice de arrays de listings).
- `sitemap_recon.py` — robots→índice→sitemaps de anuncios, cuenta URLs reales, marca SEO/facetas/bloqueos.
- `test_coches_api.py` — prueba de la API keyless (resultado: 502 CloudFront, vía SSR la sustituye).
- `smoke_test.py` — verificación de arranque del navegador.

## Veredicto del frente
- **4 de los "gigantes de pago" son GRATIS** vía Camoufox + IP residencial CH (nativa) + estado SSR:
  mobile.de (~4,4M), autoscout24 (Akamai), leboncoin (~900K, sitemap directo), coches.net.
- **1 bloqueado por ahora:** milanuncios (PerimeterX + geo-mismatch → requiere proxy ES).
- **Pendientes de probar** (mismo método): kleinanzeigen, lacentrale, gumtree, AS24 .fr/.es/.nl/.be/.ch
  (extracción), y proxies ES/DE rotados para los geo-sensibles.

---

## coches.net — ✅ CAE (DataDome vencido)
- **Vía:** Camoufox (headless, humanize, IP residencial CH) navega
  `https://www.coches.net/audi/segunda-mano/` → HTTP **200**, sin señales de bloqueo,
  título real "AUDI de segunda mano y ocasión | Coches.net", 1,37 MB.
- **Datos:** `window.__INITIAL_PROPS__ = JSON.parse("…")` → `$.initialResults.items`
  = **35 vehículos** con campos: `id, title, price, km, year, make, model, fuelType,
  url, location, hp, isFinanced, isProfessional, hasWarranty, …`.
- **Muestra real (evidence/coches_audi_listings.json):**
  - AUDI Q3 45 TFSI S tronic Quattro · 35.750 € · 36.000 km · 2022 · Málaga
  - AUDI A3 Sportback 45 TFSI e · 37.990 € · 17.300 km · 2024 · Madrid
  - AUDI A4 Avant S line 40 TFSI · 27.000 € · 122.550 km · 2021 · Málaga
- **Nota API directa:** el endpoint keyless del repo (`ms-mt--api-web.spain.advgo.net/
  search/listing`) devuelve **502 CloudFront** desde esta IP (datacenter y residencial
  igual) → contrato stale/edge-gated. La vía SSR (`__INITIAL_PROPS__`) lo hace
  innecesario: el dato ya viene renderizado por página de marca.
- **Escala:** 35/página SSR; paginación + iteración por marca/provincia escala a todo
  el inventario ES. Cost-zero.
