// Package traxio implements sub-technique G.BE.1 — TRAXIO member directory (Belgium).
//
// TRAXIO is the Belgian federation for the automotive, bicycle, and motorcycle sector
// (formerly split into FEDERAUTO, RENTA/MOBILITAS, and others; merged ~2018).
// The member search is accessible at:
//
//	https://www.traxio.be/fr/membres      (French UI)
//	https://www.traxio.be/nl/leden        (Dutch UI)
//
// # Discovery approach:
//
//  1. Fetch the member search page: GET /fr/membres?page={n}
//     — the site returns an HTML listing of member cards paginated in groups of ~25.
//  2. Parse each card with goquery: extract company name, city, postal code, and
//     the member detail-page URL.
//  3. Follow each detail URL to extract phone, website, and TRAXIO member number.
//  4. De-duplicate by member number (fallback: canonical name + postal code).
//  5. Upsert via kg.KnowledgeGraph with IdentifierMemberTraxio.
//
// robots.txt verified 2026-04-15: no Disallow rules targeting /fr/membres or
// /nl/leden. Full crawl permitted.
//
// Rate limiting: 1 req / 3 s. Country: BE.
// ConfidenceContributed: 0.20 (BaseWeights["G"]).
package traxio

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID    = "G"
	subTechID   = "G.BE.1"
	subTechName = "TRAXIO member directory (BE)"
	countryBE   = "BE"

	defaultBaseURL     = "https://www.traxio.be"
	defaultMemberPath  = "/fr/membres"
	defaultReqInterval = 3 * time.Second
	maxPages           = 50 // safety cap: ~1 250 members at 25 per page
	cardexUA           = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
)

// memberRecord holds data scraped from a TRAXIO member listing or detail page.
type memberRecord struct {
	MemberID   string // TRAXIO member number (e.g. "BE0123456789")
	Name       string
	Street     string
	PostalCode string
	City       string
	Phone      string
	Website    string
	DetailURL  string
}

// identifier returns the primary identifier: MemberID if set, else name+postalCode.
func (r *memberRecord) identifier() string {
	if r.MemberID != "" {
		return r.MemberID
	}
	return strings.ToLower(r.Name) + ":" + r.PostalCode
}

// Traxio executes the G.BE.1 sub-technique crawl.
type Traxio struct {
	graph       kg.KnowledgeGraph
	client      *http.Client
	baseURL     string
	reqInterval time.Duration
	log         *slog.Logger
}

// New returns a Traxio executor with the production endpoint.
func New(graph kg.KnowledgeGraph) *Traxio {
	return NewWithBaseURL(graph, defaultBaseURL, defaultReqInterval)
}

// NewWithBaseURL returns a Traxio executor with a custom base URL and interval
// (use interval=0 in tests).
func NewWithBaseURL(graph kg.KnowledgeGraph, baseURL string, reqInterval time.Duration) *Traxio {
	return &Traxio{
		graph:       graph,
		client:      &http.Client{Timeout: 30 * time.Second},
		baseURL:     baseURL,
		reqInterval: reqInterval,
		log:         slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (t *Traxio) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (t *Traxio) Name() string { return subTechName }

// Run fetches all TRAXIO member pages, parses member cards, and upserts each
// member into the KG.
func (t *Traxio) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: countryBE}

	seen := make(map[string]bool) // dedup by identifier

	for page := 1; page <= maxPages; page++ {
		if ctx.Err() != nil {
			break
		}

		if t.reqInterval > 0 && page > 1 {
			select {
			case <-ctx.Done():
				goto done
			case <-time.After(t.reqInterval):
			}
		}

		members, hasMore, err := t.fetchPage(ctx, page)
		if err != nil {
			t.log.Warn("traxio: page fetch error", "page", page, "err", err)
			result.Errors++
			break
		}
		if len(members) == 0 {
			break // empty page = end of listing
		}

		t.log.Debug("traxio: page fetched", "page", page, "members", len(members))

		for _, m := range members {
			if ctx.Err() != nil {
				goto done
			}

			key := m.identifier()
			if seen[key] {
				continue
			}
			seen[key] = true

			// Optionally follow detail page to enrich phone/website/memberID.
			if m.DetailURL != "" {
				if t.reqInterval > 0 {
					select {
					case <-ctx.Done():
						goto done
					case <-time.After(t.reqInterval):
					}
				}
				if enriched, err := t.fetchDetail(ctx, m); err != nil {
					t.log.Debug("traxio: detail fetch error", "url", m.DetailURL, "err", err)
				} else if enriched != nil {
					m = enriched
				}
			}

			upserted, err := t.upsert(ctx, m)
			if err != nil {
				t.log.Warn("traxio: upsert error", "name", m.Name, "err", err)
				result.Errors++
				continue
			}
			if upserted {
				result.Discovered++
				metrics.DealersTotal.WithLabelValues(familyID, countryBE).Inc()
			} else {
				result.Confirmed++
			}
		}

		if !hasMore {
			break
		}
	}

done:
	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, countryBE).Observe(result.Duration.Seconds())
	t.log.Info("traxio: done",
		"discovered", result.Discovered,
		"confirmed", result.Confirmed,
		"errors", result.Errors,
	)
	return result, nil
}

// HealthCheck verifies the TRAXIO member page is reachable.
func (t *Traxio) HealthCheck(ctx context.Context) error {
	reqURL := t.baseURL + defaultMemberPath
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", cardexUA)
	resp, err := t.client.Do(req)
	if err != nil {
		return fmt.Errorf("traxio health: %w", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("traxio health: HTTP %d", resp.StatusCode)
	}
	return nil
}

// ── Page fetcher ──────────────────────────────────────────────────────────────

// fetchPage fetches a single paginated listing page and returns the scraped
// member records plus a hasMore flag.
func (t *Traxio) fetchPage(ctx context.Context, page int) ([]*memberRecord, bool, error) {
	pageURL := t.baseURL + defaultMemberPath
	if page > 1 {
		pageURL = fmt.Sprintf("%s?page=%d", pageURL, page)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, pageURL, nil)
	if err != nil {
		return nil, false, fmt.Errorf("traxio page: build req: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "text/html,application/xhtml+xml")
	req.Header.Set("Accept-Language", "fr-BE,fr;q=0.9,nl;q=0.8")

	resp, err := t.client.Do(req)
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return nil, false, fmt.Errorf("traxio page: http: %w", err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	if resp.StatusCode == http.StatusNotFound {
		return nil, false, nil // past last page
	}
	if resp.StatusCode != http.StatusOK {
		return nil, false, fmt.Errorf("traxio page: HTTP %d at %s", resp.StatusCode, pageURL)
	}

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		return nil, false, fmt.Errorf("traxio page: parse HTML: %w", err)
	}

	return ParseMemberPage(doc, t.baseURL)
}

// ParseMemberPage extracts member records from a TRAXIO listing page.
// The TRAXIO site (Craft CMS) renders member cards as article or div elements
// with class patterns like "member-card", "company-item", or similar.
// We probe multiple selectors to stay robust to template changes.
//
// Exported for tests.
func ParseMemberPage(doc *goquery.Document, baseURL string) ([]*memberRecord, bool, error) {
	var members []*memberRecord

	// Probe common card selectors used by Craft CMS / typical BE association sites.
	cardSel := ".member-card, .company-card, article.member, .lid-item, .membre-item, .entry--member"
	doc.Find(cardSel).Each(func(_ int, s *goquery.Selection) {
		m := parseMemberCard(s, baseURL)
		if m != nil && m.Name != "" {
			members = append(members, m)
		}
	})

	// Fallback: generic list items that contain a name + address pattern.
	if len(members) == 0 {
		doc.Find("ul.members li, ul.leden li, .members-list li").Each(func(_ int, s *goquery.Selection) {
			m := parseMemberCard(s, baseURL)
			if m != nil && m.Name != "" {
				members = append(members, m)
			}
		})
	}

	// Check for a "next page" link.
	hasMore := doc.Find("a[rel=next], .pagination .next, a.next-page").Length() > 0

	return members, hasMore, nil
}

// parseMemberCard extracts a single member record from a card-level selection.
func parseMemberCard(s *goquery.Selection, baseURL string) *memberRecord {
	m := &memberRecord{}

	// Name: heading element within the card.
	m.Name = strings.TrimSpace(s.Find("h2, h3, h4, .name, .company-name, .title").First().Text())
	if m.Name == "" {
		m.Name = strings.TrimSpace(s.Find("strong, b").First().Text())
	}

	// Address block: look for a common address container.
	addrEl := s.Find(".address, address, .location, .adres")
	if addrEl.Length() == 0 {
		addrEl = s // fall back to entire card text
	}
	addrText := strings.TrimSpace(addrEl.Text())
	parseAddressText(addrText, m)

	// Detail URL.
	if href, exists := s.Find("a").First().Attr("href"); exists && href != "" {
		m.DetailURL = resolveURL(baseURL, href)
	}

	// Phone inline.
	m.Phone = strings.TrimSpace(s.Find("a[href^='tel:']").First().AttrOr("href", ""))
	m.Phone = strings.TrimPrefix(m.Phone, "tel:")

	// Website inline.
	s.Find("a[href^='http']").Each(func(_ int, a *goquery.Selection) {
		if href, ok := a.Attr("href"); ok {
			if !strings.Contains(href, "traxio.be") && m.Website == "" {
				m.Website = href
			}
		}
	})

	return m
}

// parseAddressText attempts to extract postal code and city from a free-text
// address string. Belgian postal codes are 4-digit numbers (1000–9999).
func parseAddressText(text string, m *memberRecord) {
	lines := strings.Split(text, "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		// Look for 4-digit postal code followed by city name.
		// Pattern: "1234 Cityname" or "1234  Cityname"
		for i, ch := range line {
			if ch >= '1' && ch <= '9' && i+4 <= len(line) {
				candidate := line[i : i+4]
				if isDigits(candidate) && i+5 <= len(line) {
					rest := strings.TrimSpace(line[i+4:])
					if rest != "" && !isDigits(rest[:1]) {
						m.PostalCode = candidate
						m.City = rest
						return
					}
				}
			}
		}
	}
}

func isDigits(s string) bool {
	for _, c := range s {
		if c < '0' || c > '9' {
			return false
		}
	}
	return len(s) > 0
}

// ── Detail page ───────────────────────────────────────────────────────────────

// fetchDetail fetches a TRAXIO member detail page and enriches the memberRecord.
func (t *Traxio) fetchDetail(ctx context.Context, m *memberRecord) (*memberRecord, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, m.DetailURL, nil)
	if err != nil {
		return nil, fmt.Errorf("traxio detail: build req: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "text/html,application/xhtml+xml")
	req.Header.Set("Accept-Language", "fr-BE,fr;q=0.9")

	resp, err := t.client.Do(req)
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return nil, fmt.Errorf("traxio detail: http: %w", err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	if resp.StatusCode != http.StatusOK {
		return nil, nil // non-critical; skip enrichment
	}

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		return nil, nil
	}

	return enrichFromDetail(doc, m), nil
}

// enrichFromDetail updates a memberRecord with data from a detail page.
func enrichFromDetail(doc *goquery.Document, m *memberRecord) *memberRecord {
	enriched := *m // copy

	// Member number: look for patterns like "N° membre: 12345" or data-member-id attr.
	doc.Find("[data-member-id], [data-lid-nr]").Each(func(_ int, s *goquery.Selection) {
		if id := s.AttrOr("data-member-id", s.AttrOr("data-lid-nr", "")); id != "" && enriched.MemberID == "" {
			enriched.MemberID = id
		}
	})
	// Text-based fallback for member number.
	doc.Find(".member-number, .lid-nummer, .numero-membre").Each(func(_ int, s *goquery.Selection) {
		if enriched.MemberID == "" {
			enriched.MemberID = strings.TrimSpace(s.Text())
		}
	})

	// Phone.
	if enriched.Phone == "" {
		enriched.Phone = strings.TrimPrefix(
			doc.Find("a[href^='tel:']").First().AttrOr("href", ""), "tel:")
	}

	// Website.
	if enriched.Website == "" {
		doc.Find("a[href^='http']").Each(func(_ int, a *goquery.Selection) {
			if href, ok := a.Attr("href"); ok && !strings.Contains(href, "traxio.be") {
				enriched.Website = href
			}
		})
	}

	return &enriched
}

// ── KG upsert ─────────────────────────────────────────────────────────────────

func (t *Traxio) upsert(ctx context.Context, m *memberRecord) (bool, error) {
	now := time.Now().UTC()
	idValue := m.identifier()

	existing, err := t.graph.FindDealerByIdentifier(ctx, kg.IdentifierMemberTraxio, idValue)
	if err != nil {
		return false, fmt.Errorf("traxio.upsert find: %w", err)
	}

	isNew := existing == ""
	dealerID := existing
	if isNew {
		dealerID = ulid.Make().String()
	}

	if err := t.graph.UpsertDealer(ctx, &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     m.Name,
		NormalizedName:    strings.ToLower(m.Name),
		CountryCode:       countryBE,
		Status:            kg.StatusUnverified,
		ConfidenceScore:   kg.BaseWeights[familyID],
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}); err != nil {
		return false, fmt.Errorf("traxio.upsert dealer: %w", err)
	}

	if isNew {
		if err := t.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
			IdentifierID:    ulid.Make().String(),
			DealerID:        dealerID,
			IdentifierType:  kg.IdentifierMemberTraxio,
			IdentifierValue: idValue,
		}); err != nil {
			return false, fmt.Errorf("traxio.upsert identifier: %w", err)
		}
	}

	if m.Street != "" || m.PostalCode != "" || m.City != "" {
		if err := t.graph.AddLocation(ctx, &kg.DealerLocation{
			LocationID:     ulid.Make().String(),
			DealerID:       dealerID,
			IsPrimary:      true,
			AddressLine1:   ptrIfNotEmpty(m.Street),
			PostalCode:     ptrIfNotEmpty(m.PostalCode),
			City:           ptrIfNotEmpty(m.City),
			CountryCode:    countryBE,
			Phone:          ptrIfNotEmpty(m.Phone),
			SourceFamilies: familyID,
		}); err != nil {
			t.log.Warn("traxio: add location error", "dealer", m.Name, "err", err)
		}
	}

	if m.Website != "" {
		domain := extractDomain(m.Website)
		if domain != "" {
			if err := t.graph.UpsertWebPresence(ctx, &kg.DealerWebPresence{
				WebID:                ulid.Make().String(),
				DealerID:             dealerID,
				Domain:               domain,
				URLRoot:              m.Website,
				DiscoveredByFamilies: familyID,
			}); err != nil {
				t.log.Warn("traxio: upsert web presence error", "domain", domain, "err", err)
			}
		}
	}

	if err := t.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
		SourceURL:             ptrIfNotEmpty(m.DetailURL),
	}); err != nil {
		t.log.Warn("traxio: record discovery error", "dealer", m.Name, "err", err)
	}

	return isNew, nil
}

// ── Helpers ───────────────────────────────────────────────────────────────────

func ptrIfNotEmpty(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

func extractDomain(rawURL string) string {
	if !strings.HasPrefix(rawURL, "http://") && !strings.HasPrefix(rawURL, "https://") {
		rawURL = "https://" + rawURL
	}
	after := strings.SplitN(rawURL, "//", 2)
	if len(after) < 2 {
		return ""
	}
	host := strings.SplitN(after[1], "/", 2)[0]
	return strings.TrimPrefix(host, "www.")
}

func resolveURL(baseURL, href string) string {
	if strings.HasPrefix(href, "http") {
		return href
	}
	if strings.HasPrefix(href, "/") {
		return baseURL + href
	}
	return baseURL + "/" + href
}
