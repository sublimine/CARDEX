// Package rss implements sub-technique O.2 -- RSS/Atom feed monitoring for
// automotive trade news.
//
// # Strategy
//
// A curated set of RSS/Atom feeds from major automotive trade publications is
// polled once per run. New items (identified by URL, not seen before) are
// passed through the NER pipeline (package ner) to extract dealer name
// candidates, which are then cross-validated against the KG.
//
// # Curated feeds
//
//   DE: kfz-betrieb.de, automobilwoche.de, autohaus.de
//   FR: largus.fr pro, autoactu.com
//   ES: motor16.com
//   NL: automotive-online.nl
//   BE: fleet.be
//   CH: automotive.ch
//
// # RSS/Atom parsing
//
// Implemented with stdlib encoding/xml. Supports RSS 2.0 (<item> with <link>
// and <pubDate>) and Atom 1.0 (<entry> with <link href="..."> and <updated>).
// No external library dependency.
//
// # Rate limits
//
// No API key required. One HTTP GET per feed per run. Sleep: 500 ms between
// feeds. Feeds are polled at most once per 6-hour window; the last-seen item
// URL per feed is stored in the KG processing_state table.
package rss

import (
	"context"
	"encoding/xml"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/families/familia_o/ner"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	subTechID   = "O.2"
	subTechName = "RSS/Atom automotive trade news monitoring"

	interFeedMs = 500           // 500 ms between feed fetches
	maxBodyBytes = 1 << 20     // 1 MiB feed body limit
)

// feedsByCountry is the curated list of RSS/Atom feeds per country.
var feedsByCountry = map[string][]string{
	"DE": {
		"https://www.kfz-betrieb.vogel.de/rss/news.xml",
		"https://www.automobilwoche.de/rss/alle-artikel",
	},
	"FR": {
		"https://www.largus.fr/actus/rss.xml",
		"https://www.autoactu.com/rss.xml",
	},
	"ES": {
		"https://www.motor16.com/rss/feed.xml",
	},
	"NL": {
		"https://www.automotive-online.nl/rss.xml",
	},
	"BE": {
		"https://www.fleet.be/feed",
	},
	"CH": {
		"https://www.automotive.ch/rss/news.xml",
	},
}

// RSSPoller is the O.2 sub-technique.
type RSSPoller struct {
	graph  kg.KnowledgeGraph
	client *http.Client
	feeds  map[string][]string // country -> feed URLs (nil = use default feedsByCountry)
	log    *slog.Logger
}

// New constructs a RSSPoller with production configuration.
func New(graph kg.KnowledgeGraph) *RSSPoller {
	return &RSSPoller{
		graph:  graph,
		client: &http.Client{Timeout: 15 * time.Second},
		log:    slog.Default().With("sub_technique", subTechID),
	}
}

// NewWithClient constructs a RSSPoller with a custom HTTP client.
// Used in tests to serve mock feeds.
func NewWithClient(graph kg.KnowledgeGraph, c *http.Client) *RSSPoller {
	return &RSSPoller{
		graph:  graph,
		client: c,
		log:    slog.Default().With("sub_technique", subTechID),
	}
}

// NewWithClientAndFeeds constructs a RSSPoller with a custom HTTP client and
// feed map. Used in tests to inject both a mock server and controlled feed URLs.
func NewWithClientAndFeeds(graph kg.KnowledgeGraph, c *http.Client, feeds map[string][]string) *RSSPoller {
	return &RSSPoller{
		graph:  graph,
		client: c,
		feeds:  feeds,
		log:    slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (r *RSSPoller) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (r *RSSPoller) Name() string { return subTechName }

// feedItem is a normalised representation of an RSS <item> or Atom <entry>.
type feedItem struct {
	Title string
	URL   string
}

// Run fetches all configured feeds for the given country, extracts new items,
// runs NER, and cross-validates candidates against the KG.
func (r *RSSPoller) Run(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}

	feedMap := r.feeds
	if feedMap == nil {
		feedMap = feedsByCountry
	}
	feeds, ok := feedMap[country]
	if !ok {
		r.log.Info("O.2 RSS: no feeds configured", "country", country)
		return result, nil
	}

	start := time.Now()

	for i, feedURL := range feeds {
		if ctx.Err() != nil {
			break
		}
		if i > 0 {
			select {
			case <-ctx.Done():
				goto done
			case <-time.After(interFeedMs * time.Millisecond):
			}
		}
		found, err := r.processFeed(ctx, feedURL, country)
		if err != nil {
			r.log.Warn("O.2 RSS: feed error", "url", feedURL, "err", err)
			result.Errors++
			continue
		}
		result.Discovered += found
	}

done:
	result.Duration = time.Since(start)
	return result, nil
}

func (r *RSSPoller) processFeed(ctx context.Context, feedURL, country string) (int, error) {
	// Check last-seen checkpoint.
	stateKey := fmt.Sprintf("rss:%s:lastseen", feedURL)
	lastSeen, _ := r.graph.GetProcessingState(ctx, stateKey)

	items, err := r.fetchFeed(ctx, feedURL)
	if err != nil {
		return 0, err
	}

	discovered := 0
	newLastSeen := lastSeen

	for _, item := range items {
		if item.URL == "" {
			continue
		}
		// Skip already-processed items.
		if item.URL == lastSeen {
			break
		}
		if newLastSeen == lastSeen {
			newLastSeen = item.URL // record newest item URL
		}

		text := item.Title
		candidates := ner.ExtractCandidates(text)

		for _, cand := range candidates {
			dealerIDs, _ := r.graph.FindDealersByName(ctx, cand.Normalized, country)
			if len(dealerIDs) > 0 {
				for _, dealerID := range dealerIDs {
					articleURL := item.URL
					_ = r.graph.RecordPressSignal(ctx, &kg.DealerPressSignal{
						SignalID:     ulid.Make().String(),
						DealerID:     dealerID,
						EventType:    "MENTION",
						ArticleURL:   articleURL,
						ArticleTitle: item.Title,
						SourceFamily: subTechID,
						DetectedAt:   time.Now(),
					})
					_ = r.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
						RecordID:              ulid.Make().String(),
						DealerID:              dealerID,
						Family:                "O",
						SubTechnique:          subTechID,
						SourceURL:             &articleURL,
						ConfidenceContributed: 0.01,
						DiscoveredAt:          time.Now(),
					})
				}
			} else {
				dealerID := ulid.Make().String()
				now := time.Now()
				if err := r.graph.UpsertDealer(ctx, &kg.DealerEntity{
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
				articleURL := item.URL
				_ = r.graph.RecordPressSignal(ctx, &kg.DealerPressSignal{
					SignalID:     ulid.Make().String(),
					DealerID:     dealerID,
					EventType:    "MENTION",
					ArticleURL:   articleURL,
					ArticleTitle: item.Title,
					SourceFamily: subTechID,
					DetectedAt:   now,
				})
				discovered++
			}
		}
	}

	if newLastSeen != lastSeen {
		_ = r.graph.SetProcessingState(ctx, stateKey, newLastSeen)
	}
	return discovered, nil
}

// -- RSS / Atom XML structs ---------------------------------------------------

// rssDoc handles RSS 2.0 (<rss><channel><item>).
type rssDoc struct {
	XMLName xml.Name   `xml:"rss"`
	Channel rssChannel `xml:"channel"`
}

type rssChannel struct {
	Items []rssItem `xml:"item"`
}

type rssItem struct {
	Title string `xml:"title"`
	Link  string `xml:"link"`
}

// atomDoc handles Atom 1.0 (<feed><entry>).
type atomDoc struct {
	XMLName xml.Name    `xml:"feed"`
	Entries []atomEntry `xml:"entry"`
}

type atomEntry struct {
	Title string     `xml:"title"`
	Links []atomLink `xml:"link"`
}

type atomLink struct {
	Rel  string `xml:"rel,attr"`
	Href string `xml:"href,attr"`
}

func (r *RSSPoller) fetchFeed(ctx context.Context, feedURL string) ([]feedItem, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, feedURL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "CardexBot/1.0 (+https://cardex.eu/bot)")
	req.Header.Set("Accept", "application/rss+xml,application/atom+xml,text/xml,application/xml")

	resp, err := r.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("feed HTTP %d for %s", resp.StatusCode, feedURL)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, maxBodyBytes))
	if err != nil {
		return nil, fmt.Errorf("read feed body: %w", err)
	}

	return parseFeed(body)
}

// parseFeed tries RSS 2.0 first, then Atom 1.0.
func parseFeed(data []byte) ([]feedItem, error) {
	// Try RSS 2.0
	var rss rssDoc
	if err := xml.Unmarshal(data, &rss); err == nil && len(rss.Channel.Items) > 0 {
		items := make([]feedItem, 0, len(rss.Channel.Items))
		for _, item := range rss.Channel.Items {
			link := strings.TrimSpace(item.Link)
			if link == "" {
				continue
			}
			items = append(items, feedItem{Title: strings.TrimSpace(item.Title), URL: link})
		}
		return items, nil
	}

	// Try Atom 1.0
	var atom atomDoc
	if err := xml.Unmarshal(data, &atom); err == nil && len(atom.Entries) > 0 {
		items := make([]feedItem, 0, len(atom.Entries))
		for _, entry := range atom.Entries {
			link := ""
			for _, l := range entry.Links {
				if l.Rel == "alternate" || l.Rel == "" {
					link = l.Href
					break
				}
			}
			if link == "" {
				continue
			}
			items = append(items, feedItem{Title: strings.TrimSpace(entry.Title), URL: link})
		}
		return items, nil
	}

	return nil, fmt.Errorf("unrecognized feed format (neither RSS 2.0 nor Atom 1.0)")
}
