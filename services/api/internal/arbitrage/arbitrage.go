// Package arbitrage finds cross-border price-arbitrage opportunities: a concrete
// cheap listing in one country that can be sold at another country's market
// median after deducting the full landed cost (transport + VAT + registration
// tax + fees).
package arbitrage

import (
	"context"
	"sort"
	"time"

	"cardex.eu/api/internal/landedcost"
	"cardex.eu/api/internal/store"
)

// Defaults for opportunity discovery.
const (
	DefaultMinMarginPct       = 5.0
	DefaultMaxResults         = 20
	DefaultMinSample          = 3
	DefaultListingsPerCountry = 5
)

// Options tunes opportunity discovery.
type Options struct {
	// MinMarginPct is the minimum net-margin percentage to include.
	MinMarginPct float64
	// MaxResults caps the number of opportunities returned.
	MaxResults int
	// BuyCountries / SellCountries optionally restrict source/target markets.
	BuyCountries  []string
	SellCountries []string
	// BERegion selects the Belgian registration scheme when BE is a destination.
	BERegion landedcost.BERegion
	// MinSample is the minimum listings a country needs for its stats to be trusted.
	MinSample int
	// ListingsPerCountry is how many cheapest listings to consider per source country.
	ListingsPerCountry int
}

func (o *Options) applyDefaults() {
	if o.MinMarginPct == 0 {
		o.MinMarginPct = DefaultMinMarginPct
	}
	if o.MaxResults <= 0 {
		o.MaxResults = DefaultMaxResults
	}
	if o.MinSample <= 0 {
		o.MinSample = DefaultMinSample
	}
	if o.ListingsPerCountry <= 0 {
		o.ListingsPerCountry = DefaultListingsPerCountry
	}
}

// Opportunity is one actionable cross-border arbitrage.
type Opportunity struct {
	BuyCountry       string               `json:"buy_country"`
	SellCountry      string               `json:"sell_country"`
	Listing          store.Listing        `json:"listing"`
	SellMarketP50EUR float64              `json:"sell_market_p50_eur"`
	LandedCost       landedcost.Breakdown `json:"landed_cost"`
	NetMarginEUR     float64              `json:"net_margin_eur"`
	MarginPct        float64              `json:"margin_pct"`
}

// Response is the arbitrage payload.
type Response struct {
	Query         interface{}          `json:"query"`
	Currency      string               `json:"currency"`
	Countries     []store.CountryStats `json:"market_context"`
	Opportunities []Opportunity        `json:"opportunities"`
	GeneratedAt   time.Time            `json:"generated_at"`
}

// Service finds arbitrage opportunities from the data store.
type Service struct {
	store store.Store
	now   func() time.Time
}

// New builds a Service.
func New(s store.Store) *Service {
	return &Service{store: s, now: time.Now}
}

// Find computes ranked arbitrage opportunities for the filter cohort. queryEcho
// is echoed back to the client verbatim.
func (s *Service) Find(ctx context.Context, f store.Filter, queryEcho interface{}, opts Options) (Response, error) {
	opts.applyDefaults()

	stats, err := s.store.MarketStats(ctx, f)
	if err != nil {
		return Response{}, err
	}

	// Index trusted per-country stats.
	trusted := make(map[string]store.CountryStats, len(stats))
	for _, cs := range stats {
		if cs.Count >= opts.MinSample && cs.P50 > 0 {
			trusted[cs.Country] = cs
		}
	}

	buySet := toSet(opts.BuyCountries)
	sellSet := toSet(opts.SellCountries)

	// Fetch the cheapest listings per candidate source country once.
	cheapest := make(map[string][]store.Listing)
	for country := range trusted {
		if len(buySet) > 0 && !buySet[country] {
			continue
		}
		listings, err := s.store.CheapestListings(ctx, f, country, opts.ListingsPerCountry)
		if err != nil {
			return Response{}, err
		}
		cheapest[country] = listings
	}

	currentYear := s.now().Year()
	var opportunities []Opportunity

	for sellCountry, sellStats := range trusted {
		if len(sellSet) > 0 && !sellSet[sellCountry] {
			continue
		}
		for buyCountry, listings := range cheapest {
			if buyCountry == sellCountry {
				continue
			}
			for _, l := range listings {
				veh := vehicleFromListing(l, currentYear)
				lc := landedcost.Compute(buyCountry, sellCountry, veh, landedcost.RegistrationOptions{BERegion: opts.BERegion})
				netMargin := round2(sellStats.P50 - lc.TotalLandedCostEUR)
				if netMargin <= 0 || lc.TotalLandedCostEUR <= 0 {
					continue
				}
				marginPct := round2(netMargin / lc.TotalLandedCostEUR * 100)
				if marginPct < opts.MinMarginPct {
					continue
				}
				opportunities = append(opportunities, Opportunity{
					BuyCountry:       buyCountry,
					SellCountry:      sellCountry,
					Listing:          l,
					SellMarketP50EUR: sellStats.P50,
					LandedCost:       lc,
					NetMarginEUR:     netMargin,
					MarginPct:        marginPct,
				})
			}
		}
	}

	sort.Slice(opportunities, func(i, j int) bool {
		return opportunities[i].NetMarginEUR > opportunities[j].NetMarginEUR
	})
	if len(opportunities) > opts.MaxResults {
		opportunities = opportunities[:opts.MaxResults]
	}
	if opportunities == nil {
		opportunities = []Opportunity{}
	}

	return Response{
		Query:         queryEcho,
		Currency:      "EUR",
		Countries:     stats,
		Opportunities: opportunities,
		GeneratedAt:   s.now().UTC(),
	}, nil
}

// vehicleFromListing maps a listing to a landed-cost Vehicle input.
func vehicleFromListing(l store.Listing, currentYear int) landedcost.Vehicle {
	age := 0
	if l.Year > 0 && currentYear >= l.Year {
		age = (currentYear - l.Year) * 12
	}
	return landedcost.Vehicle{
		PriceCents: int64(l.PriceEUR*100 + 0.5),
		CO2gkm:     l.CO2gkm,
		Fuel:       landedcost.NormalizeFuel(l.FuelType),
		AgeMonths:  age,
		Km:         l.MileageKm,
		PowerKW:    0,
	}
}

func toSet(items []string) map[string]bool {
	if len(items) == 0 {
		return nil
	}
	m := make(map[string]bool, len(items))
	for _, s := range items {
		m[s] = true
	}
	return m
}

func round2(v float64) float64 {
	return float64(int64(v*100+0.5)) / 100.0
}
