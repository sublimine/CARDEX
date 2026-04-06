package handlers

import (
	"net/http"
	"strings"
)

// PriceIndex handles GET /api/v1/analytics/price-index
// OHLCV-style time series for TradingView Lightweight Charts.
// open=p10, high=p90, low=p5, close=median, volume=sample_size
//
// Params: make, model, country, interval (day|week|month)
func (d *Deps) PriceIndex(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	make_ := q.Get("make")
	model := q.Get("model")
	country := q.Get("country")
	interval := q.Get("interval")

	chInterval := map[string]string{
		"day":   "toDate(snapshot_date)",
		"week":  "toStartOfWeek(snapshot_date)",
		"month": "toStartOfMonth(snapshot_date)",
	}[interval]
	if chInterval == "" {
		chInterval = "toStartOfWeek(snapshot_date)"
	}

	var where []string
	var args []any
	where = append(where, "snapshot_date >= today() - INTERVAL 2 YEAR")
	if make_ != "" {
		where = append(where, "make = ?")
		args = append(args, make_)
	}
	if model != "" {
		where = append(where, "model = ?")
		args = append(args, model)
	}
	if country != "" {
		where = append(where, "country = ?")
		args = append(args, country)
	}

	query := "SELECT " + chInterval + " AS t," +
		" argMin(median, snapshot_date) AS open," +
		" max(p90) AS high," +
		" min(p5) AS low," +
		" argMax(median, snapshot_date) AS close," +
		" sum(sample_size) AS volume," +
		" avg(median_dom) AS avg_dom" +
		" FROM cardex.price_index" +
		" WHERE " + strings.Join(where, " AND ") +
		" GROUP BY t ORDER BY t ASC"

	rows, err := d.CH.Query(r.Context(), query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "ch_error", err.Error())
		return
	}
	defer rows.Close()

	type candle struct {
		Time   string  `json:"time"`
		Open   float64 `json:"open"`
		High   float64 `json:"high"`
		Low    float64 `json:"low"`
		Close  float64 `json:"close"`
		Volume uint64  `json:"volume"`
		AvgDOM float32 `json:"avg_dom"`
	}
	var candles []candle
	for rows.Next() {
		var c candle
		if err := rows.Scan(&c.Time, &c.Open, &c.High, &c.Low, &c.Close, &c.Volume, &c.AvgDOM); err != nil {
			continue
		}
		candles = append(candles, c)
	}
	if candles == nil {
		candles = []candle{}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"make": make_, "model": model, "country": country,
		"interval": interval, "series": candles,
	})
}

// MarketDepth handles GET /api/v1/analytics/market-depth
// Order-book style: listing count per 1 000 EUR price tier.
func (d *Deps) MarketDepth(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	make_ := q.Get("make")
	model := q.Get("model")
	country := q.Get("country")

	var where []string
	var args []any
	where = append(where, "snapshot_date >= today() - 2")
	if make_ != "" {
		where = append(where, "make = ?")
		args = append(args, make_)
	}
	if model != "" {
		where = append(where, "model = ?")
		args = append(args, model)
	}
	if country != "" {
		where = append(where, "country = ?")
		args = append(args, country)
	}

	rows, err := d.CH.Query(r.Context(),
		"SELECT price_tier_eur, sum(listing_count) AS cnt, avg(avg_mileage_km) AS avg_km"+
			" FROM cardex.market_depth WHERE "+strings.Join(where, " AND ")+
			" GROUP BY price_tier_eur ORDER BY price_tier_eur ASC",
		args...,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "ch_error", err.Error())
		return
	}
	defer rows.Close()

	type tier struct {
		Price      uint32  `json:"price_tier_eur"`
		Count      uint64  `json:"count"`
		AvgMileage float64 `json:"avg_mileage_km"`
	}
	var tiers []tier
	for rows.Next() {
		var t tier
		rows.Scan(&t.Price, &t.Count, &t.AvgMileage)
		tiers = append(tiers, t)
	}
	if tiers == nil {
		tiers = []tier{}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"make": make_, "model": model, "country": country, "depth": tiers,
	})
}

// DemandSignals handles GET /api/v1/analytics/demand
// Search / view / alert counts as a time series.
func (d *Deps) DemandSignals(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	make_ := q.Get("make")
	model := q.Get("model")
	country := q.Get("country")
	days := parseInt(q.Get("days"), 30)
	if days > 365 {
		days = 365
	}

	var where []string
	var args []any
	where = append(where, "signal_date >= today() - ?")
	args = append(args, days)
	if make_ != "" {
		where = append(where, "make = ?")
		args = append(args, make_)
	}
	if model != "" {
		where = append(where, "model = ?")
		args = append(args, model)
	}
	if country != "" {
		where = append(where, "country = ?")
		args = append(args, country)
	}

	rows, err := d.CH.Query(r.Context(),
		"SELECT signal_date, signal_type, sum(count) AS total"+
			" FROM cardex.demand_signals WHERE "+strings.Join(where, " AND ")+
			" GROUP BY signal_date, signal_type ORDER BY signal_date ASC",
		args...,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "ch_error", err.Error())
		return
	}
	defer rows.Close()

	type point struct {
		Date   string `json:"date"`
		Type   string `json:"signal_type"`
		Count  uint64 `json:"count"`
	}
	var pts []point
	for rows.Next() {
		var p point
		rows.Scan(&p.Date, &p.Type, &p.Count)
		pts = append(pts, p)
	}
	if pts == nil {
		pts = []point{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"signals": pts})
}

// Heatmap handles GET /api/v1/analytics/heatmap
// Returns H3 hex IDs + listing counts for deck.gl H3HexagonLayer.
func (d *Deps) Heatmap(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	make_ := q.Get("make")
	country := q.Get("country")
	res := parseInt(q.Get("resolution"), 4)
	if res < 3 || res > 7 {
		res = 4
	}

	resField := "h3_index_res4"
	if res == 7 {
		resField = "h3_index_res7"
	}

	var where []string
	var args []any
	where = append(where, "lifecycle_status = 'MARKET_READY'")
	where = append(where, "listing_status = 'ACTIVE'")
	where = append(where, resField+" IS NOT NULL")
	if make_ != "" {
		where = append(where, "make = $1")
		args = append(args, make_)
	}
	if country != "" {
		args = append(args, country)
		where = append(where, "source_country = $"+itoa(len(args)))
	}

	rows, err := d.DB.Query(r.Context(),
		"SELECT "+resField+" AS hex_id, count(*) AS cnt, avg(gross_physical_cost_eur) AS avg_price"+
			" FROM vehicles WHERE "+strings.Join(where, " AND ")+
			" GROUP BY "+resField+" ORDER BY cnt DESC LIMIT 50000",
		args...,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "pg_error", err.Error())
		return
	}
	defer rows.Close()

	type hex struct {
		HexID    string  `json:"hex_id"`
		Count    int64   `json:"count"`
		AvgPrice float64 `json:"avg_price_eur"`
	}
	var hexes []hex
	for rows.Next() {
		var h hex
		rows.Scan(&h.HexID, &h.Count, &h.AvgPrice)
		hexes = append(hexes, h)
	}
	if hexes == nil {
		hexes = []hex{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"resolution": res, "hexes": hexes})
}

// DOMDistribution handles GET /api/v1/analytics/dom
func (d *Deps) DOMDistribution(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	make_ := q.Get("make")
	model := q.Get("model")
	country := q.Get("country")

	var where []string
	var args []any
	where = append(where, "snapshot_date >= today() - 7")
	if make_ != "" {
		where = append(where, "make = ?")
		args = append(args, make_)
	}
	if model != "" {
		where = append(where, "model = ?")
		args = append(args, model)
	}
	if country != "" {
		where = append(where, "country = ?")
		args = append(args, country)
	}

	row := d.CH.QueryRow(r.Context(),
		"SELECT p10_dom,p25_dom,median_dom,p75_dom,p90_dom,avg_dom,sample_size"+
			" FROM cardex.dom_distribution WHERE "+strings.Join(where, " AND ")+
			" ORDER BY snapshot_date DESC LIMIT 1",
		args...,
	)
	var res struct {
		P10    float32 `json:"p10_days"`
		P25    float32 `json:"p25_days"`
		Median float32 `json:"median_days"`
		P75    float32 `json:"p75_days"`
		P90    float32 `json:"p90_days"`
		Avg    float32 `json:"avg_days"`
		N      uint32  `json:"sample_size"`
	}
	if err := row.Scan(&res.P10, &res.P25, &res.Median, &res.P75, &res.P90, &res.Avg, &res.N); err != nil {
		writeError(w, http.StatusNotFound, "no_data", "no DOM data for these filters")
		return
	}
	writeJSON(w, http.StatusOK, res)
}

// PriceVolatility handles GET /api/v1/analytics/volatility
// 30-day rolling coefficient of variation (stddev/mean).
func (d *Deps) PriceVolatility(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	make_ := q.Get("make")
	model := q.Get("model")
	country := q.Get("country")
	weeks := parseInt(q.Get("weeks"), 12)

	var where []string
	var args []any
	where = append(where, "week >= today() - ?")
	args = append(args, weeks*7)
	if make_ != "" {
		where = append(where, "make = ?")
		args = append(args, make_)
	}
	if model != "" {
		where = append(where, "model = ?")
		args = append(args, model)
	}
	if country != "" {
		where = append(where, "country = ?")
		args = append(args, country)
	}

	rows, err := d.CH.Query(r.Context(),
		"SELECT week, volatility_coeff, price_avg, sample_size"+
			" FROM cardex.mv_price_volatility WHERE "+strings.Join(where, " AND ")+
			" ORDER BY week ASC",
		args...,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "ch_error", err.Error())
		return
	}
	defer rows.Close()

	type vpoint struct {
		Week       string  `json:"week"`
		Volatility float64 `json:"volatility_coeff"`
		AvgPrice   float64 `json:"avg_price_eur"`
		N          uint64  `json:"sample_size"`
	}
	var pts []vpoint
	for rows.Next() {
		var p vpoint
		rows.Scan(&p.Week, &p.Volatility, &p.AvgPrice, &p.N)
		pts = append(pts, p)
	}
	if pts == nil {
		pts = []vpoint{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"volatility": pts})
}

// itoa converts int to string (local helper, avoids strconv import clash)
func itoa(n int) string {
	const digits = "0123456789"
	if n == 0 {
		return "0"
	}
	result := ""
	for n > 0 {
		result = string(digits[n%10]) + result
		n /= 10
	}
	return result
}
