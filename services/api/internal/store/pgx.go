package store

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// PGStore is the PostgreSQL-backed Store.
type PGStore struct {
	pool   *pgxpool.Pool
	chfEUR float64
}

// NewPG creates a pooled PostgreSQL store. chfEUR is the CHF→EUR rate applied to
// Swiss-franc prices that lack a precomputed last_price_eur.
func NewPG(ctx context.Context, dsn string, chfEUR float64) (*PGStore, error) {
	cfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		return nil, fmt.Errorf("parse dsn: %w", err)
	}
	cfg.MaxConns = 8
	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, fmt.Errorf("create pool: %w", err)
	}
	return &PGStore{pool: pool, chfEUR: chfEUR}, nil
}

// Pool exposes the underlying pool for packages that share the connection
// (e.g. the alerts store).
func (s *PGStore) Pool() *pgxpool.Pool { return s.pool }

// Close releases the pool.
func (s *PGStore) Close() { s.pool.Close() }

// Ping verifies connectivity.
func (s *PGStore) Ping(ctx context.Context) error { return s.pool.Ping(ctx) }

// eurPriceExpr is the SQL expression that resolves a row's price to EUR:
// prefer the precomputed last_price_eur; otherwise convert CHF; otherwise assume
// price_raw is already EUR. $1 is the CHF→EUR rate.
const eurPriceExpr = `COALESCE(last_price_eur,
        CASE WHEN currency_raw = 'CHF' THEN price_raw * $1
             ELSE price_raw END)`

// baseWhere builds the shared WHERE clause and argument list. argStart is the
// 1-based index of the next positional argument (args already contains $1=chf).
func (s *PGStore) baseFilter(f Filter, args []any) (string, []any) {
	// $1 is always the CHF rate.
	where := ` WHERE listing_status = 'ACTIVE' AND make ILIKE $2 AND model ILIKE $3`
	args = append(args, f.Make, f.Model)
	next := 4

	if f.YearMin > 0 {
		where += fmt.Sprintf(" AND year >= $%d", next)
		args = append(args, f.YearMin)
		next++
	}
	if f.YearMax > 0 {
		where += fmt.Sprintf(" AND year <= $%d", next)
		args = append(args, f.YearMax)
		next++
	}
	if f.Fuel != "" {
		where += fmt.Sprintf(" AND fuel_type ILIKE $%d", next)
		args = append(args, f.Fuel)
		next++
	}
	if f.MileageMin > 0 {
		where += fmt.Sprintf(" AND mileage_km >= $%d", next)
		args = append(args, f.MileageMin)
		next++
	}
	if f.MileageMax > 0 {
		where += fmt.Sprintf(" AND mileage_km <= $%d", next)
		args = append(args, f.MileageMax)
		next++
	}
	if len(f.Countries) > 0 {
		where += fmt.Sprintf(" AND source_country = ANY($%d)", next)
		args = append(args, f.Countries)
		next++
	}
	return where, args
}

// MarketStats computes per-country percentiles for the cohort.
func (s *PGStore) MarketStats(ctx context.Context, f Filter) ([]CountryStats, error) {
	args := []any{s.chfEUR}
	where, args := s.baseFilter(f, args)

	query := `WITH base AS (
        SELECT source_country AS country, ` + eurPriceExpr + ` AS eur_price
        FROM vehicles` + where + `)
    SELECT country,
           COUNT(*)::int AS n,
           percentile_cont(0.10) WITHIN GROUP (ORDER BY eur_price) AS p10,
           percentile_cont(0.25) WITHIN GROUP (ORDER BY eur_price) AS p25,
           percentile_cont(0.50) WITHIN GROUP (ORDER BY eur_price) AS p50,
           percentile_cont(0.75) WITHIN GROUP (ORDER BY eur_price) AS p75,
           percentile_cont(0.90) WITHIN GROUP (ORDER BY eur_price) AS p90,
           AVG(eur_price) AS avg, MIN(eur_price) AS min, MAX(eur_price) AS max
    FROM base
    WHERE eur_price IS NOT NULL AND eur_price > 0
      AND country IS NOT NULL
    GROUP BY country
    ORDER BY country`

	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("market stats query: %w", err)
	}
	defer rows.Close()

	var out []CountryStats
	for rows.Next() {
		var cs CountryStats
		if err := rows.Scan(&cs.Country, &cs.Count, &cs.P10, &cs.P25, &cs.P50,
			&cs.P75, &cs.P90, &cs.Avg, &cs.Min, &cs.Max); err != nil {
			return nil, fmt.Errorf("scan market stats: %w", err)
		}
		out = append(out, cs)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("market stats rows: %w", err)
	}
	return out, nil
}

// CheapestListings returns the N cheapest active listings in one country.
func (s *PGStore) CheapestListings(ctx context.Context, f Filter, country string, limit int) ([]Listing, error) {
	f.Countries = []string{country}
	args := []any{s.chfEUR}
	where, args := s.baseFilter(f, args)
	limitPos := len(args) + 1
	args = append(args, limit)

	query := `SELECT vehicle_ulid, COALESCE(make,''), COALESCE(model,''),
           COALESCE(year,0), COALESCE(mileage_km,0), COALESCE(fuel_type,''),
           COALESCE(co2_gkm,0), ` + eurPriceExpr + ` AS eur_price,
           COALESCE(price_raw,0), COALESCE(currency_raw,''),
           COALESCE(source_country,''), source_url,
           COALESCE(first_seen_at, now())
    FROM vehicles` + where + `
      AND ` + eurPriceExpr + ` IS NOT NULL AND ` + eurPriceExpr + ` > 0
    ORDER BY eur_price ASC
    LIMIT $` + fmt.Sprint(limitPos)

	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("cheapest listings query: %w", err)
	}
	defer rows.Close()

	out, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (Listing, error) {
		var l Listing
		err := row.Scan(&l.ID, &l.Make, &l.Model, &l.Year, &l.MileageKm, &l.FuelType,
			&l.CO2gkm, &l.PriceEUR, &l.PriceRaw, &l.CurrencyRaw, &l.SourceCountry,
			&l.SourceURL, &l.FirstSeenAt)
		return l, err
	})
	if err != nil {
		return nil, fmt.Errorf("collect listings: %w", err)
	}
	return out, nil
}
