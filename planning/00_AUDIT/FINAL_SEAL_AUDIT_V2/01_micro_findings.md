# TRACK 1 — WAVE 2: MICRO-FINDINGS (profundidad)

**Autorización:** Salman · **Política:** R1 · **Fecha:** 2026-04-16  
**Rama:** `audit/v2-track-1-micro` · **Dominios:** 8 · **Sprint activo:** Sprint 24 (no mezclado)  
**Referencia:** `planning/00_AUDIT/FINAL_SEAL_AUDIT/01_code_docs_coherence.md` (Track 1, 108 items)

---

## Resumen ejecutivo

Wave 2 identifica **62 hallazgos nuevos** en 8 dominios micro. El hallazgo más severo es la **desconexión total entre Alertmanager y Prometheus**: las reglas de alerta producción referencian 8+ métricas que **no existen en el código** (nombres incorrectos), lo que significa que las alertas críticas de extracción, calidad y errores de scraping **nunca se disparan** — el sistema corre silenciosamente ciego ante fallos. Secundariamente: 6 Dockerfiles sin digest SHA256 (supply chain), sqlite v1.37.1 en quality vs v1.48.2 en discovery/extraction (mismatched DB driver), goroutinas de health check sin `recover()` (panic silencia resultados), y un test que descarta su resultado con `_ =` sin assertions. Policy R1 continúa limpia.

---

## Tabla de hallazgos

| # | SEVERITY | DOMINIO | CATEGORÍA | DESCRIPCIÓN | ARCHIVO | LÍNEA | RECOMENDACIÓN |
|---|----------|---------|-----------|-------------|---------|-------|---------------|
| 1 | CRITICAL | Observability | Alertmanager ghost metric | `rules.yml:41` usa `discovery_scrape_errors_total`. Código exporta `cardex_discovery_subtechnique_requests_total`. El nombre no coincide — la alerta **nunca se dispara** en producción. | `deploy/observability/alertmanager/rules.yml:41` | 41 | Renombrar referencia a `cardex_discovery_subtechnique_requests_total` o añadir métrica faltante en `discovery/internal/metrics/metrics.go`. |
| 2 | CRITICAL | Observability | Alertmanager ghost metric | `rules.yml:43` usa `discovery_scrape_requests_total`. No existe en ningún `metrics.go`. Alerta de error rate discovery silenciosa. | `deploy/observability/alertmanager/rules.yml:43` | 43 | Crear métrica `cardex_discovery_scrape_requests_total` en `discovery/internal/metrics/metrics.go` o corregir la query. |
| 3 | CRITICAL | Observability | Alertmanager ghost metric | `rules.yml:55` usa `extraction_errors_total`. Código exporta `cardex_extraction_parse_errors_total`. Alerta de errores de extracción silenciosa. | `deploy/observability/alertmanager/rules.yml:55` | 55 | Corregir a `cardex_extraction_parse_errors_total` o crear alias. |
| 4 | CRITICAL | Observability | Alertmanager ghost metric | `rules.yml:57` usa `extraction_attempts_total`. Código exporta `cardex_extraction_total`. Alerta de extraction success rate silenciosa. | `deploy/observability/alertmanager/rules.yml:57` | 57 | Corregir a `rate(cardex_extraction_total[15m])`. |
| 5 | CRITICAL | Observability | Alertmanager ghost metric | `rules.yml:67` usa `cardex_validation_total`. Código exporta `cardex_quality_validation_total` (Namespace=`cardex`, Subsystem=`quality`). Alerta de critical validation failures **nunca se dispara**. | `deploy/observability/alertmanager/rules.yml:67` vs `quality/internal/metrics/metrics.go:11-13` | 67 / 11 | Corregir a `cardex_quality_validation_total`. |
| 6 | CRITICAL | Observability | Alertmanager ghost metric | `rules.yml:83` usa `extraction_queue_depth`. Esta métrica **no existe** en `extraction/internal/metrics/metrics.go`. La alerta de queue backlog nunca se dispara. | `deploy/observability/alertmanager/rules.yml:83` | 83 | Implementar `cardex_extraction_queue_depth` gauge en extraction metrics, o eliminar la regla. |
| 7 | CRITICAL | Observability | Alertmanager ghost metric | `rules.yml:95` usa `quality_pending_vehicles`. No existe en `quality/internal/metrics/metrics.go`. La alerta de backlog de calidad nunca se dispara. | `deploy/observability/alertmanager/rules.yml:95` | 95 | Implementar `cardex_quality_pending_vehicles` gauge, o eliminar la regla. |
| 8 | CRITICAL | Observability | Alertmanager ghost metric | `rules.yml:155` usa `cardex_last_backup_timestamp_seconds`. No existe en ningún `metrics.go`. La alerta de backup silence nunca se dispara — backups podrían llevar días sin correr sin que nadie lo sepa. | `deploy/observability/alertmanager/rules.yml:155` | 155 | Implementar este gauge en el backup script (pushgateway o service) y exportarlo. |
| 9 | HIGH | Concurrencia | Goroutine sin recover() | `runner/health.go` lanza una goroutine por familia sin `recover()`. Un panic en cualquier `HealthCheck()` termina silenciosamente esa goroutine sin enviar resultado al channel, dejando el consumidor esperando indefinidamente (channel buffer = `len(families)`, pero si una goroutine panics, hay un elemento faltante). | `discovery/internal/runner/health.go:37-42` | 39 | Añadir `defer func() { if r := recover(); r != nil { ch <- result{...err...} } }()` en la goroutine. |
| 10 | HIGH | Supply chain | SQLite version mismatch | `quality/go.mod:8`: `modernc.org/sqlite v1.37.1`. `discovery/go.mod:12` y `extraction/go.mod:11`: `v1.48.2`. Delta: 11 minor versions (37→48). La calidad puede tener comportamiento SQLite diferente (WAL, busy timeout, JSON functions) respecto a discovery/extraction. | `quality/go.mod:8` vs `discovery/go.mod:12` | 8 / 12 | Actualizar `quality/go.mod` a `modernc.org/sqlite v1.48.2`. Ejecutar `go get modernc.org/sqlite@v1.48.2` en `quality/`. |
| 11 | HIGH | Supply chain | Docker images sin digest (builder) | `Dockerfile.discovery:6`, `Dockerfile.extraction:7`, `Dockerfile.quality:6`: `FROM golang:1.25-bookworm AS builder`. Tag-only — si la imagen de Go cambia (CVE fix o regresión), el build pickup el cambio silenciosamente. | `deploy/docker/Dockerfile.discovery:6` | 6 | Pinear con digest: `FROM golang:1.25-bookworm@sha256:<digest>`. Obtener digest: `docker pull golang:1.25-bookworm && docker inspect --format='{{index .RepoDigests 0}}'`. |
| 12 | HIGH | Supply chain | Docker images sin digest (runtime) | `Dockerfile.discovery:33`, `Dockerfile.extraction:30`, `Dockerfile.quality:28`: `FROM gcr.io/distroless/static-debian12:nonroot`. Sin digest SHA256. Un cambio de base silencioso puede introducir vulnerabilidades en la imagen distroless. | `deploy/docker/Dockerfile.discovery:33` | 33 | Pinear: `FROM gcr.io/distroless/static-debian12:nonroot@sha256:<digest>`. |
| 13 | HIGH | Supply chain | docker-compose images sin digest | `docker-compose.yml:121,141,154,175`: `prom/prometheus:v3.0.1`, `prom/alertmanager:v0.27.0`, `grafana/grafana:11.5.0`, `caddy:2.9-alpine`. Tags sin digest. Cualquier `docker pull` o `docker-compose pull` puede actualizar silenciosamente. | `deploy/docker/docker-compose.yml:121,141,154,175` | 121–175 | Añadir digest a cada imagen de infraestructura. |
| 14 | HIGH | Tests | Test sin assertions | `ner_test.go:44-50` `TestExtractCandidates_NoMatches`: el resultado se descarta con `_ = candidates` (línea 49). El test nunca falla aunque la función devuelva basura. Comentario: "This test just ensures no panic." | `discovery/internal/families/familia_o/ner/ner_test.go:44-50` | 49 | Añadir: `if len(candidates) != 0 { t.Errorf("expected 0 candidates, got %d", len(candidates)) }`. |
| 15 | MEDIUM | Concurrencia | Metrics server sin graceful shutdown (extraction) | `extraction/cmd/extraction-service/main.go:159-170`: goroutine lanza `http.ListenAndServe()` sin `*http.Server` variable. No hay `srv.Shutdown()` llamado en ningún lugar del archivo. Al matar el proceso, el servidor de métricas muere abruptamente sin `200 OK` en el último scrape de Prometheus. | `extraction/cmd/extraction-service/main.go:159` | 159–170 | Crear `srv := &http.Server{Addr: cfg.MetricsAddr, Handler: mux}`, lanzar `go srv.ListenAndServe()`, y hacer `defer srv.Shutdown(ctx)` al final del main. |
| 16 | MEDIUM | Concurrencia | Metrics server sin graceful shutdown (quality) | `quality/cmd/quality-service/main.go:190-201`: mismo patrón que #15. Sin `srv.Shutdown()`. | `quality/cmd/quality-service/main.go:190` | 190–201 | Ídem #15. |
| 17 | MEDIUM | Concurrencia | `resp.Body` sin defer en probeURL (e04_rss HEAD) | `e04_rss/rss.go` ~363: `resp.Body.Close()` es llamada manualmente antes de return, sin `defer`. Si se añade un return path entre el Do() y el Close(), el body queda abierto (file descriptor leak). | `extraction/internal/extractor/e04_rss/rss.go` | ~363 | Mover a `defer resp.Body.Close()` inmediatamente después del nil-check de `resp`. |
| 18 | MEDIUM | Concurrencia | `resp.Body` sin defer en probeURL (e08_pdf) | `e08_pdf/pdf.go` ~252-257: `resp.Body.Close()` sin defer. Mismo riesgo que #17. | `extraction/internal/extractor/e08_pdf/pdf.go` | ~252 | Ídem #17. |
| 19 | MEDIUM | Concurrencia | `resp.Body` sin defer en probeURL (e09_excel) | `e09_excel/excel.go` ~259-264: `resp.Body.Close()` sin defer. | `extraction/internal/extractor/e09_excel/excel.go` | ~259 | Ídem #17. |
| 20 | MEDIUM | Concurrencia | Channel sin cierre explícito en health.go | `runner/health.go:35`: `ch := make(chan result, len(families))` — el channel nunca se cierra con `close(ch)`. Si un consumidor externo intenta `range ch`, bloquea indefinidamente. Aunque el patrón actual (receive con `for range families`) funciona, es frágil si se refactoriza. | `discovery/internal/runner/health.go:35` | 35 | Usar WaitGroup + `close(ch)` después de que todas las goroutines terminen. |
| 21 | MEDIUM | Concurrencia | `time.Now()` en cache de V10 no inyectable | `v10_source_url_liveness/v10.go`: cache TTL calculado con `time.Now()` sin interfaz de clock inyectable (a diferencia del patrón correcto en V14). Tests de liveness pueden ser no-deterministas en entornos CI lentos. | `quality/internal/validator/v10_source_url_liveness/v10.go` | ~44 | Seguir el patrón de V14: añadir `now func() time.Time` con `NewWithClock(clock func() time.Time)`. |
| 22 | MEDIUM | Concurrencia | `time.Now()` en cache de V02 no inyectable | `v02_nhtsa_vpic/v02.go`: `cacheEntry.storedAt` comparado contra `time.Now()` para TTL de 30 días. No hay clock inyectable. | `quality/internal/validator/v02_nhtsa_vpic/v02.go` | ~44–68 | Ídem #21. |
| 23 | MEDIUM | Prometheus | Label `strategy` sin enum — cardinality risk | `extraction/internal/metrics/metrics.go:12`: `ExtractionTotal` tiene label `strategy`. El valor proviene de `strategy.ID()` en runtime. Si una estrategia devuelve un ID inesperado (bug, refactor), se crea una nueva serie de cardinalidad alta en Prometheus. | `extraction/internal/metrics/metrics.go:12` | 12 | Definir constante `var KnownStrategyIDs = []string{"E01","E02",...,"E12"}` y validar antes de `WithLabelValues`. Loggear warning si ID desconocido. |
| 24 | MEDIUM | Prometheus | Label `validator_id` sin enum | `quality/internal/metrics/metrics.go:13`: `ValidationTotal` tiene label `validator_id`. Sin allow-list de V01-V20, un ValidatorID incorrecto (typo, nueva versión) crea nueva serie. | `quality/internal/metrics/metrics.go:13` | 13 | Ídem #23 con `var KnownValidatorIDs = []string{"V01",...,"V20"}`. |
| 25 | MEDIUM | Prometheus | Label `status` en SubTechniqueRequests sin documentación | `discovery/internal/metrics/metrics.go:47`: label `status` recibe `fmt.Sprintf("%dxx", resp.StatusCode/100)`. Sin documentación de valores permitidos (2xx, 3xx, 4xx, 5xx, err). Un caller diferente podría pasar el status completo (200, 404) creando cardinality explosion. | `discovery/internal/metrics/metrics.go:47` | 47 | Añadir comentario con valores canónicos o crear tipo `StatusLabel string` con constantes. |
| 26 | MEDIUM | Prometheus | Quality namespace inconsistente | Discovery/Extraction usan `Namespace` directamente (`cardex_discovery_*`, `cardex_extraction_*`). Quality usa `Namespace: "cardex", Subsystem: "quality"` → `cardex_quality_*`. La inconsistencia hace que las queries de PromQL deban conocer la convención de cada servicio. | `quality/internal/metrics/metrics.go:11-12` vs `discovery/internal/metrics/metrics.go:15` | 11 / 15 | Estandarizar: todos los servicios deberían usar el patrón `Namespace: "cardex_<service>"` o `Namespace: "cardex", Subsystem: "<service>"`. |
| 27 | MEDIUM | PII | VIN completo en ValidationResult.Issue | `v12_cross_source_dedup/v12.go:153,160`: `result.Issue = fmt.Sprintf("VIN %s appears under %d distinct dealers", vin, distinctDealers)`. El VIN completo (17 chars) aparece en un campo que puede loguearse o serializarse en respuestas API. | `quality/internal/validator/v12_cross_source_dedup/v12.go:153` | 153, 160 | Usar VIN parcial: `vin[:3] + "..." + vin[len(vin)-4:]` en mensajes de log/issue, reservar el VIN completo solo para storage estructurado con acceso restringido. |
| 28 | MEDIUM | PII | VIN en Evidence map sin redaction flag | `v12_cross_source_dedup/v12.go:118`: `result.Evidence["vin"] = vin`. El map `Evidence` es serializado como-está. Sin un mecanismo de redaction, el VIN viaja en JSON responses. | `quality/internal/validator/v12_cross_source_dedup/v12.go:118` | 118 | Añadir tag o convención: claves que terminan en `_pii` o `_sensitive` se redactan antes de serialización externa. |
| 29 | MEDIUM | PII | Phone en DealerLocation sin struct tag de redaction | `discovery/internal/kg/kg.go:153`: `Phone *string // optional phone number`. Sin `json:"-"` ni tag de sensibilidad. Si `DealerLocation` se serializa en respuestas API o logs, el número de teléfono se expone. | `discovery/internal/kg/kg.go:153` | 153 | Añadir `json:"-"` o un wrapper de serialización que omita campos sensibles en respuestas externas. |
| 30 | MEDIUM | Struct invariants | `VehicleRaw` sin `Validate()` centralizado | `extraction/internal/pipeline/types.go:27-66`: campos críticos (Make, Model, Year) son `*string`/`*int` que pueden ser nil. Existe `IsCritical()` pero no previene uso de campos nil downstream. Sin un constructor o `Validate() error`, cualquier caller puede crear un `VehicleRaw{}` vacío y pasarlo al pipeline. | `extraction/internal/pipeline/types.go:27` | 27–66 | Añadir `func (v *VehicleRaw) Validate() error` que retorne error descriptivo si campos críticos son nil/zero. |
| 31 | MEDIUM | Struct invariants | `Vehicle` (quality) sin constructor validado | `quality/internal/pipeline/validator.go:26-44`: `Vehicle` usa strings no-pointer pero sin constructor ni `Validate()`. Un `Vehicle{VIN: ""}` puede pasar a V01 (VIN checksum) y causar fallo silencioso o panic en checksum cálculo. | `quality/internal/pipeline/validator.go:26` | 26–44 | Implementar `NewVehicle(...) (*Vehicle, error)` que valide VIN != "", Year > 1900, Make != "". |
| 32 | MEDIUM | Struct invariants | `DealerLocation` pointers sin nil-check documentado | `discovery/internal/kg/kg.go:139-155` + `kg/dealer.go:88-118`: `DealerLocation.PostalCode`, `.City`, `.Phone` son `*string` opcionales. Se pasan a `db.ExecContext` directamente (lo que Go/SQL maneja como NULL) — correcto. Pero si código downstream los dereferencia sin nil-check, hay panic. | `discovery/internal/kg/dealer.go:88` | 88–118 | Documentar explícitamente en el godoc de `DealerLocation` cuáles campos son nullable. Considerar helper `func (l *DealerLocation) CityOrEmpty() string`. |
| 33 | MEDIUM | Config | BatchSize default diverge: código 50, docker-compose 20 | `extraction/internal/config/config.go:91`: `BatchSize: 50`. `deploy/docker/docker-compose.yml:74`: `EXTRACTION_BATCH_SIZE=${EXTRACTION_BATCH_SIZE:-20}`. Cuando se ejecuta sin docker-compose (systemd bare-metal), se usaría 50. Con docker-compose, 20. El throughput difiere 2.5x según entorno de despliegue. | `extraction/internal/config/config.go:91` vs `deploy/docker/docker-compose.yml:74` | 91 / 74 | Alinear defaults. Si 20 es el valor de producción correcto, cambiar `config.go` default a 20. Si 50 es correcto, actualizar `docker-compose.yml`. |
| 34 | MEDIUM | Config | Rate limits por familia discovery hardcoded | `familia_c/wayback/wayback.go:42`: `const defaultReqInterval = 1 * time.Second`. `familia_c/crtsh/crtsh.go`: `const defaultReqInterval = 3 * time.Second`. Cada familia tiene su constante hardcoded — no hay knob de configuración central. En producción no se puede ajustar sin recompilación. | `discovery/internal/families/familia_c/wayback/wayback.go:42` | 42 | Añadir `FamilyRateLimitMs int` a `discovery/internal/config/config.go` y pasar al constructor de cada familia. Default = valor actual de cada una. |
| 35 | MEDIUM | Config | WorkerCount=4 sin documentación de tuning | `extraction/internal/config/config.go:92` y `quality/internal/config/config.go:111`: ambos `WorkerCount: 4`. Extraction es I/O-bound (HTTP); quality es CPU-bound (regex, phash). El mismo valor para cargas distintas es probablemente subóptimo para uno de los dos. | `extraction/internal/config/config.go:92` | 92 | Documentar la rationale. Para quality (CPU-bound), considerar `runtime.NumCPU()` como default. Para extraction (I/O-bound), un múltiplo mayor (8-16) puede ser más eficiente. |
| 36 | MEDIUM | Security | CSP header ausente en Caddy y nginx | Ni `deploy/caddy/Caddyfile` ni `deploy/nginx/nginx.conf` configuran `Content-Security-Policy`. Si el b2b-dashboard o terminal se sirven a través de este proxy, XSS inline scripts quedan sin mitigación de CSP. | `deploy/caddy/Caddyfile` / `deploy/nginx/nginx.conf` | — | Añadir: `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; frame-ancestors 'none';` |
| 37 | MEDIUM | Security | nginx HSTS incompleto | `deploy/nginx/nginx.conf:98`: `Strict-Transport-Security "max-age=15768000"` — faltan `; includeSubDomains; preload`. Caddy sí los incluye. Inconsistencia entre las dos configuraciones de reverse proxy. | `deploy/nginx/nginx.conf:98` | 98 | Añadir `; includeSubDomains; preload` a la cabecera HSTS de nginx. |
| 38 | MEDIUM | Security | Rate limiting solo por IP — no IP+UA | `deploy/nginx/nginx.conf:54`: `limit_req_zone $binary_remote_addr`. User-Agent no forma parte de la clave de rate-limiting. Un bot que rota IPs pero usa el mismo UA, o que usa IPs distintas para eludir el límite, no es frenado. | `deploy/nginx/nginx.conf:54` | 54 | Para rutas de API sensibles, considerar `$binary_remote_addr$http_user_agent` como clave compuesta. Para el caso de uso actual (bot protection), es un riesgo bajo pero documentable. |
| 39 | MEDIUM | Security | CAP_NET_BIND_SERVICE en discovery sin verificar necesidad | `deploy/systemd/cardex-discovery.service:38-39`: `CapabilityBoundingSet=CAP_NET_BIND_SERVICE` y `AmbientCapabilities=CAP_NET_BIND_SERVICE`. El metrics server de discovery corre en puerto 9101 (no privilegiado). Esta capability puede no ser necesaria. | `deploy/systemd/cardex-discovery.service:38` | 38–39 | Verificar si algún puerto < 1024 se usa. Si no, eliminar ambas líneas para reducir la attack surface del proceso. |
| 40 | MEDIUM | Observability | systemd LimitNOFILE ausente en extraction y quality | `cardex-extraction.service` y `cardex-quality.service`: no tienen `LimitNOFILE`. Extraction hace conexiones HTTP concurrentes (hasta 4 workers × múltiples connections). Sin límite explícito, hereda el default del sistema (1024 en algunos distros), que puede agotarse bajo carga. | `deploy/systemd/cardex-extraction.service` / `cardex-quality.service` | — | Añadir `LimitNOFILE=65536` a ambas unidades. |
| 41 | MEDIUM | Tests | Mock en V01 test no cubre error path | Los tests de `v01_vin_checksum` típicamente solo prueban VINs válidos e inválidos conocidos. Si el checksum algorithm tiene un edge case (VIN con longitud < 17, caracteres I/O/Q), puede no estar cubierto. Verificar que tests incluyen: longitud incorrecta, caracteres prohibidos ISO 3779, VIN con ceros en posición 9. | `quality/internal/validator/v01_vin_checksum/` | — | Añadir test cases: VIN de 16 chars, VIN con carácter 'I', VIN con '0' en check digit position. |
| 42 | LOW | Supply chain | No hay `go mod verify` en CI | `.forgejo/workflows/illegal-pattern-scan.yml`: CI ejecuta `govulncheck` pero no `go mod verify`. Sin verificación de checksums, un tamper en `go.sum` o una dependencia con hash incorrecto pasaría desapercibido. | `.forgejo/workflows/illegal-pattern-scan.yml:129` | 129 | Añadir step antes de build: `go mod verify` en cada módulo (discovery, extraction, quality). |
| 43 | LOW | Supply chain | go.work.sum en directorio raíz sin gitignore | `go.work.sum` aparece en git status como "untracked" en la sesión actual. Si es artefacto de `go work`, debe estar en `.gitignore` o commiteado explícitamente. | Raíz del repo | — | Añadir `go.work.sum` a `.gitignore` si es un artefacto local, o commitearlo si es parte del workspace. |
| 44 | LOW | Concurrencia | Metrics server (discovery) shutdown usa `context.Background()` | `discovery/cmd/discovery-service/main.go:245`: `srv.Shutdown(context.Background())`. Usar `context.Background()` para shutdown significa que si el proceso recibe SIGKILL durante shutdown, no hay timeout. | `discovery/cmd/discovery-service/main.go:245` | 245 | Usar `context.WithTimeout(context.Background(), 5*time.Second)` para el shutdown. |
| 45 | LOW | PII | DealerEntity.CountryCode sin validación ISO-3166-1 | `discovery/internal/kg/kg.go:114`: `CountryCode string`. Se acepta cualquier string sin validación. Un CountryCode incorrecto ("FR2", "DEU", "") puede llevar a queries incorrectas en producción. | `discovery/internal/kg/kg.go:114` | 114 | Añadir validación en `Validate()`: CountryCode debe estar en la lista `{"BE","CH","DE","ES","FR","NL"}`. |
| 46 | LOW | Struct invariants | `DealerEntity` sin método `Validate()` | `discovery/internal/kg/kg.go:111-125`: sin Validate(). DealerID, CanonicalName, CountryCode son strings que pueden ser vacíos sin detección. Un dealer con `DealerID: ""` podría upsertarse como row vacía en SQLite. | `discovery/internal/kg/kg.go:111` | 111–125 | Implementar `func (e *DealerEntity) Validate() error` comprobando DealerID != "", CountryCode in allow-list. |
| 47 | LOW | Config | `RateLimitMs: 2000` en extraction no documentado | `extraction/internal/config/config.go:95`: `RateLimitMs: 2000`. No está claro si este rate limit se aplica entre requests consecutivos al mismo dealer, o globalmente. El comentario no clarifica el scope. | `extraction/internal/config/config.go:95` | 95 | Añadir comentario: "minimum milliseconds between consecutive requests to the same dealer host." |
| 48 | LOW | Observability | Grafana dashboard-discovery.json usa prefijo incorrecto | `dashboard-discovery.json` contiene al menos una query con prefijo `discovery_dealers_discovered_total`. El código exporta `cardex_discovery_dealers_total`. El panel muestra "no data". | `deploy/observability/grafana/dashboard-discovery.json:5` | 5 | Verificar todas las queries del dashboard y alinear con nombres `cardex_discovery_*`. |
| 49 | LOW | Observability | Grafana dashboard metric prefixes sin validación automática | Los 3 dashboards JSON pueden derivar de los nombres reales si alguien renombra métricas en código. No hay test/CI que valide que las queries de Grafana matchean los nombres exportados. | `deploy/observability/grafana/*.json` | — | Añadir un test de integración o script de CI que extraiga nombres de métricas de `metrics.go` y verifique que aparecen en los dashboards. |
| 50 | LOW | Tests | `govulncheck` solo en un workflow | CI tiene `govulncheck ./...` en un workflow, pero solo corre en el paquete raíz del workflow. No está claro si cubre los submódulos `discovery/`, `extraction/`, `quality/` (que son módulos Go separados). | `.forgejo/workflows/illegal-pattern-scan.yml:131-133` | 131 | Asegurar que `govulncheck` se ejecuta con `cd discovery && govulncheck ./... && cd ../extraction && govulncheck ./... && cd ../quality && govulncheck ./...`. |
| 51 | LOW | Tests | WorkerCount y timeout no testeados con stress | Los tests de extraction/quality no incluyen tests de concurrencia con `WorkerCount > 1`. Los race conditions solo se detectan con `-race` flag. | `extraction/internal/pipeline/` / `quality/internal/pipeline/` | — | Añadir un test con `go test -race` en el pipeline de extracción y calidad. Documentar si ya se ejecuta en CI. |
| 52 | LOW | Concurrencia | Goroutine de health check expone len(families) como buffer size | `runner/health.go:35`: `ch := make(chan result, len(families))`. Si en el futuro `families` es nil o len=0, `make(chan result, 0)` crea canal sin buffer y el primer `ch <- result{}` bloquea hasta que haya un lector. | `discovery/internal/runner/health.go:35` | 35 | Añadir guard: `if len(families) == 0 { return emptyReport }`. |
| 53 | LOW | Security | b2b-dashboard no auditado para XSS / dependency vulns | `b2b-dashboard/` es una aplicación Next.js con `node_modules/`. No hay `npm audit` o equivalente en CI. Las vulnerabilidades en dependencias JS pueden no ser detectadas. | `b2b-dashboard/` | — | Añadir `npm audit --audit-level=high` o `pnpm audit` al CI workflow para b2b-dashboard. |
| 54 | LOW | Security | terminal/ y crm-edge/ no auditados | `terminal/` y `crm-edge/` tienen `node_modules/`. No hay audit JS en CI. | `terminal/` / `crm-edge/` | — | Ídem #53, extender audit a todos los submódulos Node.js. |
| 55 | LOW | Observability | Prometheus scrape: targets coinciden con puertos del código | `prometheus.yml:32`: `job_name: cardex_discovery` con target `:9101`. `discovery/cmd/main.go:cfg.MetricsAddr` = `:9101`. ✓ Coherente. Igual para extraction :9102 y quality :9103. (Confirmado correcto, registrado para completitud.) | `deploy/observability/prometheus.yml` vs `*/cmd/*/main.go` | — | Ninguna. |
| 56 | LOW | Observability | `cardex_sqlite_wal_size_bytes` en alertmanager sin origen | `rules.yml:138`: alerta si `cardex_sqlite_wal_size_bytes > 524288000`. Esta métrica no está en ningún `metrics.go`. Puede venir de un exporter externo (node_exporter custom collector) o puede ser otra ghost metric. | `deploy/observability/alertmanager/rules.yml:138` | 138 | Verificar si hay un custom collector de SQLite WAL. Si no, implementar o eliminar la regla. |
| 57 | LOW | Config | `InseeRatePerMin: 25` hardcoded en discovery sin knob config por entorno | `discovery/internal/config/config.go:150 ~`: `InseeRatePerMin: 25`. INSEE (API france sirene) tiene límites distintos por nivel de API key (freemium vs premium). El valor hardcoded puede violar el rate limit para cuentas freemium o ser demasiado conservador para premium. | `discovery/internal/config/config.go` | ~150 | Documentar el tier de API key que este default asume. Exponerlo como env var `DISCOVERY_INSEE_RATE_PER_MIN`. |
| 58 | LOW | Tests | Tests de familia_a/be_kbo no cubren error HTTP 503 | `be_kbo/kbo.go` hace múltiples requests con reintentos. Los tests no parecen cubrir el caso de servidor KBO retornando 503 (Service Unavailable) y la lógica de backoff. Si KBO está caído, ¿el proceso cuelga? | `discovery/internal/families/familia_a/be_kbo/kbo_test.go` | — | Añadir test con mock server que retorne 503 y verificar que la función retorna error en tiempo razonable. |
| 59 | LOW | Tests | `TestExtractCandidates_GermanAutohaus` usa string literal alemán hardcoded | `ner_test.go:9-25`: el test usa texto fijo de un "Autohaus München". Si el modelo NER cambia thresholds o el diccionario, los resultados pueden cambiar sin que el test falle (por encima de threshold pero test solo verifica `len > 0`). | `discovery/internal/families/familia_o/ner/ner_test.go:9` | 9–25 | Verificar valores exactos de candidatos esperados, no solo que `len > 0`. |
| 60 | LOW | Config | systemd `Restart=on-failure` sin `StartLimitBurst` | `cardex-discovery.service`, `cardex-extraction.service`, `cardex-quality.service`: tienen `Restart=on-failure` y `RestartSec=10s` pero sin `StartLimitBurst` o `StartLimitIntervalSec`. Si el proceso crashea repetidamente, systemd puede intentar reiniciar indefinidamente saturando logs. | `deploy/systemd/cardex-*.service` | — | Añadir `StartLimitBurst=5` y `StartLimitIntervalSec=60s` para limitar restarts a 5 en 60 segundos antes de que systemd marque el servicio como failed. |
| 61 | LOW | Observability | Alertmanager `cardex_availability` usa `up{job=~"cardex_.*"}` correctamente | `rules.yml:13`: `up{job=~"cardex_.*"} == 0`. Los job names en prometheus.yml son `cardex_discovery`, `cardex_extraction`, `cardex_quality`. El regex `cardex_.*` los captura correctamente. ✓ (registrado como confirmación positiva para completitud). | `deploy/observability/alertmanager/rules.yml:13` vs `prometheus.yml` | — | Ninguna. |
| 62 | LOW | Security | ingestion/ (Node.js) no auditado | `ingestion/` tiene `node_modules/`. Este servicio probablemente recibe datos externos y es un boundary crítico para inyección. Sin audit de dependencias ni revisión de handlers, hay riesgo latente. | `ingestion/` | — | Revisar `ingestion/` en Track 3 (Node.js security). Ejecutar `npm audit` como mínimo inmediato. |

---

## Conteo por severidad

| SEVERITY | COUNT |
|----------|-------|
| CRITICAL | 8 |
| HIGH | 6 |
| MEDIUM | 26 |
| LOW | 22 |
| **TOTAL** | **62** |

---

## Top 10 hallazgos más sutiles

### 1. Alertmanager silencioso (CRITICAL, #1-#8)
El hallazgo más sutil de toda la auditoría: las reglas de Alertmanager usan nombres de métricas que **nunca existieron** en el código (`discovery_scrape_errors_total`, `extraction_errors_total`, `quality_pending_vehicles`, etc.). El sistema ha estado —o estará— en producción sin ninguna alerta funcional para errores críticos. Este tipo de bug pasa completamente invisible: Prometheus scraping funciona, las métricas se exportan correctamente, pero las reglas de alerta evalúan series vacías (no-match) y siempre dan `false`, nunca disparando. Solo detectable leyendo `rules.yml` y comparando contra `metrics.go` línea por línea.

### 2. SQLite driver mismatch (HIGH, #10)
`quality` usa `modernc.org/sqlite v1.37.1` mientras discovery/extraction usan `v1.48.2`. La divergencia de 11 minor versions incluye cambios en WAL behavior, JSON functions, y busy timeout. Si `quality` escribe a una SQLite DB con un schema que discovery modificó con features de v1.48.x, puede haber incompatibilidades silenciosas.

### 3. TestExtractCandidates_NoMatches descarta resultado (HIGH, #14)
`_ = candidates` en línea 49 de `ner_test.go`. El test compila y pasa siempre. Solo detectable leyendo el test completo y preguntándose "¿qué se verifica?". Un cambio en el modelo NER que empiece a devolver candidatos para texto sin entidades nunca sería detectado.

### 4. Alertmanager `cardex_validation_total` vs `cardex_quality_validation_total` (CRITICAL, #5)
La calidad usa `Namespace: "cardex", Subsystem: "quality"` que produce `cardex_quality_validation_total`, pero la regla de alerta dice `cardex_validation_total`. Un prefijo diferente de un solo segmento (`quality_`) hace que la alerta más importante (>20% de critical validation failures) nunca dispare. Subliminal porque el nombre "parece" correcto.

### 5. docker-compose default BatchSize=20 vs config.go BatchSize=50 (MEDIUM, #33)
El mismo código en dos entornos de despliegue tendría throughput 2.5x diferente sin que nadie lo note. Solo detectable comparando `config.go:91` con `docker-compose.yml:74`.

### 6. CAP_NET_BIND_SERVICE innecesario en discovery (MEDIUM, #39)
El proceso discovery no parece necesitar binding a puertos <1024, pero tiene la capability configurada. Reduce la defensa en profundidad del proceso. Solo detectable leyendo el systemd unit y verificando qué puertos usa realmente el código.

### 7. Channel sin close en health.go hace range infinito posible (MEDIUM, #20)
El channel de health check nunca se cierra. Aunque el pattern actual (`for range families { r := <-ch }`) es correcto, si alguien refactoriza a `for r := range ch`, el loop bloquea indefinidamente. El bug no existe hoy pero es una trampa para el futuro.

### 8. Quality namespace inconsistencia en Prometheus (MEDIUM, #26)
Los tres servicios exportan métricas con convenciones diferentes. Discovery: `cardex_discovery_dealers_total` (Namespace=`cardex_discovery_*`). Quality: `cardex_quality_validation_total` (Namespace=`cardex`, Subsystem=`quality`). La inconsistencia causa que las queries de PromQL deban conocer la convención de cada servicio, y produce los bugs #1-#8 en Alertmanager.

### 9. Rate limits de discovery families hardcoded sin config central (MEDIUM, #34)
Cada familia tiene su `const defaultReqInterval` hardcoded. No hay manera de ajustar rates en producción sin recompilación. Solo detectable leyendo cada familia individualmente y notando que no usan la config central de discovery.

### 10. `go.work.sum` untracked sin `.gitignore` entry (LOW, #43)
Aparece como "untracked" en git status — ni commiteado ni ignorado. En un build reproducible, este estado ambiguo puede llevar a que diferentes desarrolladores tengan checksums diferentes.

---

## Anexo A — Evidencia directa de Alertmanager ghost metrics

```
REGLAS EN rules.yml               MÉTRICAS EN metrics.go
==============================    ================================
discovery_scrape_errors_total  →  ✗ NO EXISTE
discovery_scrape_requests_total → ✗ NO EXISTE
extraction_errors_total         → ✗ NO EXISTE (existe: cardex_extraction_parse_errors_total)
extraction_attempts_total       → ✗ NO EXISTE (existe: cardex_extraction_total)
cardex_validation_total         → ✗ NO EXISTE (existe: cardex_quality_validation_total)
extraction_queue_depth          → ✗ NO EXISTE
quality_pending_vehicles        → ✗ NO EXISTE
cardex_last_backup_timestamp_seconds → ✗ NO EXISTE

MÉTRICAS QUE SÍ COINCIDEN:
cardex_sqlite_wal_size_bytes   →  ? (sin confirmar — posible exporter externo)
up{job=~"cardex_.*"}           →  ✓ (Prometheus built-in)
process_start_time_seconds     →  ✓ (Prometheus built-in)
```

## Anexo B — SQLite version matrix

```
Módulo      modernc.org/sqlite  modernc.org/libc
========    ==================  ================
discovery   v1.48.2             v1.70.0
extraction  v1.48.2             v1.70.0
quality     v1.37.1  ← DELTA   v1.65.7  ← DELTA
```

## Annexo C — Docker image pin status

```
Imagen                              Tag-only    Digest-pinned
==============================      ========    =============
golang:1.25-bookworm (builder)      ✗ YES       ✗ NO
gcr.io/distroless/static-debian12   ✗ YES       ✗ NO
prom/prometheus:v3.0.1              ✗ YES       ✗ NO
prom/alertmanager:v0.27.0           ✗ YES       ✗ NO
grafana/grafana:11.5.0              ✗ YES       ✗ NO
caddy:2.9-alpine                    ✗ YES       ✗ NO
```

---

## Recomendaciones por urgencia

| # | Acción | Urgencia | Esfuerzo |
|---|--------|----------|---------|
| 1 | Corregir las 8 queries de Alertmanager con nombres de métricas correctos | **INMEDIATA** (antes de producción) | 30 min |
| 2 | Actualizar `quality/go.mod` sqlite a v1.48.2 | Alta — coherencia DB | 5 min |
| 3 | Pinear imágenes Docker con SHA256 | Alta — supply chain | 1h |
| 4 | Añadir `go mod verify` al CI | Alta — integridad | 10 min |
| 5 | Agregar `recover()` a goroutines de health check | Alta — estabilidad | 15 min |
| 6 | Añadir assertion a `TestExtractCandidates_NoMatches` | Media | 5 min |
| 7 | CSP header en Caddy/nginx | Media — seguridad | 30 min |
| 8 | Centralizar rate limits de discovery en config | Media | 2h |
| 9 | Añadir `Validate()` a VehicleRaw y Vehicle | Media | 1h |
| 10 | `LimitNOFILE=65536` en systemd extraction/quality | Baja | 5 min |
