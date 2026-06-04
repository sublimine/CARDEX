# PLAN — Portales + Discovery + Infra (branch claude/focused-turing-e4c4c2)

Engine core ya existe (identity/proxy/antidetect/session/router/monitoring/pipeline/
intelligence/coordinator/scheduler). Esto añade los **portales**, el **discovery
genérico de dealers** y la **investigación de infraestructura**.

## Contrato (VERIFICADO leyendo el código)
- `scrapers/portals/base.py::BasePortalScraper` — template method `run()`. El scraper
  concreto implementa `partition_params()`, `fetch_segment(session, params, page)` y
  opcionalmente `subdivide_segment(params)`. Devuelve **deep-link URLs**, no roots.
- `run()` ya hace: tier+circuit, identidad warmed/trust, paginación con subdivisión por
  cap estructural, softblock por 3 ciclos vacíos, trust accounting, sink `on_urls`.
  Los scrapers **NO** reimplementan retry/proxy/identity.
- Registro: `scrapers/portals/__init__.py::PORTAL_REGISTRY` (key = `DOMAIN`).
- Tier baseline: `scrapers/engine/router/domain_map.py::REGISTRY`.
- Tests: pytest markers `unit`/`integration`; fakes `_Resp(status_code,text)` y
  `_Session([responses])`; fixtures `conn`, `active_identity`.

## Regla de oro
NO inventar endpoints. Cada URL de búsqueda VERIFICADA por web research / fetch real.
Confianza marcada [VERIFIED]/[ASSUMED] en código y en docs/research/*.md.

## Fases
1. [x] Recon contratos.
2. [ ] Research endpoints+anti-bot (agentes paralelos → docs/research/*.md).
3. [ ] Portales en orden: auto-api.ch, carapis.com, mobile.de, leboncoin.fr,
       coches.net, marktplaats.nl, kleinanzeigen.de, lacentrale.fr, 2dehands.be,
       comparis.ch. Cada uno: clase + registro + tier en domain_map.
4. [ ] discovery/dealer_discovery.py (Google Places, OSM Overpass, directorios) +
       portals/generic_dealer.py (detección de inventario + parseo HTML genérico).
5. [ ] docs/INFRASTRUCTURE.md (VPS, proxies, CAPTCHA, Camoufox, tabla de costes).
6. [ ] Tests nuevos + live run (auto-api.ch + 2 portales) con output real.
7. [ ] Suite completa verde + commit + push.

## Estado
Ver PROGRESO_PORTALS.md.
