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
