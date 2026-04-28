package pulse_test

import (
	"context"
	"database/sql"
	"fmt"
	"math"
	"testing"
	"time"

	_ "modernc.org/sqlite"

	"cardex.eu/discovery/internal/pulse"
)

func openTestDB(t *testing.T) *sql.DB {
	t.Helper()
	db, err := sql.Open("sqlite", ":memory:?_pragma=foreign_keys(ON)")
	if err != nil {
		t.Fatalf("open in-memory db: %v", err)
	}
	t.Cleanup(func() { db.Close() })

	_, err = db.Exec(`
		CREATE TABLE dealer_entity (
		  dealer_id        TEXT PRIMARY KEY,
		  canonical_name   TEXT NOT NULL,
		  normalized_name  TEXT NOT NULL,
		  country_code     TEXT NOT NULL,
		  status           TEXT NOT NULL DEFAULT 'UNVERIFIED',
		  confidence_score REAL NOT NULL DEFAULT 0.0,
		  first_discovered_at TIMESTAMP NOT NULL,
		  last_confirmed_at   TIMESTAMP NOT NULL
		);
		CREATE TABLE vehicle_record (
		  vehicle_id        TEXT PRIMARY KEY,
		  dealer_id         TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
		  make_canonical    TEXT,
		  model_canonical   TEXT,
		  price_gross_eur   REAL,
		  confidence_score  REAL,
		  indexed_at        TIMESTAMP NOT NULL,
		  last_confirmed_at TIMESTAMP NOT NULL,
		  ttl_expires_at    TIMESTAMP NOT NULL,
		  status            TEXT NOT NULL DEFAULT 'ACTIVE',
		  source_url        TEXT NOT NULL DEFAULT '',
		  source_platform   TEXT NOT NULL DEFAULT 'test'
		);
		CREATE TABLE dealer_health_history (
		  id           INTEGER PRIMARY KEY AUTOINCREMENT,
		  dealer_id    TEXT NOT NULL REFERENCES dealer_entity(dealer_id),
		  health_score REAL NOT NULL,
		  health_tier  TEXT NOT NULL,
		  signals_json TEXT NOT NULL,
		  computed_at  TEXT NOT NULL
		);
		CREATE INDEX idx_dhh_dealer_time ON dealer_health_history(dealer_id, computed_at);
	`)
	if err != nil {
		t.Fatalf("create schema: %v", err)
	}
	return db
}

func insertDealer(t *testing.T, db *sql.DB, id, name, country string) {
	t.Helper()
	now := time.Now().UTC().Format(time.RFC3339)
	_, err := db.Exec(`
		INSERT INTO dealer_entity (dealer_id, canonical_name, normalized_name, country_code,
		  first_discovered_at, last_confirmed_at)
		VALUES (?,?,?,?,?,?)`, id, name, name, country, now, now)
	if err != nil {
		t.Fatalf("insertDealer: %v", err)
	}
}

func insertVehicle(t *testing.T, db *sql.DB, vid, did, make_ string, price, confidence float64, indexedAt time.Time, status string) {
	t.Helper()
	ttl := indexedAt.AddDate(0, 0, 30).Format(time.RFC3339)
	_, err := db.Exec(`
		INSERT INTO vehicle_record (vehicle_id, dealer_id, make_canonical, price_gross_eur,
		  confidence_score, indexed_at, last_confirmed_at, ttl_expires_at, status)
		VALUES (?,?,?,?,?,?,?,?,?)`,
		vid, did, make_, price, confidence,
		indexedAt.Format(time.RFC3339), indexedAt.Format(time.RFC3339), ttl, status,
	)
	if err != nil {
		t.Fatalf("insertVehicle: %v", err)
	}
}

// ── TierFromScore ──────────────────────────────────────────────────────────────

func TestTierFromScore_Healthy(t *testing.T) {
	if got := pulse.TierFromScore(85); got != pulse.TierHealthy {
		t.Errorf("score 85 → %q, want %q", got, pulse.TierHealthy)
	}
}

func TestTierFromScore_Watch(t *testing.T) {
	if got := pulse.TierFromScore(60); got != pulse.TierWatch {
		t.Errorf("score 60 → %q, want %q", got, pulse.TierWatch)
	}
}

func TestTierFromScore_Stress(t *testing.T) {
	if got := pulse.TierFromScore(40); got != pulse.TierStress {
		t.Errorf("score 40 → %q, want %q", got, pulse.TierStress)
	}
}

func TestTierFromScore_Critical(t *testing.T) {
	if got := pulse.TierFromScore(10); got != pulse.TierCritical {
		t.Errorf("score 10 → %q, want %q", got, pulse.TierCritical)
	}
}

func TestTierFromScore_Boundary70(t *testing.T) {
	if got := pulse.TierFromScore(70); got != pulse.TierHealthy {
		t.Errorf("boundary 70 → %q, want %q", got, pulse.TierHealthy)
	}
	if got := pulse.TierFromScore(69.9); got != pulse.TierWatch {
		t.Errorf("boundary 69.9 → %q, want %q", got, pulse.TierWatch)
	}
}

// ── Score: healthy dealer ──────────────────────────────────────────────────────

func TestScore_HealthyDealer(t *testing.T) {
	s := &pulse.DealerHealthScore{
		LiquidationRatio:    0.8,
		PriceTrend:          2.0,
		VolumeZScore:        0.3,
		AvgTimeOnMarket:     30,
		TimeOnMarketDelta:   5.0,
		CompositeScoreDelta: 2.0,
		BrandHHI:            0.2,
		PriceVsMarket:       1.05,
	}
	pulse.Score(s, pulse.DefaultWeights(), nil)

	if s.HealthScore < 70 {
		t.Errorf("healthy dealer score = %.1f, want >= 70", s.HealthScore)
	}
	if s.HealthTier != pulse.TierHealthy {
		t.Errorf("tier = %q, want %q", s.HealthTier, pulse.TierHealthy)
	}
	if len(s.RiskSignals) != 0 {
		t.Errorf("expected no risk signals, got %v", s.RiskSignals)
	}
}

// ── Score: stressed dealer ─────────────────────────────────────────────────────

func TestScore_StressedDealer(t *testing.T) {
	s := &pulse.DealerHealthScore{
		LiquidationRatio:    2.5,
		PriceTrend:          -12,
		VolumeZScore:        -3.0,
		AvgTimeOnMarket:     90,
		TimeOnMarketDelta:   50,
		CompositeScoreDelta: -25,
		BrandHHI:            0.9,
		PriceVsMarket:       0.60,
	}
	pulse.Score(s, pulse.DefaultWeights(), nil)

	if s.HealthScore >= 30 {
		t.Errorf("stressed dealer score = %.1f, want < 30", s.HealthScore)
	}
	if s.HealthTier != pulse.TierCritical {
		t.Errorf("tier = %q, want %q", s.HealthTier, pulse.TierCritical)
	}
}

// ── BrandHHI ──────────────────────────────────────────────────────────────────

func TestBrandHHI_SingleMake(t *testing.T) {
	db := openTestDB(t)
	insertDealer(t, db, "D1", "Mono", "DE")
	now := time.Now().UTC()
	for i := 0; i < 5; i++ {
		insertVehicle(t, db, fmt.Sprintf("V%d", i), "D1", "BMW", 20000, 0.9, now.AddDate(0, 0, -i), "ACTIVE")
	}
	s, err := pulse.ComputeSignals(context.Background(), db, "D1", now)
	if err != nil {
		t.Fatal(err)
	}
	if math.Abs(s.BrandHHI-1.0) > 0.01 {
		t.Errorf("single-make HHI = %.4f, want 1.0", s.BrandHHI)
	}
}

func TestBrandHHI_FourEqualMakes(t *testing.T) {
	db := openTestDB(t)
	insertDealer(t, db, "D2", "Multi", "DE")
	now := time.Now().UTC()
	for i, mk := range []string{"BMW", "VW", "Audi", "Mercedes"} {
		insertVehicle(t, db, fmt.Sprintf("VM%d", i), "D2", mk, 25000, 0.85, now.AddDate(0, 0, -i), "ACTIVE")
	}
	s, err := pulse.ComputeSignals(context.Background(), db, "D2", now)
	if err != nil {
		t.Fatal(err)
	}
	if math.Abs(s.BrandHHI-0.25) > 0.01 {
		t.Errorf("equal 4-make HHI = %.4f, want 0.25", s.BrandHHI)
	}
}

// ── DetectTrend ───────────────────────────────────────────────────────────────

func TestDetectTrend_Improving(t *testing.T) {
	history := []pulse.HistoryPoint{{HealthScore: 50}, {HealthScore: 55}, {HealthScore: 58}}
	if got := pulse.DetectTrend(history, 70); got != "improving" {
		t.Errorf("got %q, want improving", got)
	}
}

func TestDetectTrend_Deteriorating(t *testing.T) {
	history := []pulse.HistoryPoint{{HealthScore: 80}, {HealthScore: 75}, {HealthScore: 72}}
	if got := pulse.DetectTrend(history, 60); got != "deteriorating" {
		t.Errorf("got %q, want deteriorating", got)
	}
}

func TestDetectTrend_Stable(t *testing.T) {
	history := []pulse.HistoryPoint{{HealthScore: 65}, {HealthScore: 66}}
	if got := pulse.DetectTrend(history, 67); got != "stable" {
		t.Errorf("got %q, want stable", got)
	}
}

func TestDetectTrend_InsufficientHistory(t *testing.T) {
	if got := pulse.DetectTrend(nil, 80); got != "stable" {
		t.Errorf("nil history = %q, want stable", got)
	}
	if got := pulse.DetectTrend([]pulse.HistoryPoint{{HealthScore: 70}}, 80); got != "stable" {
		t.Errorf("1-point history = %q, want stable", got)
	}
}

// ── CollectRiskSignals ────────────────────────────────────────────────────────

func TestCollectRiskSignals_LiquidationPressure(t *testing.T) {
	s := &pulse.DealerHealthScore{LiquidationRatio: 2.0}
	if !sliceContains(pulse.CollectRiskSignals(s), "liquidation_pressure") {
		t.Error("expected liquidation_pressure signal")
	}
}

func TestCollectRiskSignals_PriceErosion(t *testing.T) {
	s := &pulse.DealerHealthScore{PriceTrend: -8}
	if !sliceContains(pulse.CollectRiskSignals(s), "price_erosion") {
		t.Error("expected price_erosion signal")
	}
}

func TestCollectRiskSignals_NoSignals(t *testing.T) {
	s := &pulse.DealerHealthScore{
		LiquidationRatio:    0.5,
		PriceTrend:          1.0,
		VolumeZScore:        0.2,
		TimeOnMarketDelta:   5.0,
		CompositeScoreDelta: 1.0,
		BrandHHI:            0.2,
		PriceVsMarket:       1.1,
	}
	if signals := pulse.CollectRiskSignals(s); len(signals) != 0 {
		t.Errorf("expected no signals, got %v", signals)
	}
}

// ── Storage ───────────────────────────────────────────────────────────────────

func TestEnsureTable_Idempotent(t *testing.T) {
	db := openTestDB(t)
	ctx := context.Background()
	if err := pulse.EnsureTable(ctx, db); err != nil {
		t.Errorf("second call: %v", err)
	}
	if err := pulse.EnsureTable(ctx, db); err != nil {
		t.Errorf("third call: %v", err)
	}
}

func TestSaveAndLoadHistory(t *testing.T) {
	db := openTestDB(t)
	insertDealer(t, db, "DH1", "Test Dealer", "DE")
	ctx := context.Background()

	for i := 0; i < 5; i++ {
		s := &pulse.DealerHealthScore{
			DealerID:    "DH1",
			HealthScore: float64(60 + i),
			HealthTier:  pulse.TierWatch,
			RiskSignals: []string{"liquidation_pressure"},
			ComputedAt:  time.Now().UTC().Add(time.Duration(i) * time.Minute),
		}
		if err := pulse.SaveSnapshot(ctx, db, s); err != nil {
			t.Fatalf("SaveSnapshot %d: %v", i, err)
		}
	}

	history, err := pulse.LoadHistory(ctx, db, "DH1", 0)
	if err != nil {
		t.Fatal(err)
	}
	if len(history) != 5 {
		t.Errorf("loaded %d history points, want 5", len(history))
	}
	if history[0].HealthScore > history[4].HealthScore {
		t.Errorf("history not ordered oldest-first")
	}
}

func TestWatchlist_FiltersCorrectly(t *testing.T) {
	db := openTestDB(t)
	ctx := context.Background()
	insertDealer(t, db, "WD1", "Critical Dealer", "DE")
	insertDealer(t, db, "WD2", "Healthy Dealer", "DE")

	save := func(id string, score float64) {
		s := &pulse.DealerHealthScore{
			DealerID:    id,
			HealthScore: score,
			HealthTier:  pulse.TierFromScore(score),
			RiskSignals: nil,
			ComputedAt:  time.Now().UTC(),
		}
		if err := pulse.SaveSnapshot(ctx, db, s); err != nil {
			t.Fatalf("SaveSnapshot: %v", err)
		}
	}
	save("WD1", 20.0)
	save("WD2", 85.0)

	results, err := pulse.Watchlist(ctx, db, 70.0, "")
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != 1 {
		t.Errorf("watchlist returned %d dealers, want 1", len(results))
	}
	if len(results) > 0 && results[0].DealerID != "WD1" {
		t.Errorf("watchlist returned %q, want WD1", results[0].DealerID)
	}
}

func TestDefaultWeights_SumToOne(t *testing.T) {
	w := pulse.DefaultWeights()
	total := w.Liquidation + w.PriceTrend + w.Volume + w.TimeOnMarket +
		w.CompositeDelta + w.BrandHHI + w.PriceVsMarket
	if math.Abs(total-1.0) > 1e-9 {
		t.Errorf("default weights sum = %.6f, want 1.0", total)
	}
}

func sliceContains(haystack []string, needle string) bool {
	for _, s := range haystack {
		if s == needle {
			return true
		}
	}
	return false
}
