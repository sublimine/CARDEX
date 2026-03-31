// Package main implements the CARDEX Forensic Crucible (Phase 5).
// Consumes stream:db_write, classifies tax status via cascade, updates vehicles, writes to stream:classified.
// See .cursor/prompts/phase-05-forensics.md for full specification.
package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/cardex/forensics/pkg/ahocorasick"
	"github.com/cardex/forensics/pkg/taxhunter"
	"github.com/cardex/forensics/pkg/vies"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

const (
	streamDbWrite     = "stream:db_write"
	streamClassified  = "stream:classified"
	consumerGroup     = "cg_forensics"
	consumerName      = "forensics-1"
	backpressureLimit = 50000
	viesTimeout       = 200 * time.Millisecond
)

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
		slog.Error("phase5: redis connection failed", "error", err)
		os.Exit(1)
	}
	defer rdb.Close()
	slog.Info("phase5: redis connected")

	pgURL := envOrDefault("DATABASE_URL", "postgres://cardex:cardex_dev_only@127.0.0.1:5432/cardex?sslmode=disable")
	pool, err := pgxpool.New(ctx, pgURL)
	if err != nil {
		slog.Error("phase5: pgxpool connect failed", "error", err)
		os.Exit(1)
	}
	defer pool.Close()
	if err := pool.Ping(ctx); err != nil {
		slog.Error("phase5: postgres ping failed", "error", err)
		os.Exit(1)
	}
	slog.Info("phase5: postgres connected")

	if err := rdb.XGroupCreateMkStream(ctx, streamDbWrite, consumerGroup, "0").Err(); err != nil && !strings.Contains(err.Error(), "BUSYGROUP") {
		slog.Warn("phase5: xgroup create", "stream", streamDbWrite, "error", err)
	}

	scanner := ahocorasick.New()
	viesClient := vies.New(viesTimeout)
	classifier := taxhunter.New(scanner, viesClient, rdb)

	slog.Info("phase5: forensics starting consumer loop")

	runConsumerLoop(ctx, rdb, pool, classifier)

	slog.Info("phase5: forensics stopped")
}

func runConsumerLoop(ctx context.Context, rdb *redis.Client, pool *pgxpool.Pool, classifier *taxhunter.Classifier) {
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		lenClassified, err := rdb.XLen(ctx, streamClassified).Result()
		if err != nil {
			slog.Error("phase5: xlen stream:classified failed", "error", err)
			time.Sleep(1 * time.Second)
			continue
		}
		if lenClassified > backpressureLimit {
			slog.Warn("phase5: backpressure", "stream", streamClassified, "len", lenClassified, "limit", backpressureLimit)
			time.Sleep(1 * time.Second)
			continue
		}

		streams, err := rdb.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group:    consumerGroup,
			Consumer: consumerName,
			Streams:  []string{streamDbWrite, ">"},
			Count:    10,
			Block:    2 * time.Second,
		}).Result()
		if err != nil && err != redis.Nil {
			slog.Error("phase5: xreadgroup failed", "stream", streamDbWrite, "error", err)
			time.Sleep(1 * time.Second)
			continue
		}
		if err == redis.Nil || len(streams) == 0 || len(streams[0].Messages) == 0 {
			continue
		}

		for _, msg := range streams[0].Messages {
			processMessage(ctx, rdb, pool, classifier, streamDbWrite, msg)
		}
	}
}

func processMessage(ctx context.Context, rdb *redis.Client, pool *pgxpool.Pool, classifier *taxhunter.Classifier, stream string, msg redis.XMessage) {
	start := time.Now()

	vehicleULID, _ := msg.Values["vehicle_ulid"].(string)
	fingerprint, _ := msg.Values["fingerprint"].(string)
	if vehicleULID == "" {
		slog.Error("phase5: vehicle_ulid missing", "stream", stream, "id", msg.ID)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	var rawDescription, sellerType, sellerVatID, originCountry string
	err := pool.QueryRow(ctx, `
		SELECT COALESCE(raw_description,''), COALESCE(seller_type,''), COALESCE(seller_vat_id,''), COALESCE(origin_country,'DE')
		FROM vehicles WHERE vehicle_ulid = $1
	`, vehicleULID).Scan(&rawDescription, &sellerType, &sellerVatID, &originCountry)
	if err != nil {
		slog.Error("phase5: vehicle query failed", "vehicle_ulid", vehicleULID, "error", err)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	input := taxhunter.VehicleInput{
		VehicleULID:   vehicleULID,
		Description:   rawDescription,
		SellerType:    sellerType,
		SellerVATID:   sellerVatID,
		OriginCountry: originCountry,
	}

	result, err := classifier.Classify(ctx, input)
	if err != nil {
		slog.Error("phase5: classify failed", "vehicle_ulid", vehicleULID, "error", err)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	_, err = pool.Exec(ctx, `
		UPDATE vehicles SET tax_status = $1, tax_confidence = $2, tax_method = $3, lifecycle_status = 'CLASSIFIED'
		WHERE vehicle_ulid = $4
	`, result.Status, result.Confidence, result.Method, vehicleULID)
	if err != nil {
		slog.Error("phase5: update vehicles failed", "vehicle_ulid", vehicleULID, "error", err)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	resultJSON, err := json.Marshal(result)
	if err != nil {
		slog.Error("phase5: json marshal failed", "vehicle_ulid", vehicleULID, "error", err)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	if err := rdb.HSet(ctx, "dict:l1_tax", vehicleULID, string(resultJSON)).Err(); err != nil {
		slog.Error("phase5: hset l1 cache failed", "vehicle_ulid", vehicleULID, "error", err)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	_, err = rdb.XAdd(ctx, &redis.XAddArgs{
		Stream: streamClassified,
		Values: map[string]interface{}{
			"vehicle_ulid": vehicleULID,
			"tax_status":   result.Status,
		},
	}).Result()
	if err != nil {
		slog.Error("phase5: xadd stream:classified failed", "vehicle_ulid", vehicleULID, "error", err)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	ackMessage(ctx, rdb, stream, msg.ID)

	slog.Info("phase5: vehicle classified",
		"phase", "forensics",
		"stream", stream,
		"vehicle_ulid", vehicleULID,
		"fingerprint", fingerprint,
		"tax_status", result.Status,
		"tax_method", result.Method,
		"latency_ms", time.Since(start).Milliseconds())
}

func ackMessage(ctx context.Context, rdb *redis.Client, stream, id string) {
	if err := rdb.XAck(ctx, stream, consumerGroup, id).Err(); err != nil {
		slog.Error("phase5: xack failed", "stream", stream, "id", id, "error", err)
	}
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
