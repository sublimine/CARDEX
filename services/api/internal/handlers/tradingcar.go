package handlers

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"
)

// parseTicker splits "BMW_3-Series_2020_DE_Gasoline" into its five components.
// Format: {make}_{model}_{year}_{country}_{fuel_type}
// Model may contain hyphens but not underscores; country is always 2 uppercase letters.
func parseTicker(ticker string) (make_, model string, year int, country, fuelType string, ok bool) {
	parts := strings.Split(ticker, "_")
	if len(parts) < 5 {
		return
	}
	make_ = parts[0]
	// year is parts[len-3], country parts[len-2], fuel parts[len-1]
	// model is everything between make and year
	fuelType = parts[len(parts)-1]
	country = parts[len(parts)-2]
	if len(country) != 2 {
		return
	}
	country = strings.ToUpper(country)
	yearStr := parts[len(parts)-3]
	y, err := strconv.Atoi(yearStr)
	if err != nil || y < 1900 || y > 2100 {
		return
	}
	year = y
	model = strings.Join(parts[1:len(parts)-3], "_")
	ok = true
	return
}

// tickerCacheKey builds a Redis key for candle caching.
func tickerCacheKey(ticker, period, from, to string) string {
	return fmt.Sprintf("tradingcar:candles:%s:%s:%s:%s", ticker, period, from, to)
}

// ──────────────────────────────────────────────────────────────────────────────
// TradingCarCandles — GET /api/v1/tradingcar/candles
// ──────────────────────────────────────────────────────────────────────────────

func (d *Deps) TradingCarCandles(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	ticker := strings.TrimSpace(q.Get("ticker"))
	if ticker == "" {
		writeError(w, http.StatusBadRequest, "missing_param", "ticker is required")
		return
	}

	period := strings.ToUpper(q.Get("period"))
	if period != "W" && period != "M" {
		period = "M"
	}

	today := time.Now().UTC().Format("2006-01-02")
	from := q.Get("from")
	to := q.Get("to")
	if to == "" {
		to = today
	}

	limit := parseInt(q.Get("limit"), 100)
	if limit > 500 {
		limit = 500
	}

	make_, model, year, country, fuelType, ok := parseTicker(ticker)
	if !ok {
		writeError(w, http.StatusBadRequest, "invalid_ticker", "ticker format must be {make}_{model}_{year}_{country(2)}_{fuel_type}")
		return
	}

	// Try Redis cache first.
	cacheKey := tickerCacheKey(ticker, period, from, to)
	if cached, err := d.Redis.Get(r.Context(), cacheKey).Bytes(); err == nil {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-Cache", "HIT")
		w.Write(cached)
		return
	}

	// Build ClickHouse query.
	var where []string
	var args []any
	where = append(where, "period_type = ?")
	args = append(args, period)
	where = append(where, "make = ?")
	args = append(args, make_)
	where = append(where, "model = ?")
	args = append(args, model)
	where = append(where, "year = ?")
	args = append(args, uint16(year))
	where = append(where, "country = ?")
	args = append(args, country)
	where = append(where, "fuel_type = ?")
	args = append(args, fuelType)
	if from != "" {
		where = append(where, "period_start >= ?")
		args = append(args, from)
	}
	where = append(where, "period_start <= ?")
	args = append(args, to)

	query := "SELECT period_start, open_eur, high_eur, low_eur, close_eur, volume, avg_mileage_km" +
		" FROM cardex.price_candles" +
		" WHERE " + strings.Join(where, " AND ") +
		" ORDER BY period_start ASC" +
		fmt.Sprintf(" LIMIT %d", limit)

	rows, err := d.CH.Query(r.Context(), query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "ch_error", err.Error())
		return
	}
	defer rows.Close()

	type candle struct {
		Time         string  `json:"time"`
		Open         float64 `json:"open"`
		High         float64 `json:"high"`
		Low          float64 `json:"low"`
		Close        float64 `json:"close"`
		Volume       uint32  `json:"volume"`
		AvgMileageKm float32 `json:"avg_mileage_km"`
	}

	var candles []candle
	for rows.Next() {
		var c candle
		if err := rows.Scan(&c.Time, &c.Open, &c.High, &c.Low, &c.Close, &c.Volume, &c.AvgMileageKm); err != nil {
			continue
		}
		candles = append(candles, c)
	}
	if candles == nil {
		candles = []candle{}
	}

	resp := map[string]any{
		"ticker": ticker,
		"period": period,
		"candles": candles,
		"meta": map[string]any{
			"make":    make_,
			"model":   strings.ReplaceAll(model, "-", " "),
			"year":    year,
			"country": country,
			"fuel":    fuelType,
		},
	}

	payload, _ := json.Marshal(resp)

	// Store in Redis TTL 1h.
	d.Redis.Set(r.Context(), cacheKey, payload, time.Hour)

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Cache", "MISS")
	w.Write(payload)
}

// ──────────────────────────────────────────────────────────────────────────────
// TradingCarTickers — GET /api/v1/tradingcar/tickers
// ──────────────────────────────────────────────────────────────────────────────

func (d *Deps) TradingCarTickers(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	search := strings.TrimSpace(q.Get("q"))
	country := strings.TrimSpace(q.Get("country"))
	make_ := strings.TrimSpace(q.Get("make"))
	fuel := strings.TrimSpace(q.Get("fuel"))
	sort_ := q.Get("sort")
	limit := parseInt(q.Get("limit"), 50)
	if limit > 200 {
		limit = 200
	}

	cacheKey := fmt.Sprintf("tradingcar:tickers:%s:%s:%s:%s:%s:%d", search, country, make_, fuel, sort_, limit)
	if cached, err := d.Redis.Get(r.Context(), cacheKey).Bytes(); err == nil {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-Cache", "HIT")
		w.Write(cached)
		return
	}

	var where []string
	var args []any

	if search != "" {
		where = append(where, "(lower(make) LIKE lower(?) OR lower(model) LIKE lower(?))")
		pattern := "%" + search + "%"
		args = append(args, pattern, pattern)
	}
	if country != "" {
		where = append(where, "country = ?")
		args = append(args, country)
	}
	if make_ != "" {
		where = append(where, "make = ?")
		args = append(args, make_)
	}
	if fuel != "" {
		where = append(where, "fuel_type = ?")
		args = append(args, fuel)
	}

	orderBy := "volume_30d DESC"
	switch sort_ {
	case "change_1w":
		orderBy = "change_1w_pct DESC"
	case "change_1m":
		orderBy = "change_1m_pct DESC"
	case "liquidity":
		orderBy = "liquidity_score DESC"
	}

	whereClause := "1=1"
	if len(where) > 0 {
		whereClause = strings.Join(where, " AND ")
	}

	query := fmt.Sprintf(
		"SELECT ticker_id, make, model, year, country, fuel_type,"+
			" last_price_eur, change_1w_pct, change_1m_pct, change_3m_pct,"+
			" volume_30d, avg_dom_30d, liquidity_score"+
			" FROM cardex.ticker_stats"+
			" WHERE %s"+
			" ORDER BY %s"+
			" LIMIT %d",
		whereClause, orderBy, limit,
	)

	rows, err := d.CH.Query(r.Context(), query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "ch_error", err.Error())
		return
	}
	defer rows.Close()

	type tickerRow struct {
		TickerID      string  `json:"ticker_id"`
		Make          string  `json:"make"`
		Model         string  `json:"model"`
		Year          uint16  `json:"year"`
		Country       string  `json:"country"`
		FuelType      string  `json:"fuel_type"`
		LastPriceEUR  float64 `json:"last_price_eur"`
		Change1WPCT   float32 `json:"change_1w_pct"`
		Change1MPCT   float32 `json:"change_1m_pct"`
		Change3MPCT   float32 `json:"change_3m_pct"`
		Volume30D     uint32  `json:"volume_30d"`
		AvgDOM30D     float32 `json:"avg_dom_30d"`
		LiquidityScore float32 `json:"liquidity_score"`
	}

	var tickers []tickerRow
	for rows.Next() {
		var t tickerRow
		if err := rows.Scan(
			&t.TickerID, &t.Make, &t.Model, &t.Year, &t.Country, &t.FuelType,
			&t.LastPriceEUR, &t.Change1WPCT, &t.Change1MPCT, &t.Change3MPCT,
			&t.Volume30D, &t.AvgDOM30D, &t.LiquidityScore,
		); err != nil {
			continue
		}
		tickers = append(tickers, t)
	}
	if tickers == nil {
		tickers = []tickerRow{}
	}

	payload, _ := json.Marshal(map[string]any{"tickers": tickers})
	d.Redis.Set(r.Context(), cacheKey, payload, 5*time.Minute)

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Cache", "MISS")
	w.Write(payload)
}

// ──────────────────────────────────────────────────────────────────────────────
// TradingCarScanner — GET /api/v1/tradingcar/scanner
// ──────────────────────────────────────────────────────────────────────────────

func (d *Deps) TradingCarScanner(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	scanType := strings.TrimSpace(q.Get("type"))
	country := strings.TrimSpace(q.Get("country"))
	limit := parseInt(q.Get("limit"), 20)
	if limit > 100 {
		limit = 100
	}

	validTypes := map[string]bool{
		"most_depreciating": true,
		"best_value":        true,
		"most_liquid":       true,
		"near_historic_low": true,
		"momentum_up":       true,
		"momentum_down":     true,
	}
	if !validTypes[scanType] {
		writeError(w, http.StatusBadRequest, "invalid_type",
			"type must be one of: most_depreciating, best_value, most_liquid, near_historic_low, momentum_up, momentum_down")
		return
	}

	cacheKey := fmt.Sprintf("tradingcar:scanner:%s:%s:%d", scanType, country, limit)
	if cached, err := d.Redis.Get(r.Context(), cacheKey).Bytes(); err == nil {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-Cache", "HIT")
		w.Write(cached)
		return
	}

	var query string
	var args []any

	countryFilter := "1=1"
	if country != "" {
		countryFilter = "country = ?"
		args = append(args, country)
	}

	baseSelect := "SELECT ticker_id, make, model, year, country, fuel_type," +
		" last_price_eur, change_1w_pct, change_1m_pct, change_3m_pct," +
		" volume_30d, avg_dom_30d, liquidity_score" +
		" FROM cardex.ticker_stats"

	switch scanType {
	case "most_depreciating":
		query = fmt.Sprintf("%s WHERE %s ORDER BY change_1m_pct ASC LIMIT %d",
			baseSelect, countryFilter, limit)

	case "best_value":
		filter := countryFilter + " AND avg_dom_30d < 30 AND change_1m_pct < -5"
		query = fmt.Sprintf("%s WHERE %s ORDER BY change_1m_pct ASC LIMIT %d",
			baseSelect, filter, limit)

	case "most_liquid":
		query = fmt.Sprintf("%s WHERE %s ORDER BY volume_30d DESC, avg_dom_30d ASC LIMIT %d",
			baseSelect, countryFilter, limit)

	case "near_historic_low":
		// Join ticker_stats with the all-time min low from price_candles.
		historicFilter := "1=1"
		if country != "" {
			historicFilter = "ts.country = ?"
			// args already has country from countryFilter setup — reset and redo for subquery join
			args = []any{country}
		}
		query = fmt.Sprintf(
			"SELECT ts.ticker_id, ts.make, ts.model, ts.year, ts.country, ts.fuel_type,"+
				" ts.last_price_eur, ts.change_1w_pct, ts.change_1m_pct, ts.change_3m_pct,"+
				" ts.volume_30d, ts.avg_dom_30d, ts.liquidity_score"+
				" FROM cardex.ticker_stats ts"+
				" INNER JOIN ("+
				"   SELECT make, model, year, country, fuel_type, min(low_eur) AS all_time_low"+
				"   FROM cardex.price_candles"+
				"   GROUP BY make, model, year, country, fuel_type"+
				" ) atl ON ts.make = atl.make AND ts.model = atl.model"+
				"       AND ts.year = atl.year AND ts.country = atl.country"+
				"       AND ts.fuel_type = atl.fuel_type"+
				" WHERE %s AND ts.last_price_eur <= atl.all_time_low * 1.10"+
				" ORDER BY (ts.last_price_eur / atl.all_time_low) ASC"+
				" LIMIT %d",
			historicFilter, limit,
		)

	case "momentum_up":
		filter := countryFilter + " AND change_1w_pct > 3 AND change_1m_pct > 5"
		query = fmt.Sprintf("%s WHERE %s ORDER BY change_1w_pct DESC LIMIT %d",
			baseSelect, filter, limit)

	case "momentum_down":
		filter := countryFilter + " AND change_1w_pct < -3 AND change_1m_pct < -5"
		query = fmt.Sprintf("%s WHERE %s ORDER BY change_1w_pct ASC LIMIT %d",
			baseSelect, filter, limit)
	}

	rows, err := d.CH.Query(r.Context(), query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "ch_error", err.Error())
		return
	}
	defer rows.Close()

	type scanRow struct {
		TickerID       string  `json:"ticker_id"`
		Make           string  `json:"make"`
		Model          string  `json:"model"`
		Year           uint16  `json:"year"`
		Country        string  `json:"country"`
		FuelType       string  `json:"fuel_type"`
		LastPriceEUR   float64 `json:"last_price_eur"`
		Change1WPCT    float32 `json:"change_1w_pct"`
		Change1MPCT    float32 `json:"change_1m_pct"`
		Change3MPCT    float32 `json:"change_3m_pct"`
		Volume30D      uint32  `json:"volume_30d"`
		AvgDOM30D      float32 `json:"avg_dom_30d"`
		LiquidityScore float32 `json:"liquidity_score"`
	}

	var results []scanRow
	for rows.Next() {
		var s scanRow
		if err := rows.Scan(
			&s.TickerID, &s.Make, &s.Model, &s.Year, &s.Country, &s.FuelType,
			&s.LastPriceEUR, &s.Change1WPCT, &s.Change1MPCT, &s.Change3MPCT,
			&s.Volume30D, &s.AvgDOM30D, &s.LiquidityScore,
		); err != nil {
			continue
		}
		results = append(results, s)
	}
	if results == nil {
		results = []scanRow{}
	}

	payload, _ := json.Marshal(map[string]any{
		"type":    scanType,
		"country": country,
		"results": results,
	})
	d.Redis.Set(r.Context(), cacheKey, payload, 10*time.Minute)

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Cache", "MISS")
	w.Write(payload)
}

// ──────────────────────────────────────────────────────────────────────────────
// TradingCarCompare — GET /api/v1/tradingcar/compare
// ──────────────────────────────────────────────────────────────────────────────

func (d *Deps) TradingCarCompare(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	tickersParam := strings.TrimSpace(q.Get("tickers"))
	if tickersParam == "" {
		writeError(w, http.StatusBadRequest, "missing_param", "tickers is required")
		return
	}

	rawTickers := strings.Split(tickersParam, ",")
	if len(rawTickers) > 5 {
		rawTickers = rawTickers[:5]
	}

	period := strings.ToUpper(q.Get("period"))
	if period != "W" && period != "M" {
		period = "M"
	}
	today := time.Now().UTC().Format("2006-01-02")
	from := q.Get("from")
	to := q.Get("to")
	if to == "" {
		to = today
	}

	type indexedCandle struct {
		Time          string  `json:"time"`
		IndexedClose  float64 `json:"indexed_close"` // normalized to 100 at first data point
		Open          float64 `json:"open"`
		High          float64 `json:"high"`
		Low           float64 `json:"low"`
		Close         float64 `json:"close"`
		Volume        uint32  `json:"volume"`
	}

	type tickerSeries struct {
		Ticker  string          `json:"ticker"`
		Make    string          `json:"make"`
		Model   string          `json:"model"`
		Year    int             `json:"year"`
		Country string          `json:"country"`
		Fuel    string          `json:"fuel"`
		Candles []indexedCandle `json:"candles"`
	}

	var series []tickerSeries

	for _, ticker := range rawTickers {
		ticker = strings.TrimSpace(ticker)
		if ticker == "" {
			continue
		}
		make_, model, year, country, fuelType, ok := parseTicker(ticker)
		if !ok {
			continue
		}

		var where []string
		var args []any
		where = append(where, "period_type = ?")
		args = append(args, period)
		where = append(where, "make = ?")
		args = append(args, make_)
		where = append(where, "model = ?")
		args = append(args, model)
		where = append(where, "year = ?")
		args = append(args, uint16(year))
		where = append(where, "country = ?")
		args = append(args, country)
		where = append(where, "fuel_type = ?")
		args = append(args, fuelType)
		if from != "" {
			where = append(where, "period_start >= ?")
			args = append(args, from)
		}
		where = append(where, "period_start <= ?")
		args = append(args, to)

		qStr := "SELECT period_start, open_eur, high_eur, low_eur, close_eur, volume" +
			" FROM cardex.price_candles" +
			" WHERE " + strings.Join(where, " AND ") +
			" ORDER BY period_start ASC LIMIT 500"

		rows, err := d.CH.Query(r.Context(), qStr, args...)
		if err != nil {
			continue
		}

		type raw struct {
			Time   string
			Open   float64
			High   float64
			Low    float64
			Close  float64
			Volume uint32
		}
		var raws []raw
		for rows.Next() {
			var rv raw
			if err := rows.Scan(&rv.Time, &rv.Open, &rv.High, &rv.Low, &rv.Close, &rv.Volume); err != nil {
				continue
			}
			raws = append(raws, rv)
		}
		rows.Close()

		// Normalize to index = 100 at first close.
		var candles []indexedCandle
		var baseClose float64
		for i, rv := range raws {
			if i == 0 {
				baseClose = rv.Close
			}
			indexed := 100.0
			if baseClose > 0 {
				indexed = (rv.Close / baseClose) * 100.0
			}
			candles = append(candles, indexedCandle{
				Time:         rv.Time,
				IndexedClose: indexed,
				Open:         rv.Open,
				High:         rv.High,
				Low:          rv.Low,
				Close:        rv.Close,
				Volume:       rv.Volume,
			})
		}
		if candles == nil {
			candles = []indexedCandle{}
		}

		series = append(series, tickerSeries{
			Ticker:  ticker,
			Make:    make_,
			Model:   strings.ReplaceAll(model, "-", " "),
			Year:    year,
			Country: country,
			Fuel:    fuelType,
			Candles: candles,
		})
	}

	if series == nil {
		series = []tickerSeries{}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"period": period,
		"from":   from,
		"to":     to,
		"series": series,
	})
}

// Ensure context is used (avoid unused import if compiler strips it).
var _ = context.Background
