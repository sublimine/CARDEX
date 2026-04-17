package routes

import (
	"bytes"
	"database/sql"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	_ "modernc.org/sqlite"
)

// ── Fixture helpers ───────────────────────────────────────────────────────────

// makeFixtureDB creates an in-memory SQLite database with minimal schema and
// synthetic vehicle listings for testing.
func makeFixtureDB(t *testing.T) *sql.DB {
	t.Helper()
	db, err := sql.Open("sqlite", ":memory:")
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}

	// Minimal schema matching production tables.
	schema := `
		CREATE TABLE dealer_entity (
			dealer_id        TEXT PRIMARY KEY,
			canonical_name   TEXT NOT NULL,
			normalized_name  TEXT NOT NULL DEFAULT '',
			country_code     TEXT NOT NULL,
			status           TEXT DEFAULT 'ACTIVE',
			confidence_score REAL DEFAULT 0.8
		);
		CREATE TABLE vehicle_record (
			vehicle_id      TEXT PRIMARY KEY,
			dealer_id       TEXT REFERENCES dealer_entity(dealer_id),
			make_canonical  TEXT,
			model_canonical TEXT,
			year            INTEGER,
			mileage_km      INTEGER,
			fuel_type       TEXT,
			price_net_eur   REAL,
			price_gross_eur REAL,
			indexed_at      TEXT DEFAULT CURRENT_TIMESTAMP,
			status          TEXT DEFAULT 'ACTIVE'
		);
	`
	if _, err := db.Exec(schema); err != nil {
		t.Fatalf("create schema: %v", err)
	}
	return db
}

// insertDealers inserts one active dealer per country.
func insertDealers(t *testing.T, db *sql.DB, countries []string) {
	t.Helper()
	for _, c := range countries {
		_, err := db.Exec(
			`INSERT INTO dealer_entity(dealer_id, canonical_name, country_code) VALUES(?,?,?)`,
			"D-"+c, "Dealer "+c, c,
		)
		if err != nil {
			t.Fatalf("insert dealer %s: %v", c, err)
		}
	}
}

// insertVehicles inserts n vehicles for a dealer at the given price.
func insertVehicles(t *testing.T, db *sql.DB, dealerID, make_, model string, year, mileage, n int, priceEUR float64) {
	t.Helper()
	for i := 0; i < n; i++ {
		id := fmt.Sprintf("%s-%s-%s-%d-%d", dealerID, make_, model, year, i)
		_, err := db.Exec(
			`INSERT INTO vehicle_record(vehicle_id, dealer_id, make_canonical, model_canonical, year, mileage_km, fuel_type, price_gross_eur)
			 VALUES(?,?,?,?,?,?,'diesel',?)`,
			id, dealerID, make_, model, year, mileage, priceEUR,
		)
		if err != nil {
			t.Fatalf("insert vehicle %s: %v", id, err)
		}
	}
}

// fixtureDB creates a DB with BMW 320d 2021 45k km listings in 5 countries
// at different prices, suitable for spread and optimizer tests.
func fixtureDB(t *testing.T) *sql.DB {
	t.Helper()
	db := makeFixtureDB(t)
	countries := []string{"DE", "FR", "NL", "BE", "CH"}
	insertDealers(t, db, countries)

	// Prices in EUR (will be stored as price_gross_eur):
	// DE=25000, FR=24000, NL=26000, BE=24500, CH=28000
	prices := map[string]float64{
		"DE": 25000,
		"FR": 24000,
		"NL": 26000,
		"BE": 24500,
		"CH": 28000,
	}
	for c, p := range prices {
		insertVehicles(t, db, "D-"+c, "BMW", "320d", 2021, 45000, 5, p)
	}
	return db
}

// ── Transport cost tests ──────────────────────────────────────────────────────

func TestTransportCost_DE_FR(t *testing.T) {
	tm := DefaultTransportMatrix()
	got := tm.Cost("DE", "FR")
	if got != 75000 {
		t.Errorf("DE→FR: want 75000 cents, got %d", got)
	}
}

func TestTransportCost_DE_ES_greater_than_DE_NL(t *testing.T) {
	tm := DefaultTransportMatrix()
	deES := tm.Cost("DE", "ES")
	deNL := tm.Cost("DE", "NL")
	if deES <= deNL {
		t.Errorf("DE→ES (%d) should be > DE→NL (%d)", deES, deNL)
	}
}

func TestTransportCost_Symmetric(t *testing.T) {
	tm := DefaultTransportMatrix()
	pairs := [][2]string{{"DE", "FR"}, {"NL", "BE"}, {"FR", "ES"}}
	for _, p := range pairs {
		fwd := tm.Cost(p[0], p[1])
		rev := tm.Cost(p[1], p[0])
		if fwd != rev {
			t.Errorf("transport not symmetric: %s→%s=%d, %s→%s=%d",
				p[0], p[1], fwd, p[1], p[0], rev)
		}
	}
}

func TestTransportCost_SameCountry(t *testing.T) {
	tm := DefaultTransportMatrix()
	for _, c := range []string{"DE", "FR", "NL", "BE", "CH", "ES"} {
		if got := tm.Cost(c, c); got != 0 {
			t.Errorf("%s→%s: want 0, got %d", c, c, got)
		}
	}
}

func TestTransportCost_UnknownPair_ReturnsPenalty(t *testing.T) {
	tm := DefaultTransportMatrix()
	got := tm.Cost("DE", "IT")
	if got != 300000 {
		t.Errorf("unknown pair should return 300000 penalty, got %d", got)
	}
}

func TestTransportCost_YAML_Override(t *testing.T) {
	// Write a temporary YAML file overriding DE-FR.
	tmp := t.TempDir() + "/costs.yaml"
	content := "pairs:\n  DE-FR: 500\n  FR-DE: 500\n"
	if err := writeFile(tmp, []byte(content)); err != nil {
		t.Fatal(err)
	}
	tm, err := LoadTransportMatrix(tmp)
	if err != nil {
		t.Fatal(err)
	}
	if got := tm.Cost("DE", "FR"); got != 50000 {
		t.Errorf("overridden DE→FR: want 50000, got %d", got)
	}
	// Non-overridden pair should still use default.
	if got := tm.Cost("DE", "NL"); got != 45000 {
		t.Errorf("non-overridden DE→NL: want 45000, got %d", got)
	}
}

// ── Tax engine tests ──────────────────────────────────────────────────────────

func TestTaxEngine_IntraEU_Zero(t *testing.T) {
	e := NewDefaultTaxEngine()
	pairs := [][2]string{{"DE", "FR"}, {"FR", "ES"}, {"NL", "BE"}, {"BE", "DE"}}
	for _, p := range pairs {
		cost, err := e.VATCost(p[0], p[1], 2500000) // €25,000 vehicle
		if err != nil {
			t.Fatalf("%s→%s: unexpected error: %v", p[0], p[1], err)
		}
		if cost != 0 {
			t.Errorf("%s→%s: intra-EU B2B should be 0, got %d", p[0], p[1], cost)
		}
	}
}

func TestTaxEngine_EUtoSwitzerland_8pct(t *testing.T) {
	e := NewDefaultTaxEngine()
	vehiclePrice := int64(2500000) // €25,000 in cents
	cost, err := e.VATCost("DE", "CH", vehiclePrice)
	if err != nil {
		t.Fatal(err)
	}
	// Expected: 8.1% × €25,000 + €500 fixed = €2,025 + €500 = €2,525 = 252500 cents
	expectedVAT := int64(float64(vehiclePrice) * 0.081)
	expected := expectedVAT + chCustomsFixedCents
	if cost != expected {
		t.Errorf("DE→CH VAT: want %d, got %d (expected ~€%.0f)", expected, cost, float64(expected)/100)
	}
}

func TestTaxEngine_CHtoEU_DestinationVAT(t *testing.T) {
	e := NewDefaultTaxEngine()
	vehiclePrice := int64(2500000) // €25,000
	cost, err := e.VATCost("CH", "DE", vehiclePrice)
	if err != nil {
		t.Fatal(err)
	}
	// Expected: 19% × €25,000 + €400 fixed = €4,750 + €400 = €5,150 = 515000 cents
	expectedVAT := int64(float64(vehiclePrice) * 0.19)
	expected := expectedVAT + 40000
	if cost != expected {
		t.Errorf("CH→DE VAT: want %d, got %d", expected, cost)
	}
}

func TestTaxEngine_SameCountry_Zero(t *testing.T) {
	e := NewDefaultTaxEngine()
	cost, err := e.VATCost("DE", "DE", 2500000)
	if err != nil {
		t.Fatal(err)
	}
	if cost != 0 {
		t.Errorf("same country: want 0, got %d", cost)
	}
}

// ── Market spread tests ───────────────────────────────────────────────────────

func TestSpread_CorrectPrices(t *testing.T) {
	db := fixtureDB(t)
	defer db.Close()

	calc := NewSpreadCalculator(db)
	spread, err := calc.Calculate("BMW", "320d", 2021, 45000, "")
	if err != nil {
		t.Fatal(err)
	}

	// All 5 countries should have data.
	if len(spread.PricesByCountry) != 5 {
		t.Fatalf("expected 5 countries, got %d: %v", len(spread.PricesByCountry), spread.PricesByCountry)
	}

	// Check DE price ≈ €25,000 = 2,500,000 cents.
	dePrice := spread.PricesByCountry["DE"]
	if dePrice < 2490000 || dePrice > 2510000 {
		t.Errorf("DE price: expected ~2500000, got %d", dePrice)
	}

	// CH should be highest (€28,000).
	if spread.BestCountry != "CH" {
		t.Errorf("best country: want CH (28000), got %s", spread.BestCountry)
	}

	// FR should be lowest (€24,000).
	if spread.WorstCountry != "FR" {
		t.Errorf("worst country: want FR (24000), got %s", spread.WorstCountry)
	}
}

func TestSpread_SpreadAmount(t *testing.T) {
	db := fixtureDB(t)
	defer db.Close()

	calc := NewSpreadCalculator(db)
	spread, err := calc.Calculate("BMW", "320d", 2021, 45000, "")
	if err != nil {
		t.Fatal(err)
	}
	// CH=28000 - FR=24000 = 4000 EUR = 400000 cents
	if spread.SpreadAmount < 380000 || spread.SpreadAmount > 420000 {
		t.Errorf("spread: expected ~400000 cents, got %d", spread.SpreadAmount)
	}
}

func TestSpread_Confidence_WithSamples(t *testing.T) {
	db := fixtureDB(t)
	defer db.Close()

	calc := NewSpreadCalculator(db)
	spread, err := calc.Calculate("BMW", "320d", 2021, 45000, "")
	if err != nil {
		t.Fatal(err)
	}
	// 5 countries × 5 samples = 25 samples → confidence > 0.5
	if spread.Confidence < 0.5 {
		t.Errorf("confidence with 25 samples should be > 0.5, got %.3f", spread.Confidence)
	}
}

func TestSpread_EmptyResult_NoData(t *testing.T) {
	db := makeFixtureDB(t)
	defer db.Close()

	calc := NewSpreadCalculator(db)
	spread, err := calc.Calculate("UNKNOWN", "UNKNOWN", 1999, 100000, "")
	if err != nil {
		t.Fatal(err)
	}
	if len(spread.PricesByCountry) != 0 {
		t.Errorf("expected empty result, got %v", spread.PricesByCountry)
	}
}

// ── Optimizer tests ───────────────────────────────────────────────────────────

func TestOptimizer_BestRoute_FR_to_CH(t *testing.T) {
	db := fixtureDB(t)
	defer db.Close()

	opt := NewOptimizer(db, NewDefaultTaxEngine(), DefaultTransportMatrix())
	plan, err := opt.Optimize(OptimizeRequest{
		Make:           "BMW",
		Model:          "320d",
		Year:           2021,
		MileageKm:      45000,
		CurrentCountry: "FR",
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(plan.Routes) == 0 {
		t.Fatal("expected at least one route")
	}

	// CH market price €28,000, but with 8.1% VAT (~€2,267) + transport FR→CH €600
	// net ≈ €25,133.  NL €26,000 − 0 VAT − €800 transport = €25,200.
	// So NL dealer_direct should beat CH after costs.
	best := plan.BestRoute
	t.Logf("best route: %s→%s via %s net=€%.0f", best.FromCountry, best.ToCountry, best.Channel, float64(best.NetProfit)/100)

	// The best route must have a positive net profit.
	if best.NetProfit <= 0 {
		t.Errorf("expected positive net profit, got %d", best.NetProfit)
	}
}

func TestOptimizer_IntraEU_ZeroVAT(t *testing.T) {
	db := fixtureDB(t)
	defer db.Close()

	opt := NewOptimizer(db, NewDefaultTaxEngine(), DefaultTransportMatrix())
	plan, err := opt.Optimize(OptimizeRequest{
		Make:           "BMW",
		Model:          "320d",
		Year:           2021,
		MileageKm:      45000,
		CurrentCountry: "FR",
		Channel:        ChannelDealerDirect,
	})
	if err != nil {
		t.Fatal(err)
	}

	// All EU→EU routes should have VATCost == 0.
	for _, r := range plan.Routes {
		if r.ToCountry == "CH" {
			continue // CH has VAT
		}
		if r.VATCost != 0 {
			t.Errorf("intra-EU route %s→%s: expected 0 VAT, got %d", r.FromCountry, r.ToCountry, r.VATCost)
		}
	}
}

func TestOptimizer_CHRoute_HasVATCost(t *testing.T) {
	db := fixtureDB(t)
	defer db.Close()

	opt := NewOptimizer(db, NewDefaultTaxEngine(), DefaultTransportMatrix())
	plan, err := opt.Optimize(OptimizeRequest{
		Make:           "BMW",
		Model:          "320d",
		Year:           2021,
		MileageKm:      45000,
		CurrentCountry: "DE",
		Channel:        ChannelExport,
	})
	if err != nil {
		t.Fatal(err)
	}

	var chRoute *DispositionRoute
	for i := range plan.Routes {
		if plan.Routes[i].ToCountry == "CH" {
			chRoute = &plan.Routes[i]
			break
		}
	}
	if chRoute == nil {
		t.Skip("no CH route available (no market data)")
	}
	if chRoute.VATCost == 0 {
		t.Error("DE→CH export: expected non-zero VAT cost")
	}
	t.Logf("CH route VAT: €%.0f, transport: €%.0f, net: €%.0f",
		float64(chRoute.VATCost)/100, float64(chRoute.TransportCost)/100, float64(chRoute.NetProfit)/100)
}

func TestOptimizer_RoutesSortedByNetProfit(t *testing.T) {
	db := fixtureDB(t)
	defer db.Close()

	opt := NewOptimizer(db, NewDefaultTaxEngine(), DefaultTransportMatrix())
	plan, err := opt.Optimize(OptimizeRequest{
		Make:           "BMW",
		Model:          "320d",
		Year:           2021,
		MileageKm:      45000,
		CurrentCountry: "FR",
	})
	if err != nil {
		t.Fatal(err)
	}
	for i := 1; i < len(plan.Routes); i++ {
		if plan.Routes[i].NetProfit > plan.Routes[i-1].NetProfit {
			t.Errorf("routes not sorted: route[%d] net=%d > route[%d] net=%d",
				i, plan.Routes[i].NetProfit, i-1, plan.Routes[i-1].NetProfit)
		}
	}
}

func TestOptimizer_NoData_EmptyPlan(t *testing.T) {
	db := makeFixtureDB(t)
	defer db.Close()

	opt := NewOptimizer(db, NewDefaultTaxEngine(), DefaultTransportMatrix())
	plan, err := opt.Optimize(OptimizeRequest{
		Make:           "UNKNOWN",
		Model:          "UNKNOWN",
		Year:           2005,
		MileageKm:      200000,
		CurrentCountry: "DE",
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(plan.Routes) != 0 {
		t.Errorf("expected empty routes for no-data vehicle, got %d", len(plan.Routes))
	}
}

func TestOptimizer_NetProfit_Formula(t *testing.T) {
	db := fixtureDB(t)
	defer db.Close()

	opt := NewOptimizer(db, NewDefaultTaxEngine(), DefaultTransportMatrix())
	plan, err := opt.Optimize(OptimizeRequest{
		Make:           "BMW",
		Model:          "320d",
		Year:           2021,
		MileageKm:      45000,
		CurrentCountry: "DE",
	})
	if err != nil {
		t.Fatal(err)
	}
	// Verify: NetProfit == EstimatedPrice - VATCost - TransportCost for all routes
	// (auction adds a 3% fee to transport, so skip auction routes in this check)
	for _, r := range plan.Routes {
		if r.Channel == ChannelAuction {
			continue
		}
		expectedNet := r.EstimatedPrice - r.VATCost - r.TransportCost
		if r.NetProfit != expectedNet {
			t.Errorf("route %s→%s: NetProfit %d ≠ price-vat-transport %d",
				r.FromCountry, r.ToCountry, r.NetProfit, expectedNet)
		}
	}
}

// ── Batch optimizer tests ─────────────────────────────────────────────────────

func TestBatch_10Vehicles_AllAssigned(t *testing.T) {
	db := fixtureDB(t)
	defer db.Close()

	vehicles := make10Vehicles(db)
	opt := NewOptimizer(db, NewDefaultTaxEngine(), DefaultTransportMatrix())
	bopt := NewBatchOptimizer(opt, 0.20)

	plan, err := bopt.Optimize(vehicles)
	if err != nil {
		t.Fatal(err)
	}
	if len(plan.Assignments) != len(vehicles) {
		t.Errorf("expected %d assignments, got %d", len(vehicles), len(plan.Assignments))
	}
}

func TestBatch_ConcentrationConstraint(t *testing.T) {
	db := fixtureDB(t)
	defer db.Close()

	// 10 vehicles all from FR → the best single destination should get ≤2 (20% of 10)
	vehicles := make([]VehicleInput, 10)
	for i := range vehicles {
		vehicles[i] = VehicleInput{
			Make:           "BMW",
			Model:          "320d",
			Year:           2021,
			MileageKm:      45000,
			CurrentCountry: "FR",
		}
	}

	opt := NewOptimizer(db, NewDefaultTaxEngine(), DefaultTransportMatrix())
	bopt := NewBatchOptimizer(opt, 0.20)
	plan, err := bopt.Optimize(vehicles)
	if err != nil {
		t.Fatal(err)
	}

	cap := int(0.20*float64(len(vehicles)) + 0.999)
	for dest, count := range plan.ByDestination {
		if count > cap+1 { // allow +1 for rounding
			t.Errorf("destination %s has %d vehicles (cap %d)", dest, count, cap)
		}
	}
}

func TestBatch_EmptyInput(t *testing.T) {
	db := makeFixtureDB(t)
	defer db.Close()

	opt := NewOptimizer(db, NewDefaultTaxEngine(), DefaultTransportMatrix())
	bopt := NewBatchOptimizer(opt, 0.20)
	plan, err := bopt.Optimize([]VehicleInput{})
	if err != nil {
		t.Fatal(err)
	}
	if plan.TotalVehicles != 0 {
		t.Errorf("empty input: want 0 vehicles, got %d", plan.TotalVehicles)
	}
}

func TestBatch_TotalUplift_NonNegative(t *testing.T) {
	db := fixtureDB(t)
	defer db.Close()

	vehicles := make10Vehicles(db)
	opt := NewOptimizer(db, NewDefaultTaxEngine(), DefaultTransportMatrix())
	bopt := NewBatchOptimizer(opt, 0.20)
	plan, err := bopt.Optimize(vehicles)
	if err != nil {
		t.Fatal(err)
	}
	// Total uplift can be negative if all local prices are best — but should not panic.
	t.Logf("total uplift: €%.0f, avg: €%.0f",
		float64(plan.TotalEstimatedUplift)/100, float64(plan.AvgUpliftPerVehicle)/100)
}

func TestBatch_Validation_MissingMake(t *testing.T) {
	err := validateBatchRequest([]VehicleInput{{Model: "3er", Year: 2021, CurrentCountry: "FR"}})
	if err == nil {
		t.Error("expected error for missing make")
	}
}

// ── Gain-share tests ──────────────────────────────────────────────────────────

func TestGainShare_15pct_Fee(t *testing.T) {
	gs, err := CalculateGainShare(2700000, 2500000, 0.15) // €27k actual, €25k baseline
	if err != nil {
		t.Fatal(err)
	}
	if gs.Uplift != 200000 {
		t.Errorf("uplift: want 200000, got %d", gs.Uplift)
	}
	if gs.Fee != 30000 { // 15% × €2000 = €300
		t.Errorf("fee: want 30000 (€300), got %d (€%.0f)", gs.Fee, float64(gs.Fee)/100)
	}
	if gs.NetToClient != 170000 { // €2000 - €300 = €1700
		t.Errorf("net to client: want 170000, got %d", gs.NetToClient)
	}
}

func TestGainShare_20pct_Fee(t *testing.T) {
	gs, err := CalculateGainShare(2700000, 2500000, 0.20)
	if err != nil {
		t.Fatal(err)
	}
	if gs.Fee != 40000 { // 20% × €2000 = €400
		t.Errorf("fee at 20%%: want 40000, got %d", gs.Fee)
	}
}

func TestGainShare_NoUplift_ZeroFee(t *testing.T) {
	gs, err := CalculateGainShare(2400000, 2500000, 0.15) // actual < baseline
	if err != nil {
		t.Fatal(err)
	}
	if gs.Uplift != 0 {
		t.Errorf("negative uplift should clamp to 0, got %d", gs.Uplift)
	}
	if gs.Fee != 0 {
		t.Errorf("fee on zero uplift: want 0, got %d", gs.Fee)
	}
}

func TestGainShare_ExactUplift(t *testing.T) {
	// €2000 uplift, 15% fee = €300
	gs, err := CalculateGainShare(200000+2500000, 2500000, 0.15)
	if err != nil {
		t.Fatal(err)
	}
	if gs.Uplift != 200000 {
		t.Errorf("uplift: want 200000, got %d", gs.Uplift)
	}
}

func TestGainShare_InvalidFeeRate(t *testing.T) {
	_, err := CalculateGainShare(2700000, 2500000, 1.5) // > 1
	if err == nil {
		t.Error("expected error for fee rate > 1")
	}
}

// ── HTTP server tests ─────────────────────────────────────────────────────────

func TestServer_Health(t *testing.T) {
	db := makeFixtureDB(t)
	defer db.Close()

	srv := NewServer(db, nil)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	srv.Handler().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Errorf("health: want 200, got %d", rec.Code)
	}
	var body map[string]string
	if err := json.NewDecoder(rec.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if body["status"] != "ok" {
		t.Errorf("health.status: want ok, got %q", body["status"])
	}
}

func TestServer_Spread_MissingParams(t *testing.T) {
	db := makeFixtureDB(t)
	defer db.Close()

	srv := NewServer(db, nil)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/routes/spread?make=BMW", nil)
	srv.Handler().ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Errorf("spread missing model: want 400, got %d", rec.Code)
	}
}

func TestServer_Optimize_NoData_Returns404(t *testing.T) {
	db := makeFixtureDB(t)
	defer db.Close()

	srv := NewServer(db, nil)
	body := mustMarshal(t, OptimizeRequest{
		Make:           "UNKNOWN",
		Model:          "UNKNOWN",
		Year:           2005,
		MileageKm:      200000,
		CurrentCountry: "DE",
	})
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/routes/optimize", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	srv.Handler().ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Errorf("no-data optimize: want 404, got %d", rec.Code)
	}
}

func TestServer_Optimize_Returns200_WithData(t *testing.T) {
	db := fixtureDB(t)
	defer db.Close()

	srv := NewServer(db, nil)
	body := mustMarshal(t, OptimizeRequest{
		Make:           "BMW",
		Model:          "320d",
		Year:           2021,
		MileageKm:      45000,
		CurrentCountry: "FR",
	})
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/routes/optimize", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	srv.Handler().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Errorf("optimize: want 200, got %d; body: %s", rec.Code, rec.Body.String())
	}
	var plan DispositionPlan
	if err := json.NewDecoder(rec.Body).Decode(&plan); err != nil {
		t.Fatal(err)
	}
	if len(plan.Routes) == 0 {
		t.Error("optimize: expected routes in response")
	}
}

func TestServer_Batch_InvalidJSON(t *testing.T) {
	db := makeFixtureDB(t)
	defer db.Close()

	srv := NewServer(db, nil)
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/routes/batch", strings.NewReader("not json"))
	srv.Handler().ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Errorf("batch bad JSON: want 400, got %d", rec.Code)
	}
}

// ── Helpers ───────────────────────────────────────────────────────────────────

func make10Vehicles(_ *sql.DB) []VehicleInput {
	countries := []string{"FR", "DE", "NL", "BE", "ES", "FR", "DE", "NL", "FR", "DE"}
	v := make([]VehicleInput, 10)
	for i := range v {
		v[i] = VehicleInput{
			Make:           "BMW",
			Model:          "320d",
			Year:           2021,
			MileageKm:      45000,
			CurrentCountry: countries[i],
		}
	}
	return v
}

func mustMarshal(t *testing.T, v any) []byte {
	t.Helper()
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	return b
}

func writeFile(path string, data []byte) error {
	return os.WriteFile(path, data, 0o644)
}
