---
name: GOAL #1 — 100% territorio + 900K+ dealers
description: PRIORIDAD ABSOLUTA. Scrapers para TODOS los portales + Discovery Crawler para TODOS los dealers individuales (~900K+) en 6 países. HANDS OFF. NO PARAR. EJECUTAR.
type: project
originSessionId: f40b2fe4-7b98-4b15-bea1-af705c3e870f
---

# GOAL #1 — COBERTURA 100% DEL TERRITORIO + 900K+ DEALERS

**Qué:** Dos frentes simultáneos hasta cobertura total en DE/FR/ES/NL/BE/CH:
1. **Portales agregadores:** 71 implementados, T0/T1 cerrado. Mantener.
2. **Discovery Crawler: TODOS los dealers individuales (~900K+ estimados).** No 75K, no 140K — TODOS. Buscar bajo cada piedra. Cada concesionario, garaje, taller de VO, importador, broker, con presencia web debe estar indexado.

**SIN TECHO (Salman 2026-06-07):** 900K es un PISO, no un techo. Se indexan TODOS los dealers con web que existan, sea el número que sea — nada de techos mentales. Tres frentes SIMULTÁNEOS, todos máxima prioridad: (A) DESCUBRIR más dealers (OSM-full, geo-sweep H3, todos los OEM, directorios), (B) CONVERTIR (resolución de dominio name→web a escala), (C) SCRAPING A MEDIDA por dealer (config guardada por web + drift + auto-remediación). No basta con uno; corren en paralelo y se TERMINAN.

**MÉTRICA DE ÉXITO (re-clarificado por Salman 2026-06-07, NO confundir):** el goal son **dealers CON WEB resuelta** (de los que se puede scrapear inventario), NO filas brutas en `discovery_candidates`. 3M de dealers sin web no valen nada. Reportar SIEMPRE "dealers con dominio web", no el total bruto. Estado 2026-06-07: 551K filas pero solo ~30.395 con web → la palanca crítica es la **RESOLUCIÓN DE DOMINIO a escala** (name+ciudad → web) sobre los ~520K dealers identificados sin web. Ver [[project_cardex_state]]. RAM del host: procesar por lotes pequeños (nunca evitar trabajo "por RAM"; usarla poco a poco).

**Universo de dealers estimado:**
- DE: ~36K (KBA/ZDK) + independientes
- FR: ~38K (SIRENE NAF 4511Z/4519Z) + independientes
- ES: ~25K (CNAE 4511/4519) + importadores
- NL: ~12K (KVK/RDW) + importadores
- BE: ~8K (BCE) + importadores
- CH: ~5K (ZEFIX) + independientes
- **Long tail no registrado:** brokers online, importadores sin establecimiento, marketplace sellers → potencialmente 2-3x más

**Fuentes de discovery (agotar TODAS):**
- Registros mercantiles: SIRENE, ZEFIX, KVK, BCE, CNAE/DGT, Handelsregister
- OpenStreetMap: car_dealer, car_repair, used_car_dealer
- Certificate Transparency logs
- Common Crawl (keywords automotrices)
- Portal aggregators (dealers listados en AutoScout24, mobile.de, etc.)
- OEM dealer locators (BMW, Mercedes, VW, Renault, PSA, etc.)
- Google Maps Places API (car_dealer category)
- Trustpilot (categoría automotive)
- BOVAG (NL), FEGARBEL (BE), AGVS (CH), VDA (DE)
- Sitemaps de portales grandes (contienen dealer pages)
- DDG/Bing search: "occasion [ciudad]", "gebrauchtwagen [ciudad]", etc.
- Yellow Pages equivalents: PagesJaunes, Gelbe Seiten, Gouden Gids, Paginas Amarillas

**Pipeline:**
1. Census → discovery_candidates (PG)
2. Clasificación automática (CMS, tiene_inventario, tier)
3. Crawl frontier runner (Thompson Sampling, rate limits, robots.txt)
4. Extracción multi-strategy (JSON-LD, microdata, OG, body scrape, Next.js, Nuxt.js, dealerK)
5. Entity resolution (Fellegi-Sunter dedup cross-source)
6. Delta pipeline → vehicle_index (altas/bajas)
7. Cadencia adaptiva (scheduler_pg)

**Reglas operativas (actualización 2026-06-05):**
- HANDS OFF total. NO parar. NO preguntar. Gestionar bloqueos autónomamente.
- Si una petición no se acepta, buscar alternativa y seguir.
- Supervisión activa constante de todas las sesiones.
- Cuando no haya faena técnica → investigar competencia, documentar ventajas competitivas.
- Sesiones paralelas agresivas.
- NUNCA defaultear a "no se puede" — agotar toda vía técnica.
- Presupuesto ~300 CHF/mes, preferir gratis.

**How to apply:** TODA conversación: ¿cuántos dealers faltan? → lanzar trabajo. Trabajo en paralelo siempre. Cero tiempo muerto.
