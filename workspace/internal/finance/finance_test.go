package finance

import (
	"bytes"
	"database/sql"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	_ "modernc.org/sqlite"
)

// ── helpers ───────────────────────────────────────────────────────────────────

func newTestDB(t *testing.T) *sql.DB {
	t.Helper()
	db, err := sql.Open("sqlite", fmt.Sprintf("file:%s?mode=memory&cache=shared", t.Name()))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	db.SetMaxOpenConns(1)
	if err := EnsureSchema(db); err != nil {
		t.Fatalf("schema: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	return db
}

const testTenant = "tenant-test"
const testVehicle = "vehicle-001"

func mustCreate(t *testing.T, s *Store, vehicleID string, typ TransactionType, cents int64, date string) *Transaction {
	t.Helper()
	tx, err := s.Create(testTenant, vehicleID, CreateTransactionRequest{
		Type:        typ,
		AmountCents: cents,
		Currency:    "EUR",
		Date:        date,
	})
	if err != nil {
		t.Fatalf("create tx: %v", err)
	}
	return tx
}

// ── Group 1: Transaction CRUD ─────────────────────────────────────────────────

func TestCreateTransaction_Defaults(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	tx, err := s.Create(testTenant, testVehicle, CreateTransactionRequest{
		Type:        TxPurchase,
		AmountCents: 2000000, // 20 000.00 EUR
	})
	if err != nil {
		t.Fatalf("Create: %v", err)
	}
	if tx.Currency != "EUR" {
		t.Errorf("expected default currency EUR, got %q", tx.Currency)
	}
	if tx.Date == "" {
		t.Error("expected date to default to today")
	}
	if tx.TenantID != testTenant {
		t.Errorf("tenant mismatch: %q", tx.TenantID)
	}
}

func TestCreateTransaction_InvalidType(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	_, err := s.Create(testTenant, testVehicle, CreateTransactionRequest{
		Type:        "invalid_type",
		AmountCents: 1000,
	})
	if err == nil {
		t.Fatal("expected error for invalid type")
	}
}

func TestCreateTransaction_ZeroAmount(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	_, err := s.Create(testTenant, testVehicle, CreateTransactionRequest{
		Type:        TxPurchase,
		AmountCents: 0,
	})
	if err == nil {
		t.Fatal("expected error for zero amount")
	}
}

func TestListByVehicle_Empty(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	txs, err := s.ListByVehicle(testTenant, "no-such-vehicle")
	if err != nil {
		t.Fatalf("ListByVehicle: %v", err)
	}
	if len(txs) != 0 {
		t.Errorf("expected 0 transactions, got %d", len(txs))
	}
}

func TestListByVehicle_ReturnsSortedByDate(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	mustCreate(t, s, testVehicle, TxPurchase, 2000000, "2026-01-15")
	mustCreate(t, s, testVehicle, TxTransport, 30000, "2026-01-10")
	mustCreate(t, s, testVehicle, TxSale, 2500000, "2026-03-01")

	txs, err := s.ListByVehicle(testTenant, testVehicle)
	if err != nil {
		t.Fatalf("ListByVehicle: %v", err)
	}
	if len(txs) != 3 {
		t.Fatalf("expected 3 txs, got %d", len(txs))
	}
	// transport (Jan 10) must come before purchase (Jan 15)
	if txs[0].Date > txs[1].Date {
		t.Errorf("not sorted by date asc: %q > %q", txs[0].Date, txs[1].Date)
	}
}

func TestUpdateTransaction_Success(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	orig := mustCreate(t, s, testVehicle, TxPurchase, 2000000, "2026-01-15")

	updated, err := s.Update(testTenant, orig.ID, CreateTransactionRequest{
		Type:        TxPurchase,
		AmountCents: 1900000,
		Currency:    "EUR",
		Date:        "2026-01-15",
		Notes:       "price renegotiated",
	})
	if err != nil {
		t.Fatalf("Update: %v", err)
	}
	if updated.AmountCents != 1900000 {
		t.Errorf("expected 1900000, got %d", updated.AmountCents)
	}
	if updated.Notes != "price renegotiated" {
		t.Errorf("notes not updated: %q", updated.Notes)
	}
}

func TestUpdateTransaction_NotFound(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	_, err := s.Update(testTenant, "nonexistent-id", CreateTransactionRequest{
		Type: TxPurchase, AmountCents: 1000, Currency: "EUR",
	})
	if err == nil {
		t.Fatal("expected not-found error")
	}
}

func TestDeleteTransaction_Success(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	tx := mustCreate(t, s, testVehicle, TxPurchase, 2000000, "2026-01-15")
	if err := s.Delete(testTenant, tx.ID); err != nil {
		t.Fatalf("Delete: %v", err)
	}
	txs, _ := s.ListByVehicle(testTenant, testVehicle)
	if len(txs) != 0 {
		t.Errorf("expected empty list after delete, got %d", len(txs))
	}
}

// ── Group 2: Vehicle P&L ──────────────────────────────────────────────────────

func TestVehiclePnL_NoTransactions(t *testing.T) {
	pnl := computeVehiclePnL(testTenant, "empty-vehicle", nil, nil)
	if pnl.TotalCostCents != 0 || pnl.TotalRevCents != 0 {
		t.Errorf("expected zero P&L for empty vehicle")
	}
	if pnl.DaysInStock != 0 {
		t.Errorf("expected 0 days in stock")
	}
}

func TestVehiclePnL_CostOnly(t *testing.T) {
	txs := []Transaction{
		{Type: TxPurchase, AmountCents: 2000000, Currency: "EUR", Date: "2026-01-01"},
		{Type: TxTransport, AmountCents: 50000, Currency: "EUR", Date: "2026-01-03"},
	}
	pnl := computeVehiclePnL(testTenant, testVehicle, txs, nil)
	if pnl.TotalCostCents != 2050000 {
		t.Errorf("expected 2050000 cost, got %d", pnl.TotalCostCents)
	}
	if pnl.TotalRevCents != 0 {
		t.Errorf("expected 0 revenue")
	}
	if pnl.GrossMarginCents != -2050000 {
		t.Errorf("expected margin −2050000, got %d", pnl.GrossMarginCents)
	}
}

func TestVehiclePnL_PositiveMargin(t *testing.T) {
	txs := []Transaction{
		{Type: TxPurchase, AmountCents: 2000000, Currency: "EUR", Date: "2026-01-01"},
		{Type: TxReconditioning, AmountCents: 100000, Currency: "EUR", Date: "2026-01-10"},
		{Type: TxSale, AmountCents: 2500000, Currency: "EUR", Date: "2026-02-01"},
	}
	pnl := computeVehiclePnL(testTenant, testVehicle, txs, nil)
	if pnl.TotalCostCents != 2100000 {
		t.Errorf("expected cost 2100000, got %d", pnl.TotalCostCents)
	}
	if pnl.TotalRevCents != 2500000 {
		t.Errorf("expected revenue 2500000, got %d", pnl.TotalRevCents)
	}
	if pnl.GrossMarginCents != 400000 {
		t.Errorf("expected margin 400000, got %d", pnl.GrossMarginCents)
	}
	wantMarginPct := float64(400000) / float64(2500000) * 100
	if pnl.MarginPct < wantMarginPct-0.01 || pnl.MarginPct > wantMarginPct+0.01 {
		t.Errorf("expected margin %% %.2f, got %.2f", wantMarginPct, pnl.MarginPct)
	}
}

func TestVehiclePnL_NegativeMargin(t *testing.T) {
	txs := []Transaction{
		{Type: TxPurchase, AmountCents: 2000000, Currency: "EUR", Date: "2026-01-01"},
		{Type: TxSale, AmountCents: 1800000, Currency: "EUR", Date: "2026-02-01"},
	}
	pnl := computeVehiclePnL(testTenant, testVehicle, txs, nil)
	if pnl.GrossMarginCents != -200000 {
		t.Errorf("expected negative margin −200000, got %d", pnl.GrossMarginCents)
	}
	if pnl.MarginPct >= 0 {
		t.Errorf("expected negative margin %%, got %.2f", pnl.MarginPct)
	}
}

func TestVehiclePnL_DaysInStock(t *testing.T) {
	purchaseDate := "2026-01-01"
	saleDate := "2026-02-01" // 31 days later
	txs := []Transaction{
		{Type: TxPurchase, AmountCents: 2000000, Currency: "EUR", Date: purchaseDate},
		{Type: TxSale, AmountCents: 2200000, Currency: "EUR", Date: saleDate},
	}
	pnl := computeVehiclePnL(testTenant, testVehicle, txs, nil)
	if pnl.DaysInStock != 31 {
		t.Errorf("expected 31 days in stock, got %d", pnl.DaysInStock)
	}
}

func TestVehiclePnL_ROIPct(t *testing.T) {
	txs := []Transaction{
		{Type: TxPurchase, AmountCents: 1000000, Currency: "EUR", Date: "2026-01-01"},
		{Type: TxSale, AmountCents: 1200000, Currency: "EUR", Date: "2026-02-01"},
	}
	pnl := computeVehiclePnL(testTenant, testVehicle, txs, nil)
	// ROI = 200000 / 1000000 * 100 = 20%
	if pnl.ROIPct < 19.99 || pnl.ROIPct > 20.01 {
		t.Errorf("expected ROI 20%%, got %.2f", pnl.ROIPct)
	}
}

func TestVehiclePnL_MultiCurrency(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	// CHF 1.00 = EUR 1.05
	_ = s.UpsertExchangeRate(ExchangeRate{FromCurrency: "CHF", ToCurrency: "EUR", Rate: 1.05, ValidFrom: "2026-01-01"})

	txs := []Transaction{
		{Type: TxPurchase, AmountCents: 100000, Currency: "CHF", Date: "2026-01-05"},
		{Type: TxSale, AmountCents: 200000, Currency: "EUR", Date: "2026-02-01"},
	}
	rf := func(from, date string) (float64, error) { return s.GetExchangeRate(from, "EUR", date) }
	pnl := computeVehiclePnL(testTenant, testVehicle, txs, rf)
	// CHF 100000 * 1.05 = EUR 105000
	if pnl.TotalCostCents != 105000 {
		t.Errorf("expected cost 105000 EUR, got %d", pnl.TotalCostCents)
	}
	if pnl.GrossMarginCents != 200000-105000 {
		t.Errorf("expected margin 95000, got %d", pnl.GrossMarginCents)
	}
}

// ── Group 3: Fleet P&L ────────────────────────────────────────────────────────

func TestFleetPnL_MultipleVehicles(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	calc := NewCalculator(s)

	mustCreate(t, s, "v1", TxPurchase, 2000000, "2026-01-01")
	mustCreate(t, s, "v1", TxSale, 2300000, "2026-02-01")
	mustCreate(t, s, "v2", TxPurchase, 1500000, "2026-01-15")
	mustCreate(t, s, "v2", TxSale, 1700000, "2026-02-15")

	pnl, err := calc.CalculateFleetPnL(testTenant, "2026-01-01", "2026-03-01")
	if err != nil {
		t.Fatalf("FleetPnL: %v", err)
	}
	if pnl.VehicleCount != 2 {
		t.Errorf("expected 2 vehicles, got %d", pnl.VehicleCount)
	}
	if pnl.TotalCostCents != 3500000 {
		t.Errorf("expected total cost 3500000, got %d", pnl.TotalCostCents)
	}
	if pnl.TotalRevCents != 4000000 {
		t.Errorf("expected total revenue 4000000, got %d", pnl.TotalRevCents)
	}
	if pnl.GrossMarginCents != 500000 {
		t.Errorf("expected gross margin 500000, got %d", pnl.GrossMarginCents)
	}
}

func TestFleetPnL_BestWorstVehicle(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	calc := NewCalculator(s)

	// v1: margin = +300000
	mustCreate(t, s, "v1", TxPurchase, 2000000, "2026-01-01")
	mustCreate(t, s, "v1", TxSale, 2300000, "2026-02-01")
	// v2: margin = −200000 (loss)
	mustCreate(t, s, "v2", TxPurchase, 1500000, "2026-01-01")
	mustCreate(t, s, "v2", TxSale, 1300000, "2026-02-01")

	pnl, _ := calc.CalculateFleetPnL(testTenant, "2026-01-01", "2026-03-01")
	if pnl.BestVehicleID != "v1" {
		t.Errorf("expected best=v1, got %q", pnl.BestVehicleID)
	}
	if pnl.WorstVehicleID != "v2" {
		t.Errorf("expected worst=v2, got %q", pnl.WorstVehicleID)
	}
	if pnl.BestMarginCents != 300000 {
		t.Errorf("expected best margin 300000, got %d", pnl.BestMarginCents)
	}
}

func TestFleetPnL_CostByType(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	calc := NewCalculator(s)

	mustCreate(t, s, "v1", TxPurchase, 2000000, "2026-01-01")
	mustCreate(t, s, "v1", TxTransport, 50000, "2026-01-05")
	mustCreate(t, s, "v1", TxReconditioning, 100000, "2026-01-10")

	pnl, _ := calc.CalculateFleetPnL(testTenant, "2026-01-01", "2026-03-01")
	if pnl.CostByType["purchase"] != 2000000 {
		t.Errorf("purchase cost: expected 2000000, got %d", pnl.CostByType["purchase"])
	}
	if pnl.CostByType["transport"] != 50000 {
		t.Errorf("transport cost: expected 50000, got %d", pnl.CostByType["transport"])
	}
	if pnl.CostByType["reconditioning"] != 100000 {
		t.Errorf("reconditioning cost: expected 100000, got %d", pnl.CostByType["reconditioning"])
	}
}

func TestFleetPnL_EmptyRange(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	calc := NewCalculator(s)
	pnl, err := calc.CalculateFleetPnL(testTenant, "2020-01-01", "2020-01-31")
	if err != nil {
		t.Fatalf("FleetPnL empty: %v", err)
	}
	if pnl.VehicleCount != 0 {
		t.Errorf("expected 0 vehicles")
	}
	if pnl.GrossMarginCents != 0 {
		t.Errorf("expected 0 margin")
	}
}

// ── Group 4: Monthly P&L ──────────────────────────────────────────────────────

func TestMonthlyPnL_Basic(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	calc := NewCalculator(s)

	mustCreate(t, s, "v1", TxPurchase, 2000000, "2026-03-01")
	mustCreate(t, s, "v1", TxSale, 2400000, "2026-03-20")

	mp, err := calc.CalculateMonthlyPnL(testTenant, 2026, 3)
	if err != nil {
		t.Fatalf("MonthlyPnL: %v", err)
	}
	if mp.TotalCostCents != 2000000 {
		t.Errorf("cost: expected 2000000, got %d", mp.TotalCostCents)
	}
	if mp.TotalRevCents != 2400000 {
		t.Errorf("rev: expected 2400000, got %d", mp.TotalRevCents)
	}
	if mp.GrossMarginCents != 400000 {
		t.Errorf("margin: expected 400000, got %d", mp.GrossMarginCents)
	}
}

func TestMonthlyPnL_WithPreviousMonth(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	calc := NewCalculator(s)

	// February
	mustCreate(t, s, "v1", TxPurchase, 1500000, "2026-02-01")
	mustCreate(t, s, "v1", TxSale, 1800000, "2026-02-15")
	// March
	mustCreate(t, s, "v2", TxPurchase, 2000000, "2026-03-01")
	mustCreate(t, s, "v2", TxSale, 2500000, "2026-03-20")

	mp, _ := calc.CalculateMonthlyPnL(testTenant, 2026, 3)
	if mp.PrevTotalRevCents != 1800000 {
		t.Errorf("prev rev: expected 1800000, got %d", mp.PrevTotalRevCents)
	}
	if mp.PrevGrossMarginCents != 300000 {
		t.Errorf("prev margin: expected 300000, got %d", mp.PrevGrossMarginCents)
	}
}

func TestMonthlyPnL_GrowthRate(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	calc := NewCalculator(s)

	mustCreate(t, s, "v1", TxSale, 1000000, "2026-02-15") // prev month revenue = 1M
	mustCreate(t, s, "v2", TxSale, 1500000, "2026-03-15") // curr month revenue = 1.5M

	mp, _ := calc.CalculateMonthlyPnL(testTenant, 2026, 3)
	// RevGrowthPct = (1500000 - 1000000) / 1000000 * 100 = 50%
	if mp.RevGrowthPct < 49.9 || mp.RevGrowthPct > 50.1 {
		t.Errorf("expected revenue growth 50%%, got %.2f", mp.RevGrowthPct)
	}
}

func TestMonthlyPnL_EmptyMonth(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	calc := NewCalculator(s)
	mp, err := calc.CalculateMonthlyPnL(testTenant, 2020, 6)
	if err != nil {
		t.Fatalf("MonthlyPnL empty: %v", err)
	}
	if mp.TotalRevCents != 0 || mp.GrossMarginCents != 0 {
		t.Error("expected zero P&L for empty month")
	}
}

// ── Group 5: Alerts ───────────────────────────────────────────────────────────

func TestAlerts_NegativeMargin(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	alertSvc := NewAlertService(s)

	today := time.Now().Format("2006-01-02")
	mustCreate(t, s, "v-neg", TxPurchase, 2000000, today)
	mustCreate(t, s, "v-neg", TxSale, 1500000, today)

	alerts, err := alertSvc.GetAlerts(testTenant)
	if err != nil {
		t.Fatalf("GetAlerts: %v", err)
	}
	found := false
	for _, a := range alerts {
		if a.VehicleID == "v-neg" && a.Type == AlertNegativeMargin {
			found = true
			if a.Severity != "critical" {
				t.Errorf("expected critical severity, got %q", a.Severity)
			}
		}
	}
	if !found {
		t.Error("expected AlertNegativeMargin for vehicle with negative margin")
	}
}

func TestAlerts_StockTooLong(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	alertSvc := NewAlertService(s)

	// Purchase 70 days ago, no sale
	oldDate := time.Now().AddDate(0, 0, -70).Format("2006-01-02")
	mustCreate(t, s, "v-old", TxPurchase, 2000000, oldDate)

	alerts, err := alertSvc.GetAlerts(testTenant)
	if err != nil {
		t.Fatalf("GetAlerts: %v", err)
	}
	found := false
	for _, a := range alerts {
		if a.VehicleID == "v-old" && a.Type == AlertStockTooLong {
			found = true
		}
	}
	if !found {
		t.Error("expected AlertStockTooLong for vehicle in stock 70 days")
	}
}

func TestAlerts_ReconditioningHigh(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	alertSvc := NewAlertService(s)

	today := time.Now().Format("2006-01-02")
	mustCreate(t, s, "v-recond", TxPurchase, 1000000, today) // purchase 10 000 EUR
	mustCreate(t, s, "v-recond", TxReconditioning, 200000, today) // 20% of purchase → above 15%

	alerts, err := alertSvc.GetAlerts(testTenant)
	if err != nil {
		t.Fatalf("GetAlerts: %v", err)
	}
	found := false
	for _, a := range alerts {
		if a.VehicleID == "v-recond" && a.Type == AlertReconditioningHigh {
			found = true
		}
	}
	if !found {
		t.Error("expected AlertReconditioningHigh for reconditioning > 15% of purchase")
	}
}

func TestAlerts_NoAlerts(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	alertSvc := NewAlertService(s)

	today := time.Now().Format("2006-01-02")
	// healthy vehicle: purchase + low reconditioning + good sale
	mustCreate(t, s, "v-ok", TxPurchase, 2000000, today)
	mustCreate(t, s, "v-ok", TxReconditioning, 100000, today) // 5% — below threshold
	mustCreate(t, s, "v-ok", TxSale, 2500000, today)          // positive margin

	alerts, _ := alertSvc.GetAlerts(testTenant)
	for _, a := range alerts {
		if a.VehicleID == "v-ok" {
			t.Errorf("unexpected alert for healthy vehicle: type=%s", a.Type)
		}
	}
}

// ── Group 6: Exchange Rates ───────────────────────────────────────────────────

func TestExchangeRate_Upsert(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	if err := s.UpsertExchangeRate(ExchangeRate{
		FromCurrency: "CHF", ToCurrency: "EUR", Rate: 1.05, ValidFrom: "2026-01-01",
	}); err != nil {
		t.Fatalf("UpsertExchangeRate: %v", err)
	}
	rate, err := s.GetExchangeRate("CHF", "EUR", "2026-06-01")
	if err != nil {
		t.Fatalf("GetExchangeRate: %v", err)
	}
	if rate < 1.04 || rate > 1.06 {
		t.Errorf("expected rate ~1.05, got %v", rate)
	}
}

func TestExchangeRate_FallbackNoRate(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	rate, err := s.GetExchangeRate("GBP", "EUR", "2026-01-01")
	if err != nil {
		t.Fatalf("GetExchangeRate fallback: %v", err)
	}
	if rate != 1.0 {
		t.Errorf("expected fallback rate 1.0, got %v", rate)
	}
}

func TestExchangeRate_SameCurrency(t *testing.T) {
	db := newTestDB(t)
	s := NewStore(db)
	rate, err := s.GetExchangeRate("EUR", "EUR", "2026-01-01")
	if err != nil {
		t.Fatalf("same-currency rate: %v", err)
	}
	if rate != 1.0 {
		t.Errorf("expected 1.0 for same currency, got %v", rate)
	}
}

// ── Group 7: HTTP handlers ────────────────────────────────────────────────────

func newTestHandler(t *testing.T) (http.Handler, *Store) {
	t.Helper()
	db := newTestDB(t)
	s := NewStore(db)
	calc := NewCalculator(s)
	alertSvc := NewAlertService(s)
	return Handler(s, calc, alertSvc), s
}

func TestHTTP_CreateAndListTx(t *testing.T) {
	h, _ := newTestHandler(t)

	body := `{"type":"purchase","amount_cents":2000000,"currency":"EUR","date":"2026-01-01"}`
	req := httptest.NewRequest(http.MethodPost, "/api/v1/vehicles/v1/transactions", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Tenant-ID", testTenant)
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != http.StatusCreated {
		t.Fatalf("create tx: expected 201, got %d — %s", rr.Code, rr.Body.String())
	}

	req2 := httptest.NewRequest(http.MethodGet, "/api/v1/vehicles/v1/transactions", nil)
	req2.Header.Set("X-Tenant-ID", testTenant)
	rr2 := httptest.NewRecorder()
	h.ServeHTTP(rr2, req2)
	if rr2.Code != http.StatusOK {
		t.Fatalf("list tx: expected 200, got %d", rr2.Code)
	}
	var txs []Transaction
	if err := json.NewDecoder(rr2.Body).Decode(&txs); err != nil {
		t.Fatalf("decode list: %v", err)
	}
	if len(txs) != 1 {
		t.Errorf("expected 1 transaction, got %d", len(txs))
	}
}

func TestHTTP_VehiclePnL(t *testing.T) {
	h, s := newTestHandler(t)
	mustCreate(t, s, "v-pnl", TxPurchase, 2000000, "2026-01-01")
	mustCreate(t, s, "v-pnl", TxSale, 2500000, "2026-02-01")

	req := httptest.NewRequest(http.MethodGet, "/api/v1/vehicles/v-pnl/pnl", nil)
	req.Header.Set("X-Tenant-ID", testTenant)
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("vehicle pnl: expected 200, got %d — %s", rr.Code, rr.Body.String())
	}
	var pnl VehiclePnL
	if err := json.NewDecoder(rr.Body).Decode(&pnl); err != nil {
		t.Fatalf("decode pnl: %v", err)
	}
	if pnl.GrossMarginCents != 500000 {
		t.Errorf("expected margin 500000, got %d", pnl.GrossMarginCents)
	}
}

func TestHTTP_Alerts(t *testing.T) {
	h, s := newTestHandler(t)
	today := time.Now().Format("2006-01-02")
	mustCreate(t, s, "v-loss", TxPurchase, 2000000, today)
	mustCreate(t, s, "v-loss", TxSale, 1800000, today)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/fleet/alerts", nil)
	req.Header.Set("X-Tenant-ID", testTenant)
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("alerts: expected 200, got %d", rr.Code)
	}
	var alerts []Alert
	if err := json.NewDecoder(rr.Body).Decode(&alerts); err != nil {
		t.Fatalf("decode alerts: %v", err)
	}
	found := false
	for _, a := range alerts {
		if a.Type == AlertNegativeMargin {
			found = true
		}
	}
	if !found {
		t.Error("expected at least one negative margin alert")
	}
}
