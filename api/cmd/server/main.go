package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"runtime"
	"strings"

	"github.com/redis/go-redis/v9"
)

var rdb *redis.Client

type Opportunity struct {
	VIN           string `json:"vin"`
	QuoteID       string `json:"quote_id"`
	LegalStatus   string `json:"legal_status,omitempty"`
	NetLandedCost string `json:"nlc,omitempty"`
}

func init() {
	rdb = redis.NewClient(&redis.Options{Addr: "127.0.0.1:6379", PoolSize: 500})
}

// Middleware para habilitar CORS hacia el Frontend B2B
func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		if r.Method == "OPTIONS" {
			w.WriteHeader(http.StatusOK)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// Endpoint: /api/v1/market/opportunities
func getOpportunities(w http.ResponseWriter, r *http.Request) {
	ctx := context.Background()

	// Escaneo de llaves de estado (En producción se usa Redis Search o ClickHouse, SCAN es para Fase 1)
	var cursor uint64
	var keys []string
	var err error

	// Recuperar hasta 100 vehículos procesados
	keys, _, err = rdb.Scan(ctx, cursor, "vehicle_state:*", 100).Result()
	if err != nil {
		http.Error(w, `{"error": "DATABASE_TIMEOUT"}`, http.StatusInternalServerError)
		return
	}

	var opportunities []Opportunity

	for _, key := range keys {
		data, err := rdb.HGetAll(ctx, key).Result()
		if err != nil || len(data) == 0 {
			continue
		}

		vin := strings.Replace(key, "vehicle_state:", "", 1)

		opp := Opportunity{
			VIN:           vin,
			QuoteID:       data["quote_id"],
			LegalStatus:   data["legal_status"],
			NetLandedCost: data["nlc"],
		}
		opportunities = append(opportunities, opp)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status": "success",
		"count":  len(opportunities),
		"data":   opportunities,
	})
}

func main() {
	runtime.GOMAXPROCS(4)

	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/market/opportunities", getOpportunities)

	handler := corsMiddleware(mux)

	log.Println("[API] REST B2B Market API Activa en TCP:8083")
	if err := http.ListenAndServe("0.0.0.0:8083", handler); err != nil {
		log.Fatal(err)
	}
}
