# 03 — Component Detail (C4 Level 3)

## Identificador
- Nivel C4: Component, Fecha: 2026-04-14, Estado: DOCUMENTADO

## Organización del repositorio Go

```
cardex/
├── cmd/
│   ├── discovery/      → main.go del Discovery Service
│   ├── extraction/     → main.go del Extraction Service
│   ├── quality/        → main.go del Quality Service
│   ├── nlg/            → main.go del NLG batch worker
│   ├── index/          → main.go del Index Writer Service
│   ├── api/            → main.go del API Service
│   └── sse/            → main.go del SSE Gateway
├── internal/
│   ├── discovery/      → lógica de familias A-O
│   ├── extraction/     → estrategias E01-E12
│   ├── quality/        → validators V01-V20
│   ├── nlg/            → NLG pipeline + llama.cpp bridge
│   ├── index/          → escritura OLTP + OLAP
│   ├── api/            → handlers HTTP + query engine
│   ├── graph/          → knowledge graph: CRUD, dedup, confidence
│   ├── nats/           → wrapper NATS embedded
│   ├── metrics/        → Prometheus registry compartida
│   └── config/         → carga de config via env + YAML
├── pkg/
│   ├── vin/            → VIN validation + checksum ISO 3779
│   ├── geo/            → haversine, geocoder wrapper
│   ├── fx/             → FX rates reader
│   ├── equipment/      → normalizer vocabulario V18
│   └── crawler/        → HTTP client con CardexBot UA, retry, rate limit
└── scripts/
    ├── seed/           → bootstrap NHTSA mirror, MaxMind download
    └── deploy/         → rsync + systemctl restart
```

## Discovery Service — componentes internos

```go
// internal/discovery/

// FamilyRunner — interfaz que implementa cada familia A-O
type FamilyRunner interface {
    ID() string                    // "A", "B", ..., "O"
    Name() string
    Run(ctx context.Context, country string) ([]DealerCandidate, error)
    EstimatedDuration() time.Duration
    LastRunAt() time.Time
}

// Orchestrator — ejecuta familias en paralelo con rate limiting
type Orchestrator struct {
    families []FamilyRunner
    graph    *graph.KnowledgeGraph
    nats     *nats.Client
    metrics  *metrics.Registry
}

func (o *Orchestrator) RunCycle(ctx context.Context, countries []string) (*CycleReport, error)
func (o *Orchestrator) RunFamily(ctx context.Context, family FamilyRunner, country string) error

// Deduplicator — fusiona candidatos con entidades existentes
type Deduplicator struct {
    graph *graph.KnowledgeGraph
}

func (d *Deduplicator) Process(candidate DealerCandidate) (*graph.DealerEntity, MergeAction, error)
// MergeAction: CREATE | MERGE_VAT | MERGE_DOMAIN | MERGE_NAME_GEO | CANDIDATE

// SaturationTracker — nivel de saturación por familia+país
type SaturationTracker struct {
    db *sql.DB
}

func (s *SaturationTracker) RecordCycleResult(family, country string, delta int) error
func (s *SaturationTracker) GetSaturationLevel(country string) SaturationLevel
```

## Extraction Service — componentes internos

```go
// internal/extraction/

// Orchestrator — cascada E01-E12 por dealer
type Orchestrator struct {
    strategies []ExtractionStrategy  // ver INTERFACES.md en 04_EXTRACTION_PIPELINE
    nats       *nats.Client
    graph      *graph.KnowledgeGraph
    metrics    *metrics.Registry
}

func (o *Orchestrator) ExtractForDealer(ctx context.Context, dealer graph.DealerEntity) (*ExtractionResult, error)
func (o *Orchestrator) ProcessQueue(ctx context.Context) error  // consume NATS dealer_ready queue

// PlaywrightRunner — wrapper del browser headless
type PlaywrightRunner struct {
    browser playwright.Browser  // singleton, reutilizado
    ua      string              // "CardexBot/1.0 (+https://cardex.io/bot)"
}

func (r *PlaywrightRunner) FetchPage(ctx context.Context, url string) (*PageContent, error)
func (r *PlaywrightRunner) InterceptXHR(ctx context.Context, url string, patterns []string) ([]XHRCapture, error)

// StrategyRegistry — resolución de estrategias por dealer
type StrategyRegistry struct {
    strategies map[string]ExtractionStrategy
}

func (r *StrategyRegistry) Applicable(dealer graph.DealerEntity) []ExtractionStrategy  // ordenados por Priority()
func (r *StrategyRegistry) Register(s ExtractionStrategy)

// RateLimiter — por dominio, respeta robots.txt Crawl-Delay
type RateLimiter struct {
    limiters map[string]*rate.Limiter  // domain → token bucket
    mu       sync.RWMutex
}

func (rl *RateLimiter) Wait(ctx context.Context, domain string) error
func (rl *RateLimiter) SetRate(domain string, reqPerSec float64)
```

## Quality Service — componentes internos

```go
// internal/quality/

// Pipeline — ejecuta V01-V20 en orden de fase
type Pipeline struct {
    validators []Validator  // ver INTERFACES.md en 05_QUALITY_PIPELINE
    graph      *graph.KnowledgeGraph
    nats       *nats.Client
    metrics    *metrics.Registry
}

func (p *Pipeline) Validate(ctx context.Context, record *VehicleRecord) (*PipelineOutcome, error)
func (p *Pipeline) ProcessQueue(ctx context.Context) error

// ValidatorRegistry — resolución por ID
type ValidatorRegistry struct {
    validators map[string]Validator
}

func (r *ValidatorRegistry) Get(id string) (Validator, bool)
func (r *ValidatorRegistry) Ordered() []Validator  // ordered by phase: VIN → Image → Price → Enrichment → Final

// ManualReviewQueue — interfaz con la cola de revisión manual
type ManualReviewQueue struct {
    db *sql.DB
}

func (q *ManualReviewQueue) Enqueue(record *VehicleRecord, reason string) error
func (q *ManualReviewQueue) Pending() ([]*ReviewItem, error)
func (q *ManualReviewQueue) Approve(vehicleID string, operatorNote string) error
func (q *ManualReviewQueue) Reject(vehicleID string, reason string) error

// DLQ — dead-letter queue para registros FAIL BLOCKING
type DeadLetterQueue struct {
    db   *sql.DB
    nats *nats.Client
}

func (q *DeadLetterQueue) Enqueue(record *VehicleRecord, outcome *PipelineOutcome) error
func (q *DeadLetterQueue) Retry(vehicleID string) error  // re-ingesta en quality queue
func (q *DeadLetterQueue) Purge(olderThan time.Duration) error
```

## NLG Service — componentes internos

```go
// internal/nlg/

// BatchProcessor — worker nocturno que consume nlg_pending queue
type BatchProcessor struct {
    generator   *DescriptionGenerator
    db          *sql.DB
    nats        *nats.Client
    metrics     *metrics.Registry
    grammarCheck *LanguageToolClient
}

func (p *BatchProcessor) ProcessQueue(ctx context.Context) error
func (p *BatchProcessor) ProcessRecord(ctx context.Context, vehicleID string) error

// DescriptionGenerator — wrapper llama.cpp
type DescriptionGenerator struct {
    model  *llama.Model  // llama.cpp Go bindings (CGO)
    config GeneratorConfig
}

func (g *DescriptionGenerator) Generate(ctx context.Context, facts DescriptionFacts, lang string) (string, error)
func (g *DescriptionGenerator) ValidateOutput(desc string, facts DescriptionFacts) error  // hallucination check
func (g *DescriptionGenerator) TemplateFallback(facts DescriptionFacts, lang string) string

// LanguageToolClient — REST client para LanguageTool local
type LanguageToolClient struct {
    baseURL string  // "http://localhost:8010/v2"
}

func (c *LanguageToolClient) Check(text, lang string) ([]GrammarIssue, error)

// PriorityQueue — ordena registros pendientes por importancia del dealer
type PriorityQueue struct {
    db *sql.DB
}

func (q *PriorityQueue) NextBatch(size int) ([]string, error)  // vehicleIDs ordenados por dealer.confidence_score DESC
```

## Index Writer Service — componentes internos

```go
// internal/index/

// Writer — escribe registros PASS en OLTP + OLAP
type Writer struct {
    oltp    *sql.DB      // SQLite OLTP
    olap    *duckdb.DB   // DuckDB OLAP
    nats    *nats.Client
    metrics *metrics.Registry
}

func (w *Writer) PublishVehicle(ctx context.Context, record *VehicleRecord) error
func (w *Writer) ExpireVehicle(ctx context.Context, vehicleID string, reason ExpireReason) error
func (w *Writer) ProcessQueue(ctx context.Context) error

// TTLManager — gestiona expiración de listings
type TTLManager struct {
    db     *sql.DB
    nats   *nats.Client
}

func (m *TTLManager) RunExpiration(ctx context.Context) error  // cron cada hora
func (m *TTLManager) ExtendTTL(vehicleID string, extension time.Duration) error

// DeltaDetector — detecta cambios en registros ya indexados (via fingerprint SHA256)
type DeltaDetector struct {
    db *sql.DB
}

func (d *DeltaDetector) HasChanged(vehicleID string, newFingerprint string) (bool, error)
func (d *DeltaDetector) UpdateFingerprint(vehicleID string, fingerprint string) error
```

## API Service — componentes internos

```go
// internal/api/

// Router — chi router con middleware chain
type Router struct {
    db      *duckdb.DB
    oltp    *sql.DB
    nats    *nats.Client
    metrics *metrics.Registry
}

func (r *Router) Handler() http.Handler

// VehicleQueryHandler — queries B2B sobre DuckDB OLAP
type VehicleQueryHandler struct {
    db *duckdb.DB
}

func (h *VehicleQueryHandler) Search(w http.ResponseWriter, r *http.Request)
// Query params: make, model, year_from/to, mileage_max, price_min/max, country, fuel, transmission, page, per_page

func (h *VehicleQueryHandler) GetVehicle(w http.ResponseWriter, r *http.Request)   // GET /vehicles/:id
func (h *VehicleQueryHandler) GetVehicleByVIN(w http.ResponseWriter, r *http.Request)  // GET /vehicles/vin/:vin

// EdgeIngestionHandler — recibe inventario de dealers E11
type EdgeIngestionHandler struct {
    nats    *nats.Client
    graph   *graph.KnowledgeGraph
}

func (h *EdgeIngestionHandler) IngestInventory(w http.ResponseWriter, r *http.Request)  // POST /edge/inventory

// AuthMiddleware — API key B2B (no OAuth en fase inicial)
type AuthMiddleware struct {
    db *sql.DB
}

func (m *AuthMiddleware) Handler(next http.Handler) http.Handler

// RateLimitMiddleware — por API key, 1000 req/hora en free tier
type RateLimitMiddleware struct {
    limiters map[string]*rate.Limiter
    mu       sync.RWMutex
}
```

## Knowledge Graph — componentes internos (paquete pkg compartido)

```go
// internal/graph/

// KnowledgeGraph — abstracción sobre SQLite OLTP
type KnowledgeGraph struct {
    db *sql.DB
}

// Dealer operations
func (g *KnowledgeGraph) GetDealer(dealerID string) (*DealerEntity, error)
func (g *KnowledgeGraph) UpsertDealer(dealer *DealerEntity) error
func (g *KnowledgeGraph) GetDealerByVAT(vat string) (*DealerEntity, error)
func (g *KnowledgeGraph) GetDealerByDomain(domain string) (*DealerEntity, error)
func (g *KnowledgeGraph) GetDealerLocation(dealerID string) (*DealerLocation, error)
func (g *KnowledgeGraph) UpdateConfidenceScore(dealerID string, score float64) error

// Vehicle operations
func (g *KnowledgeGraph) GetVehicleByVIN(vin string) ([]*VehicleSourceWitness, error)
func (g *KnowledgeGraph) GetPriceStats(make, model string, year int, country string) (*PriceStats, error)
func (g *KnowledgeGraph) UpsertVehicle(record *VehicleRecord) error
func (g *KnowledgeGraph) SetVehicleStatus(vehicleID string, status VehicleStatus) error

// Pipeline operations
func (g *KnowledgeGraph) SavePipelineResult(vehicleID string, result *ValidationResult) error
func (g *KnowledgeGraph) GetPipelineHistory(vehicleID string) ([]*ValidationResult, error)
```
