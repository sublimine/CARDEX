package finance

import (
	"fmt"
	"time"
)

const (
	thresholdDaysInStock      = 60   // days without sale triggers alert
	thresholdReconditioningPct = 15.0 // reconditioning/purchase > this% triggers alert
)

// AlertService detects financial anomalies across a tenant's vehicle portfolio.
type AlertService struct {
	store *Store
}

// NewAlertService creates an AlertService backed by store.
func NewAlertService(store *Store) *AlertService { return &AlertService{store: store} }

// GetAlerts returns all active financial alerts for the tenant.
// Scans all vehicles with transactions in the trailing 365 days.
func (a *AlertService) GetAlerts(tenantID string) ([]Alert, error) {
	today := time.Now().Format("2006-01-02")
	from := time.Now().AddDate(-1, 0, 0).Format("2006-01-02")

	txs, err := a.store.ListByDateRange(tenantID, from, today)
	if err != nil {
		return nil, err
	}

	rf := func(cur, date string) (float64, error) {
		return a.store.GetExchangeRate(cur, "EUR", date)
	}

	var alerts []Alert
	for vehicleID, vtxs := range groupByVehicle(txs) {
		alerts = append(alerts, checkVehicleAlerts(tenantID, vehicleID, vtxs, rf)...)
	}
	metricAlertsActive.Set(float64(len(alerts)))
	return alerts, nil
}

// checkVehicleAlerts evaluates the three alert conditions for one vehicle.
func checkVehicleAlerts(tenantID, vehicleID string, txs []Transaction, getRate rateFunc) []Alert {
	var alerts []Alert
	now := time.Now()

	pnl := computeVehiclePnL(tenantID, vehicleID, txs, getRate)

	var hasSale bool
	var purchaseCents, recondCents int64
	for _, tx := range txs {
		switch tx.Type {
		case TxSale:
			hasSale = true
		case TxPurchase:
			purchaseCents += tx.AmountCents
		case TxReconditioning:
			recondCents += tx.AmountCents
		}
	}

	// 1. Negative gross margin (vehicle already sold at a loss).
	if hasSale && pnl.GrossMarginCents < 0 {
		alerts = append(alerts, Alert{
			ID:        newID(),
			TenantID:  tenantID,
			VehicleID: vehicleID,
			Type:      AlertNegativeMargin,
			Message: fmt.Sprintf(
				"vehicle %s sold with negative gross margin: %.2f EUR",
				vehicleID, float64(pnl.GrossMarginCents)/100,
			),
			Severity:  "critical",
			CreatedAt: now,
		})
	}

	// 2. Vehicle in stock ≥ 60 days without a sale.
	if !hasSale && pnl.DaysInStock >= thresholdDaysInStock {
		alerts = append(alerts, Alert{
			ID:        newID(),
			TenantID:  tenantID,
			VehicleID: vehicleID,
			Type:      AlertStockTooLong,
			Message: fmt.Sprintf(
				"vehicle %s has been in stock %d days without a sale",
				vehicleID, pnl.DaysInStock,
			),
			Severity:  "warning",
			CreatedAt: now,
		})
	}

	// 3. Reconditioning cost > 15% of purchase price.
	if purchaseCents > 0 {
		recondPct := float64(recondCents) / float64(purchaseCents) * 100
		if recondPct > thresholdReconditioningPct {
			alerts = append(alerts, Alert{
				ID:        newID(),
				TenantID:  tenantID,
				VehicleID: vehicleID,
				Type:      AlertReconditioningHigh,
				Message: fmt.Sprintf(
					"vehicle %s reconditioning is %.1f%% of purchase price (threshold %.0f%%)",
					vehicleID, recondPct, thresholdReconditioningPct,
				),
				Severity:  "warning",
				CreatedAt: now,
			})
		}
	}

	return alerts
}
