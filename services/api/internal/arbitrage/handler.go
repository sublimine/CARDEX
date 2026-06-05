package arbitrage

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"cardex.eu/api/internal/httpx"
	"cardex.eu/api/internal/landedcost"
	"cardex.eu/api/internal/metrics"
	"cardex.eu/api/internal/redisx"
	"cardex.eu/api/internal/restparams"
)

const routeLabel = "/api/v1/arbitrage"

// queryEcho mirrors the resolved request back to the client.
type queryEcho struct {
	Make          string   `json:"make"`
	Model         string   `json:"model"`
	YearMin       int      `json:"year_min,omitempty"`
	YearMax       int      `json:"year_max,omitempty"`
	Fuel          string   `json:"fuel,omitempty"`
	MileageMin    int      `json:"mileage_min,omitempty"`
	MileageMax    int      `json:"mileage_max,omitempty"`
	MinMarginPct  float64  `json:"min_margin_pct"`
	BuyCountries  []string `json:"buy_countries,omitempty"`
	SellCountries []string `json:"sell_countries,omitempty"`
}

// Handler returns the HTTP handler for GET /api/v1/arbitrage. Each query is
// bounded by queryTimeout.
func Handler(svc *Service, cache *redisx.Client, ttl, queryTimeout time.Duration, log *slog.Logger) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		f, err := restparams.ParseFilter(q)
		if err != nil {
			httpx.WriteError(w, http.StatusBadRequest, "invalid_parameters", err.Error())
			return
		}

		minMargin, err := restparams.ParsePositiveFloat(q, "min_margin_pct", DefaultMinMarginPct)
		if err != nil {
			httpx.WriteError(w, http.StatusBadRequest, "invalid_parameters", err.Error())
			return
		}
		maxResults, err := restparams.ParseLimit(q, "max_results", DefaultMaxResults, 100)
		if err != nil {
			httpx.WriteError(w, http.StatusBadRequest, "invalid_parameters", err.Error())
			return
		}
		buyCountries, err := parseCountryList(q.Get("buy_country"))
		if err != nil {
			httpx.WriteError(w, http.StatusBadRequest, "invalid_parameters", err.Error())
			return
		}
		sellCountries, err := parseCountryList(q.Get("sell_country"))
		if err != nil {
			httpx.WriteError(w, http.StatusBadRequest, "invalid_parameters", err.Error())
			return
		}
		region, err := parseBERegion(q.Get("be_region"))
		if err != nil {
			httpx.WriteError(w, http.StatusBadRequest, "invalid_parameters", err.Error())
			return
		}

		opts := Options{
			MinMarginPct:  minMargin,
			MaxResults:    maxResults,
			BuyCountries:  buyCountries,
			SellCountries: sellCountries,
			BERegion:      region,
		}
		echo := queryEcho{
			Make: f.Make, Model: f.Model, YearMin: f.YearMin, YearMax: f.YearMax,
			Fuel: f.Fuel, MileageMin: f.MileageMin, MileageMax: f.MileageMax,
			MinMarginPct: minMargin, BuyCountries: buyCountries, SellCountries: sellCountries,
		}

		cacheKey := httpx.CacheKey(routeLabel, q.Encode())
		if cache != nil {
			if raw, ok, _ := cache.GetCached(r.Context(), cacheKey); ok {
				metrics.CacheHits.WithLabelValues(routeLabel).Inc()
				w.Header().Set("Content-Type", "application/json; charset=utf-8")
				w.Header().Set("X-Cache", "HIT")
				w.WriteHeader(http.StatusOK)
				_, _ = w.Write(raw)
				return
			}
			metrics.CacheMisses.WithLabelValues(routeLabel).Inc()
		}

		ctx, cancel := context.WithTimeout(r.Context(), queryTimeout)
		defer cancel()

		resp, err := svc.Find(ctx, f, echo, opts)
		if err != nil {
			log.Error("arbitrage query failed", "err", err, "request_id", httpx.RequestID(r.Context()))
			httpx.WriteError(w, http.StatusInternalServerError, "query_failed", "failed to compute arbitrage opportunities")
			return
		}

		body, err := json.Marshal(resp)
		if err != nil {
			httpx.WriteError(w, http.StatusInternalServerError, "encode_failed", "failed to encode response")
			return
		}
		if cache != nil {
			if err := cache.SetCached(r.Context(), cacheKey, body, ttl); err != nil {
				log.Warn("arbitrage cache set failed", "err", err)
			}
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		w.Header().Set("X-Cache", "MISS")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(body)
	}
}

// parseCountryList validates a CSV country list against the supported set.
func parseCountryList(raw string) ([]string, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, nil
	}
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		code := strings.ToUpper(strings.TrimSpace(p))
		if code == "" {
			continue
		}
		if !restparams.SupportedCountries[code] {
			return nil, fmt.Errorf("unsupported country %q; supported: DE, FR, ES, NL, BE, CH", code)
		}
		out = append(out, code)
	}
	return out, nil
}

func parseBERegion(raw string) (landedcost.BERegion, error) {
	switch strings.ToUpper(strings.TrimSpace(raw)) {
	case "", "FLANDERS":
		return landedcost.BEFlanders, nil
	case "WALLONIA":
		return landedcost.BEWallonia, nil
	case "BRUSSELS":
		return landedcost.BEBrussels, nil
	default:
		return "", fmt.Errorf("invalid be_region %q; supported: FLANDERS, WALLONIA, BRUSSELS", raw)
	}
}
