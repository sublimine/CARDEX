# 06 — Stack Decisions

## Identificador
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Principio de evaluación

Cada decisión de stack se justifica en tres dimensiones:
1. **Funcional:** ¿cumple los requisitos técnicos del caso de uso?
2. **Operacional:** ¿puede ser mantenido por 1 persona sin conocimiento especializado?
3. **Económico:** ¿tiene coste €0 de licencia y coste de recursos compatible con VPS CX41?

---

## Capa: Lenguaje Principal

| | Decisión | Alternativas consideradas |
|---|---|---|
| **Elección** | **Go 1.22+** | Rust, Python, Node.js, Java |

**Justificación:**
- **Performance:** compilado a binario nativo, GC con latencias <5ms, sin JVM overhead
- **Concurrencia:** goroutines + channels modelan naturalmente el pipeline de eventos (NATS → validadores → índice)
- **Binario único:** `go build` produce un ejecutable estático sin dependencias de runtime — simplifica deployment (`rsync` + `systemctl restart`)
- **Ecosistema:** drivers de primera calidad para SQLite (`modernc.org/sqlite`, pure Go sin CGO), DuckDB Go driver, NATS Go client, `net/http` stdlib para crawling
- **Razón de descarte Rust:** curva de aprendizaje borrow checker + ecosistema async más complejo para 1 developer; performance ventaja marginal para casos de uso I/O-bound
- **Razón de descarte Python:** GIL (Global Interpreter Lock) limita paralelismo CPU real; overhead de runtime; performance de crawling 5-10× inferior a Go
- **Razón de descarte Java:** JVM memory overhead (~300-500 MB baseline) incompatible con presupuesto RAM; startup lento; sin beneficio claro frente a Go

---

## Capa: ML Inference (clasificadores de imagen, NLP)

| | Decisión | Alternativas consideradas |
|---|---|---|
| **Elección** | **ONNX Runtime CPU (INT8)** | TensorFlow, PyTorch, TFLite, CoreML |

**Justificación:**
- **Portabilidad:** modelos ONNX exportables desde PyTorch/TensorFlow, ejecutables en Go via `onnxruntime-go`
- **INT8 quantization:** modelos cuantizados a INT8 reducen memoria ~4× y aumentan throughput ~2-4× en CPU sin GPU
- **Memory footprint:** YOLOv8n INT8 ~6 MB, MobileNetV3 INT8 ~2 MB, spaCy ONNX ~45 MB — caben en 500 MB total
- **Razón de descarte PyTorch:** proceso Python separado con overhead IPC; torch completo >1 GB RAM; no necesitamos gradientes en inference
- **Razón de descarte TFLite:** ecosistema Go incompleto; menos modelos disponibles en este formato
- **Throughput estimado:** YOLOv8n INT8 en 4 vCPU AMD EPYC → ~15-25 imágenes/segundo (suficiente para pipeline asíncrono)

---

## Capa: NLG (generación de descripciones)

| | Decisión | Alternativas consideradas |
|---|---|---|
| **Elección** | **llama.cpp + Llama 3 8B Instruct Q4_K_M** | GPT-4 API, Mistral API, Falcon, Phi-3, GPT-J |

**Justificación:**
- **Gratuito y local:** cero llamadas a APIs externas, sin coste por token, sin dependencia de disponibilidad de terceros
- **Calidad:** Llama 3 8B Instruct (Meta, Apache 2.0) es el mejor modelo open-source <10B para instrucción en múltiples idiomas (ES/FR/DE/NL/EN/IT)
- **Q4_K_M:** quantización 4-bit con método K-mean — mejor balance calidad/velocidad para CPU inference; 4.5 GB de VRAM/RAM
- **llama.cpp:** implementación C++ optimizada para CPU (AVX2, NEON), bindings Go via CGO, activamente mantenida
- **Throughput en CX41:** ~2-8 tokens/segundo en 4 vCPU → ~15-60 segundos por descripción de 120 palabras → ventana nocturna 5.5h → ~500-1300 descripciones/noche → suficiente para S0
- **Razón de descarte GPT-4 API:** coste ~€0.02-0.06 por descripción; con 50.000 vehículos = €1.000-3.000 → incompatible con €0 OPEX
- **Razón de descarte Phi-3 mini:** calidad en ES/FR inferior a Llama 3; multilingual peor documentado
- **Template fallback:** cuando LLM no disponible o produce alucinación → `text/template` Go determinístico

---

## Capa: OLTP — Base de datos operacional

| | Decisión | Alternativas consideradas |
|---|---|---|
| **Elección** | **SQLite 3 (WAL mode)** | PostgreSQL, MySQL, CockroachDB, BoltDB |

**Justificación:**
- **WAL mode:** Write-Ahead Logging permite readers concurrentes sin bloquear al writer; throughput de escritura >10.000 INSERT/s en NVMe
- **Sin proceso separado:** SQLite es una librería, no un daemon; sin overhead de networking, sin gestión de conexiones, sin pg_hba.conf
- **Driver pure Go:** `modernc.org/sqlite` — sin CGO, compila en cualquier plataforma, sin dependencias de sistema
- **Backup trivial:** `sqlite3 main.db ".backup main_backup.db"` — backup online sin locking aplicación
- **Tamaño esperado S0:** 5-20 GB — dentro de los límites donde SQLite es la solución óptima
- **Razón de descarte PostgreSQL:** daemon separado ~50 MB RAM baseline; requiere gestión de roles, conexiones, vacuuming; overhead operacional desproporcionado para 1 developer
- **Migración a PostgreSQL (S2):** cuando WAL contention impide throughput requerido (estimado >100 escrituras/segundo concurrentes)
- **Invariante:** todas las foreign keys activadas (`PRAGMA foreign_keys = ON`), journals en WAL, checkpoint automático cada 1.000 páginas

---

## Capa: OLAP — Queries analíticas

| | Decisión | Alternativas consideradas |
|---|---|---|
| **Elección** | **DuckDB + parquet files** | Elasticsearch, ClickHouse, Redshift, BigQuery, SQLite FTS |

**Justificación:**
- **DuckDB:** motor analítico embebido (librería Go, sin daemon), vectorizado, columnar — queries complejas de búsqueda B2B en <500ms sobre millones de registros
- **Parquet:** formato columnar estándar, compresión ~10:1 sobre CSV, permite queries parciales (column pruning), portátil
- **Queries B2B típicas:** `SELECT * FROM vehicles WHERE make='BMW' AND year BETWEEN 2018 AND 2022 AND price_eur < 25000 AND country='DE' ORDER BY confidence_score DESC LIMIT 50` — DuckDB ejecuta esto en <200ms con 500.000 registros
- **Sin daemon:** DuckDB embebido en el binario Go del API service; sin proceso separado, sin configuración de red
- **Razón de descarte Elasticsearch:** 512 MB+ RAM solo para JVM; configuración compleja de índices; sharding innecesario en S0; license cambiante (SSPL en versiones recientes)
- **Razón de descarte ClickHouse:** excesivo para S0; requiere servidor separado; overhead de configuración
- **Separación OLTP/OLAP:** SQLite para escrituras frecuentes y datos relacionales (pipeline results, knowledge graph); DuckDB para queries de lectura complejas B2B

---

## Capa: Message Queue / Event Broker

| | Decisión | Alternativas consideradas |
|---|---|---|
| **Elección** | **NATS embedded (natsd)** | RabbitMQ, Kafka, Redis Pub/Sub, Go channels |

**Justificación:**
- **Embedded mode:** NATS puede correr embebido dentro de un proceso Go — sin daemon separado, sin Docker requerido, sin configuración de red
- **Subjects:** `dealer.new`, `extraction.queued`, `vehicle.raw.ready`, `vehicle.validated`, `nlg.pending`, `nlg.complete`, `vehicle.live`, `vehicle.invalidated` — modelo pub/sub limpio
- **Persistencia JetStream:** NATS JetStream provee at-least-once delivery con ACK, replay de mensajes, DLQ — garantías suficientes para pipeline
- **Memoria:** NATS embedded ~10-20 MB RAM
- **Razón de descarte Kafka:** mínimo 1 broker Kafka = ~512 MB RAM + Zookeeper; overhead operacional extremo para pipeline de 1 VPS
- **Razón de descarte RabbitMQ:** daemon Erlang ~150 MB; configuración AMQP compleja; sin ventaja sobre NATS en este caso
- **Razón de descarte Go channels:** no persistentes — un crash pierde todos los mensajes en vuelo; sin replay, sin DLQ, sin backpressure entre procesos

---

## Capa: HTTP Client (crawling)

| | Decisión | Alternativas consideradas |
|---|---|---|
| **Elección** | **net/http stdlib + retry middleware custom** | Colly, Scrapy, Selenium, curl_cffi |

**Justificación:**
- **net/http stdlib:** production-grade, TLS 1.3, HTTP/2, conexiones persistentes (keep-alive), sin dependencias externas
- **CardexBot/1.0 UA:** `User-Agent: CardexBot/1.0 (+https://cardex.io/bot)` — identificable, sin fingerprint evasion
- **Retry middleware:** exponential backoff con jitter, max 3 intentos, respeta `Retry-After` headers
- **Rate limiter per-domain:** `golang.org/x/time/rate` token bucket — `robots.txt` Crawl-Delay honrado
- **Razón de descarte curl_cffi:** diseñado explícitamente para evadir TLS fingerprinting — ilegal en CARDEX por política C-04/C-10
- **Razón de descarte Colly:** abstracción innecesaria sobre net/http; limitaciones en configuración de concurrencia; sin beneficio claro
- **robots.txt:** cargado y cacheado por dominio al inicio de cada extracción; refresh cada 24h

---

## Capa: Headless Browser

| | Decisión | Alternativas consideradas |
|---|---|---|
| **Elección** | **Playwright (Go bindings via playwright-go) — CardexBot/1.0, cero evasión** | Puppeteer, Selenium, playwright-stealth, Splash |

**Justificación:**
- **playwright-go:** bindings Go oficialmente soportados para Playwright (Microsoft); Chromium headless sin UI
- **Transparent UA:** `CardexBot/1.0` configurado explícitamente; sin modificación de headers TLS, sin fingerprintig evasion
- **XHR interception:** `page.Route()` para capturar llamadas XHR/Fetch de inventario — E07 usa esto para APIs no documentadas
- **Network throttling:** configurable para simular comportamiento normal (no flood)
- **Razón de descarte playwright-stealth:** diseñado para evadir detección — prohibido explícitamente en CARDEX (ILLEGAL_CODE_PURGE_PLAN.md)
- **Razón de descarte Splash:** proyecto poco activo; basado en Lua+Python; overhead adicional sin ventaja

---

## Capa: NLP (procesamiento de texto en extractores + V04)

| | Decisión | Alternativas consideradas |
|---|---|---|
| **Elección** | **spaCy multilingual ONNX (xx_ent_wiki_sm)** | NLTK, Stanford NLP, transformers full, regex puro |

**Justificación:**
- **ONNX export:** spaCy permite exportar modelos a ONNX para inference sin proceso Python en runtime
- **Modelo multilingual:** `xx_ent_wiki_sm` cubre DE/FR/ES/NL/IT/EN con NER para marcas de coches, ciudades, organizaciones
- **Vocabulario custom:** diccionario extendido de 60+ marcas de coches europeas para V04
- **Tamaño:** modelo ONNX ~45 MB, inference <10ms por título de listing
- **Razón de descarte transformers full (BERT/RoBERTa):** modelos 400 MB+; inference 200-500ms por texto; excesivo para title classification

---

## Capa: VIN Decoder

| | Decisión | Alternativas consideradas |
|---|---|---|
| **Elección** | **NHTSA vPIC SQLite mirror local** | NHTSA API online, autoapi.io, carquery.com |

**Justificación:**
- **Sin llamadas en runtime:** el mirror completo NHTSA vPIC (~3.5 GB SQLite) se descarga una vez y actualiza mensualmente; V02 hace queries locales sin latencia de red
- **NHTSA vPIC:** base de datos oficial US, cubre fabricantes mundiales por WMI (World Manufacturer Identifier), incluye make/model/year/body/engine
- **Descarga gratuita:** NHTSA ofrece dump público en formato Access/CSV, convertible a SQLite
- **Razón de descarte NHTSA API online:** latencia de red ~200-500ms por VIN; rate limiting 100 req/min; dependencia de disponibilidad externa

---

## Capa: Alternative Search Engine

| | Decisión | Alternativas consideradas |
|---|---|---|
| **Elección** | **SearXNG self-hosted (Docker)** | Google Custom Search API, Bing API, DuckDuckGo API, Brave API |

**Justificación:**
- **Self-hosted:** sin rate limits externos, sin coste por query, ~200 MB RAM Docker
- **Meta-search:** agrega resultados de Google, Bing, DuckDuckGo, Brave, Marginalia, etc. — mayor cobertura que un solo motor
- **Free tier APIs como fallback:** Brave Search API (2.000 req/mes free), Marginalia API (experimental free) — configurables en SearXNG
- **Familia K:** ~10.000 queries/ciclo de discovery — imposible con APIs con rate limits de pago
- **Razón de descarte Google Custom Search:** 100 queries/día free, luego $5/1.000 queries — con 10.000 queries/ciclo = $50/ciclo = prohibitivo

---

## Capa: Observabilidad

| | Decisión | Alternativas consideradas |
|---|---|---|
| **Elección** | **Prometheus + Grafana + OpenTelemetry (traces)** | Datadog, New Relic, Elastic APM, Zabbix |

**Justificación:**
- **Prometheus:** pull-based metrics, TSDB embebida, 2 años de retención posible, standard de facto en open-source
- **Grafana:** dashboards sobre Prometheus, alert rules, zero licensing
- **OpenTelemetry:** estándar abierto para traces distribuidos; exporta a Jaeger (self-hosted) o OTLP
- **Docker Compose:** Prometheus + Grafana corren en Docker, aislados del proceso Go, fáciles de actualizar
- **Razón de descarte Datadog:** $15-30/host/mes — incompatible con €0 OPEX
- **Razón de descarte Elastic APM:** stack ELK completo ~2 GB RAM mínimo — incompatible con VPS 16 GB compartido

---

## Capa: CI/CD

| | Decisión | Alternativas consideradas |
|---|---|---|
| **Elección** | **Forgejo self-hosted (Docker)** | GitHub Actions, GitLab CI, Jenkins, Drone CI |

**Justificación:**
- **Self-hosted:** código nunca abandona el VPS; sin dependencia de GitHub/GitLab
- **Forgejo:** fork de Gitea, activamente mantenido, compatible con GitHub Actions syntax
- **Illegal pattern linter:** CI step custom con `grep` sobre blacklist C-04/C-10 → hard fail si detecta curl_cffi, playwright-stealth, JA3/JA4, etc.
- **Deploy in-place:** rsync binarios + `systemctl restart` — sin Kubernetes, sin Docker Swarm, sin downtime de servicios no modificados
- **Razón de descarte GitHub Actions:** requiere código en GitHub (seguridad) o runner self-hosted (configuración adicional); webhook delay vs local Forgejo

---

## Capa: Backup y Cifrado

| | Decisión | Alternativas consideradas |
|---|---|---|
| **Elección** | **rsync diferencial + age encryption** | restic, duplicati, GPG, borg backup |

**Justificación:**
- **rsync:** herramienta estándar Unix, diferencial (solo transfiere cambios), eficiente sobre SSH
- **age:** herramienta moderna de cifrado de archivos (Go implementation), criptografía X25519+ChaCha20-Poly1305, más simple que GPG
- **Storage Box Hetzner:** €3/mes, SFTP/SSH, 1 TB, mismo DC → tráfico interno gratuito
- **Razón de descarte restic:** excelente herramienta pero más compleja de operar; age+rsync es más simple y auditables
- **Razón de descarte borg:** fork comunitario, requiere borg instalado en ambos extremos, menos portable

---

## Resumen ejecutivo

| Capa | Elección | RAM estimada | €/mes |
|---|---|---|---|
| Lenguaje | Go 1.22+ | — | €0 |
| ML Inference | ONNX Runtime INT8 | ~500 MB (modelos) | €0 |
| NLG | llama.cpp Llama 3 8B Q4_K_M | 4.5 GB (nocturno) | €0 |
| OLTP | SQLite 3 WAL | <100 MB runtime | €0 |
| OLAP | DuckDB + parquet | ~200 MB runtime | €0 |
| Queue | NATS embedded | ~20 MB | €0 |
| HTTP Client | net/http stdlib | minimal | €0 |
| Headless | Playwright (transparent) | ~300 MB | €0 |
| NLP | spaCy ONNX | ~45 MB | €0 |
| VIN Decoder | NHTSA SQLite local | ~10 MB runtime | €0 |
| Search Alt | SearXNG Docker | ~200 MB | €0 |
| Observability | Prometheus + Grafana | ~768 MB | €0 |
| CI/CD | Forgejo Docker | ~512 MB | €0 |
| Backup | rsync + age | — | €3 (Storage Box) |
| **TOTAL stack** | | **~7.2 GB peak (nocturno)** | **€3 licencias** |
