# Familia J — Capas regionales/cantonales/municipales sub-jurisdiccionales

## Identificador
- ID: J, Nombre: Sub-jurisdicciones, Categoría: Sub-jurisdictional
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Los registros nacionales (Familia A) no siempre desagregan al máximo nivel administrativo. Sub-jurisdicciones (Bundesländer, départements, Comunidades Autónomas, provincies, régions, cantones) frecuentemente exponen datos locales adicionales, registros municipales, licencias comerciales específicas que capturan dealers no presentes en el registro federal o con datos más completos.

170 sub-jurisdicciones totales en los 6 países. Cada una es potencialmente una fuente adicional. Esta familia es la palanca de exhaustividad territorial.

## Inventario de sub-jurisdicciones

### J.DE — 16 Bundesländer + ~400 Kreise (distritos)
Fuentes potenciales por Bundesland:
- **Gewerbeamt** municipal: Berlin, München, Hamburg, Frankfurt, Köln, Stuttgart, Düsseldorf, Leipzig, Dresden, Hannover, Nürnberg (mayores). Cada Gewerbeamt puede tener lista de licencias activas.
- **Portales Open Data regionales**: Berlin.de Open Data, Hamburg Transparenzportal, München Open Data, etc.
- **Statistische Landesämter**: agregados sectoriales por Land.

### J.FR — 13 régions + 96 départements + 36.000 communes
- **data.gouv.fr** agregador nacional de datos open
- Portales departementales: Paris Open Data (https://opendata.paris.fr), Lyon (https://data.grandlyon.com), Marseille Open Data, Toulouse Open Data, Nantes (https://data.nantesmetropole.fr), Bordeaux, Lille
- **CCI Régionales** (13): directorios sectoriales por région (Auvergne-Rhône-Alpes, Bourgogne-Franche-Comté, Bretagne, Centre-Val de Loire, Corse, Grand Est, Hauts-de-France, Île-de-France, Normandie, Nouvelle-Aquitaine, Occitanie, Pays de la Loire, Provence-Alpes-Côte d'Azur)

### J.ES — 17 CCAA + 50 provincias + 8.131 municipios
Fuentes principales:
- **datos.gob.es** agregador nacional
- Portales CCAA: **datos.madrid.es**, **opendata.barcelona.cat**, **opendata.euskadi.eus** (País Vasco), **opendata.aragon.es**, **datosabiertos.jcyl.es** (Castilla y León), **datosabiertos.malaga.eu**, **opendata.valencia.es**, **opendatabi.com** (Bilbao)
- **Cámaras de Comercio provinciales** (50): cada una con directorio sectorial (Madrid, Barcelona, Valencia, Sevilla, Bilbao, Málaga, Zaragoza, etc.)
- **BOP** (Boletines Oficiales Provinciales) — anuncios de actividad económica a nivel provincial

### J.NL — 12 provincies + 342 gemeenten
- **data.overheid.nl** agregador nacional
- **Provinciale portales**: data.provincie-utrecht.nl, etc. (algunas tienen)
- **Gemeentelijke open data**: Amsterdam (https://data.amsterdam.nl), Rotterdam, Den Haag, Utrecht, Eindhoven (https://data.eindhoven.nl), etc.
- **CBS Statline** (Centraal Bureau voor de Statistiek) — agregados sectoriales

### J.BE — 3 régions + 10 provincies + 581 communes
- **Vlaanderen**: statistiekvlaanderen.be, geopunt.be, vlaio.be (agencia empresas)
- **Wallonie**: iweps.be, walstat.be, awex.be
- **Bruxelles**: hub.brussels, ibsa.brussels, https://opendata.brussels.be
- Provincias: Antwerpen, Vlaams-Brabant, Oost-Vlaanderen, West-Vlaanderen, Limburg, Brabant Wallon, Hainaut, Liège, Luxembourg, Namur

### J.CH — 26 cantones + ~2.200 Gemeinden
- **opendata.swiss** agregador federal
- **Kantonale Handelsregister** (cross-Familia A.CH.2): 26 cantones con registros independientes
- **Portales open data cantonales**: Zürich (https://data.stadt-zuerich.ch), Bern (https://www.bern.ch/open-data), Basel-Stadt (https://data.bs.ch), Genève (https://ge.ch/sitg/geodata), Lausanne, Vaud (https://www.vd.ch)
- **Statistik Schweiz cantonal**: BFS (Bundesamt für Statistik) con desagregación cantonal

## Sub-técnicas

### J.M1 — Agregador nacional primero, sub-jurisdicción después
Empezar por data.gouv.fr, datos.gob.es, data.overheid.nl, opendata.swiss, data.gov.be (cuando exista) — muchos datasets sub-jurisdiccionales están agregados en el portal federal.

### J.M2 — Portal por portal cuando agregador no cubre
Para datos no disponibles federal, recorrido sistemático por portal regional/municipal.

### J.M3 — Búsqueda por dataset-type
Términos de búsqueda estandarizados: "commerce", "Gewerbe", "licence commerciale", "establecimientos comerciales", "handelsregister", "bedrijven" → filtro por sector auto/transport.

### J.M4 — BOE/BOPs scraping paciente
Boletines oficiales regionales/provinciales contienen anuncios de actividad económica (altas, bajas, modificaciones) a nivel infra-nacional. Parser sistemático de PDFs/XMLs.

## Base legal
Datos abiertos regionales/municipales bajo licencias CC BY o equivalentes nacionales. Directiva EU 2019/1024. Consumo con atribución cuando la licencia lo requiera.

## Métricas
- `sub_jurisdictions_mapped(país)` — cuántas se han integrado vs total
- `unique_discovery_rate_per_sub_jurisdiction` — dealers únicos que cada sub aporta
- `coverage_depth_score` — granularidad territorial alcanzada

## Implementación
- Módulo Go: `discovery/family_j/`
- Sub-módulos por país y por tipo de portal
- Persistencia: tabla `sub_jurisdiction_sources` + `sub_jurisdiction_entities`
- Cron: trimestral por sub-jurisdicción
- Coste: alto inicial (170 sub-jurs × parser específico), bajo en mantenimiento
- Esta familia requiere paciencia iterativa: no se completa en un sprint

## Cross-validation

> Hipótesis de diseño — porcentajes de overlap a validar empíricamente en primera ejecución de discovery completo.

| Familia | Overlap hipotético | Único de J |
|---|---|---|
| A | ~70% (mayoría ya en registro federal) | J captura pequeños comercios con licencia municipal sin registro federal prominente |
| B | ~80% | J añade contexto administrativo + fechas de licencia |
| G | ~30% | J captura dealers no asociados a asociación federal |

## Riesgos y mitigaciones
- R-J1: portales sub-jurisdiccionales con UX lamentable / datos desactualizados. Mitigación: priorizar portales con mejor mantenimiento (mayores ciudades), aceptar gaps en sub-jurisdicciones pequeñas.
- R-J2: formatos heterogéneos (PDF escaneado, XML mal-formed, CSV con codificación rara). Mitigación: parser robusto + OCR para PDFs cuando necesario.
- R-J3: alto coste de implementación inicial. Mitigación: priorización por tamaño (Bundesland/CCAA grandes primero), expansión iterativa.

## Iteración futura
- Micro-jurisdicciones que aparezcan (nuevas mancomunidades, áreas metropolitanas)
- Datasets sectoriales específicos (licencias de transporte, autorizaciones comerciales particulares)
- Integración de BOE-BOPs históricos para reconstruir evolución temporal
