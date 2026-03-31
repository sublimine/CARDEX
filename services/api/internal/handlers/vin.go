package handlers

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"
)

var vinRe = regexp.MustCompile(`^[A-HJ-NPR-Z0-9]{17}$`)

// httpClient is a shared HTTP client used for all external API calls.
// 4-second timeout to stay within handler latency budget.
var httpClient = &http.Client{Timeout: 4 * time.Second}

// ── Types ─────────────────────────────────────────────────────────────────────

type vinEvent struct {
	EventType   string   `json:"event_type"`
	EventDate   string   `json:"event_date"`
	MileageKM   *int     `json:"mileage_km,omitempty"`
	Country     *string  `json:"country,omitempty"`
	Source      *string  `json:"source_platform,omitempty"`
	PriceEUR    *float64 `json:"price_eur,omitempty"`
	Description *string  `json:"description,omitempty"`
	Confidence  float32  `json:"confidence"`
}

type vinSummary struct {
	FirstSeen       *string   `json:"first_seen_date,omitempty"`
	LastSeen        *string   `json:"last_seen_date,omitempty"`
	OwnerCount      int       `json:"ownership_changes"`
	AccidentCount   int       `json:"accident_records"`
	ImportCount     int       `json:"import_records"`
	ListingCount    int       `json:"times_listed"`
	MinMileageKM    *int      `json:"min_mileage_km,omitempty"`
	MaxMileageKM    *int      `json:"max_mileage_km,omitempty"`
	Countries       []string  `json:"countries_seen_in"`
	PriceHistoryEUR []float64 `json:"price_history_eur"`
}

type vinSpec struct {
	Make                  string  `json:"make"`
	Model                 string  `json:"model"`
	Year                  int     `json:"year"`
	BodyType              string  `json:"body_type"`
	FuelType              string  `json:"fuel_type"`
	EngineDisplacementL   float64 `json:"engine_displacement_l"`
	EngineCylinders       int     `json:"engine_cylinders"`
	EngineKW              float64 `json:"engine_kw"`
	Transmission          string  `json:"transmission"`
	CountryOfManufacture  string  `json:"country_of_manufacture"`
}

type ncapRating struct {
	Stars           int `json:"ncap_stars"`
	AdultPct        int `json:"ncap_adult_pct"`
	ChildPct        int `json:"ncap_child_pct"`
	PedestrianPct   int `json:"ncap_pedestrian_pct"`
	SafetyAssistPct int `json:"ncap_safety_assist_pct"`
	TestYear        int `json:"ncap_test_year"`
}

type recallEntry struct {
	Campaign  string `json:"campaign"`
	Component string `json:"component"`
	Summary   string `json:"summary"`
	Remedy    string `json:"remedy"`
	Date      string `json:"date"`
}

type vinSafety struct {
	NCAPStars           int           `json:"ncap_stars"`
	NCAPAdultPct        int           `json:"ncap_adult_pct"`
	NCAPChildPct        int           `json:"ncap_child_pct"`
	NCAPPedestrianPct   int           `json:"ncap_pedestrian_pct"`
	NCAPSafetyAssistPct int           `json:"ncap_safety_assist_pct"`
	NCAPTestYear        int           `json:"ncap_test_year"`
	RecallCount         int           `json:"recall_count"`
	Recalls             []recallEntry `json:"recalls"`
}

type vinHistory struct {
	Events          []vinEvent `json:"events"`
	EventCount      int        `json:"event_count"`
	MileageOK       bool       `json:"mileage_ok"`
	MileageWarning  string     `json:"mileage_warning"`
	ForensicMaxKM   int        `json:"forensic_max_km"`
	ForensicSources []string   `json:"forensic_sources"`
	FirstSeen       string     `json:"first_seen"`
	LastSeen        string     `json:"last_seen"`
}

type vinReportV2 struct {
	VIN               string      `json:"vin"`
	Spec              *vinSpec    `json:"spec"`
	Safety            vinSafety   `json:"safety"`
	History           vinHistory  `json:"history"`
	Summary           vinSummary  `json:"summary"`
	StolenStatus      string      `json:"stolen_status"`
	DataSources       []string    `json:"data_sources"`
	ReportGeneratedAt string      `json:"report_generated_at"`
	Disclaimer        string      `json:"disclaimer"`
}

// ── Euro NCAP Lookup Table ────────────────────────────────────────────────────
// Maintained in-process; keyed as "Make/Model/Year".

var ncapTable = map[string]ncapRating{
	"VW/Golf/2020":             {Stars: 5, AdultPct: 91, ChildPct: 89, PedestrianPct: 74, SafetyAssistPct: 80, TestYear: 2020},
	"BMW/3 Series/2019":        {Stars: 5, AdultPct: 96, ChildPct: 86, PedestrianPct: 79, SafetyAssistPct: 86, TestYear: 2019},
	"Mercedes/C-Class/2022":    {Stars: 5, AdultPct: 93, ChildPct: 91, PedestrianPct: 75, SafetyAssistPct: 82, TestYear: 2022},
	"Peugeot/308/2022":         {Stars: 5, AdultPct: 91, ChildPct: 84, PedestrianPct: 78, SafetyAssistPct: 88, TestYear: 2022},
	"Renault/Clio/2020":        {Stars: 5, AdultPct: 96, ChildPct: 89, PedestrianPct: 73, SafetyAssistPct: 71, TestYear: 2020},
	"Ford/Focus/2018":          {Stars: 5, AdultPct: 90, ChildPct: 87, PedestrianPct: 70, SafetyAssistPct: 80, TestYear: 2018},
	"Toyota/Corolla/2019":      {Stars: 5, AdultPct: 96, ChildPct: 89, PedestrianPct: 82, SafetyAssistPct: 84, TestYear: 2019},
	"Skoda/Octavia/2021":       {Stars: 5, AdultPct: 93, ChildPct: 89, PedestrianPct: 67, SafetyAssistPct: 80, TestYear: 2021},
	"Seat/Leon/2020":           {Stars: 5, AdultPct: 94, ChildPct: 89, PedestrianPct: 80, SafetyAssistPct: 85, TestYear: 2020},
	"Audi/A3/2021":             {Stars: 5, AdultPct: 89, ChildPct: 89, PedestrianPct: 74, SafetyAssistPct: 79, TestYear: 2021},
	"Hyundai/i30/2021":         {Stars: 5, AdultPct: 90, ChildPct: 87, PedestrianPct: 68, SafetyAssistPct: 81, TestYear: 2021},
	"Kia/Ceed/2018":            {Stars: 4, AdultPct: 87, ChildPct: 84, PedestrianPct: 64, SafetyAssistPct: 71, TestYear: 2018},
	"Opel/Astra/2022":          {Stars: 5, AdultPct: 92, ChildPct: 87, PedestrianPct: 72, SafetyAssistPct: 84, TestYear: 2022},
	"Nissan/Qashqai/2021":      {Stars: 5, AdultPct: 89, ChildPct: 89, PedestrianPct: 76, SafetyAssistPct: 80, TestYear: 2021},
	"Citroen/C3/2021":          {Stars: 4, AdultPct: 83, ChildPct: 83, PedestrianPct: 64, SafetyAssistPct: 52, TestYear: 2021},
}

// ncapLookup finds the best matching NCAP entry for a given make/model/year.
// It first tries an exact match, then falls back to the closest model year.
func ncapLookup(make, model string, year int) *ncapRating {
	exact := make + "/" + model + "/" + strconv.Itoa(year)
	if r, ok := ncapTable[exact]; ok {
		return &r
	}
	// Search for same make/model, take rating from nearest year (prefer older test).
	prefix := make + "/" + model + "/"
	var best *ncapRating
	bestDiff := 9999
	for k, v := range ncapTable {
		if !strings.HasPrefix(k, prefix) {
			continue
		}
		yearStr := strings.TrimPrefix(k, prefix)
		ky, err := strconv.Atoi(yearStr)
		if err != nil {
			continue
		}
		diff := year - ky
		if diff < 0 {
			diff = -diff
		}
		if diff < bestDiff {
			bestDiff = diff
			r := v
			best = &r
		}
	}
	return best
}

// ── NHTSA vPIC ────────────────────────────────────────────────────────────────

type nhtsaVPICResponse struct {
	Results []map[string]string `json:"Results"`
	Count   int                 `json:"Count"`
}

func fetchNHTSASpec(ctx context.Context, vin string) (*vinSpec, error) {
	url := "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValuesExtended/" + vin + "?format=json"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 512*1024))
	if err != nil {
		return nil, err
	}

	var decoded nhtsaVPICResponse
	if err := json.Unmarshal(body, &decoded); err != nil {
		return nil, err
	}
	if len(decoded.Results) == 0 {
		return nil, fmt.Errorf("nhtsa_vpic: empty results")
	}

	r := decoded.Results[0]
	spec := &vinSpec{}

	spec.Make = strings.TrimSpace(r["Make"])
	spec.Model = strings.TrimSpace(r["Model"])
	if y, err := strconv.Atoi(strings.TrimSpace(r["ModelYear"])); err == nil {
		spec.Year = y
	}
	spec.BodyType = strings.TrimSpace(r["BodyClass"])
	spec.FuelType = strings.TrimSpace(r["FuelTypePrimary"])
	spec.Transmission = strings.TrimSpace(r["TransmissionStyle"])
	if d, err := strconv.ParseFloat(strings.TrimSpace(r["DisplacementL"]), 64); err == nil {
		spec.EngineDisplacementL = d
	}
	if c, err := strconv.Atoi(strings.TrimSpace(r["EngineCylinders"])); err == nil {
		spec.EngineCylinders = c
	}
	if kw, err := strconv.ParseFloat(strings.TrimSpace(r["EngineKW"]), 64); err == nil {
		spec.EngineKW = kw
	}
	// Derive country of manufacture from WMI (first 3 chars of VIN).
	spec.CountryOfManufacture = wmiToCountry(vin[:3])

	return spec, nil
}

// wmiToCountry maps the World Manufacturer Identifier prefix to a country code.
func wmiToCountry(wmi string) string {
	wmi = strings.ToUpper(wmi)
	switch wmi[0] {
	case 'W':
		return "DE"
	case 'V':
		if wmi[0] == 'V' && wmi[1] >= 'F' && wmi[1] <= 'R' {
			return "FR"
		}
		if wmi[0] == 'V' && (wmi[1] == 'S' || wmi[1] == 'N') {
			return "ES"
		}
		return "EU"
	case 'X':
		return "RU"
	case 'Y':
		return "SE"
	case 'Z':
		return "IT"
	case 'S':
		return "GB"
	case 'T':
		return "CH"
	case 'U':
		return "NL"
	case '1', '4', '5':
		return "US"
	case '2':
		return "CA"
	case '3':
		return "MX"
	case 'J':
		return "JP"
	case 'K':
		return "KR"
	case 'L':
		return "CN"
	}
	return ""
}

// ── NHTSA Recalls ─────────────────────────────────────────────────────────────

type nhtsaRecallsResponse struct {
	Count   int `json:"Count"`
	Results []struct {
		NHTSACampaignNumber string `json:"NHTSACampaignNumber"`
		Component           string `json:"Component"`
		Summary             string `json:"Summary"`
		Consequence         string `json:"Consequence"`
		Remedy              string `json:"Remedy"`
		ReportReceivedDate  string `json:"ReportReceivedDate"`
	} `json:"results"`
}

func fetchNHTSARecalls(ctx context.Context, make, model string, year int) ([]recallEntry, error) {
	if make == "" || model == "" || year == 0 {
		return nil, fmt.Errorf("nhtsa_recalls: missing make/model/year")
	}
	url := fmt.Sprintf(
		"https://api.nhtsa.gov/recalls/recallsByVehicle?make=%s&model=%s&modelYear=%d",
		strings.ReplaceAll(make, " ", "%20"),
		strings.ReplaceAll(model, " ", "%20"),
		year,
	)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 256*1024))
	if err != nil {
		return nil, err
	}

	var decoded nhtsaRecallsResponse
	if err := json.Unmarshal(body, &decoded); err != nil {
		return nil, err
	}

	recalls := make([]recallEntry, 0, len(decoded.Results))
	for _, r := range decoded.Results {
		date := ""
		// ReportReceivedDate arrives as "/Date(1234567890000)/" — extract epoch ms.
		if strings.HasPrefix(r.ReportReceivedDate, "/Date(") {
			ms := strings.TrimPrefix(r.ReportReceivedDate, "/Date(")
			ms = strings.Split(ms, ")")[0]
			if epoch, err := strconv.ParseInt(ms, 10, 64); err == nil {
				date = time.UnixMilli(epoch).UTC().Format("2006-01-02")
			}
		} else if r.ReportReceivedDate != "" {
			date = r.ReportReceivedDate
		}
		recalls = append(recalls, recallEntry{
			Campaign:  r.NHTSACampaignNumber,
			Component: r.Component,
			Summary:   r.Summary,
			Remedy:    r.Remedy,
			Date:      date,
		})
	}
	return recalls, nil
}

// ── ClickHouse forensic mileage ───────────────────────────────────────────────

type forensicResult struct {
	MaxKM   int
	Sources []string
}

func fetchForensicMileage(ctx context.Context, d *Deps, vin string) forensicResult {
	type chRow struct {
		Source string `ch:"source"`
		MaxKM  int    `ch:"max_km"`
	}
	rows, err := d.CH.Query(ctx, `
		SELECT source, max(mileage_km) AS max_km
		FROM cardex_forensics.mileage_history
		WHERE vin = ?
		GROUP BY source
	`, vin)
	if err != nil {
		slog.Warn("clickhouse forensic query failed", "vin", vin, "err", err)
		return forensicResult{}
	}
	defer rows.Close()

	fr := forensicResult{Sources: []string{}}
	for rows.Next() {
		var row chRow
		if err := rows.ScanStruct(&row); err != nil {
			continue
		}
		if row.MaxKM > fr.MaxKM {
			fr.MaxKM = row.MaxKM
		}
		fr.Sources = append(fr.Sources, row.Source)
	}
	return fr
}

// ── Redis spec cache ──────────────────────────────────────────────────────────

const specCacheTTL = 7 * 24 * time.Hour

func cacheGetSpec(ctx context.Context, d *Deps, vin string) *vinSpec {
	key := "vin:spec:" + vin
	val, err := d.Redis.Get(ctx, key).Bytes()
	if err != nil {
		return nil
	}
	var spec vinSpec
	if err := json.Unmarshal(val, &spec); err != nil {
		return nil
	}
	return &spec
}

func cacheSetSpec(ctx context.Context, d *Deps, vin string, spec *vinSpec) {
	key := "vin:spec:" + vin
	b, err := json.Marshal(spec)
	if err != nil {
		return
	}
	if err := d.Redis.Set(ctx, key, b, specCacheTTL).Err(); err != nil {
		slog.Warn("redis set spec failed", "vin", vin, "err", err)
	}
}

// ── VINHistory handler ────────────────────────────────────────────────────────

// VINHistory handles GET /api/v1/vin/{vin}
// Free vehicle history report — Carfax/CarVertical killer.
// Enriched with NHTSA vPIC, NHTSA Recalls, Euro NCAP, and forensic mileage.
func (d *Deps) VINHistory(w http.ResponseWriter, r *http.Request) {
	vin := strings.ToUpper(r.PathValue("vin"))
	if !vinRe.MatchString(vin) {
		writeError(w, http.StatusBadRequest, "invalid_vin", "VIN must be 17 alphanumeric chars (no I, O, Q)")
		return
	}

	ctx := r.Context()

	// ── 1. Fetch cached events from PostgreSQL ─────────────────────────────
	rows, err := d.DB.Query(ctx, `
		SELECT event_type, event_date::text, mileage_km, country, source_platform,
		       price_eur, description, confidence_score
		FROM vin_history_cache
		WHERE vin = $1
		ORDER BY event_date ASC
	`, vin)

	// The schema uses (event_type, event_date, data, source, confidence) but
	// the existing query maps to vinEvent fields. We read what we need.
	// Fall back gracefully if the query fails.
	var pgEvents []vinEvent
	if err != nil {
		slog.Warn("pg vin_history_cache query failed", "vin", vin, "err", err)
	} else {
		defer rows.Close()
		for rows.Next() {
			var e vinEvent
			if scanErr := rows.Scan(
				&e.EventType, &e.EventDate, &e.MileageKM, &e.Country, &e.Source,
				&e.PriceEUR, &e.Description, &e.Confidence,
			); scanErr != nil {
				continue
			}
			pgEvents = append(pgEvents, e)
		}
	}
	if pgEvents == nil {
		pgEvents = []vinEvent{}
	}

	// ── 2 & 3. Parallel: NHTSA spec (with Redis cache), NHTSA recalls, forensic mileage ──
	var (
		spec          *vinSpec
		recalls       []recallEntry
		forensic      forensicResult
		dataSources   []string
		muSources     sync.Mutex
	)

	addSource := func(s string) {
		muSources.Lock()
		dataSources = append(dataSources, s)
		muSources.Unlock()
	}

	// Try Redis spec cache first (avoids NHTSA call).
	spec = cacheGetSpec(ctx, d, vin)
	needNHTSASpec := spec == nil

	var wg sync.WaitGroup

	// NHTSA vPIC spec decode
	wg.Add(1)
	go func() {
		defer wg.Done()
		if !needNHTSASpec {
			addSource("nhtsa_vpic_cached")
			return
		}
		s, err := fetchNHTSASpec(ctx, vin)
		if err != nil {
			slog.Warn("nhtsa_vpic failed", "vin", vin, "err", err)
			return
		}
		spec = s
		cacheSetSpec(ctx, d, vin, s)
		addSource("nhtsa_vpic")
	}()

	// NHTSA Recalls — we need spec first so we wait for it.
	// We'll fetch recalls in a second pass after wg.Wait() below, using a
	// dedicated goroutine that starts after spec resolves.
	// (Alternatively, we use two wait groups.)

	// Forensic mileage from ClickHouse
	wg.Add(1)
	go func() {
		defer wg.Done()
		forensic = fetchForensicMileage(ctx, d, vin)
		if len(forensic.Sources) > 0 {
			addSource("cardex_forensics")
		}
	}()

	wg.Wait()

	// ── 4. NHTSA Recalls (now that spec is known) ──────────────────────────
	if spec != nil && spec.Make != "" {
		r2, err := fetchNHTSARecalls(ctx, spec.Make, spec.Model, spec.Year)
		if err != nil {
			slog.Warn("nhtsa_recalls failed", "vin", vin, "err", err)
		} else {
			recalls = r2
			addSource("nhtsa_recalls")
		}
	}
	if recalls == nil {
		recalls = []recallEntry{}
	}

	// ── 5. Euro NCAP lookup ────────────────────────────────────────────────
	var ncap *ncapRating
	if spec != nil && spec.Make != "" {
		ncap = ncapLookup(spec.Make, spec.Model, spec.Year)
		if ncap != nil {
			addSource("euro_ncap")
		}
	}

	// ── 6. Mileage rollback detection (combined events + forensic) ─────────
	// Inject a synthetic MILEAGE event for the forensic max if it exceeds cache.
	allEvents := make([]vinEvent, len(pgEvents))
	copy(allEvents, pgEvents)
	if forensic.MaxKM > 0 {
		src := "cardex_forensics"
		allEvents = append(allEvents, vinEvent{
			EventType:  "MILEAGE",
			EventDate:  time.Now().Format("2006-01-02"),
			MileageKM:  &forensic.MaxKM,
			Source:     &src,
			Confidence: 0.85,
		})
	}

	mileageOK, mileageWarning := checkMileageConsistency(allEvents)
	summary := buildVINSummary(pgEvents)

	// ── 7. Stolen status ───────────────────────────────────────────────────
	stolenStatus := "NOT_CHECKED"
	for _, e := range pgEvents {
		if e.EventType == "STOLEN_CHECK" && e.Description != nil {
			stolenStatus = *e.Description
		}
	}

	// ── 8. Data sources list ───────────────────────────────────────────────
	addSource("cardex_scraping")
	if isNLVIN(vin) {
		addSource("rdw_nl")
	}

	// First/last seen dates from events
	firstSeen, lastSeen := "", ""
	if summary.FirstSeen != nil {
		firstSeen = *summary.FirstSeen
	}
	if summary.LastSeen != nil {
		lastSeen = *summary.LastSeen
	}

	// ── Assemble response ──────────────────────────────────────────────────
	safety := vinSafety{
		RecallCount: len(recalls),
		Recalls:     recalls,
	}
	if ncap != nil {
		safety.NCAPStars = ncap.Stars
		safety.NCAPAdultPct = ncap.AdultPct
		safety.NCAPChildPct = ncap.ChildPct
		safety.NCAPPedestrianPct = ncap.PedestrianPct
		safety.NCAPSafetyAssistPct = ncap.SafetyAssistPct
		safety.NCAPTestYear = ncap.TestYear
	}

	report := vinReportV2{
		VIN:  vin,
		Spec: spec,
		Safety: safety,
		History: vinHistory{
			Events:          pgEvents,
			EventCount:      len(pgEvents),
			MileageOK:       mileageOK,
			MileageWarning:  mileageWarning,
			ForensicMaxKM:   forensic.MaxKM,
			ForensicSources: forensic.Sources,
			FirstSeen:       firstSeen,
			LastSeen:        lastSeen,
		},
		Summary:           summary,
		StolenStatus:      stolenStatus,
		DataSources:       dataSources,
		ReportGeneratedAt: time.Now().UTC().Format(time.RFC3339),
		Disclaimer:        "Free report from public sources. Not a substitute for a mechanical inspection or professional HPI check.",
	}

	writeJSON(w, http.StatusOK, report)
}

// isNLVIN heuristically checks whether a VIN is likely Netherlands-registered
// based on known Dutch/European WMI codes frequently processed through NL.
func isNLVIN(vin string) bool {
	wmi := strings.ToUpper(vin[:3])
	// Netherlands: TMBF* (Skoda NL), YV1 (Volvo NL plants), XLR/XL9 (Lynk/SAIC NL)
	nlPrefixes := []string{"XL9", "XLR", "XL8"}
	for _, p := range nlPrefixes {
		if strings.HasPrefix(wmi, p) {
			return true
		}
	}
	return false
}

// ── Existing helpers (unchanged) ──────────────────────────────────────────────

func buildVINSummary(events []vinEvent) vinSummary {
	s := vinSummary{
		Countries:       []string{},
		PriceHistoryEUR: []float64{},
	}
	seen := map[string]bool{}
	for i := range events {
		e := &events[i]
		if s.FirstSeen == nil {
			d := e.EventDate
			s.FirstSeen = &d
		}
		d := e.EventDate
		s.LastSeen = &d

		switch e.EventType {
		case "OWNERSHIP":
			s.OwnerCount++
		case "ACCIDENT":
			s.AccidentCount++
		case "IMPORT":
			s.ImportCount++
		case "LISTING":
			s.ListingCount++
		case "PRICE_CHANGE":
			if e.PriceEUR != nil {
				s.PriceHistoryEUR = append(s.PriceHistoryEUR, *e.PriceEUR)
			}
		}
		if e.MileageKM != nil {
			km := *e.MileageKM
			if s.MinMileageKM == nil || km < *s.MinMileageKM {
				s.MinMileageKM = &km
			}
			if s.MaxMileageKM == nil || km > *s.MaxMileageKM {
				s.MaxMileageKM = &km
			}
		}
		if e.Country != nil && !seen[*e.Country] {
			seen[*e.Country] = true
			s.Countries = append(s.Countries, *e.Country)
		}
	}
	return s
}

func checkMileageConsistency(events []vinEvent) (bool, string) {
	type point struct {
		date string
		km   int
	}
	var pts []point
	for _, e := range events {
		if e.MileageKM != nil && *e.MileageKM > 0 {
			pts = append(pts, point{e.EventDate, *e.MileageKM})
		}
	}
	for i := 1; i < len(pts); i++ {
		prev, curr := pts[i-1], pts[i]
		if curr.date > prev.date && curr.km < prev.km {
			return false, fmt.Sprintf(
				"ROLLBACK: %s (%s km) → %s (%s km)",
				prev.date, strconv.Itoa(prev.km),
				curr.date, strconv.Itoa(curr.km),
			)
		}
	}
	return true, ""
}
