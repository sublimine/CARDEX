# CARDEX — Principios institucionales

## Identificador
- Documento: 01_PRINCIPLES
- Versión: 1.0
- Fecha: 2026-04-14
- Estado: AUTORITATIVO

Cinco principios. Cada uno con implicaciones operacionales concretas para arquitectura, código, validación y métricas.

## R1 — Legalidad estricta

### Enunciado
Cero técnicas de evasión técnica de medidas de protección. Todo acceso a datos es transparente, identificable y opera bajo una base legal explícita.

### Implicaciones operacionales

**Arquitectura.** El cliente HTTP central declara User-Agent identificable (`CardexBot/X.Y (+https://cardex.eu/bot)`), respeta `robots.txt` por defecto, honra rate limits declarados en cabeceras `Retry-After` y `X-RateLimit-*`, y mantiene cookie jar persistente solo cuando es legalmente apropiado. No hay ningún módulo de TLS impersonation, JA3/JA4 spoofing, residential proxy rotation evasivo, ni playwright stealth. Headless cuando es ineludible (sitios que requieren JS render legítimamente) usa Chromium con UA transparente.

**Código.** Cualquier dependencia que provea capacidades de evasión está prohibida. Lista negra explícita: `curl_cffi`, `playwright-stealth`, `puppeteer-extra`, `undetected-chromedriver`, `2captcha`, `anticaptcha`, librerías comerciales de proxy residencial (ScrapingBee, ScraperAPI, Bright Data, Smartproxy). El CI debe fallar build ante introducción de cualquiera.

**Validación.** Cada PR pasa por linter custom que busca patrones sospechosos (lista en `00_AUDIT/ILLEGAL_CODE_PURGE_PLAN.md`). Ninguna excepción justificada por "es solo para testing" o "es solo para una fuente puntual".

**Métricas.** Tracking de la base legal aplicable a cada fuente accedida: `legal_basis ∈ {open_data, sitemap_implicit_license, schema_org_syndication, eu_data_act_delegation, b2b_contract, dealer_consent_edge}`. Ningún acceso sin base legal asignada.

### Excepciones permitidas
Ninguna. Si una fuente requiere evasión para ser accedida, se considera no accesible bajo este régimen. La cobertura no se mejora violando ley.

## R2 — Presupuesto OPEX runtime mínimo

### Enunciado
Operación 100% sostenible sobre un único VPS de bajo coste mensual. Stack tecnológico íntegramente open-source y self-hosted. Ninguna dependencia de API de pago en runtime.

**OPEX runtime realista: €60-150/mes en operación a escala documentada** (Common Crawl monthly processing >150GB + Llama batch nocturno + observability stack + backups). El target inicial de ~€22/mes es válido SOLO durante fase pre-launch con volumen reducido (sin batch NLG nocturno, sin Common Crawl, sin tráfico de buyers).

Desglose pre-launch: €18 VPS + €3 Storage Box + ~€1.25 dominio = ~€22/mes.
Desglose operación plena estimada: €18 VPS + €3 Storage Box + €1.25 dominio + €30-100 tráfico/egress + €10-30 VPS adicional worker batch = €62-152/mes.

### Implicaciones operacionales

**Arquitectura.** VPS objetivo Hetzner CX41 (4 vCPU AMD, 16 GB RAM, 240 GB NVMe, 20 TB tráfico) o equivalente, ~€18/mes base (€18 VPS + €3 Storage Box + ~€1.25 dominio). Stack:

- OS: Debian 12 minimal hardened
- Lenguaje principal: Go (binarios estáticos, footprint <50 MB típico). Python solo para ML inference y PDF parsing
- OLTP: SQLite con WAL + mmap
- OLAP: DuckDB sobre archivos parquet en disco
- Cache: Redis embedded o BoltDB
- Queue: NATS embedded como librería Go (no broker separado)
- HTTP fetcher: Go nativo con middleware propio
- Headless ineludible: Playwright sobre Chromium local
- ML inference: ONNX Runtime CPU-only con modelos cuantizados INT8
- NLG: llama.cpp con Llama 3 8B cuantizado Q4_K_M
- VIN decode: NHTSA vPIC API mirror local
- Búsqueda alternativa: SearXNG self-hosted
- Observability: Prometheus + Grafana self-hosted
- CI/CD: Forgejo o Gitea self-hosted
- Backup: rsync diferencial diario a Hetzner Storage Box (€3/mes 1 TB)

**Código.** Ninguna integración a servicio SaaS de pago. Ninguna llamada a OpenAI, Anthropic API, Google Cloud Vision, AWS Rekognition, Bing Search, Twilio, Stripe, etc. Si una capacidad solo está disponible vía SaaS de pago, se difiere o se sustituye por alternativa open-source aunque inferior en velocidad/calidad.

**Validación.** Footprint de memoria total bajo carga típica <12 GB, picos <14 GB. Tiempo de procesamiento por job batch documentado. Disco utilizado <200 GB. Si alguna métrica supera el VPS objetivo, se rediseña o se difiere capacidad, no se escala.

**Métricas.** RAM peak por proceso, CPU% sostenido, disk I/O, network throughput. Dashboard Grafana visible en cada momento.

### Camino de escalado
Cuando el negocio valide, escalado horizontal trivial: VPS workers conectados al NATS central, sharding por país. Vertical: upgrade a CX51 (8 vCPU, 32 GB) o EX44 dedicado. Específico para NLG: GPU server cuando el volumen lo justifique. Storage: migrar OLAP a Postgres + ClickHouse cluster cuando >10M registros. Hasta entonces: una máquina, disciplina lean.

## R3 — Calidad institucional zero-error

### Enunciado
Ningún registro publicado sin pasar las 20 validaciones V01-V20 documentadas en `05_QUALITY_PIPELINE/`. Lo que no llega al estándar entra en cola de revisión humana. La calidad no se sacrifica por volumen.

### Implicaciones operacionales

**Arquitectura.** Pipeline de calidad como gateway obligatorio entre extracción e índice live. Cualquier camino que evite el pipeline está prohibido. Dead-letter queue + manual review queue como ciudadanos de primera clase, no como afterthought.

**Código.** Cada validador V01-V20 es un módulo Go independiente con interfaz uniforme. La cadena se ejecuta como pipeline observable. Cualquier fallo se reporta con severidad y se enruta correctamente. Tests obligatorios para cada validador con casos edge documentados.

**Validación.** Dataset de test propio con N vehículos manualmente verificados. CI ejecuta el pipeline completo sobre el dataset y falla si error rate >0.5%.

**Métricas.** Por cada vehículo: validators pasados, validators fallados, tiempo de procesamiento. Por cada fuente: tasa de aceptación, tasa de revisión manual, tasa de rechazo definitivo. Dashboard de calidad en tiempo real.

### Estándar mínimo de publicación
Un vehículo solo aparece en el índice live si: (1) los 20 validadores pasaron o el caso fue revisado humanamente y aprobado, (2) tiene puntero válido a foto activa en CDN del proveedor, (3) tiene descripción NLG generada coherente, (4) tiene VIN válido o flag explícito de "VIN no disponible", (5) freshness <TTL de su fuente.

## R4 — Sin techos mentales en discovery

### Enunciado
El descubrimiento de dealers no tiene objetivo numérico cerrado. El proceso es iterativo hasta exhaustividad verificable. Cada nuevo vector descubierto se integra. Cada hueco identifica un vector adicional.

### Implicaciones operacionales

**Arquitectura.** El knowledge graph dealer almacena para cada entidad las fuentes que la descubrieron. Análisis cruzado periódico identifica vectores con bajo discovery único, vectores con alto discovery único, y huecos sistemáticos. El sistema es auto-introspectivo sobre su propia cobertura.

**Código.** Cada familia de discovery es un módulo plug-in. Añadir un vector nuevo no requiere modificar el core — solo registrar el módulo en el orquestador. Esto permite expansión continua sin refactorización.

**Validación.** Definición operacional de exhaustividad: tres ciclos consecutivos de las N familias actuales sin un solo dealer nuevo descubierto durante T tiempo de búsqueda activa. T se calibra por país y por familia. Cuando se cumple, se declara saturación de las familias actuales y se inicia búsqueda explícita de nuevos vectores.

**Métricas.** Por familia: discovery rate, unique discovery rate (dealers que solo esta familia capturó), shared discovery rate (dealers compartidos con otras familias), false positive rate (dealers descubiertos que no son dealers reales). Tendencia temporal de cada métrica.

### Comportamiento al alcanzar saturación
No se declara "100% alcanzado" — se declara "saturación de las N familias actuales". A continuación: análisis cualitativo de qué tipo de dealer queda sin cubrir + búsqueda activa de nuevos vectores que lo capturen + integración del vector encontrado + nueva ronda de discovery. El proceso es indefinido hasta que el coste marginal de añadir vectores nuevos exceda el valor marginal del descubrimiento.

## R5 — Multi-redundancia 360° por defecto

### Enunciado
Ningún registro indexado por una sola fuente. Mínimo tres vectores independientes para confianza alta en discovery. Mínimo dos validaciones independientes para confianza alta en cada campo de un vehículo.

### Implicaciones operacionales

**Arquitectura.** El knowledge graph almacena en cada nodo las N fuentes que lo descubrieron. La confianza es función monotónica creciente del número de fuentes independientes que lo respaldan. El índice de vehículos almacena para cada campo crítico (VIN, make, model, año, precio, foto) las N fuentes que lo confirmaron.

**Código.** Cada validador V01-V20 documenta qué fuentes consume. La cross-validation es nativa del pipeline, no opcional. La función `confidence(record)` es central y observable.

**Validación.** Un dealer aparecido solo en una familia entra como BAJA-CONFIANZA y no se le activa indexación de catálogo automática hasta que se cruce con al menos otra familia. Un vehículo con VIN solo verificado por NLP del título (no por VIN-decode ni por image classification) no se publica.

**Métricas.** Distribución de confidence score por país, por familia, por dealer, por vehículo. Identificación de zonas con baja redundancia para targeting de vectores adicionales.

### Excepciones documentadas
Algunos campos pueden tolerar single-source si la fuente es de máxima autoridad: VIN provisto por NHTSA vPIC API, make/model provisto por OEM API oficial. Lista de fuentes de máxima autoridad documentada y revisada.
