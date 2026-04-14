// Package lacentrale implements sub-technique F.4 — La Centrale Pro dealer directory.
//
// La Centrale publishes an SEO-friendly static-HTML garage annuaire at:
//
//	https://www.lacentrale.fr/annuaire/garages-regions
//
// The annuaire is structured in two levels:
//  1. Region index — lists all French regions with links to their garage pages.
//  2. Region garage listing — paginated list of garages within a region.
//
// Each garage listing page contains <article class="garageCard"> cards. The
// crawler first fetches the region index to enumerate all region URLs, then
// paginates through each region's garage listing.
//
// Pagination: detected via <a class="pagination-next"> link on each listing page.
//
// Rate limiting: 1 req / 3 s (conservative; La Centrale is a public French
// marketplace served via CDN; no published crawl budget).
// robots.txt: /annuaire/ is accessible to Googlebot (Google-indexed as of
// 2026-04-14); robots.txt returned 403 from cloud IP — treated as unrestricted
// under RFC 9309 §2.2.3 (inaccessible robots.txt = no restriction).
//
// Identifier type: LACENTRALE_PRO_ID — value is the data-garage-id attribute
// from each garage card (e.g. "lc-75001").
package lacentrale

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	defaultBaseURL     = "https://www.lacentrale.fr"
	defaultReqInterval = 3 * time.Second
	cardexUA           = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
	familyID           = "F"
	subTechID          = "F.4"
	subTechName        = "La Centrale Pro dealer directory"
	country            = "FR"
)

// LaCentrale executes F.4 sub-technique crawl.
type LaCentrale struct {
	graph       kg.KnowledgeGraph
	client      *http.Client
	baseURL     string
	reqInterval time.Duration
	log         *slog.Logger
}

// New creates a LaCentrale executor with the production endpoint.
func New(graph kg.KnowledgeGraph) *LaCentrale {
	return NewWithBaseURL(graph, defaultBaseURL, defaultReqInterval)
}

// NewWithBaseURL creates a LaCentrale executor with a custom base URL and
// request interval (use interval=0 in tests).
func NewWithBaseURL(graph kg.KnowledgeGraph, baseURL string, reqInterval time.Duration) *LaCentrale {
	return &LaCentrale{
		graph:       graph,
		client:      &http.Client{Timeout: 30 * time.Second},
		baseURL:     baseURL,
		reqInterval: reqInterval,
		log:         slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (lc *LaCentrale) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (lc *LaCentrale) Name() string { return subTechName }

// garageCard holds data extracted from a single garage listing card.
type garageCard struct {
	GarageID string // data-garage-id value
	Name     string
	Address  string
	Phone    string
	Website  string // external URL, may be empty
}

// Run crawls the La Centrale annuaire: enumerates regions, then paginates
// through each region's garage listing, upserting dealers into the KG.
func (lc *LaCentrale) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}

	regionURLs, err := lc.fetchRegionIndex(ctx)
	if err != nil {
		return result, fmt.Errorf("lacentrale.Run: region index: %w", err)
	}

	for i, regionURL := range regionURLs {
		if ctx.Err() != nil {
			break
		}
		if i > 0 && lc.reqInterval > 0 {
			select {
			case <-ctx.Done():
				break
			case <-time.After(lc.reqInterval):
			}
		}
		if err := lc.crawlRegion(ctx, regionURL, result); err != nil {
			lc.log.Warn("lacentrale: region error", "url", regionURL, "err", err)
			result.Errors++
		}
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, country).Observe(result.Duration.Seconds())
	lc.log.Info("lacentrale: done",
		"discovered", result.Discovered,
		"confirmed", result.Confirmed,
		"errors", result.Errors,
	)
	return result, nil
}

// crawlRegion paginates through all garage listing pages for a single region,
// upserting each garage into the KG.
func (lc *LaCentrale) crawlRegion(ctx context.Context, regionURL string, result *runner.SubTechniqueResult) error {
	pageURL := regionURL
	for pageURL != "" {
		if ctx.Err() != nil {
			break
		}

		cards, nextURL, err := lc.fetchGarageListingPage(ctx, pageURL)
		if err != nil {
			result.Errors++
			lc.log.Warn("lacentrale: listing page error", "url", pageURL, "err", err)
			break
		}

		for _, card := range cards {
			upserted, err := lc.upsert(ctx, card)
			if err != nil {
				lc.log.Warn("lacentrale: upsert error", "name", card.Name, "err", err)
				result.Errors++
				continue
			}
			if upserted {
				result.Discovered++
				metrics.DealersTotal.WithLabelValues(familyID, country).Inc()
			} else {
				result.Confirmed++
			}
		}

		if nextURL == "" {
			break
		}
		pageURL = nextURL

		if lc.reqInterval > 0 {
			select {
			case <-ctx.Done():
				return nil
			case <-time.After(lc.reqInterval):
			}
		}
	}
	return nil
}

// upsert writes a garage card to the KG. Returns true when a new entity was
// created, false when an existing entity was re-confirmed.
func (lc *LaCentrale) upsert(ctx context.Context, card garageCard) (bool, error) {
	if card.Name == "" || card.GarageID == "" {
		return false, nil
	}
	now := time.Now().UTC()

	existing, err := lc.graph.FindDealerByIdentifier(ctx, kg.IdentifierLaCentraleProID, card.GarageID)
	if err != nil {
		return false, fmt.Errorf("lacentrale.upsert find: %w", err)
	}

	isNew := existing == ""
	dealerID := existing
	if isNew {
		dealerID = ulid.Make().String()
	}

	entity := &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     card.Name,
		NormalizedName:    strings.ToLower(card.Name),
		CountryCode:       country,
		Status:            kg.StatusUnverified,
		ConfidenceScore:   kg.BaseWeights[familyID],
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}
	if err := lc.graph.UpsertDealer(ctx, entity); err != nil {
		return false, fmt.Errorf("lacentrale.upsert dealer: %w", err)
	}

	if isNew {
		if err := lc.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
			IdentifierID:    ulid.Make().String(),
			DealerID:        dealerID,
			IdentifierType:  kg.IdentifierLaCentraleProID,
			IdentifierValue: card.GarageID,
		}); err != nil {
			return false, fmt.Errorf("lacentrale.upsert identifier: %w", err)
		}
	}

	// Location (address + optional phone).
	if card.Address != "" || card.Phone != "" {
		city, postalCode := parseFrenchAddress(card.Address)
		if err := lc.graph.AddLocation(ctx, &kg.DealerLocation{
			LocationID:     ulid.Make().String(),
			DealerID:       dealerID,
			IsPrimary:      true,
			AddressLine1:   ptrIfNotEmpty(card.Address),
			PostalCode:     postalCode,
			City:           city,
			CountryCode:    country,
			Phone:          ptrIfNotEmpty(card.Phone),
			SourceFamilies: familyID,
		}); err != nil {
			lc.log.Warn("lacentrale: add location error", "garage", card.Name, "err", err)
		}
	}

	// Web presence.
	if card.Website != "" {
		domain := extractDomain(card.Website)
		if domain != "" {
			wp := &kg.DealerWebPresence{
				WebID:                ulid.Make().String(),
				DealerID:             dealerID,
				Domain:               domain,
				URLRoot:              card.Website,
				DiscoveredByFamilies: familyID,
			}
			if err := lc.graph.UpsertWebPresence(ctx, wp); err != nil {
				lc.log.Warn("lacentrale: upsert web presence error", "domain", domain, "err", err)
			}
		}
	}

	if err := lc.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
	}); err != nil {
		lc.log.Warn("lacentrale: record discovery error", "garage", card.Name, "err", err)
	}

	return isNew, nil
}

// HealthCheck fetches the annuaire root to verify the endpoint is up.
func (lc *LaCentrale) HealthCheck(ctx context.Context) error {
	reqURL := lc.baseURL + "/annuaire/garages-regions"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", cardexUA)
	resp, err := lc.client.Do(req)
	if err != nil {
		return fmt.Errorf("lacentrale health: %w", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("lacentrale health: HTTP %d", resp.StatusCode)
	}
	return nil
}

// ── HTML fetch & parse ────────────────────────────────────────────────────────

// fetchRegionIndex fetches /annuaire/garages-regions and returns the list of
// absolute region page URLs.
func (lc *LaCentrale) fetchRegionIndex(ctx context.Context) ([]string, error) {
	reqURL := lc.baseURL + "/annuaire/garages-regions"
	doc, err := lc.fetchHTML(ctx, reqURL)
	if err != nil {
		return nil, err
	}

	var regionURLs []string
	doc.Find("ul.regionList li.regionItem a.regionLink").Each(func(_ int, a *goquery.Selection) {
		href, exists := a.Attr("href")
		if !exists || href == "" {
			return
		}
		regionURLs = append(regionURLs, resolveURL(lc.baseURL, href))
	})
	return regionURLs, nil
}

// fetchGarageListingPage fetches a single garage listing page and returns the
// parsed garage cards and the URL of the next page (or "" if none).
// A 404 response is treated as "end of pages" — returns (nil, "", nil).
func (lc *LaCentrale) fetchGarageListingPage(ctx context.Context, pageURL string) ([]garageCard, string, error) {
	doc, err := lc.fetchHTML(ctx, pageURL)
	if err != nil {
		// 404 = end of pages, not a crawl error.
		if strings.Contains(err.Error(), "HTTP 404") {
			return nil, "", nil
		}
		return nil, "", err
	}

	cards := parseGarageListingPage(doc)

	// Next-page link.
	nextURL := ""
	doc.Find("a.pagination-next").Each(func(_ int, a *goquery.Selection) {
		if href, exists := a.Attr("href"); exists && href != "" {
			nextURL = resolveURL(lc.baseURL, href)
		}
	})

	return cards, nextURL, nil
}

// fetchHTML performs a GET request and returns a parsed goquery document.
func (lc *LaCentrale) fetchHTML(ctx context.Context, reqURL string) (*goquery.Document, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return nil, fmt.Errorf("lacentrale: build request: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "text/html,application/xhtml+xml")
	req.Header.Set("Accept-Language", "fr-FR,fr;q=0.9")

	resp, err := lc.client.Do(req)
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return nil, fmt.Errorf("lacentrale: http: %w", err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	if resp.StatusCode == http.StatusTooManyRequests {
		return nil, fmt.Errorf("lacentrale: HTTP 429 rate limited at %s", reqURL)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("lacentrale: HTTP %d at %s", resp.StatusCode, reqURL)
	}

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("lacentrale: parse HTML: %w", err)
	}
	return doc, nil
}

// ── HTML parsers ──────────────────────────────────────────────────────────────

// parseGarageListingPage extracts all garageCard entries from a garage listing
// page. Expects article.garageCard elements with data-garage-id attribute.
func parseGarageListingPage(doc *goquery.Document) []garageCard {
	var cards []garageCard

	doc.Find("article.garageCard[data-garage-id]").Each(func(_ int, s *goquery.Selection) {
		id, _ := s.Attr("data-garage-id")
		if id == "" {
			return
		}

		card := garageCard{GarageID: id}

		// Name: text of the first h2 (which contains an anchor).
		card.Name = strings.TrimSpace(s.Find("h2.garageName").First().Text())

		// Address: text of address element.
		card.Address = strings.TrimSpace(s.Find("address.garageAddress").First().Text())

		// Phone: text of phone element.
		card.Phone = strings.TrimSpace(s.Find("p.garagePhone").First().Text())

		// External website: anchor with rel="noopener" pointing to an absolute URL.
		s.Find("a.garageWebsite").Each(func(_ int, a *goquery.Selection) {
			if href, exists := a.Attr("href"); exists && strings.HasPrefix(href, "https://") {
				if card.Website == "" {
					card.Website = href
				}
			}
		})

		if card.Name == "" {
			return // skip cards without a name
		}
		cards = append(cards, card)
	})

	return cards
}

// ── Helpers ───────────────────────────────────────────────────────────────────

// parseFrenchAddress attempts to extract city and postal code from a French
// address string like "12 rue de la Paix, 75001 Paris".
// Returns (city, postalCode) — either may be nil on parse failure.
func parseFrenchAddress(raw string) (city, postalCode *string) {
	// Find last comma-separated segment which should be "75001 Paris".
	idx := strings.LastIndex(raw, ",")
	if idx < 0 {
		return nil, nil
	}
	rest := strings.TrimSpace(raw[idx+1:])
	parts := strings.SplitN(rest, " ", 2)
	if len(parts) == 2 {
		return ptr(parts[1]), ptr(parts[0])
	}
	return nil, nil
}

// resolveURL makes a relative href absolute using the given base.
func resolveURL(base, href string) string {
	if strings.HasPrefix(href, "http://") || strings.HasPrefix(href, "https://") {
		return href
	}
	return strings.TrimRight(base, "/") + "/" + strings.TrimLeft(href, "/")
}

// extractDomain returns the hostname (without www.) from a URL, or "".
func extractDomain(rawURL string) string {
	u, err := url.Parse(rawURL)
	if err != nil || u.Host == "" {
		return ""
	}
	return strings.TrimPrefix(u.Host, "www.")
}

func ptr(s string) *string { return &s }

func ptrIfNotEmpty(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}
