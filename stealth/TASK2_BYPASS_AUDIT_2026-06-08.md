# Task 2 — Bypass exhaustion: lacentrale (DataDome) · milanuncios (PerimeterX)
**Fecha:** 2026-06-08 · **Modo:** live probing (curl_cffi + Camoufox), solo lectura · **Host IP:** datacenter/CH (flagged)

Veredicto corto: **ninguna vía gratis rinde inventario.** El bloqueo está en la **capa de reputación de IP/ASN** (DataDome y PerimeterX flaggean esta IP), no solo en el reto JS — por eso Camoufox (que vence Akamai gratis en mobile.de) NO basta aquí. **Requieren proxy residencial de pago** (FR para lacentrale, ES para milanuncios). Filas insertadas: **0** en ambos (BEFORE=AFTER=0).

## lacentrale.fr (DataDome)
| Vía | Probado | Resultado |
|---|---|---|
| a) curl_cffi /api/v1/search, /api/v2, /graphql, /lrp/api/search, /finder/search, /vo/api, /mobile/api | sí | **403 DataDome** (geo.captcha-delivery) en TODAS |
| a) subdominios api./ws./mobile./app./bff./gateway./search./vo./gw./edge./m2./data. | sí | **DNS no resuelve** (no existen) |
| b) sitemap.xml, sitemap_index.xml, sitemaps.xml, robots.txt | sí | **403 DataDome** (incl. robots) |
| b) ficha de detalle directa (auto-occasion-annonce-*.html) | sí | **403 DataDome** (el detalle TAMBIÉN está gateado) |
| Camoufox warm home + 3 settle/reload, locale fr-FR | sí | **403 DataDome en la propia home** |
| c) Tor | sí | no instalado (9050 rechaza) |
| c) proxies free (Proxifly datacenter) | sí | timeout (muertos); datacenter → ASN-flag de todos modos |
| d) repos bypass GitHub 2025-26 | evaluado | requieren residencial; ninguno crackea headless desde IP flagged |
→ **Requiere proxy residencial FR/EU.** Adaptar: residencial FR + Camoufox (test gratis = ScrapeOps residential free 100MB, requiere API key).

## milanuncios.com (PerimeterX / HUMAN)
| Vía | Probado | Resultado |
|---|---|---|
| a) curl_cffi /api/v3/ads, /api/v1/listings | sí | **404** (no existen) |
| a) curl_cffi /lrp/api/search, /graphql, /ms/search, /mu-api, /services/search | sí | **405 PerimeterX** "Pardon Our Interruption" |
| a) subdominios api./ws./mobile./app./gateway./search./prod./gw./edge. | sí | **DNS no resuelve** |
| b) sitemap.xml, sitemap_index.xml, /sitemaps/, sitemap-coches.xml | sí | **403 AmazonS3** access denied |
| b) robots.txt | sí | **405 PerimeterX** |
| Camoufox home | sí | **200** (1,2MB) — pero solo shell; carrusel `warrantyCarsCarousel` no expuso ads parseables (0 extraídos) |
| Camoufox /coches-de-segunda-mano/ (listing) + reload ×2, locale es-ES | sí | **405 PerimeterX** ambas tries |
| c) Tor / proxies free | sí | igual que lacentrale (no viable) |
| d) repos bypass | evaluado | PerimeterX domina con biometría de ratón (press&hold); solver+residencial necesarios |
→ **Requiere proxy residencial ES + capa behavioral/solver PX.** Adaptar: residencial ES + solver (p.ej. Pr0t0ns/PerimeterX-Reverse) o servicio PX.

## Contraste con mobile.de (la línea gratis/pago)
- **Akamai v3 (mobile.de): GRATIS con Camoufox** — warm pasa, ~99% del catálogo enumerable por faceteo, ~964 listings/min/navegador.
- **DataDome (lacentrale) y PerimeterX (milanuncios): NO gratis** — bloqueo a nivel IP/ASN; sin proxy residencial no hay vía. Esa es la frontera real.
