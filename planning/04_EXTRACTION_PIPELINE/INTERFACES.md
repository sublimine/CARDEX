# Interfaces Go — Extraction Pipeline

## Identificador
- Documento: EXTRACTION_INTERFACES
- Versión: 1.0
- Fecha: 2026-04-14
- Estado: AUTORITATIVO

## Propósito
Define las interfaces Go canónicas que todas las estrategias E01-E12 deben implementar. La uniformidad de interfaz permite al orquestador componer estrategias dinámicamente y añadir estrategias E13+ sin refactorización.

## Package y ubicación

```
services/pipeline/extraction/
├── interfaces.go      ← definiciones canónicas (este documento)
├── orchestrator.go    ← ExtractionOrchestrator
├── result.go          ← tipos de resultado
├── strategies/
│   ├── e01_jsonld/
│   ├── e02_cms_rest/
│   ├── e03_sitemap/
│   ├── e04_rss_atom/
│   ├── e05_dms_api/
│   ├── e06_microdata/
│   ├── e07_playwright_xhr/
│   ├── e08_pdf/
│   ├── e09_csv_excel/
│   ├── e10_mobile_api/
│   ├── e11_edge_onboarding/
│   └── e12_manual_review/
└── dead_letter/
```

## Interfaces

```go
package extraction

import (
    "context"
    "time"
)

// ExtractionStrategy es la interfaz que toda estrategia E01-E12 (y futuras E13+) debe implementar.
// El orquestador opera exclusivamente a través de esta interfaz.
type ExtractionStrategy interface {
    // ID devuelve el identificador canónico ("E01", "E02", ...).
    ID() string

    // Name devuelve el nombre descriptivo ("JSON-LD Schema.org", ...).
    Name() string

    // Applicable realiza un pre-check rápido (sin I/O de red) para determinar
    // si esta estrategia es candidata para el dealer dado.
    // Debe ser O(1) o muy barato. El orquestador lo llama antes de Extract.
    Applicable(dealer Dealer) bool

    // Extract ejecuta la extracción completa para el dealer.
    // Debe respetar ctx.Done() para cancelación.
    // Nunca debe hacer I/O que viole robots.txt o ToS del dealer.
    Extract(ctx context.Context, dealer Dealer) (*ExtractionResult, error)

    // Priority determina el orden en la cascada. Mayor valor = se intenta primero.
    // E01=1200, E02=1100, E03=1000, E04=900, E05=1050, E06=800,
    // E07=700, E08=300, E09=400, E10=200, E11=100, E12=0
    Priority() int
}

// ExtractionResult encapsula el resultado de una estrategia de extracción.
type ExtractionResult struct {
    DealerID string
    Strategy string // ID de la estrategia que produjo este resultado

    // Vehicles contiene los vehículos extraídos en formato raw (pre-normalización).
    Vehicles []VehicleRaw

    // PartialSuccess indica que se extrajeron algunos datos pero faltan campos críticos.
    PartialSuccess bool

    // FullSuccess indica que todos los campos críticos están presentes en todos los vehículos.
    FullSuccess bool

    // FieldsExtracted lista los campos que se extrajeron exitosamente.
    FieldsExtracted []string

    // FieldsMissing lista los campos críticos que no se pudieron extraer.
    FieldsMissing []string

    // NextFallback, si no nil, sugiere la siguiente estrategia a intentar.
    // El orquestador puede o no respetar esta sugerencia.
    NextFallback *string

    ExtractedAt time.Time
    SourceURL   string
    SourceCount int // número de páginas/endpoints consultados

    // Errors contiene errores no fatales encontrados durante la extracción.
    // Un resultado puede tener Errors y ser PartialSuccess simultáneamente.
    Errors []ExtractionError
}

// ExtractionError captura un error con contexto de diagnóstico.
type ExtractionError struct {
    Code    string // "HTTP_403", "ROBOTS_DISALLOW", "PARSE_ERROR", "TIMEOUT", etc.
    Message string
    URL     string
    Fatal   bool
}

// VehicleRaw contiene los campos de un vehículo en formato raw post-extracción,
// pre-normalización por el quality pipeline (V01-V20).
// Todos los campos son punteros para distinguir "ausente" de "cero/vacío".
type VehicleRaw struct {
    // Facts — no copyrightable, base del modelo índice-puntero
    VIN          *string
    Make         *string
    Model        *string
    Year         *int
    Mileage      *int    // km
    FuelType     *string // "gasoline"|"diesel"|"hybrid"|"electric"|"lpg"|"cng"|"hydrogen"
    Transmission *string // "manual"|"automatic"|"semi-automatic"
    PowerKW      *int
    BodyType     *string // "sedan"|"hatchback"|"suv"|"estate"|"coupe"|"convertible"|"van"|"pickup"
    Color        *string // color exterior normalizable
    Doors        *int
    Seats        *int

    // Precio — en moneda original, conversión a EUR en normalización
    PriceNet    *float64
    PriceGross  *float64
    Currency    *string // ISO 4217
    VATMode     *string // "net"|"gross"|"unknown"

    // Punteros (modelo índice — nunca se copian las imágenes ni descripciones)
    SourceURL       string   // URL canónica del listing en el site del dealer
    SourceListingID string   // ID del listing en la plataforma de origen
    ImageURLs       []string // lista de URLs de imágenes — punteros, no copias

    // Equipment y extras
    Equipment        []string               // vocabulario controlado, normalizado post-extracción
    AdditionalFields map[string]interface{} // campos específicos de la estrategia no normalizados aún
}

// Dealer es el input del orquestador para decidir qué estrategias intentar.
// Proviene del knowledge graph (dealer_entity + dealer_web_presence + CMS/DMS signals).
type Dealer struct {
    ID              string
    Domain          string
    URLRoot         string
    CountryCode     string // DE|FR|ES|BE|NL|CH
    PlatformType    string // "CMS_WORDPRESS"|"CMS_SHOPIFY"|"DMS_HOSTED"|"NATIVE"|"UNKNOWN"
    CMSDetected     string // plugin/theme fingerprinted (Familia D)
    DMSProvider     string // si DMS_HOSTED (Familia E): "dealersocket"|"cdk"|"autobiz"|"kerridge"|etc.
    ExtractionHints []string
    RobotsTxtURL    string
    SitemapURL      string
    RSSFeedURL      string
}

// ExtractionOrchestrator compone y ejecuta las estrategias en orden de prioridad descendente.
type ExtractionOrchestrator struct {
    strategies []ExtractionStrategy
}

// NewOrchestrator construye el orquestador con todas las estrategias registradas,
// ordenadas automáticamente por Priority() descendente.
func NewOrchestrator(strategies ...ExtractionStrategy) *ExtractionOrchestrator {
    o := &ExtractionOrchestrator{strategies: strategies}
    o.sortByPriority()
    return o
}

// ExtractForDealer ejecuta la cascada de estrategias para un dealer dado.
// Retorna el primer resultado exitoso (PartialSuccess o FullSuccess).
// Si ninguna estrategia produce resultado, retorna ExtractionResult con FullSuccess=false
// y NextFallback apuntando a "E11" o "E12" según el diagnóstico.
func (o *ExtractionOrchestrator) ExtractForDealer(ctx context.Context, d Dealer) (*ExtractionResult, error) {
    var lastResult *ExtractionResult

    for _, strategy := range o.strategies {
        if !strategy.Applicable(d) {
            continue
        }

        result, err := strategy.Extract(ctx, d)
        if err != nil {
            // Error fatal de estrategia (no del dealer) — log y continuar
            continue
        }

        lastResult = result

        if result.FullSuccess || result.PartialSuccess {
            return result, nil
        }

        // Si la estrategia sugiere un fallback específico, honrarlo si está disponible
        if result.NextFallback != nil {
            if next := o.findByID(*result.NextFallback); next != nil {
                if next.Applicable(d) {
                    fallbackResult, ferr := next.Extract(ctx, d)
                    if ferr == nil && (fallbackResult.FullSuccess || fallbackResult.PartialSuccess) {
                        return fallbackResult, nil
                    }
                }
            }
        }
    }

    // Todas las estrategias automáticas fallaron → enrutar a dead letter
    if lastResult == nil {
        lastResult = &ExtractionResult{
            DealerID:     d.ID,
            PartialSuccess: false,
            FullSuccess:  false,
        }
    }
    e11 := "E11"
    lastResult.NextFallback = &e11
    return lastResult, nil
}

func (o *ExtractionOrchestrator) sortByPriority() {
    // sort.Slice sobre o.strategies por Priority() descendente
}

func (o *ExtractionOrchestrator) findByID(id string) ExtractionStrategy {
    for _, s := range o.strategies {
        if s.ID() == id {
            return s
        }
    }
    return nil
}
```

## Constantes de prioridad

```go
const (
    PriorityE01 = 1200 // JSON-LD Schema.org — máxima prioridad
    PriorityE02 = 1100 // CMS REST endpoint
    PriorityE05 = 1050 // DMS hosted API (alta prioridad para ese segmento)
    PriorityE03 = 1000 // Sitemap XML
    PriorityE04 = 900  // RSS/Atom
    PriorityE06 = 800  // Microdata/RDFa
    PriorityE07 = 700  // XHR/AJAX discovery
    PriorityE09 = 400  // CSV/Excel feeds
    PriorityE08 = 300  // PDF catalog
    PriorityE10 = 200  // Mobile app API
    PriorityE11 = 100  // Edge onboarding
    PriorityE12 = 0    // Manual review
)
```

## Campos críticos definidos

Los campos que deben estar presentes para que un `VehicleRaw` sea `FullSuccess`:

```go
var CriticalFields = []string{
    "Make",
    "Model",
    "Year",
    "PriceNet",    // o PriceGross si VATMode lo justifica
    "SourceURL",
    "ImageURLs",   // al menos 1 URL
}
```

Un `VehicleRaw` que tiene todos los `CriticalFields` pero le faltan campos secundarios (Mileage, Color, PowerKW) cuenta como `PartialSuccess`. Un resultado donde >80% de los vehículos son `FullSuccess` se clasifica el `ExtractionResult` global como `FullSuccess`.

## Contrato de seguridad

Cada implementación de `ExtractionStrategy` DEBE:

1. Leer `dealer.RobotsTxtURL` y verificar que el path objetivo no está en `Disallow` antes de cualquier request.
2. Usar únicamente `User-Agent: CardexBot/1.0 (+https://cardex.io/bot)`.
3. Respetar `Crawl-delay` si presente en robots.txt.
4. No usar curl_cffi, playwright-stealth, ni ninguna técnica de la blacklist.
5. Registrar `legal_basis` en cada request: `"sitemap_implicit_license"`, `"schema_org_syndication"`, `"eu_data_act_delegation"`, etc.

Violaciones de este contrato son bloqueadas por el linter CI introducido en Fase 0.
