package main

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"runtime"
	"time"

	"github.com/redis/go-redis/v9"
)

var rdb *redis.Client

// Simulación de Secret en Bóveda KMS
const secretKey = "CARDEX_INSTITUTIONAL_HMAC_SECRET"

type VehiclePayload struct {
	VIN               string  `json:"vin"`
	GrossPhysicalCost float64 `json:"GrossPhysicalCost"`
	CO2               int     `json:"co2"`
	AgeMonths         int     `json:"age_months"`
	OriginCountry     string  `json:"origin_country"`
	TargetMarket      string  `json:"target_market"`
	DaysOnMarket      int     `json:"days_on_market"`
	TaxStatus         string  `json:"TaxStatus"`
}

type MarketQuote struct {
	VIN           string  `json:"vin"`
	NetLandedCost float64 `json:"nlc"`
	QuoteID       string  `json:"quote_id"`
	SDIAlert      bool    `json:"sdi_alert"`
}

func init() {
	rdb = redis.NewClient(&redis.Options{Addr: "127.0.0.1:6379", PoolSize: 2000})

	// Pre-cargamos la Matriz Logística Base en el arranque
	rdb.HSet(context.Background(), "logistics:worst_case", "DE", "1050.00", "FR", "750.00", "NL", "950.00")

	// Pre-cargamos el LUA Mutex Atómico para Fase 8 (Dark Pool)
	luaMutex := `
	KEYS[1] = "lock:vehicle_hash"
	ARGV[1] = "buyer_id"
	ARGV[2] = "quote_id_hmac"

	if redis.call("EXISTS", KEYS[1]) == 1 then
		return -1 -- SOLD_OUT
	end

	local current_quote = redis.call("HGET", "vehicle_state:"..KEYS[1], "quote_id")
	if current_quote and current_quote ~= ARGV[2] then
		return -2 -- PRICE_MISMATCH
	end

	redis.call("SET", KEYS[1], ARGV[1], "EX", 120) -- Escrow Lógico 120s
	return 1 -- ACEPTADO
	`
	_, err := rdb.ScriptLoad(context.Background(), luaMutex).Result()
	if err != nil {
		log.Fatalf("FATAL: Fallo al inyectar el LUA Mutex: %v", err)
	}
}

func generateQuoteID(vin string, price float64) string {
	payload := fmt.Sprintf("%s_%.2f_%d", vin, price, time.Now().UnixNano())
	h := hmac.New(sha256.New, []byte(secretKey))
	h.Write([]byte(payload))
	return hex.EncodeToString(h.Sum(nil))
}

func processFinancials(msgID string, rawJSON string) {
	var v VehiclePayload
	if err := json.Unmarshal([]byte(rawJSON), &v); err != nil {
		return
	}

	if v.TargetMarket == "" {
		v.TargetMarket = "ES"
	}
	if v.OriginCountry == "" {
		v.OriginCountry = "DE"
	} // Asumimos DE para el test

	worstStr, _ := rdb.HGet(context.Background(), "logistics:worst_case", v.OriginCountry).Result()
	var logistics float64 = 950.0
	if worstStr != "" {
		fmt.Sscanf(worstStr, "%f", &logistics)
	}

	// Cálculo del Net Landed Cost
	nlc := v.GrossPhysicalCost + logistics

	// Generación de Quote inmutable
	quoteID := generateQuoteID(v.VIN, nlc)

	// Seller Desperation Index (SDI) - Algoritmo acantilado
	isDesperate := (v.DaysOnMarket >= 58 && v.DaysOnMarket <= 65) || (v.DaysOnMarket >= 88 && v.DaysOnMarket <= 95)

	quote := MarketQuote{
		VIN:           v.VIN,
		NetLandedCost: nlc,
		QuoteID:       quoteID,
		SDIAlert:      isDesperate,
	}

	payload, _ := json.Marshal(quote)

	pipe := rdb.Pipeline()
	// PARCHE DE TELEMETRÍA: Guardamos el estado completo para la Mesa de Decisiones
	pipe.HSet(context.Background(), "vehicle_state:"+v.VIN, map[string]interface{}{
		"quote_id":     quoteID,
		"nlc":          fmt.Sprintf("%.2f", nlc),
		"legal_status": v.TaxStatus,
	})
	pipe.XAdd(context.Background(), &redis.XAddArgs{
		Stream: "stream:darkpool_ready",
		Values: map[string]interface{}{"data": payload},
	})
	pipe.XAck(context.Background(), "stream:market_ready", "cg_alpha", msgID)
	_, err := pipe.Exec(context.Background())

	if err == nil {
		log.Printf("[ALPHA ENGINE] Cotización Sellada. VIN: %s | NLC: %.2f | QuoteID: %s", v.VIN, nlc, quoteID[:8]+"...")
	}
}

func main() {
	runtime.GOMAXPROCS(8)
	log.Println("[V2.0] Alpha Engine Activo. LUA Mutex Inyectado y NLC Transfronterizo Operando.")

	rdb.XGroupCreateMkStream(context.Background(), "stream:market_ready", "cg_alpha", "$")

	for {
		msgs, err := rdb.XReadGroup(context.Background(), &redis.XReadGroupArgs{
			Group:    "cg_alpha",
			Consumer: "worker_alpha",
			Streams:  []string{"stream:market_ready", ">"},
			Count:    100,
			Block:    2000 * time.Millisecond,
		}).Result()

		if err != nil || len(msgs) == 0 {
			continue
		}

		for _, msg := range msgs[0].Messages {
			processFinancials(msg.ID, msg.Values["data"].(string))
		}
	}
}
