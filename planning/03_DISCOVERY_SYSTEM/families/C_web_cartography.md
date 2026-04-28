# Familia C — Cartografía web profunda (Common Crawl + alternativos)

## Identificador
- ID: C
- Nombre: Cartografía web profunda
- Categoría: Web-cartography
- Fecha: 2026-04-14
- Estado: DOCUMENTADO

## Propósito y rationale
Construir el mapa exhaustivo de la presencia web del ecosistema dealer europeo aprovechando datasets web públicos (Common Crawl, Internet Archive, Certificate Transparency, passive DNS). Esta familia es la palanca que permite descubrimiento masivo legal sin necesidad de crawlear sites individualmente — lee de datasets que terceros públicos ya han crawleado.

Es el corazón del approach lean €0: en lugar de tener nuestra propia infraestructura de crawl masivo (cara, técnicamente compleja, legalmente ambigua a escala), aprovechamos crawls públicos existentes y nos enfocamos en consumo selectivo + extracción dirigida.

## Sub-técnicas y fuentes

### C.1 — Common Crawl

#### C.1.1 — CC-Index Parquet local
- URL base: https://commoncrawl.org/the-data/get-started/
- Datos: índice columnar mensual de TODAS las URLs crawleadas (~150 GB/mes)
- Acceso: descarga de chunks parquet selectivos (free, requesterpays opcional)
- Procesamiento: DuckDB sobre disco local
- Latencia query: segundos sobre TLD-filtered chunks

#### C.1.2 — Estrategia de filtrado
- Descarga selectiva de cdx-NN.parquet por mes
- Filtro inicial por TLD: `.de`, `.fr`, `.es`, `.be`, `.nl`, `.ch`
- Filtro secundario por path patterns: `/used-cars/`, `/voiture-occasion/`, `/coches-segunda-mano/`, `/inventory/`, `/auto/`, `/vehicule/`, `/wagen/`, `/voertuig/`, `/fahrzeug/`
- Volumen post-filtro estimado: chunks de 100-500 MB por mes por país

#### C.1.3 — WARC harvesting selectivo
- Identificadas URLs candidatas, descarga del WARC fragment correspondiente
- Procesamiento streaming con `warcio`
- Footprint memoria <500 MB

#### C.1.4 — Schema.org / JSON-LD extraction
Filtro por presencia de tipos:
- `@type:Vehicle`
- `@type:Car`
- `@type:MotorVehicle`
- `@type:Motorcycle`
- `@type:AutoDealer`
- `@type:AutoRepair`
- `@type:Offer` con `itemOffered` de tipo Vehicle

Extracción del grafo estructurado completo. Esto entrega catálogos enteros sin visitar la página individualmente.

#### C.1.5 — Microdata (HTML5) y RDFa fallback
Sites pre-Schema.org pero con datos estructurados en formato anterior.

#### C.1.6 — OpenGraph product:vehicle tags
Facebook OG tags con propiedades vehículo. Aunque diseñados para sharing social, sirven como structured data.

#### C.1.7 — Sitemap.xml content-type discovery
Common Crawl también indexa sitemaps. Filtro por sitemaps que listen URLs con patrones vehicle. Discovery de catálogos completos.

### C.2 — Internet Archive Wayback Machine

#### C.2.1 — Acceso
- URL: https://archive.org/wayback/available
- API: gratuita, libre
- Datos: snapshots históricos de webs

#### C.2.2 — Casos de uso
- Detectar dealers cerrados (snapshot reciente, sin DNS actual)
- Detectar dominios reciclados (cambio brusco de contenido)
- Recuperar catálogos pre-cambio para análisis temporal
- Validar inicio operación de dealer (primer snapshot)

### C.3 — Certificate Transparency logs (crt.sh)

#### C.3.1 — Acceso
- URL: https://crt.sh
- API: HTTP libre + dataset descargable
- Base legal: CT logs son públicos por diseño

#### C.3.2 — Estrategia
Reverse search por palabras clave en SAN entries:
- `auto`, `kfz`, `voiture`, `coche`, `wagen`, `dealer`, `garage`, `motors`, `automobile`
Por TLD: `.de`, `.fr`, `.es`, `.be`, `.nl`, `.ch`

Discovery de subdominios dealer no encontrados por otra vía.

### C.4 — Passive DNS

#### C.4.1 — Servicios free tier
- SecurityTrails: 50 queries/día gratis
- VirusTotal passive DNS: free con cuenta
- Hackertarget: 50 queries/día gratis
- DNSDumpster: HTML público

#### C.4.2 — Casos de uso
- Discovery de subdominios de un dominio dealer raíz
- Mapeo de IPs hosting → reverse para descubrir dealers compartiendo proveedor (ver Familia E)

### C.5 — Open data web indices

- Hispar Top 100M (alternativa a Alexa, gratis)
- Cisco Umbrella Top 1M
- Estrategia: filtrado por dominio europeo + categoría auto

## Base legal
- Common Crawl: explícitamente para data mining, indexación y research (Crawl is permission-free per CCBot user-agent reputation, datasets bajo CC BY 4.0)
- Internet Archive: política de archivado permitido, contenido bajo restricciones del original
- CT logs: público por diseño (RFC 6962)
- Passive DNS free tiers: dentro de los límites del free tier
- Web indices: CC BY o equivalente

Cero crawling propio masivo. Consumo de crawls ajenos.

## Métricas

- `unique_dealer_domains_discovered(país)` — dominios únicos identificados
- `schema_org_coverage_rate(país)` — % dominios con structured data extraíble
- `subdomain_enumeration_depth(dominio)` — subdominios encontrados por dominio raíz
- `cross_validation_rate_with_A_B(país)` — % dominios cuyo dealer está en A o B
- `historical_evolution_score(dominio)` — % dominios con histórico Wayback mappable

## Implementación

- Módulo Go: `discovery/family_c/`
- Sub-módulos: `commoncrawl/`, `wayback/`, `crtsh/`, `passive_dns/`, `web_indices/`
- Procesamiento: pipeline batch nocturno (Common Crawl mensual)
- Persistencia: DuckDB para CC-Index queries + SQLite para resultados consolidados
- Coste cómputo: alto en CC processing (CPU + I/O), bajo en queries derivadas
- Dependencias: `duckdb` Go bindings, `warcio` (Python subprocess), DNS resolver propio

## Cross-validation con otras familias

> Hipótesis de diseño — porcentajes de overlap a validar empíricamente en primera ejecución de discovery completo.

| Otra familia | Overlap hipotético | Discovery único de C |
|---|---|---|
| A | ~50% | C captura empresas con presencia web sin equivalente fácil en registro mercantil |
| B | ~70% | C captura dominios sin POI físico (pure online) |
| D | ~80% | C es el seed que alimenta D (CMS fingerprinting requiere URL primero) |
| E | ~60% | C aporta dominios; E identifica los hosted en infra DMS |

## Riesgos y mitigaciones

- **R-C1:** Common Crawl tiene gaps temporales en sites pequeños. Mitigación: agregación multi-mes + complementar con C.3 (CT logs) que captura DNS no necesariamente crawleado.
- **R-C2:** Schema.org markup ausente en sites lamentables (los target del long-tail). Mitigación: combinar con D (CMS fingerprinting que extrae sin Schema).
- **R-C3:** Falsos positivos: dominios que mencionan "auto" sin ser dealers (auto-escuelas, autoescuelas, car-sharing, etc.). Mitigación: clasificador dealer/no-dealer con regex + ML.
- **R-C4:** Passive DNS limits estrictos. Mitigación: priorizar dominios alta-confianza desde A+B y usar PDNS solo como enriquecimiento.

## Iteración futura

- Integración de WebRTC leak detection logs (avanzado, especulativo)
- Cosechas de nuevos crawlers públicos emergentes (CC alternatives)
- Análisis de cambios estructurales en sitios via Wayback delta para detectar pivots de negocio
