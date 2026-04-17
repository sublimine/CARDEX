package ev_watch

import (
	"context"
	"database/sql"
	"fmt"
	"math/rand"
	"testing"
	"time"

	_ "modernc.org/sqlite"
)

// ── Test helpers ──────────────────────────────────────────────────────────────

func openTestDB(t *testing.T) *sql.DB {
	t.Helper()
	db, err := sql.Open("sqlite", ":memory:?_journal_mode=WAL")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	if _, err := db.Exec(testSchema); err != nil {
		t.Fatalf("create schema: %v", err)
	}
	return db
}

// Minimal subset of discovery schema needed by the analyzer.
const testSchema = `
CREATE TABLE IF NOT EXISTS dealer_entity (
    dealer_id    TEXT PRIMARY KEY,
    country_code TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vehicle_record (
    vehicle_id      TEXT PRIMARY KEY,
    vin             TEXT,
    dealer_id       TEXT NOT NULL,
    make_canonical  TEXT,
    model_canonical TEXT,
    year            INTEGER,
    mileage_km      INTEGER,
    fuel_type       TEXT,
    price_gross_eur REAL,
    price_net_eur   REAL,
    source_url      TEXT NOT NULL DEFAULT 'http://test.example',
    source_platform TEXT NOT NULL DEFAULT 'test',
    indexed_at      TEXT NOT NULL DEFAULT (datetime('now')),
    last_confirmed_at TEXT NOT NULL DEFAULT (datetime('now')),
    ttl_expires_at  TEXT NOT NULL DEFAULT (datetime('now', '+30 days')),
    status          TEXT NOT NULL DEFAULT 'PENDING_REVIEW'
);
`

// insertDealer inserts a dealer_entity row.
func insertDealer(t *testing.T, db *sql.DB, dealerID, country string) {
	t.Helper()
	_, err := db.Exec(`INSERT INTO dealer_entity(dealer_id, country_code) VALUES (?,?)`,
		dealerID, country)
	if err != nil {
		t.Fatalf("insert dealer %s: %v", dealerID, err)
	}
}

// insertEVListing inserts one EV vehicle_record row.
func insertEVListing(t *testing.T, db *sql.DB,
	id, dealerID, make_, model string, year, mileage int, priceEUR float64) {
	t.Helper()
	_, err := db.Exec(`
		INSERT INTO vehicle_record
		    (vehicle_id, vin, dealer_id, make_canonical, model_canonical,
		     year, mileage_km, fuel_type, price_gross_eur)
		VALUES (?,?,?,?,?,?,?,'electric',?)`,
		id, "VIN"+id, dealerID, make_, model, year, mileage, priceEUR)
	if err != nil {
		t.Fatalf("insert listing %s: %v", id, err)
	}
}

// insertNonEVListing inserts a non-electric vehicle_record row.
func insertNonEVListing(t *testing.T, db *sql.DB, id, dealerID string, priceEUR float64) {
	t.Helper()
	_, err := db.Exec(`
		INSERT INTO vehicle_record
		    (vehicle_id, vin, dealer_id, make_canonical, model_canonical,
		     year, mileage_km, fuel_type, price_gross_eur)
		VALUES (?,?,?,'BMW','320d',2021,50000,'diesel',?)`,
		id, "VIN"+id, dealerID, priceEUR)
	if err != nil {
		t.Fatalf("insert non-ev %s: %v", id, err)
	}
}

// seedTeslaModel3Cohort inserts 50 Tesla Model 3 2021 DE listings with a normal
// price distribution around €28,000 ± €2,000 (mileage: 30,000–80,000 km),
// plus n anomalous listings priced 30% below the mean (~€19,600).
func seedTeslaModel3Cohort(t *testing.T, db *sql.DB, normal, anomalous int) {
	t.Helper()
	rng := rand.New(rand.NewSource(42))

	insertDealer(t, db, "D_DE", "DE")

	// Normal listings: price follows a distribution consistent with a downward
	// slope on mileage. Base price €32,000, minus €0.12 per km.
	for i := 0; i < normal; i++ {
		mileage := 30000 + rng.Intn(50000)
		basePrice := 32000.0 - 0.12*float64(mileage)
		noise := (rng.Float64()*2 - 1) * 800 // ±€800 noise
		price := basePrice + noise
		insertEVListing(t, db,
			fmt.Sprintf("TM3-N%03d", i), "D_DE",
			"TESLA", "MODEL 3", 2021, mileage, price)
	}

	// Anomalous listings: same mileage range but price 30% below expected.
	for i := 0; i < anomalous; i++ {
		mileage := 40000 + rng.Intn(20000)
		basePrice := 32000.0 - 0.12*float64(mileage)
		price := basePrice * 0.70 // 30% discount — battery suspect
		insertEVListing(t, db,
			fmt.Sprintf("TM3-A%03d", i), "D_DE",
			"TESLA", "MODEL 3", 2021, mileage, price)
	}
}

// ── Tests ──────────────────────────────────────────────────────────────────────

func TestAnalyzer_FlagsAnomalies(t *testing.T) {
	db := openTestDB(t)
	seedTeslaModel3Cohort(t, db, 50, 3)

	a := NewAnalyzer(db)
	scores, err := a.RunAnalysis(context.Background())
	if err != nil {
		t.Fatalf("RunAnalysis: %v", err)
	}

	if len(scores) != 53 {
		t.Fatalf("want 53 scored listings, got %d", len(scores))
	}

	var flagged int
	for _, s := range scores {
		if s.AnomalyFlag {
			flagged++
			if s.EstimatedSoH == "normal" {
				t.Errorf("anomaly listing %s should not have SoH=normal", s.ListingID)
			}
		}
	}
	if flagged < 3 {
		t.Errorf("want >= 3 anomalies flagged, got %d", flagged)
	}
	// The 3 anomalous listings should all be flagged (priced 30% below cohort mean)
	for i := 0; i < 3; i++ {
		id := fmt.Sprintf("TM3-A%03d", i)
		found := false
		for _, s := range scores {
			if s.ListingID == id && s.AnomalyFlag {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("listing %s should be flagged as anomaly", id)
		}
	}
}

func TestAnalyzer_IgnoresNonEV(t *testing.T) {
	db := openTestDB(t)
	insertDealer(t, db, "D_DE", "DE")
	// Insert only non-EV listings (diesel)
	for i := 0; i < 30; i++ {
		insertNonEVListing(t, db, fmt.Sprintf("BMW-%03d", i), "D_DE", 25000+float64(i)*100)
	}

	a := NewAnalyzer(db)
	scores, err := a.RunAnalysis(context.Background())
	if err != nil {
		t.Fatalf("RunAnalysis: %v", err)
	}
	if len(scores) != 0 {
		t.Errorf("want 0 scores (no EV listings), got %d", len(scores))
	}
}

func TestAnalyzer_SmallCohortSkipped(t *testing.T) {
	db := openTestDB(t)
	insertDealer(t, db, "D_DE", "DE")
	// Only 10 EV listings — below MinCohortSize
	for i := 0; i < 10; i++ {
		insertEVListing(t, db, fmt.Sprintf("EV-%03d", i), "D_DE",
			"POLESTAR", "2", 2022, 30000+i*1000, 32000-float64(i)*200)
	}

	a := NewAnalyzer(db)
	scores, err := a.RunAnalysis(context.Background())
	if err != nil {
		t.Fatalf("RunAnalysis: %v", err)
	}
	if len(scores) != 0 {
		t.Errorf("cohort < %d should be skipped, got %d scores", MinCohortSize, len(scores))
	}
}

func TestAnalyzer_SeverityLevels(t *testing.T) {
	db := openTestDB(t)
	seedTeslaModel3Cohort(t, db, 50, 3)

	a := NewAnalyzer(db)
	scores, err := a.RunAnalysis(context.Background())
	if err != nil {
		t.Fatalf("RunAnalysis: %v", err)
	}

	for _, s := range scores {
		// EstimatedSoH must be one of the three valid values.
		switch s.EstimatedSoH {
		case "normal", "below_average", "suspicious":
		default:
			t.Errorf("unexpected EstimatedSoH %q for listing %s", s.EstimatedSoH, s.ListingID)
		}
		// AnomalyFlag consistency: must match z < -1.5 rule.
		wantFlag := s.ZScore < -1.5
		if s.AnomalyFlag != wantFlag {
			t.Errorf("listing %s: z=%.2f anomaly_flag=%v, want %v",
				s.ListingID, s.ZScore, s.AnomalyFlag, wantFlag)
		}
		// SoH consistency
		switch {
		case s.ZScore < -2.0 && s.EstimatedSoH != "suspicious":
			t.Errorf("listing %s z=%.2f: want suspicious, got %s", s.ListingID, s.ZScore, s.EstimatedSoH)
		case s.ZScore >= -2.0 && s.ZScore < -1.5 && s.EstimatedSoH != "below_average":
			t.Errorf("listing %s z=%.2f: want below_average, got %s", s.ListingID, s.ZScore, s.EstimatedSoH)
		case s.ZScore >= -1.5 && s.EstimatedSoH != "normal":
			t.Errorf("listing %s z=%.2f: want normal, got %s", s.ListingID, s.ZScore, s.EstimatedSoH)
		}
	}
}

func TestAnalyzer_CohortSizeExactlyMinimum(t *testing.T) {
	db := openTestDB(t)
	insertDealer(t, db, "D_DE", "DE")
	// Exactly MinCohortSize listings — should be analysed.
	for i := 0; i < MinCohortSize; i++ {
		insertEVListing(t, db, fmt.Sprintf("MIN-%03d", i), "D_DE",
			"HYUNDAI", "IONIQ 5", 2022, 20000+i*1500, 38000-float64(i)*300)
	}
	a := NewAnalyzer(db)
	scores, err := a.RunAnalysis(context.Background())
	if err != nil {
		t.Fatalf("RunAnalysis: %v", err)
	}
	if len(scores) != MinCohortSize {
		t.Errorf("want %d scores at minimum cohort, got %d", MinCohortSize, len(scores))
	}
}

func TestAnalyzer_UpsertIdempotent(t *testing.T) {
	db := openTestDB(t)
	seedTeslaModel3Cohort(t, db, 30, 0)

	a := NewAnalyzer(db)
	// Run twice — second run should update, not duplicate.
	if _, err := a.RunAnalysis(context.Background()); err != nil {
		t.Fatalf("first run: %v", err)
	}
	if _, err := a.RunAnalysis(context.Background()); err != nil {
		t.Fatalf("second run: %v", err)
	}

	var count int
	db.QueryRow(`SELECT COUNT(*) FROM ev_anomaly_scores`).Scan(&count) //nolint:errcheck
	if count != 30 {
		t.Errorf("want 30 rows after two runs, got %d", count)
	}
}

func TestAnalyzer_ConfidenceRange(t *testing.T) {
	db := openTestDB(t)
	seedTeslaModel3Cohort(t, db, 40, 0)

	a := NewAnalyzer(db)
	scores, err := a.RunAnalysis(context.Background())
	if err != nil {
		t.Fatalf("RunAnalysis: %v", err)
	}

	for _, s := range scores {
		if s.Confidence < 0 || s.Confidence > 1 {
			t.Errorf("listing %s: confidence %.3f out of [0,1]", s.ListingID, s.Confidence)
		}
	}
}

func TestAnalyzer_MultipleCountries(t *testing.T) {
	db := openTestDB(t)
	insertDealer(t, db, "D_DE", "DE")
	insertDealer(t, db, "D_FR", "FR")

	rng := rand.New(rand.NewSource(99))
	// 25 DE listings
	for i := 0; i < 25; i++ {
		mileage := 20000 + rng.Intn(60000)
		price := 30000.0 - 0.10*float64(mileage) + (rng.Float64()*2-1)*500
		insertEVListing(t, db, fmt.Sprintf("DE-%03d", i), "D_DE",
			"VW", "ID.4", 2022, mileage, price)
	}
	// 25 FR listings (different cohort country)
	for i := 0; i < 25; i++ {
		mileage := 20000 + rng.Intn(60000)
		price := 29000.0 - 0.10*float64(mileage) + (rng.Float64()*2-1)*500
		insertEVListing(t, db, fmt.Sprintf("FR-%03d", i), "D_FR",
			"VW", "ID.4", 2022, mileage, price)
	}

	a := NewAnalyzer(db)
	scores, err := a.RunAnalysis(context.Background())
	if err != nil {
		t.Fatalf("RunAnalysis: %v", err)
	}
	// Both cohorts should produce 25 scored listings each.
	if len(scores) != 50 {
		t.Errorf("want 50 scores (2 countries × 25), got %d", len(scores))
	}
}

// ── OLS regression unit tests ─────────────────────────────────────────────────

func TestOLSRegression_PerfectLine(t *testing.T) {
	// y = 2x + 5
	x := []float64{0, 1, 2, 3, 4, 5}
	y := make([]float64, len(x))
	for i := range x {
		y[i] = 2*x[i] + 5
	}
	slope, intercept := olsRegression(x, y)
	if abs(slope-2.0) > 1e-9 {
		t.Errorf("slope: want 2.0, got %.6f", slope)
	}
	if abs(intercept-5.0) > 1e-9 {
		t.Errorf("intercept: want 5.0, got %.6f", intercept)
	}
}

func TestOLSRegression_ConstantX(t *testing.T) {
	// All x equal — regression falls back to mean(y).
	x := []float64{1, 1, 1, 1}
	y := []float64{10, 20, 30, 40}
	slope, intercept := olsRegression(x, y)
	if abs(slope) > 1e-9 {
		t.Errorf("slope: want 0, got %.6f", slope)
	}
	if abs(intercept-25.0) > 1e-9 {
		t.Errorf("intercept: want 25.0 (mean), got %.6f", intercept)
	}
}

func TestMeanAndStddev(t *testing.T) {
	v := []float64{2, 4, 4, 4, 5, 5, 7, 9}
	m := mean(v)
	if abs(m-5.0) > 1e-9 {
		t.Errorf("mean: want 5.0, got %.6f", m)
	}
	s := stddev(v, m)
	// Population std dev of this set is 2.0
	if abs(s-2.0) > 1e-9 {
		t.Errorf("stddev: want 2.0, got %.6f", s)
	}
}

func TestCohortConfidence(t *testing.T) {
	cases := []struct{ n int; want float64 }{
		{20, 0.20},
		{50, 0.50},
		{100, 1.00},
		{150, 1.00},
	}
	for _, c := range cases {
		got := cohortConfidence(c.n)
		if abs(got-c.want) > 1e-9 {
			t.Errorf("cohortConfidence(%d): want %.2f, got %.4f", c.n, c.want, got)
		}
	}
}

func TestEstimateSoH(t *testing.T) {
	cases := []struct{ z float64; want string }{
		{0.5, "normal"},
		{-1.0, "normal"},
		{-1.5, "normal"},   // exactly at boundary — still normal
		{-1.51, "below_average"},
		{-1.9, "below_average"},
		{-2.0, "below_average"}, // boundary is exclusive: z < -2.0 for suspicious
		{-3.0, "suspicious"},
	}
	for _, c := range cases {
		got := estimateSoH(c.z)
		if got != c.want {
			t.Errorf("estimateSoH(%.2f): want %s, got %s", c.z, c.want, got)
		}
	}
}

// ── Schema test ───────────────────────────────────────────────────────────────

func TestEnsureSchema_Idempotent(t *testing.T) {
	db, err := sql.Open("sqlite", ":memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if err := EnsureSchema(db); err != nil {
		t.Fatalf("first call: %v", err)
	}
	if err := EnsureSchema(db); err != nil {
		t.Fatalf("second call: %v", err)
	}
}

// ── Performance / timing ──────────────────────────────────────────────────────

func TestAnalyzer_DetectedAtSet(t *testing.T) {
	db := openTestDB(t)
	seedTeslaModel3Cohort(t, db, 25, 0)

	before := time.Now().Add(-time.Second)
	a := NewAnalyzer(db)
	scores, err := a.RunAnalysis(context.Background())
	if err != nil {
		t.Fatalf("RunAnalysis: %v", err)
	}
	after := time.Now().Add(time.Second)

	for _, s := range scores {
		if s.DetectedAt.Before(before) || s.DetectedAt.After(after) {
			t.Errorf("listing %s: DetectedAt %v outside expected window", s.ListingID, s.DetectedAt)
		}
	}
}

func abs(x float64) float64 {
	if x < 0 {
		return -x
	}
	return x
}
