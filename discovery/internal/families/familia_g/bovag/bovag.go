// Package bovag implements sub-technique G.NL.1 — BOVAG member directory (Netherlands).
//
// BOVAG (Nederlandse Bond voor de Automobielbranche) publishes ~650 member pages at:
//
//	https://www.bovag.nl/leden/{slug}
//
// Discovery approach (two-phase):
//
//  1. Parse https://www.bovag.nl/sitemap.xml — filter all URLs matching /leden/ path.
//  2. For each member page: GET the Next.js SSG page, extract the embedded
//     <script id="__NEXT_DATA__"> JSON payload, unmarshal the member record from
//     props.pageProps.page.{name,memberId,slug,phoneNumber,website,address}.
//
// robots.txt verified 2026-04-15: only /studio is Disallowed. /leden/ is fully open.
//
// Member data extracted from __NEXT_DATA__:
//   - name            → canonical dealer name
//   - memberId        → BOVAG member number (e.g. "02833100")
//   - slug            → URL slug (fallback identifier)
//   - address.street  → street name
//   - address.housenumber → house number (int or string in JSON)
//   - address.postalCode  → Dutch postal code (e.g. "1033 SC")
//   - address.city    → city
//   - phoneNumber     → phone (optional)
//   - website         → URL (optional)
//   - kvkNumber       → KvK registration number (cross-ref to Family A)
//
// Rate limiting: 1 req / 3 s (sitemap + member pages share the same limiter).
// Identifier type: MEMBER_BOVAG with value = memberId (fallback: slug).
// ConfidenceContributed: 0.20 (BaseWeights["G"]).
package bovag

import (
	"context"
	"encoding/json"
	"encoding/xml"
	"fmt"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	defaultBaseURL     = "https://www.bovag.nl"
	defaultSitemapPath = "/sitemap.xml"
	defaultReqInterval = 3 * time.Second
	cardexUA           = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
	familyID           = "G"
	subTechID          = "G.NL.1"
	subTechName        = "BOVAG member directory"
	country            = "NL"
)

// BOVAG executes the G.NL.1 sub-technique crawl.
type BOVAG struct {
	graph       kg.KnowledgeGraph
	client      *http.Client
	baseURL     string
	reqInterval time.Duration
	log         *slog.Logger
}

// New returns a BOVAG executor with the production endpoint.
func New(graph kg.KnowledgeGraph) *BOVAG {
	return NewWithBaseURL(graph, defaultBaseURL, defaultReqInterval)
}

// NewWithBaseURL returns a BOVAG executor with a custom base URL and interval
// (use interval=0 in tests).
func NewWithBaseURL(graph kg.KnowledgeGraph, baseURL string, reqInterval time.Duration) *BOVAG {
	return &BOVAG{
		graph:       graph,
		client:      &http.Client{Timeout: 30 * time.Second},
		baseURL:     baseURL,
		reqInterval: reqInterval,
		log:         slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (b *BOVAG) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (b *BOVAG) Name() string { return subTechName }

// memberRecord mirrors the relevant fields from __NEXT_DATA__ props.pageProps.page.
type memberRecord struct {
	Name        string `json:"name"`
	MemberID    string `json:"memberId"`
	Slug        string `json:"slug"`
	PhoneNumber string `json:"phoneNumber"`
	Email       string `json:"email"`
	Website     string `json:"website"`
	KvKNumber   string `json:"kvkNumber"`
	Address     struct {
		Street      string          `json:"street"`
		HouseNumber json.RawMessage `json:"housenumber"` // int or string in JSON
		PostalCode  string          `json:"postalCode"`
		City        string          `json:"city"`
	} `json:"address"`
}

// streetFull concatenates street + house number.
func (r memberRecord) streetFull() string {
	raw := strings.TrimSpace(strings.Trim(string(r.Address.HouseNumber), `"`))
	if raw == "" || raw == "null" || raw == "0" {
		return r.Address.Street
	}
	// raw may be an integer (e.g. 16) or a string (e.g. "16a")
	return fmt.Sprintf("%s %s", r.Address.Street, raw)
}

// identifier returns the primary identifier value: memberId if set, else slug.
func (r memberRecord) identifier() string {
	if r.MemberID != "" {
		return r.MemberID
	}
	return r.Slug
}

// nextData is the minimal wrapper around the Next.js __NEXT_DATA__ script payload.
type nextData struct {
	Props struct {
		PageProps struct {
			Page memberRecord `json:"page"`
		} `json:"pageProps"`
	} `json:"props"`
}

// Run fetches the BOVAG sitemap, discovers all /leden/ member URLs, and upserts
// each member into the KG.
func (b *BOVAG) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}

	memberURLs, err := b.fetchSitemap(ctx)
	if err != nil {
		result.Errors++
		result.Duration = time.Since(start)
		return result, fmt.Errorf("bovag: sitemap: %w", err)
	}

	b.log.Info("bovag: sitemap parsed", "member_urls", len(memberURLs))

	for _, memberURL := range memberURLs {
		if ctx.Err() != nil {
			break
		}

		if b.reqInterval > 0 {
			select {
			case <-ctx.Done():
				goto done
			case <-time.After(b.reqInterval):
			}
		}

		rec, err := b.fetchMember(ctx, memberURL)
		if err != nil {
			b.log.Warn("bovag: member fetch error", "url", memberURL, "err", err)
			result.Errors++
			continue
		}
		if rec == nil || rec.Name == "" {
			b.log.Debug("bovag: empty member record", "url", memberURL)
			continue
		}

		upserted, err := b.upsert(ctx, rec)
		if err != nil {
			b.log.Warn("bovag: upsert error", "name", rec.Name, "err", err)
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

done:
	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, country).Observe(result.Duration.Seconds())
	b.log.Info("bovag: done",
		"discovered", result.Discovered,
		"confirmed", result.Confirmed,
		"errors", result.Errors,
	)
	return result, nil
}

// HealthCheck verifies the BOVAG site is reachable.
func (b *BOVAG) HealthCheck(ctx context.Context) error {
	reqURL := b.baseURL + defaultSitemapPath
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", cardexUA)
	resp, err := b.client.Do(req)
	if err != nil {
		return fmt.Errorf("bovag health: %w", err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("bovag health: HTTP %d", resp.StatusCode)
	}
	return nil
}

// ── Sitemap ──────────────────────────────────────────────────────────────────

// sitemapURLSet is the XML root element.
type sitemapURLSet struct {
	XMLName xml.Name      `xml:"urlset"`
	URLs    []sitemapEntry `xml:"url"`
}

type sitemapEntry struct {
	Loc string `xml:"loc"`
}

// fetchSitemap fetches the BOVAG sitemap and returns all /leden/ URLs.
func (b *BOVAG) fetchSitemap(ctx context.Context) ([]string, error) {
	reqURL := b.baseURL + defaultSitemapPath
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return nil, fmt.Errorf("bovag sitemap: build req: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "application/xml, text/xml")

	resp, err := b.client.Do(req)
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return nil, fmt.Errorf("bovag sitemap: http: %w", err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("bovag sitemap: HTTP %d", resp.StatusCode)
	}

	var urlset sitemapURLSet
	if err := xml.NewDecoder(resp.Body).Decode(&urlset); err != nil {
		return nil, fmt.Errorf("bovag sitemap: parse XML: %w", err)
	}

	var ledenURLs []string
	for _, entry := range urlset.URLs {
		if strings.Contains(entry.Loc, "/leden/") {
			ledenURLs = append(ledenURLs, entry.Loc)
		}
	}
	return ledenURLs, nil
}

// ── Member page ───────────────────────────────────────────────────────────────

// fetchMember fetches a BOVAG /leden/ page and extracts member data from
// the embedded __NEXT_DATA__ JSON.
func (b *BOVAG) fetchMember(ctx context.Context, memberURL string) (*memberRecord, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, memberURL, nil)
	if err != nil {
		return nil, fmt.Errorf("bovag member: build req: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "text/html,application/xhtml+xml")
	req.Header.Set("Accept-Language", "nl-NL,nl;q=0.9")

	resp, err := b.client.Do(req)
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return nil, fmt.Errorf("bovag member: http: %w", err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	if resp.StatusCode == http.StatusNotFound {
		return nil, nil // member page removed; skip gracefully
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("bovag member: HTTP %d at %s", resp.StatusCode, memberURL)
	}

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("bovag member: parse HTML: %w", err)
	}

	return parseMemberPage(doc)
}

// parseMemberPage extracts the memberRecord from the __NEXT_DATA__ script tag.
func parseMemberPage(doc *goquery.Document) (*memberRecord, error) {
	scriptContent := doc.Find(`script#__NEXT_DATA__`).Text()
	if scriptContent == "" {
		return nil, fmt.Errorf("bovag: __NEXT_DATA__ script not found")
	}

	var nd nextData
	if err := json.Unmarshal([]byte(scriptContent), &nd); err != nil {
		return nil, fmt.Errorf("bovag: unmarshal __NEXT_DATA__: %w", err)
	}

	rec := &nd.Props.PageProps.Page
	if rec.Name == "" {
		return nil, nil // not a member page (e.g. 404 placeholder)
	}
	return rec, nil
}

// ── KG upsert ─────────────────────────────────────────────────────────────────

// upsert writes a memberRecord to the KG. Returns true when a new entity was
// created, false when an existing one was re-confirmed.
func (b *BOVAG) upsert(ctx context.Context, rec *memberRecord) (bool, error) {
	now := time.Now().UTC()
	idValue := rec.identifier()

	existing, err := b.graph.FindDealerByIdentifier(ctx, kg.IdentifierMemberBOVAG, idValue)
	if err != nil {
		return false, fmt.Errorf("bovag.upsert find: %w", err)
	}

	isNew := existing == ""
	dealerID := existing
	if isNew {
		dealerID = ulid.Make().String()
	}

	entity := &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     rec.Name,
		NormalizedName:    strings.ToLower(rec.Name),
		CountryCode:       country,
		Status:            kg.StatusUnverified,
		ConfidenceScore:   kg.BaseWeights[familyID],
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}
	if err := b.graph.UpsertDealer(ctx, entity); err != nil {
		return false, fmt.Errorf("bovag.upsert dealer: %w", err)
	}

	if isNew {
		if err := b.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
			IdentifierID:    ulid.Make().String(),
			DealerID:        dealerID,
			IdentifierType:  kg.IdentifierMemberBOVAG,
			IdentifierValue: idValue,
		}); err != nil {
			return false, fmt.Errorf("bovag.upsert identifier: %w", err)
		}

		// Cross-reference KvK if available (links to Family A).
		if rec.KvKNumber != "" {
			if err := b.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
				IdentifierID:    ulid.Make().String(),
				DealerID:        dealerID,
				IdentifierType:  kg.IdentifierKvK,
				IdentifierValue: rec.KvKNumber,
			}); err != nil {
				b.log.Warn("bovag: add KvK identifier error", "dealer", rec.Name, "err", err)
			}
		}
	}

	// Location (address + optional phone).
	street := rec.streetFull()
	if street != "" || rec.Address.PostalCode != "" || rec.Address.City != "" {
		if err := b.graph.AddLocation(ctx, &kg.DealerLocation{
			LocationID:     ulid.Make().String(),
			DealerID:       dealerID,
			IsPrimary:      true,
			AddressLine1:   ptrIfNotEmpty(street),
			PostalCode:     ptrIfNotEmpty(rec.Address.PostalCode),
			City:           ptrIfNotEmpty(rec.Address.City),
			CountryCode:    country,
			Phone:          ptrIfNotEmpty(rec.PhoneNumber),
			SourceFamilies: familyID,
		}); err != nil {
			b.log.Warn("bovag: add location error", "dealer", rec.Name, "err", err)
		}
	}

	// Web presence.
	if rec.Website != "" {
		domain := extractDomain(rec.Website)
		if domain != "" {
			wp := &kg.DealerWebPresence{
				WebID:                ulid.Make().String(),
				DealerID:             dealerID,
				Domain:               domain,
				URLRoot:              rec.Website,
				DiscoveredByFamilies: familyID,
			}
			if err := b.graph.UpsertWebPresence(ctx, wp); err != nil {
				b.log.Warn("bovag: upsert web presence error", "domain", domain, "err", err)
			}
		}
	}

	// Audit trail.
	if err := b.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
	}); err != nil {
		b.log.Warn("bovag: record discovery error", "dealer", rec.Name, "err", err)
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
	// Normalise: add scheme if missing.
	if !strings.HasPrefix(rawURL, "http://") && !strings.HasPrefix(rawURL, "https://") {
		rawURL = "https://" + rawURL
	}
	// Simple extraction: find host between // and next /
	after := strings.SplitN(rawURL, "//", 2)
	if len(after) < 2 {
		return ""
	}
	host := strings.SplitN(after[1], "/", 2)[0]
	host = strings.TrimPrefix(host, "www.")
	return host
}

// houseNumberString converts the raw JSON house number (int or quoted string) to
// a plain string, stripping surrounding quotes. Exported for tests.
func HouseNumberString(raw json.RawMessage) string {
	if len(raw) == 0 {
		return ""
	}
	s := strings.TrimSpace(string(raw))
	// Quoted string
	if strings.HasPrefix(s, `"`) {
		var v string
		if err := json.Unmarshal(raw, &v); err == nil {
			return v
		}
	}
	// Numeric
	var n int
	if err := json.Unmarshal(raw, &n); err == nil {
		if n == 0 {
			return ""
		}
		return strconv.Itoa(n)
	}
	return ""
}
