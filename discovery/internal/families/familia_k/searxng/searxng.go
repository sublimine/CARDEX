// Package searxng implements sub-technique K.1 — SearXNG meta-search (pan-EU).
//
// SearXNG is a privacy-respecting, self-hostable meta-search engine that
// federates 70+ underlying search engines. CARDEX uses public SearXNG instances
// as a discovery layer to find dealer domains not yet in the KG.
//
// # Strategy
//
// For each target country, ~10 query templates are submitted to 3–5 public
// SearXNG instances (rotated to distribute load). Each query returns up to 20
// results. The response URL list is cross-checked against dealer_web_presence:
//
//   - Known domain   → RecordDiscovery (confirmation signal)
//   - Unknown domain → UpsertWebPresence as DOMAIN_FROM_SEARCH (low-confidence candidate)
//
// Total budget: ~10 queries × 6 countries = 60 queries/session, at 1 query/5s
// per instance = ~5 min/session.
//
// # Checkpointing
//
// The last processed query index per country is stored in the KG processing_state
// table (key = "searxng:{country}:last_index") so that interrupted runs resume
// from where they left off.
//
// # SearXNG JSON API
//
// GET {instance}/search?q={query}&format=json&language={lang}&safesearch=0
//
// Response:
//
//	{
//	  "query": "...",
//	  "number_of_results": 123,
//	  "results": [
//	    {"url": "https://example.com", "title": "...", "content": "...", "score": 1.2}
//	  ]
//	}
//
// robots.txt: public SearXNG instances explicitly allow /search?format=json
// (the JSON endpoint is designed for programmatic use). Verified on searx.be,
// searx.info, and opnxng.com.
//
// Rate limiting: 1 query / 5 s per instance, rotated across instances.
// BaseWeights["K"] = 0.05.
package searxng

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const searchMetaJSON = `{"low_confidence":true,"source":"searxng","pending_cross_validation":true}`

const (
	familyID    = "K"
	subTechID   = "K.1"
	subTechName = "SearXNG meta-search (pan-EU)"

	defaultReqInterval = 5 * time.Second
	maxResultsPerQuery = 20

	cardexUA = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
)

// defaultInstances is the list of well-maintained public SearXNG instances that
// expose the JSON API. Verified available as of 2026-04-15.
var defaultInstances = []string{
	"https://searx.be",
	"https://searx.info",
	"https://opnxng.com",
	"https://search.ononoki.org",
	"https://searxng.site",
}

// queryTemplates maps ISO country codes to ~10 query strings designed to surface
// automotive dealer operator websites for that market.
var queryTemplates = map[string][]string{
	"DE": {
		`"Autohaus" site:.de`,
		`"Gebrauchtwagen Händler" site:.de`,
		`"Kfz-Handel" site:.de`,
		`"Autohandel" site:.de`,
		`"Fahrzeughandel" site:.de`,
		`"Neuwagen Händler" site:.de`,
		`"Automobilhandel" site:.de`,
		`"Auto Ankauf Verkauf" site:.de`,
		`"Fahrzeugbetrieb" site:.de`,
		`"Kfz-Betrieb Gebrauchtwagenhandel" site:.de`,
	},
	"FR": {
		`"concessionnaire automobile" site:.fr`,
		`"garage automobile" site:.fr`,
		`"vente voiture occasion" site:.fr`,
		`"mandataire automobile" site:.fr`,
		`"vente véhicules occasions" site:.fr`,
		`"reprise véhicule occasion" site:.fr`,
		`"commerce véhicules d'occasion" site:.fr`,
		`"garage multi-marques" site:.fr`,
		`"vente VO" "véhicules d'occasion" site:.fr`,
		`"concessionnaire auto agréé" site:.fr`,
	},
	"ES": {
		`"concesionario automóviles" site:.es`,
		`"compraventa vehículos" site:.es`,
		`"venta coches usados" site:.es`,
		`"vehículos segunda mano" site:.es`,
		`"venta vehículos de ocasión" site:.es`,
		`"automoción" "stock vehículos" site:.es`,
		`"compra venta coches" site:.es`,
		`"taller concesionario" site:.es`,
		`"dealer automóviles" site:.es`,
		`"ocasión certificada" site:.es`,
	},
	"NL": {
		`"autobedrijf" site:.nl`,
		`"autohandel" site:.nl`,
		`"occasions dealer" site:.nl`,
		`"tweedehands auto" site:.nl`,
		`"autodealer" site:.nl`,
		`"autoverkoop" site:.nl`,
		`"gebruikte auto" site:.nl`,
		`"auto occasions" site:.nl`,
		`"erkend autobedrijf" site:.nl`,
		`"autobedrijf tweedehands" site:.nl`,
	},
	"BE": {
		`"autohandelaar" site:.be`,
		`"garage automobile Belgique" site:.be`,
		`"voitures d'occasion" site:.be`,
		`"autohandel" site:.be`,
		`"tweedehands wagens" site:.be`,
		`"vente véhicules occasion Belgique" site:.be`,
		`"autocentrum" site:.be`,
		`"wagens te koop" site:.be`,
		`"concessionnaire automobile Belgique" site:.be`,
		`"autoverkoop" site:.be`,
	},
	"CH": {
		`"Occasionshandel" site:.ch`,
		`"Gebrauchtwagen Garage" site:.ch`,
		`"voiture d'occasion Suisse" site:.ch`,
		`"concessionnaire automobile Suisse" site:.ch`,
		`"Auto Ankauf" site:.ch`,
		`"Occasionszentrum" site:.ch`,
		`"Fahrzeughandel Schweiz" site:.ch`,
		`"auto occasion" site:.ch`,
		`"Gebrauchtwagen Händler Schweiz" site:.ch`,
		`"Automarkt" site:.ch`,
	},
}

// countryLanguage maps ISO codes to the Accept-Language / SearXNG language parameter.
var countryLanguage = map[string]string{
	"DE": "de-DE",
	"FR": "fr-FR",
	"ES": "es-ES",
	"NL": "nl-NL",
	"BE": "fr-BE",
	"CH": "de-CH",
}

// searchResult mirrors a single result object from the SearXNG JSON response.
type searchResult struct {
	URL     string  `json:"url"`
	Title   string  `json:"title"`
	Content string  `json:"content"`
	Score   float64 `json:"score"`
}

// searchResponse mirrors the top-level SearXNG JSON response.
type searchResponse struct {
	Query           string         `json:"query"`
	NumberOfResults int            `json:"number_of_results"`
	Results         []searchResult `json:"results"`
}

// SearXNG executes the K.1 sub-technique meta-search crawl.
type SearXNG struct {
	graph       kg.KnowledgeGraph
	client      *http.Client
	instances   []string
	reqInterval time.Duration
	log         *slog.Logger
}

// New returns a SearXNG executor with the default public instances.
func New(graph kg.KnowledgeGraph) *SearXNG {
	return NewWithConfig(graph, defaultInstances, defaultReqInterval)
}

// NewWithConfig returns a SearXNG executor with custom instances and interval
// (use interval=0 in tests).
func NewWithConfig(graph kg.KnowledgeGraph, instances []string, reqInterval time.Duration) *SearXNG {
	return &SearXNG{
		graph:       graph,
		client:      &http.Client{Timeout: 20 * time.Second},
		instances:   instances,
		reqInterval: reqInterval,
		log:         slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (s *SearXNG) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (s *SearXNG) Name() string { return subTechName }

// Run executes the country's query templates against the SearXNG instance pool.
func (s *SearXNG) Run(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}

	templates, ok := queryTemplates[country]
	if !ok || len(templates) == 0 {
		s.log.Info("searxng: no query templates for country", "country", country)
		result.Duration = time.Since(start)
		return result, nil
	}

	lang := countryLanguage[country]
	if lang == "" {
		lang = "en-US"
	}

	// Load checkpoint — resume from last processed index.
	startIdx := 0
	cpKey := "searxng:" + country + ":last_index"
	if cp, err := s.graph.GetProcessingState(ctx, cpKey); err == nil && cp != "" {
		if n, err := strconv.Atoi(cp); err == nil && n > 0 {
			startIdx = n
		}
	}

	if startIdx >= len(templates) {
		startIdx = 0 // full cycle complete; restart
	}

	for i := startIdx; i < len(templates); i++ {
		if ctx.Err() != nil {
			break
		}

		if s.reqInterval > 0 && i > startIdx {
			select {
			case <-ctx.Done():
				goto done
			case <-time.After(s.reqInterval):
			}
		}

		instance := s.instances[i%len(s.instances)]
		query := templates[i]

		results, err := s.query(ctx, instance, query, lang)
		if err != nil {
			s.log.Warn("searxng: query error",
				"instance", instance, "query", query, "err", err)
			result.Errors++
			continue
		}

		s.log.Debug("searxng: query done",
			"country", country, "idx", i, "results", len(results))

		for _, r := range results {
			domain := extractDomain(r.URL)
			if domain == "" {
				continue
			}

			knownDealerID, err := s.graph.FindDealerIDByDomain(ctx, domain)
			if err != nil {
				continue
			}

			if knownDealerID != "" {
				// Domain already in KG — record discovery confirmation.
				_ = s.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
					RecordID:              ulid.Make().String(),
					DealerID:              knownDealerID,
					Family:                familyID,
					SubTechnique:          subTechID,
					ConfidenceContributed: kg.BaseWeights[familyID],
					DiscoveredAt:          time.Now().UTC(),
					SourceURL:             ptrStr(r.URL),
				})
				result.Confirmed++
				metrics.DealersTotal.WithLabelValues(familyID, country).Inc()
			} else {
				// Unknown domain — create a thin low-confidence dealer entity and
				// record the domain as a web presence candidate for cross-validation
				// by Families A/B/H. The canonical name defaults to the domain until
				// a richer source provides a proper name.
				if err := s.upsertCandidate(ctx, domain, r.URL, country); err != nil {
					s.log.Debug("searxng: upsert candidate error",
						"domain", domain, "err", err)
				} else {
					result.Discovered++
				}
			}
		}

		// Save checkpoint after each successful query.
		_ = s.graph.SetProcessingState(ctx, cpKey, strconv.Itoa(i+1))
	}

done:
	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, country).Observe(result.Duration.Seconds())
	s.log.Info("searxng: done",
		"country", country,
		"discovered", result.Discovered,
		"confirmed", result.Confirmed,
		"errors", result.Errors,
	)
	return result, nil
}

// ── Candidate upsert ─────────────────────────────────────────────────────────

// upsertCandidate creates (or re-confirms) a thin low-confidence dealer entity
// for an unknown domain discovered via SearXNG. The entity is tagged with
// DOMAIN_FROM_SEARCH and MetadataJSON.pending_cross_validation=true so that
// downstream families (A/B/H) can enrich or discard it.
func (s *SearXNG) upsertCandidate(ctx context.Context, domain, rawURL, country string) error {
	now := time.Now().UTC()

	// Check if we already have a web presence for this domain.
	existingDealerID, err := s.graph.FindDealerIDByDomain(ctx, domain)
	if err != nil {
		return err
	}

	// Check DOMAIN_FROM_SEARCH identifier.
	dealerID := existingDealerID
	if dealerID == "" {
		idDealerID, err := s.graph.FindDealerByIdentifier(ctx, kg.IdentifierDomainFromSearch, domain)
		if err == nil {
			dealerID = idDealerID
		}
	}

	isNew := dealerID == ""
	if isNew {
		dealerID = ulid.Make().String()
	}

	meta := searchMetaJSON
	if err := s.graph.UpsertDealer(ctx, &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     domain, // placeholder until enriched
		NormalizedName:    strings.ToLower(domain),
		CountryCode:       country,
		Status:            kg.StatusUnverified,
		ConfidenceScore:   kg.BaseWeights[familyID],
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
		MetadataJSON:      &meta,
	}); err != nil {
		return fmt.Errorf("searxng.upsertCandidate dealer: %w", err)
	}

	if isNew {
		if err := s.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
			IdentifierID:    ulid.Make().String(),
			DealerID:        dealerID,
			IdentifierType:  kg.IdentifierDomainFromSearch,
			IdentifierValue: domain,
			SourceFamily:    familyID,
			ValidStatus:     "PENDING",
		}); err != nil {
			return fmt.Errorf("searxng.upsertCandidate identifier: %w", err)
		}

		if err := s.graph.UpsertWebPresence(ctx, &kg.DealerWebPresence{
			WebID:                ulid.Make().String(),
			DealerID:             dealerID,
			Domain:               domain,
			URLRoot:              rawURL,
			DiscoveredByFamilies: familyID,
			MetadataJSON:         &meta,
		}); err != nil {
			return fmt.Errorf("searxng.upsertCandidate web presence: %w", err)
		}
	}

	if err := s.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
		SourceURL:             ptrStr(rawURL),
	}); err != nil {
		return fmt.Errorf("searxng.upsertCandidate discovery: %w", err)
	}

	return nil
}

// ── HTTP query ────────────────────────────────────────────────────────────────

// query submits a single search query to a SearXNG instance and returns results.
func (s *SearXNG) query(ctx context.Context, instance, q, lang string) ([]searchResult, error) {
	reqURL := instance + "/search?" + url.Values{
		"q":          {q},
		"format":     {"json"},
		"language":   {lang},
		"safesearch": {"0"},
		"pageno":     {"1"},
	}.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return nil, fmt.Errorf("searxng.query: build req: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "application/json")

	resp, err := s.client.Do(req)
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return nil, fmt.Errorf("searxng.query: http: %w", err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("searxng.query: HTTP %d from %s", resp.StatusCode, instance)
	}

	var sr searchResponse
	if err := json.NewDecoder(resp.Body).Decode(&sr); err != nil {
		return nil, fmt.Errorf("searxng.query: decode JSON: %w", err)
	}

	if len(sr.Results) > maxResultsPerQuery {
		sr.Results = sr.Results[:maxResultsPerQuery]
	}
	return sr.Results, nil
}

// ── Helpers ───────────────────────────────────────────────────────────────────

func extractDomain(rawURL string) string {
	if !strings.Contains(rawURL, "://") {
		return ""
	}
	u, err := url.Parse(rawURL)
	if err != nil || u.Host == "" {
		return ""
	}
	return strings.TrimPrefix(u.Host, "www.")
}

func ptrStr(s string) *string { return &s }
