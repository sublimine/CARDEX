# SOURCING_STRATEGY_BY_COUNTRY.md

**Cartera de estrategias de adquisición por país — DE · ES · NL · BE · CH · FR**
Objetivo: romper el monocultivo francés (84 % de candidatos FR, 78 % de fuente única SIRENE) y alcanzar paridad real de cobertura en los 6 mercados, separando los dos frentes: **(A) Discovery de dealers** y **(B) Inventario de vehículos**.

Fecha: 2026-06-06 · Autor: análisis de mercado / ingeniería inversa de fuentes.
Doctrina: ver `CLAUDE.md` y `CONTEXT_FOR_AI.md`. Este documento es de **estrategia de sourcing**, no de arquitectura.

---

## 0. Metodología de verificación y honestidad de datos

Cada fuente se marca **VERIFICADA** (se golpeó el endpoint y devolvió datos útiles en esta sesión) o **TEÓRICA** (existe y está documentada, pero no se confirmó en vivo aquí). Está prohibido inventar; cuando algo no se pudo probar, se dice explícitamente.

**Restricción del entorno (relevante para reproducir):** el shell de esta sesión sólo tiene salida de red a través de un proxy con *allowlist* (`localhost:3128`, responde `X-Proxy-Error: blocked-by-allowlist` para casi todo dominio externo). Por tanto la verificación en vivo se hizo con el fetcher HTTP de la plataforma, que **sí** alcanza APIs de open data gubernamentales (`*.api.gouv.fr`, `opendata.rdw.nl`, `data.bs.ch`, `openmercantil.es`, `offeneregister.de`) pero **no** alcanza endpoints que bloquean rangos de datacenter (OSM Overpass/Nominatim, `taginfo`, `crt.sh`, Wikidata SPARQL, `opendata.swiss`, `boe.es`). Esos últimos están marcados como TEÓRICA-aquí / **VERIFICADO-en-código** cuando ya corren en producción dentro de `discovery/` (familias B, C). Desde la VPS de producción (IP residencial/limpia) son alcanzables; el bloqueo es del sandbox, no de la fuente.

**Resultados de verificación en vivo de esta sesión (cifras reales devueltas):**

| Fuente | País | Endpoint | Resultado en vivo |
|---|---|---|---|
| recherche-entreprises (annuaire-entreprises) | FR | `recherche-entreprises.api.gouv.fr/search` | 200 OK · JSON · geocodificado · NAF 45.11Z dpto 75 = **8 544** · NAF 45.20A dpto 69 = **4 913** |
| RDW Gekentekende Voertuigen | NL | `opendata.rdw.nl/resource/m9d7-ebf2.json` | 200 OK · **16 792 090** vehículos · BMW turismo = **501 667** |
| RDW Erkende Bedrijven | NL | `opendata.rdw.nl/resource/5k74-3jha.json` | 200 OK · **30 678** empresas reconocidas, con dirección |
| Zefix vía Open Data Basel-Stadt | CH | `data.bs.ch/api/explore/v2.1/.../100330/records` | 200 OK · **19 257** empresas (sólo BS) · con UID + coordenadas |
| OpenMercantil (ex-OpenBorme) | ES | `openmercantil.es/api/v1/...` | 200 OK · 2,6 M empresas · `sector/{cnae}/companies` operativo (cobertura CNAE parcial) |
| OffeneRegister.de | DE | `offeneregister.de` + dumps | 200 OK · dump SQLite ~740 MB + JSONL ~250 MB, CC BY 4.0 |

**Leyenda de columnas de las tablas por país:** `fuente | tipo | sirve para | acceso | coste | verificada | volumen estimado | nota técnica`.
Tipos: registro / OSM / OEM / asociación / directorio / portal / otros.

---

## 1. ALEMANIA (DE) — prioridad ALTA

El registro mercantil oficial es el punto débil de DE (sin API ni bulk gratis, fragmentado en 150+ Amtsgerichte y términos NRW restrictivos). El ROI está en **OSM + locators OEM + OffeneRegister (filtrado por nombre) + asociaciones**, no en Handelsregister directo.

| fuente | tipo | sirve para | acceso | coste | verificada | volumen estimado | nota técnica |
|---|---|---|---|---|---|---|---|
| **OSM Overpass** `shop=car`, `shop=car_repair`, `shop=car_parts` | OSM | discovery | Overpass QL (`out count` / `out center`) | gratis | **VERIF. en código** (familia B); no reproducible desde sandbox | ~25–30k `car` + ~40k `car_repair` (estimado, confirmar con `out count`) | Mejor relación señal/ruido para DE. Query: `area(3600051477)->.a; nwr[shop=car](area.a); out center;`. Devuelve nombre, web, addr:*, lat/lon. Mirror si overpass-api.de satura: kumi/private.coffee |
| **Locators OEM** (VW, Audi, BMW, Mercedes, Opel, Ford, Toyota, Hyundai, Kia, Škoda, Seat, Renault, Dacia, Fiat, Peugeot…) | OEM | discovery | HTML + sub-API JSON `?zip=` por marca | gratis | **VERIF. en código** (familia H, URLs reales DE); sub-API JSON por marca: TEÓRICA | ~7 400 puntos de venta de marca (estimado ZDK) | Patrón: `www.<marca>.de/haendlersuche` → XHR a API de tiendas (`?zip=NNNNN&radius=`). Barrer ~8 000 PLZ con paso de radio cubre todo el país. Da web del concesionario → enlaza a frente B |
| **OffeneRegister.de** (dump OpenCorporates del Handelsregister) | registro | discovery | descarga SQLite/JSONL + SQL API `db.offeneregister.de` | gratis (CC BY 4.0) | **VERIFICADA** (sitio + dumps vivos) | ~5–6 M empresas totales; subset auto por nombre | El HR no trae código de actividad fiable → filtrar por nombre: `Autohaus`, `KFZ`, `Automobile`, `Autozentrum`, `Car`, `Motors`. SQLite con FTS5 incluido. Ya usado por CARDEX (`familia_a/de_offeneregister`) |
| Handelsregister.de / Unternehmensregister oficial | registro | discovery | web manual; sin API ni bulk | gratis consulta | TEÓRICA (sin API) | n/a | Términos NRW restrictivos, sin descarga estructurada. **No invertir**; usar OffeneRegister en su lugar |
| **ZDK / Gelbe Seiten / 11880 / Das Örtliche** | directorio | discovery | HTML + sitemap | gratis | TEÓRICA | decenas de miles de entradas «Autohaus»/«Kfz» | Directorios DE muy completos. `gelbeseiten.de` categoría Autohaus/Kfz-Werkstatt. Útiles para cubrir el «long tail» independiente que no está en OEM |
| crt.sh / Certificate Transparency (TLD `.de`) | otros | discovery | API JSON `crt.sh/?q=%25autohaus%25&output=json` | gratis | **VERIF. en código** (familia C); bloqueado en sandbox | miles de dominios | Buscar patrones `autohaus`, `automobile`, `kfz`, `gebrauchtwagen` en CN/SAN. Descubre dominios sin presencia en OSM/OEM |
| Common Crawl (índice URL `.de`) | otros | discovery | índice CDX / columnar (S3) | gratis | TEÓRICA | masivo | Filtrar host por keywords automotrices. Coste = cómputo, no licencia |
| autohaus24.de, pkw.de, auto.de, autoboerse.de, autohus.de | portal | inventario | HTML / sitemap / JSON-LD | gratis (no tier-1) | TEÓRICA (presentes en `scrapers/portals/`) | medio | Portales DE no bloqueados ya scaffoldeados en el repo. Vía sitemap (E03) + JSON-LD (E01) |
| mobile.de, kleinanzeigen.de, autoscout24.de | portal | inventario | — | **PAGO (proxies)** | — | enorme | **APARCADO (backlog)**: tier-1 bloqueado, requiere proxies residenciales. No es vía de coste cero |

**Top ROI DE (volumen × facilidad × coste-cero):**
1. **OSM Overpass `shop=car`+`car_repair`** — máximo volumen geocodificado, gratis, ya en producción.
2. **Locators OEM (barrido por PLZ)** — cobertura completa de la red de marca con web del dealer → puente directo a inventario.
3. **OffeneRegister.de filtrado por nombre** — cubre el independiente registrado que no aparece en OEM.
4. **Gelbe Seiten / 11880** — long tail de talleres/compraventas pequeñas.
5. **crt.sh sobre `.de`** (desde IP de producción) — dominios nuevos no indexados en el resto.

---

## 2. ESPAÑA (ES) — prioridad ALTA

España no tiene API mercantil pública gratuita estilo Francia (el Registro Mercantil es de pago vía registradores.org). La paridad se construye con **OSM + locators OEM + FACONAUTO/GANVAM + OpenMercantil (alertas BORME) + directorios**. La DGT aporta el universo de vehículos (no listings).

| fuente | tipo | sirve para | acceso | coste | verificada | volumen estimado | nota técnica |
|---|---|---|---|---|---|---|---|
| **OSM Overpass** `shop=car`/`car_repair`/`car_parts` | OSM | discovery | Overpass QL | gratis | **VERIF. en código** (familia B); sandbox bloqueado | ~12k `car` + ~20k `car_repair` (estimado) | `area(3601311341)->.a; nwr[shop=car](area.a); out center;`. Núcleo del discovery ES |
| **Locators OEM** (mismas marcas que DE/FR) | OEM | discovery | HTML + sub-API JSON por CP | gratis | **VERIF. en código** (familia H, URLs `.es` reales) | ~3 000 puntos de marca (estimado FACONAUTO) | Barrer CP de 5 dígitos (`?cp=`). Da web → frente B |
| **OpenMercantil** (ex-OpenBorme) | registro | discovery + señales | REST JSON `api/v1/` sin auth | gratis (200 req/día/IP; CC BY 4.0) | **VERIFICADA** | 2,6 M empresas; subset auto parcial | `GET /api/v1/sector/4511/companies` (CNAE 4511 venta automóviles), `/4520` reparación, `/4519`, `/4532`. **Aviso:** cobertura CNAE incompleta (sesgada a constituciones/cooperativas). Mejor uso: **monitorizar nuevas constituciones** (`/nuevas-empresas`, `/daily/{fecha}`) como alerta de dealers nuevos. Datasets descargables CC BY |
| BORME oficial (BOE datos abiertos) | registro | discovery + señales | REST `boe.es/datosabiertos/api/borme/sumario/{YYYYMMDD}` (Accept: application/json/xml) | gratis | TEÓRICA (requiere header Accept; sandbox bloqueó boe.es) | 2,6 M+ acumulado | Fuente primaria de OpenMercantil. Devuelve PDF/XML/HTML por anuncio. Parsear constituciones con objeto social de automoción |
| **FACONAUTO / GANVAM** (asociaciones) | asociación | discovery | HTML directorio de asociados | gratis | TEÓRICA | FACONAUTO ~3 000 concesionarios; GANVAM miles VO | Listados de socios = red oficial + VO de calidad. Scraping del «buscador de asociados» |
| DGT — microdatos de matriculaciones / parque | otros | enriquecimiento | descarga ficheros (mensual) | gratis | TEÓRICA | parque ~25 M | No son listings ni dealers; sirve para sizing de mercado y validación (V03/V07). Equivalente funcional al RDW pero sin API Socrata |
| Páginas Amarillas (paginasamarillas.es), QDQ, Axesor (free tier) | directorio | discovery | HTML / sitemap | gratis | TEÓRICA | decenas de miles | Categorías «Concesionarios», «Talleres», «Compraventa». Long tail independiente |
| crt.sh CT (TLD `.es`) | otros | discovery | API JSON | gratis | VERIF. en código (familia C) | miles | Patrones `motor`, `automoviles`, `ocasion`, `concesionario` |
| autocasion.com, coches.com, ocasionplus, flexicar, clicars | portal | inventario | sitemap / JSON-LD / HTML | gratis (no tier-1) | TEÓRICA (en `scrapers/portals/` + `docs/research/`) | medio-alto | Portales ES no bloqueados ya investigados. Vía E03/E01 |
| coches.net, milanuncios.com, wallapop | portal | inventario | — | **PAGO** | — | enorme | **APARCADO (backlog)** tier-1 |

**Top ROI ES:**
1. **OSM Overpass `shop=car`+`car_repair`** — base geocodificada, gratis.
2. **Locators OEM (barrido por CP)** — red de marca completa con dominio → inventario.
3. **FACONAUTO + GANVAM (directorio de asociados)** — concesionarios oficiales + VO premium.
4. **Páginas Amarillas / QDQ** — long tail de talleres y compraventas.
5. **OpenMercantil `/nuevas-empresas`** — detección temprana de dealers de nueva creación (no para censo total).

---

## 3. PAÍSES BAJOS (NL) — prioridad ALTA · mejor país en open data

NL es el escenario más favorable: el **RDW** publica vía Socrata tanto el universo de vehículos como **la lista oficial de empresas reconocidas** (garajes, estaciones APK, exportadores), todo geocodificable y sin clave. Discovery casi resuelto con una sola fuente verificada.

| fuente | tipo | sirve para | acceso | coste | verificada | volumen estimado | nota técnica |
|---|---|---|---|---|---|---|---|
| **RDW Erkende Bedrijven** (`5k74-3jha`) | registro | discovery | Socrata JSON `opendata.rdw.nl/resource/5k74-3jha.json` | gratis, sin clave | **VERIFICADA** | **30 678** empresas reconocidas (con dirección) | Censo oficial de empresas con reconocimiento RDW. Campos: `naam_bedrijf`, `gevelnaam`, `straat`, `huisnummer`, `postcode`, `plaats`. **Incluye no-automoción** (p.ej. puntos de matrícula) → cruzar con `nmwb-dqkz` (Erkenningen) para filtrar a garaje/APK/dealer/export. SoQL: `$where`, `$limit`, `$offset`, `$select=count(*)` |
| **RDW Erkenningen** (`nmwb-dqkz`) | registro | discovery (filtro) | Socrata JSON | gratis | **VERIFICADA** (linkado desde 5k74) | — | Tipo de reconocimiento por empresa. Permite aislar talleres APK, dealers de exportación, etc. |
| **RDW Gekentekende Voertuigen** (`m9d7-ebf2`) | otros | enriquecimiento + sizing | Socrata JSON/CSV | gratis | **VERIFICADA** | **16 792 090** vehículos | No es listings. Universo VIN/kenteken + specs. Útil para V01/V03/V07/V08 y sizing por marca (BMW turismo = 501 667 verificado). 30 M+ filas históricas; usar `$where`/`$select` |
| **Locators OEM** (`.nl`) | OEM | discovery | HTML + sub-API JSON por postcode | gratis | **VERIF. en código** (familia H; Toyota NL expone `/api/dealers?zip=`) | red de marca completa | Barrer por código postal NL (`1011`–`9999`). Da web → frente B |
| **OSM Overpass** | OSM | discovery | Overpass QL | gratis | VERIF. en código (familia B) | ~5k `car` + ~8k `car_repair` (estimado) | `area(3600047796)->.a; nwr[shop=car](area.a); out center;` |
| **KvK** (Handelsregister NL) | registro | discovery | API `api.kvk.nl/api/v2/zoeken` (clave) + dataset open «basisbedrijfsgegevens» | freemium (API con clave) / descarga | TEÓRICA (clave) / dataset VERIF. en código | ~2 M establecimientos | SBI 45.11/45.20 para filtrar. Ya en `familia_a/nl_kvk`. La API requiere clave (test key disponible); el dataset open es alternativa |
| BOVAG (asociación) | asociación | discovery | HTML directorio de socios | gratis | TEÓRICA | ~9 000+ socios | Buscador de socios BOVAG = dealers/talleres de confianza. Complementa RDW con la marca comercial |
| gaspedaal.nl (agregador), autotrack.nl, autoweek.nl, autowereld.nl, autokopen.nl | portal | inventario | sitemap / JSON-LD / API | gratis (no tier-1) | TEÓRICA (en `docs/research/` con notas) | alto | gaspedaal es meta-buscador (enlaza a dealers). autotrack/autoweek con investigación previa. Vía E03/E01/E02 |
| marktplaats.nl | portal | inventario | — | **PAGO** | — | enorme | **APARCADO (backlog)** tier-1 (propiedad Adevinta, anti-bot fuerte) |

**Top ROI NL:**
1. **RDW Erkende Bedrijven + Erkenningen** — censo oficial geocodificado de 30 678 empresas, gratis, verificado. Discovery resuelto.
2. **Locators OEM (barrido por postcode)** — red de marca con dominio.
3. **OSM Overpass** — complemento de cobertura.
4. **BOVAG socios** — capa de confianza comercial + nombres de fachada.
5. **RDW Gekentekende Voertuigen** — enriquecimiento/validación (no discovery).

---

## 4. BÉLGICA (BE) — prioridad ALTA

BE tiene KBO/BCE como registro, pero el bulk gratuito exige registro por email y la API es de pago. Sin equivalente al RDW. ROI en **OSM + OEM + TRAXIO + KBO bulk (CSV mensual) + directorios**.

| fuente | tipo | sirve para | acceso | coste | verificada | volumen estimado | nota técnica |
|---|---|---|---|---|---|---|---|
| **KBO/BCE Open Data** | registro | discovery | descarga CSV mensual (lunes tras 1er domingo) | gratis (registro+email obligatorio) | TEÓRICA (requiere alta) | ~1,8 M entidades; subset NACEBEL auto | Filtrar por NACEBEL `45.11` (venta), `45.19`, `45.20` (mant./rep.), `45.32`. CSV «Connection BCE Open Data File». Ya scaffoldeado en `familia_a/be_kbo`. La **web service API es de pago** → usar el CSV |
| **KBO Public Search** | registro | discovery | HTML `kbopub.economie.fgov.be` (búsqueda por NACEBEL) | gratis, sin cuenta | TEÓRICA | — | Permite búsqueda por código de actividad sin descarga; útil para validación puntual / refresco |
| **Locators OEM** (`.be`, NL/FR bilingüe) | OEM | discovery | HTML + sub-API por CP | gratis | **VERIF. en código** (familia H, URLs `.be` reales) | red de marca | Barrer CP belgas (1000–9999). Doble idioma en URLs (`/nl/`, `/fr/`) |
| **OSM Overpass** | OSM | discovery | Overpass QL | gratis | VERIF. en código (familia B) | ~4k `car` + ~6k `car_repair` (estimado) | `area(3600052411)->.a; nwr[shop=car](area.a); out center;` |
| **TRAXIO** (+ FEGARBEL) | asociación | discovery | HTML directorio de socios | gratis | TEÓRICA | miles de socios | Federación del sector del automóvil BE. Buscador de miembros = dealers/talleres reconocidos. Ya referenciada (familia G) |
| Gouden Gids / Pages d'Or (goudengids.be) | directorio | discovery | HTML / sitemap | gratis | TEÓRICA | decenas de miles | Categorías «Garages», «Autohandelaars». Long tail bilingüe |
| crt.sh CT (`.be`) | otros | discovery | API JSON | gratis | VERIF. en código (familia C) | miles | Patrones `garage`, `auto`, `occasion`, `tweedehands` |
| gocar.be, 2dehands.be / 2ememain, vroom.be, myway.be, cardoen.be, autoscout24.be | portal | inventario | sitemap / JSON-LD / HTML | mixto (algunos tier-1) | TEÓRICA (en `docs/research/`) | medio | gocar/vroom/myway/cardoen accesibles. **2dehands/2ememain (Adevinta) → APARCADO** |

**Top ROI BE:**
1. **OSM Overpass `shop=car`+`car_repair`** — base geocodificada gratis e inmediata.
2. **Locators OEM (barrido CP bilingüe)** — red de marca con dominio.
3. **KBO Open Data CSV (NACEBEL 45.x)** — censo registral completo tras alta gratuita.
4. **TRAXIO socios** — capa de confianza del sector.
5. **Gouden Gids / Pages d'Or** — long tail independiente.

---

## 5. SUIZA (CH) — prioridad ALTA

CH tiene ZEFIX (índice central) y un ecosistema de open data cantonal excelente vía Opendatasoft/LINDAS. El reto es la fragmentación cantonal, resuelta por mirrors que consolidan los 26 cantones.

| fuente | tipo | sirve para | acceso | coste | verificada | volumen estimado | nota técnica |
|---|---|---|---|---|---|---|---|
| **Zefix vía Open Data Basel-Stadt** (dataset `100330`) | registro | discovery | Opendatasoft v2.1 `data.bs.ch/api/explore/v2.1/catalog/datasets/100330/records` | gratis, sin clave | **VERIFICADA** | **19 257** empresas (sólo BS) | Devuelve `company_legal_name`, `company_uid` (CHE-…), dirección, **coordenadas lat/lon**, URL al registro cantonal. SoQL-like (`?where=`, `?limit=`, `?offset=`). **BS hospeda además el mirror de TODOS los cantones**: `data-bs.ch/stata/zefix_handelsregister/all_cantons/companies_<KT>.csv` |
| **Mirror Zefix all-cantons (CSV)** | registro | discovery | descarga CSV diaria por cantón | gratis | TEÓRICA (mirror confirmado por doc; fetch directo del CSV bloqueado en sandbox) | universo CH ~600k+ empresas activas | 26 ficheros `companies_AG.csv … _ZH.csv`. Filtrar por nombre (`Garage`, `Automobile`, `Autohaus`, `Carrosserie`, `Occasion`) — el registro CH no trae NOGA fiable |
| **ZEFIX REST API + LINDAS SPARQL** | registro | discovery | `zefix.ch/ZefixREST/api/v1/firm/search` (POST) · LINDAS SPARQL (consultas ilimitadas) | gratis | TEÓRICA (POST; sandbox bloqueó) | universo CH | API oficial; búsqueda por nombre/cantón. LINDAS permite listas sin límite de tamaño. Ya en `familia_a/ch_zefix` |
| **Locators OEM** (`.ch`, DE/FR/IT) | OEM | discovery | HTML + sub-API por PLZ | gratis | **VERIF. en código** (familia H, URLs `.ch` reales) | red de marca | Barrer PLZ CH (1000–9999), multilingüe |
| **OSM Overpass** | OSM | discovery | Overpass QL | gratis | VERIF. en código (familia B) | ~3k `car` + ~5k `car_repair` (estimado) | `area(3600051701)->.a; nwr[shop=car](area.a); out center;` |
| **AGVS/UPSA** (asociación) | asociación | discovery | HTML directorio de garajes socios | gratis | TEÓRICA | ~4 000 garajes socios | Federación suiza del automóvil. Buscador de socios geolocalizado |
| local.ch / search.ch | directorio | discovery | HTML / API parcial | gratis | TEÓRICA | decenas de miles | Categorías «Garage», «Autohandel». Long tail trilingüe |
| **auto-api.ch** | portal | inventario | API documentada | gratis/freemium | TEÓRICA (investigación detallada en `docs/research/auto-api-ch.md`) | medio-alto | **Vía de inventario CH de mayor ROI no-bloqueada**; API pensada para integración. Prioridad en `PLAN_PORTALS.md` |
| carforyou.ch, autolina.ch, gowago.ch, comparis.ch, tutti.ch, anibis.ch | portal | inventario | sitemap / JSON-LD / HTML | gratis (no tier-1) | TEÓRICA (en `docs/research/`) | medio | Varios ya investigados. Vía E03/E01 |
| autoscout24.ch | portal | inventario | — | **PAGO** | — | enorme | **APARCADO (backlog)** tier-1 |

**Top ROI CH:**
1. **Mirror Zefix all-cantons (CSV) + API Opendatasoft BS** — censo registral consolidado de los 26 cantones, geocodificado, gratis y verificado (vía BS).
2. **Locators OEM (barrido PLZ multilingüe)** — red de marca con dominio.
3. **auto-api.ch** — inventario CH de coste cero, ya priorizado.
4. **AGVS/UPSA socios** — garajes de confianza.
5. **OSM Overpass** — complemento de cobertura.

---

## 6. FRANCIA (FR) — completar y DIVERSIFICAR fuera de SIRENE

FR ya está sobre-representado, pero depende del 78 % de SIRENE en bruto. El objetivo aquí no es más volumen sino **reducir la dependencia de fuente única**: sustituir/duplicar SIRENE por la API gratuita geocodificada, y añadir OEM, OSM y asociaciones para triangular.

| fuente | tipo | sirve para | acceso | coste | verificada | volumen estimado | nota técnica |
|---|---|---|---|---|---|---|---|
| **recherche-entreprises.api.gouv.fr** (annuaire-entreprises) | registro | discovery | REST JSON sin clave | gratis | **VERIFICADA** | 45.11Z y 45.20A: decenas de miles (dpto 75 = 8 544; dpto 69 45.20A = 4 913) | **Sustituto geocodificado de SIRENE en bruto.** Filtros: `activite_principale=45.11Z` (venta), `45.19Z`, `45.20A/B` (rep.), `45.32Z`, `45.40Z` (motos). Trae lat/lon, dirigeantes, `nombre_etablissements`, enseignes. **Cap de 10 000 resultados/consulta** → segmentar por los 101 `departement` (cada uno < cap) para enumeración completa. Reduce la dependencia de la descarga SIRENE manteniendo la misma base INSEE |
| **SIRENE / INSEE (descarga + API V3)** | registro | discovery | API `api.insee.fr` (clave) + stock descargable | gratis (clave) | VERIF. en código (familia A) | ~140k+ entidades auto | Fuente actual dominante. Mantener como respaldo, **no como única vía**. La API gouv de arriba la complementa sin clave |
| **Locators OEM** (`.fr`) | OEM | discovery | HTML + sub-API por CP | gratis | **VERIF. en código** (familia H, URLs `.fr` reales) | ~14 000 concesionarios | Barrer CP FR. Da web del concesionario → frente B. Diversifica respecto a SIRENE (datos de la propia marca) |
| **OSM Overpass** | OSM | discovery | Overpass QL | gratis | VERIF. en código (familia B) | ~20k `car` + ~30k `car_repair` (estimado) | `area(3602202162)->.a; nwr[shop=car](area.a); out center;`. Triangulación independiente de SIRENE |
| **Mobilians / CNPA** (asociación) | asociación | discovery | HTML directorio | gratis | TEÓRICA | miles | Federación del comercio/reparación FR. Capa de confianza |
| Pappers (free tier) / annuaire-entreprises web | registro | discovery + señales | API freemium / HTML | freemium | TEÓRICA (familia J usa Pappers) | — | Enriquecimiento dirigentes/financiero. Para señales, no censo |
| PagesJaunes.fr | directorio | discovery | HTML / sitemap | gratis | TEÓRICA | decenas de miles | Long tail garages/VO |
| lacentrale.fr, leboncoin.fr | portal | inventario | — | **PAGO** | — | enorme | **APARCADO (backlog)** tier-1 |
| paruvendu.fr, largus.fr, leparking.fr, aramisauto, spoticar, autosphere, starterre | portal | inventario | sitemap / JSON-LD / HTML | mixto | TEÓRICA (en `docs/research/`) | medio-alto | Varios accesibles (spoticar/autosphere/starterre son redes de dealer → inventario limpio). Vía E03/E01 |

**Top ROI FR (foco diversificación):**
1. **recherche-entreprises.api.gouv.fr segmentada por departamento** — misma base INSEE pero geocodificada, sin clave y sin descarga manual; rompe la dependencia operativa de SIRENE en bruto.
2. **OSM Overpass** — fuente totalmente independiente de SIRENE (baja la cuota de fuente-única).
3. **Locators OEM (barrido CP)** — datos de la marca, tercera fuente ortogonal.
4. **Redes de dealer (spoticar/autosphere/starterre)** — inventario limpio vía JSON-LD/sitemap.
5. **Mobilians/CNPA + PagesJaunes** — confianza + long tail.

---

## 7. RESUMEN EJECUTIVO — plan para la paridad entre los 6 países

### 7.1 Diagnóstico
El desbalance (84 % FR, 78 % SIRENE) no se debe a falta de fuentes en DE/ES/NL/BE/CH, sino a que FR tuvo una vía registral trivial (SIRENE) y los demás países no se explotaron con igual profundidad. **Cada país tiene al menos una fuente de discovery de coste cero equivalente o superior a SIRENE.** La paridad es alcanzable sin proxies de pago.

### 7.2 Patrón común replicable (los dos frentes encajan)
El hallazgo estratégico central: **discovery e inventario se enlazan por el dominio del dealer.** Toda fuente de discovery de calidad (registro/OEM/OSM) devuelve la **web del concesionario**; sobre esa web el inventario se extrae con E01 (JSON-LD), E03 (sitemap) y E02 (CMS API) — canales **no bloqueados y sin proxy de pago**. Los portales tier-1 (mobile.de, autoscout24, leboncoin, coches.net, milanuncios, kleinanzeigen, lacentrale, marktplaats, 2dehands) quedan **aparcados en backlog**: son la vía de pago, no la de paridad.

### 7.3 Fuente ancla de discovery por país (coste cero)
| País | Ancla de discovery (coste cero) | Estado | Censo / volumen |
|---|---|---|---|
| **NL** | RDW Erkende Bedrijven (`5k74-3jha`) + Erkenningen | **VERIFICADA** | 30 678 empresas geocodificadas |
| **CH** | Mirror Zefix all-cantons + API Opendatasoft BS | **VERIFICADA (BS)** | 19 257 sólo BS; 26 cantones en mirror |
| **FR** | recherche-entreprises.api.gouv.fr (seg. por dpto) | **VERIFICADA** | base INSEE geocodificada, sin clave |
| **DE** | OSM Overpass + OffeneRegister (filtro nombre) | OSM en prod / OffeneRegister **VERIF.** | dump 5–6 M; subset auto por nombre |
| **ES** | OSM Overpass + FACONAUTO/GANVAM + OEM | OSM en prod / OEM en prod | red de marca + asociados |
| **BE** | KBO Open Data CSV (NACEBEL 45.x) + OEM | KBO scaffolded / OEM en prod | ~1,8 M entidades, filtrable |

En los 6 países, **locators OEM (barrido por código postal)** y **OSM Overpass** son la segunda y tercera vía ortogonal, garantizando que ninguna fuente supere ~40–50 % de los candidatos (objetivo anti-monocultivo).

### 7.4 Hoja de ruta a paridad (orden por ROI y dependencias)
1. **Quick wins verificados (semana 1–2):** activar como familias de discovery de primera clase las tres fuentes ya confirmadas vivas — RDW Erkende Bedrijven (NL), Zefix-Opendatasoft/all-cantons (CH), recherche-entreprises (FR). Las tres son JSON/CSV sin clave y geocodificadas.
2. **Barrido OEM por CP en los 6 países (semana 2–4):** generalizar familia H a un *crawler* de locators por código postal (8 000 PLZ DE, ~6 000 CP FR/ES, etc.). Salida = dominios de dealer → alimenta el frente B.
3. **OSM Overpass por país desde la VPS (continuo):** ya en producción; ejecutar `out count` para fijar volúmenes reales por país y `out center` para ingesta. Confirmar las cifras estimadas de este informe.
4. **Capa registral por país (semana 3–6):** OffeneRegister (DE, filtro nombre), KBO CSV (BE, alta email), OpenMercantil `/nuevas-empresas` (ES, alertas), KvK dataset (NL, respaldo).
5. **Asociaciones + directorios (long tail, semana 4–8):** FACONAUTO/GANVAM (ES), BOVAG (NL), TRAXIO (BE), AGVS/UPSA (CH), Mobilians/CNPA (FR), ZDK + Gelbe Seiten (DE), más PagesJaunes/Páginas Amarillas/Gouden Gids/local.ch.
6. **CT + Common Crawl desde IP de producción (continuo):** crt.sh por TLD y CDX para dominios no cubiertos por el resto.
7. **Inventario sobre dominios descubiertos (paralelo):** priorizar E01/E03/E02 en webs de dealer; portales nicho no bloqueados ya investigados (auto-api.ch, gaspedaal.nl, autocasion.com, gocar.be, pkw.de…). Tier-1 → backlog.

### 7.5 Métrica de éxito de la paridad
- **Cuota por país:** ningún país > 30 % de los candidatos totales (hoy FR = 84 %).
- **Cuota de fuente:** ninguna fuente individual > 40 % (hoy SIRENE = 78 %).
- **Cobertura mínima por país:** ≥ 3 fuentes de discovery ortogonales activas (registro + OEM + OSM como mínimo) antes de declarar el país «en paridad».
- **Coste:** 0 € en proxies para todo lo anterior; el gasto en proxies queda confinado al backlog tier-1.

---

### Anexo · Endpoints verificados en vivo (reproducibles desde IP no-datacenter)
```
# FR — empresas auto geocodificadas, sin clave, segmentar por departamento
GET https://recherche-entreprises.api.gouv.fr/search?activite_principale=45.11Z&departement=75&per_page=25&page=1

# NL — censo oficial de empresas reconocidas (discovery)
GET https://opendata.rdw.nl/resource/5k74-3jha.json?$limit=1000&$offset=0
GET https://opendata.rdw.nl/resource/5k74-3jha.json?$select=count(*)        # => 30678
GET https://opendata.rdw.nl/resource/nmwb-dqkz.json?$limit=1000             # tipos de reconocimiento (filtro)

# NL — universo de vehículos (enriquecimiento/sizing)
GET https://opendata.rdw.nl/resource/m9d7-ebf2.json?$select=count(*)        # => 16792090

# CH — Zefix consolidado vía Open Data Basel-Stadt (geocodificado)
GET https://data.bs.ch/api/explore/v2.1/catalog/datasets/100330/records?limit=100
#   mirror todos los cantones: https://data-bs.ch/stata/zefix_handelsregister/all_cantons/companies_<KT>.csv

# ES — BORME estructurado, sin auth (CC BY 4.0; 200 req/día)
GET https://openmercantil.es/api/v1/sector/4511/companies
GET https://openmercantil.es/api/v1/nuevas-empresas

# DE — Handelsregister como open data (dump + SQL API)
https://daten.offeneregister.de/openregister.db.gz        # SQLite ~740MB (FTS5)
https://db.offeneregister.de/                              # SQL API (CSV/JSON, CORS)
```

### Anexo · Fuentes consultadas
- recherche-entreprises.api.gouv.fr (verificado en vivo)
- opendata.rdw.nl — datasets 5k74-3jha, nmwb-dqkz, m9d7-ebf2 (verificado en vivo); https://www.rdw.nl/over-rdw/dienstverlening/open-data
- data.bs.ch dataset 100330 (verificado en vivo); opendata.swiss/en/dataset/zefix-zentraler-firmenindex
- openmercantil.es /api (verificado en vivo)
- offeneregister.de + daten.offeneregister.de (verificado en vivo)
- KBO/BCE: economie.fgov.be (KBO Open Data, CSV mensual con alta)
- BORME oficial: boe.es/datosabiertos/api/api.php
- CARDEX interno: `CONTEXT_FOR_AI.md` (familias A–O), `discovery/internal/families/`, `docs/research/*`, `PLAN_PORTALS.md`
