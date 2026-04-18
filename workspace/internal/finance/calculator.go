package finance

import (
	"math"
	"time"
)

// rateFunc converts an amount from a foreign currency to EUR.
// Receives the source currency and the transaction date (YYYY-MM-DD).
// Returns a multiplier; 1.0 means no conversion (same currency or no rate).
type rateFunc func(fromCurrency, date string) (float64, error)

// Calculator computes P&L metrics from transaction data.
type Calculator struct {
	store *Store
}

// NewCalculator creates a Calculator backed by store.
func NewCalculator(store *Store) *Calculator { return &Calculator{store: store} }

// CalculateVehiclePnL computes the full P&L for a single vehicle.
func (c *Calculator) CalculateVehiclePnL(tenantID, vehicleID string) (*VehiclePnL, error) {
	txs, err := c.store.ListByVehicle(tenantID, vehicleID)
	if err != nil {
		return nil, err
	}
	rf := func(from, date string) (float64, error) {
		return c.store.GetExchangeRate(from, "EUR", date)
	}
	pnl := computeVehiclePnL(tenantID, vehicleID, txs, rf)
	metricMarginCents.Observe(float64(pnl.GrossMarginCents))
	return pnl, nil
}

// CalculateFleetPnL aggregates P&L across all vehicles with transactions in [from, to].
func (c *Calculator) CalculateFleetPnL(tenantID, from, to string) (*FleetPnL, error) {
	txs, err := c.store.ListByDateRange(tenantID, from, to)
	if err != nil {
		return nil, err
	}
	rf := func(cur, date string) (float64, error) {
		return c.store.GetExchangeRate(cur, "EUR", date)
	}

	fleet := &FleetPnL{
		TenantID:   tenantID,
		From:       from,
		To:         to,
		CostByType: make(map[string]int64),
		Currency:   "EUR",
	}

	byVehicle := groupByVehicle(txs)
	fleet.VehicleCount = len(byVehicle)

	var marginsSum float64
	var marginsCount int
	bestSet, worstSet := false, false

	for vehicleID, vtxs := range byVehicle {
		vp := computeVehiclePnL(tenantID, vehicleID, vtxs, rf)
		fleet.TotalCostCents += vp.TotalCostCents
		fleet.TotalRevCents += vp.TotalRevCents
		fleet.GrossMarginCents += vp.GrossMarginCents

		if vp.TotalRevCents > 0 {
			marginsSum += vp.MarginPct
			marginsCount++
		}
		if !bestSet || vp.GrossMarginCents > fleet.BestMarginCents {
			fleet.BestVehicleID = vehicleID
			fleet.BestMarginCents = vp.GrossMarginCents
			bestSet = true
		}
		if !worstSet || vp.GrossMarginCents < fleet.WorstMarginCents {
			fleet.WorstVehicleID = vehicleID
			fleet.WorstMarginCents = vp.GrossMarginCents
			worstSet = true
		}
		for _, tx := range vtxs {
			if tx.Type.IsCost() {
				fleet.CostByType[string(tx.Type)] += tx.AmountCents
			}
		}
	}
	if marginsCount > 0 {
		fleet.AvgMarginPct = marginsSum / float64(marginsCount)
	}
	return fleet, nil
}

// CalculateMonthlyPnL computes P&L for (year, month) and the preceding month.
func (c *Calculator) CalculateMonthlyPnL(tenantID string, year, month int) (*MonthlyPnL, error) {
	currTxs, err := c.store.ListByMonth(tenantID, year, month)
	if err != nil {
		return nil, err
	}
	prevYear, prevMonth := year, month-1
	if prevMonth < 1 {
		prevMonth, prevYear = 12, year-1
	}
	prevTxs, err := c.store.ListByMonth(tenantID, prevYear, prevMonth)
	if err != nil {
		return nil, err
	}

	curr := sumTxs(currTxs)
	prev := sumTxs(prevTxs)

	mp := &MonthlyPnL{
		TenantID:             tenantID,
		Year:                 year,
		Month:                month,
		TotalCostCents:       curr.cost,
		TotalRevCents:        curr.rev,
		GrossMarginCents:     curr.rev - curr.cost,
		PrevTotalCostCents:   prev.cost,
		PrevTotalRevCents:    prev.rev,
		PrevGrossMarginCents: prev.rev - prev.cost,
		Currency:             "EUR",
	}
	if curr.rev > 0 {
		mp.MarginPct = float64(mp.GrossMarginCents) / float64(curr.rev) * 100
	}
	if prev.rev > 0 {
		mp.RevGrowthPct = float64(curr.rev-prev.rev) / float64(prev.rev) * 100
	}
	prevMargin := prev.rev - prev.cost
	if prevMargin != 0 {
		mp.MarginGrowthPct = float64(mp.GrossMarginCents-prevMargin) / math.Abs(float64(prevMargin)) * 100
	}
	return mp, nil
}

// ── pure computation (exported for tests without DB) ─────────────────────────

// computeVehiclePnL is the pure P&L engine. getRate is optional; pass nil to
// skip multi-currency conversion (treats all amounts as EUR).
func computeVehiclePnL(tenantID, vehicleID string, txs []Transaction, getRate rateFunc) *VehiclePnL {
	pnl := &VehiclePnL{
		VehicleID:    vehicleID,
		TenantID:     tenantID,
		Currency:     "EUR",
		Transactions: txs,
	}

	today := time.Now().UTC().Truncate(24 * time.Hour)
	var purchaseDate, saleDate time.Time

	for _, tx := range txs {
		amtEUR := tx.AmountCents
		if tx.Currency != "EUR" && getRate != nil {
			if rate, err := getRate(tx.Currency, tx.Date); err == nil && rate > 0 {
				amtEUR = int64(math.Round(float64(tx.AmountCents) * rate))
			}
		}
		if tx.Type.IsCost() {
			pnl.TotalCostCents += amtEUR
		} else {
			pnl.TotalRevCents += amtEUR
		}

		d, err := time.Parse("2006-01-02", tx.Date)
		if err != nil {
			continue
		}
		if tx.Type == TxPurchase && (purchaseDate.IsZero() || d.Before(purchaseDate)) {
			purchaseDate = d
		}
		if tx.Type == TxSale && (saleDate.IsZero() || d.After(saleDate)) {
			saleDate = d
		}
	}

	pnl.GrossMarginCents = pnl.TotalRevCents - pnl.TotalCostCents
	if pnl.TotalRevCents > 0 {
		pnl.MarginPct = float64(pnl.GrossMarginCents) / float64(pnl.TotalRevCents) * 100
	}
	if pnl.TotalCostCents > 0 {
		pnl.ROIPct = float64(pnl.GrossMarginCents) / float64(pnl.TotalCostCents) * 100
	}

	if !purchaseDate.IsZero() {
		end := today
		if !saleDate.IsZero() {
			end = saleDate
		}
		days := int(end.Sub(purchaseDate).Hours() / 24)
		if days < 0 {
			days = 0
		}
		pnl.DaysInStock = days
		if days > 0 {
			pnl.CostPerDayCents = pnl.TotalCostCents / int64(days)
		}
	}
	return pnl
}

type txSums struct{ cost, rev int64 }

func sumTxs(txs []Transaction) txSums {
	var s txSums
	for _, tx := range txs {
		if tx.Type.IsCost() {
			s.cost += tx.AmountCents
		} else {
			s.rev += tx.AmountCents
		}
	}
	return s
}

func groupByVehicle(txs []Transaction) map[string][]Transaction {
	m := make(map[string][]Transaction)
	for _, tx := range txs {
		m[tx.VehicleID] = append(m[tx.VehicleID], tx)
	}
	return m
}
