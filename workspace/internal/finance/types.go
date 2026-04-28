// Package finance implements per-vehicle P&L tracking for CARDEX Workspace.
// It manages financial transactions, computes gross margins / ROI, and generates
// fleet-level P&L aggregates and automatic financial alerts.
package finance

import "time"

// TransactionType enumerates every category of financial event on a vehicle.
type TransactionType string

const (
	TxPurchase       TransactionType = "purchase"
	TxSale           TransactionType = "sale"
	TxTransport      TransactionType = "transport"
	TxReconditioning TransactionType = "reconditioning"
	TxInspection     TransactionType = "inspection"
	TxRegistration   TransactionType = "registration"
	TxInsurance      TransactionType = "insurance"
	TxStorage        TransactionType = "storage"
	TxSyndicationFee TransactionType = "syndication_fee"
	TxPlatformFee    TransactionType = "platform_fee"
	TxTax            TransactionType = "tax"
	TxOther          TransactionType = "other"
)

var validTypes = map[TransactionType]bool{
	TxPurchase: true, TxSale: true, TxTransport: true,
	TxReconditioning: true, TxInspection: true, TxRegistration: true,
	TxInsurance: true, TxStorage: true, TxSyndicationFee: true,
	TxPlatformFee: true, TxTax: true, TxOther: true,
}

// Valid reports whether the type is a known transaction type.
func (t TransactionType) Valid() bool { return validTypes[t] }

// IsCost reports whether this type represents a cost (not revenue).
func (t TransactionType) IsCost() bool { return t != TxSale }

// Transaction is a single financial event associated with a vehicle.
type Transaction struct {
	ID           string          `json:"id"`
	TenantID     string          `json:"tenant_id"`
	VehicleID    string          `json:"vehicle_id"`
	Type         TransactionType `json:"type"`
	AmountCents  int64           `json:"amount_cents"`  // always positive
	Currency     string          `json:"currency"`       // ISO 4217, e.g. "EUR"
	VATCents     int64           `json:"vat_cents"`
	VATRate      float64         `json:"vat_rate"`
	Counterparty string          `json:"counterparty"`
	Reference    string          `json:"reference"`
	Date         string          `json:"date"` // YYYY-MM-DD
	Notes        string          `json:"notes"`
	CreatedAt    time.Time       `json:"created_at"`
	UpdatedAt    time.Time       `json:"updated_at"`
}

// VehiclePnL is the profit-and-loss summary for a single vehicle.
type VehiclePnL struct {
	VehicleID        string        `json:"vehicle_id"`
	TenantID         string        `json:"tenant_id"`
	TotalCostCents   int64         `json:"total_cost_cents"`    // sum of all cost transactions (EUR)
	TotalRevCents    int64         `json:"total_revenue_cents"` // sum of sale transactions (EUR)
	GrossMarginCents int64         `json:"gross_margin_cents"`  // revenue − cost
	MarginPct        float64       `json:"margin_pct"`          // gross_margin / revenue × 100
	ROIPct           float64       `json:"roi_pct"`             // gross_margin / cost × 100
	DaysInStock      int           `json:"days_in_stock"`
	CostPerDayCents  int64         `json:"cost_per_day_cents"`
	Currency         string        `json:"currency"` // always "EUR" (base)
	Transactions     []Transaction `json:"transactions,omitempty"`
}

// FleetPnL is the P&L aggregation across all vehicles for a date range.
type FleetPnL struct {
	TenantID         string           `json:"tenant_id"`
	From             string           `json:"from"`
	To               string           `json:"to"`
	VehicleCount     int              `json:"vehicle_count"`
	TotalCostCents   int64            `json:"total_cost_cents"`
	TotalRevCents    int64            `json:"total_revenue_cents"`
	GrossMarginCents int64            `json:"gross_margin_cents"`
	AvgMarginPct     float64          `json:"avg_margin_pct"`
	BestVehicleID    string           `json:"best_vehicle_id,omitempty"`
	BestMarginCents  int64            `json:"best_margin_cents"`
	WorstVehicleID   string           `json:"worst_vehicle_id,omitempty"`
	WorstMarginCents int64            `json:"worst_margin_cents"`
	CostByType       map[string]int64 `json:"cost_by_type"`
	Currency         string           `json:"currency"`
}

// MonthlyPnL is the P&L for a single calendar month with prior-month comparison.
type MonthlyPnL struct {
	TenantID             string  `json:"tenant_id"`
	Year                 int     `json:"year"`
	Month                int     `json:"month"`
	TotalCostCents       int64   `json:"total_cost_cents"`
	TotalRevCents        int64   `json:"total_revenue_cents"`
	GrossMarginCents     int64   `json:"gross_margin_cents"`
	MarginPct            float64 `json:"margin_pct"`
	PrevTotalCostCents   int64   `json:"prev_total_cost_cents"`
	PrevTotalRevCents    int64   `json:"prev_total_revenue_cents"`
	PrevGrossMarginCents int64   `json:"prev_gross_margin_cents"`
	RevGrowthPct         float64 `json:"rev_growth_pct"`
	MarginGrowthPct      float64 `json:"margin_growth_pct"`
	Currency             string  `json:"currency"`
}

// AlertType classifies the financial warning.
type AlertType string

const (
	AlertNegativeMargin     AlertType = "negative_margin"
	AlertStockTooLong       AlertType = "stock_too_long"
	AlertReconditioningHigh AlertType = "reconditioning_high"
)

// Alert is an active financial warning for a vehicle.
type Alert struct {
	ID        string    `json:"id"`
	TenantID  string    `json:"tenant_id"`
	VehicleID string    `json:"vehicle_id"`
	Type      AlertType `json:"type"`
	Message   string    `json:"message"`
	Severity  string    `json:"severity"` // "warning" | "critical"
	CreatedAt time.Time `json:"created_at"`
}

// ExchangeRate is a point-in-time FX rate (from → to).
type ExchangeRate struct {
	FromCurrency string  `json:"from_currency"`
	ToCurrency   string  `json:"to_currency"`
	Rate         float64 `json:"rate"`
	ValidFrom    string  `json:"valid_from"` // YYYY-MM-DD
}

// CreateTransactionRequest is the request body for POST /vehicles/{id}/transactions.
type CreateTransactionRequest struct {
	Type         TransactionType `json:"type"`
	AmountCents  int64           `json:"amount_cents"`
	Currency     string          `json:"currency,omitempty"`
	VATCents     int64           `json:"vat_cents,omitempty"`
	VATRate      float64         `json:"vat_rate,omitempty"`
	Counterparty string          `json:"counterparty,omitempty"`
	Reference    string          `json:"reference,omitempty"`
	Date         string          `json:"date,omitempty"` // YYYY-MM-DD; defaults to today
	Notes        string          `json:"notes,omitempty"`
}
