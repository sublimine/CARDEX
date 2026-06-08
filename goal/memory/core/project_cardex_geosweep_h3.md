---
name: project_cardex_geosweep_h3
description: "Estrategia de discovery geo-sweep con mallado H3 (hexagonal) para cobertura 100% de dealers, incl. long-tail"
metadata: 
  node_type: memory
  type: project
  originSessionId: 020fe92e-3d59-49f4-9abe-f0ad36acb37d
---

Idea estratégica validada por Salman (2026-06-06) para GOAL #2 (cobertura total de dealers, incl. "el garaje de pueblo con 4 coches"): **geo-sweep con H3 de Uber** — teselar cada país en celdas hexagonales de resolución variable (fino en ciudad, grueso en campo). El agente recorre celda a celda y en cada una ejecuta: (1) búsqueda geográfica de negocios del sector vía OSM/Overpass (GRATIS) y (2) barrido con diccionario multilingüe exhaustivo de términos por idioma (Autohaus, garage, occasion, taller, broker, importador… 2000+ términos). Doble red: geográfica + semántica.

**Valoración honesta:** alcanza el 100% de dealers con presencia digital, no el 100,00% absoluto (un negocio sin web ni registro ni ficha es invisible). Overpass cubre lo mapeado en OSM (gratis); el long-tail fuera de OSM requeriría Google Places Nearby por celda = DE PAGO → backlog. H3 garantiza cero huecos geográficos; complementa los registros mercantiles ([[feedback_budget_zero_park_paid]]).

**Estado:** anotada como capa de discovery futura del blueprint; NO implementada aún (Salman pidió solo valorarla). Incorporar al blueprint cuando se aborde la fase de dealers (P2). Ver [[project_cardex_architecture]] y [[goal_cardex_total_coverage]].
