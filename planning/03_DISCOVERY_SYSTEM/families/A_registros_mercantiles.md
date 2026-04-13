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

#### A.DE.1 — Bundesanzeiger
- URL base: https://www.bundesanzeiger.de
- Acceso: HTML público + dataset JSON parcial
- Datos: Jahresabschlüsse de empresas, incluidas pequeñas
- Volumen estimado: cientos de miles de entidades, filtro NACE necesario
- Rate limit: no documentado, conservador (1 req/s)
- Base legal: registro público obligatorio

#### A.DE.2 — Handelsregister B (GmbH/AG/UG)
- URL base: https://www.handelsregister.de
- Acceso: HTML, formularios búsqueda
- Datos: razón social, dirección, objeto social, capital, administradores, fecha constitución
- Rate limit: estricto (anti-bulk download)
- Base legal: registro público

#### A.DE.3 — 16 Gewerbeämter regionales (Bundesländer)
Listado por Bundesland:
- Baden-Württemberg, Bayern, Berlin, Brandenburg, Bremen, Hamburg, Hessen, Mecklenburg-Vorpommern, Niedersachsen, Nordrhein-Westfalen, Rheinland-Pfalz, Saarland, Sachsen, Sachsen-Anhalt, Schleswig-Holstein, Thüringen.
- Cada uno con portal Gewerbeamt independiente
- Acceso: variado por land — algunos open data, otros requieren consulta individual
- Datos: Gewerbeanmeldungen (alta de actividad económica)
- Cobertura: capta dealers que no aparecen en Handelsregister (autónomos, pequeñas estructuras)

#### A.DE.4 — Wirtschaftszweig 45.11 dataset
- Fuente: Statistisches Bundesamt (Destatis) — datasets agregados
- Uso: validación cruzada del orden de magnitud

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

#### A.ES.1 — BORME (Boletín Oficial del Registro Mercantil)
- URL base: https://www.boe.es/diario_borme
- Acceso: PDF/XML diario gratis
- Datos: actos de inscripción registral mercantil
- Estrategia: parser PDF acumulativo histórico + XML diario forward

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

#### A.NL.1 — KvK (Kamer van Koophandel) Open API
- URL base: https://api.kvk.nl
- Acceso: API REST con auth (free tier)
- Datos: KvK number, statutaire naam, SBI codes, adres, status
- SBI 4511 — Handel in en reparatie van personenauto's en lichte bedrijfsauto's
- Rate limit: free tier limitado (~100 req/dag)
- Base legal: Handelsregisterwet 2007

#### A.NL.2 — Handelsregister bulk export
- KvK ofrece descarga periódica del registro completo
- Acceso: paid pero no oneroso (~€50 single-shot)
- Estrategia: bootstrap inicial con bulk + sync diario vía API

#### A.NL.3 — 12 provincies — registros locales
- Noord-Holland, Zuid-Holland, Utrecht, Flevoland, Gelderland, Overijssel, Drenthe, Groningen, Friesland, Noord-Brabant, Limburg, Zeeland
- Algunas con datos abiertos sectoriales

### Bélgica (BE)

#### A.BE.1 — BCE/KBO (Banque-Carrefour des Entreprises / Crossroads Bank)
- URL base: https://kbopub.economie.fgov.be + https://economie.fgov.be/fr/themes/entreprises/banque-carrefour-des/services-pour-tous/donnees-publiques-en-libre
- Acceso: descarga completa gratuita en CSV/XML — 3 GB total
- Datos: número empresa, denominaciones, NACE codes, dirección, status, administradores
- NACE BE: 45110, 45190, 45200
- Base legal: acceso público garantizado por ley

#### A.BE.2 — 3 regiones (Vlaanderen, Wallonie, Brussels)
- Cada región con base de datos regional complementaria
- Vlaanderen: VLAIO, Statistik Vlaanderen
- Wallonie: AWEX, IWEPS
- Brussels: hub.brussels

### Suiza (CH)

#### A.CH.1 — Zefix (Zentraler Firmenindex)
- URL base: https://www.zefix.ch
- Acceso: HTML público + API REST limitada
- Datos: razón social, sede, NOGA codes (equivalente NACE suizo), administradores
- NOGA 4511, 4519, 4520
- Base legal: registro público

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

| Otra familia | Overlap esperado | Discovery único de A |
|---|---|---|
| B (geo) | ~60% | A captura empresas registradas sin POI físico aparente |
| C (web) | ~50% | A captura empresas sin presencia web identificada |
| F (aggregators) | ~30% | A captura long-tail invisible en marketplaces |
| G (asociaciones) | ~80% para miembros | A captura no-miembros (mayoría del long-tail) |
| H (OEM) | ~25% | A captura independientes y multi-marca |

## Riesgos y mitigaciones

- **R-A1:** API rate limits restrictivos (NL KvK, FR Sirene). Mitigación: cache permanente, sync incremental, retry con backoff.
- **R-A2:** Cambios de estructura en formatos PDF/XML (ES BORME, BE BCE). Mitigación: tests de regresión sobre samples archivados.
- **R-A3:** Datos parciales en algunos cantones suizos. Mitigación: marcar entidad con flag `coverage:partial` y compensar con familia B/C.
- **R-A4:** Empresas con NACE asignado erróneamente que no son dealers reales. Mitigación: validación cruzada con familia M (signals operativos VAT activo).

## Iteración futura

Tras saturación inicial, la familia A se expande con:
- Históricos pre-2010 cuando estén disponibles digitalmente
- Sub-registros municipales adicionales (en DE: Gewerbeämter por ciudad mayor, no solo Bundesland)
- Datasets de quiebras/liquidaciones para mantener estado actualizado (familia A debe distinguir activo vs cesado)
