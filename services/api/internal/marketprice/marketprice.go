// Package marketprice serves per-country price distributions (P10/P25/P50/P75/P90)
// for a vehicle cohort defined by make/model/year/fuel/mileage.
package marketprice

import (
	"context"

	"cardex.eu/api/internal/store"
)

// Service computes market-price statistics from the data store.
type Service struct {
	store store.Store
}

// New builds a Service.
func New(s store.Store) *Service { return &Service{store: s} }

// QueryEcho echoes the resolved filter back to the client.
type QueryEcho struct {
	Make       string   `json:"make"`
	Model      string   `json:"model"`
	YearMin    int      `json:"year_min,omitempty"`
	YearMax    int      `json:"year_max,omitempty"`
	Fuel       string   `json:"fuel,omitempty"`
	MileageMin int      `json:"mileage_min,omitempty"`
	MileageMax int      `json:"mileage_max,omitempty"`
	Countries  []string `json:"countries,omitempty"`
}

// Response is the market-price payload. All prices are EUR.
type Response struct {
	Query     QueryEcho            `json:"query"`
	Currency  string               `json:"currency"`
	Countries []store.CountryStats `json:"countries"`
}

// Query returns the per-country price distribution for the filter cohort.
func (s *Service) Query(ctx context.Context, f store.Filter) (Response, error) {
	stats, err := s.store.MarketStats(ctx, f)
	if err != nil {
		return Response{}, err
	}
	return Response{
		Query:     echo(f),
		Currency:  "EUR",
		Countries: stats,
	}, nil
}

func echo(f store.Filter) QueryEcho {
	return QueryEcho{
		Make:       f.Make,
		Model:      f.Model,
		YearMin:    f.YearMin,
		YearMax:    f.YearMax,
		Fuel:       f.Fuel,
		MileageMin: f.MileageMin,
		MileageMax: f.MileageMax,
		Countries:  f.Countries,
	}
}
