// Package mobilians implements sub-technique G.FR.1 — Mobilians member directory (France).
//
// Mobilians (formerly CNPA) is the French automotive professional trade union.
// Its member directory (annuaire) is at:
//
//	https://mobilians.fr/annuaire/
//
// The annuaire page is a Joomla + YOOtheme site with a map-based member search.
// The search endpoint is `libraries/search_es.php?type=json` which returns a
// JSON list of members — but it returns HTTP 403 when called directly without a
// browser session (CSRF or session-based protection).
//
// Strategy: two-phase with browser.
//
//	Phase 1 — InterceptXHR:
//	  Navigate to /annuaire/ with browser.InterceptXHR. If the page fires an
//	  XHR call to search_es.php on load (default results), capture the JSON.
//
//	Phase 2 — FetchHTML fallback:
//	  If InterceptXHR finds no data, use browser.FetchHTML to render the
//	  annuaire page and parse member cards from the rendered HTML.
//
// robots.txt: not verified (mobilians.fr robots.txt not checked in Sprint 6
// research). Crawl is limited to the /annuaire/ path with 3s per-host interval.
//
// Identifier type: MEMBER_MOBILIANS with value = member ID from JSON or
// normalised slug from the member name.
// ConfidenceContributed: 0.20 (BaseWeights["G"]).
package mobilians

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"regexp"
	"strings"
	"time"
	"unicode"

	"github.com/PuerkitoBio/goquery"
	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/browser"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	defaultBaseURL  = "https://mobilians.fr"
	annuairePath    = "/annuaire/"
	familyID        = "G"
	subTechID       = "G.FR.1"
	subTechName     = "Mobilians member directory"
	country         = "FR"
)

// Mobilians executes the G.FR.1 sub-technique.
type Mobilians struct {
	graph   kg.KnowledgeGraph
	b       browser.Browser
	baseURL string
	log     *slog.Logger
}

// New creates a Mobilians executor with production settings.
func New(graph kg.KnowledgeGraph, b browser.Browser) *Mobilians {
	return NewWithBaseURL(graph, b, defaultBaseURL)
}

// NewWithBaseURL creates a Mobilians executor with a custom base URL (for tests).
func NewWithBaseURL(graph kg.KnowledgeGraph, b browser.Browser, baseURL string) *Mobilians {
	return &Mobilians{
		graph:   graph,
		b:       b,
		baseURL: baseURL,
		log:     slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (m *Mobilians) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (m *Mobilians) Name() string { return subTechName }

// Run executes the Mobilians member directory crawl.
func (m *Mobilians) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}

	if m.b == nil {
		m.log.Warn("mobilians: browser not initialised — skipping G.FR.1")
		result.Duration = time.Since(start)
		return result, nil
	}

	annuaireURL := m.baseURL + annuairePath
	m.log.Info("mobilians: starting crawl", "url", annuaireURL)

	members, strategy, err := m.fetchMembers(ctx, annuaireURL)
	if err != nil {
		result.Errors++
		result.Duration = time.Since(start)
		return result, fmt.Errorf("mobilians: fetch members: %w", err)
	}

	m.log.Info("mobilians: members fetched",
		"count", len(members), "strategy", strategy)

	for _, mem := range members {
		if ctx.Err() != nil {
			break
		}
		if mem.Name == "" {
			continue
		}
		upserted, err := m.upsert(ctx, mem)
		if err != nil {
			m.log.Warn("mobilians: upsert error", "name", mem.Name, "err", err)
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

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, country).Observe(result.Duration.Seconds())
	m.log.Info("mobilians: done",
		"discovered", result.Discovered,
		"confirmed", result.Confirmed,
		"errors", result.Errors,
	)
	return result, nil
}

// fetchMembers tries Phase 1 (InterceptXHR) then Phase 2 (FetchHTML).
// Returns a slice of MobiliansMember and the strategy used ("xhr" or "html").
func (m *Mobilians) fetchMembers(ctx context.Context, annuaireURL string) ([]MobiliansMember, string, error) {
	// Phase 1: InterceptXHR — capture search_es.php JSON on page load.
	filter := browser.XHRFilter{
		URLPattern:    `search_es\.php`,
		MethodFilter:  []string{"GET", "POST"},
		MinStatusCode: 200,
	}
	captures, err := m.b.InterceptXHR(ctx, annuaireURL, filter)
	if err != nil {
		m.log.Warn("mobilians: InterceptXHR error", "err", err)
		// Non-fatal — fall through to Phase 2.
	}
	for _, c := range captures {
		members, parseErr := ParseMembersJSON(c.ResponseBody)
		if parseErr == nil && len(members) > 0 {
			return members, "xhr", nil
		}
	}

	// Phase 2: FetchHTML — parse rendered member cards.
	res, err := m.b.FetchHTML(ctx, annuaireURL, &browser.FetchOptions{
		WaitForNetworkIdle: true,
		Timeout:            30 * time.Second,
	})
	if err != nil {
		return nil, "html", fmt.Errorf("mobilians: FetchHTML: %w", err)
	}

	members := ParseMembersHTML(res.HTML)
	if len(members) == 0 {
		m.log.Info("mobilians: no members found in rendered HTML",
			"reason", "annuaire may require JS form interaction for full listing; defer to Sprint 9")
	}
	return members, "html", nil
}

// ── JSON parser (Phase 1 — XHR) ───────────────────────────────────────────────

// mobiliansMemberJSON mirrors the member shape returned by search_es.php.
// The exact schema is not public; this struct covers common Joomla search plugin
// response fields.
type mobiliansMemberJSON struct {
	ID      interface{} `json:"id"`   // may be int or string
	Title   string      `json:"title"`
	Name    string      `json:"name"`
	Address string      `json:"address"`
	Street  string      `json:"street"`
	Zip     string      `json:"zip"`
	City    string      `json:"city"`
	Phone   string      `json:"phone"`
	Email   string      `json:"email"`
	Type    string      `json:"type"`
	URL     string      `json:"url"`
}

// mobiliansMembersResponse wraps common Joomla search plugin response shapes.
type mobiliansMembersResponse struct {
	Hits    []mobiliansMemberJSON `json:"hits"`
	Results []mobiliansMemberJSON `json:"results"`
	Items   []mobiliansMemberJSON `json:"items"`
	Data    []mobiliansMemberJSON `json:"data"`
}

// ParseMembersJSON parses a raw XHR response body from search_es.php.
// Exported for testing.
func ParseMembersJSON(body []byte) ([]MobiliansMember, error) {
	if len(body) == 0 {
		return nil, nil
	}

	// Try object envelope first; ignore error — body may be a bare array.
	var resp mobiliansMembersResponse
	_ = json.Unmarshal(body, &resp)

	rawList := resp.Hits
	if len(rawList) == 0 {
		rawList = resp.Results
	}
	if len(rawList) == 0 {
		rawList = resp.Items
	}
	if len(rawList) == 0 {
		rawList = resp.Data
	}

	// Bare array fallback.
	if len(rawList) == 0 {
		var arr []mobiliansMemberJSON
		if err := json.Unmarshal(body, &arr); err == nil {
			rawList = arr
		}
	}

	members := make([]MobiliansMember, 0, len(rawList))
	for _, raw := range rawList {
		name := raw.Title
		if name == "" {
			name = raw.Name
		}
		if name == "" {
			continue
		}

		idStr := fmt.Sprintf("%v", raw.ID)
		if idStr == "<nil>" || idStr == "0" {
			idStr = ""
		}

		addr := raw.Street
		if addr == "" {
			addr = raw.Address
		}

		members = append(members, MobiliansMember{
			ID:      idStr,
			Name:    strings.TrimSpace(name),
			Street:  strings.TrimSpace(addr),
			Zip:     strings.TrimSpace(raw.Zip),
			City:    strings.TrimSpace(raw.City),
			Phone:   strings.TrimSpace(raw.Phone),
			Email:   strings.TrimSpace(raw.Email),
			Website: strings.TrimSpace(raw.URL),
		})
	}
	return members, nil
}

// ── HTML parser (Phase 2 — FetchHTML) ────────────────────────────────────────

// ParseMembersHTML extracts MobiliansMember records from rendered annuaire HTML.
//
// Mobilians uses Joomla + YOOtheme; member cards are typically rendered in
// article elements or div.uk-card containers. The parser uses a broad approach:
// look for elements with class patterns matching "item", "card", "entry",
// "member", "adherent", then extract text content for name/address/phone.
//
// Exported for testing.
func ParseMembersHTML(htmlContent string) []MobiliansMember {
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(htmlContent))
	if err != nil {
		return nil
	}

	var members []MobiliansMember

	// Try common Joomla/YOOtheme selectors for member cards.
	selectors := []string{
		"article.uk-article",
		".uk-card",
		".yoo-directory-item",
		".sobipro-entry",
		".sp-field-value",
		"[class*='member']",
		"[class*='adherent']",
		"[class*='item']",
	}

	seen := make(map[string]bool)

	for _, sel := range selectors {
		doc.Find(sel).Each(func(_ int, s *goquery.Selection) {
			mem := extractMemberFromCard(s)
			if mem.Name == "" || seen[mem.Name] {
				return
			}
			seen[mem.Name] = true
			members = append(members, mem)
		})
		if len(members) > 0 {
			break // found results with this selector; no need to try others
		}
	}

	return members
}

// extractMemberFromCard extracts a MobiliansMember from a single card selection.
func extractMemberFromCard(s *goquery.Selection) MobiliansMember {
	var mem MobiliansMember

	// Name: first h1, h2, or h3 in the card.
	s.Find("h1, h2, h3").First().Each(func(_ int, h *goquery.Selection) {
		mem.Name = strings.TrimSpace(h.Text())
	})

	// Address: look for elements containing typical French address patterns.
	s.Find("p, span, div").Each(func(_ int, el *goquery.Selection) {
		text := strings.TrimSpace(el.Text())
		if text == "" || text == mem.Name {
			return
		}

		// French phone pattern: starts with 0 and has 10 digits.
		if isFrenchPhone(text) && mem.Phone == "" {
			mem.Phone = text
			return
		}

		// French postal code: 5 digits at start of word boundary.
		if containsFrenchPostalCode(text) && mem.Street == "" {
			mem.Street = text
			// Try to split postal code and city.
			if zip, city := extractZipCity(text); zip != "" {
				mem.Zip = zip
				mem.City = city
			}
		}
	})

	// Email: <a href="mailto:...">
	s.Find(`a[href^="mailto:"]`).First().Each(func(_ int, a *goquery.Selection) {
		href, _ := a.Attr("href")
		mem.Email = strings.TrimPrefix(href, "mailto:")
	})

	// Website: <a href="http..."> not mail
	s.Find(`a[href^="http"]`).First().Each(func(_ int, a *goquery.Selection) {
		href, _ := a.Attr("href")
		if !strings.Contains(href, "mobilians.fr") {
			mem.Website = href
		}
	})

	return mem
}

// ── MobiliansMember ───────────────────────────────────────────────────────────

// MobiliansMember holds the data extracted for a single Mobilians directory member.
type MobiliansMember struct {
	ID      string
	Name    string
	Street  string
	Zip     string
	City    string
	Phone   string
	Email   string
	Website string
}

func (m MobiliansMember) identifier() string {
	if m.ID != "" {
		return m.ID
	}
	// Normalised slug from name.
	slug := strings.ToLower(m.Name)
	slug = strings.Map(func(r rune) rune {
		if unicode.IsLetter(r) || unicode.IsDigit(r) {
			return r
		}
		return '-'
	}, slug)
	return strings.Trim(slug, "-")
}

// ── KG upsert ────────────────────────────────────────────────────────────────

func (m *Mobilians) upsert(ctx context.Context, mem MobiliansMember) (bool, error) {
	now := time.Now().UTC()
	idValue := mem.identifier()

	existing, err := m.graph.FindDealerByIdentifier(ctx, kg.IdentifierMemberMobilians, idValue)
	if err != nil {
		return false, fmt.Errorf("mobilians.upsert find: %w", err)
	}

	isNew := existing == ""
	dealerID := existing
	if isNew {
		dealerID = ulid.Make().String()
	}

	if err := m.graph.UpsertDealer(ctx, &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     mem.Name,
		NormalizedName:    strings.ToLower(mem.Name),
		CountryCode:       country,
		Status:            kg.StatusUnverified,
		ConfidenceScore:   kg.BaseWeights[familyID],
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}); err != nil {
		return false, fmt.Errorf("mobilians.upsert dealer: %w", err)
	}

	if isNew {
		if err := m.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
			IdentifierID:    ulid.Make().String(),
			DealerID:        dealerID,
			IdentifierType:  kg.IdentifierMemberMobilians,
			IdentifierValue: idValue,
		}); err != nil {
			return false, fmt.Errorf("mobilians.upsert identifier: %w", err)
		}
	}

	if mem.Street != "" || mem.Zip != "" || mem.City != "" {
		if err := m.graph.AddLocation(ctx, &kg.DealerLocation{
			LocationID:     ulid.Make().String(),
			DealerID:       dealerID,
			IsPrimary:      true,
			AddressLine1:   ptrIfNotEmpty(mem.Street),
			PostalCode:     ptrIfNotEmpty(mem.Zip),
			City:           ptrIfNotEmpty(mem.City),
			CountryCode:    country,
			Phone:          ptrIfNotEmpty(mem.Phone),
			SourceFamilies: familyID,
		}); err != nil {
			m.log.Warn("mobilians: add location error", "name", mem.Name, "err", err)
		}
	}

	if mem.Website != "" {
		if dom := extractDomain(mem.Website); dom != "" {
			if err := m.graph.UpsertWebPresence(ctx, &kg.DealerWebPresence{
				WebID:                ulid.Make().String(),
				DealerID:             dealerID,
				Domain:               dom,
				URLRoot:              mem.Website,
				DiscoveredByFamilies: familyID,
			}); err != nil {
				m.log.Warn("mobilians: upsert web presence error", "domain", dom, "err", err)
			}
		}
	}

	if err := m.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
	}); err != nil {
		m.log.Warn("mobilians: record discovery error", "name", mem.Name, "err", err)
	}

	return isNew, nil
}

// ── Helpers ───────────────────────────────────────────────────────────────────

var frenchPhoneRe = regexp.MustCompile(`^0[0-9\s\.\-]{8,14}$`)
var frenchZipRe = regexp.MustCompile(`\b([0-9]{5})\b`)

func isFrenchPhone(s string) bool {
	s = strings.TrimSpace(s)
	return frenchPhoneRe.MatchString(s)
}

func containsFrenchPostalCode(s string) bool {
	return frenchZipRe.MatchString(s)
}

// extractZipCity splits "12345 Paris" or "12345, Paris Cedex" into zip+city.
func extractZipCity(addr string) (zip, city string) {
	m := frenchZipRe.FindStringIndex(addr)
	if m == nil {
		return "", ""
	}
	zip = addr[m[0]:m[1]]
	after := strings.TrimSpace(addr[m[1]:])
	after = strings.TrimPrefix(after, ",")
	after = strings.TrimSpace(after)
	city = after
	return zip, city
}

func extractDomain(rawURL string) string {
	if !strings.Contains(rawURL, "://") {
		rawURL = "https://" + rawURL
	}
	idx := strings.Index(rawURL, "://")
	if idx < 0 {
		return ""
	}
	rest := rawURL[idx+3:]
	rest = strings.TrimPrefix(rest, "www.")
	if slash := strings.Index(rest, "/"); slash > 0 {
		rest = rest[:slash]
	}
	return rest
}

func ptrIfNotEmpty(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}
