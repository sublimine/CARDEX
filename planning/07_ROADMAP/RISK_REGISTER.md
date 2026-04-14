# Risk Register

## Identificador
- Fecha: 2026-04-14, Estado: DOCUMENTADO
- Revisión: trimestral (ver PHASE_8_MAINTENANCE.md — ciclo trimestral)

## Convención de evaluación

| Probabilidad | Definición |
|---|---|
| ALTA | >50% de que ocurra durante el proyecto |
| MEDIA | 20-50% de probabilidad |
| BAJA | <20% de probabilidad |

| Impacto | Definición |
|---|---|
| CRÍTICO | Detiene el proyecto o requiere reescritura mayor |
| ALTO | Retrasa el roadmap ≥1 fase o requiere trabajo significativo no planificado |
| MEDIO | Requiere trabajo adicional pero no desvía el roadmap |
| BAJO | Inconveniencia menor, resuelto en <1 semana |

**Prioridad = Probabilidad × Impacto** (mayor prioridad = actuar primero)

---

## Categoría: Legal

### R-L-01: Cease and desist de plataforma de anuncios
- **Descripción:** Una plataforma (mobile.de, AutoScout24, leboncoin, etc.) envía una comunicación legal exigiendo que CARDEX deje de indexar su contenido, alegando violación del derecho sui generis de base de datos (Directiva 96/9/CE) o de sus términos de servicio.
- **Probabilidad:** MEDIA
- **Impacto:** ALTO (suspensión de una fuente de datos importante)
- **Mitigación:**
  1. Robots.txt compliance es la primera línea de defensa — se documenta y se cumple estrictamente
  2. CARDEX extrae metadatos estructurados mínimos, no el contenido creativo protegido (texto del dealer, imágenes del dealer)
  3. Responder a cualquier comunicación legal en <48h con la posición legal documentada (se puede contratar asesor ad-hoc para este caso)
  4. Si la plataforma tiene razón: suspender extracción de esa plataforma, reclasificar sus dealers a E12 o E11
  5. Diseñar el sistema de forma que ninguna fuente única sea indispensable — diversificación de fuentes reduce el impacto
- **Trigger de acción:** recepción de comunicación formal (email o carta) de representante legal de la plataforma
- **Status:** ABIERTO — monitorizar

### R-L-02: Cambio en EU Data Act o GDPR que afecte al modelo E11
- **Descripción:** La legislación EU que fundamenta E11 (EU Data Act, DSA) se modifica o su interpretación cambia, afectando la base legal del Edge Client.
- **Probabilidad:** BAJA
- **Impacto:** MEDIO (E11 afectado, pero E01-E10 y E12 no dependen de él)
- **Mitigación:**
  1. E11 está diseñado con consentimiento explícito del dealer — incluso si el EU Data Act cambia, el consentimiento voluntario sigue siendo válido
  2. E11 es una de 12 estrategias — su pérdida reduce cobertura en un porcentaje manejable
  3. Monitorizar EUR-Lex para cambios relevantes en EU Data Act (alerta Google Scholar)
- **Trigger de acción:** publicación de nuevo reglamento o jurisprudencia relevante
- **Status:** ABIERTO — monitorizando EUR-Lex

### R-L-03: Interpretación de robots.txt como contrato vinculante en jurisdicción específica
- **Descripción:** Un tribunal en DE, FR o ES establece jurisprudencia de que la violación de robots.txt constituye incumplimiento contractual o trespass.
- **Probabilidad:** BAJA
- **Impacto:** CRÍTICO si afecta a todos los crawlers en esa jurisdicción
- **Mitigación:**
  1. CARDEX cumple robots.txt estrictamente — si esta jurisprudencia emerge, CARDEX ya cumple
  2. Documentar todos los accesos a robots.txt con timestamps
  3. La jurisprudencia favorece a quienes tienen UA identificable y cumplen robots.txt
- **Trigger de acción:** sentencia publicada en una jurisdicción objetivo
- **Status:** ABIERTO — CARDEX ya tiene la mejor posición posible

### R-L-04: Litigio por precio de vehículo incorrecto causando daño a comprador B2B
- **Descripción:** Un comprador B2B toma una decisión de compra basándose en un precio de CARDEX que resulta incorrecto (error de extracción o precio desactualizado), y alega daño económico.
- **Probabilidad:** BAJA
- **Impacto:** MEDIO (reputacional + posible indemnización menor)
- **Mitigación:**
  1. Disclaimer claro en la API: "Los precios son indicativos y se actualizan con TTL de 72h; verificar con el dealer antes de cualquier transacción"
  2. V15 + V16 detectan inconsistencias de precio — confidence_score bajo para precios dudosos
  3. CARDEX no es parte de la transacción — solo un índice de referencia
  4. TTL de 72h garantiza que los precios no están "años" desactualizados
- **Trigger de acción:** reclamación formal de un buyer
- **Status:** ABIERTO — mitigación en diseño del sistema

---

## Categoría: Técnico

### R-T-01: Llama 3 8B cambia de licencia o deja de ser descargable públicamente
- **Descripción:** Meta retira la licencia Apache 2.0 de Llama 3 o impone restricciones de uso comercial que impiden el uso de CARDEX.
- **Probabilidad:** BAJA
- **Impacto:** ALTO (NLG service requiere reescritura para otro modelo)
- **Mitigación:**
  1. Mantener una copia del modelo GGUF en el Storage Box de backup (la descarga fue bajo Apache 2.0)
  2. Alternativas documentadas: Mistral 7B (Apache 2.0), Phi-3 mini, Qwen2 7B — todos Apache 2.0 o similar
  3. Template fallback en V19 funciona sin LLM — la calidad baja pero el sistema no se rompe
- **Trigger de acción:** anuncio de Meta de cambio de licencia o restricción de acceso
- **Status:** ABIERTO — almacenar copia del modelo post-download

### R-T-02: Dependencia Go crítica deprecada o con vulnerabilidad
- **Descripción:** Una librería Go en el stack crítico (modernc.org/sqlite, nats.go, duckdb-go) tiene una vulnerabilidad de seguridad o se depreca sin mantenimiento.
- **Probabilidad:** MEDIA
- **Impacto:** MEDIO (parche o sustitución de dependencia)
- **Mitigación:**
  1. `govulncheck ./...` en CI — detecta vulnerabilidades conocidas en cada PR
  2. `go mod tidy` + revisión de `go.sum` en CI
  3. Para SQLite: `modernc.org/sqlite` tiene alternativa en `mattn/go-sqlite3` (CGO pero más maduro)
  4. Para NATS: nats.io es un proyecto activo con empresa detrás (Synadia)
- **Trigger de acción:** CVE publicado en un paquete directo, o anuncio de deprecación
- **Status:** ABIERTO — govulncheck activo en CI

### R-T-03: Estructura de DOM/HTML de plataforma de anuncios cambia (breaking change)
- **Descripción:** mobile.de, AutoScout24 o leboncoin rediseña su frontend, rompiendo los extractores E01/E07 que dependen de su estructura.
- **Probabilidad:** ALTA (ocurre con certeza en el largo plazo)
- **Impacto:** MEDIO (requiere actualización de extractores, downtime de cobertura en esa plataforma)
- **Mitigación:**
  1. E07 (Playwright) captura XHR — más resistente a cambios de DOM que scraping HTML
  2. Monitor de estructura de página: alertar cuando el hash de la estructura HTML cambia significativamente
  3. Las métricas de coverage por plataforma detectan el problema rápidamente (cobertura cae)
  4. Cada extractor tiene su propia suite de tests con fixtures — un cambio de estructura rompe los tests primero, no producción
- **Trigger de acción:** coverage de plataforma baja >20% en 24h
- **Status:** ABIERTO — mitigación por diseño (XHR preference en E07)

### R-T-04: SQLite WAL insuficiente para throughput requerido en S0
- **Descripción:** El volumen de escrituras concurrentes al SQLite OLTP supera la capacidad de WAL mode, causando latencias o bloqueos.
- **Probabilidad:** BAJA en S0, ALTA en S1+
- **Impacto:** MEDIO (latencias en pipeline, posible necesidad de upgrade a S1 antes de lo esperado)
- **Mitigación:**
  1. Criterios de scaling en `10_SCALING_PATH.md` monitorizan WAL checkpoint latency p99
  2. SQLite WAL puede manejar ~10.000 writes/s en NVMe — CARDEX S0 estimado <1.000 writes/s
  3. Separación OLTP/OLAP reduce presión en SQLite (DuckDB absorbe queries analíticas)
- **Trigger de acción:** WAL checkpoint latency p99 >200ms sostenido 24h
- **Status:** ABIERTO — monitorizado en Grafana

### R-T-05: ONNX Runtime o modelos ML producen resultados inconsistentes entre versiones
- **Descripción:** Una actualización de ONNX Runtime cambia el output de un clasificador de imagen, afectando V05 o V10.
- **Probabilidad:** BAJA
- **Impacto:** MEDIO (posible flood de MANUAL_REVIEW si un clasificador empieza a falar)
- **Mitigación:**
  1. Pin de versión de ONNX Runtime en go.mod — no actualizar automáticamente
  2. Tests de regresión sobre dataset fijo de imágenes de referencia (no producción)
  3. Si V10 (vehicle binary classifier) empieza a falar masivamente → alerting rule "ValidatorFailRateHigh" se dispara
- **Trigger de acción:** fail rate de V05 o V10 >2× el expected rate
- **Status:** ABIERTO — versión pinneada

---

## Categoría: Operacional

### R-O-01: VPS Hetzner CX41 outage
- **Descripción:** El VPS tiene una interrupción no planificada (fallo de hardware, mantenimiento de Hetzner, etc.).
- **Probabilidad:** BAJA (Hetzner SLA 99.9% uptime)
- **Impacto:** ALTO (sistema no disponible durante el outage)
- **Mitigación:**
  1. Backups en Storage Box (mismo datacenter, tráfico interno gratuito) — sistema restaurable en <2 horas
  2. Runbook de recuperación completo (ver `07_DEPLOYMENT_TOPOLOGY.md` + `docs/runbook.md`)
  3. Hetzner ofrece "Rescue Mode" para arrancar desde imagen ISO si hay corrupción de disco
  4. UptimeRobot alerta en <2 minutos — el operador puede actuar rápidamente
  5. En S1+: segundo VPS en región diferente absorbe tráfico durante outage del primero
- **Trigger de acción:** UptimeRobot alerta de downtime
- **Status:** ABIERTO — runbook preparado en P5

### R-O-02: Operador (Salman) no disponible por período prolongado
- **Descripción:** El único operador está inaccesible por enfermedad, viaje, u otra causa durante >7 días.
- **Probabilidad:** MEDIA
- **Impacto:** MEDIO (manual review queue se acumula; nada más se rompe — el sistema es autónomo)
- **Mitigación:**
  1. El sistema está diseñado para ser autónomo — discovery, extraction, quality y NLG corren sin intervención
  2. El único impacto de la ausencia del operador es la manual review queue (SLA <24h)
  3. El runbook debe ser suficientemente claro para que un segundo operador (técnico de confianza) pueda asumir temporalmente
  4. La manual review queue acumulada no se pierde — se procesa cuando el operador regresa
- **Trigger de acción:** operador inaccesible >48h
- **Status:** ABIERTO — runbook como segunda línea de defensa

### R-O-03: Disco /srv del VPS lleno de forma inesperada
- **Descripción:** El crecimiento de los datos (SQLite, DuckDB parquet, logs) supera el estimado y llena /srv antes de la migración S1.
- **Probabilidad:** BAJA en los primeros 12 meses (estimado ~60 GB de 240 GB)
- **Impacto:** ALTO (el pipeline de ingesta se para — no puede escribir nuevos records)
- **Mitigación:**
  1. Alerting rule "DiskUsageHigh" a 80% — tiempo de reacción >1 semana normalmente
  2. Limpieza de parquet files antiguos (DuckDB expunge de records EXPIRED/SOLD > 90 días)
  3. Rotación de journald logs agresiva si /var/log crece
  4. Upgrade a CX51 (360 GB NVMe) es inmediato via Hetzner Cloud API
- **Trigger de acción:** alerta Prometheus DiskUsageHigh (>80%)
- **Status:** ABIERTO — alerta activa en P5

---

## Categoría: Mercado

### R-M-01: Competidor con más recursos lanza producto equivalente
- **Descripción:** Una empresa bien financiada (AutoScout24, CarGurus, OEM alliance) lanza un índice B2B con características similares a CARDEX.
- **Probabilidad:** MEDIA (el mercado B2B está subatendido, alguien más lo verá)
- **Impacto:** MEDIO (CARDEX pierde exclusividad de mercado, pero no invalidez del producto)
- **Mitigación:**
  1. La ventaja de CARDEX no es solo el índice — es la independencia del dealer, la cobertura multi-plataforma, y el precio €0 OPEX que permite precios bajos al buyer
  2. Acelerar la apertura a los 6 países para tener masa crítica antes de que el competidor llegue
  3. Los grandes competidores suelen tener más datos propietarios pero peor diversificación de fuentes — CARDEX tiene 15 familias de discovery vs. una sola fuente
- **Trigger de acción:** anuncio público de producto competidor
- **Status:** ABIERTO — monitorizar sector

### R-M-02: Dealers rechazan el modelo de indexación sin consentimiento explícito
- **Descripción:** Una asociación de dealers (ZDK en DE, CNPA en FR) lanza campaña para que sus miembros bloqueen a CardexBot vía robots.txt.
- **Probabilidad:** BAJA
- **Impacto:** ALTO si es masivo (pérdida de cobertura en un país)
- **Mitigación:**
  1. CARDEX genera valor para los dealers — sus vehículos son visibles a más compradores B2B
  2. E11 (Edge Client) convierte el "indexado pasivo" en "indexado activo con consentimiento" — dar esta opción proactivamente reduce la fricción
  3. Outreach a asociaciones de dealers con propuesta de valor clara antes de que se convierta en problema
- **Trigger de acción:** comunicado de asociación de dealers mencionando CARDEX o CardexBot
- **Status:** ABIERTO — E11 como herramienta de mitigación proactiva

### R-M-03: Mercado B2B no valora la solución (NPS crónico bajo)
- **Descripción:** Tras P7, el NPS se mantiene crónicamente por debajo de T_NPS a pesar de iteraciones de mejora, indicando que el problema resuelto no es valorado lo suficiente.
- **Probabilidad:** BAJA (el mercado B2B de vehículos de ocasión está claramente subatendido en EU)
- **Impacto:** CRÍTICO para la viabilidad comercial
- **Mitigación:**
  1. Las entrevistas con buyers durante P7 (soft launch) deben detectar este problema antes de la apertura pública
  2. Si el NPS es bajo, investigar qué valoran realmente los buyers (¿precio? ¿freshness? ¿cobertura?) antes de iterar ciegamente
  3. Pivotar la proposición de valor si necesario — los datos del knowledge graph son valiosos incluso si el "índice público B2B" no es el producto correcto
- **Trigger de acción:** NPS <T_NPS durante 3 encuestas mensuales consecutivas
- **Status:** ABIERTO — validación en P7

---

## Resumen de riesgos por prioridad

| ID | Categoría | Prob | Impacto | Prioridad | Status |
|---|---|---|---|---|---|
| R-T-03 | Técnico — DOM change | ALTA | MEDIO | **ALTA** | Abierto |
| R-L-01 | Legal — C&D plataforma | MEDIA | ALTO | **ALTA** | Abierto |
| R-O-02 | Operacional — operador ausente | MEDIA | MEDIO | MEDIA | Abierto |
| R-M-01 | Mercado — competidor | MEDIA | MEDIO | MEDIA | Abierto |
| R-T-02 | Técnico — dependencia deprecada | MEDIA | MEDIO | MEDIA | Abierto |
| R-L-02 | Legal — EU Data Act change | BAJA | MEDIO | BAJA | Abierto |
| R-T-01 | Técnico — Llama 3 licencia | BAJA | ALTO | BAJA | Abierto |
| R-O-01 | Operacional — VPS outage | BAJA | ALTO | BAJA | Abierto |
| R-O-03 | Operacional — disco lleno | BAJA | ALTO | BAJA | Abierto |
| R-L-03 | Legal — robots.txt jurisprudencia | BAJA | CRÍTICO | BAJA | Abierto |
| R-T-04 | Técnico — SQLite WAL | BAJA | MEDIO | BAJA | Abierto |
| R-T-05 | Técnico — ONNX inconsistencia | BAJA | MEDIO | BAJA | Abierto |
| R-L-04 | Legal — precio incorrecto | BAJA | MEDIO | BAJA | Abierto |
| R-M-02 | Mercado — dealers bloquean bot | BAJA | ALTO | BAJA | Abierto |
| R-M-03 | Mercado — NPS bajo crónico | BAJA | CRÍTICO | BAJA | Abierto |
