// Package gdelt implements sub-technique O.1 -- GDELT Project press archive mining.
//
// # What it does
//
// GDELT (Global Database of Events, Language, and Tone) indexes worldwide news
// 24/7 with full-text search across 100+ languages. O.1 queries GDELT for recent
// automotive dealer mentions in the target country and:
//
//  1. Fetches the article list (up to 10 articles, 1-week timespan).
//  2. Downloads each article's HTML and extracts body text via goquery.
//  3. Runs NER (package ner) over the text to extract dealer name candidates.
//  4. Cross-validates against the KG:
//     - Match found → RecordDiscovery + RecordPressSignal (event signal)
//     - No match    → UpsertDealer (LOW_CONFIDENCE) + RecordPressSignal
//
// # Rate limits
//
// GDELT API is free and permits automated access. Practical limit: ~100 req/h.
// O.1 makes 1 API query per country per run + up to 10 article fetches.
// Sleep: 2 s between article fetches (polite crawl).
//
// # GDELT Doc 2.0 API
//
//	GET https://api.gdeltproject.org/api/v2/doc/doc
//	  ?query={q}&mode=ArtList&format=json&timespan=1W&maxrecords=10
//
// Response (200 OK):
//
//	{
//	  "articles": [
//	    {
//	      "url":           "https://...",
//	      "title":         "Autohaus Muster eröffnet neuen Showroom",
//	      "seendate":      "20240415T120000Z",
//	      "sourcecountry": "Germany",
//	      "language":      "German"
//	    }
//	  ]
//	}
//
// Query template:
//
//	("Autohaus" OR "car dealer" OR "Garage" OR "concessionnaire"
//	  OR "concesionario" OR "autobedrijf") sourcecountry:{GDELT_CODE}
package gdelt

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/families/familia_o/ner"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	subTechID    = "O.1"
	subTechName  = "GDELT Project automotive press archive mining"
	defaultBase  = "https://api.gdeltproject.org"
	maxArticles  = 10
	artFetchSleep = 2 * time.Second
)

// gdeltCountry maps ISO-3166-1 alpha-2 to GDELT sourcecountry filter.
var gdeltCountry = map[string]string{
	"DE": "Germany",
	"FR": "France",
	"ES": "Spain",
	"NL": "Netherlands",
	"BE": "Belgium",
	"CH": "Switzerland",
}

// queryTemplate returns the GDELT search query for a given country.
const queryTemplate = `("Autohaus" OR "car dealer" OR "Garage" OR "concessionnaire" OR "concesionario" OR "autobedrijf" OR "concessionario") sourcecountry:%s`

// GDELT is the O.1 sub-technique.
type GDELT struct {
	graph   kg.KnowledgeGraph
	baseURL string
	client  *http.Client
	log     *slog.Logger
}

// New constructs a GDELT client with production configuration.
func New(graph kg.KnowledgeGraph) *GDELT {
	return &GDELT{
		graph:   graph,
		baseURL: defaultBase,
		client:  &http.Client{Timeout: 20 * time.Second},
		log:     slog.Default().With("sub_technique", subTechID),
	}
}

// NewWithClient constructs a GDELT client with a custom HTTP client and base URL.
// Used in tests to redirect requests to a mock server.
func NewWithClient(graph kg.KnowledgeGraph, baseURL string, c *http.Client) *GDELT {
	return &GDELT{
		graph:   graph,
		baseURL: baseURL,
		client:  c,
		log:     slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (g *GDELT) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (g *GDELT) Name() string { return subTechName }

type gdeltResponse struct {
	Articles []struct {
		URL           string `json:"url"`
		Title         string `json:"title"`
		SeenDate      string `json:"seendate"`
		SourceCountry string `json:"sourcecountry"`
		Language      string `json:"language"`
	} `json:"articles"`
}

// Run queries GDELT for automotive dealer mentions in the given country,
// fetches article HTML, runs NER, and cross-validates against the KG.
func (g *GDELT) Run(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}

	gdeltCode, ok := gdeltCountry[country]
	if !ok {
		g.log.Info("O.1 GDELT: country not supported", "country", country)
		return result, nil
	}

	start := time.Now()
	articles, err := g.fetchArticleList(ctx, gdeltCode)
	if err != nil {
		return result, fmt.Errorf("O.1: fetch article list: %w", err)
	}
	g.log.Info("O.1 GDELT: articles fetched", "country", country, "count", len(articles))

	for i, art := range articles {
		if ctx.Err() != nil {
			break
		}
		if i > 0 {
			select {
			case <-ctx.Done():
				goto done
			case <-time.After(artFetchSleep):
			}
		}
		found, processErr := g.processArticle(ctx, art.URL, art.Title, country)
		if processErr != nil {
			g.log.Warn("O.1: article processing error", "url", art.URL, "err", processErr)
			result.Errors++
			continue
		}
		result.Discovered += found
	}

done:
	result.Duration = time.Since(start)
	return result, nil
}

type articleRef struct {
	URL   string
	Title string
}

func (g *GDELT) fetchArticleList(ctx context.Context, gdeltCode string) ([]articleRef, error) {
	query := fmt.Sprintf(queryTemplate, gdeltCode)
	params := url.Values{
		"query":      {query},
		"mode":       {"ArtList"},
		"format":     {"json"},
		"timespan":   {"1W"},
		"maxrecords": {fmt.Sprintf("%d", maxArticles)},
	}
	apiURL := g.baseURL + "/api/v2/doc/doc?" + params.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, apiURL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/json")

	resp, err := g.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("O.1: GDELT HTTP %d", resp.StatusCode)
	}

	var data gdeltResponse
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return nil, fmt.Errorf("O.1: decode GDELT response: %w", err)
	}

	refs := make([]articleRef, 0, len(data.Articles))
	for _, a := range data.Articles {
		if a.URL != "" {
			refs = append(refs, articleRef{URL: a.URL, Title: a.Title})
		}
	}
	return refs, nil
}

func (g *GDELT) processArticle(ctx context.Context, articleURL, title, country string) (int, error) {
	text, err := g.fetchArticleText(ctx, articleURL)
	if err != nil {
		// Non-fatal: article may be paywalled or unavailable.
		text = title // fall back to NER on title only
	}
	if text == "" {
		text = title
	}

	candidates := ner.ExtractCandidates(text)
	if len(candidates) == 0 {
		return 0, nil
	}

	discovered := 0
	for _, cand := range candidates {
		dealerIDs, _ := g.graph.FindDealersByName(ctx, cand.Normalized, country)
		if len(dealerIDs) > 0 {
			// Existing dealer -- record press mention.
			for _, dealerID := range dealerIDs {
				_ = g.graph.RecordPressSignal(ctx, &kg.DealerPressSignal{
					SignalID:     ulid.Make().String(),
					DealerID:     dealerID,
					EventType:    "MENTION",
					ArticleURL:   articleURL,
					ArticleTitle: title,
					SourceFamily: subTechID,
					DetectedAt:   time.Now(),
				})
				_ = g.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
					RecordID:              ulid.Make().String(),
					DealerID:              dealerID,
					Family:                "O",
					SubTechnique:          subTechID,
					SourceURL:             &articleURL,
					ConfidenceContributed: 0.01, // press mention is a weak confirmation
					DiscoveredAt:          time.Now(),
				})
			}
		} else {
			// Unknown dealer -- create LOW_CONFIDENCE candidate.
			dealerID := ulid.Make().String()
			now := time.Now()
			if err := g.graph.UpsertDealer(ctx, &kg.DealerEntity{
				DealerID:          dealerID,
				CanonicalName:     cand.Raw,
				NormalizedName:    cand.Normalized,
				CountryCode:       country,
				Status:            kg.StatusUnverified,
				ConfidenceScore:   0.05,
				FirstDiscoveredAt: now,
				LastConfirmedAt:   now,
			}); err != nil {
				continue
			}
			_ = g.graph.RecordPressSignal(ctx, &kg.DealerPressSignal{
				SignalID:     ulid.Make().String(),
				DealerID:     dealerID,
				EventType:    "MENTION",
				ArticleURL:   articleURL,
				ArticleTitle: title,
				SourceFamily: subTechID,
				DetectedAt:   now,
			})
			_ = g.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
				RecordID:              ulid.Make().String(),
				DealerID:              dealerID,
				Family:                "O",
				SubTechnique:          subTechID,
				SourceURL:             &articleURL,
				ConfidenceContributed: 0.05,
				DiscoveredAt:          now,
			})
			discovered++
		}
	}
	return discovered, nil
}

// fetchArticleText fetches an article URL and extracts visible body text using
// goquery. Returns empty string on fetch error (caller falls back to title).
func (g *GDELT) fetchArticleText(ctx context.Context, articleURL string) (string, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, articleURL, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("User-Agent", "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)")
	req.Header.Set("Accept", "text/html,application/xhtml+xml")

	resp, err := g.client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("article HTTP %d", resp.StatusCode)
	}

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		return "", err
	}

	// Remove script and style nodes.
	doc.Find("script, style, nav, footer, header").Remove()

	var parts []string
	doc.Find("p, h1, h2, h3").Each(func(_ int, s *goquery.Selection) {
		if text := strings.TrimSpace(s.Text()); text != "" {
			parts = append(parts, text)
		}
	})
	return strings.Join(parts, " "), nil
}
