# PLAN — Multi-Strategy Portal Investigation (2026-06)

## Misión
Para cada portal T0/T1 (57 total), investigar TODAS las vías de extracción de
deep-links: sitemap.xml (listing-level / segment / index), robots.txt (Sitemap:
declarations + Disallow), API interna (JSON/REST/GraphQL). Recomendar la vía
óptima. Implementar el cambio donde exista sitemap-listing o API interna sin usar.

## Contexto arquitectónico [VERIFIED]
- El scraper produce **deep-link URLs** (URLs de detalle) para un sink. NO extrae
  datos del vehículo (eso es la stage Go de extraction).
- Por tanto un **sitemap a nivel de listing** (enumera cada URL de vehículo) es la
  fuente IDEAL: lista directa, sin cap de paginación, datacenter-IP-friendly.
- Bases: `base.py` (template), `http_base.py` (GET-HTML o POST/GET-JSON),
  `html_search_base.py` (sitemap-seeded segments + HTML search), `autoscout24_base.py`.
- Scraper activo = `scrapers/portals/<dir>/__init__.py`. Los flat files
  (`marktplaats.py`, `leboncoin.py`, etc.) NO están en PORTAL_REGISTRY → dead code.

## Clasificación de sitemap
- **LISTING** → enumera URLs de detalle de vehículos → harvest directo (reemplaza paginación). ORO.
- **SEGMENT** → páginas marca/modelo/categoría → seed de segmentos (HtmlSearchScraper).
- **INDEX** → apunta a sub-sitemaps → recursar.
- **NONE/403** → 404 = no hay; 403/challenge = puede existir tras JA3 gate (confirmar con curl_cffi).

## Batches (8 agentes paralelos)
1. NL: marktplaats, nederlandmobiel, viabovag, autotrack, gaspedaal, autokopen, autowereld
2. BE: tweedehands(2dehands), 2ememain, cardoen, moniteurautomobile, youcar, myway, belgiemobiel, vroom
3. CH: autolina, tutti, anibis, carforyou, gowago, comparis
4. FR-1: autosphere, auto-selection, heycar, paruvendu, largus, aramisauto, leparking, reezocar
5. FR-2: spoticar, annonces-automobile, starterre, carizy, capcar, jeanlain, gueudet, distinxion
6. ES: wallapop, motor, autocasion, ocasionplus, flexicar, clicars, buscocoches, coches.net
7. DE: autoboerse, carvago, auto.de, pkw, autohaus24, autohus, truckscout24, classic-trader
8. MULTI: autohero, caravenue, simplicicar

## Criterios de aceptación
- [ ] docs/MULTI_STRATEGY_PORTALS_2026-06.md con tabla completa (57 filas)
- [ ] Cada fila: Portal | País | Vía actual | Sitemap? | API interna? | Vía óptima
- [ ] Implementado el cambio en portales con sitemap-listing o API interna sin usar
- [ ] Tests verdes en los scrapers tocados (GOWORK no aplica — Python; pytest)
- [ ] Stack Strategy B intacto, JA3 coherente, sin .exe
