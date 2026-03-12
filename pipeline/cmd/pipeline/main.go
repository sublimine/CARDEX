// Package main implements the CARDEX HFT Pipeline (Phase 4).
// Consumes stream:ingestion_raw, deduplicates via RedisBloom,
// computes H3 geospatial index, converts FX, and writes to stream:db_write.
package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/cardex/pipeline/pkg/bloom"
	"github.com/cardex/pipeline/pkg/fx"
	"github.com/cardex/pipeline/pkg/h3"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/oklog/ulid/v2"
	"github.com/redis/go-redis/v9"
)

const (
	streamIngestionRaw = "stream:ingestion_raw"
	streamDbWrite      = "stream:db_write"
	consumerGroup      = "cg_pipeline"
	consumerName       = "pipeline-1"
	bloomKey           = "bloom:vehicles"
	backpressureLimit  = 50000
)

// vehiclePayload matches the JSON structure from gateway stream:ingestion_raw.
type vehiclePayload struct {
	VIN          string  `json:"vin,omitempty"`
	SourceID     string  `json:"source_id"`
	Make         string  `json:"make"`
	Model        string  `json:"model"`
	Year         int     `json:"year"`
	MileageKM    int     `json:"mileage_km"`
	Color        string  `json:"color,omitempty"`
	FuelType     string  `json:"fuel_type,omitempty"`
	Transmission string  `json:"transmission,omitempty"`
	CO2GKM       int     `json:"co2_gkm,omitempty"`
	PowerKW      int     `json:"power_kw,omitempty"`
	PriceRaw     float64 `json:"price_raw"`
	CurrencyRaw  string  `json:"currency_raw"`
	Lat          float64 `json:"lat,omitempty"`
	Lng          float64 `json:"lng,omitempty"`
	Description  string  `json:"description,omitempty"`
	SellerType   string  `json:"seller_type,omitempty"`
	SellerVATID  string  `json:"seller_vat_id,omitempty"`
}

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	rdb := redis.NewClient(&redis.Options{
		Addr:     envOrDefault("REDIS_ADDR", "127.0.0.1:6379"),
		Password: envOrDefault("REDIS_PASS", ""),
		PoolSize: 50,
	})
	if err := rdb.Ping(ctx).Err(); err != nil {
		slog.Error("phase4: redis connection failed", "error", err)
		os.Exit(1)
	}
	defer rdb.Close()
	slog.Info("phase4: redis connected")

	if err := rdb.XGroupCreateMkStream(ctx, streamIngestionRaw, consumerGroup, "0").Err(); err != nil && !strings.Contains(err.Error(), "BUSYGROUP") {
		slog.Warn("phase4: xgroup create", "stream", streamIngestionRaw, "error", err)
	}

	pgURL := envOrDefault("DATABASE_URL", "postgres://cardex:cardex_dev_only@127.0.0.1:5432/cardex?sslmode=disable")
	pool, err := pgxpool.New(ctx, pgURL)
	if err != nil {
		slog.Error("phase4: pgxpool connect failed", "error", err)
		os.Exit(1)
	}
	defer pool.Close()
	if err := pool.Ping(ctx); err != nil {
		slog.Error("phase4: postgres ping failed", "error", err)
		os.Exit(1)
	}
	slog.Info("phase4: postgres connected")

	bloomFilter := bloom.New(rdb, bloomKey)
	fxBuffer := fx.New(rdb)
	if err := fxBuffer.Refresh(ctx); err != nil {
		slog.Error("phase4: fx buffer refresh failed at startup", "error", err)
		os.Exit(1)
	}
	slog.Info("phase4: fx buffer refreshed")

	go refreshFXPeriodically(ctx, fxBuffer, time.Hour)

	idx := &h3.Indexer{}

	slog.Info("phase4: pipeline starting consumer loop")

	runConsumerLoop(ctx, rdb, pool, bloomFilter, fxBuffer, idx)

	slog.Info("phase4: pipeline stopped")
}

func refreshFXPeriodically(ctx context.Context, fxBuf *fx.Buffer, interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := fxBuf.Refresh(ctx); err != nil {
				slog.Error("phase4: fx buffer periodic refresh failed", "error", err)
			} else {
				slog.Info("phase4: fx buffer refreshed")
			}
		}
	}
}

func runConsumerLoop(ctx context.Context, rdb *redis.Client, pool *pgxpool.Pool, b *bloom.Bloom, fxBuf *fx.Buffer, idx *h3.Indexer) {
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		lenDbWrite, err := rdb.XLen(ctx, streamDbWrite).Result()
		if err != nil {
			slog.Error("phase4: xlen stream:db_write failed", "error", err)
			time.Sleep(1 * time.Second)
			continue
		}
		if lenDbWrite > backpressureLimit {
			slog.Warn("phase4: backpressure", "stream", streamDbWrite, "len", lenDbWrite, "limit", backpressureLimit)
			time.Sleep(1 * time.Second)
			continue
		}

		streams, err := rdb.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group:    consumerGroup,
			Consumer: consumerName,
			Streams:  []string{streamIngestionRaw, ">"},
			Count:    10,
			Block:    2 * time.Second,
		}).Result()
		if err != nil && err != redis.Nil {
			slog.Error("phase4: xreadgroup failed", "stream", streamIngestionRaw, "error", err)
			time.Sleep(1 * time.Second)
			continue
		}
		if err == redis.Nil || len(streams) == 0 || len(streams[0].Messages) == 0 {
			continue
		}

		for _, msg := range streams[0].Messages {
			processMessage(ctx, rdb, pool, b, fxBuf, idx, streamIngestionRaw, msg)
		}
	}
}

func processMessage(ctx context.Context, rdb *redis.Client, pool *pgxpool.Pool, b *bloom.Bloom, fxBuf *fx.Buffer, idx *h3.Indexer, stream string, msg redis.XMessage) {
	start := time.Now()
	payloadStr, ok := msg.Values["payload"].(string)
	if !ok {
		slog.Error("phase4: payload missing or not string", "stream", stream, "id", msg.ID)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}
	source, _ := msg.Values["source"].(string)
	channel, _ := msg.Values["channel"].(string)
	if source == "" {
		source = "UNKNOWN"
	}
	if channel == "" {
		channel = "B2B_WEBHOOK"
	}

	var v vehiclePayload
	if err := json.Unmarshal([]byte(payloadStr), &v); err != nil {
		slog.Error("phase4: invalid payload json", "stream", stream, "id", msg.ID, "error", err)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	fingerprint := computeFingerprint(v.VIN, v.Color, v.MileageKM)

	exists, err := b.Exists(ctx, fingerprint)
	if err != nil {
		slog.Error("phase4: bloom exists failed", "fingerprint", fingerprint, "error", err)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}
	if exists {
		slog.Info("phase4: duplicate skipped", "fingerprint", fingerprint, "source_id", v.SourceID, "latency_ms", time.Since(start).Milliseconds())
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	if err := b.Add(ctx, fingerprint); err != nil {
		slog.Error("phase4: bloom add failed", "fingerprint", fingerprint, "error", err)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	priceEUR, err := fxBuf.ToEUR(ctx, v.PriceRaw, v.CurrencyRaw)
	if err != nil {
		slog.Warn("phase4: fx fail-closed", "fingerprint", fingerprint, "currency", v.CurrencyRaw, "error", err)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	if priceEUR < 1000 || priceEUR > 500000 {
		slog.Info("phase4: outlier discarded", "reason", "OUTLIER_PRICE", "fingerprint", fingerprint, "price_eur", priceEUR)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	var h3Res4, h3Res7 string
	if v.Lat != 0 || v.Lng != 0 {
		h3Res4, h3Res7, err = idx.Compute(v.Lat, v.Lng)
		if err != nil {
			slog.Warn("phase4: h3 compute failed", "fingerprint", fingerprint, "lat", v.Lat, "lng", v.Lng, "error", err)
		}
	}

	vehicleULID := ulid.Make().String()

	err = pool.QueryRow(ctx, `
		INSERT INTO vehicles (
			vehicle_ulid, fingerprint_sha256, vin, source_id, source_platform, ingestion_channel,
			make, model, year, mileage_km, color, fuel_type, transmission, co2_gkm, power_kw,
			price_raw, currency_raw, gross_physical_cost_eur, lat, lng, h3_index_res4, h3_index_res7,
			raw_description, seller_type, seller_vat_id, lifecycle_status
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, 'INGESTED')
		ON CONFLICT (fingerprint_sha256) DO UPDATE SET
			last_updated_at = NOW(),
			price_raw = EXCLUDED.price_raw,
			currency_raw = EXCLUDED.currency_raw,
			gross_physical_cost_eur = EXCLUDED.gross_physical_cost_eur
		RETURNING vehicle_ulid
	`,
		vehicleULID, fingerprint, nullStr(v.VIN), v.SourceID, source, channel,
		v.Make, v.Model, v.Year, v.MileageKM, nullStr(v.Color), nullStr(v.FuelType), nullStr(v.Transmission), v.CO2GKM, v.PowerKW,
		v.PriceRaw, v.CurrencyRaw, priceEUR, nullFloat(v.Lat), nullFloat(v.Lng), nullStr(h3Res4), nullStr(h3Res7),
		nullStr(v.Description), nullStr(v.SellerType), nullStr(v.SellerVATID),
	).Scan(&vehicleULID)
	if err != nil {
		slog.Error("phase4: insert vehicles failed", "fingerprint", fingerprint, "error", err)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	_, err = rdb.XAdd(ctx, &redis.XAddArgs{
		Stream: streamDbWrite,
		Values: map[string]interface{}{
			"vehicle_ulid": vehicleULID,
			"fingerprint":  fingerprint,
		},
	}).Result()
	if err != nil {
		slog.Error("phase4: xadd stream:db_write failed", "vehicle_ulid", vehicleULID, "error", err)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	ackMessage(ctx, rdb, stream, msg.ID)
	slog.Info("phase4: vehicle processed",
		"vehicle_ulid", vehicleULID,
		"fingerprint", fingerprint,
		"source", source,
		"source_id", v.SourceID,
		"latency_ms", time.Since(start).Milliseconds())
}

func computeFingerprint(vin, color string, mileageKM int) string {
	lowerColor := strings.ToLower(color)
	input := fmt.Sprintf("%s%s%d", vin, lowerColor, mileageKM)
	hash := sha256.Sum256([]byte(input))
	return hex.EncodeToString(hash[:])
}

func ackMessage(ctx context.Context, rdb *redis.Client, stream, id string) {
	if err := rdb.XAck(ctx, stream, consumerGroup, id).Err(); err != nil {
		slog.Error("phase4: xack failed", "stream", stream, "id", id, "error", err)
	}
}

func nullStr(s string) interface{} {
	if s == "" {
		return nil
	}
	return s
}

func nullFloat(f float64) interface{} {
	if f == 0 {
		return nil
	}
	return f
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
