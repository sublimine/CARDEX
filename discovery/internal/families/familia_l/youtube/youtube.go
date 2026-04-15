// Package youtube implements sub-technique L.3 — YouTube dealer channel search.
//
// # Strategy
//
// YouTube Data API v3 (free tier: 10,000 units/day; channel search costs 100
// units per call, giving 100 searches/day — sufficient for CARDEX scale).
//
// For each target country:
//  1. Search YouTube for car-dealer channels with country-specific query terms.
//  2. Retrieve channel details (title, description, country, customUrl).
//  3. For channels where the description or snippet contains a website URL that
//     matches an existing KG dealer domain: upsert dealer_social_profile.
//  4. For channels that name-match an existing KG dealer (fuzzy): upsert
//     dealer_social_profile with lower confidence.
//
// # YouTube Data API endpoints used
//
//   - search.list: part=snippet, type=channel, q={query}, regionCode={CC},
//     maxResults=50
//     Cost: 100 units per call
//
//   - channels.list: part=snippet,brandingSettings, id={ids}
//     Cost: 1 unit per call
//     Note: website URL is NOT in brandingSettings via API. The description
//     field often contains website URLs which we extract via regex.
//
// # API key
//
// Requires environment variable YOUTUBE_API_KEY. When absent, Run logs an info
// message and returns an empty result (no error). Obtain a free key at:
// console.cloud.google.com → APIs & Services → YouTube Data API v3.
//
// # Rate limiting
//
// 1 API call / 5 s (conservative; the 10k unit/day budget allows ~100 search
// calls/day, spread across 6 countries = ~16 calls/country/day).
//
// # BaseWeights["L"] = 0.10
//
// YouTube channel cross-match is a medium-confidence signal: a dealer that
// actively maintains a YouTube channel is likely legitimate and operational.
package youtube

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"

	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID    = "L"
	subTechID   = "L.3"
	subTechName = "YouTube dealer channel search"

	defaultBaseURL  = "https://www.googleapis.com/youtube/v3"
	defaultInterval = 5 * time.Second
	maxResults      = 50

	cardexUA = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
)

// reURL matches bare https?:// URLs in text (channel descriptions).
var reURL = regexp.MustCompile(`https?://[^\s"'<>]+`)

// countryQueries maps country code to YouTube search queries (native language).
var countryQueries = map[string][]string{
	"DE": {
		"Autohaus offizieller YouTube Kanal",
		"Gebrauchtwagen Handel YouTube",
		"Fahrzeughandel YouTube Kanal",
	},
	"FR": {
		"concessionnaire automobile YouTube officiel",
		"garage automobile YouTube chaine",
		"vente voitures YouTube",
	},
	"ES": {
		"concesionario automovil YouTube oficial",
		"compraventa coches YouTube canal",
		"dealer coches YouTube",
	},
	"NL": {
		"autobedrijf YouTube kanaal officieel",
		"autoverkoop dealer YouTube",
	},
	"BE": {
		"garagiste belge YouTube officiel",
		"autohandel belgie YouTube kanaal",
	},
	"CH": {
		"Autohaus Schweiz YouTube Kanal",
		"garage automobile suisse YouTube",
	},
}

// -- YouTube API response types -----------------------------------------------

type searchResponse struct {
	Items []searchItem `json:"items"`
}

type searchItem struct {
	ID      itemID      `json:"id"`
	Snippet itemSnippet `json:"snippet"`
}

type itemID struct {
	Kind      string `json:"kind"`
	ChannelID string `json:"channelId"`
}

type itemSnippet struct {
	Title       string `json:"title"`
	Description string `json:"description"`
	ChannelID   string `json:"channelId"`
	CountryCode string `json:"country"`
}

type channelsResponse struct {
	Items []channelItem `json:"items"`
}

type channelItem struct {
	ID      string        `json:"id"`
	Snippet channelSnippet `json:"snippet"`
}

type channelSnippet struct {
	Title       string `json:"title"`
	Description string `json:"description"`
	Country     string `json:"country"`
	CustomURL   string `json:"customUrl"`
}

// -- YouTube sub-technique ----------------------------------------------------

// YouTube executes the L.3 sub-technique.
type YouTube struct {
	graph       kg.KnowledgeGraph
	client      *http.Client
	baseURL     string
	apiKey      string
	reqInterval time.Duration
	log         *slog.Logger
}

// New returns a YouTube executor. apiKey may be empty (Run will skip gracefully).
func New(graph kg.KnowledgeGraph, apiKey string) *YouTube {
	return NewWithBaseURL(graph, apiKey, defaultBaseURL, defaultInterval)
}

// NewWithBaseURL returns a YouTube executor with custom base URL and interval
// (use interval=0 in tests).
func NewWithBaseURL(graph kg.KnowledgeGraph, apiKey, baseURL string, reqInterval time.Duration) *YouTube {
	return &YouTube{
		graph:       graph,
		client:      &http.Client{Timeout: 15 * time.Second},
		baseURL:     baseURL,
		apiKey:      apiKey,
		reqInterval: reqInterval,
		log:         slog.Default().With("sub_technique", subTechID),
	}
}

// NewWithClient returns a YouTube executor using a custom HTTP client (for tests).
func NewWithClient(graph kg.KnowledgeGraph, apiKey, baseURL string, c *http.Client) *YouTube {
	return &YouTube{
		graph:   graph,
		client:  c,
		baseURL: baseURL,
		apiKey:  apiKey,
		log:     slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (y *YouTube) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (y *YouTube) Name() string { return subTechName }

// Run searches YouTube for car dealer channels in the given country and
// cross-references them with the KG.
func (y *YouTube) Run(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}

	if y.apiKey == "" {
		y.log.Info("L.3 YouTube: no API key configured; skipping",
			"hint", "set YOUTUBE_API_KEY env var to enable YouTube channel discovery",
			"country", country,
		)
		result.Duration = time.Since(start)
		return result, nil
	}

	queries, ok := countryQueries[country]
	if !ok {
		y.log.Debug("L.3 YouTube: no queries for country", "country", country)
		result.Duration = time.Since(start)
		return result, nil
	}

	seenChannelID := make(map[string]bool)

	for _, q := range queries {
		if ctx.Err() != nil {
			break
		}
		if y.reqInterval > 0 {
			select {
			case <-ctx.Done():
				goto done
			case <-time.After(y.reqInterval):
			}
		}

		channels, err := y.searchChannels(ctx, q, country)
		if err != nil {
			y.log.Warn("L.3 YouTube: search error", "query", q, "err", err)
			result.Errors++
			metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
			continue
		}
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "2xx").Inc()

		for _, ch := range channels {
			if ctx.Err() != nil {
				goto done
			}
			if seenChannelID[ch.ID] {
				continue // already processed this channel in a previous query
			}
			seenChannelID[ch.ID] = true

			n, err := y.processChannel(ctx, ch, country)
			if err != nil {
				y.log.Warn("L.3 YouTube: process channel error",
					"channel", ch.ID, "err", err)
				result.Errors++
				continue
			}
			result.Discovered += n
		}
	}

done:
	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, country).Observe(result.Duration.Seconds())
	y.log.Info("L.3 YouTube: done",
		"country", country,
		"discovered", result.Discovered,
		"errors", result.Errors,
	)
	return result, nil
}

// searchChannels queries the YouTube Data API for channel search results.
func (y *YouTube) searchChannels(ctx context.Context, query, regionCode string) ([]channelItem, error) {
	searchURL := fmt.Sprintf("%s/search?%s", y.baseURL, url.Values{
		"part":       {"snippet"},
		"type":       {"channel"},
		"q":          {query},
		"regionCode": {regionCode},
		"maxResults": {fmt.Sprintf("%d", maxResults)},
		"key":        {y.apiKey},
	}.Encode())

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, searchURL, nil)
	if err != nil {
		return nil, fmt.Errorf("build search request: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)

	resp, err := y.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("search request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("search HTTP %d", resp.StatusCode)
	}

	var sr searchResponse
	if err := json.NewDecoder(resp.Body).Decode(&sr); err != nil {
		return nil, fmt.Errorf("decode search response: %w", err)
	}

	// Gather channel IDs and fetch details.
	ids := make([]string, 0, len(sr.Items))
	for _, item := range sr.Items {
		if item.ID.ChannelID != "" {
			ids = append(ids, item.ID.ChannelID)
		} else if item.Snippet.ChannelID != "" {
			ids = append(ids, item.Snippet.ChannelID)
		}
	}
	if len(ids) == 0 {
		return nil, nil
	}

	return y.fetchChannelDetails(ctx, ids)
}

// fetchChannelDetails retrieves channel snippet+brandingSettings for the given IDs.
func (y *YouTube) fetchChannelDetails(ctx context.Context, ids []string) ([]channelItem, error) {
	detailURL := fmt.Sprintf("%s/channels?%s", y.baseURL, url.Values{
		"part": {"snippet"},
		"id":   {strings.Join(ids, ",")},
		"key":  {y.apiKey},
	}.Encode())

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, detailURL, nil)
	if err != nil {
		return nil, fmt.Errorf("build channels request: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)

	resp, err := y.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("channels request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("channels HTTP %d", resp.StatusCode)
	}

	var cr channelsResponse
	if err := json.NewDecoder(resp.Body).Decode(&cr); err != nil {
		return nil, fmt.Errorf("decode channels response: %w", err)
	}
	return cr.Items, nil
}

// processChannel cross-references a YouTube channel against the KG.
// Returns the count of new social profile records upserted.
func (y *YouTube) processChannel(ctx context.Context, ch channelItem, country string) (int, error) {
	// Extract website URLs from channel description.
	urls := reURL.FindAllString(ch.Snippet.Description, -1)

	matched := false
	for _, rawURL := range urls {
		domain := extractDomain(rawURL)
		if domain == "" || isYouTubeDomain(domain) {
			continue
		}
		// Check if this domain is in the KG.
		dealerID, err := y.graph.FindDealerIDByDomain(ctx, domain)
		if err != nil || dealerID == "" {
			continue
		}
		// Found a KG match — upsert social profile.
		profileURL := "https://www.youtube.com/channel/" + ch.ID
		if ch.Snippet.CustomURL != "" {
			profileURL = "https://www.youtube.com/" + strings.TrimPrefix(ch.Snippet.CustomURL, "@")
		}

		now := time.Now().UTC()
		metaJSON := fmt.Sprintf(`{"title":%q,"country":%q}`,
			ch.Snippet.Title, ch.Snippet.Country)

		chID := ch.ID
		profile := &kg.DealerSocialProfile{
			ProfileID:            ulid.Make().String(),
			DealerID:             dealerID,
			Platform:             "youtube",
			ProfileURL:           profileURL,
			ExternalID:           &chID,
			LastActivityDetected: &now,
			MetadataJSON:         &metaJSON,
		}
		if err := y.graph.UpsertSocialProfile(ctx, profile); err != nil {
			return 0, fmt.Errorf("upsert social profile: %w", err)
		}
		y.log.Debug("L.3 YouTube: channel linked to dealer",
			"channel", ch.ID,
			"channel_title", ch.Snippet.Title,
			"domain", domain,
			"dealer_id", dealerID,
		)
		matched = true
		break // one channel → one dealer link per run
	}
	if matched {
		return 1, nil
	}
	return 0, nil
}

// extractDomain returns the hostname from a URL string.
func extractDomain(rawURL string) string {
	u, err := url.Parse(rawURL)
	if err != nil {
		return ""
	}
	host := strings.ToLower(u.Hostname())
	// Strip www.
	host = strings.TrimPrefix(host, "www.")
	return host
}

// isYouTubeDomain returns true for youtube.com and related Google domains that
// should not be treated as dealer websites.
func isYouTubeDomain(domain string) bool {
	skip := []string{
		"youtube.com", "youtu.be", "google.com", "goo.gl",
		"bit.ly", "t.co", "facebook.com", "instagram.com",
		"twitter.com", "x.com", "tiktok.com",
	}
	for _, s := range skip {
		if domain == s || strings.HasSuffix(domain, "."+s) {
			return true
		}
	}
	return false
}
