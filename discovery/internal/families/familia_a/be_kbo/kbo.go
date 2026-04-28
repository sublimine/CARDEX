// Package be_kbo implements sub-technique A.BE.1 — KBO/BCE Open Data.
//
// Coverage: Belgian Crossroads Bank for Enterprises (Kruispuntbank van
// Ondernemingen / Banque-Carrefour des Entreprises) — complete national
// enterprise register with NACE-BEL codes, released monthly as a ~3 GB zip
// under an open data licence.
//
// Strategy:
//  1. Authenticate to https://kbopub.economie.fgov.be/kbo-open-data/login
//     using KBO_USER + KBO_PASS environment variables.
//     Parses the HTML login form to extract the action URL and any CSRF token,
//     then POSTs the credentials. Follows redirects with a cookie jar.
//  2. Discovers the most recent KboOpenData_YYYY_MM_Full.zip download link
//     from the authenticated download page.
//  3. Downloads the zip to a temp directory (streaming, not in RAM).
//  4. Streams each of the 6 relevant CSVs from the zip:
//     enterprise.csv, activity.csv, denomination.csv, address.csv.
//     All delimited by '|' (pipe), UTF-8, double-quote quoting.
//  5. Builds a join in memory via map[EnterpriseNumber] (string → struct).
//     Filters by NACE-BEL codes 45111, 45112, 45113, 45190, 45200.
//  6. Upserts each matching enterprise as DealerEntity with identifier KBO_BCE.
//  7. Logs progress every 10 000 enterprises. Cleans up temp dir on exit.
//
// Config: KBO_USER, KBO_PASS (required). If absent: Run returns a descriptive
//         error pointing to kbopub.economie.fgov.be/kbo-open-data/login.
package be_kbo

import (
	"archive/zip"
	"context"
	"encoding/csv"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"golang.org/x/net/html"

	"github.com/oklog/ulid/v2"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	loginURL     = "https://kbopub.economie.fgov.be/kbo-open-data/login"
	downloadPage = "https://kbopub.economie.fgov.be/kbo-open-data/download"
	cardexUA     = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
	subTechID    = "A.BE.1"
	subTechName  = "KBO/BCE Open Data"
	familyID     = "A"
	countryBE    = "BE"
	logEvery     = 10_000
)

// naceTargets are the NACE-BEL codes for automotive dealers.
var naceTargets = map[string]bool{
	"45111": true,
	"45112": true,
	"45113": true,
	"45190": true,
	"45200": true,
}

// KBO implements runner.SubTechnique for A.BE.1.
type KBO struct {
	graph    kg.KnowledgeGraph
	username string
	password string
	client   *http.Client
	log      *slog.Logger

	// loginURLOverride and downloadPageOverride allow injection of test servers.
	loginURLOverride    string
	downloadPageOverride string
}

// New creates a KBO sub-technique executor.
func New(graph kg.KnowledgeGraph, username, password string) *KBO {
	return NewWithOverrides(graph, username, password, "", "")
}

// NewWithOverrides creates a KBO executor with custom server URLs (for tests).
func NewWithOverrides(graph kg.KnowledgeGraph, username, password, loginOverride, dlOverride string) *KBO {
	jar, _ := cookiejar.New(nil)
	return &KBO{
		graph:               graph,
		username:            username,
		password:            password,
		loginURLOverride:    loginOverride,
		downloadPageOverride: dlOverride,
		client: &http.Client{
			Timeout: 0, // no timeout for the large download
			Jar:     jar,
			CheckRedirect: func(req *http.Request, via []*http.Request) error {
				req.Header.Set("User-Agent", cardexUA)
				if len(via) > 10 {
					return fmt.Errorf("kbo: too many redirects")
				}
				return nil
			},
		},
		log: slog.Default().With("sub_technique", subTechID),
	}
}

func (k *KBO) ID() string      { return subTechID }
func (k *KBO) Name() string    { return subTechName }
func (k *KBO) Country() string { return countryBE }

// Run authenticates, downloads the latest KBO full dataset, parses it, and
// upserts automotive dealers into the KG.
func (k *KBO) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{
		SubTechniqueID: subTechID,
		Country:        countryBE,
	}

	if k.username == "" || k.password == "" {
		return result, fmt.Errorf(
			"kbo.Run: KBO_USER and KBO_PASS must be set — register at %s", loginURL)
	}

	// 1. Authenticate.
	if err := k.login(ctx); err != nil {
		result.Errors++
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "auth_err").Inc()
		return result, fmt.Errorf("kbo.Run: login: %w", err)
	}
	metrics.SubTechniqueRequests.WithLabelValues(subTechID, "2xx").Inc()

	// 2. Discover download URL.
	zipURL, err := k.discoverZipURL(ctx)
	if err != nil {
		result.Errors++
		return result, fmt.Errorf("kbo.Run: discover zip: %w", err)
	}

	// 3. Download zip to temp directory.
	tmpDir, err := os.MkdirTemp("", "kbo_*")
	if err != nil {
		return result, fmt.Errorf("kbo.Run: temp dir: %w", err)
	}
	defer os.RemoveAll(tmpDir)

	zipPath := filepath.Join(tmpDir, "KboOpenData.zip")
	if err := k.downloadFile(ctx, zipURL, zipPath); err != nil {
		result.Errors++
		return result, fmt.Errorf("kbo.Run: download zip: %w", err)
	}
	metrics.SubTechniqueRequests.WithLabelValues(subTechID, "2xx").Inc()

	// 4-6. Parse CSVs and upsert.
	if err := k.parseAndUpsert(ctx, zipPath, result); err != nil {
		return result, err
	}

	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, countryBE).Observe(result.Duration.Seconds())
	k.log.Info("kbo run complete",
		"discovered", result.Discovered,
		"errors", result.Errors,
		"duration", result.Duration,
	)
	return result, nil
}

// ── Authentication ─────────────────────────────────────────────────────────

// login fetches the login page, discovers form fields, and POSTs credentials.
func (k *KBO) login(ctx context.Context) error {
	target := loginURL
	if k.loginURLOverride != "" {
		target = k.loginURLOverride
	}

	// GET login page.
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, target, nil)
	req.Header.Set("User-Agent", cardexUA)
	resp, err := k.client.Do(req)
	if err != nil {
		return fmt.Errorf("kbo: get login page: %w", err)
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	resp.Body.Close()
	if err != nil {
		return fmt.Errorf("kbo: read login page: %w", err)
	}

	// Parse form to extract action URL and hidden fields (CSRF token etc.).
	formAction, fields, err := parseLoginForm(string(body), target)
	if err != nil {
		return fmt.Errorf("kbo: parse login form: %w", err)
	}

	// Fill credentials.
	fields = fillCredentials(fields, k.username, k.password)

	// POST credentials.
	form := url.Values{}
	for k, v := range fields {
		form.Set(k, v)
	}
	req2, _ := http.NewRequestWithContext(ctx, http.MethodPost,
		formAction, strings.NewReader(form.Encode()))
	req2.Header.Set("User-Agent", cardexUA)
	req2.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req2.Header.Set("Referer", target)

	resp2, err := k.client.Do(req2)
	if err != nil {
		return fmt.Errorf("kbo: post credentials: %w", err)
	}
	resp2.Body.Close()

	// A successful login results in a redirect to an authenticated page.
	// Check we landed somewhere other than the login page.
	if strings.Contains(resp2.Request.URL.String(), "login") {
		return fmt.Errorf("kbo: login failed — still on login page after POST (wrong credentials?)")
	}
	return nil
}

// discoverZipURL fetches the download page and finds the most recent
// KboOpenData_..._Full.zip download link.
func (k *KBO) discoverZipURL(ctx context.Context) (string, error) {
	target := downloadPage
	if k.downloadPageOverride != "" {
		target = k.downloadPageOverride
	}

	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, target, nil)
	req.Header.Set("User-Agent", cardexUA)
	resp, err := k.client.Do(req)
	if err != nil {
		return "", fmt.Errorf("kbo: get download page: %w", err)
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	resp.Body.Close()
	if err != nil {
		return "", fmt.Errorf("kbo: read download page: %w", err)
	}

	zipURL := extractZipLink(string(body), target)
	if zipURL == "" {
		return "", fmt.Errorf("kbo: no KboOpenData Full zip link found on download page")
	}
	k.log.Info("kbo: found zip", "url", zipURL)
	return zipURL, nil
}

// downloadFile streams the resource at url to a local file.
func (k *KBO) downloadFile(ctx context.Context, srcURL, destPath string) error {
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, srcURL, nil)
	req.Header.Set("User-Agent", cardexUA)

	resp, err := k.client.Do(req)
	if err != nil {
		return fmt.Errorf("kbo: download %s: %w", srcURL, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("kbo: download HTTP %d", resp.StatusCode)
	}

	f, err := os.Create(destPath)
	if err != nil {
		return err
	}
	defer f.Close()

	if _, err := io.Copy(f, resp.Body); err != nil {
		return fmt.Errorf("kbo: write zip: %w", err)
	}
	return nil
}

// ── CSV parsing ────────────────────────────────────────────────────────────

// kboRecord collects joined data for one enterprise.
type kboRecord struct {
	EnterpriseNumber string
	Status           string
	StartDate        string
	Denomination     string
	Street           string
	HouseNumber      string
	ZipCode          string
	Municipality     string
	NaceCodes        []string
}

// parseAndUpsert opens the zip, parses the 4 relevant CSVs in streaming
// fashion, and upserts matching enterprises.
func (k *KBO) parseAndUpsert(ctx context.Context, zipPath string, result *runner.SubTechniqueResult) error {
	fi, err := os.Stat(zipPath)
	if err != nil {
		return fmt.Errorf("kbo: stat zip: %w", err)
	}

	f, err := os.Open(zipPath)
	if err != nil {
		return fmt.Errorf("kbo: open zip: %w", err)
	}
	defer f.Close()

	zr, err := zip.NewReader(f, fi.Size())
	if err != nil {
		return fmt.Errorf("kbo: open zip reader: %w", err)
	}

	// Pass 1: activity.csv → set of enterprise numbers with target NACE codes.
	naceMatches := make(map[string][]string) // enterprise → NACE codes
	if err := k.parseActivityCSV(ctx, zr, naceMatches); err != nil {
		return fmt.Errorf("kbo: parse activity.csv: %w", err)
	}
	if len(naceMatches) == 0 {
		k.log.Warn("kbo: no NACE target matches in activity.csv — check NACE codes or zip structure")
		return nil
	}
	k.log.Info("kbo: NACE matches found", "count", len(naceMatches))

	// Pass 2: build records for matched enterprises.
	records := make(map[string]*kboRecord, len(naceMatches))
	for num, codes := range naceMatches {
		records[num] = &kboRecord{
			EnterpriseNumber: num,
			NaceCodes:        codes,
		}
	}

	k.parseDenominationCSV(ctx, zr, records)
	k.parseAddressCSV(ctx, zr, records)
	k.parseEnterpriseCSV(ctx, zr, records)

	// Pass 3: upsert.
	processed := 0
	for _, rec := range records {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if err := k.upsertRecord(ctx, rec); err != nil {
			result.Errors++
			continue
		}
		result.Discovered++
		processed++
		metrics.DealersTotal.WithLabelValues(familyID, countryBE).Inc()
		if processed%logEvery == 0 {
			k.log.Info("kbo: upsert progress", "processed", processed)
		}
	}
	return nil
}

// findCSVFile locates a zip entry by filename (case-insensitive suffix match).
func findCSVFile(zr *zip.Reader, name string) *zip.File {
	lower := strings.ToLower(name)
	for _, f := range zr.File {
		if strings.ToLower(filepath.Base(f.Name)) == lower {
			return f
		}
	}
	return nil
}

// parseActivityCSV reads activity.csv and populates naceMatches.
// KBO activity.csv columns: EntityNumber|ActivityGroup|NaceVersion|NaceCode|Classification
func (k *KBO) parseActivityCSV(ctx context.Context, zr *zip.Reader, naceMatches map[string][]string) error {
	f := findCSVFile(zr, "activity.csv")
	if f == nil {
		return fmt.Errorf("kbo: activity.csv not found in zip")
	}
	rc, err := f.Open()
	if err != nil {
		return err
	}
	defer rc.Close()

	r := csv.NewReader(rc)
	r.Comma = '|'
	r.LazyQuotes = true

	header, err := r.Read()
	if err != nil {
		return err
	}
	col := makeColMap(header)
	entityCol := col["EntityNumber"]
	naceCol := col["NaceCode"]
	if entityCol < 0 || naceCol < 0 {
		return fmt.Errorf("kbo: activity.csv missing EntityNumber or NaceCode columns")
	}

	for {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		rec, err := r.Read()
		if err == io.EOF {
			break
		}
		if err != nil || entityCol >= len(rec) || naceCol >= len(rec) {
			continue
		}
		nace := strings.TrimSpace(rec[naceCol])
		if !naceTargets[nace] {
			continue
		}
		entity := strings.TrimSpace(rec[entityCol])
		naceMatches[entity] = append(naceMatches[entity], nace)
	}
	return nil
}

// parseDenominationCSV reads denomination.csv and adds names to records.
// KBO denomination.csv columns: EntityNumber|Language|TypeOfDenomination|Denomination
func (k *KBO) parseDenominationCSV(ctx context.Context, zr *zip.Reader, records map[string]*kboRecord) {
	f := findCSVFile(zr, "denomination.csv")
	if f == nil {
		return
	}
	rc, _ := f.Open()
	defer rc.Close()

	r := csv.NewReader(rc)
	r.Comma = '|'
	r.LazyQuotes = true

	header, _ := r.Read()
	col := makeColMap(header)
	entityCol := col["EntityNumber"]
	denomCol := col["Denomination"]
	typeCol := col["TypeOfDenomination"]
	langCol := col["Language"]
	if entityCol < 0 || denomCol < 0 {
		return
	}

	for {
		rec, err := r.Read()
		if err == io.EOF {
			break
		}
		if err != nil || entityCol >= len(rec) || denomCol >= len(rec) {
			continue
		}
		entity := strings.TrimSpace(rec[entityCol])
		entry, ok := records[entity]
		if !ok {
			continue
		}
		if entry.Denomination != "" {
			continue // already have a name
		}
		denomType := ""
		if typeCol >= 0 && typeCol < len(rec) {
			denomType = strings.TrimSpace(rec[typeCol])
		}
		lang := ""
		if langCol >= 0 && langCol < len(rec) {
			lang = strings.TrimSpace(rec[langCol])
		}
		// Prefer French (2) or Dutch (1) commercial name (type 001 or 003)
		if denomType == "001" || denomType == "003" || lang == "1" || lang == "2" {
			entry.Denomination = strings.TrimSpace(rec[denomCol])
		}
	}
}

// parseAddressCSV reads address.csv and adds addresses to records.
// KBO address.csv columns: EntityNumber|TypeOfAddress|CountryNL|ZipCode|MunicipalityNL|StreetNL|HouseNumber|Box|ExtraAddressInfo|DateStrikingOff
func (k *KBO) parseAddressCSV(ctx context.Context, zr *zip.Reader, records map[string]*kboRecord) {
	f := findCSVFile(zr, "address.csv")
	if f == nil {
		return
	}
	rc, _ := f.Open()
	defer rc.Close()

	r := csv.NewReader(rc)
	r.Comma = '|'
	r.LazyQuotes = true

	header, _ := r.Read()
	col := makeColMap(header)
	entityCol := col["EntityNumber"]
	zipCol := col["ZipCode"]
	munCol := col["MunicipalityNL"]
	streetCol := col["StreetNL"]
	houseCol := col["HouseNumber"]
	if entityCol < 0 {
		return
	}

	for {
		rec, err := r.Read()
		if err == io.EOF {
			break
		}
		if err != nil || entityCol >= len(rec) {
			continue
		}
		entity := strings.TrimSpace(rec[entityCol])
		entry, ok := records[entity]
		if !ok || entry.ZipCode != "" {
			continue
		}
		if zipCol >= 0 && zipCol < len(rec) {
			entry.ZipCode = strings.TrimSpace(rec[zipCol])
		}
		if munCol >= 0 && munCol < len(rec) {
			entry.Municipality = strings.TrimSpace(rec[munCol])
		}
		if streetCol >= 0 && streetCol < len(rec) {
			entry.Street = strings.TrimSpace(rec[streetCol])
		}
		if houseCol >= 0 && houseCol < len(rec) {
			entry.HouseNumber = strings.TrimSpace(rec[houseCol])
		}
	}
}

// parseEnterpriseCSV reads enterprise.csv and adds status/start date.
// KBO enterprise.csv columns: EnterpriseNumber|Status|JuridicalSituation|TypeOfEnterprise|JuridicalForm|JuridicalFormCAC|StartDate
func (k *KBO) parseEnterpriseCSV(ctx context.Context, zr *zip.Reader, records map[string]*kboRecord) {
	f := findCSVFile(zr, "enterprise.csv")
	if f == nil {
		return
	}
	rc, _ := f.Open()
	defer rc.Close()

	r := csv.NewReader(rc)
	r.Comma = '|'
	r.LazyQuotes = true

	header, _ := r.Read()
	col := makeColMap(header)
	numCol := col["EnterpriseNumber"]
	statusCol := col["Status"]
	startCol := col["StartDate"]
	if numCol < 0 {
		return
	}

	for {
		rec, err := r.Read()
		if err == io.EOF {
			break
		}
		if err != nil || numCol >= len(rec) {
			continue
		}
		num := strings.TrimSpace(rec[numCol])
		entry, ok := records[num]
		if !ok {
			continue
		}
		if statusCol >= 0 && statusCol < len(rec) {
			entry.Status = strings.TrimSpace(rec[statusCol])
		}
		if startCol >= 0 && startCol < len(rec) {
			entry.StartDate = strings.TrimSpace(rec[startCol])
		}
	}
}

// upsertRecord writes one KBO enterprise into the KG.
func (k *KBO) upsertRecord(ctx context.Context, rec *kboRecord) error {
	if rec.EnterpriseNumber == "" {
		return nil
	}
	now := time.Now().UTC()

	existing, err := k.graph.FindDealerByIdentifier(ctx, kg.IdentifierKBO, rec.EnterpriseNumber)
	if err != nil {
		return err
	}
	dealerID := ulid.Make().String()
	if existing != "" {
		dealerID = existing
	}

	name := rec.Denomination
	if name == "" {
		name = rec.EnterpriseNumber // fallback if no denomination
	}

	status := kboStatus(rec.Status)
	entity := &kg.DealerEntity{
		DealerID:          dealerID,
		CanonicalName:     name,
		NormalizedName:    strings.ToLower(name),
		CountryCode:       countryBE,
		Status:            status,
		ConfidenceScore:   kg.ComputeConfidence([]string{familyID}),
		FirstDiscoveredAt: now,
		LastConfirmedAt:   now,
	}
	if err := k.graph.UpsertDealer(ctx, entity); err != nil {
		return err
	}

	if err := k.graph.AddIdentifier(ctx, &kg.DealerIdentifier{
		IdentifierID:    ulid.Make().String(),
		DealerID:        dealerID,
		IdentifierType:  kg.IdentifierKBO,
		IdentifierValue: rec.EnterpriseNumber,
		SourceFamily:    familyID,
		ValidStatus:     "VALID",
	}); err != nil {
		return err
	}

	if rec.ZipCode != "" || rec.Municipality != "" {
		loc := &kg.DealerLocation{
			LocationID:     ulid.Make().String(),
			DealerID:       dealerID,
			IsPrimary:      true,
			CountryCode:    countryBE,
			SourceFamilies: familyID,
		}
		if rec.ZipCode != "" {
			loc.PostalCode = &rec.ZipCode
		}
		if rec.Municipality != "" {
			loc.City = &rec.Municipality
		}
		if rec.Street != "" {
			line := rec.Street
			if rec.HouseNumber != "" {
				line += " " + rec.HouseNumber
			}
			loc.AddressLine1 = &line
		}
		if err := k.graph.AddLocation(ctx, loc); err != nil {
			return err
		}
	}

	entRef := rec.EnterpriseNumber
	return k.graph.RecordDiscovery(ctx, &kg.DiscoveryRecord{
		RecordID:              ulid.Make().String(),
		DealerID:              dealerID,
		Family:                familyID,
		SubTechnique:          subTechID,
		SourceRecordID:        &entRef,
		ConfidenceContributed: kg.BaseWeights[familyID],
		DiscoveredAt:          now,
	})
}

// ── HTML parsing helpers ───────────────────────────────────────────────────

// parseLoginForm extracts the form action URL and all input fields from an HTML login form.
func parseLoginForm(body, pageURL string) (action string, fields map[string]string, err error) {
	fields = make(map[string]string)

	doc, err := html.Parse(strings.NewReader(body))
	if err != nil {
		return "", nil, fmt.Errorf("parse HTML: %w", err)
	}

	var walk func(*html.Node)
	walk = func(n *html.Node) {
		if n.Type == html.ElementNode && n.Data == "form" {
			for _, attr := range n.Attr {
				if attr.Key == "action" {
					action = attr.Val
				}
			}
		}
		if n.Type == html.ElementNode && n.Data == "input" {
			var name, value, inputType string
			for _, attr := range n.Attr {
				switch attr.Key {
				case "name":
					name = attr.Val
				case "value":
					value = attr.Val
				case "type":
					inputType = attr.Val
				}
			}
			if name != "" && inputType != "submit" && inputType != "button" {
				fields[name] = value
			}
		}
		for c := n.FirstChild; c != nil; c = c.NextSibling {
			walk(c)
		}
	}
	walk(doc)

	if action == "" {
		action = pageURL // fall back to same page
	} else if !strings.HasPrefix(action, "http") {
		// Resolve relative action URL.
		base, _ := url.Parse(pageURL)
		rel, _ := url.Parse(action)
		action = base.ResolveReference(rel).String()
	}

	return action, fields, nil
}

// fillCredentials sets username/password in the form fields map by detecting
// common field name patterns.
func fillCredentials(fields map[string]string, username, password string) map[string]string {
	userPatterns := []string{"username", "j_username", "email", "user", "login", "userid"}
	passPatterns := []string{"password", "j_password", "passwd", "pass", "pwd"}

	for k := range fields {
		lower := strings.ToLower(k)
		for _, p := range userPatterns {
			if strings.Contains(lower, p) {
				fields[k] = username
				break
			}
		}
		for _, p := range passPatterns {
			if strings.Contains(lower, p) {
				fields[k] = password
				break
			}
		}
	}
	return fields
}

// extractZipLink finds the most recent KboOpenData Full.zip href in the HTML.
var zipLinkRe = regexp.MustCompile(`(?i)href="([^"]*KboOpenData[^"]*Full[^"]*\.zip)"`)

func extractZipLink(body, baseURL string) string {
	// Try regex first (fast path).
	matches := zipLinkRe.FindStringSubmatch(body)
	if len(matches) >= 2 {
		href := matches[1]
		if strings.HasPrefix(href, "http") {
			return href
		}
		base, _ := url.Parse(baseURL)
		rel, _ := url.Parse(href)
		return base.ResolveReference(rel).String()
	}

	// Fallback: parse HTML links containing "kboopen" and ".zip".
	doc, err := html.Parse(strings.NewReader(body))
	if err != nil {
		return ""
	}
	var found string
	var walk func(*html.Node)
	walk = func(n *html.Node) {
		if found != "" {
			return
		}
		if n.Type == html.ElementNode && n.Data == "a" {
			for _, attr := range n.Attr {
				if attr.Key == "href" &&
					strings.Contains(strings.ToLower(attr.Val), "kboopen") &&
					strings.HasSuffix(strings.ToLower(attr.Val), ".zip") {
					found = attr.Val
					return
				}
			}
		}
		for c := n.FirstChild; c != nil; c = c.NextSibling {
			walk(c)
		}
	}
	walk(doc)

	if found == "" {
		return ""
	}
	if strings.HasPrefix(found, "http") {
		return found
	}
	base, _ := url.Parse(baseURL)
	rel, _ := url.Parse(found)
	return base.ResolveReference(rel).String()
}

// ── Status mapping ─────────────────────────────────────────────────────────

func kboStatus(s string) kg.DealerStatus {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "active", "actief", "actif":
		return kg.StatusActive
	case "stopped", "gestopt", "arrêté":
		return kg.StatusClosed
	default:
		return kg.StatusUnverified
	}
}

// makeColMap builds a name→index map from a CSV header row (case-insensitive).
func makeColMap(header []string) map[string]int {
	m := make(map[string]int, len(header))
	for i, col := range header {
		m[strings.TrimSpace(col)] = i
		m[strings.ToLower(strings.TrimSpace(col))] = i
	}
	return m
}
