# Familia K — Buscadores alternativos open-source

## Identificador
- ID: K, Nombre: Buscadores alternativos open-source, Categoría: Search-alt
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Google y Bing tienen el índice más completo de la web, pero su API es de pago o está limitada. Para €0 OPEX, se aprovechan buscadores alternativos open-source, federados o indie con políticas de acceso programático abierto. Permite ejecutar queries sistemáticos geo-filtrados (`"vehículos ocasión" site:.es`, `"Gebrauchtwagen Händler" site:.de`) para descubrir dominios dealer no capturados por familias previas.

## Fuentes

### K.1 — SearXNG self-hosted
- Meta-buscador open-source federando 70+ engines (Google, Bing, DuckDuckGo, Yandex, Brave, Mojeek, Startpage, Qwant, etc.)
- Self-hosted en el mismo VPS (~200 MB RAM, Docker)
- Permite queries programáticos sin rate limit propio (los rate limits son por engine upstream)
- URL: https://github.com/searxng/searxng
- Respuesta JSON vía `?format=json`

### K.2 — YaCy distributed P2P search
- Buscador federado peer-to-peer
- Índice distribuido entre nodos
- Self-hosted, acceso gratuito
- URL: https://yacy.net
- Útil para búsquedas con soberanía total sin dependencia de upstream

### K.3 — Brave Search API
- Free tier: 2.000 queries/mes (suficiente para discovery targeted, no masivo)
- URL: https://brave.com/search/api
- Índice propio de Brave (no dependiente de Google/Bing)
- Datos estructurados, alta calidad

### K.4 — Marginalia Search
- Buscador indie enfocado en web "artesanal" y small sites
- **Ideal para long-tail**: prioriza sites pequeños que Google desprioriza
- URL: https://search.marginalia.nu
- API limitada pero gratuita

### K.5 — Mojeek
- Free tier limitado, paid tier barato
- Crawler propio no dependiente de Google/Bing
- URL: https://www.mojeek.com/services/search

### K.6 — DuckDuckGo HTML scraping
- ToS permite renderizar resultados programáticamente
- URL base: https://html.duckduckgo.com/html/
- Parser HTML → extracción de resultados
- No oficial pero práctica establecida

### K.7 — Wikidata SPARQL (cross-Familia B.2 pero con otro ángulo)
- Queries SPARQL para entidades con propiedad dealer + geo
- Cobertura limitada pero alta calidad

### K.8 — Internet Archive search API
- Búsqueda sobre el índice de Wayback Machine
- Útil para dealers históricos o sites actualmente caídos

## Sub-técnicas

### K.M1 — Queries sistemáticos por país
Templates por país e idioma, ejecutados combinatoriamente:

```
DE: "Gebrauchtwagen Händler" site:.de
    "Kfz-Händler" site:.de
    "Autohaus" + [ciudad mayor] site:.de
FR: "voiture occasion professionnel" site:.fr
    "concessionnaire automobile" site:.fr
    "garage automobile" + [ville] site:.fr
ES: "vehículos ocasión" site:.es
    "concesionario" + [provincia] site:.es
    "compra-venta coches" site:.es
NL: "tweedehands auto dealer" site:.nl
    "autohandel" site:.nl
BE: "autohandelaar" site:.be
    "garage automobile Belgique" site:.be
CH: "Gebrauchtwagen Garage" site:.ch
    "voiture d'occasion Suisse" site:.ch
```

Total estimado: ~200 query templates × 6 países × N ciudades = ~10.000 queries únicos (ejecutables en ventana semanal sin saturar ningún engine).

### K.M2 — Long-tail term mining
Análisis de queries que retornan resultados NO encontrados por familias previas → identificación de nuevos terms efectivos (ej. "ocasion pro BtoB", "handelaar bedrijfsauto", "garage exposition voiture"). Ciclo iterativo.

### K.M3 — SERP structure parsing
Extracción no solo de URLs sino también de:
- Title del resultado
- Snippet (~10 palabras — bajo excepción Infopaq)
- Presencia de rich results (Schema.org en SERP)

### K.M4 — Competitor SERP intelligence
Queries de productos/modelos específicos → identificación de qué dealers aparecen en top para qué segmento → input para priorización.

## Base legal
- SearXNG/YaCy: self-hosted, legal
- Brave/Marginalia/Mojeek: free tiers dentro de ToS
- DuckDuckGo HTML: prácticamente permitido
- Wikidata: CC0
- Respeto a todos los ToS upstream

## Métricas
- `unique_dealers_discovered_via_K(país)` — dealers solo esta familia captura
- `query_yield_rate(query_template)` — % queries que retornan dealer relevante
- `geo_coverage_balance` — distribución de discoveries por región

## Implementación
- Módulo Go: `discovery/family_k/`
- SearXNG como backend en Docker compose
- Cron: queries batch semanal
- Coste: bajo (SearXNG local + rate limits respetados de upstream)
- Persistencia: resultados en SQLite + índice de queries ejecutados para evitar duplicación

## Cross-validation

| Familia | Overlap | Único de K |
|---|---|---|
| C (web cartography) | ~60% | K captura sites no crawleados por Common Crawl (emergentes o small) |
| F (aggregators) | ~30% | K captura independientes fuera de marketplaces |
| J (sub-jurisdicciones) | ~20% | K aporta dimension "lo que Google indexa", ortogonal a registros |

## Riesgos y mitigaciones
- R-K1: rate limits upstream en SearXNG. Mitigación: distribución temporal + query batching + multi-engine rotation.
- R-K2: SERPs con resultados SEO manipulados. Mitigación: cross-validation con familias A/B; descartar dominios sin correlación con dealer registrado.
- R-K3: Marginalia cobertura limitada. Mitigación: complementar con otros engines.

## Iteración futura
- Entrenamiento de clasificador dealer/no-dealer sobre snippets SERP para mejorar filtrado
- Uso de Common Crawl's CC-News para discovery via menciones de prensa (cross-Familia O)
- Integración de LLM local para reformulación automática de queries que expanden cobertura
