// Package autoscout24 implements sub-technique F.2 — AutoScout24 dealer directory (pan-EU).
//
// AutoScout24 is Europe's largest car marketplace. Its public dealer directory
// lists all professional dealers registered on the platform.
//
// robots.txt verification (2026-04-15):
//
//	DE: https://www.autoscout24.de — /haendler/ NOT blocked
//	FR: https://www.autoscout24.fr — /concessionnaires/ NOT blocked
//	NL: https://www.autoscout24.nl — /handelaar/ NOT blocked
//	BE: https://www.autoscout24.be — /handelaar/ NOT blocked (/garages/ blocked)
//	CH: https://www.autoscout24.ch — /haendler/ NOT blocked
//	ES: DEFERRED — robots.txt connection error; path status unknown
//
// Two-phase crawl:
//  1. Listing pages — browser.FetchHTML (Next.js SPA; requires JS execution).
//     Parse rendered HTML for dealer profile URL links.
//     Pagination: ?currentPage=N (starts at 1) until empty page.
//  2. Profile pages — standard HTTP GET (Next.js SSG; server-rendered HTML).
//     Extract data from <script id="__NEXT_DATA__"> JSON.
//     JSON path: props.pageProps.dealerInfoPage.{id,name,address,contact}
//
// Identifier type: AUTOSCOUT24_ID with value = dealer's AS24 account ID.
// ConfidenceContributed: 0.20 (BaseWeights["F"]).
package autoscout24

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"path"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/browser"
	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	defaultReqInterval = 3 * time.Second
	cardexUA           = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
	familyID           = "F"
	subTechID          = "F.2"
	subTechName        = "AutoScout24 dealer directory"
)

// countryConf holds the AutoScout24 settings per country.
type countryConf struct {
	// BaseURL is the country-specific AutoScout24 domain.
	BaseURL string
	// DirPath is the dealer directory path on that domain (with trailing slash).
	DirPath string
}

// countryConfigs maps ISO country code to AutoScout24 dealer-directory config.
// robots.txt verified for each entry; ES explicitly deferred (robots.txt error).
var countryConfigs = map[string]countryConf{
	"DE": {BaseURL: "https://www.autoscout24.de", DirPath: "/haendler/"},
	"FR": {BaseURL: "https://www.autoscout24.fr", DirPath: "/concessionnaires/"},
	"NL": {BaseURL: "https://www.autoscout24.nl", DirPath: "/handelaar/"},
	"BE": {BaseURL: "https://www.autoscout24.be", DirPath: "/handelaar/"},
	"CH": {BaseURL: "https://www.autoscout24.ch", DirPath: "/haendler/"},
}

// AutoScout24 executes the F.2 sub-technique crawl for a given country.
type AutoScout24 struct {
	graph       kg.KnowledgeGraph
	b           browser.Browser // for listing pages (SPA)
	client      *http.Client    // for profile pages (SSG)
	reqInterval time.Duration
	log         *slog.Logger
}

// New creates an AutoScout24 executor with production settings.
func New(graph kg.KnowledgeGraph, b browser.Browser) *AutoScout24 {
	return NewWithInterval(graph, b, defaultReqInterval)
}

// NewWithInterval creates an AutoScout24 executor with a custom request interval
// (use 0 in tests).
func NewWithInterval(graph kg.KnowledgeGraph, b browser.Browser, reqInterval time.Duration) *AutoScout24 {
	return &AutoScout24{
		graph:       graph,
		b:           b,
		client:      &http.Client{Timeout: 30 * time.Second},
		reqInterval: reqInterval,
		log:         slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (a *AutoScout24) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (a *AutoScout24) Name() string { return subTechName }

// Run crawls AutoScout24 for the given country and upserts all dealers found.
// Returns a nil error with deferred log when country is not configured (ES).
func (a *AutoScout24) Run(ctx context.Context, country string) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: country}

	ccfg, ok := countryConfigs[country]
	if !ok {
		a.log.Info("autoscout24: country not configured", "country", country,
			"reason", "robots.txt inaccessible or path blocked; see package doc")
		result.Duration = time.Since(start)
		return result, nil
	}

	if a.b == nil {
		a.log.Warn("autoscout24: browser not initialised — skipping F.2", "country", country)
		result.Duration = time.Since(start)
		return result, nil
	}

	a.log.Info("autoscout24: starting crawl", "country", country, "base", ccfg.BaseURL)

	seen := make(map[string]bool) // canonical profile URL → already enqueued

	for page := 1; ; page++ {
		if ctx.Err() != nil {
			break
		}

		listURL := fmt.Sprintf("%s%s?currentPage=%d", ccfg.BaseURL, ccfg.DirPath, page)
		links, err := a.fetchListingLinks(ctx, listURL, ccfg.DirPath)
		if err != nil {
			a.log.Warn("autoscout24: listing page error", "url", listURL, "err", err)
			result.Errors++
			break
		}
		if len(links) == 0 {
			break // end of pagination
		}

		newLinks := 0
		for _, link := range links {
			if seen[link] {
				continue
			}
			seen[link] = true
			newLinks++

			if a.reqInterval > 0 {
				select {
				case <-ctx.Done():
					goto done
				case <-time.After(a.reqInterval):
				}
			}

			rec, err := a.fetchDealerProfile(ctx, link)
			if err != nil {
				a.log.Warn("autoscout24: profile fetch error", "url", link, "err", err)
				result.Errors++
				continue
			}
			if rec == nil || rec.canonicalName() == "" {
				continue
			}

			upserted, err := a.upsert(ctx, rec, country)
			if err != nil {
				a.log.Warn("autoscout24: upsert error", "name", rec.canonicalName(), "err", err)
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

		if newLinks == 0 {
			break // all links on this page already seen → loop guard
		}
	}

done:
	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, country).Observe(result.Duration.Seconds())
	a.log.Info("autoscout24: done",
		"country", country,
		"discovered", result.Discovered,
		"confirmed", result.Confirmed,
		"errors", result.Errors,
	)
	return result, nil
}

// ── Listing page ──────────────────────────────────────────────────────────────

// fetchListingLinks renders a dealer-directory listing page via the browser
// (required for Next.js SPA) and returns absolute dealer-profile URLs.
func (a *AutoScout24) fetchListingLinks(ctx context.Context, listURL, dirPath string) ([]string, error) {
	res, err := a.b.FetchHTML(ctx, listURL, &browser.FetchOptions{
		WaitForNetworkIdle: true,
		Timeout:            25 * time.Second,
	})
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return nil, fmt.Errorf("autoscout24 listing FetchHTML: %w", err)
	}
	if res.StatusCode == http.StatusNotFound {
		return nil, nil
	}
	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", res.StatusCode/100)).Inc()

	return ParseListingLinks(res.HTML, res.FinalURL, dirPath), nil
}

// ParseListingLinks extracts absolute dealer-profile URLs from rendered listing HTML.
//
// Only links whose path starts with dirPath and whose final slug is not a known
// meta-path (suche, faq, contact, …) are returned. Exported for testing.
func ParseListingLinks(htmlContent, baseURL, dirPath string) []string {
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(htmlContent))
	if err != nil {
		return nil
	}

	dirPath = "/" + strings.Trim(dirPath, "/") + "/"
	base, _ := url.Parse(baseURL)

	seen := make(map[string]bool)
	var links []string

	doc.Find("a[href]").Each(func(_ int, s *goquery.Selection) {
		href, ok := s.Attr("href")
		if !ok || href == "" {
			return
		}
		ref, err := url.Parse(href)
		if err != nil {
			return
		}

		var abs *url.URL
		if base != nil {
			abs = base.ResolveReference(ref)
		} else {
			abs = ref
		}

		p := abs.Path
		if !strings.HasPrefix(p, dirPath) {
			return
		}
		slug := path.Base(strings.TrimRight(p, "/"))
		if slug == "" || slug == strings.Trim(dirPath, "/") || metaSlugs[strings.ToLower(slug)] {
			return
		}

		canonical := abs.Scheme + "://" + abs.Host + dirPath + slug + "/"
		if seen[canonical] {
			return
		}
		seen[canonical] = true
		links = append(links, canonical)
	})
	return links
}

// metaSlugs is the set of AutoScout24 path segments that are not dealer profiles.
var metaSlugs = map[string]bool{
	"suche": true, "search": true, "recherche": true,
	"hinzufuegen": true, "ajouter": true, "toevoegen": true,
	"faq": true, "hilfe": true, "aide": true, "hulp": true,
	"kontakt": true, "contact": true, "impressum": true,
	"datenschutz": true, "privacy": true,
}

// ── Profile page ──────────────────────────────────────────────────────────────

// fetchDealerProfile fetches a Next.js SSG dealer profile page and parses
// the embedded __NEXT_DATA__ JSON.
func (a *AutoScout24) fetchDealerProfile(ctx context.Context, profileURL string) (*DealerInfoPage, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, profileURL, nil)
	if err != nil {
		return nil, fmt.Errorf("autoscout24 profile build req: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "text/html,application/xhtml+xml")

	resp, err := a.client.Do(req)
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return nil, fmt.Errorf("autoscout24 profile http: %w", err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	if resp.StatusCode == http.StatusNotFound {
		return nil, nil
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("autoscout24 profile HTTP %d at %s", resp.StatusCode, profileURL)
	}

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("autoscout24 profile parse HTML: %w", err)
	}
	return ParseDealerProfile(doc)
}

// ParseDealerProfile extracts dealer data from the embedded __NEXT_DATA__ JSON
// on a Next.js SSG AutoScout24 dealer profile page. Exported for testing.
func ParseDealerProfile(doc *goquery.Document) (*DealerInfoPage, error) {
	scriptText := doc.Find(`script#__NEXT_DATA__`).Text()
	if scriptText == "" {
		return nil, fmt.Errorf("autoscout24: __NEXT_DATA__ not found")
	}

	var nd as24NextData
	if err := json.Unmarshal([]byte(scriptText), &nd); err != nil {
		return nil, fmt.Errorf("autoscout24: unmarshal __NEXT_DATA__: %w", err)
	}

	info := &nd.Props.PageProps.DealerInfoPage
	if info.canonicalName() == "" {
		return nil, nil
	}
	return info, nil
}

// ── __NEXT_DATA__ types ───────────────────────────────────────────────────────

// as24NextData is the root wrapper of AutoScout24's __NEXT_DATA__ JSON.
type as24NextData struct {
	Props struct {
		PageProps struct {
			DealerInfoPage DealerInfoPage `json:"dealerInfoPage"`
		} `json:"pageProps"`
	} `json:"props"`
}

// DealerInfoPage mirrors the dealerInfoPage object in __NEXT_DATA__ on
// AutoScout24 dealer profile pages.
//
// AutoScout24 uses slightly different field names across TLDs and versions;
// the struct covers the most common variants. The canonicalXxx() helpers
// return the first non-empty value found.
type DealerInfoPage struct {
	// ID field variants
	ID        string `json:"id"`
	AccountID string `json:"accountId"`
	DealerID  string `json:"dealerId"`

	// Name field variants
	Name        string `json:"name"`
	DealerName  string `json:"dealerName"`
	CompanyName string `json:"companyName"`

	Address struct {
		Street      string `json:"street"`
		Zip         string `json:"zip"`
		ZipCode     string `json:"zipCode"`
		City        string `json:"city"`
		Country     string `json:"country"`
		CountryCode string `json:"countryCode"`
	} `json:"address"`

	Contact struct {
		Phone   string `json:"phone"`
		Email   string `json:"email"`
		Website string `json:"website"`
		URL     string `json:"url"`
	} `json:"contact"`
}

func (d *DealerInfoPage) canonicalID() string {
	for _, v := range []string{d.ID, d.AccountID, d.DealerID} {
		if v != "" {
			return v
		}
	}
	return ""
}

func (d *DealerInfoPage) canonicalName() string {
	for _, v := range []string{d.Name, d.DealerName, d.CompanyName} {
		if v != "" {
			return v
		}
	}
	return ""
}

func (d *DealerInfoPage) zip() string {
	if d.Address.Zip != "" {
		return d.Address.Zip
	}
	return d.Address.ZipCode
}

func (d *DealerInfoPage) countryCode() string {
	if d.Address.CountryCode != "" {
		return d.Address.CountryCode
	}
	return d.Address.Country
}

func (d *DealerInfoPage) website() string {
	if d.Contact.Website != "" {
		return d.Contact.Website
	}
	return d.Contact.URL
}

// ── KG upsert ────────────────────────────────────────────────────────────────

func (a *AutoScout24) upsert(ctx context.Context, info *DealerInfoPage, country string) (bool, error) {
	now := time.Now().UTC()

	idValue := info.canonicalID()
	if idValue == "" {
		idValue = strings.ToLower(strings.ReplaceAll(info.canonicalName(), " ", "-"))
	}

	existing, err := a.graph.FindDealerByIdentifier(ctx, kg.IdentifierAutoScout24ID, idValue)
	if err != nil {
		return false, fmt.Errorf("autoscout24.upsert find: %w", err)
	}

	isNew := existing == ""
	dealerID := existing
	if isNew {
		dealerID = ulid.Make().String()
	}

	name := info.canonicalName()
	if err := a.graph.UpsertDealer(ctx, &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     name,
		NormalizedName:    strings.ToLower(name),
		CountryCode:       country,
		Status:            kg.StatusUnverified,
		ConfidenceScore:   kg.BaseWeights[familyID],
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}); err != nil {
		return false, fmt.Errorf("autoscout24.upsert dealer: %w", err)
	}

	if isNew {
		if err := a.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
			IdentifierID:    ulid.Make().String(),
			DealerID:        dealerID,
			IdentifierType:  kg.IdentifierAutoScout24ID,
			IdentifierValue: idValue,
		}); err != nil {
			return false, fmt.Errorf("autoscout24.upsert identifier: %w", err)
		}
	}

	cc := info.countryCode()
	if cc == "" {
		cc = country
	}
	street := strings.TrimSpace(info.Address.Street)
	if street != "" || info.zip() != "" || info.Address.City != "" {
		if err := a.graph.AddLocation(ctx, &kg.DealerLocation{
			LocationID:     ulid.Make().String(),
			DealerID:       dealerID,
			IsPrimary:      true,
			AddressLine1:   ptrIfNotEmpty(street),
			PostalCode:     ptrIfNotEmpty(info.zip()),
			City:           ptrIfNotEmpty(info.Address.City),
			CountryCode:    cc,
			Phone:          ptrIfNotEmpty(info.Contact.Phone),
			SourceFamilies: familyID,
		}); err != nil {
			a.log.Warn("autoscout24: add location error", "dealer", name, "err", err)
		}
	}

	if ws := info.website(); ws != "" {
		if dom := extractDomain(ws); dom != "" {
			if err := a.graph.UpsertWebPresence(ctx, &kg.DealerWebPresence{
				WebID:                ulid.Make().String(),
				DealerID:             dealerID,
				Domain:               dom,
				URLRoot:              ws,
				DiscoveredByFamilies: familyID,
			}); err != nil {
				a.log.Warn("autoscout24: upsert web presence error", "domain", dom, "err", err)
			}
		}
	}

	if err := a.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
	}); err != nil {
		a.log.Warn("autoscout24: record discovery error", "dealer", name, "err", err)
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
	if !strings.Contains(rawURL, "://") {
		rawURL = "https://" + rawURL
	}
	u, err := url.Parse(rawURL)
	if err != nil || u.Host == "" {
		return ""
	}
	return strings.TrimPrefix(u.Host, "www.")
}
