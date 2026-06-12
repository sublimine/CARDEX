# AUDITORÍA EXHAUSTIVA DE ENTREGABLES — CARDEX Fase Cero

**Fecha:** 2026-06-05
**Autor:** Auditoría estratégica automatizada
**Contexto verificado contra:** `CONTEXT_FOR_AI.md` (2026-04-15), `STATUS.md` (2026-04-27), codebase real, `SPEC.md` (visión sellada)

---

## REALIDAD VERIFICADA DE CARDEX (base de la auditoría)

Antes de evaluar cualquier entregable, la verdad operativa:

- **Infraestructura desplegada:** 1x Hetzner CX42 (~€22/mes), SQLite WAL, 3 servicios Go (discovery/extraction/quality), Docker Compose + Caddy + Prometheus/Grafana
- **Scraper fleet:** 84 directorios de portal en `scrapers/portals/`, stack Strategy B (curl_cffi + Camoufox + proxies residenciales). Motor de scraping diseñado pero pendiente de implementación completa (`scrapers/engine/`)
- **Pipeline real:** 15 familias de discovery, 14 estrategias de extracción, 21 validadores de calidad. 1.55M vehículos indexados (snapshot 2026-04-10)
- **Innovation:** 3 servicios experimentales (GNN, RAG, Chronos forecasting) — no desplegados en producción
- **Frontend:** Dashboard React PWA en `workspace/web/` (construido, no desplegado). B2B dashboard Next.js (construido, no desplegado)
- **Lo que NO existe:** PostgreSQL, Redis, ClickHouse, MeiliSearch, microservicios, multi-nodo, frontend público, Chrome extension, B2B webhooks, motor financiero, motor fiscal
- **Presupuesto:** €300/mes TOTAL
- **Equipo:** 1 fundador + AI
- **Contactos comerciales:** cero
- **Financiación:** cero
- **Revenue:** cero

---

## TABLA RESUMEN DE VEREDICTOS

| # | Entregable | Potencia | Factibilidad | Veredicto | Prioridad |
|---|-----------|----------|-------------|-----------|-----------|
| 1 | Investor pitch deck | Media | Baja | NO ENTRA | — |
| 2 | Financial model Excel | Media | Media | ENTRA CON MODIFICACIONES | P3 |
| 3 | Product roadmap feature planning | Media | Alta | ENTRA CON MODIFICACIONES | P2 |
| 4 | B2B dealer sales playbook | Alta | Baja | NO ENTRA | — |
| 5 | SEO marketing go-to-market | Baja | Media | NO ENTRA | — |
| 6 | Customer success retention | Baja | Nula | NO ENTRA | — |
| 7 | GDPR compliance vehicle data | Alta | Alta | ENTRA | P1 |
| 8 | Risk management continuity plan | Media | Alta | ENTRA CON MODIFICACIONES | P4 |
| 9 | Operations runbook | Alta | Alta | ENTRA | P1 |
| 10 | Developer onboarding docs | Media | Alta | ENTRA CON MODIFICACIONES | P5 |
| 11 | API design OpenAPI spec | Alta | Alta | ENTRA | P2 |
| 12 | Vehicle data normalization framework | Alta | Alta | ENTRA | P1 |
| 13 | Partnership integration strategy | Media | Baja | NO ENTRA | — |
| 14 | Monetization strategy deep analysis | Alta | Media | ENTRA CON MODIFICACIONES | P2 |
| 15 | European vehicle pricing intelligence | Alta | Alta | ENTRA | P1 |
| 16 | Infrastructure architecture doc | Alta | Alta | ENTRA | P1 |
| 17 | OPENLANE deep ecosystem audit | Alta | Alta | ENTRA | P2 |
| 18 | AUTO1 Group deep audit | Alta | Alta | ENTRA | P2 |
| 19 | Autorola + Indicata deep audit | Alta | Alta | ENTRA | P2 |
| 20 | CarOnSale deep audit | Alta | Alta | ENTRA | P2 |
| 21 | Indirect competitors ecosystem map | Alta | Alta | ENTRA | P3 |
| 22 | Automotive data intelligence deep | Alta | Alta | ENTRA | P1 |
| 23 | Anti-detection systems research | Alta | Alta | ENTRA | P1 |

**Resumen:** 18 ENTRA (13 directos + 5 con modificaciones) / 5 NO ENTRA

---

## ANÁLISIS DETALLADO POR ENTREGABLE

---

### 1. CARDEX Investor Pitch Deck

**Tipo:** Presentación PPTX
**Propósito declarado:** Atraer inversión para CARDEX

**Evaluación:**

- **Potencia real:** Media. Un pitch deck es esencial para fundraising, pero CARDEX no está en posición de levantar ronda. Sin tracción (cero revenue, cero usuarios), sin equipo, sin métricas de producto — ningún inversor serio mira un deck sin estas tres cosas. El deck es prematuro.
- **Beneficio para CARDEX hoy:** Nulo. No hay pipeline de inversores, no hay warm intros, no hay red de VCs. Un deck frío enviado a info@vc.com tiene un conversion rate de <0.1%.
- **Beneficio para el mercado:** Nulo. No posiciona competitivamente. Los competidores (AUTO1, Autorola, CarOnSale) no se intimidan con slides.
- **Factibilidad:** Baja. Crear el deck es trivial, pero usarlo requiere acceso a inversores que no existe. El coste de oportunidad es alto: horas dedicadas a pulir slides que nadie verá.

**VEREDICTO: NO ENTRA**

**Razón:** Prematuro. Fundraising requiere: (1) tracción demostrable, (2) acceso a inversores, (3) equipo que inspire confianza. CARDEX tiene 0/3. El deck debe crearse DESPUÉS de demostrar revenue recurrente, aunque sea €500/mes. Guarda el contenido como borrador mental; no lo pulas hasta tener tracción.

---

### 2. CARDEX Financial Model Excel

**Tipo:** Spreadsheet XLSX
**Propósito declarado:** Proyecciones financieras, unit economics, escenarios de crecimiento

**Evaluación:**

- **Potencia real:** Media. Un modelo financiero disciplinado es valioso para tomar decisiones, pero solo si refleja la realidad. Si asume ingresos por suscripciones SaaS a 6 meses, es ficción. Si modela costes reales (€22 VPS + proxies + dominio) y escenarios de revenue realistas, es útil.
- **Beneficio para CARDEX hoy:** Condicional. Si el modelo incluye burn rate real, runway con €300/mes, y escenarios de primera venta, sí aporta. Si proyecta ARR de €500K a 18 meses sin base empírica, es humo.
- **Factibilidad:** Media. El modelo existe, pero necesita rediseño radical.

**VEREDICTO: ENTRA CON MODIFICACIONES**

**Modificaciones requeridas:**
1. Eliminar toda proyección que asuma equipo >1 persona en los próximos 6 meses
2. Modelar escenarios de primera venta: ¿cuántos dealers necesitan pagar cuánto para cubrir €300/mes?
3. Incluir coste real de proxies (Decodo/Oxylabs ≈ €50-150/mes según volumen), VPS, dominio
4. Agregar escenario "ramen profitability": revenue mínimo para cubrir costes operativos sin margen
5. Eliminar proyecciones de contratación y oficinas

---

### 3. Product Roadmap Feature Planning

**Tipo:** Documento de planificación
**Propósito declarado:** Roadmap de funcionalidades futuras

**Evaluación:**

- **Potencia real:** Media. Un roadmap es útil para priorizar, pero en fase cero la prioridad es una sola: generar revenue. Si el roadmap lista 50 features sin una jerarquía brutal centrada en monetización, distrae.
- **Beneficio para CARDEX hoy:** Condicional. CARDEX tiene infraestructura técnica avanzada (15 familias discovery, 21 validadores, 84 scrapers). Lo que falta es el puente entre esa infraestructura y el primer euro. El roadmap debe reflejar ese gap.
- **Factibilidad:** Alta.

**VEREDICTO: ENTRA CON MODIFICACIONES**

**Modificaciones requeridas:**
1. Reducir a 3 fases: (a) MVP vendible (próximos 30 días), (b) Producto mejorado (60-90 días), (c) Escala (6+ meses)
2. Cada feature debe responder: "¿esto genera revenue o reduce churn?" — si la respuesta es no, sale del roadmap fase-cero
3. Prioridad absoluta: API de datos o dashboard que un dealer pueda pagar HOY
4. Eliminar features de Series A (multi-tenant, SIP gateway, WASM terminal, Karma system)

---

### 4. B2B Dealer Sales Playbook

**Tipo:** Documento de ventas
**Propósito declarado:** Guía para vender a concesionarios

**Evaluación:**

- **Potencia real:** Alta en teoría, pero irrelevante sin contexto. Un playbook de ventas asume: equipo de ventas, CRM, pipeline de leads, pricing establecido, producto probado. CARDEX no tiene nada de esto.
- **Beneficio para CARDEX hoy:** Nulo. El fundador no puede hacer cold outreach a scale sin automatización. Un playbook para una persona no necesita un documento — necesita 10 dealers target, un email, y un teléfono.
- **Factibilidad:** Baja. Asume capacidades de go-to-market que no existen.

**VEREDICTO: NO ENTRA**

**Razón:** Prematuro. Lo que necesita el fundador es una lista de 10-20 dealers target en un mercado específico (p.ej. concesionarios de multimarca en NRW, Alemania) y un email template personalizado. No un playbook de 30 páginas. Cuando haya 3 clientes pagando, entonces se formaliza el proceso.

---

### 5. SEO Marketing Go-to-Market Strategy

**Tipo:** Documento de estrategia
**Propósito declarado:** Posicionamiento orgánico y captación de tráfico

**Evaluación:**

- **Potencia real:** Baja. SEO es un juego de 6-18 meses. CARDEX no tiene frontend público desplegado. No tiene blog. No tiene dominio con autoridad. SEO orgánico contra competidores como mobile.de (DA 90+), AutoScout24, o Coches.net es irrelevante en fase cero.
- **Beneficio para CARDEX hoy:** Nulo. El producto es B2B, no B2C. Los dealers no buscan "vehicle data API" en Google. Se les vende por relación directa, referral, o en ferias del sector.
- **Factibilidad:** Media técnicamente, pero el ROI en fase cero es cero.

**VEREDICTO: NO ENTRA**

**Razón:** Misallocation of resources. SEO para B2B automotive intelligence es un canal de Series A+. En fase cero, el canal es: LinkedIn outreach directo al decision maker del concesionario, participación en foros como Motor-Talk.de, y presencia en ferias sectoriales (Automechanika, AutoZum). Ninguno requiere un documento de estrategia SEO.

---

### 6. Customer Success Retention Framework

**Tipo:** Framework operativo
**Propósito declarado:** Retención de clientes

**Evaluación:**

- **Potencia real:** Baja. Customer success es crítico cuando tienes clientes. CARDEX tiene cero.
- **Beneficio para CARDEX hoy:** Nulo. No se puede retener lo que no se tiene.
- **Factibilidad:** Nula en la práctica.

**VEREDICTO: NO ENTRA**

**Razón:** Completamente prematuro. Customer success framework se construye DESPUÉS de tener 10+ clientes pagando y entender sus patrones de uso y churn. Crear un framework teórico de retención sin clientes es ejercicio académico. Cuando el primer cliente haga churn, ese dolor enseñará más que cualquier documento.

---

### 7. GDPR Compliance Vehicle Data

**Tipo:** Documento legal/técnico
**Propósito declarado:** Cumplimiento RGPD para datos de vehículos

**Evaluación:**

- **Potencia real:** Alta. CARDEX scrapea datos de 84+ portales en 6 países de la UE. El RGPD no es opcional. Un scraper que procesa datos de dealers (nombre, teléfono, dirección, VAT ID) SIN cumplimiento RGPD documentado es una bomba legal. Las multas son hasta 4% del revenue global o €20M — en el caso de CARDEX, la multa mínima seguiría siendo devastadora.
- **Beneficio para CARDEX hoy:** Directo. Protege al fundador legalmente. Cualquier dealer que pregunte "¿cómo manejan mis datos?" necesita una respuesta documentada, no improvisada.
- **Beneficio para el mercado:** Alto. Demuestra profesionalidad ante potenciales clientes B2B que operan en jurisdicciones estrictas (DE, NL).
- **Factibilidad:** Alta. Es documentación + configuración. No requiere presupuesto adicional.

**VEREDICTO: ENTRA**

**Prioridad: P1**

**Acción:** Verificar que cubre: (1) base legal del scraping (interés legítimo vs. consentimiento), (2) política de retención de datos, (3) procedimiento de derecho de supresión (Art. 17), (4) registro de actividades de tratamiento (Art. 30), (5) evaluación de impacto (DPIA) para scraping masivo, (6) posición sobre datos de vehículos vs. datos personales de dealers.

---

### 8. Risk Management Continuity Plan

**Tipo:** Documento operativo
**Propósito declarado:** Gestión de riesgos y continuidad del negocio

**Evaluación:**

- **Potencia real:** Media. Un plan de continuidad es importante, pero para una startup de una persona con un VPS, la continuidad es: "si el VPS muere, restauro backup en otro VPS". La complejidad es baja.
- **Beneficio para CARDEX hoy:** Moderado. El riesgo real en fase cero no es la caída de un servidor — es: (a) ser demandado por un portal scrapeado, (b) que los proxies se bloqueen en cadena, (c) que el fundador se queme. Esos riesgos no los cubre un BCP tradicional.
- **Factibilidad:** Alta.

**VEREDICTO: ENTRA CON MODIFICACIONES**

**Modificaciones requeridas:**
1. Eliminar escenarios de multi-nodo, failover de cluster, disaster recovery empresarial
2. Centrar en riesgos REALES de fase cero: riesgo legal de scraping (C&D letters), riesgo de bloqueo de proxies, riesgo de dependencia de proveedor único (Hetzner), riesgo de burnout del fundador
3. Incluir playbook de respuesta a C&D (cease and desist) de un portal
4. Incluir plan de migración rápida si Hetzner cierra la cuenta
5. Documentar backup/restore actual (que ya existe en `deploy/scripts/backup.sh`)

---

### 9. Operations Runbook CARDEX

**Tipo:** Documento operativo
**Propósito declarado:** Procedimientos operativos del sistema

**Evaluación:**

- **Potencia real:** Alta. CARDEX tiene un sistema complejo: 3 servicios Go + fleet de scrapers + Docker Compose + Prometheus + Caddy + SQLite. Sin runbook, si algo falla a las 3 AM, el fundador reconstruye de memoria. Con `STATUS.md` listando TECH-004 (runbooks no formalizados) como deuda técnica, este entregable ataca una necesidad real.
- **Beneficio para CARDEX hoy:** Directo. Ya existe `deploy/runbook.md` (12 pasos de provisioning) y `deploy/incident-runbooks/`, pero la cobertura es incompleta. El entregable complementa lo existente.
- **Factibilidad:** Alta. Es documentación sobre infraestructura que ya está operativa.

**VEREDICTO: ENTRA**

**Prioridad: P1**

**Acción:** Verificar que cubre: (1) deploy from scratch del CX42, (2) restore de backup SQLite, (3) restart de servicios tras crash, (4) rotación de proxies, (5) qué hacer cuando un scraper falla en cadena, (6) monitoring — qué alertas existen y qué hacer con cada una (las 8 alertas de Alertmanager).

---

### 10. Developer Onboarding Technical Docs

**Tipo:** Documentación técnica
**Propósito declarado:** Onboarding de nuevos desarrolladores

**Evaluación:**

- **Potencia real:** Media. No hay desarrolladores que onboardear. El equipo es el fundador + AI. Sin embargo, la documentación técnica bien hecha facilita el trabajo con AI y reduce el coste de contexto en cada sesión.
- **Beneficio para CARDEX hoy:** Moderado. CONTEXT_FOR_AI.md ya sirve como onboarding para AI. ARCHITECTURE.md documenta el pipeline. El valor marginal de un onboarding doc adicional es limitado si los existentes están bien.
- **Factibilidad:** Alta.

**VEREDICTO: ENTRA CON MODIFICACIONES**

**Modificaciones requeridas:**
1. Renombrar mentalmente: no es "developer onboarding" — es "AI context optimization"
2. Verificar que no duplica CONTEXT_FOR_AI.md y ARCHITECTURE.md
3. Valor real: documentar los GAPS que CONTEXT_FOR_AI.md no cubre (p.ej. cómo correr el scraper fleet end-to-end, cómo interpretar las métricas de Grafana, cómo debuggear un scraper específico)
4. Si duplica los docs existentes: eliminar

---

### 11. CARDEX API Design OpenAPI Spec

**Tipo:** Especificación técnica
**Propósito declarado:** Diseño de API para acceso a datos CARDEX

**Evaluación:**

- **Potencia real:** Alta. Si CARDEX va a monetizar, necesita exponer datos a través de una API. Una spec OpenAPI es el artefacto que convierte "tenemos datos" en "tenemos un producto vendible". Es el puente entre infraestructura y revenue.
- **Beneficio para CARDEX hoy:** Directo y crítico. Sin API definida, no hay producto. Con spec OpenAPI, se puede: (a) generar documentación interactiva (Swagger UI), (b) generar SDKs para clientes, (c) definir pricing por endpoint/llamada, (d) mostrar a un dealer potencial exactamente qué datos obtiene.
- **Beneficio para el mercado:** Alto. Demuestra madurez técnica ante potenciales clientes e integradores.
- **Factibilidad:** Alta. Los datos existen en SQLite, los servicios Go ya exponen HTTP. Definir la spec es trabajo de diseño, no de infraestructura nueva.

**VEREDICTO: ENTRA**

**Prioridad: P2**

**Acción:** Asegurar que la spec define: (1) endpoints de búsqueda de vehículos (por marca, modelo, país, precio), (2) endpoint de detalle de vehículo, (3) endpoint de estadísticas de mercado (precio medio, volumen, tendencias), (4) autenticación (API key), (5) rate limiting, (6) pricing model por llamada. La spec ES el producto.

---

### 12. Vehicle Data Normalization Framework

**Tipo:** Framework técnico
**Propósito declarado:** Normalización de datos de vehículos de múltiples fuentes

**Evaluación:**

- **Potencia real:** Alta. CARDEX extrae datos de 84+ portales con formatos heterogéneos. Un BMW Serie 3 aparece como "BMW 3er", "BMW Serie 3", "BMW 3-Series", "BMW 320d", etc. Sin normalización, los datos son ruido. Con normalización, son inteligencia de mercado.
- **Beneficio para CARDEX hoy:** Directo. La calidad de los datos ES el producto. Si un dealer consulta "BMW Serie 3, <50.000 km, <€25.000, Alemania" y obtiene basura mal normalizada, no vuelve. V04 (NLP make/model) y V12 (cross-source dedup) ya atacan esto parcialmente. El framework documenta y amplía la lógica.
- **Factibilidad:** Alta. Extensión de lo que ya existe en `quality/internal/validator/`.

**VEREDICTO: ENTRA**

**Prioridad: P1**

**Acción:** Verificar cobertura de: (1) taxonomía canónica de marcas/modelos (make → canonical_make), (2) normalización de colores (6 idiomas → código estándar), (3) normalización de combustible/transmisión, (4) conversión de unidades (millas→km, libras→EUR), (5) deduplicación cross-portal.

---

### 13. Partnership Integration Strategy Doc

**Tipo:** Documento de estrategia
**Propósito declarado:** Estrategia de partnerships e integraciones

**Evaluación:**

- **Potencia real:** Media. Los partnerships son valiosos, pero requieren leverage negociador. CARDEX sin revenue, sin usuarios, sin marca, sin red de contactos no tiene nada que ofrecer a un partner. Un documento de estrategia de partnerships sin el poder para ejecutarlo es decoración.
- **Beneficio para CARDEX hoy:** Nulo. ¿Quién va a hacer partnership con una startup sin tracción? Los DMS (Incadea, MotorManager) no responden emails fríos de empresas sin clientes. Las casas de subasta (BCA, Manheim) no integran APIs de startups sin volumen.
- **Factibilidad:** Baja. El documento puede existir; la ejecución, no.

**VEREDICTO: NO ENTRA**

**Razón:** Prematuro. Los partnerships se forman cuando: (a) tienes algo que el partner necesita (datos únicos, distribución, tecnología), (b) puedes demostrar tracción. CARDEX tiene (a) parcialmente (datos de 6 países), pero sin (b) nadie contesta el email. Guárdalo como roadmap de relaciones, pero no inviertas tiempo en pulirlo.

---

### 14. Monetization Strategy Deep Analysis

**Tipo:** Análisis estratégico
**Propósito declarado:** Definición del modelo de negocio y monetización

**Evaluación:**

- **Potencia real:** Alta. Esta es posiblemente la pregunta más importante de fase cero: ¿cómo conviertes datos de vehículos en euros? Si el análisis explora modelos realistas (API-as-a-Service por llamada, dashboard de suscripción, data feeds B2B), es el documento más valioso del lote.
- **Beneficio para CARDEX hoy:** Directo. Sin modelo de monetización claro, no hay negocio. Es pre-requisito para todo lo demás.
- **Factibilidad:** Media. El análisis puede existir, pero la factibilidad de cada modelo depende de la capacidad de ejecución.

**VEREDICTO: ENTRA CON MODIFICACIONES**

**Modificaciones requeridas:**
1. Eliminar modelos que requieran licencia financiera (créditos computacionales con caducidad per SPEC.md es smart pero complejo regulatoriamente)
2. Priorizar modelos ejecutables por 1 persona: (a) API de datos de mercado con pricing por llamada (Stripe metered billing), (b) reportes de pricing por marca/modelo/país (PDF automatizado, €50-200/reporte), (c) alertas de oportunidad de arbitraje (email/webhook, suscripción mensual)
3. Validar con 5 dealers reales antes de construir: ¿pagarían por esto? ¿cuánto?
4. Incluir modelo freemium: X llamadas gratis → paid tier

---

### 15. European Vehicle Pricing Intelligence

**Tipo:** Análisis de inteligencia de mercado
**Propósito declarado:** Inteligencia de precios de vehículos europeos

**Evaluación:**

- **Potencia real:** Alta. CARDEX tiene 1.55M vehículos indexados de 6 países. Convertir esos datos en inteligencia de pricing (precio medio por make/model/year/country, tendencias, arbitraje cross-border) es el CORE VALUE PROPOSITION. Esto no es un entregable — es el producto.
- **Beneficio para CARDEX hoy:** Directo. Este análisis demuestra que los datos de CARDEX tienen valor comercial. Es la prueba de concepto que se puede mostrar a un dealer: "mira, un BMW 320d 2020 en DE cuesta €22.500 de media, en ES €24.800 — hay un arbitraje de €2.300".
- **Factibilidad:** Alta. Los datos están. Chronos forecasting (innovation service) puede amplificar el análisis.

**VEREDICTO: ENTRA**

**Prioridad: P1**

**Acción:** Este documento debería ser el demo que se enseña a los primeros prospects. Convertirlo en un sample report interactivo o PDF ejecutivo que demuestre el valor de los datos de CARDEX.

---

### 16. CARDEX Infrastructure Architecture Doc

**Tipo:** Documentación técnica
**Propósito declarado:** Documentación de la arquitectura de infraestructura

**Evaluación:**

- **Potencia real:** Alta. Ya existe `ARCHITECTURE.md` y `docs/INFRASTRUCTURE.md`. Si este entregable complementa o consolida, aporta. La infraestructura real (CX42, Docker, Caddy, Prometheus, SQLite) necesita documentación actualizada — no la visión aspiracional (3x AX102, PostgreSQL, ClickHouse).
- **Beneficio para CARDEX hoy:** Directo. Reduce el bus factor de 1. Si el fundador enferma, un tercero (o una AI) puede operar el sistema con documentación completa.
- **Factibilidad:** Alta. Documentar lo que existe.

**VEREDICTO: ENTRA**

**Prioridad: P1**

**Acción:** Verificar que refleja la realidad (SQLite, no PostgreSQL). Debe estar alineado con `CONTEXT_FOR_AI.md`, no con `SPEC.md`. Si describe la visión aspiracional en vez de la realidad, necesita rewrite.

> *(Corrección 2026-06-12: la premisa "la realidad = SQLite, no PostgreSQL" quedó invalidada — el almacén vivo es **PostgreSQL 16** y el pipeline vivo es la flota Python; `CONTEXT_FOR_AI.md` fue eliminado por stale. Alinear con `README.md` + `STATUS.md`.)*

---

### 17. OPENLANE Deep Ecosystem Audit

**Tipo:** Investigación competitiva
**Propósito declarado:** Análisis profundo del ecosistema OPENLANE (KAR Global → OPENLANE)

**Evaluación:**

- **Potencia real:** Alta. OPENLANE es el mayor ecosistema B2B de remarketing de vehículos en Europa (post-adquisición de TradePlace, ADESA Europe). Entender cómo operan, sus APIs, su pricing, sus debilidades, y dónde CARDEX puede ofrecer algo que ellos no — es inteligencia competitiva pura.
- **Beneficio para CARDEX hoy:** Directo. Permite posicionar CARDEX en los gaps de OPENLANE. Si OPENLANE cobra €X por inspección y CARDEX puede ofrecer validación automatizada gratuita, eso es una cuña de entrada.
- **Factibilidad:** Alta. Es research, no requiere presupuesto.

**VEREDICTO: ENTRA**

**Prioridad: P2**

---

### 18. AUTO1 Group Deep Audit

**Tipo:** Investigación competitiva
**Propósito declarado:** Análisis profundo de AUTO1 Group (wirkaufendeinauto.de, Autohero)

**Evaluación:**

- **Potencia real:** Alta. AUTO1 es el mayor player B2B/B2C de vehículos usados en Europa. Market cap >€2B. Entiende el mercado. Sus reportes anuales, sus márgenes, su churn de dealers, su pricing — todo es inteligencia accionable.
- **Beneficio para CARDEX hoy:** Directo. AUTO1 publica datos en sus earnings calls que revelan: márgenes por vehículo, costes de adquisición, tiempo medio en inventario. Esos datos calibran las proyecciones de CARDEX.
- **Factibilidad:** Alta.

**VEREDICTO: ENTRA**

**Prioridad: P2**

---

### 19. Autorola + Indicata Deep Audit

**Tipo:** Investigación competitiva
**Propósito declarado:** Análisis profundo de Autorola (subastas B2B online) e Indicata (analytics arm de Autorola)

**Evaluación:**

- **Potencia real:** Alta. Indicata es el competidor más directo de CARDEX en pricing intelligence. Su producto "Indicata Market Watch" hace exactamente lo que CARDEX quiere hacer: pricing analytics para dealers. Entender sus features, pricing, gaps, y limitaciones es CRÍTICO.
- **Beneficio para CARDEX hoy:** Directo. Indicata cobra €300-600/mes por su dashboard. Si CARDEX puede ofrecer datos comparables o complementarios a menor precio, hay mercado validado.
- **Factibilidad:** Alta.

**VEREDICTO: ENTRA**

**Prioridad: P2**

**Acción:** Usar este audit para definir el pricing de CARDEX. Si Indicata cobra €X, CARDEX se posiciona en €X/3 o complementario.

---

### 20. CarOnSale Deep Audit

**Tipo:** Investigación competitiva
**Propósito declarado:** Análisis profundo de CarOnSale (subastas B2B de vehículos)

**Evaluación:**

- **Potencia real:** Alta. CarOnSale es una startup B2B de subastas de vehículos con presencia en DE, NL, BE. Su modelo (comisión por transacción) y su stack tecnológico son relevantes. Su fundraising history (Series A, B) revela qué valoran los inversores en este espacio.
- **Beneficio para CARDEX hoy:** Directo como benchmark.
- **Factibilidad:** Alta.

**VEREDICTO: ENTRA**

**Prioridad: P2**

---

### 21. Indirect Competitors Ecosystem Map

**Tipo:** Investigación competitiva
**Propósito declarado:** Mapeo del ecosistema de competidores indirectos

**Evaluación:**

- **Potencia real:** Alta. Más allá de los competidores directos (plataformas de subastas B2B), hay un ecosistema de players indirectos: DAT/Schwacke (valuaciones), TecAlliance (datos técnicos), Eurotax (benchmarking), FleetLogistics (gestión de flotas). Entender quién hace qué evita construir algo que ya existe y revela oportunidades de integración.
- **Beneficio para CARDEX hoy:** Moderado-alto. Evita invertir en features que un player establecido ya ofrece gratis o barato.
- **Factibilidad:** Alta.

**VEREDICTO: ENTRA**

**Prioridad: P3**

---

### 22. Automotive Data Intelligence Deep

**Tipo:** Investigación estratégica
**Propósito declarado:** Análisis profundo del sector de inteligencia de datos automotriz

**Evaluación:**

- **Potencia real:** Alta. Entiende el mercado total addressable: quién compra datos de vehículos, por qué, cuánto pagan, y qué falta. Si este documento mapea los compradores de datos (insurers, lenders, OEMs, dealers, fleet managers) y cuantifica lo que pagan, es un asset de estrategia core.
- **Beneficio para CARDEX hoy:** Directo. Define el TAM real, no el aspiracional. Si el mercado de data intelligence automotive en EU vale €2B y CARDEX puede capturar €100K del nicho de cross-border pricing, ese número es más útil que cualquier TAM genérico en un pitch deck.
- **Factibilidad:** Alta.

**VEREDICTO: ENTRA**

**Prioridad: P1**

---

### 23. Anti-Detection Systems Research

**Tipo:** Investigación técnica
**Propósito declarado:** Investigación de sistemas anti-detección para web scraping

**Evaluación:**

- **Potencia real:** Alta. El scraping es la fuente de datos de CARDEX. Sin capacidad de scraping, no hay producto. Los portales (mobile.de, AutoScout24, leboncoin) usan Cloudflare, DataDome, PerimeterX, Akamai. CARDEX ya opera con Strategy B (curl_cffi + Camoufox + proxies residenciales). Esta investigación alimenta directamente la capacidad técnica core.
- **Beneficio para CARDEX hoy:** Directo e inmediato. Ya documenta `docs/SCRAPING_ENGINE.md` (814 líneas). La research de anti-detection complementa y actualiza el conocimiento del stack adversarial.
- **Factibilidad:** Alta. Es research sobre tecnología que ya se usa.

**VEREDICTO: ENTRA**

**Prioridad: P1**

**Acción:** Verificar que cubre: fingerprinting TLS (JA3/JA4), browser fingerprinting (Canvas, WebGL, AudioContext), WAF classification (Cloudflare, DataDome, PerimeterX), técnicas de evasión con Camoufox, rotación de identidades, y detección de softblocks.

---

## PRIORIZACIÓN DE ENTREGABLES APROBADOS

### Tier 1 — Críticos (implementar inmediatamente, impacto directo en supervivencia/revenue)

| Prioridad | Entregable | Justificación |
|-----------|-----------|---------------|
| P1 | #7 GDPR Compliance | Protección legal existencial. Sin esto, un C&D puede destruir la empresa |
| P1 | #9 Operations Runbook | Reduce bus factor de 1. El sistema ya existe, necesita documentación operativa |
| P1 | #12 Vehicle Data Normalization | La calidad de datos ES el producto. Sin normalización, los datos no se venden |
| P1 | #15 European Vehicle Pricing Intelligence | Es la demostración del valor comercial. El sample report que cierra la primera venta |
| P1 | #16 Infrastructure Architecture | Documentación de lo que realmente está desplegado. Reduce dependencia del fundador |
| P1 | #22 Automotive Data Intelligence | Define el mercado real. Sin esto, se vende a ciegas |
| P1 | #23 Anti-Detection Research | Mantiene operativa la fuente de datos. Sin scraping, no hay CARDEX |

### Tier 2 — Importantes (implementar en 30-60 días, impulsa posicionamiento y producto)

| Prioridad | Entregable | Justificación |
|-----------|-----------|---------------|
| P2 | #3 Product Roadmap (modificado) | Foco en las 3 features que generan revenue |
| P2 | #11 API Design OpenAPI | La spec ES el producto vendible. Convertir datos en API comercializable |
| P2 | #14 Monetization Strategy (modificado) | Define cómo se cobra. Sin esto, se regala el trabajo |
| P2 | #17 OPENLANE Audit | Inteligencia competitiva para posicionamiento |
| P2 | #18 AUTO1 Audit | Benchmark financiero del mercado |
| P2 | #19 Autorola/Indicata Audit | Competidor directo en pricing analytics — define pricing de CARDEX |
| P2 | #20 CarOnSale Audit | Benchmark de startup B2B en el mismo espacio |

### Tier 3 — Útiles (implementar cuando Tier 1-2 estén cerrados)

| Prioridad | Entregable | Justificación |
|-----------|-----------|---------------|
| P3 | #2 Financial Model (modificado) | Útil para decisiones, pero no genera revenue directo |
| P3 | #21 Indirect Competitors Map | Completa la visión competitiva |

### Tier 4 — Marginal (implementar solo si sobra tiempo)

| Prioridad | Entregable | Justificación |
|-----------|-----------|---------------|
| P4 | #8 Risk Management (modificado) | Útil pero no urgente si se tiene el runbook |
| P5 | #10 Developer Onboarding (modificado) | Solo si aporta valor sobre CONTEXT_FOR_AI.md existente |

---

## ENTREGABLES DESCARTADOS — REGISTRO DE RAZONES

| # | Entregable | Razón de descarte | Cuándo reconsiderar |
|---|-----------|-------------------|---------------------|
| 1 | Investor Pitch Deck | Sin tracción, sin red de VCs, sin equipo. Deck prematuro | Cuando haya €5K MRR y 10+ clientes pagando |
| 4 | B2B Sales Playbook | Asume equipo de ventas y pipeline. No aplica para fundador solo | Cuando haya proceso de venta repetible (3+ clientes cerrados con el mismo approach) |
| 5 | SEO Go-to-Market | Canal incorrecto para B2B fase cero. ROI a 12+ meses | Cuando haya frontend público y budget de contenido |
| 6 | Customer Success Retention | Cero clientes = cero retención posible | Cuando haya 10+ clientes activos y se observe churn |
| 13 | Partnership Integration Strategy | Sin leverage negociador, los partners no contestan | Cuando CARDEX tenga datos o distribución que un partner necesite |

---

## RECOMENDACIONES TRANSVERSALES

**1. La obsesión debe ser el primer euro.**
14 de 23 entregables son útiles. Pero ninguno genera revenue por sí solo. La prioridad absoluta es: (a) definir el producto mínimo vendible (API o dashboard), (b) definir el precio, (c) encontrar 5 dealers que paguen. Todo lo demás es infraestructura de soporte.

**2. Convertir el pricing intelligence (#15) en un demo vendible.**
El entregable #15 debería convertirse en un PDF ejecutivo de 5 páginas que muestre: "Aquí están los 10 mejores arbitrajes DE→ES de esta semana, con margen estimado por vehículo." Ese PDF, enviado a 20 dealers por email, es el primer test de mercado real. Coste: €0.

**3. La API spec (#11) es el producto, no documentación.**
Una spec OpenAPI no es documentación técnica — es la definición del producto. Debe diseñarse pensando en el dealer que la va a consumir, no en el desarrollador que la va a implementar. Incluir pricing en la spec misma (free tier: 100 llamadas/día, paid: €99/mes unlimited).

**4. Los audits competitivos (#17-21) deben informar el pricing.**
Si Indicata cobra €400/mes y CARDEX ofrece datos similares a €99/mes, hay una propuesta de valor clara. Los audits no son ejercicios académicos — son instrumentos de pricing.

**5. Eliminar toda referencia a infraestructura aspiracional.**
Cualquier entregable que mencione PostgreSQL, ClickHouse, Redis, 3x AX102, o multi-nodo como si existiera debe ser corregido. La credibilidad se destruye cuando un documento describe una realidad que no es. SQLite, CX42, €22/mes — esa es la verdad, y es respetable.

---

## LISTA FINAL DE IMPLEMENTACIÓN (14 entregables)

En orden de ejecución:

1. **#7 GDPR Compliance** — escudo legal inmediato
2. **#23 Anti-Detection Research** — mantiene el motor de datos vivo
3. **#12 Vehicle Data Normalization** — calidad de datos = calidad de producto
4. **#15 Pricing Intelligence** → convertir en demo vendible
5. **#16 Infrastructure Architecture** — documentar la realidad
6. **#9 Operations Runbook** — operaciones documentadas
7. **#22 Automotive Data Intelligence** — entender el mercado
8. **#11 API Design OpenAPI** — definir el producto
9. **#14 Monetization Strategy** (modificado) — definir el precio
10. **#17-20 Competitive Audits** — informar posicionamiento y pricing
11. **#3 Product Roadmap** (modificado) — hoja de ruta enfocada
12. **#2 Financial Model** (modificado) — proyecciones realistas
13. **#21 Indirect Competitors Map** — completar visión competitiva
14. **#8 Risk Management** (modificado) — mitigación de riesgos reales
15. **#10 Developer Onboarding** (modificado, solo si no duplica CONTEXT_FOR_AI.md)

---

*Documento generado contra el estado verificado del repositorio a 2026-06-05. Cualquier discrepancia con la realidad del código invalida las conclusiones afectadas. Releer CONTEXT_FOR_AI.md antes de actuar sobre este documento.*
