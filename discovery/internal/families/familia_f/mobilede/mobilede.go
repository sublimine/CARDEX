// Package mobilede implements sub-technique F.1 — mobile.de Händlersuche.
//
// mobile.de publishes an SEO-friendly static-HTML dealer directory at:
//
//	https://home.mobile.de/regional/haendler-{page}.html  (page = 0, 1, 2, …)
//
// Each page contains a list of <div class="dealerItem"> cards. Pagination
// continues until a page returns no cards or a 404/non-200 response.
//
// Two-phase crawl:
//  1. Listing pages — extract dealer name, address, external website URL and
//     internal mobile.de detail URL from each dealerItem card.
//  2. Detail page  — fetch the dealer's mobile.de profile page to extract the
//     phone number from div.phoneNumbers.dealerContactPhoneNumbers.
//
// Rate limiting: 1 req / 3 s across both listing and detail requests.
// robots.txt verified 2026-04-14: /regional/ is NOT disallowed.
//
// The dealer identifier stored in the KG uses type MOBILE_DE_ID whose value is
// the slug extracted from the detail URL path (e.g. "autohaus-muster-gmbh-12345").
package mobilede

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"path"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/oklog/ulid/v2"
	"golang.org/x/net/html"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	defaultBaseURL     = "https://home.mobile.de"
	defaultReqInterval = 3 * time.Second
	cardexUA           = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
	familyID           = "F"
	subTechID          = "F.1"
	subTechName        = "mobile.de Händlersuche"
	country            = "DE"
)

// MobileDe executes F.1 sub-technique crawl.
type MobileDe struct {
	graph       kg.KnowledgeGraph
	client      *http.Client
	baseURL     string
	reqInterval time.Duration
	log         *slog.Logger
}

// New creates a MobileDe executor with the production endpoint.
func New(graph kg.KnowledgeGraph) *MobileDe {
	return NewWithBaseURL(graph, defaultBaseURL, defaultReqInterval)
}

// NewWithBaseURL creates a MobileDe executor with a custom base URL and
// request interval (use interval=0 in tests).
func NewWithBaseURL(graph kg.KnowledgeGraph, baseURL string, reqInterval time.Duration) *MobileDe {
	return &MobileDe{
		graph:       graph,
		client:      &http.Client{Timeout: 30 * time.Second},
		baseURL:     baseURL,
		reqInterval: reqInterval,
		log:         slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (m *MobileDe) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (m *MobileDe) Name() string { return subTechName }

// dealerCard is the data extracted from a single dealerItem card.
type dealerCard struct {
	Name      string
	Address   string
	Website   string // external URL, may be empty
	DetailURL string // absolute URL to mobile.de dealer profile
	Slug      string // identifier extracted from DetailURL path
}

// Run crawls all listing pages for Germany, fetches each dealer's detail page
// for phone extraction, and upserts results into the KG.
func (m *MobileDe) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}

	for page := 0; ; page++ {
		if ctx.Err() != nil {
			break
		}

		if page > 0 && m.reqInterval > 0 {
			select {
			case <-ctx.Done():
				break
			case <-time.After(m.reqInterval):
			}
		}

		listURL := fmt.Sprintf("%s/regional/haendler-%d.html", m.baseURL, page)
		cards, err := m.fetchListingPage(ctx, listURL)
		if err != nil {
			m.log.Warn("mobilede: listing page error", "url", listURL, "err", err)
			result.Errors++
			// Stop pagination on persistent error (e.g. 404 = end of pages).
			break
		}
		if len(cards) == 0 {
			// Empty page — we've reached the end of the directory.
			break
		}

		for _, card := range cards {
			if ctx.Err() != nil {
				break
			}

			// Rate limit between detail fetches.
			if m.reqInterval > 0 {
				select {
				case <-ctx.Done():
					break
				case <-time.After(m.reqInterval):
				}
			}

			phone := ""
			if card.DetailURL != "" {
				phone, err = m.fetchPhone(ctx, card.DetailURL)
				if err != nil {
					m.log.Warn("mobilede: detail page error", "url", card.DetailURL, "err", err)
					// Non-fatal: continue without phone.
				}
			}

			upserted, err := m.upsert(ctx, card, phone)
			if err != nil {
				m.log.Warn("mobilede: upsert error", "name", card.Name, "err", err)
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
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, country).Observe(result.Duration.Seconds())
	m.log.Info("mobilede: done",
		"discovered", result.Discovered,
		"confirmed", result.Confirmed,
		"errors", result.Errors,
	)
	return result, nil
}

// upsert writes a dealer card to the KG. Returns true when a new entity was
// created, false when an existing one was re-confirmed.
func (m *MobileDe) upsert(ctx context.Context, card dealerCard, phone string) (bool, error) {
	now := time.Now().UTC()

	// Check if this dealer already exists by MOBILE_DE_ID.
	existing, err := m.graph.FindDealerByIdentifier(ctx, kg.IdentifierMobileDeID, card.Slug)
	if err != nil {
		return false, fmt.Errorf("mobilede.upsert find: %w", err)
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
	if err := m.graph.UpsertDealer(ctx, entity); err != nil {
		return false, fmt.Errorf("mobilede.upsert dealer: %w", err)
	}

	if isNew {
		if err := m.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
			IdentifierID:   ulid.Make().String(),
			DealerID:       dealerID,
			IdentifierType: kg.IdentifierMobileDeID,
			IdentifierValue: card.Slug,
		}); err != nil {
			return false, fmt.Errorf("mobilede.upsert identifier: %w", err)
		}
	}

	// Add location (address + optional phone).
	if card.Address != "" || phone != "" {
		addr1, postalCode, city := parseGermanAddress(card.Address)
		phonePtr := ptrIfNotEmpty(phone)
		if err := m.graph.AddLocation(ctx, &kg.DealerLocation{
			LocationID:     ulid.Make().String(),
			DealerID:       dealerID,
			IsPrimary:      true,
			AddressLine1:   addr1,
			PostalCode:     postalCode,
			City:           city,
			CountryCode:    country,
			Phone:          phonePtr,
			SourceFamilies: familyID,
		}); err != nil {
			m.log.Warn("mobilede: add location error", "dealer", card.Name, "err", err)
		}
	}

	// Record web presence if we have an external website.
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
			if err := m.graph.UpsertWebPresence(ctx, wp); err != nil {
				m.log.Warn("mobilede: upsert web presence error", "domain", domain, "err", err)
			}
		}
	}

	// Audit trail.
	if err := m.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
	}); err != nil {
		m.log.Warn("mobilede: record discovery error", "dealer", card.Name, "err", err)
	}

	return isNew, nil
}

// HealthCheck fetches the regional directory root to verify the endpoint is up.
func (m *MobileDe) HealthCheck(ctx context.Context) error {
	reqURL := m.baseURL + "/regional/haendler-0.html"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", cardexUA)
	resp, err := m.client.Do(req)
	if err != nil {
		return fmt.Errorf("mobilede health: %w", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("mobilede health: HTTP %d", resp.StatusCode)
	}
	return nil
}

// ── HTML fetch & parse ────────────────────────────────────────────────────────

// fetchListingPage fetches a haendler listing page and returns all dealer cards
// found. Returns an empty slice (and no error) when the page returns 404.
func (m *MobileDe) fetchListingPage(ctx context.Context, pageURL string) ([]dealerCard, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, pageURL, nil)
	if err != nil {
		return nil, fmt.Errorf("mobilede: build request: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "text/html,application/xhtml+xml")
	req.Header.Set("Accept-Language", "de-DE,de;q=0.9")

	resp, err := m.client.Do(req)
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return nil, fmt.Errorf("mobilede: http: %w", err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	if resp.StatusCode == http.StatusNotFound {
		return nil, nil // end of pages
	}
	if resp.StatusCode == http.StatusTooManyRequests {
		return nil, fmt.Errorf("mobilede: HTTP 429 rate limited")
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("mobilede: HTTP %d at %s", resp.StatusCode, pageURL)
	}

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("mobilede: parse HTML: %w", err)
	}

	return parseListingPage(doc, m.baseURL), nil
}

// fetchPhone fetches a dealer detail page and returns the first phone number
// found in div.phoneNumbers.dealerContactPhoneNumbers.
func (m *MobileDe) fetchPhone(ctx context.Context, detailURL string) (string, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, detailURL, nil)
	if err != nil {
		return "", fmt.Errorf("mobilede: build detail request: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "text/html,application/xhtml+xml")
	req.Header.Set("Accept-Language", "de-DE,de;q=0.9")

	resp, err := m.client.Do(req)
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return "", fmt.Errorf("mobilede: http detail: %w", err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("mobilede: detail HTTP %d", resp.StatusCode)
	}

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		return "", fmt.Errorf("mobilede: parse detail HTML: %w", err)
	}

	phone := strings.TrimSpace(
		doc.Find("div.phoneNumbers.dealerContactPhoneNumbers span.phoneNumber").First().Text(),
	)
	return phone, nil
}

// ── HTML parsers ──────────────────────────────────────────────────────────────

// parseListingPage extracts all dealerCard entries from a haendler listing page.
func parseListingPage(doc *goquery.Document, baseURL string) []dealerCard {
	var cards []dealerCard

	doc.Find("div.dealerItem").Each(func(_ int, s *goquery.Selection) {
		card := dealerCard{}

		// Name: text content of the first h3 element.
		card.Name = strings.TrimSpace(s.Find("h3").First().Text())
		if card.Name == "" {
			return // skip cards without a name
		}

		// Internal detail URL: first a[href] that contains "/haendler/".
		s.Find("a").Each(func(_ int, a *goquery.Selection) {
			href, exists := a.Attr("href")
			if !exists {
				return
			}
			if strings.Contains(href, "/haendler/") && card.DetailURL == "" {
				card.DetailURL = resolveURL(baseURL, href)
				card.Slug = slugFromPath(href)
			}
			// External website: absolute HTTPS URL NOT pointing to baseURL.
			if strings.HasPrefix(href, "https://") && !strings.Contains(href, "mobile.de") {
				if card.Website == "" {
					card.Website = href
				}
			}
		})

		// Address: text nodes directly inside the div (not in child elements).
		card.Address = extractTextNodes(s, card.Name)

		if card.Slug == "" {
			// Fallback: derive slug from the dealer name.
			card.Slug = "name-" + strings.ToLower(strings.ReplaceAll(card.Name, " ", "-"))
		}

		cards = append(cards, card)
	})

	return cards
}

// extractTextNodes collects direct text-node content from a selection,
// excluding the text of any named heading.
func extractTextNodes(s *goquery.Selection, excludeName string) string {
	var parts []string
	s.Contents().Each(func(_ int, child *goquery.Selection) {
		if len(child.Nodes) == 0 {
			return
		}
		if child.Nodes[0].Type == html.TextNode {
			t := strings.TrimSpace(child.Text())
			if t != "" && t != excludeName {
				parts = append(parts, t)
			}
		}
	})
	return strings.Join(parts, " ")
}

// ── Helpers ───────────────────────────────────────────────────────────────────

// resolveURL makes a relative href absolute using the given base URL.
func resolveURL(base, href string) string {
	if strings.HasPrefix(href, "http://") || strings.HasPrefix(href, "https://") {
		return href
	}
	return strings.TrimRight(base, "/") + "/" + strings.TrimLeft(href, "/")
}

// slugFromPath extracts the last non-empty path segment from a URL path.
// E.g. "/haendler/autohaus-muster-gmbh-12345" → "autohaus-muster-gmbh-12345"
func slugFromPath(rawPath string) string {
	p := strings.TrimSuffix(path.Base(rawPath), ".html")
	p = strings.TrimSuffix(p, path.Ext(p))
	return p
}

// extractDomain returns the hostname from a URL string, or "" on parse error.
func extractDomain(rawURL string) string {
	u, err := url.Parse(rawURL)
	if err != nil || u.Host == "" {
		return ""
	}
	return strings.TrimPrefix(u.Host, "www.")
}

// parseGermanAddress splits a raw German address string of the form
// "Musterstraße 1, 12345 Berlin" into (addressLine1, postalCode, city).
// Returns (nil, nil, nil) when the input is empty. Falls back to storing
// everything in addressLine1 when the format is unexpected.
func parseGermanAddress(raw string) (addressLine1, postalCode, city *string) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, nil, nil
	}
	// Try to split on the last comma: "street, postalCode city"
	idx := strings.LastIndex(raw, ",")
	if idx < 0 {
		return ptr(raw), nil, nil
	}
	street := strings.TrimSpace(raw[:idx])
	rest := strings.TrimSpace(raw[idx+1:])

	// rest should be "12345 Berlin" — split on first space.
	parts := strings.SplitN(rest, " ", 2)
	if len(parts) == 2 {
		return ptr(street), ptr(parts[0]), ptr(parts[1])
	}
	// Fallback: can't parse; store whole string in line 1.
	return ptr(raw), nil, nil
}

func ptr(s string) *string { return &s }

func ptrIfNotEmpty(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}
