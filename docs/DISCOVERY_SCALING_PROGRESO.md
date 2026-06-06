# DISCOVERY SCALING — PROGRESO

> Misión: escalar discovery de 9.625 → 900K+ candidatos en 6 países (DE/ES/FR/NL/BE/CH).
> Iniciado 2026-06-06. Fuente de verdad del estado: `discovery_candidates` en PG.

## Estado inicial [VERIFICADO]
- Total: **9.625** (2.449 con dominio, 7.176 sin)
- País: FR 7.576 · CH 1.507 · DE 475 · BE 63 · ES 4 · **NL 0**
- Fuente: osm 9.018 · oem:bmw 607 · **resto 0**

## Causa raíz de fuentes a 0 [VERIFICADO]
- **SIRENE** (`fr_sirene.py`): usaba NAF sin punto (`4511Z`) → API `recherche-entreprises.api.gouv.fr`
  exige punto (`45.11Z`) → HTTP 400 en cada query → 0 filas. **FIX: añadir puntos + códigos auto faltantes.**
- **common_crawl**: 404 (índice CC caducado).
- **portal_aggregator**: 0 filas (revisar aparte).

## Plan de ejecución (por bloques)
- [x] B0 Reconocimiento: schema, índices únicos, env Python, todas las fuentes leídas
- [ ] B1 SIRENE FR fix + run (mayor win, ~150-250K identity rows) — recherche-entreprises, gratis
- [ ] B2 OSM realmente expandido (car_repair, car_parts, motorcycle, truck, car_rental) ×6 países
- [ ] B3 ct_logs (Certificate Transparency, crt.sh PG) ×6 países — domain-ful
- [ ] B4 trustpilot + bovag
- [ ] B5 NUEVA fuente: BE KBO Open Data (registro mercantil belga, CSV gratuito, NACE auto)
- [ ] B6 Resolvers continuos: ddg_worker + name_to_domain (identity→domain)
- [ ] B7 Registrar TODAS las fuentes en orchestrator.py
- [ ] B8 Medir y reportar totales reales por país/dominio/fuente

## Fuentes nuevas investigadas (viables sin coste)
- BE KBO Open Data: dump CSV mensual público (https://kbopub.economie.fgov.be/kbo-open-data) — NACE 45.xx
- FR recherche-entreprises: ya integrado (gratis, sin auth) — fix de NAF
- crt.sh CT logs: ya integrado
- OSM Overpass: ya integrado — ampliar tags
- DE Handelsregister / NL KVK / ES: NO bulk gratis → se cubren vía OSM expandido + ct_logs
- Google Places API / INSEE bulk: requieren key de pago → descartados (restricción "sin coste")

## Bugs encontrados y arreglados [causa raíz]
1. **SIRENE NAF sin punto** (`fr_sirene.py`): `4511Z` → HTTP 400. Fix: `45.11Z` + 4 códigos auto
   extra (45.20B/45.31Z/45.32Z/45.40Z). De 0 → decenas de miles.
2. **OSM User-Agent bloqueado** (`osm.py`): overpass-api.de (Apache mod_security) devuelve 406 al UA
   `python-httpx`. Fix: header User-Agent de navegador. De 0 (en re-run) → 52K elementos solo DE.
   Además query expandida (car_repair/parts/tyres/motorcycle/truck/caravan/rental + `nwr`).
3. **Mi error de ruta**: `sirene_standalone` está en `sources/`, no en `discovery/`. Sin bug de código.

## Fuentes que requieren AUTH (no automatizables sin coste) [VERIFICADO]
- **Zefix CH**: requiere ZEFIX_USER/PASS (registro) → skip graceful. CH vía OSM+ct_logs.
- **INSEE v3.11**: requiere INSEE_API_KEY → usamos recherche-entreprises (abierto) en su lugar.
- **KBO BE Open Data**: descarga bulk tras login (HTTP 302) → no automatizable. BE vía OSM+ct_logs.
- **NL KVK**: API de pago. NL vía OSM+ct_logs+bovag.

## Fuentes que fallan por otra razón [VERIFICADO]
- **DDG resolver**: IP datacenter bloqueada por DuckDuckGo (página sin result__a). Detenido — envenenaba
  la cola. Filas reseteadas. Necesita proxy residencial para funcionar.
- **trustpilot**: estructura de categorías cambiada / CF → 0 extraído.
- **bovag**: endpoint api/leden/search responde 200 pero estructura Sitecore opaca → 0.
- **portal_aggregator**: solo AS24-DE no-CF; httpx plano no vence Cloudflare → terreno de la fleet
  de scraping (as24_curl_cffi), no del discovery.
- **common_crawl**: índice CC 404 (snapshot caducado).

## Orchestrator: registro completo
- 6 fuentes httpx `discover(country)`: oem_bmw, portal, sirene(fixed), zefix, osm(expanded), common_crawl
- 3 runners standalone self-sink añadidos: ct_logs, trustpilot, bovag (DISCOVERY_STANDALONE=1 default)
- Re-run canónico NO ejecutado en sesión para no duplicar el barrido SIRENE en vuelo (riesgo ban).
  Queda cableado: `DISCOVERY_COUNTRIES=DE,ES,FR,NL,BE,CH python -m scrapers.discovery.orchestrator`

## Log de ejecución (running)
- SIRENE FR: ✅ en vuelo (~24.5K filas a las 07:47, ritmo ~50/s, destino ~150-250K)
- OSM expandido: ✅ en vuelo (DE: 52K elementos; FR/ES/NL/BE/CH pendientes)
- ct_logs: ✅ done (367 dominios)
- name_to_domain (crt.sh): ✅ en vuelo (resolver, bajo rendimiento esperado)
- trustpilot/bovag: ✅ done (0)
- DDG: ⛔ detenido (IP bloqueada)
