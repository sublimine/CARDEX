# CARDEX 13/10 — Plan de Cobertura Funcional Total

Fecha: 2026-05-07  
Estado: Documento estratégico/técnico  
Scope: producto, datos, scraping/extracción, discovery, quality, Check, Workspace, API, legal, SRE, seguridad y go-to-market  
Tipo de cambio: documentación únicamente, sin modificación de código productivo

---

## 0. Propósito

Este documento define qué tendría que existir para que CARDEX alcance un estándar funcional **13/10**: no simplemente un MVP correcto, sino una plataforma B2B de inteligencia de vehículo usado que sea objetivamente superior a la combinación manual de marketplaces, herramientas de pricing, hojas Excel, llamadas a dealers, verificadores de historial y CRM.

El objetivo no es añadir features indiscriminadamente. El objetivo es construir un sistema que sea:

1. legalmente defensible;
2. medible de extremo a extremo;
3. funcionalmente completo;
4. operativamente resiliente;
5. comercialmente útil para compradores B2B reales;
6. capaz de demostrar valor económico con datos, no con promesas.

La definición de 13/10 para CARDEX es:

> Un comprador B2B profesional puede usar CARDEX para encontrar stock europeo que no detectaría de forma eficiente en mobile.de, AutoScout24, AutoUncle, llamadas directas, hojas Excel o feeds parciales; puede ver el riesgo, comparar precio, deduplicar fuentes, calcular margen, contactar al dealer, operar el deal y exportarlo por API, todo con trazabilidad legal y freshness medido.

---

## 1. Principios no negociables

### 1.1. Legal-first

CARDEX no debe depender de técnicas grises. Para 13/10, todo acceso automatizado debe ser defendible en auditoría.

Reglas:

- usar únicamente User-Agent identificable `CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)` para tráfico automatizado de crawling/indexación;
- respetar robots.txt;
- no usar stealth browser;
- no usar fingerprint spoofing;
- no usar TLS impersonation;
- no usar proxies residenciales;
- no usar rotación de IP para evitar límites;
- no usar anti-captcha;
- no copiar contenido creativo cuando basten hechos estructurados;
- registrar evidencia mínima de acceso, fuente, timestamp, estrategia y decisión robots.

### 1.2. Medición antes que intuición

Ningún módulo debe considerarse completo si no tiene métricas.

Ejemplos:

- `extraction_success_rate(strategy, country)`;
- `freshness_sla_pct(country, source_type)`;
- `duplicate_vehicle_rate(country)`;
- `false_merge_rate`;
- `dead_letter_rate(country)`;
- `manual_review_age_p95`;
- `robots_disallow_total(domain, country)`;
- `legal_kill_switch_active_total`;
- `buyer_margin_discovered_eur_monthly`.

### 1.3. Evidencia por campo

Cada dato útil debe tener procedencia:

```json
{
  "field": "price_gross_eur",
  "value": 18490,
  "source_url": "https://dealer.example/stock/123",
  "strategy": "E01",
  "observed_at": "2026-05-07T10:15:00Z",
  "confidence": 0.96,
  "conflicts": []
}
```

### 1.4. Canonical first

El producto no debe centrarse en listings aislados, sino en vehículos canónicos y observaciones.

- Un vehículo puede aparecer en varias fuentes.
- Un listing puede cambiar de precio.
- Un dealer puede duplicar stock en varias plataformas.
- Una fuente puede estar desactualizada.

CARDEX debe representar esta realidad explícitamente.

### 1.5. No silent failures

Si una estrategia deja de funcionar, debe verse en dashboards y alertas. No puede haber fallos silenciosos de scraping, extraction, freshness, Check, API o Workspace.

---

## 2. Estado base asumido

CARDEX ya dispone de una base con:

- `discovery/`: descubrimiento multi-familia A-O;
- `extraction/`: estrategias E01-E13 registradas en el servicio;
- `quality/`: validadores V01-V20;
- `workspace/`: CRM, inbox, documents, finance, media, kanban, web PWA;
- `innovation/`: servicios experimentales como routes, trust, tax, forecasting, RAG/GNN;
- `deploy/`: single VPS, Caddy, Prometheus, Grafana, backups;
- `CONTEXT_FOR_AI.md`: jerarquía de realidad frente a visión.

El salto 13/10 consiste en cerrar las brechas entre:

- módulo existente vs módulo productivo;
- documentación vs medición real;
- capacidad técnica vs utilidad comercial;
- scraping puntual vs sistema de datos autocurativo.

---

## 3. Scorecard 13/10

| Área | Gate 13/10 |
|---|---|
| Legal/compliance | 0 fuentes grises activas, 0 findings bloqueantes, 100% fuentes clasificadas |
| Discovery | Cobertura auditable por país, entity resolution dealer, ownership histórico de dominios |
| Extraction | Success rate real >85% en dealers web activos maduros, E07/E10/E11 productivos |
| Freshness | 99% de listings activos dentro de SLA por segmento |
| Vehicle identity | Canonical vehicle, duplicate rate <0.5%, false merge rate <0.1% |
| Quality | Precisión >98% en campos críticos medidos con corpus validado |
| Check | Risk report legal y explicable para 6 países, sin inventar endpoints ni datos |
| Workspace | Flujo sourcing→deal→docs→finance→syndication conectado |
| API | OpenAPI estable, API keys, scopes, webhooks, bulk export, integración <1 día |
| Intelligence | Opportunity engine con backtest y margen realizado vs estimado |
| Observabilidad | No silent failures, dashboards por país/fuente/estrategia, alertas accionables |
| Seguridad | CI supply-chain, secrets scanning, SBOM, restore drills, runbooks |
| Mercado | 10+ usuarios B2B activos usando datos reales |
| Valor | Margen económico descubierto y medido por usuario/mes |

---

## 4. Bloque A — Compliance total

### 4.1. Problema

Un sistema B2B de datos no puede escalar si su adquisición de datos depende de técnicas que un competidor, plataforma o regulador pueda atacar fácilmente.

Los mayores riesgos son:

- cease-and-desist de plataformas;
- conflicto con robots.txt;
- uso de User-Agent no identificable;
- scraping de contenido protegido;
- bypass de límites;
- uso de fuentes restringidas sin contrato;
- datos personales o PII persistidos innecesariamente.

### 4.2. Objetivo 13/10

CARDEX debe poder mostrar, para cada fuente y cada extractor:

- por qué se permite usarla;
- qué datos se extraen;
- qué datos no se extraen;
- cómo se respeta robots.txt;
- qué User-Agent se usa;
- cómo se apaga la fuente;
- qué evidencia queda para auditoría.

### 4.3. Arquitectura requerida

#### 4.3.1. Source Legal Registry

Crear una tabla o módulo operacional:

```sql
CREATE TABLE source_legal_registry (
  source_id              TEXT PRIMARY KEY,
  source_name            TEXT NOT NULL,
  country_code           TEXT,
  source_type            TEXT NOT NULL,
  legal_class            TEXT NOT NULL,
  access_basis           TEXT NOT NULL,
  allowed_data_fields    TEXT NOT NULL,
  forbidden_data_fields  TEXT,
  robots_required        INTEGER NOT NULL DEFAULT 1,
  user_agent_required    TEXT NOT NULL,
  consent_required       INTEGER NOT NULL DEFAULT 0,
  contract_required      INTEGER NOT NULL DEFAULT 0,
  status                 TEXT NOT NULL DEFAULT 'ACTIVE',
  reviewed_at            TEXT NOT NULL,
  reviewed_by            TEXT,
  notes                  TEXT
);
```

Legal classes:

| Clase | Significado | Uso permitido |
|---|---|---|
| A | API pública/open data | Sí, con rate limits y términos |
| B | Web pública con robots permitido | Sí, solo hechos mínimos |
| C | Fuente con consentimiento dealer | Sí, según consentimiento |
| D | Fuente restringida/contrato requerido | No, salvo contrato |
| E | Fuente prohibida o gris | No |

#### 4.3.2. Robots Decision Log

```sql
CREATE TABLE robots_decision_log (
  id              TEXT PRIMARY KEY,
  host            TEXT NOT NULL,
  url             TEXT NOT NULL,
  user_agent      TEXT NOT NULL,
  allowed         INTEGER NOT NULL,
  robots_hash     TEXT,
  fetched_at      TEXT NOT NULL,
  ttl_expires_at  TEXT NOT NULL,
  strategy_id     TEXT,
  dealer_id       TEXT
);
```

#### 4.3.3. Kill-switch operacional

```sql
CREATE TABLE source_kill_switch (
  source_id      TEXT PRIMARY KEY,
  enabled        INTEGER NOT NULL DEFAULT 1,
  reason         TEXT,
  disabled_at    TEXT,
  disabled_by    TEXT,
  expires_at     TEXT,
  incident_id    TEXT
);
```

### 4.4. Tareas atómicas

1. Buscar en todo el repo `Mozilla`, `Chrome`, `Safari`, `Firefox`, `proxy`, `bypass`, `cloudflare`, `rotation`, `captcha`, `stealth`.
2. Sustituir cualquier User-Agent no institucional en código activo.
3. Aislar código histórico en `deprecated/` o eliminarlo si viola política.
4. Crear `source_legal_registry`.
5. Crear `robots_decision_log`.
6. Crear `source_kill_switch`.
7. Añadir CI que bloquee User-Agent no CardexBot en código activo.
8. Añadir CI que bloquee patrones de evasión y bypass.
9. Añadir tests que verifiquen que cada estrategia declara `source_type` y `legal_class`.
10. Añadir endpoint interno `/ops/legal/sources`.
11. Añadir dashboard compliance.
12. Documentar respuesta ante cease-and-desist en runbook.

### 4.5. Definition of Done

- 100% estrategias declaran clase legal.
- 100% tráfico automatizado usa CardexBot salvo integraciones API con requisitos propios documentados.
- 100% dominios web consultan robots antes del crawling HTML.
- 0 fuentes E activas.
- 0 findings bloqueantes en auditoría legal.
- Kill-switch probado en simulacro.

---

## 5. Bloque B — Extraction industrial

### 5.1. Problema

El pipeline de extracción tiene muchas estrategias, pero 13/10 exige que cada una tenga comportamiento productivo, métricas, tests y fallback claro. No basta con que el servicio registre E01-E13.

### 5.2. Estrategias objetivo

| Estrategia | Objetivo 13/10 |
|---|---|
| E01 JSON-LD | Alta precisión, fixtures multilingües, schema variants |
| E02 CMS REST | WordPress/plugins comunes, endpoints detectados, pagination |
| E03 Sitemap | Sitemap index, nested sitemaps, URL classification |
| E04 RSS/Atom | Feeds inventory, incremental detection |
| E05 DMS API | Adapters por DMS real, contratos/API cuando aplique |
| E06 Microdata/RDFa | Legacy structured fallback |
| E07 Playwright XHR | Interceptor real, no no-op, SPA coverage |
| E08 PDF | Tablas, OCR legal, layout variants |
| E09 Excel/CSV | Dialect detection, sheets, encoding, mapping |
| E10 Email | IMAP opt-in, attachments, forwarding parsers |
| E11 Edge Push | Dealer consent, signed push, Tauri/CLI real |
| E12 Manual Review | Cola priorizada, SLA, feedback loop |
| E13 VLM | Opt-in, cost-aware, last automated fallback |

### 5.3. E07 Playwright real

#### Problema específico

E07 no puede ser no-op en producción. Los sitios SPA modernos son una parte crítica de la cobertura real. Si E07 no funciona, el sistema sobreestima cobertura.

#### Requisitos

- Implementar `XHRInterceptor` real dentro de extraction o módulo compartido.
- No depender de paquetes `internal` de otro módulo si rompe encapsulación.
- Configurar browser con identidad CardexBot donde sea posible.
- No usar stealth.
- No usar evasión de fingerprint.
- Respetar robots y kill-switch.
- Limitar tiempo por página.
- Capturar solo XHR relevantes.
- Guardar fixtures JSON anonimizados.
- Métrica `e07_interceptor_mode` con valores `real|noop`.
- Alerta si producción arranca en modo `noop`.

#### Tareas

1. Crear `extraction/internal/browser/playwright.go`.
2. Implementar `InterceptXHR(ctx, url, filter)`.
3. Inyectar en `main.go` cuando `EXTRACTION_PLAYWRIGHT_ENABLED=true`.
4. Añadir health check de browser.
5. Añadir fixtures de 100 XHR captures.
6. Añadir tests offline de `parseXHRBody`.
7. Añadir test de integración opcional con browser.
8. Añadir métrica de modo no-op.
9. Añadir alerta `E07NoopInProduction`.

### 5.4. E10 Email productivo

#### Requisitos

- IMAP con consentimiento dealer.
- Soporte OAuth/app password donde aplique.
- Lectura incremental.
- Deduplicación por Message-ID y attachment hash.
- Parsers de CSV/XLS/PDF adjuntos.
- Redacción PII.
- Mapeo a `VehicleRaw`.
- Auditoría de consentimiento.

#### Tareas

1. Crear `email_source_account`.
2. Crear `email_ingestion_cursor`.
3. Crear parser MIME.
4. Crear `attachment_inventory_detector`.
5. Reutilizar E08/E09 para adjuntos.
6. Crear tests con 50 emails fixture.
7. Añadir métricas `e10_messages_processed_total`, `e10_attachments_parsed_total`, `e10_inventory_detected_total`.

### 5.5. E11 Edge Push como moat

#### Requisitos

- Dealer instala cliente.
- Dealer ve qué se comparte.
- Dealer puede pausar.
- API key rotatoria.
- Payload firmado.
- TLS.
- Push incremental.
- Logs dealer-side.
- Health central.

#### Tareas

1. Onboarding UI para dealer.
2. Generación de API key por dealer.
3. Signed payload con timestamp y nonce.
4. Rechazo de replay.
5. CLI `cardex-dealer test-connection`.
6. Tauri client con pantalla de estado.
7. Mapping CSV local.
8. Auto-update.
9. Endpoint `/edge/health`.
10. Dashboard Edge adoption.

### 5.6. Scheduler adaptativo

El scheduler no debe usar solo intervalos fijos por estrategia.

Fórmula objetivo:

```text
next_extraction_at = now + f(
  strategy,
  dealer_stock_size,
  observed_change_rate,
  buyer_interest,
  source_reliability,
  error_rate,
  legal_class,
  prior_success
)
```

#### Segmentos

| Segmento | SLA |
|---|---|
| High-value/high-interest | 6h |
| Dealer grande activo | 12h |
| Dealer normal | 24-48h |
| Dealer pequeño estable | 72h |
| Fuente con errores | Backoff |
| Fuente legalmente sensible | Baja frecuencia o apagada |

### 5.7. Metrics obligatorias

- `extraction_strategy_attempts_total{strategy,country}`
- `extraction_strategy_success_total{strategy,country}`
- `extraction_strategy_partial_total{strategy,country}`
- `extraction_strategy_failure_total{strategy,country,reason}`
- `extraction_vehicles_found_total{strategy,country}`
- `extraction_latency_seconds{strategy}`
- `extraction_dead_letter_total{country}`
- `extraction_robots_disallowed_total{country,host}`
- `extraction_http_status_total{strategy,status}`
- `extraction_noop_strategy_active{strategy}`

### 5.8. Definition of Done

- E07 real en producción o explícitamente deshabilitado con impacto medido.
- E10 deja de ser stub.
- E11 tiene al menos 10 dealers piloto.
- Cada estrategia tiene fixtures offline.
- Dashboard por estrategia/país.
- Dead-letter rate medido.
- Success rate real, no estimado.

---

## 6. Bloque C — Discovery 360 auditable

### 6.1. Problema

Discovery A-O es potente, pero 13/10 exige que la cobertura sea verificable contra denominadores, que la entidad dealer esté resuelta y que el ownership de dominios no sea ambiguo.

### 6.2. Denominadores oficiales

Crear `market_denominator`:

```sql
CREATE TABLE market_denominator (
  id                  TEXT PRIMARY KEY,
  country_code        TEXT NOT NULL,
  region_code         TEXT,
  dealer_type         TEXT NOT NULL,
  denominator_count   INTEGER NOT NULL,
  source_name         TEXT NOT NULL,
  source_url          TEXT NOT NULL,
  source_date         TEXT NOT NULL,
  methodology         TEXT,
  confidence          REAL NOT NULL,
  created_at          TEXT NOT NULL
);
```

### 6.3. Entity resolution dealer

Un dealer canónico debe fusionar:

- VAT/UID;
- razón social;
- nombre comercial;
- dominio;
- teléfono;
- email genérico;
- dirección;
- coordenadas;
- OEM affiliation;
- marketplace IDs;
- DMS provider;
- sucursales;
- grupo empresarial.

### 6.4. Domain ownership history

```sql
CREATE TABLE domain_ownership_history (
  id                    TEXT PRIMARY KEY,
  domain                TEXT NOT NULL,
  dealer_id             TEXT NOT NULL,
  valid_from            TEXT NOT NULL,
  valid_to              TEXT,
  confidence            REAL NOT NULL,
  evidence_json         TEXT NOT NULL,
  change_reason         TEXT,
  created_at            TEXT NOT NULL
);
```

### 6.5. Confidence model v2

El scoring actual no debe tratar señales correlacionadas como independientes.

Ejemplo de dependencias:

- marketplace backlink y dealer website pueden derivar de la misma fuente;
- OSM y Wikidata pueden estar desactualizados;
- VAT registry prueba entidad legal, no stock activo;
- OEM locator prueba autorización, no disponibilidad de usados;
- social profile prueba presencia, no inventario.

El modelo debe calcular:

```text
P(active_dealer)
P(has_used_inventory)
P(domain_owned_by_dealer)
P(contact_valid)
P(source_reliable)
```

### 6.6. Saturation dashboard

Por país:

- denominator oficial;
- dealers descubiertos;
- dealers activos;
- dealers con dominio;
- dealers con stock extraído;
- dealers en dead-letter;
- dealers edge-connected;
- cobertura por región;
- cobertura por tipo de dealer;
- confidence distribution.

### 6.7. Definition of Done

- 6 países con denominador documentado.
- Cobertura calculable automáticamente.
- Dealer duplicate rate <1%.
- Domain ownership conflicts visibles.
- Confidence model calibrado con dataset etiquetado.
- Saturation report mensual.

---

## 7. Bloque D — Identidad canónica de vehículo

### 7.1. Problema

Un listing no es un vehículo. El mismo coche puede aparecer en dealer web, mobile.de, AutoScout24, CSV, PDF y edge push. CARDEX 13/10 debe crear una entidad canónica.

### 7.2. Modelo propuesto

```sql
CREATE TABLE canonical_vehicle (
  canonical_vehicle_id       TEXT PRIMARY KEY,
  vin                        TEXT,
  plate_hash                 TEXT,
  make_canonical             TEXT,
  model_canonical            TEXT,
  variant_canonical          TEXT,
  year                       INTEGER,
  body_type                  TEXT,
  fuel_type                  TEXT,
  first_seen_at              TEXT NOT NULL,
  last_seen_at               TEXT NOT NULL,
  identity_confidence        REAL NOT NULL,
  merge_status               TEXT NOT NULL DEFAULT 'ACTIVE'
);
```

```sql
CREATE TABLE vehicle_listing_observation (
  observation_id             TEXT PRIMARY KEY,
  canonical_vehicle_id       TEXT,
  dealer_id                  TEXT NOT NULL,
  source_id                  TEXT NOT NULL,
  source_url                 TEXT NOT NULL,
  source_listing_id          TEXT,
  extraction_strategy        TEXT NOT NULL,
  observed_at                TEXT NOT NULL,
  price_gross_eur            REAL,
  price_net_eur              REAL,
  mileage_km                 INTEGER,
  listing_status             TEXT,
  field_confidence_json      TEXT NOT NULL,
  raw_fingerprint_sha256     TEXT NOT NULL
);
```

### 7.3. Merge engine

Niveles:

1. VIN exacto.
2. Matrícula legalmente disponible.
3. Dealer + source listing ID.
4. Canonical URL.
5. Fuzzy identity: make/model/year/km/color/price/window.
6. Photo perceptual hash donde sea legal.
7. Temporal continuity.

### 7.4. Merge explainability

```json
{
  "candidate_a": "obs_1",
  "candidate_b": "obs_2",
  "decision": "MERGE",
  "confidence": 0.94,
  "reasons": ["same_vin", "same_dealer", "price_delta_below_1pct"],
  "conflicts": ["mileage_delta_500km"],
  "review_required": false
}
```

### 7.5. Split workflow

Si se fusionan dos vehículos erróneamente:

- split manual;
- rollback observations;
- audit trail;
- training sample negativo;
- test fixture.

### 7.6. Definition of Done

- Duplicate rate <0.5%.
- False merge rate <0.1%.
- 100% merges con explicación.
- Price history por vehículo canónico.
- Listing history por source.
- Split workflow operativo.

---

## 8. Bloque E — Freshness y sold detection

### 8.1. Problema

En automoción B2B, un dato viejo destruye confianza. El sistema debe saber si un vehículo sigue activo, si el precio cambió y cuándo se verificó cada campo.

### 8.2. Freshness por campo

Cada campo crítico debe tener `last_verified_at`:

- precio;
- kilometraje;
- estado;
- URL;
- fotos;
- dealer;
- VIN;
- matrícula cuando aplique;
- disponibilidad.

### 8.3. Sold detection v2

Señales:

- HTTP 404/410;
- redirect a catálogo general;
- desaparece del sitemap;
- schema.org availability;
- texto sold/reserved en DE/FR/ES/NL/BE/EN;
- edge push status;
- marketplace status;
- price removed;
- contact form disabled.

### 8.4. Freshness SLA

| Tipo | SLA |
|---|---|
| High-interest active listing | 6h |
| Normal active listing | 24h |
| Low-interest active listing | 72h |
| Suspected sold | 6h recheck |
| Dealer dead | weekly |
| Edge push | <1h |

### 8.5. Métricas

- `vehicle_freshness_sla_pct{country,segment}`
- `vehicle_stale_total{country}`
- `sold_false_active_rate{country}`
- `price_stale_rate{country}`
- `field_age_seconds{field,country}`

### 8.6. Definition of Done

- 99% de listings activos dentro de SLA.
- Sold false-active rate <0.5%.
- Price stale rate <1%.
- Freshness visible por país/fuente/dealer.

---

## 9. Bloque F — Quality como decision engine

### 9.1. Problema

Un score compuesto único no basta. El usuario necesita saber:

1. si los datos son fiables;
2. si el coche es comercialmente interesante;
3. si hay riesgo de compra.

### 9.2. Scores separados

```text
DataQualityScore: completitud, consistencia, freshness, fuente, conflictos.
CommercialScore: precio vs mercado, liquidez, margen, demanda, route.
RiskScore: historial, dealer trust, recalls, km, legal flags, anomalies.
```

### 9.3. Field Confidence

```json
{
  "make": {"value": "BMW", "confidence": 0.99, "sources": ["E01", "E07"]},
  "price": {"value": 18490, "confidence": 0.92, "sources": ["E01"], "age_hours": 8},
  "mileage": {"value": 118000, "confidence": 0.88, "conflicts": ["E07 reported 117500"]}
}
```

### 9.4. Conflict resolver

Conflicts must not be overwritten silently:

- price conflict >3% triggers review;
- mileage conflict >1000km triggers warning;
- VIN conflict triggers critical;
- make/model conflict triggers identity review;
- status conflict active/sold triggers fast recheck.

### 9.5. Manual review priority

Priority formula:

```text
priority = commercial_value * buyer_interest * risk_severity * confidence_gap * freshness_impact
```

### 9.6. Definition of Done

- Critical field precision >98%.
- Manual review SLA <24h.
- 100% critical conflicts visible.
- Quality score correlates with downstream complaints/outcomes.
- Every manual correction creates a fixture or rule update.

---

## 10. Bloque G — CARDEX Check premium/legal

### 10.1. Objetivo

Check debe ser un risk engine, no una pantalla decorativa.

### 10.2. Source capability matrix

Por país y dato:

| País | VIN | matrícula | inspección | km | robo | embargo | export | recalls | fuente |
|---|---|---|---|---|---|---|---|---|---|
| NL | Alta | Alta | APK | Parcial | Sí | No | Sí | EU/RDW | Open data |
| ES | Variable | Variable | ITV difícil | Variable | DGT/pro | Sí si legal | Sí | EU | Requiere legal review |
| FR | Limitada | Limitada | CT restringido | Limitado | No público | No público | Variable | EU | Professional access |
| BE | Limitada | Variable | GOCA/Car-Pass | Car-Pass | Variable | No | Variable | EU | B2B contract |
| DE | VIN/recalls parciales | placa limitada | TÜV no central | No público | No | No | No | KBA/EU | mixed |
| CH | Cantonal | Cantonal | MFK cantonal | No central | No | No | Variable | ASTRA/EU | per-canton |

### 10.3. Reglas

- Si la fuente no es pública o consentida, devolver `unavailable`.
- No inventar endpoints.
- No simular respuestas.
- No usar scraping gris.
- Cada alerta debe tener source y timestamp.

### 10.4. Output objetivo

```text
BUY / CAUTION / DO NOT BUY
```

Con explicación:

- open recall;
- stolen flag;
- mileage rollback;
- inspection gap;
- export/import issue;
- embargo/precinto/baja;
- dealer trust;
- price too low vs cohort;
- data unavailable warning.

### 10.5. Definition of Done

- 6 países con capability matrix.
- 0 datos inventados.
- 0 fuentes grises.
- Cada alerta explica source/evidence.
- False critical alert <1%.
- Missed critical alert <0.5% en corpus validado.

---

## 11. Bloque H — Workspace conectado end-to-end

### 11.1. Objetivo

Workspace debe ser el lugar donde se opera el negocio, no una colección de módulos.

### 11.2. Flujo completo

```text
Opportunity detected
→ user saves vehicle
→ risk check
→ dealer contact
→ inbox thread
→ deal created
→ kanban stage
→ calendar task
→ documents
→ finance/P&L
→ transport/route
→ syndication/resale
→ realized margin
```

### 11.3. Integraciones internas

| Origen | Destino | Regla |
|---|---|---|
| Vehicle | Deal | save/contact creates deal |
| Inbox | Deal | inquiry/reply updates stage |
| Deal | Calendar | reserved/in_transit creates tasks |
| Deal | Documents | contract/invoice generated |
| Vehicle | Finance | purchase/sale/recon costs |
| Finance | Intelligence | realized margin feedback |
| Syndication | Vehicle | status published/sold/withdrawn |
| Check | RiskScore | critical flags block auto-advance |

### 11.4. Roles y permisos

- owner;
- admin;
- buyer;
- sales;
- finance;
- ops;
- readonly;
- external accountant.

### 11.5. Audit trail

```sql
CREATE TABLE workspace_audit_log (
  id              TEXT PRIMARY KEY,
  tenant_id       TEXT NOT NULL,
  actor_id        TEXT NOT NULL,
  entity_type     TEXT NOT NULL,
  entity_id       TEXT NOT NULL,
  action          TEXT NOT NULL,
  previous_json   TEXT,
  next_json       TEXT,
  created_at      TEXT NOT NULL
);
```

### 11.6. Definition of Done

- 90% workflows sin Excel.
- Every important action audited.
- Deal P&L actual vs estimated tracked.
- Inbox/Deal/Kanban/Finance connected.
- Workspace usable by pilot dealers.

---

## 12. Bloque I — Intelligence y Opportunity Engine

### 12.1. Objetivo

El valor real de CARDEX no es listar coches. Es encontrar margen.

### 12.2. Opportunity types

- underpriced vs cohort;
- fresh price drop;
- cross-border arbitrage;
- dealer distress;
- low-risk high-liquidity vehicle;
- EV anomaly discount;
- route-optimized resale;
- high trust dealer new stock;
- stale listing negotiation candidate.

### 12.3. Comparable engine

Para cada vehículo:

- cohort country/make/model/year/km/fuel/transmission;
- median price;
- p25/p75;
- sample count;
- confidence;
- time-to-sell proxy;
- price trend;
- liquidity.

### 12.4. Opportunity score

```text
OpportunityScore = f(
  discount_vs_market,
  liquidity,
  risk_score,
  dealer_trust,
  freshness,
  route_margin,
  buyer_preferences,
  confidence
)
```

### 12.5. Backtesting

Toda oportunidad debe medirse:

- predicted margin;
- realized margin;
- predicted time-to-sell;
- actual time-to-sell;
- risk prediction;
- actual issue count;
- user action taken.

### 12.6. Definition of Done

- Daily top opportunities.
- Backtest dashboard.
- Realized vs estimated margin.
- Alerts actionable, not noisy.
- 10 users B2B confirm value.

---

## 13. Bloque J — API B2B profesional

### 13.1. Objetivo

Un cliente B2B debe poder integrar CARDEX en su sistema en menos de un día.

### 13.2. Endpoints mínimos

```text
GET  /api/v1/search
GET  /api/v1/vehicles/{id}
GET  /api/v1/vehicles/{id}/history
GET  /api/v1/vehicles/{id}/risk
GET  /api/v1/dealers/{id}
GET  /api/v1/dealers/{id}/inventory
GET  /api/v1/opportunities
GET  /api/v1/check/vin/{vin}
GET  /api/v1/check/plate/{country}/{plate}
GET  /api/v1/pricing/comparables
POST /api/v1/routes/optimize
POST /api/v1/bulk/export
POST /api/v1/webhooks
```

### 13.3. Webhook events

```text
vehicle.created
vehicle.updated
vehicle.price_changed
vehicle.sold_detected
vehicle.risk_changed
dealer.created
dealer.trust_changed
opportunity.created
freshness.sla_breached
source.disabled
```

### 13.4. API controls

- API keys;
- OAuth/JWT for workspace;
- scopes;
- tenant isolation;
- quotas;
- cursor pagination;
- idempotency keys;
- request logs;
- OpenAPI spec;
- examples;
- changelog;
- versioning.

### 13.5. Definition of Done

- OpenAPI generated.
- Postman/Bruno collection.
- Example scripts.
- Sandbox data.
- API integration <1 day by pilot.
- Webhooks tested.

---

## 14. Bloque K — Observabilidad y SRE

### 14.1. Objetivo

No debe existir fallo silencioso.

### 14.2. Dashboards

1. Executive Coverage.
2. Country Health.
3. Discovery A-O.
4. Extraction E01-E13.
5. Freshness SLA.
6. Quality V01-V20.
7. Check Sources.
8. Workspace Usage.
9. API Usage.
10. Legal/Compliance.
11. Infra/VPS.
12. Security/Supply Chain.

### 14.3. Alerts críticas

- extraction success drop >20% in 24h;
- freshness SLA breach;
- E07 noop in prod;
- HTTP 403 spike;
- HTTP 429 spike;
- robots disallow change;
- legal source disabled;
- duplicate spike;
- false-active sold spike;
- manual review SLA breach;
- DB busy timeout spike;
- disk >80%;
- backup failure;
- API 5xx >1%;
- source kill-switch activated.

### 14.4. Synthetic tests

Cada hora:

- fixture dealer extraction;
- quality pipeline fixture;
- API search;
- Check sample;
- Workspace login/API;
- backup status;
- Prometheus target status.

### 14.5. Definition of Done

- Detection <5 min.
- Root-cause dashboard <15 min.
- Restore drill passed.
- Failover drill documented.
- Weekly ops report generated.

---

## 15. Bloque L — Test corpus y regression harness

### 15.1. Fixture bank mínimo

| Área | Fixtures |
|---|---:|
| E01 JSON-LD | 100 |
| E02 CMS REST | 50 |
| E03 Sitemap | 100 |
| E04 RSS | 30 |
| E05 DMS | 50 |
| E07 XHR | 100 |
| E08 PDF | 50 |
| E09 Excel/CSV | 50 |
| E10 Email | 50 |
| Check VIN/plate | 100 |
| Quality vehicles | 500 |
| Dedupe scenarios | 200 |

### 15.2. Golden outputs

```json
{
  "fixture_id": "e01_de_bmw_001",
  "expected_vehicle_count": 23,
  "required_fields": {
    "make": 0.99,
    "model": 0.98,
    "price": 0.97,
    "source_url": 1.0
  },
  "known_missing": ["vin"],
  "notes": "Dealer does not publish VIN"
}
```

### 15.3. Policy

Every production bug becomes:

1. issue;
2. fixture;
3. failing test;
4. fix;
5. regression test.

### 15.4. Definition of Done

- Offline deterministic tests.
- Fixture coverage by country/strategy.
- CI blocks regression.
- Parser accuracy tracked over time.

---

## 16. Bloque M — Seguridad y supply chain

### 16.1. CI gates

- govulncheck all Go modules;
- npm audit policy for frontend;
- pip-audit for Python requirements;
- gitleaks;
- go mod verify;
- SBOM generation;
- illegal pattern scan;
- User-Agent scan;
- license scan.

### 16.2. Runtime hardening

- systemd hardening;
- non-root services;
- read-only paths where possible;
- firewall;
- fail2ban;
- Caddy rate limiting;
- secrets via age/systemd-creds;
- backup encryption;
- restore drills.

### 16.3. Definition of Done

- 0 known critical CVEs.
- 0 secrets in repo.
- SBOM produced per release.
- Restore tested twice.
- Security incident runbook exists.

---

## 17. Bloque N — Go-to-market funcional

### 17.1. Qué no atacar primero

No competir inicialmente como:

- B2C marketplace;
- sustituto directo de mobile.de;
- sustituto directo de AutoScout24;
- historial tipo Carfax sin acuerdos;
- herramienta genérica de CRM para todos.

### 17.2. Qué atacar primero

Atacar:

- buyers B2B cross-border;
- traders medianos;
- exportadores;
- flotas pequeñas;
- dealers que buscan sourcing;
- compradores que hoy trabajan con Excel;
- long-tail stock;
- oportunidades de margen bajo radar.

### 17.3. Producto inicial vendible

```text
CARDEX Pro Sourcing:
Inventario europeo deduplicado + alertas de margen + risk check + API/export.
```

### 17.4. Métrica reina

```text
buyer_margin_discovered_eur_per_month
```

Submétricas:

- oportunidades vistas;
- oportunidades guardadas;
- dealers contactados;
- deals iniciados;
- margen estimado;
- margen realizado;
- tiempo ahorrado;
- false positives.

### 17.5. Definition of Done

- 10 usuarios B2B activos.
- 3 meses de uso continuo.
- NPS medido.
- Margen descubierto medido.
- Feedback loop semanal.

---

## 18. Roadmap por fases

### Fase 1 — 0 a 30 días: limpiar y medir

Objetivo: eliminar incertidumbre básica.

Entregables:

- compliance audit;
- source legal registry;
- kill-switch;
- robots decision log;
- E07 no-op alert;
- extraction metrics;
- freshness base;
- fixture corpus inicial;
- dead-letter dashboard;
- API health;
- legal runbook.

Resultado esperado:

- scraping/extraction pasa de sistema prometedor a sistema medible;
- riesgos grises visibles o apagados;
- se deja de hablar de cobertura estimada sin datos.

### Fase 2 — 31 a 60 días: cobertura real en país piloto

Objetivo: demostrar stock real.

Entregables:

- país piloto seleccionado;
- 1.000+ dealers medidos;
- E01-E09 success rate real;
- E07 real;
- E10 alpha;
- E11 piloto;
- canonical vehicle v1;
- dedupe v1;
- price history;
- sold detection v2;
- opportunity score v1.

Resultado esperado:

- cobertura real demostrada;
- pipeline empieza a generar oportunidades útiles.

### Fase 3 — 61 a 90 días: producto B2B vendible

Objetivo: que compradores reales lo usen.

Entregables:

- Search API v1;
- Vehicle detail API;
- Risk report;
- Watchlists;
- Alerts;
- CSV/export;
- comparables;
- 5 buyers piloto;
- feedback loop;
- realized vs estimated margin tracking.

Resultado esperado:

- CARDEX deja de ser plataforma técnica y se convierte en herramienta de sourcing.

### Fase 4 — 91 a 180 días: expansión institucional

Objetivo: 6 países con estándares medibles.

Entregables:

- denominadores por país;
- coverage dashboards;
- confidence model v2;
- ownership history;
- dedupe v2;
- Check legal integrations roadmap;
- Workspace connected flows;
- SLOs;
- restore drills;
- legal audit;
- 20-50 usuarios B2B.

Resultado esperado:

- plataforma europea seria.

### Fase 5 — 181 a 365 días: moat 13/10

Objetivo: ventaja difícil de copiar.

Entregables:

- Edge dealer network;
- API ecosystem;
- opportunity engine backtested;
- buyer workflows diarios;
- DMS integrations;
- proprietary historical data;
- dealer trust score real;
- public coverage benchmark;
- legal data agreements;
- recurring revenue.

Resultado esperado:

- CARDEX no solo compite: crea una categoría B2B diferenciada.

---

## 19. Backlog atómico 100 tickets

### Compliance

1. `audit-user-agents`
2. `remove-browser-ua-from-active-crawlers`
3. `source-legal-registry-schema`
4. `robots-decision-log-schema`
5. `source-kill-switch-schema`
6. `legal-incident-log-schema`
7. `ci-block-non-cardex-ua`
8. `ci-block-evasion-patterns`
9. `field-provenance-required`
10. `cease-and-desist-runbook`

### Extraction

11. `wire-real-playwright-interceptor`
12. `e07-prod-noop-alert`
13. `e07-fixture-corpus`
14. `e10-imap-reader`
15. `e10-attachment-parser`
16. `e08-pdf-table-extractor-v2`
17. `e09-csv-dialect-detection`
18. `strategy-circuit-breakers`
19. `domain-auto-throttling`
20. `extraction-success-dashboard`

### Discovery

21. `market-denominator-schema`
22. `country-coverage-dashboard`
23. `dealer-entity-resolution-v2`
24. `domain-ownership-history`
25. `confidence-model-v2`
26. `duplicate-dealer-detector`
27. `dealer-group-detection`
28. `discovery-saturation-report`
29. `source-reliability-score`
30. `dead-domain-recovery`

### Vehicle identity

31. `canonical-vehicle-table`
32. `listing-observation-table`
33. `vin-dedupe`
34. `plate-dedupe-where-legal`
35. `fuzzy-dedupe`
36. `merge-explainability`
37. `manual-split-workflow`
38. `price-history-events`
39. `mileage-history-events`
40. `photo-hash-dedupe-where-allowed`

### Quality

41. `data-quality-score`
42. `commercial-score`
43. `risk-score`
44. `field-confidence-json`
45. `conflict-resolution-engine`
46. `manual-review-priority`
47. `quality-feedback-loop`
48. `validator-regression-fixtures`
49. `freshness-score`
50. `sold-status-v2`

### Check

51. `country-source-matrix`
52. `check-legal-mode-only`
53. `rapex-eu-integration-hardening`
54. `ncap-cache-and-versioning`
55. `rdw-nl-v2`
56. `dgt-legal-path`
57. `car-pass-be-contract-path`
58. `histovec-fr-access-path`
59. `check-risk-decision`
60. `check-evidence-rendering`

### API/Product

61. `openapi-spec`
62. `search-api-v1`
63. `vehicle-detail-api-v1`
64. `dealer-api-v1`
65. `opportunity-api-v1`
66. `webhooks-v1`
67. `bulk-export-v1`
68. `api-keys-scopes`
69. `tenant-rate-limits`
70. `sdk-examples`

### Workspace

71. `vehicle-to-deal-flow`
72. `deal-to-document-flow`
73. `deal-to-finance-flow`
74. `inbox-to-deal-linking`
75. `kanban-automation`
76. `workspace-audit-log`
77. `roles-permissions`
78. `dealer-edge-settings-ui`
79. `syndication-status-sync`
80. `pnl-realized-vs-estimated`

### Intelligence

81. `comparables-engine`
82. `market-median-by-cohort`
83. `liquidity-score`
84. `opportunity-score`
85. `route-margin-calculator`
86. `transport-cost-calibration`
87. `tax-cost-calibration`
88. `price-drop-alerts`
89. `dealer-stress-signals`
90. `backtest-opportunities`

### SRE/Security

91. `slo-dashboard`
92. `synthetic-extraction-test`
93. `backup-restore-drill`
94. `failover-runbook`
95. `sbom-generation`
96. `gitleaks-ci`
97. `govulncheck-all-modules`
98. `npm-audit-policy`
99. `incident-command-center`
100. `ops-weekly-report`

---

## 20. Orden de ejecución recomendado

No ejecutar por orden numérico. Ejecutar por desbloqueo de riesgo.

### Prioridad P0 — antes de crecer

1. Compliance audit.
2. Source legal registry.
3. Kill-switch.
4. E07 no-op alert.
5. Extraction metrics.
6. Dead-letter dashboard.
7. User-Agent CI hardening.
8. Robots decision log.

### Prioridad P1 — cobertura funcional real

1. E07 real.
2. Country pilot.
3. Fixture corpus.
4. Canonical vehicle.
5. Dedupe v1.
6. Freshness SLA.
7. Sold detection v2.
8. Search API.

### Prioridad P2 — valor comercial

1. Comparables engine.
2. Opportunity score.
3. Risk score.
4. Watchlists.
5. Alerts.
6. CSV/API export.
7. Buyer pilots.
8. Margin tracking.

### Prioridad P3 — moat

1. Edge dealer network.
2. Workspace full flow.
3. Check legal integrations.
4. Confidence model v2.
5. Ownership history.
6. API ecosystem.
7. Backtesting.
8. Public coverage benchmark.

---

## 21. Criterio final de 13/10

CARDEX alcanza 13/10 cuando se pueden afirmar simultáneamente estas frases con evidencia:

1. Tenemos 6 países medidos, no supuestos.
2. Cada dato crítico tiene fuente, timestamp y confidence.
3. Cada fuente está legalmente clasificada.
4. Cada extractor tiene success rate real.
5. Los fallos de extracción se detectan en minutos.
6. Los vehículos están deduplicados canónicamente.
7. El usuario ve oportunidades, no solo listados.
8. El riesgo de compra está explicado.
9. La freshness se mide por SLA.
10. La API se integra en menos de un día.
11. Workspace conecta el ciclo comercial completo.
12. Los buyers reales encuentran margen medible.
13. El sistema es más útil unido que cualquier combinación manual de portales y Excel.

---

## 22. Resumen ejecutivo

El camino al 13/10 no es aumentar complejidad: es aumentar verificabilidad.

La secuencia correcta es:

```text
Legalidad → Medición → Cobertura → Identidad canónica → Freshness → Quality/Risk → API → Opportunity → Workspace → Usuarios reales → Margen demostrado
```

Sin usuarios reales, CARDEX puede llegar a 9 técnico.  
Con usuarios reales, datos frescos, dedupe fuerte, compliance limpio y margen demostrado, CARDEX puede convertirse en 13 funcional.
