# 03 — Tooling Benchmark

## Identificador
- Fecha: 2026-04-14, Estado: DOCUMENTADO
- Convención: recursos estimados para VPS Hetzner CX41 (4 vCPU, 16 GB RAM, 240 GB NVMe)

---

## 1. Language / Runtime

| Candidato | Licencia | Pros | Contras | RAM baseline | Stars GitHub | Decisión |
|---|---|---|---|---|---|---|
| **Go 1.22+** | BSD-3 | Compilado nativo, goroutines, stdlib net/http excelente, binario único sin runtime, GC pausas <5ms | No tan expresivo como Rust; sin REPL para exploración | ~0 MB (binario) | — (stdlib) | ✅ **ELEGIDO** |
| Rust 1.77+ | MIT/Apache | Performance superior, zero-cost abstractions, sin GC | Curva de aprendizaje alta (borrow checker); ecosystem async más complejo | ~0 MB (binario) | — | Descartado |
| Python 3.12 | PSF | Ecosystem ML/AI excelente, rapidez de prototipado | GIL limita paralelismo CPU; overhead runtime 30-50 MB; performance crawling 5-10× peor que Go | 30-50 MB | — | Descartado para servicios principales; usado para NLG via Python bridge |
| Node.js 20 | MIT | Ecosystem npm amplio; async I/O maduro | Single-threaded (worker_threads complicado); tipado débil; runtime 50 MB+ | 50+ MB | — | Descartado |

**Justificación CARDEX:** Go es el equilibrio óptimo entre performance (comparable a Rust para I/O-bound), operabilidad (binario único, `systemctl restart`), y ecosystem (drivers SQLite, DuckDB, NATS, Playwright todos de primera calidad).

---

## 2. OLTP — Base de datos operacional

| Candidato | Licencia | Pros | Contras | RAM baseline | Decisión |
|---|---|---|---|---|---|
| **SQLite 3 (WAL)** | Public Domain | Librería embebida, sin daemon, zero-config, backup trivial (`.backup`), WAL mode permite readers concurrentes, driver pure-Go `modernc.org/sqlite` | Single-writer (no concurrent writes desde múltiples procesos), no adecuado para >50 writes/s sostenido desde múltiples hosts | <10 MB | ✅ **ELEGIDO** |
| PostgreSQL 16 | PostgreSQL Lic. | ACID completo, concurrent writes, extensiones (PostGIS, JSONB), madurez | Daemon separado (~50 MB baseline), gestión de roles/conexiones, vacuuming, overhead operacional | 50-100 MB | Reservado para S2 |
| MySQL/MariaDB 10.11 | GPL | Conocido, buen performance | Mismo overhead que Postgres sin sus ventajas; ACID menos robusto que Postgres | 50+ MB | Descartado |
| BoltDB (bbolt) | MIT | Embebido Go, B-tree ACID | No tiene SQL, API de bajo nivel, sin joins, difícil de mantener | <5 MB | Descartado |

---

## 3. OLAP — Queries analíticas

| Candidato | Licencia | Pros | Contras | RAM runtime | Decisión |
|---|---|---|---|---|---|
| **DuckDB** | MIT | Vectorizado columnar, embebido (librería), queries complejas en <500ms sobre millones de registros, parquet nativo, Go driver oficial | Single-writer embebido (no concurrent writes desde múltiples procesos), no cluster | ~200 MB | ✅ **ELEGIDO** |
| ClickHouse | Apache 2.0 | Performance extremo para agregaciones, clustering, sharding | Servidor separado (~500 MB+ baseline), configuración compleja, overhead para S0 | 512+ MB | Reservado para S3 |
| Apache Arrow/Parquet (sin query engine) | Apache 2.0 | Formato estándar, portable | Sin query engine propio — necesita DuckDB o Spark encima | N/A | Formato usado con DuckDB |
| Elasticsearch | SSPL (v7.10+) | Full-text search integrado | Licencia SSPL problemática, JVM 512+ MB, complejidad operacional | 512+ MB | Descartado |

---

## 4. Message Queue / Event Broker

| Candidato | Licencia | Pros | Contras | RAM | Decisión |
|---|---|---|---|---|---|
| **NATS (embedded natsd)** | Apache 2.0 | Puede correr embebido en proceso Go (sin daemon externo), JetStream at-least-once delivery, latencia <1ms, 10-20 MB en embedded mode | JetStream clustering requiere ≥3 nodes (no aplica en S0) | ~10-20 MB | ✅ **ELEGIDO** |
| RabbitMQ | MPL 2.0 | AMQP maduro, UI de gestión | Daemon Erlang ~150 MB, configuración AMQP verbose, overhead no justificado en S0 | ~150 MB | Descartado |
| Apache Kafka | Apache 2.0 | Throughput extremo, durable log, replay | Mínimo 1 broker + Zookeeper = ~600-800 MB; latencia ~10-50ms; exceso para S0 | 600+ MB | Descartado |
| Redis Streams | BSD-3 | Simple, conocido, baja latencia | No persistence durable por defecto; si Redis cae pierdes mensajes en vuelo | ~30 MB | Considerado para cache, no para queue primario |

---

## 5. Cache

| Candidato | Licencia | Pros | Contras | RAM | Decisión |
|---|---|---|---|---|---|
| **Redis 7 (standalone lite)** | BSD-3 (community) | Atomic operations, pub/sub, TTL nativo, driver Go excelente (`go-redis`) | Daemon separado; en S0 puede ser overhead innecesario para uso mínimo | ~30 MB | Considerado para cache de API keys y rate limiter state |
| **BoltDB (bbolt)** | MIT | Embebido Go, zero-config, B-tree, persistente | No distribuido; sin TTL nativo (requiere implementación manual) | <5 MB | ✅ **ELEGIDO** para cache local embebida (robots.txt cache, FX rates en memoria) |
| Memcached | BSD | Ultra-simple, rápido | Sin persistencia; sin tipos de datos ricos; menos útil que Redis | ~20 MB | Descartado |
| Ristretto (Go in-process) | Apache 2.0 | Cache in-memory Go, TTL nativo, concurrente | Solo en-proceso — se pierde al reiniciar | ~10 MB variable | Útil para cache de request dentro de un proceso |

**Nota:** en S0, el uso de cache es mínimo. La mayoría de datos "cachéables" (NHTSA, FX rates, robots.txt) están en SQLite con TTL gestionado a nivel de aplicación.

---

## 6. HTTP Client (crawling)

| Candidato | Licencia | Pros | Contras | Decisión |
|---|---|---|---|---|
| **net/http stdlib Go** | BSD-3 | Sin dependencias, TLS 1.3, HTTP/2, keep-alive, total control de UA y headers | Más verboso que frameworks de scraping | ✅ **ELEGIDO** con middleware custom |
| Colly (Go) | Apache 2.0 | Framework de scraping Go popular, callbacks, rate limiting integrado | Abstracción que limita control fino; no necesitamos lo que añade sobre net/http | Descartado |
| Scrapy (Python) | BSD-3 | Framework maduro, async, pipelines | Python — performance inferior; proceso separado para Go pipeline | Descartado |
| Crawlee (Node.js) | Apache 2.0 | Moderno, Playwright integrado | Node.js — overhead; no integración nativa con Go pipeline | Descartado |

---

## 7. Headless Browser

| Candidato | Licencia | Pros | Contras | RAM | Decisión |
|---|---|---|---|---|---|
| **Playwright (playwright-go)** | Apache 2.0 | Bindings Go oficialmente soportados, Chromium/Firefox/WebKit, XHR interception nativa, API limpia | CGO/proceso separado para Chromium; ~300 MB por instancia Chromium | ~300 MB/instancia | ✅ **ELEGIDO** (CardexBot UA, cero evasión) |
| Puppeteer (Node.js) | Apache 2.0 | Muy popular, ecosystem rico | Node.js — proceso separado; binding Go complejo | ~250 MB/instancia | Descartado |
| Selenium (+ WebDriver) | Apache 2.0 | Estándar histórico, múltiples lenguajes | Más lento que Playwright; WebDriver protocol overhead; API más verbosa | ~400 MB/instancia | Descartado |
| chromedp (Go) | MIT | Bindings Go nativos para Chrome DevTools Protocol | API de bajo nivel; menos features que Playwright (no WebKit/Firefox); mantenimiento menor | ~250 MB | Alternativa si playwright-go da problemas |

**Restricción absoluta:** playwright-stealth, `excludeSwitches`, `useAutomationExtension: false` y cualquier técnica de fingerprint evasion están **prohibidos**. Ver ILLEGAL_CODE_PURGE_PLAN.md.

---

## 8. NLP (procesamiento de texto)

| Candidato | Licencia | Pros | Contras | RAM modelo | Decisión |
|---|---|---|---|---|---|
| **spaCy (multilingual ONNX)** | MIT | Modelo `xx_ent_wiki_sm` cubre DE/FR/ES/NL/EN/IT, export a ONNX para inference en Go, custom vocabulary de marcas, NER entrenado | Precisión inferior a transformers completos para casos edge | ~45 MB ONNX | ✅ **ELEGIDO** |
| Stanford NLP / Stanza | Apache 2.0 | Alta precisión, modelos por idioma | Proceso Java/Python separado; overhead ~500 MB+; latencia más alta | ~300-500 MB | Descartado |
| HuggingFace Transformers (BERT/mBERT) | Apache 2.0 | Máxima precisión para NER | Modelos 400 MB+; inference 200-500ms por texto; excesivo para title classification | 400+ MB | Excesivo para V04 |
| Regex puro | — | Zero dependencies | No captura variaciones de nombres de marcas no anticipadas; frágil ante nuevas marcas | 0 MB | Fallback, no primario |

---

## 9. NLG / LLM local

| Candidato | Licencia | Pros | Contras | RAM | Tokens/s (4 vCPU est.) | Decisión |
|---|---|---|---|---|---|---|
| **Llama 3 8B Instruct Q4_K_M** (via llama.cpp) | Meta Llama 3 Community (Apache 2.0 compatible para commercial) | Mejor calidad multilingual open-source <10B, Apache 2.0, llama.cpp optimizado para CPU (AVX2), 4.5 GB GGUF | Lento en CPU (~2-8 tok/s); requiere ventana nocturna; CGO binding | ~4.5 GB | ~2-8 tok/s | ✅ **ELEGIDO** |
| Mistral 7B Instruct Q4_K_M | Apache 2.0 | Muy buena calidad, Apache 2.0 puro, tamaño similar | Multilingual ligeramente inferior a Llama 3 para FR/DE/ES/NL | ~4.0 GB | ~3-9 tok/s | Alternativa si Llama 3 da problemas |
| Phi-3 Mini 3.8B Q4 (Microsoft) | MIT | Muy pequeño (~2 GB), rápido | Calidad multilingual inferior; inglés-dominant | ~2.1 GB | ~8-15 tok/s | Alternativa si latencia es crítica |
| Falcon 7B | Apache 2.0 | Buen rendimiento en inglés | Multilingual inferior; menos mantenido post-2024 | ~4.0 GB | ~2-6 tok/s | Descartado |
| GPT-4 / Claude API | Propietario | Máxima calidad | €0.02-0.10 por descripción; 50.000 vehículos = €1.000-5.000; incompatible con €0 OPEX | N/A (cloud) | N/A | Descartado (OPEX) |
| Ollama (runtime alternativo) | MIT | Interface unificada para múltiples modelos | Runtime Python + overhead adicional; llama.cpp directo es más eficiente | overhead | — | Descartado en favor de llama.cpp directo |

---

## 10. Image Classification (ML)

| Candidato | Licencia | Pros | Contras | RAM modelo | Throughput (4 vCPU est.) | Decisión |
|---|---|---|---|---|---|---|
| **YOLOv8n INT8 ONNX** | AGPL 3.0 (Ultralytics) | Mejor precision/speed tradeoff para object detection, export ONNX trivial, fine-tunable en Stanford Cars | AGPL puede requerir revisión legal para uso comercial embebido | ~6 MB INT8 | ~15-25 img/s | ✅ **ELEGIDO para V05** (vehicle detection) |
| **MobileNetV3 Small INT8 ONNX** | Apache 2.0 | Ultra-ligero (~2 MB INT8), bueno para clasificación binaria (vehicle/non-vehicle), Apache 2.0 | Menor precisión que YOLOv8 para detection; mejor para classification binaria | ~2 MB INT8 | ~30-50 img/s | ✅ **ELEGIDO para V10** (binary vehicle classifier) |
| EfficientNet-B0 INT8 | Apache 2.0 | Mejor accuracy que MobileNet, razonable en tamaño | Ligeramente más lento que MobileNetV3 para CPU | ~15 MB INT8 | ~10-20 img/s | Alternativa si MobileNetV3 insuficiente |
| ResNet-50 | Apache 2.0 | Modelo base establecido, bien estudiado | ~50 MB, más lento que versiones lite | ~50 MB | ~5-10 img/s | Demasiado pesado para S0 |

**Nota legal YOLOv8:** la licencia AGPL-3.0 de Ultralytics requiere que si se distribuye software que usa YOLOv8, el código fuente debe ser open-source bajo AGPL. En CARDEX (sistema interno), esto se puede gestionar. Verificar con asesor legal si CARDEX se distribuye como SaaS. Alternativa: RT-DETR (Apache 2.0) si AGPL es problema.

---

## 11. Image Hashing (dedup de imágenes)

| Candidato | Licencia | Pros | Contras | Decisión |
|---|---|---|---|---|
| **goimagehash (Go)** | MIT | Pure Go, pHash + aHash + dHash, Hamming distance nativo, sin CGO | Menos features que implementaciones C++ | ✅ **ELEGIDO** |
| imagehash (Python) | BSD-2 | Popular, bien testeado, múltiples algoritmos | Python — proceso separado o bridge CGO; overhead | Descartado |
| pHash (C++) | LGPL | Implementación de referencia | CGO necesario; LGPL requiere análisis de linking | Descartado |

---

## 12. VIN Decode

| Candidato | Licencia | Pros | Contras | Decisión |
|---|---|---|---|---|
| **NHTSA vPIC SQLite mirror** | Public Domain (gov) | Sin llamadas en runtime, ~3.5 GB SQLite descargable, cobertura mundial de WMI, actualización mensual disponible | Solo VINs de vehículos homologados en US (WMI worldwide); algunos VINs EU raros no cubiertos | ✅ **ELEGIDO** |
| NHTSA vPIC API online | Public Domain | Sin setup | Latencia ~200-500ms/req, rate limit ~100 req/min; dependencia de disponibilidad | Descartado para runtime |
| DAT VIN API | Propietario | Alta cobertura EU | Pago; €€€ enterprise | Descartado (OPEX) |
| `cdelorme/vin` Go library | MIT | ISO 3779 checksum validation en Go | Solo validación de checksum, no decode de make/model | ✅ Usado para V01 (checksum), complementa NHTSA para V02 |
| `nicholasgasior/govin` | MIT | Decode básico de WMI | Datos limitados, menos completo que NHTSA mirror | Descartado |

---

## 13. Alternative Search Engine

| Candidato | Licencia | Pros | Contras | RAM | Decisión |
|---|---|---|---|---|---|
| **SearXNG** | AGPL 3.0 | Meta-search (agrega Google, Bing, DuckDuckGo, Brave, Marginalia), self-hosted, ~200 MB Docker, sin rate limits propios | AGPL; requiere Docker; configuración de engines manual | ~200 MB | ✅ **ELEGIDO** |
| YaCy | GPL-2.0 | Peer-to-peer search, sin dependencias externas | Calidad de resultados inferior a SearXNG (crawl propio limitado); lento | ~500 MB | Descartado |
| Whoogle | MIT | Google results sin tracking, self-hosted | Solo Google — punto único de falla; Google cambia frecuentemente su HTML | ~100 MB | Descartado (dependencia única) |
| Brave Search API | Propietario | Alta calidad, API REST simple, 2.000 req/mes free | Rate limit insuficiente para 10.000 queries/ciclo discovery; pago después | N/A | Usado como engine adicional dentro de SearXNG |
| Marginalia Search API | Apache 2.0 experimental | Indie web focused, sin big-tech | Cobertura muy limitada fuera de indie web | N/A | Usado como engine adicional dentro de SearXNG |

---

## 14. HTML Parsers

| Candidato | Licencia | Pros | Contras | Decisión |
|---|---|---|---|---|
| **goquery (Go)** | MIT | Sintaxis jQuery-like, mature, puro Go, excelente para E01/E06/E04 | Solo HTML — no maneja JavaScript rendering | ✅ **ELEGIDO** para extracción estática |
| lxml (Python) | BSD | Muy rápido para XML/HTML, XPath nativo | Python; proceso separado o bridge | Descartado |
| cheerio (Node.js) | MIT | jQuery-like, popular | Node.js; proceso separado | Descartado |
| BeautifulSoup (Python) | MIT | Muy popular, tolerante a HTML malformado | Python; más lento que lxml; proceso separado | Descartado |
| html.Parser stdlib Go | BSD | Zero dependencies | API de bajo nivel — más código para parsing básico vs goquery | Usado internamente por goquery |

---

## 15. CI/CD

| Candidato | Licencia | Pros | Contras | RAM | Decisión |
|---|---|---|---|---|---|
| **Forgejo** | MIT | Fork de Gitea activamente mantenido, compatible GitHub Actions syntax, self-hosted, ~512 MB Docker | UI menos pulida que GitHub/GitLab | ~512 MB | ✅ **ELEGIDO** |
| Gitea | MIT | Original (Forgejo es fork), stable | Menos activo que Forgejo desde el fork; comunidad dividida | ~512 MB | Descartado en favor de Forgejo |
| Drone CI / Woodpecker CI | Apache 2.0 | CI-only, ligero, YAML pipelines | Sin gestión de código — necesita GitHub/Gitea además | ~200 MB | Descartado (necesitamos git hosting también) |
| Jenkins | MIT | Muy maduro, ecosystem de plugins enorme | JVM ~512 MB+; configuración XML legacy; overkill | ~512 MB+ | Descartado |
| GitHub Actions (cloud) | Propietario | Excellent ecosystem, gratis para repos públicos | Código abandona el VPS; dependencia de GitHub | N/A | Descartado (seguridad) |
| GitLab CE | MIT | Feature-complete | RAM mínima ~2 GB — incompatible con VPS 16 GB compartido | ~2 GB | Descartado (demasiado pesado) |

---

## 16. Observabilidad

| Candidato | Licencia | Pros | Contras | RAM | Decisión |
|---|---|---|---|---|---|
| **Prometheus + Grafana** | Apache 2.0 | Stack standard de facto, ecosystem de exporters enorme, Go client oficial, Grafana dashboards, AlertManager | Prometheus TSDB en disco crece con retención; federation compleja a escala | ~512 MB combinado | ✅ **ELEGIDO** |
| VictoriaMetrics | Apache 2.0 | Más eficiente que Prometheus en RAM/disco, compatible PromQL | Menos ecosystem de integración nativa Go; menor comunidad | ~200 MB | Alternativa si Prometheus consume demasiado disco |
| InfluxDB (OSS) | MIT (OSS) | Time-series nativo, Flux query language | RAM uso similar a Prometheus; Flux menos estándar que PromQL; licencia cambió en v2+ | ~300 MB | Descartado |
| Datadog / New Relic | SaaS | Zero-ops, excellent dashboards | €15-30/host/mes — incompatible con €0 OPEX | N/A | Descartado |

---

## 17. Reverse Proxy / TLS

| Candidato | Licencia | Pros | Contras | RAM | Decisión |
|---|---|---|---|---|---|
| **Caddy 2** | Apache 2.0 | TLS automático Let's Encrypt sin configuración, Caddyfile simple, HTTP/3 nativo, Unix socket support | Menor ecosystem de módulos que Nginx | ~50 MB | ✅ **ELEGIDO** |
| Nginx | BSD-2 | Battle-tested, performance extremo, ecosystem vasto | TLS manual (certbot externo); configuración más verbosa | ~10 MB | Alternativa si Caddy da problemas |
| Traefik v3 | MIT | TLS automático, Docker-native, dynamic config | Docker-centric en su paradigma; overhead en modo no-Docker | ~50 MB | Descartado (Go services no son Docker) |
| HAProxy | GPL 2.0 | Performance ultra-alto, load balancing avanzado | Sin TLS automático; overkill para single-VPS | ~5 MB | Relevante en S2+ |

---

## 18. Backup y cifrado

| Candidato | Licencia | Pros | Contras | Decisión |
|---|---|---|---|---|
| **rsync + age** | GPL + MIT | rsync diferencial estándar Unix, incremental; age es criptografía moderna (X25519+ChaCha20-Poly1305), más simple que GPG | No tiene deduplicación de bloques (restic lo hace mejor para grandes datos binarios) | ✅ **ELEGIDO** |
| restic | BSD-2 | Excelente dedup de bloques, encrypted, cross-platform, soporte múltiples backends (S3, SFTP) | Más complejo de configurar que rsync+age; requiere restic en ambos extremos | Alternativa válida para S1+ |
| BorgBackup | BSD-2 | Dedup, compresión, encryption, muy eficiente | Requiere borg instalado en el servidor remoto (Storage Box de Hetzner no lo tiene por defecto) | Descartado |
| duplicity | GPL | Backup incremental cifrado, soporte SFTP | Python runtime; más lento que rsync; menos activamente mantenido | Descartado |

---

## Tabla resumen de decisiones

| Capa | Decisión | Alternativa S1/S2 | Licencia |
|---|---|---|---|
| Language | Go 1.22+ | — | BSD-3 |
| OLTP | SQLite 3 WAL | PostgreSQL 16 (S2) | Public Domain |
| OLAP | DuckDB + parquet | ClickHouse (S3) | MIT |
| Queue | NATS embedded | NATS cluster (S1) | Apache 2.0 |
| Cache | BoltDB / in-process | Redis 7 (S1) | MIT / BSD-3 |
| HTTP client | net/http stdlib | — | BSD-3 |
| Headless | Playwright (transparent) | chromedp | Apache 2.0 |
| NLP | spaCy multilingual ONNX | mBERT (si precisión insuf.) | MIT |
| NLG | Llama 3 8B Q4_K_M / llama.cpp | Mistral 7B | Meta Community Lic. |
| Image detection | YOLOv8n INT8 ONNX | RT-DETR (si AGPL problema) | AGPL 3.0 |
| Image classifier | MobileNetV3 INT8 ONNX | EfficientNet-B0 | Apache 2.0 |
| Image hash | goimagehash | — | MIT |
| VIN decode | NHTSA vPIC SQLite | — | Public Domain |
| Search alt | SearXNG Docker | — | AGPL 3.0 |
| HTML parser | goquery | — | MIT |
| CI/CD | Forgejo Docker | — | MIT |
| Observability | Prometheus + Grafana | VictoriaMetrics | Apache 2.0 |
| Reverse proxy | Caddy 2 | Nginx | Apache 2.0 |
| Backup | rsync + age | restic (S1+) | GPL + MIT |
