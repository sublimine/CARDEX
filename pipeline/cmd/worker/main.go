package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"runtime"
	"strconv"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
	"github.com/uber/h3-go/v4"
)

var rdb *redis.Client

type VehiclePayload struct {
	ID                string  `json:"ID"`
	Source            string  `json:"Source"`
	VIN               string  `json:"vin"` // Captura el test payload
	Color             string  `json:"Color"`
	Currency          string  `json:"Currency"`
	DamageCode        string  `json:"DamageCode"`
	Lat               float64 `json:"Lat"`
	Lng               float64 `json:"Lng"`
	Mileage           int     `json:"Mileage"`
	PriceRaw          float64 `json:"PriceRaw"`
	GrossPhysicalCost float64 `json:"GrossPhysicalCost"`
	ThumbURL          string  `json:"ThumbURL"`
	RawDescription    string  `json:"RawDescription"`
	H3Index           string  `json:"H3Index"`
}

func init() {
	rdb = redis.NewClient(&redis.Options{Addr: "127.0.0.1:6379", PoolSize: 2000})
}

// 1. DEDUPLICACIÓN O(1) (Filtros de Bloom)
func isDuplicate(ctx context.Context, fingerprint string) bool {
	exists, err := rdb.Do(ctx, "BF.ADD", "bloom:vehicles", fingerprint).Bool()
	if err != nil {
		// Fallback silencioso si RedisBloom no está cargado en el contenedor local
		if strings.Contains(err.Error(), "unknown command") {
			log.Printf("[WARNING] Módulo RedisBloom ausente. Saltando deduplicación para %s", fingerprint)
			return false
		}
		return false
	}
	return !exists
}

// 2. FAIL-CLOSED ORACLE (Bomba de Divisas Desactivada)
func applyBankersBuffer(price float64, currency string) (float64, error) {
	if currency == "" || currency == "EUR" {
		return price, nil
	}
	bufferStr, err := rdb.HGet(context.Background(), "fx_buffer", currency).Result()
	if err != nil || bufferStr == "" {
		return 0, fmt.Errorf("FATAL_CURRENCY_FAIL: [%s]", currency)
	}
	bufferMultiplier, _ := strconv.ParseFloat(bufferStr, 64)
	if bufferMultiplier <= 0 {
		return 0, fmt.Errorf("FATAL_CURRENCY_ZERO")
	}
	return price * bufferMultiplier, nil
}

func calculateGrossPhysicalCost(v *VehiclePayload) (float64, error) {
	basePrice, err := applyBankersBuffer(v.PriceRaw, v.Currency)
	if err != nil {
		return 0, err
	}
	if v.DamageCode != "" {
		costStr, err := rdb.HGet(context.Background(), "b2b_rosetta:"+strings.ToUpper(v.Source), v.DamageCode).Result()
		if err == nil && costStr != "" {
			repairCost, _ := strconv.ParseFloat(costStr, 64)
			return basePrice + repairCost, nil
		}
	}
	return basePrice, nil
}

func processPipeline(msgID string, rawJSON string) {
	ctx := context.Background()
	var v VehiclePayload
	if err := json.Unmarshal([]byte(rawJSON), &v); err != nil {
		log.Printf("[DROP] JSON corrupto: %v", err)
		rdb.XAck(ctx, "stream:ingestion_raw", "cg_pipeline", msgID)
		return
	}

	hashInput := sha256.Sum256([]byte(v.VIN + strings.ToLower(v.Color) + strconv.Itoa(v.Mileage)))
	fingerprint := hex.EncodeToString(hashInput[:])

	if isDuplicate(ctx, fingerprint) {
		log.Printf("[DROP] Vehículo duplicado detectado: %s", fingerprint)
		rdb.XAck(ctx, "stream:ingestion_raw", "cg_pipeline", msgID)
		return
	}

	grossCost, err := calculateGrossPhysicalCost(&v)
	if err != nil {
		log.Printf("[DROP CRÍTICO] Divisa no soportada o coste inválido: %v", err)
		rdb.XAck(ctx, "stream:ingestion_raw", "cg_pipeline", msgID)
		return
	}
	v.GrossPhysicalCost = grossCost
	v.Currency = "EUR"

	if v.Lat != 0 && v.Lng != 0 {
		latLng := h3.NewLatLng(v.Lat, v.Lng)
		h3Idx, err := h3.LatLngToCell(latLng, 4)
		if err == nil {
			v.H3Index = h3Idx.String()
		}
	}

	finalJSON, _ := json.Marshal(v)
	pipe := rdb.Pipeline()
	pipe.XAdd(ctx, &redis.XAddArgs{Stream: "stream:db_write", Values: map[string]interface{}{"data": finalJSON}})

	if v.ThumbURL != "" {
		pipe.XAdd(ctx, &redis.XAddArgs{
			Stream: "stream:visual_audit",
			MaxLen: 1000,
			Approx: true,
			Values: map[string]interface{}{"hash": fingerprint, "url": v.ThumbURL},
		})
	}
	pipe.XAck(ctx, "stream:ingestion_raw", "cg_pipeline", msgID)
	_, err = pipe.Exec(ctx)
	if err == nil {
		log.Printf("[HFT] Activo procesado y enrutado a Fase 5 (VIN: %s)", v.VIN)
	}
}

func main() {
	runtime.GOMAXPROCS(8)
	log.Println("[V2.0] Tubería HFT Activa. RedisBloom, Uber H3 y Gross Physical Cost en línea.")

	// Tolerancia si el grupo ya existe
	rdb.XGroupCreateMkStream(context.Background(), "stream:ingestion_raw", "cg_pipeline", "$")

	for {
		msgs, err := rdb.XReadGroup(context.Background(), &redis.XReadGroupArgs{
			Group:    "cg_pipeline",
			Consumer: "worker_pipeline",
			Streams:  []string{"stream:ingestion_raw", ">"},
			Count:    100,
			Block:    2000 * time.Millisecond,
		}).Result()

		if err != nil || len(msgs) == 0 {
			continue
		}

		for _, msg := range msgs[0].Messages {
			processPipeline(msg.ID, msg.Values["payload"].(string))
		}
	}
}
