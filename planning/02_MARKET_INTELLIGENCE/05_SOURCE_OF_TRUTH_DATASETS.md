# 05 — Catálogo de Datasets Fuente de Verdad

## Identificador
- Fecha: 2026-04-14, Estado: DOCUMENTADO
- Alcance: datasets oficiales usados como denominadores de cobertura y fuentes de datos fácticos verificables

## Nota metodológica

Este documento cataloga los datasets oficiales que CARDEX usa o pretende usar como:
1. **Denominadores de cobertura** — para calcular qué porcentaje del mercado real está indexado.
2. **Fuentes de datos fácticos verificables** — para cross-validar VINs, registros de empresas, o estadísticas de mercado.
3. **Fuentes de enriquecimiento** — para completar datos que los anunciantes no siempre incluyen.

Los datasets se clasifican en tres niveles de accesibilidad:
- **OPEN** — acceso libre, sin registro, sin coste, licencia permisiva (CC0, CC-BY, ODbL, dominio público).
- **PUBLIC-API** — acceso libre con API pública, posiblemente con rate limits o registro gratuito requerido.
- **RESTRICTED** — acceso de pago, sujeto a acuerdo comercial, o con restricciones de uso significativas.
- **NOT-AVAILABLE** — datos que existen en el organismo oficial pero no están publicados en ningún formato accesible.

---

## I. Datasets por País — Registros de Vehículos

### I.1 — NL — RDW Open Data (PAÍS PILOTO)

**Organismo:** Rijksdienst voor het Wegverkeer (RDW)
**URL:** https://opendata.rdw.nl/en/datasets
**Accesibilidad:** OPEN (CC0 — dominio público)
**Formato:** CSV, JSON, API SODA (Socrata Open Data API)
**Frecuencia de actualización:** Diaria

**Datasets relevantes:**

| Dataset ID | Nombre | Contenido | Filas (est.) |
|---|---|---|---|
| `m9d7-ebf2` | Gekentekende voertuigen | Matrícula, marca, modelo, tipo carrocería, color, cilindrada, fecha 1ª matrícula, masa, potencia | ~9M |
| `8ys7-d773` | Voertuigen | Datos técnicos detallados por VIN | ~9M |
| `a34c-vvps` | Gekentekende voertuigen brandstof | Tipo de combustible por matrícula | ~9M |
| `t3tf-6b2n` | Voertuigen APK (ITV) | Historico de inspecciones técnicas | ~80M |
| `hx2c-gt7k` | Terugroepacties (Recalls) | Recalls activos por marca/modelo | Variable |

**Uso en CARDEX:**
- **Denominador de cobertura NL:** `SELECT COUNT(DISTINCT kenteken) FROM rdw_voertuigen WHERE voertuigsoort = 'Personenauto' AND status = 'ACTIEF'` — número exacto de turismos activos matriculados en NL. Esto permite calcular la cobertura de CARDEX con precisión VIN-level.
- **Cross-validación V01 (VIN):** el RDW dataset contiene el kenteken (matrícula NL) pero no el VIN completo WVTA en todos los registros. La relación matrícula↔VIN puede inferirse en muchos casos via los datasets de homologación.
- **V06 (datos técnicos):** potencia (vermogenKW), cilindrada, combustible son verificables contra los datasets `voertuigen` y `brandstof`.

**Nota de licencia:** CC0 permite uso comercial ilimitado. No se requiere atribución (aunque buena práctica incluirla). El RDW no puede reclamar derechos sui generis sobre estos datos pues los ha liberado explícitamente bajo CC0.

**Implementación técnica:**
```bash
# Download incremental (delta daily)
curl -o /srv/cardex/data/rdw/gekentekende_delta.csv \
  "https://opendata.rdw.nl/resource/m9d7-ebf2.csv?$where=datum_tenaamstelling>'2026-04-13'&$limit=50000"

# Full import to DuckDB
duckdb /srv/cardex/data/rdw.duckdb << 'EOF'
CREATE TABLE IF NOT EXISTS rdw_voertuigen AS
SELECT * FROM read_csv_auto('/srv/cardex/data/rdw/gekentekende_*.csv');
EOF
```

---

### I.2 — DE — KBA (Kraftfahrt-Bundesamt)

**Organismo:** Kraftfahrt-Bundesamt (KBA)
**URL:** https://www.kba.de/DE/Statistik/statistik_node.html
**Accesibilidad:** PUBLIC-API (datos estadísticos gratuitos; datos VIN-level: RESTRICTED)
**Formato:** Excel, CSV (estadísticas agregadas), PDF

**Datasets disponibles públicamente:**

| Publicación | Contenido | Frecuencia | Acceso |
|---|---|---|---|
| FZ 1 — Neuzulassungen | Matriculaciones nuevas por marca/modelo/mes | Mensual | OPEN (Excel) |
| FZ 8 — Bestand | Parc total por marca/modelo/edad | Anual (enero 1) | OPEN (Excel) |
| FZ 27 — Besitzumschreibungen | Transferencias de titularidad (transacciones ocasión) | Mensual | OPEN (Excel) |
| FZ 13 — Außerbetriebsetzungen | Bajas del parc | Mensual | OPEN (Excel) |
| VIN-level individual | Datos individuales por matrícula/VIN | — | RESTRICTED (§31 StVG) |

**Restricción crítica:** Los datos individuales de vehículos alemanes están protegidos por el § 31 StVG (Straßenverkehrsgesetz). El acceso a datos VIN-level o matrícula-level requiere legitimación específica (propietario del vehículo, autoridades, tasadores acreditados). CARDEX **no puede** acceder a datos VIN-level del KBA sin acuerdo formal.

**Uso en CARDEX:**
- **Denominador de cobertura DE:** estadístico solamente — `FZ 27 Besitzumschreibungen` da el número total de transferencias de titularidad (proxy de transacciones B2C+B2B) pero no un denominador VIN-level.
- **Validación macroeconómica:** verificar que las tendencias de volumen de CARDEX son coherentes con los datos KBA agregados (sanity check de cobertura).

**Fuente primaria:** https://www.kba.de/DE/Statistik/Fahrzeuge/Neuzulassungen/neuzulassungen_node.html

---

### I.3 — FR — ANTS / SIV (Système d'Immatriculation des Véhicules)

**Organismo:** Agence Nationale des Titres Sécurisés (ANTS) / Ministère de l'Intérieur
**URL:** https://www.ants.gouv.fr
**Accesibilidad:** NOT-AVAILABLE para datos individuales; estadísticas agregadas: RESTRICTED (via AAA Data)

**Situación:**
- El SIV (Système d'Immatriculation des Véhicules) contiene todos los vehículos matriculados en FR con datos de propietario, historial de transferencias, estado.
- **Acceso al SIV:** estrictamente reservado a autoridades públicas, profesionales del automóvil acreditados (via portail SIV), y organismos con acceso formal. CARDEX no puede acceder al SIV directamente.
- Los datos VIN-level del SIV no son open data ni están disponibles via API pública.

**Alternativa — AAA Data:**
- **AAA Data** (filial del Groupe Argus) redistribuye estadísticas del SIV bajo acuerdo comercial.
- Los datos AAA Data incluyen: estadísticas por marca/modelo/año, datos de primera immatriculation, historial de propietarios (anonimizados a nivel estadístico).
- **Coste:** [pendiente verificación empírica — placeholder: acuerdo comercial, estimado €5.000-20.000/año según volumen]
- CARDEX no depende de AAA Data en fase MVP — es una fuente de enriquecimiento opcional para P1.

**Denominador FR para cobertura CARDEX:**
- ANTS publica estadísticas anuales de matriculaciones totales por categoría — este es el denominador estadístico disponible.
- No existe un denominador VIN-level público en FR equivalente al RDW NL.

**Fuente:** https://www.securite-routiere.gouv.fr/les-medias/nos-publications/bilan-de-laccidentalite-de-lannee-2023 (estadísticas FR); https://www.aaagroup.com/fr/produits/donnees/ (AAA Data comercial)

---

### I.4 — ES — DGT / IDEAUTO

**Organismo:** Dirección General de Tráfico (DGT)
**URL:** https://www.dgt.es/inicio/estadisticas/
**Accesibilidad:** Estadísticas: OPEN (CSV/Excel); Datos individuales: RESTRICTED (tasa + legitimación)

**Datasets disponibles:**

| Dataset | Contenido | Frecuencia | Acceso |
|---|---|---|---|
| Estadísticas de matriculaciones | Matriculaciones nuevas y ocasión por provincia/marca | Mensual | OPEN (PDF/Excel) |
| Anuario estadístico general | Parc por antigüedad/combustible | Anual | OPEN (PDF) |
| Consulta individual (tasa 3.1) | Datos de un vehículo concreto por matrícula | Per consulta | RESTRICTED (€2-5/consulta) |

**Restricción ES:** La DGT cobra tasa para consultas individuales de vehículos. El acceso masivo a datos VIN-level requeriría un acuerdo específico con la DGT — no existe acceso open data equivalente al RDW.

**IDEAUTO:**
- [pendiente verificación empírica — placeholder: IDEAUTO es un proveedor privado español de datos de vehículos de ocasión, con datos de anuncios de Coches.net y otros portales]. Datos comerciales.

**Uso en CARDEX:**
- Denominador ES: estadístico (anuario DGT).
- Consultas individuales VIN: posible via tasa DGT para verificación puntual de historial, no para indexación masiva.

**Fuente:** https://www.dgt.es/inicio/estadisticas/vehiculos-matriculados/

---

### I.5 — BE — DIV / Vias

**Organismo:** Direction pour l'Immatriculation des Véhicules (DIV) / Vias institute
**URL:** https://mobilit.belgium.be/fr/vehicules / https://www.vias.be/fr/nosrecherches/statistiques
**Accesibilidad:** Estadísticas: PUBLIC (web); Datos individuales: RESTRICTED

**Situación BE:**
- La DIV gestiona el registro de vehículos en BE. Datos individuales no son open data.
- Vias (antiguo IBSR) publica estadísticas trimestrales de matriculaciones y parc.
- **FEBIAC** (Fédération Belge de l'Industrie de l'Automobile et du Cycle) publica estadísticas mensuales de matriculaciones.

**Datos disponibles:**

| Fuente | Contenido | Frecuencia | Acceso |
|---|---|---|---|
| DIV Statistiques | Parc por marca/tipo/año | Anual | OPEN (PDF) |
| FEBIAC | Matriculaciones nuevas | Mensual | OPEN (web) |
| Vias Statistics | Estadísticas accidentes y parc | Anual | OPEN (PDF) |
| DIV individual | Datos VIN/matrícula individual | — | RESTRICTED |

**Uso en CARDEX:**
- Denominador BE: estadístico (DIV/FEBIAC).

**Fuente:** https://www.febiac.be/fr/statistiques, https://mobilit.belgium.be/fr/vehicules/statistiques

---

### I.6 — CH — ASTRA / MOFIS

**Organismo:** Bundesamt für Strassen (ASTRA)
**URL:** https://www.astra.admin.ch/astra/de/home/fachleute/fahrzeuge/fahrzeugstatistiken.html
**Accesibilidad:** Estadísticas: OPEN; MOFIS (datos técnicos): RESTRICTED

**Datasets disponibles:**

| Dataset | Contenido | Frecuencia | Acceso |
|---|---|---|---|
| Statistisches Jahrbuch Strassenverkehr | Parc, matriculaciones anuales | Anual | OPEN (PDF) |
| Zulassungsstatistik | Matriculaciones mensuales por marca | Mensual | OPEN (Excel/web) |
| MOFIS (Motor vehicle information) | Datos técnicos individuales VIN | — | RESTRICTED (acuerdo formal) |
| Strassenverkehrsamt cantonal | Datos por cantón | Variable | Variable por cantón |

**MOFIS:** El Motor Vehicle Information System de ASTRA contiene datos técnicos de todos los vehículos matriculados en CH. El acceso requiere un acuerdo formal con ASTRA — no es open data. CARDEX no puede acceder a MOFIS sin dicho acuerdo (ver Restricción Absoluta R-A-8 en 04_REGULATORY_FRAMEWORK.md).

**Denominador CH:** estadístico anual (Statistisches Jahrbuch). El más impreciso de los 6 países — actualización anual solamente.

**Fuente:** https://www.astra.admin.ch/astra/de/home/fachleute/fahrzeuge/fahrzeugstatistiken.html

---

## II. Datasets de Registros de Empresas (Dealers)

### II.1 — NL — KvK (Kamer van Koophandel) API

**Organismo:** Kamer van Koophandel
**URL:** https://developers.kvk.nl/
**Accesibilidad:** PUBLIC-API (registro gratuito, rate limits: 100 req/h free tier)
**Formato:** JSON REST API

**Endpoints relevantes:**
```
GET /api/v2/zoeken?handelsnaam={name}&sbi={code}&pagina={n}
# KvK usa códigos SBI de 4 dígitos (no 2.x):
# SBI code 4511 = handel in en reparatie van personenauto's en lichte bedrijfsauto's
# SBI code 4519 = handel in andere motorvoertuigen
# SBI code 4520 = onderhoud en reparatie van motorvoertuigen

GET /api/v2/basisprofielen/{kvkNummer}
# Datos completos del registro: naam, adres, SBI, rechtsvorm, activiteiten, vestigingen
```

**Uso en CARDEX:**
- Familia A (Business Registry Discovery) usa la KvK API para descubrir dealers registrados con SBI 4511/4519/4520 en NL.
- Cross-validación de VAT numbers (BTW-nummer en NL) extraídos de anuncios con el registro KvK.
- V08 (VAT validation) — el KvK BTW-nummer puede verificarse tanto via VIES como via KvK directamente.

**Rate limits:** El free tier (100 req/h) es suficiente para el volumen de descubrimiento de CARDEX en NL (~10.000 dealers total, discovery cycle cada 30 días). No requiere upgrade en S0.

**Fuente:** https://developers.kvk.nl/documentation

---

### II.2 — DE — Handelsregister (Bundesamt für Justiz)

**Organismo:** Bundesamt für Justiz / Justizportale der Länder
**URL:** https://www.handelsregister.de
**Accesibilidad:** PUBLIC (búsqueda web, descarga CSV/XML)
**Formato:** Web scraping + CSV parcial (no API oficial estable)

**Situación:** El Handelsregister alemán está distribuido por Länder (no centralizado a nivel federal). Existe un portal de búsqueda centralizado (handelsregister.de) pero no hay API oficial. Los datos están disponibles públicamente pero requieren scraping o descarga manual.

**Alternativa — OpenCorporates:**
- OpenCorporates indexa datos del Handelsregister y ofrece API (free tier: 50 req/día; paid: ilimitado).
- URL: https://api.opencorporates.com/v0.4/companies/search?jurisdiction_code=de&q={name}

**Uso en CARDEX:**
- Familia A para DE: combina OpenCorporates + web scraping selectivo del Handelsregister para dealers Kfz (WZ 45.1/45.2).
- Cross-validación USt-IdNr (VAT DE) via VIES + Bundeszentralamt für Steuern.

**Fuente:** https://www.handelsregister.de, https://api.opencorporates.com/documentation

---

### II.3 — FR — INSEE SIRENE

**Organismo:** Institut national de la statistique et des études économiques (INSEE)
**URL:** https://api.insee.fr/entreprises/sirene/V3/siret
**Accesibilidad:** PUBLIC-API (token gratuito requerido, rate limits generosos)
**Formato:** JSON REST API

**Endpoints relevantes:**
```
GET /siret?q=activitePrincipaleUniteLegale:45.1*+OR+activitePrincipaleUniteLegale:45.2*
&nombre=1000&debut=0
# NAF code 45.1 = Commerce de véhicules automobiles
# NAF code 45.2 = Entretien et réparation de véhicules automobiles

GET /siren/{siren}
# Datos completos del grupo empresarial

GET /siret/{siret}
# Datos del establecimiento individual
```

**Datos disponibles:**
- Denominación social, SIRET/SIREN, code APE/NAF, adresse, date création, statut (actif/cessé).
- 70+ millones de establecimientos en el SIRENE — es la base de datos de empresas más completa de FR.

**Uso en CARDEX:**
- Familia A para FR: consulta SIRENE con NAF 45.1/45.2 para descubrir dealers activos en FR.
- Cross-validación de SIRET/SIREN extraídos de anuncios — verificación de que el dealer existe en el registro oficial.
- V08 (VAT validation FR): número TVA FR (FR + 11 dígitos) verificable via VIES + SIRENE.

**Rate limits:** Token gratuito permite ~10 req/s. Suficiente para discovery cycle CARDEX.

**Fuente:** https://api.insee.fr/catalogue/, https://www.sirene.fr/sirene/public/accueil

---

### II.4 — ES — Registro Mercantil (BORME)

**Organismo:** Ministerio de Justicia (Registradores de España)
**URL:** https://www.boe.es/diario_borme/
**Accesibilidad:** PUBLIC (descarga BORME diario en XML), datos detallados: RESTRICTED (via registradores.org con coste)
**Formato:** XML (BORME), web scraping para datos individuales

**Situación ES:**
- El BORME (Boletín Oficial del Registro Mercantil) publica diariamente las inscripciones en el Registro Mercantil en XML libre.
- Los datos completos de cada empresa (objeto social, administradores, capital) requieren consulta individual via registradores.org (coste ~€3-5/consulta).

**Alternativa para CARDEX:**
- Para descubrimiento de dealers (CNAE 45.1/45.2), CARDEX puede usar el BORME XML para detectar nuevas inscripciones y bajas.
- Para validación de NIF/CIF, la AEAT ofrece verificación de número válido (no de datos de la empresa) via VIES para NIF intracomunitarios.

**SABI (Bureau van Dijk):** Base de datos comercial de empresas españolas con datos financieros. [pendiente verificación empírica — placeholder: €10.000-50.000/año según licencia] — no viable en fase MVP.

**Fuente:** https://www.boe.es/diario_borme/, https://www.registradores.org/

---

### II.5 — BE — BCE (Banque-Carrefour des Entreprises)

**Organismo:** Service public fédéral Économie / FOD Economie
**URL:** https://kbopub.economie.fgov.be/kbopub/zoeknaamfonetischform.html
**Accesibilidad:** PUBLIC (búsqueda web); API: PUBLIC-API (OpenData BCE)
**Formato:** CSV bulk download, web search

**OpenData BCE:**
- La BCE publica sus datos completos como open data descargable mensualmente.
- URL descarga: https://economie.fgov.be/fr/themes/entreprises/banque-carrefour-des-entreprises/opendata-bce
- Formato: ZIP con CSVs (enterprise.csv, establishment.csv, activity.csv, address.csv, contact.csv)
- Licencia: CC-BY 4.0 (atribución requerida — "Source: BCE/KBO")

**Contenido:**
- `activity.csv` con `nace_version=2008` y `nace_code LIKE '45%'` identifica dealers de automóviles en BE.
- `enterprise.csv` con `status='Active'` y `juridical_form` — filtra empresas activas.
- Cruce con `address.csv` da dirección del establecimiento.

**Uso en CARDEX:**
- Descarga mensual del bulk export BCE (comprimido ~500 MB).
- Import a DuckDB: `CREATE TABLE bce_activity AS SELECT * FROM read_csv_auto('activity.csv')`.
- Query: `SELECT * FROM bce_activity WHERE nace_code LIKE '45%' AND status='Active'` — lista completa de dealers BE.
- Denominador de cobertura BE: `COUNT(DISTINCT enterprise_number) FROM bce_activity WHERE nace_code IN ('45.1','45.2')`.

**Fuente:** https://economie.fgov.be/fr/themes/entreprises/banque-carrefour-des-entreprises/opendata-bce

---

### II.6 — CH — UID-Register (Unternehmens-Identifikationsregister)

**Organismo:** Bundesamt für Statistik (BFS) / Eidgenössische Steuerverwaltung (ESTV)
**URL:** https://www.uid.admin.ch/uid-home.aspx
**Accesibilidad:** PUBLIC-API (SOAP/XML web service, registro gratuito)
**Formato:** SOAP web service

**Endpoints:**
```xml
<!-- Búsqueda por categoría de empresa -->
<uid:searchEntities>
  <uid:searchParameters>
    <uid:uidOrganisationId>...</uid:uidOrganisationId>
    <uid:chid>...</uid:chid>
    <uid:enterpriseIdentification>
      <uid:category>ESTAB</uid:category>  <!-- Establecimientos -->
      <uid:noga08Code>451*</noga08Code>  <!-- NOGA 451 = Handel mit Motorfahrzeugen -->
    </uid:enterpriseIdentification>
  </uid:searchParameters>
</uid:searchEntities>
```

**Uso en CARDEX:**
- Familia A para CH: consulta UID-Register con NOGA 451 (equivalente a NACE 45.1 en CH) para descubrir dealers.
- En CH, el UID (Unternehmens-Identifikationsnummer) es el equivalente del SIRET/SIREN o KvK — es el identificador único de empresa.
- V08 (VAT validation CH): el MWST-Nummer suizo (CHE + 9 dígitos + indicador) puede verificarse via UID-Register. CH no es miembro de VIES (sistema UE).

**Nota:** El UID-Register es el sustituto de VIES para la validación de empresas en CH. CARDEX lo menciona en el 04_REGULATORY_FRAMEWORK.md como la alternativa nativa CH al sistema UE.

**Fuente:** https://www.uid.admin.ch/uid-home.aspx, https://www.uid.admin.ch/doc/uid_wsvc_aufruf_v4.5.pdf (SOAP API docs)

---

## III. VIES — Validación de VAT Numbers UE

**Organismo:** Comisión Europea (DG TAXUD)
**URL:** https://ec.europa.eu/taxation_customs/vies/
**Accesibilidad:** PUBLIC-API (REST JSON, sin clave de API requerida)
**Cobertura:** 27 países UE (no CH)

**API REST:**
```
GET https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{countryCode}/vat/{vatNumber}

# Ejemplo:
GET https://ec.europa.eu/taxation_customs/vies/rest-api/ms/NL/vat/NL123456789B01

# Respuesta:
{
  "isValid": true,
  "name": "EXAMPLE BV",
  "address": "STRAAT 1, 1234AB AMSTERDAM",
  "countryCode": "NL",
  "vatNumber": "NL123456789B01"
}
```

**Rate limits:** [pendiente verificación empírica — placeholder: ~60-100 req/min sin autenticación; la Comisión no publica límites oficiales pero en la práctica se aplican]

**Uso en CARDEX:**
- V08 (VAT number validation): validación de todos los NIF/VAT extraídos de anuncios para los 5 países UE (DE/FR/ES/BE/NL).
- La respuesta de VIES incluye nombre y dirección de la empresa — puede usarse para completar datos del dealer si el anuncio solo tiene el VAT number.
- CH: UID-Register (ver §II.6). No VIES.

**Fuente:** https://ec.europa.eu/taxation_customs/vies/#/vat-validation

---

## IV. Datos de Mercado — Estadísticas Agregadas

### IV.1 — ACEA (European Automobile Manufacturers' Association)

**Organismo:** ACEA
**URL:** https://www.acea.auto/statistics/
**Accesibilidad:** OPEN (Excel/PDF, sin registro)
**Contenido:** Matriculaciones EU27+UK+EFTA, parc total, desglose por combustible, ventas de ocasión.
**Frecuencia:** Mensual (matriculaciones), anual (parc + transacciones ocasión)

**Uso en CARDEX:**
- Validación macroeconómica de las estimaciones de tamaño de mercado de 01_MARKET_CENSUS.md.
- Dato de referencia para P1 (verificación de cifras de mercado).
- Métrica de denominador proxy para países sin VIN-level open data.

---

### IV.2 — Eurostat — Estadísticas de Transporte

**Organismo:** Eurostat (Comisión Europea)
**URL:** https://ec.europa.eu/eurostat/data/database (sección "Transport")
**Accesibilidad:** OPEN (API REST Eurostat)
**Datasets relevantes:**

| Dataset Code | Contenido |
|---|---|
| `road_eqs_carmot` | Parc de vehículos por tipo de motor y país |
| `road_eqs_carage` | Parc por antigüedad y país |
| `road_if_roadsc` | Longitud red vial por país (contexto) |

**API Eurostat:**
```
GET https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/road_eqs_carmot
?format=JSON&lang=EN&geo=DE&geo=FR&geo=ES&geo=BE&geo=NL
```

---

### IV.3 — ECB FX Feed — Tipos de Cambio

**Organismo:** European Central Bank (BCE)
**URL:** https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml
**Accesibilidad:** OPEN (XML público, sin autenticación)
**Contenido:** Tipos de cambio EUR contra ~30 monedas (incluye CHF) actualizados cada día hábil ~16:00 CET
**Uso en CARDEX:** V15 (currency normalization) — CARDEX usa el feed diario ECB para convertir CHF→EUR en listings suizos.

**Implementación:**
```go
// Actualización diaria del tipo de cambio CHF/EUR
type ECBFeed struct {
    Date  time.Time
    Rates map[string]float64 // {"CHF": 0.984, "GBP": 0.857, ...}
}

func FetchECBRates(ctx context.Context) (*ECBFeed, error) {
    url := "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
    // Parsear XML y devolver ECBFeed
}
```

**Fuente:** https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/eurofxref-graph-chf.en.html

---

### IV.4 — NHTSA vPIC — VIN Decoder

**Organismo:** National Highway Traffic Safety Administration (NHTSA, USA)
**URL:** https://vpic.nhtsa.dot.gov/api/
**Accesibilidad:** PUBLIC-API (sin autenticación, open data)
**Cobertura VIN:** Global — incluye VINs europeos (WMI codes de marcas europeas registradas en NHTSA)

**Endpoints:**
```
GET https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{VIN}?format=json

# Respuesta incluye:
# - Make, Model, ModelYear
# - BodyClass (sedan, SUV, etc.)
# - DriveType (FWD, RWD, AWD)
# - EngineDisplacementL, EngineCylinders
# - FuelTypePrimary
# - GVWR (Gross Vehicle Weight Rating)
# - PlantCity, PlantCountry (lugar de fabricación)
# - ErrorCode = "0" si decodificación exitosa
```

**Uso en CARDEX:**
- V01 (VIN validation): decodificación del VIN para verificar marca/modelo declarado en el anuncio vs WMI code real.
- V06 (technical specs cross-check): cilindrada, tipo de combustible, año de modelo son verificables via vPIC.
- **Estrategia:** mirror local del dataset vPIC para evitar dependencia de API externa:
  - NHTSA publica el dataset completo vPIC para descarga: https://vpic.nhtsa.dot.gov/api/Home/Index/ApiDocumentation#Flat-File
  - Formato: Microsoft Access .mdb (legacy) + CSV exports
  - Actualización: trimestral
  - Tamaño: ~500 MB comprimido

**Implementación mirror local:**
```sql
-- SQLite local mirror de vPIC (actualización trimestral)
CREATE TABLE vpic_wmi (
    wmi         TEXT PRIMARY KEY,  -- 3 chars World Manufacturer Identifier
    make_name   TEXT,
    country     TEXT,
    vehicle_type TEXT
);

CREATE TABLE vpic_make_model (
    make_id     INTEGER,
    make_name   TEXT,
    model_id    INTEGER,
    model_name  TEXT
);
```

**Fuente:** https://vpic.nhtsa.dot.gov/api/, https://vpic.nhtsa.dot.gov/api/Home/Index/ApiDocumentation

---

## V. Tabla Resumen — Datasets por Uso

| Dataset | País | Acceso | Uso en CARDEX | Denominador VIN-level |
|---|---|---|---|---|
| RDW Open Data | NL | OPEN (CC0) | Coverage denominator, V01, V06 | **Sí** |
| KBA FZ 8/27 | DE | OPEN (Excel) | Macro denominator, sanity check | No (estadístico) |
| ANTS/SIV | FR | RESTRICTED | N/A en MVP | No |
| DGT Estadísticas | ES | OPEN (PDF/Excel) | Macro denominator | No |
| DIV/FEBIAC | BE | OPEN (web) | Macro denominator | No |
| ASTRA Statistik | CH | OPEN (PDF/Excel) | Macro denominator | No |
| KvK API | NL | PUBLIC-API | Familia A discovery, V08 | — |
| Handelsregister DE | DE | PUBLIC (web) | Familia A discovery | — |
| INSEE SIRENE | FR | PUBLIC-API | Familia A discovery, V08 | — |
| BORME | ES | PUBLIC (XML) | Familia A discovery | — |
| BCE OpenData | BE | OPEN (CC-BY) | Familia A discovery, V08 | — |
| UID-Register | CH | PUBLIC-API (SOAP) | Familia A discovery, V08 | — |
| VIES | UE (5) | PUBLIC-API | V08 VAT validation | — |
| ACEA Statistics | EU | OPEN | Macro validation | No |
| Eurostat Transport | EU | OPEN | Macro validation | No |
| ECB FX Feed | EUR | OPEN | V15 CHF→EUR conversion | — |
| NHTSA vPIC | Global | PUBLIC-API | V01 VIN decode, V06 specs | — |

---

## VI. Prioridad de Implementación por Fase

### P1 (Market Intelligence — verificación de cifras)
1. RDW Open Data → descargar y verificar volumen NL (único VIN-level)
2. KBA FZ 8 + FZ 27 → verificar cifras DE de 01_MARKET_CENSUS.md
3. ACEA Statistics → verificar tabla comparativa 6 países
4. BCE OpenData → contar dealers BE activos NACE 45.1/45.2

### P2 (Discovery Buildout)
5. KvK API → discovery familia A en NL
6. INSEE SIRENE → discovery familia A en FR
7. UID-Register → discovery familia A en CH
8. VIES → validación VAT todos los países

### P3 (Extraction Pipeline)
9. NHTSA vPIC → V01 VIN validation (mirror local)
10. ECB FX Feed → V15 CHF conversion (scheduled daily)

### P5 (Infrastructure)
11. RDW Open Data → pipeline de actualización diaria automatizada

---

## VII. Notas de Acceso y Operación

### Seguridad de acceso a APIs públicas
- **KvK API:** token almacenado en systemd-creds (`/etc/cardex/kvk.env`), nunca en código fuente.
- **INSEE SIRENE:** token almacenado en `/etc/cardex/insee.env`.
- **VIES:** sin token — API pública; tráfico a `ec.europa.eu` via CardexBot/1.0.
- **ECB XML:** sin autenticación — descarga diaria via cron a `/srv/cardex/data/ecb/`.
- **RDW SODA API:** sin autenticación para bulk; app_token opcional para rates más altos — almacenar en `/etc/cardex/rdw.env` si se registra.

### Backup de datasets críticos
Los datasets con acceso restringido o que pueden cambiar de URL deben mantenerse en backup local:
```
/srv/cardex/data/
├── rdw/          # RDW delta diarios
├── vpic/         # NHTSA vPIC trimestral mirror
├── ecb/          # ECB FX feed diario
├── bce/          # BCE OpenData mensual bulk
└── sirene/       # INSEE SIRENE snapshots (si se adquiere bulk)
```

Storage Box (1 TB): los backups de estos datasets son parte del backup diferencial diario con age encryption.
