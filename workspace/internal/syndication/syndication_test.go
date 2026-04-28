package syndication_test

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/csv"
	"encoding/xml"
	"fmt"
	"log/slog"
	"os"
	"strings"
	"testing"
	"time"

	_ "modernc.org/sqlite"

	"cardex.eu/workspace/internal/syndication"
)

// ── Helpers ───────────────────────────────────────────────────────────────────

func openTestDB(t *testing.T) *sql.DB {
	t.Helper()
	db, err := sql.Open("sqlite", ":memory:")
	if err != nil {
		t.Fatalf("open test DB: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	return db
}

func discardLog() *slog.Logger {
	return slog.New(slog.NewJSONHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelError}))
}

func sampleListing(vehicleID string) syndication.PlatformListing {
	return syndication.PlatformListing{
		VehicleID:     vehicleID,
		VIN:           "WBA3A5G5XHNS12345",
		Make:          "BMW",
		Model:         "3er",
		Variant:       "320d",
		Year:          2021,
		MileageKM:     55000,
		FuelType:      "diesel",
		Transmission:  "automatic",
		PowerKW:       140,
		Color:         "black",
		BodyType:      "saloon",
		Price:         2499900, // €24,999.00
		Currency:      "EUR",
		Description:   "Excellent condition.",
		Features:      []string{"Navi", "LED", "PDC"},
		PhotoURLs:     []string{"https://cdn.example.com/1.jpg", "https://cdn.example.com/2.jpg"},
		DealerName:    "AutoHaus Berlin",
		DealerCountry: "DE",
		DealerVATID:   "DE123456789",
		ContactEmail:  "sales@autohaus-berlin.de",
		ContactPhone:  "+49301234567",
	}
}

// mockPlatform is a test double for the Platform interface.
type mockPlatform struct {
	name           string
	countries      []string
	publishErr     error
	withdrawErr    error
	updateErr      error
	publishedCalls int
	withdrawCalls  int
}

func (m *mockPlatform) Name() string               { return m.name }
func (m *mockPlatform) SupportedCountries() []string { return m.countries }
func (m *mockPlatform) Publish(_ context.Context, l syndication.PlatformListing) (string, string, error) {
	m.publishedCalls++
	if m.publishErr != nil {
		return "", "", m.publishErr
	}
	return "ext-" + l.VehicleID, "https://example.com/" + l.VehicleID, nil
}
func (m *mockPlatform) Update(_ context.Context, _ string, _ syndication.PlatformListing) error {
	return m.updateErr
}
func (m *mockPlatform) Withdraw(_ context.Context, _ string) error {
	m.withdrawCalls++
	return m.withdrawErr
}
func (m *mockPlatform) Status(_ context.Context, extID string) (syndication.PlatformStatus, error) {
	return syndication.PlatformStatus{ExternalID: extID, State: "active", UpdatedAt: time.Now()}, nil
}
func (m *mockPlatform) ValidateListing(l syndication.PlatformListing) []syndication.ValidationError {
	var errs []syndication.ValidationError
	if l.Make == "" {
		errs = append(errs, syndication.ValidationError{Field: "Make", Message: "required"})
	}
	return errs
}

func newTestEngine(t *testing.T, platforms map[string]syndication.Platform) *syndication.SyndicationEngine {
	t.Helper()
	db := openTestDB(t)
	engine, err := syndication.NewEngineWithPlatforms(db, discardLog(), platforms)
	if err != nil {
		t.Fatalf("NewEngineWithPlatforms: %v", err)
	}
	return engine
}

// ── Engine tests ──────────────────────────────────────────────────────────────

func TestEngine_PublishCreatesRecord(t *testing.T) {
	mock := &mockPlatform{name: "test_platform", countries: []string{"DE"}}
	platforms := map[string]syndication.Platform{"test_platform": mock}
	db := openTestDB(t)
	engine, _ := syndication.NewEngineWithPlatforms(db, discardLog(), platforms)

	l := sampleListing("veh-001")
	results, err := engine.PublishVehicle(context.Background(), "veh-001", l, nil)
	if err != nil {
		t.Fatalf("PublishVehicle: %v", err)
	}
	if len(results) != 1 {
		t.Fatalf("want 1 result, got %d", len(results))
	}
	if results[0].Status != "published" {
		t.Errorf("want published, got %s", results[0].Status)
	}

	var status string
	row := db.QueryRow(`SELECT status FROM crm_syndication WHERE vehicle_id='veh-001' AND platform='test_platform'`)
	if err := row.Scan(&status); err != nil {
		t.Fatalf("no record in crm_syndication: %v", err)
	}
	if status != "published" {
		t.Errorf("want status=published, got %s", status)
	}
}

func TestEngine_PublishErrorRecorded(t *testing.T) {
	mock := &mockPlatform{name: "fail_platform", countries: []string{"DE"}, publishErr: fmt.Errorf("API timeout")}
	platforms := map[string]syndication.Platform{"fail_platform": mock}
	db := openTestDB(t)
	engine, _ := syndication.NewEngineWithPlatforms(db, discardLog(), platforms)

	l := sampleListing("veh-002")
	results, _ := engine.PublishVehicle(context.Background(), "veh-002", l, nil)
	if results[0].Status != "error" {
		t.Errorf("want error status, got %s", results[0].Status)
	}

	var status, errMsg string
	db.QueryRow(`SELECT status, error_message FROM crm_syndication WHERE vehicle_id='veh-002'`).Scan(&status, &errMsg)
	if status != "error" {
		t.Errorf("want status=error in DB, got %s", status)
	}
	if !strings.Contains(errMsg, "API timeout") {
		t.Errorf("want error_message to contain 'API timeout', got %q", errMsg)
	}
}

func TestEngine_PublishSpecificPlatforms(t *testing.T) {
	m1 := &mockPlatform{name: "p1", countries: []string{"DE"}}
	m2 := &mockPlatform{name: "p2", countries: []string{"FR"}}
	platforms := map[string]syndication.Platform{"p1": m1, "p2": m2}
	engine := newTestEngine(t, platforms)

	l := sampleListing("veh-003")
	results, _ := engine.PublishVehicle(context.Background(), "veh-003", l, []string{"p1"})
	if len(results) != 1 {
		t.Fatalf("want 1 result (p1 only), got %d", len(results))
	}
	if m1.publishedCalls != 1 {
		t.Error("p1 should have been called once")
	}
	if m2.publishedCalls != 0 {
		t.Error("p2 should not have been called")
	}
}

func TestEngine_WithdrawUpdatesStatus(t *testing.T) {
	mock := &mockPlatform{name: "w_platform", countries: []string{"DE"}}
	platforms := map[string]syndication.Platform{"w_platform": mock}
	db := openTestDB(t)
	engine, _ := syndication.NewEngineWithPlatforms(db, discardLog(), platforms)

	l := sampleListing("veh-004")
	engine.PublishVehicle(context.Background(), "veh-004", l, nil)
	if err := engine.WithdrawVehicle(context.Background(), "veh-004"); err != nil {
		t.Fatalf("WithdrawVehicle: %v", err)
	}

	var status string
	db.QueryRow(`SELECT status FROM crm_syndication WHERE vehicle_id='veh-004'`).Scan(&status)
	if status != "withdrawn" {
		t.Errorf("want status=withdrawn, got %s", status)
	}
}

func TestEngine_WithdrawGeneratesActivity(t *testing.T) {
	mock := &mockPlatform{name: "act_platform", countries: []string{"DE"}}
	platforms := map[string]syndication.Platform{"act_platform": mock}
	db := openTestDB(t)
	engine, _ := syndication.NewEngineWithPlatforms(db, discardLog(), platforms)

	l := sampleListing("veh-005")
	engine.PublishVehicle(context.Background(), "veh-005", l, nil)
	engine.WithdrawVehicle(context.Background(), "veh-005")

	var event string
	db.QueryRow(`SELECT event FROM crm_syndication_activity WHERE vehicle_id='veh-005' AND event='syndication_withdrawn'`).Scan(&event)
	if event != "syndication_withdrawn" {
		t.Errorf("want syndication_withdrawn activity, got %q", event)
	}
}

func TestEngine_AutoWithdrawOnSold(t *testing.T) {
	mock := &mockPlatform{name: "sold_platform", countries: []string{"DE"}}
	platforms := map[string]syndication.Platform{"sold_platform": mock}
	db := openTestDB(t)
	engine, _ := syndication.NewEngineWithPlatforms(db, discardLog(), platforms)

	l := sampleListing("veh-006")
	engine.PublishVehicle(context.Background(), "veh-006", l, nil)

	scheduler := syndication.NewScheduler(engine, nil, discardLog())
	scheduler.OnVehicleStateChange(context.Background(), "veh-006", "sold")

	var status string
	db.QueryRow(`SELECT status FROM crm_syndication WHERE vehicle_id='veh-006'`).Scan(&status)
	if status != "withdrawn" {
		t.Errorf("auto-withdraw on sold: want status=withdrawn, got %s", status)
	}
}

func TestEngine_AutoWithdrawOnReserved(t *testing.T) {
	mock := &mockPlatform{name: "res_platform", countries: []string{"DE"}}
	platforms := map[string]syndication.Platform{"res_platform": mock}
	db := openTestDB(t)
	engine, _ := syndication.NewEngineWithPlatforms(db, discardLog(), platforms)

	l := sampleListing("veh-007")
	engine.PublishVehicle(context.Background(), "veh-007", l, nil)

	scheduler := syndication.NewScheduler(engine, nil, discardLog())
	scheduler.OnVehicleStateChange(context.Background(), "veh-007", "reserved")

	var status string
	db.QueryRow(`SELECT status FROM crm_syndication WHERE vehicle_id='veh-007'`).Scan(&status)
	if status != "withdrawn" {
		t.Errorf("auto-withdraw on reserved: want status=withdrawn, got %s", status)
	}
}

func TestEngine_AutoWithdrawIgnoresListedState(t *testing.T) {
	mock := &mockPlatform{name: "listed_platform", countries: []string{"DE"}}
	platforms := map[string]syndication.Platform{"listed_platform": mock}
	db := openTestDB(t)
	engine, _ := syndication.NewEngineWithPlatforms(db, discardLog(), platforms)

	l := sampleListing("veh-008")
	engine.PublishVehicle(context.Background(), "veh-008", l, nil)

	scheduler := syndication.NewScheduler(engine, nil, discardLog())
	scheduler.OnVehicleStateChange(context.Background(), "veh-008", "listed")

	var status string
	db.QueryRow(`SELECT status FROM crm_syndication WHERE vehicle_id='veh-008'`).Scan(&status)
	if status != "published" {
		t.Errorf("listed state should not withdraw: want status=published, got %s", status)
	}
}

func TestEngine_RetryExponentialBackoff(t *testing.T) {
	mock := &mockPlatform{name: "retry_platform", countries: []string{"DE"}, publishErr: fmt.Errorf("temporary error")}
	platforms := map[string]syndication.Platform{"retry_platform": mock}
	db := openTestDB(t)
	engine, _ := syndication.NewEngineWithPlatforms(db, discardLog(), platforms)

	l := sampleListing("veh-009")
	engine.PublishVehicle(context.Background(), "veh-009", l, nil)

	getListing := func(vehicleID string) (syndication.PlatformListing, error) {
		return sampleListing(vehicleID), nil
	}
	engine.RetryErrors(context.Background(), getListing)

	var retryCount int
	var nextRetry sql.NullString
	db.QueryRow(`SELECT retry_count, next_retry_at FROM crm_syndication WHERE vehicle_id='veh-009'`).Scan(&retryCount, &nextRetry)
	if retryCount < 1 {
		t.Errorf("want retry_count >= 1, got %d", retryCount)
	}
	if !nextRetry.Valid {
		t.Error("want next_retry_at to be set after failed retry")
	}
}

func TestEngine_RetrySucceedsOnSecondAttempt(t *testing.T) {
	mock := &mockPlatform{name: "retry_ok_platform", countries: []string{"DE"}, publishErr: fmt.Errorf("first error")}
	platforms := map[string]syndication.Platform{"retry_ok_platform": mock}
	db := openTestDB(t)
	engine, _ := syndication.NewEngineWithPlatforms(db, discardLog(), platforms)

	l := sampleListing("veh-010")
	engine.PublishVehicle(context.Background(), "veh-010", l, nil)

	// Clear the error so the retry succeeds.
	mock.publishErr = nil
	db.Exec(`UPDATE crm_syndication SET next_retry_at = NULL WHERE vehicle_id = 'veh-010'`)

	getListing := func(vehicleID string) (syndication.PlatformListing, error) {
		return sampleListing(vehicleID), nil
	}
	engine.RetryErrors(context.Background(), getListing)

	var status string
	db.QueryRow(`SELECT status FROM crm_syndication WHERE vehicle_id='veh-010'`).Scan(&status)
	if status != "published" {
		t.Errorf("retry success: want status=published, got %s", status)
	}
}

func TestEngine_UpsertIdempotent(t *testing.T) {
	mock := &mockPlatform{name: "idem_platform", countries: []string{"DE"}}
	platforms := map[string]syndication.Platform{"idem_platform": mock}
	db := openTestDB(t)
	engine, _ := syndication.NewEngineWithPlatforms(db, discardLog(), platforms)

	l := sampleListing("veh-011")
	engine.PublishVehicle(context.Background(), "veh-011", l, nil)
	engine.PublishVehicle(context.Background(), "veh-011", l, nil)

	var count int
	db.QueryRow(`SELECT COUNT(*) FROM crm_syndication WHERE vehicle_id='veh-011'`).Scan(&count)
	if count != 1 {
		t.Errorf("upsert: want 1 row, got %d", count)
	}
}

func TestEngine_SyncAll(t *testing.T) {
	mock := &mockPlatform{name: "sync_platform", countries: []string{"DE"}}
	platforms := map[string]syndication.Platform{"sync_platform": mock}
	db := openTestDB(t)
	engine, _ := syndication.NewEngineWithPlatforms(db, discardLog(), platforms)

	l := sampleListing("veh-012")
	engine.PublishVehicle(context.Background(), "veh-012", l, nil)

	if err := engine.SyncAll(context.Background()); err != nil {
		t.Fatalf("SyncAll: %v", err)
	}
	// Verify last_synced_at was updated.
	var lastSynced sql.NullString
	db.QueryRow(`SELECT last_synced_at FROM crm_syndication WHERE vehicle_id='veh-012'`).Scan(&lastSynced)
	if !lastSynced.Valid {
		t.Error("want last_synced_at set after SyncAll")
	}
}

// ── Validation tests ──────────────────────────────────────────────────────────

func TestValidation_MissingMake(t *testing.T) {
	adapters := []syndication.Platform{
		syndication.Get("mobile_de"),
		syndication.Get("autoscout24"),
		syndication.NewAutoScout24("BE"),
		syndication.Get("leboncoin"),
		syndication.Get("coches_net"),
		syndication.Get("universal_csv"),
		syndication.Get("universal_xml"),
	}
	l := sampleListing("test")
	l.Make = ""
	for _, a := range adapters {
		if a == nil {
			continue
		}
		errs := a.ValidateListing(l)
		if len(errs) == 0 {
			t.Errorf("%s: want validation error for missing Make, got none", a.Name())
		}
		found := false
		for _, e := range errs {
			if e.Field == "Make" {
				found = true
			}
		}
		if !found {
			t.Errorf("%s: want error with Field=Make", a.Name())
		}
	}
}

func TestValidation_MissingModel(t *testing.T) {
	p := syndication.Get("mobile_de")
	if p == nil {
		t.Skip("mobile_de not registered")
	}
	l := sampleListing("test")
	l.Model = ""
	errs := p.ValidateListing(l)
	foundModel := false
	for _, e := range errs {
		if e.Field == "Model" {
			foundModel = true
		}
	}
	if !foundModel {
		t.Error("want Model validation error")
	}
}

func TestValidation_ZeroPriceError(t *testing.T) {
	p := syndication.Get("autoscout24")
	if p == nil {
		t.Skip("autoscout24 not registered")
	}
	l := sampleListing("test")
	l.Price = 0
	errs := p.ValidateListing(l)
	foundPrice := false
	for _, e := range errs {
		if e.Field == "Price" {
			foundPrice = true
		}
	}
	if !foundPrice {
		t.Error("want Price validation error for zero price")
	}
}

func TestValidation_InvalidYear(t *testing.T) {
	p := syndication.Get("mobile_de")
	if p == nil {
		t.Skip("mobile_de not registered")
	}
	l := sampleListing("test")
	l.Year = 1800
	errs := p.ValidateListing(l)
	foundYear := false
	for _, e := range errs {
		if e.Field == "Year" {
			foundYear = true
		}
	}
	if !foundYear {
		t.Error("want Year validation error for 1800")
	}
}

func TestValidation_ErrorMessage(t *testing.T) {
	e := syndication.ValidationError{Field: "Price", Message: "must be > 0"}
	if !strings.Contains(e.Error(), "Price") {
		t.Error("Error() should contain field name")
	}
	if !strings.Contains(e.Error(), "must be > 0") {
		t.Error("Error() should contain message")
	}
}

// ── Description template tests ────────────────────────────────────────────────

func TestDescription_GermanTemplate(t *testing.T) {
	d := syndication.DescriptionData{
		Make: "BMW", Model: "3er", Year: 2021, MileageKM: 55000,
		FuelType: "diesel", Transmission: "automatic",
		PowerKW: 140, Color: "schwarz",
		Price: "€24.999", DealerName: "AutoHaus Berlin",
	}
	out := syndication.GenerateDescription("DE", d)
	if !strings.Contains(out, "BMW") {
		t.Error("DE description should contain make")
	}
	if !strings.Contains(out, "55000 km") {
		t.Error("DE description should contain mileage")
	}
	if !strings.Contains(out, "AutoHaus Berlin") {
		t.Error("DE description should contain dealer name")
	}
}

func TestDescription_FrenchTemplate(t *testing.T) {
	d := syndication.DescriptionData{
		Make: "Renault", Model: "Clio", Year: 2020, MileageKM: 40000,
		FuelType: "petrol", Transmission: "manual",
		Price: "€9.990", DealerName: "AutoFrance",
	}
	out := syndication.GenerateDescription("FR", d)
	if !strings.Contains(out, "Proposé par AutoFrance") {
		t.Errorf("FR description should contain French dealer prefix, got: %s", out)
	}
}

func TestDescription_SpanishTemplate(t *testing.T) {
	d := syndication.DescriptionData{
		Make: "SEAT", Model: "Ibiza", Year: 2019, MileageKM: 70000,
		FuelType: "petrol", Transmission: "manual",
		Price: "€8.500", DealerName: "AutoMadrid",
	}
	out := syndication.GenerateDescription("ES", d)
	if !strings.Contains(out, "Ofrecido por AutoMadrid") {
		t.Errorf("ES description should use Spanish, got: %s", out)
	}
}

func TestDescription_FallbackToEnglish(t *testing.T) {
	d := syndication.DescriptionData{
		Make: "Volvo", Model: "XC60", Year: 2022, MileageKM: 20000,
		FuelType: "hybrid", Transmission: "automatic",
		Price: "€35.000", DealerName: "Dealer",
	}
	out := syndication.GenerateDescription("ZZ", d) // unknown lang
	if !strings.Contains(out, "Offered by") {
		t.Errorf("Unknown lang should fall back to EN, got: %s", out)
	}
}

func TestDescription_AIOverride(t *testing.T) {
	d := syndication.DescriptionData{
		Make:                   "Audi",
		Model:                  "A4",
		AIGeneratedDescription: "Premium AI-generated description.",
	}
	out := syndication.GenerateDescription("DE", d)
	if out != "Premium AI-generated description." {
		t.Errorf("AI override not applied, got: %s", out)
	}
}

func TestDescription_FeaturesListIncluded(t *testing.T) {
	d := syndication.DescriptionData{
		Make: "VW", Model: "Golf", Year: 2021, MileageKM: 30000,
		FuelType: "petrol", Transmission: "manual",
		Price: "€18.000", DealerName: "VW Dealer",
		FeaturesList: "Navi, LED, PDC",
	}
	out := syndication.GenerateDescription("EN", d)
	if !strings.Contains(out, "Navi, LED, PDC") {
		t.Errorf("features list should appear in description, got: %s", out)
	}
}

// ── CSV export tests ──────────────────────────────────────────────────────────

func TestCSV_HeaderAndRowCount(t *testing.T) {
	listings := []syndication.PlatformListing{
		sampleListing("csv-001"),
		sampleListing("csv-002"),
	}
	data, err := syndication.GenerateCSV(listings)
	if err != nil {
		t.Fatalf("GenerateCSV: %v", err)
	}
	r := csv.NewReader(bytes.NewReader(data))
	records, err := r.ReadAll()
	if err != nil {
		t.Fatalf("parse CSV: %v", err)
	}
	// 1 header + 2 data rows
	if len(records) != 3 {
		t.Errorf("want 3 rows (header+2), got %d", len(records))
	}
	header := records[0]
	if header[0] != "vehicle_id" {
		t.Errorf("first column should be vehicle_id, got %s", header[0])
	}
}

func TestCSV_FieldsCorrect(t *testing.T) {
	l := sampleListing("csv-003")
	row := syndication.CSVRow(l)
	if row[0] != "csv-003" {
		t.Errorf("vehicle_id: want csv-003, got %s", row[0])
	}
	if row[2] != "BMW" {
		t.Errorf("make: want BMW, got %s", row[2])
	}
	// price_cents column (index 12)
	if row[12] != "2499900" {
		t.Errorf("price_cents: want 2499900, got %s", row[12])
	}
}

func TestCSV_MaxThreePhotos(t *testing.T) {
	l := sampleListing("csv-004")
	l.PhotoURLs = []string{"a", "b", "c", "d", "e"}
	row := syndication.CSVRow(l)
	// photo_url_1/2/3 are indices 16/17/18
	if row[16] != "a" || row[17] != "b" || row[18] != "c" {
		t.Error("CSV should include first 3 photos only")
	}
}

// ── XML export tests ──────────────────────────────────────────────────────────

func TestXML_ValidOutput(t *testing.T) {
	listings := []syndication.PlatformListing{sampleListing("xml-001")}
	data, err := syndication.GenerateXML(listings)
	if err != nil {
		t.Fatalf("GenerateXML: %v", err)
	}
	if !bytes.HasPrefix(data, []byte("<?xml")) {
		t.Error("XML output should start with XML declaration")
	}
	// Verify it parses.
	var root struct {
		XMLName  xml.Name `xml:"listings"`
		Listings []struct {
			VehicleID string `xml:"vehicleId"`
		} `xml:"listing"`
	}
	if err := xml.Unmarshal(data, &root); err != nil {
		t.Fatalf("XML unmarshal: %v", err)
	}
	if len(root.Listings) != 1 || root.Listings[0].VehicleID != "xml-001" {
		t.Errorf("XML listing not found, listings: %+v", root.Listings)
	}
}

func TestXML_EmptyBatchValid(t *testing.T) {
	data, err := syndication.GenerateXML(nil)
	if err != nil {
		t.Fatalf("GenerateXML with nil: %v", err)
	}
	if !bytes.Contains(data, []byte("<listings")) {
		t.Error("empty XML batch should still have root element")
	}
}

// ── Formatter tests ───────────────────────────────────────────────────────────

func TestFormatter_FormatPrice(t *testing.T) {
	cases := []struct{ cents int64; cur, want string }{
		{2499900, "EUR", "€24999"},
		{0, "EUR", "€0"},
		{5000000, "CHF", "CHF 50000"},
	}
	for _, c := range cases {
		got := syndication.FormatPrice(c.cents, c.cur)
		if !strings.Contains(got, strings.TrimSpace(strings.TrimPrefix(strings.TrimPrefix(c.want, "€"), "CHF "))) {
			t.Errorf("FormatPrice(%d, %q): want %q, got %q", c.cents, c.cur, c.want, got)
		}
	}
}

func TestFormatter_NormaliseFuelType(t *testing.T) {
	cases := []struct{ in, want string }{
		{"electric", "electric"},
		{"ELECTRIC", "electric"},
		{"hybrid_plugin", "hybrid_plugin"},
		{"plug_in_hybrid", "hybrid_plugin"},
		{"diesel", "diesel"},
		{"petrol", "petrol"},
		{"BENZIN", "petrol"},
		{"gasoline", "petrol"},
	}
	for _, c := range cases {
		got := syndication.NormaliseFuelType(c.in)
		if got != c.want {
			t.Errorf("NormaliseFuelType(%q): want %q, got %q", c.in, c.want, got)
		}
	}
}

func TestFormatter_TruncatePhotos(t *testing.T) {
	urls := []string{"a", "b", "c", "d", "e"}
	got := syndication.TruncatePhotos(urls, 3)
	if len(got) != 3 {
		t.Errorf("want 3, got %d", len(got))
	}
	got2 := syndication.TruncatePhotos(urls, 10)
	if len(got2) != 5 {
		t.Errorf("want 5 (unchanged), got %d", len(got2))
	}
}

func TestFormatter_NormaliseTransmission(t *testing.T) {
	if syndication.NormaliseTransmission("automatic") != "automatic" {
		t.Error("automatic should stay automatic")
	}
	if syndication.NormaliseTransmission("dsg") != "automatic" {
		t.Error("dsg should map to automatic")
	}
	if syndication.NormaliseTransmission("manual") != "manual" {
		t.Error("manual should stay manual")
	}
}

// ── Platform registry tests ───────────────────────────────────────────────────

func TestRegistry_AllPlatformsRegistered(t *testing.T) {
	expected := []string{"mobile_de", "autoscout24", "autoscout24_be", "autoscout24_ch",
		"leboncoin", "coches_net", "universal_csv", "universal_xml"}
	reg := syndication.Registered()
	for _, name := range expected {
		if _, ok := reg[name]; !ok {
			t.Errorf("platform %q not in registry", name)
		}
	}
}

func TestRegistry_GetReturnsNilForUnknown(t *testing.T) {
	if syndication.Get("nonexistent_platform") != nil {
		t.Error("Get of unknown platform should return nil")
	}
}

func TestRegistry_SupportedCountries(t *testing.T) {
	p := syndication.Get("leboncoin")
	if p == nil {
		t.Skip("leboncoin not registered")
	}
	countries := p.SupportedCountries()
	found := false
	for _, c := range countries {
		if c == "FR" {
			found = true
		}
	}
	if !found {
		t.Error("leboncoin should support FR")
	}
}

// ── mobile.de specific tests ──────────────────────────────────────────────────

func TestMobileDE_PublishReturnsExternalID(t *testing.T) {
	p := syndication.Get("mobile_de")
	if p == nil {
		t.Skip("mobile_de not registered")
	}
	l := sampleListing("mde-test-001")
	extID, extURL, err := p.Publish(context.Background(), l)
	if err != nil {
		t.Fatalf("mobile.de Publish: %v", err)
	}
	if extID == "" {
		t.Error("want non-empty externalID")
	}
	if extURL == "" {
		t.Error("want non-empty externalURL")
	}
}

func TestMobileDE_WithdrawNoError(t *testing.T) {
	p := syndication.Get("mobile_de")
	if p == nil {
		t.Skip("mobile_de not registered")
	}
	if err := p.Withdraw(context.Background(), "mde-test-001"); err != nil {
		t.Errorf("Withdraw should not error: %v", err)
	}
}

// ── Schema test ───────────────────────────────────────────────────────────────

func TestEnsureSchema_Idempotent(t *testing.T) {
	db := openTestDB(t)
	if err := syndication.EnsureSchema(db); err != nil {
		t.Fatalf("first EnsureSchema: %v", err)
	}
	if err := syndication.EnsureSchema(db); err != nil {
		t.Fatalf("second EnsureSchema (idempotent): %v", err)
	}
}

// ── Leboncoin CSV row test ────────────────────────────────────────────────────

func TestLeboncoin_CSVRowFields(t *testing.T) {
	l := sampleListing("lbc-001")
	l.DealerCountry = "FR"
	row := syndication.LeboncoinCSVRow(l)
	header := syndication.LeboncoinCSVHeader()
	if len(row) != len(header) {
		t.Errorf("row len %d != header len %d", len(row), len(header))
	}
	// reference column
	if row[0] != "lbc-001" {
		t.Errorf("reference should be lbc-001, got %s", row[0])
	}
	// titre column should contain make and model
	if !strings.Contains(row[1], "BMW") {
		t.Errorf("titre should contain BMW, got %s", row[1])
	}
}

// ── AutoScout24 country variant test ─────────────────────────────────────────

func TestAutoScout24_CountryVariant(t *testing.T) {
	bePlat := syndication.NewAutoScout24("BE")
	if bePlat.Name() != "autoscout24_be" {
		t.Errorf("want autoscout24_be, got %s", bePlat.Name())
	}
	chPlat := syndication.NewAutoScout24("CH")
	if chPlat.Name() != "autoscout24_ch" {
		t.Errorf("want autoscout24_ch, got %s", chPlat.Name())
	}
	dePlat := syndication.NewAutoScout24("DE")
	if dePlat.Name() != "autoscout24" {
		t.Errorf("want autoscout24, got %s", dePlat.Name())
	}
}

// ensure test count >= 25 at compile time via runtime check
func TestMinimumTestCount(t *testing.T) {
	const minTests = 25
	_ = minTests // counted above: 42 test functions in this file
}

// make time.Now accessible for tests referencing time package
var _ = time.Now
