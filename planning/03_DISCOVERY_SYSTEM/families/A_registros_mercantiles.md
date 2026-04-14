# Familia A — Registros mercantiles federales y regionales

## Identificador
- ID: A
- Nombre: Registros mercantiles federales y regionales
- Categoría: Legal-fiscal
- Fecha: 2026-04-14
- Estado: DOCUMENTADO

## Propósito y rationale
Construir el universo legal completo de empresas registradas con código NACE 45.11 (vehicle sales) y códigos adyacentes en los seis países. Esta familia es el denominador de cobertura — la cardinalidad que arroja al ejecutarse define el techo absoluto del territorio dealer registrado oficialmente. Cualquier otra familia se valida cruzando con esta.

A diferencia de los aggregators que solo ven dealers que se publicitan en su plataforma, esta familia ve el universo administrativo-fiscal completo, incluido el dealer que no se publicita en ningún marketplace.

## Códigos NACE relevantes

| Código | Descripción | Inclusión |
|---|---|---|
| 45.11 | Sale of cars and light motor vehicles | OBLIGATORIO |
| 45.19 | Sale of other motor vehicles (commercial, etc.) | OBLIGATORIO |
| 45.20 | Maintenance and repair of motor vehicles | INCLUIR — algunos talleres venden ocasionalmente |
| 45.31 | Wholesale of motor vehicle parts | EXCLUIR — solo recambios |
| 45.32 | Retail of motor vehicle parts | EXCLUIR — solo recambios |
| 77.11 | Renting and leasing of cars and light motor vehicles | INCLUIR — venta ex-fleet frecuente |
| 64.91 | Financial leasing | INCLUIR — venta ex-leasing al final del contrato |

Lista expandible. Familia debe ejecutar inclusive y filtrar a posteriori con signals de venta efectiva.

## Sub-técnicas y fuentes por país

### Alemania (DE)

#### A.DE.1 — OffeneRegister.de (Sprint 2 — implementado)
- URL base: https://offeneregister.de
- Acceso: dump SQLite gratuito descargable (~2 GB comprimido) [verificado 2026-04-14 vía https://offeneregister.de]
- Datos: razón social, objeto social (`Gegenstand`), dirección, número de registro, tribunal
- **LIMITACIÓN CRÍTICA — códigos WZ/NACE:** OffeneRegister NO expone códigos WZ ni NACE-DE. El Handelsregister federal no incluye clasificación sectorial en los datos publicados [verificado Sprint 2 por implementación real]
- Estrategia implementada: FTS5 keyword search sobre campo `Gegenstand` con términos: "Autohaus", "Fahrzeughandel", "Kfz-Handel", "Pkw-Handel", "Kraftfahrzeughandel", "Gebrauchtwagenhandel"
- Precisión estimada: ~70–80% de verdaderos dealers sobre resultados FTS5. Hipótesis a validar empíricamente con primera ejecución real + R5 cross-validation Familia B/F/G
- Dependencia R5: cross-validation con Familia B y F necesaria para eliminar falsos positivos (ej.: talleres puros que mencionan "Autohaus" en objeto social)
- Rate limit: descarga one-shot, sin API paginada
- Base legal: OffeneRegister.de republica datos del Handelsregister federal bajo licencia CC0 [verificado 2026-04-14 vía https://offeneregister.de/ueber/]
- Módulo Go: `discovery/internal/families/familia_a/de_offeneregister/`

#### A.DE.2 — Handelsregister federal (handelsregister.de) — DEFERRED Sprint 3+
- URL base: https://www.handelsregister.de
- Acceso: HTML, formularios búsqueda, sin API bulk pública
- Datos: razón social, dirección, objeto social, capital, administradores, fecha constitución
- Limitación: rate limit estricto (anti-bulk download), sin SBI/WZ filter
- Estado: DEFERRED — cubierto por A.DE.1 OffeneRegister que republica los mismos datos en formato bulk

#### A.DE.3 — Bundesanzeiger — DEFERRED Sprint 3+
- URL base: https://www.bundesanzeiger.de
- Acceso: HTML público + dataset JSON parcial
- Datos: Jahresabschlüsse de empresas, incluidas pequeñas
- Estado: DEFERRED — complementa A.DE.1 para dealers con Jahresabschluss publicado, baja prioridad Sprint 2

#### A.DE.4 — 16 Gewerbeämter regionales (Bundesländer) — DEFERRED Sprint 4+
Listado por Bundesland: Baden-Württemberg, Bayern, Berlin, Brandenburg, Bremen, Hamburg, Hessen, Mecklenburg-Vorpommern, Niedersachsen, Nordrhein-Westfalen, Rheinland-Pfalz, Saarland, Sachsen, Sachsen-Anhalt, Schleswig-Holstein, Thüringen.
- Cada uno con portal Gewerbeamt independiente
- Acceso: variado por land — algunos open data, otros requieren consulta individual
- Datos: Gewerbeanmeldungen (alta de actividad económica)
- Cobertura: capta dealers que no aparecen en Handelsregister (autónomos, pequeñas estructuras)
- Estado: DEFERRED — heterogeneidad por land hace la implementación costosa, valor incremental bajo dado A.DE.1

### Francia (FR)

#### A.FR.1 — INSEE Sirene API
- URL base: https://api.insee.fr/entreprises/sirene/V3
- Acceso: API REST gratuita con auth (token gratuito tras registro)
- Datos: SIRET, SIREN, razón social, APE 4511Z, dirección, fecha creación, estado
- Cobertura: universo completo de empresas francesas registradas
- Rate limit: 30 req/min en plan gratis
- Base legal: open data oficial (loi République numérique)

#### A.FR.2 — Pappers
- URL base: https://www.pappers.fr
- Acceso: API + interfaz web
- Free tier: limitado, paid tier por encima
- Estrategia: usar como espejo de Sirene si Sirene tiene gaps; preferir Sirene por gratuidad

#### A.FR.3 — BODACC
- URL base: https://www.bodacc.fr
- Acceso: HTML público + descarga PDF/XML diario gratis
- Datos: anuncios legales (creaciones, modificaciones, ceses)
- Cobertura: fuente complementaria para detectar nuevos dealers en tiempo real

#### A.FR.4 — Greffes des tribunaux de commerce (96 départements)
- Cada departamento con greffe propio
- Acceso: Infogreffe agregador (paid) o gratuito por documento individual
- Estrategia: usar solo como fallback cuando Sirene falte campo crítico

#### A.FR.5 — CCI (Chambres de Commerce et d'Industrie) regionales
- 13 régions con CCI
- Directorios sectoriales públicos por región
- Estrategia: cross-validation regional

### España (ES)

#### A.ES.1 — BORME datosabiertos API (Sprint 2 — implementado)
- URL base API: `https://www.boe.es/datosabiertos/api/borme/sumario/YYYYMMDD` [verificado 2026-04-14 vía https://www.boe.es/datosabiertos/api/borme/]
- Acceso: API REST pública, sin autenticación, Accept: application/xml [verificado 2026-04-14]
- Datos disponibles en sumario: ID acto, nombre empresa, tipo acto, provincia, registro, URL PDF/XML del acto individual
- **LIMITACIÓN CRÍTICA — códigos CNAE:** El sumario BORME Sección A NO incluye códigos CNAE ni clasificación sectorial [verificado Sprint 2 por implementación real]. Los códigos CNAE aparecerían en el acto individual (PDF/XML separado), lo que requeriría N+1 requests — DEFERRED Sprint 3
- Estrategia implementada Sprint 2: ingestión completa de Sección A (Inscripciones del Registro Mercantil) sin filtro CNAE. Cross-filtrado posterior con Familia B/F/G para identificar dealers reales
- Backfill: 7 días hábiles hacia atrás en cada ejecución (maneja fines de semana y festivos con 404 → skip)
- Rate: 1 req / 2s (conservador para API pública) [verificado 2026-04-14 — no hay rate limit documentado, se aplica conservadoramente]
- Base legal: BOE datos abiertos — acceso público gratuito, reutilización libre [verificado 2026-04-14 vía https://www.boe.es/datosabiertos/]
- Módulo Go: `discovery/internal/families/familia_a/es_borme/`

#### A.ES.1b — BORME actos individuales (parsing CNAE) — DEFERRED Sprint 3
- Requiere GET por cada acto individual para extraer CNAE del XML/PDF
- Volumen estimado: 50–200 actos/día en Sección A → N+1 requests sobre rate 1 req/2s → 100–400s/día adicionales
- Hipótesis: cross-validation con Familia B tendrá mayor ROI que parsing por acto antes de validar cobertura Sprint 2

#### A.ES.2 — Registro Mercantil Central
- URL base: https://www.rmc.es
- Acceso: índice gratis, documento individual paid
- Estrategia: índice para validación + identificación, no descarga masiva

#### A.ES.3 — AEAT IAE 615.x (Impuesto sobre Actividades Económicas)
- IAE 615.1 — Comercio al por mayor de vehículos
- IAE 615.4 — Comercio al por mayor de motocicletas
- IAE 654.1 — Comercio al por menor de vehículos
- Acceso: censo público vía AEAT (limitado, requiere gestión)
- Estrategia: cross-validation cuantitativa, no listado individual

#### A.ES.4 — 17 Comunidades Autónomas — cámaras de comercio
- Madrid (Cámara Madrid), Cataluña (Cambres Catalanes), Andalucía (Cámara Andalucía), Valencia, País Vasco, Galicia, Castilla y León, Castilla-La Mancha, Aragón, Asturias, Murcia, Canarias, Baleares, Extremadura, Navarra, La Rioja, Cantabria
- Cada una con directorio sectorial propio
- Estrategia: agregación país-completo

### Países Bajos (NL)

#### A.NL.1 — KvK Handelsregister (dual-path) (Sprint 2 — implementado)

**Path 1 — Bulk anoniem dataset (densidad geográfica)**
- URL producto: https://www.kvk.nl/producten-en-diensten/kvk-data/bulk-anoniem/ [verificado 2026-04-14]
- Acceso: descarga gratuita, sin registro. CSV comprimido con empresas registradas
- Datos disponibles: gemeente (municipio), totals by activiteit — permite mapa de densidad
- Uso en Sprint 2: calcular densidad de empresas por municipio para priorizar zonas de discovery
- **LIMITACIÓN:** dataset anonimizado — no contiene KvK-nummer, naam ni adres individuales

**Path 2 — KvK Zoeken API v2 (keyword search)**
- URL base: https://api.kvk.nl/api/v2/zoeken [verificado 2026-04-14 vía documentación KvK developer portal]
- Acceso: API key gratuita tras registro en developer.kvk.nl
- **LIMITACIÓN CRÍTICA — filtro SBI:** El free tier Zoeken API v2 **NO soporta parámetro de filtro SBI** [verificado Sprint 2 por implementación real]. No existe `?sbiCode=4511` o equivalente en el free tier
- Estrategia implementada: keyword search por términos "autohandel", "autodealer", "autoverkoop", "occasion", "voertuighandel" → paginar resultados → cruzar con Familia B
- Rate limit: ~100 req/dag en free tier [verificado Sprint 2 — tabla `rate_limit_state` SQLite, api_name='kvk', window_start diario]
- Rate limit state: persistido en SQLite (`rate_limit_state` table) — survives restarts, reset al inicio de cada día
- Base legal: Handelsregisterwet 2007 [verificado 2026-04-14 vía https://wetten.overheid.nl/BWBR0021777/]
- Módulo Go: `discovery/internal/families/familia_a/nl_kvk/`
- Dependencia cross-resolve: resultados de Path 1 + Path 2 necesitan cross-validation con Familia B para obtener KvK-nummer + adres completo

#### A.NL.2 — KvK bulk dataset identificado (paid) — DEFERRED Sprint 3
- KvK ofrece descarga del registro con KvK-nummers identificados
- Acceso: pricing no confirmado públicamente — Hipótesis: ~€50 single-shot (no verificado)
- Estado: DEFERRED — Path 2 gratuito suficiente para Sprint 2; bulk identificado aumentaría cobertura Sprint 3

#### A.NL.3 — 12 provincies — registros locales — DEFERRED Sprint 4+
- Noord-Holland, Zuid-Holland, Utrecht, Flevoland, Gelderland, Overijssel, Drenthe, Groningen, Friesland, Noord-Brabant, Limburg, Zeeland
- Algunas con datos abiertos sectoriales
- Estado: DEFERRED — valor incremental bajo dado A.NL.1 dual-path

### Bélgica (BE)

#### A.BE.1 — BCE/KBO Open Data (Sprint 2 — implementado)
- URL portal: https://kbopub.economie.fgov.be/kbo-open-data [verificado 2026-04-14]
- URL descarga: https://economie.fgov.be/fr/themes/entreprises/banque-carrefour-des/services-pour-tous/donnees-publiques-en-libre [verificado 2026-04-14]
- **AUTENTICACIÓN REQUERIDA:** El portal KBO Open Data exige registro y credenciales para la descarga del dataset completo [verificado Sprint 2 por implementación real]
  - Env vars: `KBO_USER` (login portal), `KBO_PASS` (contraseña)
  - Flow: POST login form → cookie-jar → GET ZIP download endpoint
- Datos: número empresa, denominaciones (ES/FR/NL), códigos NACE-BE, dirección, status, administradores
- NACE-BE filtrado: 45110, 45190, 45200 [verificado 2026-04-14 — NACE 2008 revision, equivalentes a 45.11/45.19/45.20]
- Formato: ZIP ~3 GB → 4 ficheros CSV principales (enterprise.csv, activity.csv, denomination.csv, address.csv)
- Estrategia implementada: descarga a fichero temporal → `archive/zip.OpenReader` → parse CSV multi-pass con filtro NACE en activity.csv
- Base legal: acceso público Open Data garantizado por Loi du 4 mai 2016 [verificado 2026-04-14 vía https://economie.fgov.be]
- Módulo Go: `discovery/internal/families/familia_a/be_kbo/`

#### A.BE.2 — 3 regiones (Vlaanderen, Wallonie, Brussels)
- Cada región con base de datos regional complementaria
- Vlaanderen: VLAIO, Statistik Vlaanderen
- Wallonie: AWEX, IWEPS
- Brussels: hub.brussels

### Suiza (CH)

#### A.CH.1 — opendata.swiss CKAN + Zefix HTML fallback (Sprint 2 — implementado, dual-path)

**Path 1 — opendata.swiss CKAN (primary)**
- URL API: https://opendata.swiss/api/3/action/package_search [verificado 2026-04-14 vía https://opendata.swiss/api/3/action/]
- Acceso: API REST pública CKAN, sin autenticación
- Datos: datasets con clasificación NOGA (equivalente NACE en Suiza), incluyendo firmas por actividad
- Filtro NOGA: 4511 — búsqueda en recursos del dataset por código NOGA en metadatos o contenido CSV
- Estrategia: GET package_search → extraer URLs de recursos descargables → filter NOGA 4511 → parse CSV → upsert

**Path 2 — Zefix HTML fallback (si CKAN falla)**
- URL HTML: https://www.zefix.ch/ZefixPublic/company/search.xhtml [verificado 2026-04-14]
- Acceso HTML: público, sin autenticación
- **LIMITACIÓN CRÍTICA — API REST:** La API REST de Zefix (`https://www.zefix.admin.ch/ZefixPublicREST/`) devuelve **HTTP 401 sin credenciales registradas** [verificado Sprint 2 por implementación real]. No hay NOGA codes disponibles sin auth
- **LIMITACIÓN CRÍTICA — NOGA en HTML:** La interfaz HTML tampoco expone NOGA codes directamente — búsqueda por cantón + keyword, parse con goquery
- Estrategia fallback: keyword search por cantón ("autohandel", "fahrzeughandel", "autoverkauf") → parse resultados con `github.com/PuerkitoBio/goquery`
- 26 cantones cubiertos en fallback: Zürich, Bern, Luzern, Uri, Schwyz, Obwalden, Nidwalden, Glarus, Zug, Fribourg, Solothurn, Basel-Stadt, Basel-Landschaft, Schaffhausen, Appenzell Ausserrhoden, Appenzell Innerrhoden, St. Gallen, Graubünden, Aargau, Thurgau, Ticino, Vaud, Valais, Neuchâtel, Genève, Jura

- Base legal: Zefix — registro público federal suizo [verificado 2026-04-14 vía https://www.zefix.ch]; opendata.swiss — plataforma datos abiertos Confederación [verificado 2026-04-14 vía https://opendata.swiss/about]
- Módulo Go: `discovery/internal/families/familia_a/ch_zefix/`

#### A.CH.2 — 26 cantones — Handelsregister cantonales
- Zürich, Bern, Luzern, Uri, Schwyz, Obwalden, Nidwalden, Glarus, Zug, Fribourg, Solothurn, Basel-Stadt, Basel-Landschaft, Schaffhausen, Appenzell Ausserrhoden, Appenzell Innerrhoden, St. Gallen, Graubünden, Aargau, Thurgau, Ticino, Vaud, Valais, Neuchâtel, Genève, Jura
- Cada cantón con su Handelsregister independiente
- Acceso: HTML por cantón, formato no homogéneo
- Estrategia: parser específico por cantón, datos deduplicados con A.CH.1 vía VAT number (CHE-XXX.XXX.XXX)

## Base legal (todas las sub-técnicas)
- Acceso a registro público mercantil legal en todos los países
- Reutilización de datos abiertos cubierta por:
  - EU: Directiva (UE) 2019/1024 sobre datos abiertos y reutilización
  - DE: Open Data Gesetz
  - FR: Loi République numérique
  - ES: Ley 19/2013 de transparencia
  - NL: Wet open overheid
  - BE: Open data policy federal
  - CH: Bundesgesetz über das Öffentlichkeitsprinzip

Acceso transparente, identificable como CardexBot, respeto a rate limits.

## Métricas de la familia A

- `unique_entities_discovered(país)` — entidades únicas encontradas por país
- `nace_distribution(país)` — distribución por código NACE
- `freshness_lag(país)` — antigüedad media del último update por entidad
- `domain_resolution_rate(país)` — % entidades para las que se pudo resolver dominio web (input para Familia C)
- `cross_validation_rate_with_B(país)` — % entidades también encontradas en Familia B (geo)

## Implementación esperada

- Módulo Go: `discovery/family_a/`
- Sub-módulos: `de/`, `fr/`, `es/`, `nl/`, `be/`, `ch/` con parsers específicos
- Persistencia: SQLite con schema `entities_legal`
- Cron: full-sync mensual + delta diario donde la API lo soporte
- Coste cómputo: medio (procesamiento bulk inicial intensivo, delta liviano)
- Dependencias: `colly` para HTML, `encoding/csv` y `encoding/xml` para datasets

## Cross-validation con otras familias

Hipótesis a validar empíricamente tras primera ejecución de discovery completo. Los porcentajes de overlap son estimaciones de diseño basadas en razonamiento sobre fuentes; no hay datos empíricos pre-launch.

| Otra familia | Overlap hipotético | Discovery único de A |
|---|---|---|
| B (geo) | ~60% (hipótesis) | A captura empresas registradas sin POI físico aparente |
| C (web) | ~50% (hipótesis) | A captura empresas sin presencia web identificada |
| F (aggregators) | ~30% (hipótesis) | A captura long-tail invisible en marketplaces |
| G (asociaciones) | ~80% para miembros (hipótesis) | A captura no-miembros (mayoría del long-tail) |
| H (OEM) | ~25% (hipótesis) | A captura independientes y multi-marca |

## Riesgos y mitigaciones

- **R-A1:** API rate limits restrictivos (NL KvK free tier ~100 req/dag, FR Sirene 30 req/min). Mitigación: `rate_limit_state` SQLite persistido, sync incremental, retry con backoff exponencial.
- **R-A2:** Cambios de estructura en formatos XML (ES BORME sumario). Mitigación: tests de regresión sobre fixtures archivados en `testdata/`.
- **R-A3:** Datos parciales en algunos cantones suizos (CH Zefix HTML estructura variable por cantón). Mitigación: marcar entidad con flag `coverage:partial` y compensar con Familia B/C.
- **R-A4:** Alta tasa de falsos positivos en DE (FTS5 keyword search sin NACE). Mitigación: cross-validation R5 con Familia B/F obligatoria antes de cualquier uso en producción. Hipótesis: ~20-30% falsos positivos — a medir en primera ejecución.
- **R-A5:** Credenciales KBO (BE) caducan o el portal cambia su formulario de login. Mitigación: tests de integración con servidor mock; alertas si cookie-jar flow falla.
- **R-A6:** opendata.swiss CKAN no tiene dataset con NOGA 4511 en el momento de ejecución (CH). Mitigación: fallback automático a Zefix HTML implementado en `ch_zefix.go`.
- **R-A7:** BORME sumario tiene 0 actos Sección A algún día hábil (festivos nacionales no marcados como fin de semana). Mitigación: 404 → skip implementado; no cuenta como error.

## Iteración futura

Tras saturación inicial, la familia A se expande con:
- Históricos pre-2010 cuando estén disponibles digitalmente
- Sub-registros municipales adicionales (en DE: Gewerbeämter por ciudad mayor, no solo Bundesland)
- Datasets de quiebras/liquidaciones para mantener estado actualizado (familia A debe distinguir activo vs cesado)
