# Familia M — Validaciones fiscales y signals operativos

## Identificador
- ID: M, Nombre: Signals fiscales y operativos, Categoría: Fiscal-signals
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
El universo dealer del knowledge graph puede contener entidades registradas pero inactivas, quebradas, dormantes o "empresa-pantalla". Esta familia aporta signals independientes de actividad real: VAT activo, plantilla reciente contratada, presencia en registros fiscales actualizados, actividad tributaria reciente. Convierte el knowledge graph de "lista de empresas registradas" en "lista de empresas OPERATIVAS".

## Fuentes

### M.1 — VIES (VAT Information Exchange System) — EU
- URL: https://ec.europa.eu/taxation_customs/vies/
- API REST libre (SOAP + REST)
- Validación de VAT number por país → devuelve NOMBRE + DIRECCIÓN + STATUS (valid/invalid)
- Cobertura: todos los países EU (DE/FR/ES/BE/NL)
- Rate limit: razonable, usable a escala
- Uso principal: validación de actividad (VIES valid = empresa operativa)

### M.2 — MwSt-Nummer CH
- Registro suizo de VAT (CH no es EU → no VIES)
- URL: https://www.uid.admin.ch
- Búsqueda por UID (CHE-XXX.XXX.XXX)
- Datos: razón social, dirección, status

### M.3 — BTW-nummer NL
- Validación específica NL dentro de VIES + lookup KvK

### M.4 — USt-IdNr DE
- Validación específica DE dentro de VIES + Bundeszentralamt für Steuern

### M.5 — Numéro de TVA FR
- Validación específica FR dentro de VIES

### M.6 — NIF ES
- Validación específica ES dentro de VIES

### M.7 — Numéro d'entreprise BE
- Validación específica BE dentro de VIES + BCE/KBO

### M.8 — Job boards — signals de plantilla activa

#### M.8.1 — Indeed (multi-país)
- URL: https://www.indeed.{de|fr|es|nl|be|ch}
- Búsqueda por títulos: "Automobilverkäufer", "Vendeur automobile", "Comercial automoción", "Autoverkoper", etc.
- Geo-filtered por código postal
- Signal: dealer con ofertas activas = plantilla en expansión = operativo

#### M.8.2 — Stepstone (DE, NL, BE)
- Plataforma job board DACH + Benelux
- URL: https://www.stepstone.de/stellenangebote

#### M.8.3 — Welcome to the Jungle (FR, ES, BE)
- URL: https://www.welcometothejungle.com
- Perfil empresa con "we're hiring"

#### M.8.4 — InfoJobs (ES)
- URL: https://www.infojobs.net

#### M.8.5 — LinkedIn Jobs
- Búsqueda por industry automotive + geo + job titles

#### M.8.6 — StackOverflow Jobs (legacy, limited) — útil para OEM digital dealers

### M.9 — Bolsas de trabajo sectoriales automoción
- Autojob.de, Automobilwoche Stellenmarkt (DE)
- Jobautomobile.fr (FR)
- etc.

### M.10 — Export/import customs aggregates
- Eurostat datasets sobre exportación/importación vehicle
- Algunos países publican aduanas per-empresa (limitado)
- Signal: empresa con actividad internacional = establishment serio

### M.11 — Registro de concursos / quiebras
- BORME ES (sección quiebras)
- BODACC FR (sección redressement/liquidation)
- Bundesanzeiger DE (Insolvenzen)
- Openfaillissementen NL
- **Uso negativo**: empresa en concurso → flag en knowledge graph, no activar indexación de catálogo

## Sub-técnicas

### M.M1 — VIES batch validation
Para cada empresa del knowledge graph con VAT conocido, ejecutar batch VIES validation mensual. Output: `vat_active_status + validation_date`.

### M.M2 — Job board sweeping
Sweeps semanales por job boards con queries geo-filtrados. Cross-reference empresa contratante con knowledge graph → signal actividad.

### M.M3 — Monitoring de insolvencias
Ingesta continua de boletines de insolvencia → alerta por match con empresas del knowledge graph → flag state change.

### M.M4 — Composite operational score
Fórmula: `operational_score = w1·vat_active + w2·recent_job_posting + w3·no_insolvency + w4·recent_activity_external_signal`

Pesos calibrables. Score bajo T_inactive → entidad queda en "archive" (no se intenta indexar catálogo).

## Base legal
- VIES: API pública oficial EU
- Job boards: acceso HTML público sujeto a ToS de cada plataforma, respeto estricto
- Boletines oficiales: datos públicos garantizados por ley
- Cross-country handling acorde a GDPR (datos de empresas son esencialmente no-PII excepto administradores personas físicas)

## Métricas
- `vat_active_rate(país)` — % empresas del knowledge graph con VIES valid
- `operational_score_distribution` — distribución del score
- `insolvency_detection_latency` — tiempo entre aparición en boletín oficial y flag en CARDEX
- `job_posting_signal_correlation` — correlación entre hiring y indexación exitosa (signal de calidad)

## Implementación
- Módulo Go: `discovery/family_m/`
- Sub-módulos: `vies/`, `job_boards/`, `insolvency_monitors/`, `scoring/`
- Persistencia: tabla `operational_signals` con timestamp por signal + función de scoring
- Cron: VIES mensual, job boards semanal, insolvencias diario
- Coste: bajo (queries rate-limited controlados)

## Cross-validation

M es familia de enriquecimiento, no de discovery primario. Complementa todas las demás familias añadiendo dimension de "empresa operativa" al knowledge graph.

## Riesgos y mitigaciones
- R-M1: VIES temporalmente caído. Mitigación: retry + mark entity como "pending validation", no bloquear pipeline.
- R-M2: job board anti-bot escala. Mitigación: rate limits muy conservadores, rotación de fuentes, no evasión.
- R-M3: falsos positivos de operational score (empresa dormida pero con VAT activo histórico). Mitigación: combinación multi-signal + thresholds calibrados empíricamente.

## Iteración futura
- Integración de registros de licencias municipales activas (cross-Familia J)
- Análisis de DNS uptime de sus websites como signal complementario
- Monitoreo de redes sociales para post frequency (cross-Familia L)
