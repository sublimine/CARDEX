package marketprice

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"time"

	"cardex.eu/api/internal/httpx"
	"cardex.eu/api/internal/metrics"
	"cardex.eu/api/internal/redisx"
	"cardex.eu/api/internal/restparams"
)

const routeLabel = "/api/v1/market-price"

// Handler returns the HTTP handler for GET /api/v1/market-price. Responses are
// cached in Redis for ttl keyed on the request query; each query is bounded by
// queryTimeout.
func Handler(svc *Service, cache *redisx.Client, ttl, queryTimeout time.Duration, log *slog.Logger) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		f, err := restparams.ParseFilter(r.URL.Query())
		if err != nil {
			httpx.WriteError(w, http.StatusBadRequest, "invalid_parameters", err.Error())
			return
		}

		cacheKey := httpx.CacheKey(routeLabel, r.URL.Query().Encode())
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

		resp, err := svc.Query(ctx, f)
		if err != nil {
			log.Error("market-price query failed", "err", err, "request_id", httpx.RequestID(r.Context()))
			httpx.WriteError(w, http.StatusInternalServerError, "query_failed", "failed to compute market price")
			return
		}

		body, err := json.Marshal(resp)
		if err != nil {
			httpx.WriteError(w, http.StatusInternalServerError, "encode_failed", "failed to encode response")
			return
		}
		if cache != nil {
			if err := cache.SetCached(r.Context(), cacheKey, body, ttl); err != nil {
				log.Warn("market-price cache set failed", "err", err)
			}
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		w.Header().Set("X-Cache", "MISS")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(body)
	}
}
