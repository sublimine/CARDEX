// Package main implements the CARDEX Alpha Engine (Phase 6).
// Consumes stream:classified, computes NLC, generates quotes, detects SDI, writes to stream:quoted.
// See .cursor/prompts/phase-06-financial.md for full specification.
package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/cardex/alpha/pkg/nlc"
	"github.com/cardex/alpha/pkg/quote"
	"github.com/cardex/alpha/pkg/sdi"
	"github.com/cardex/alpha/pkg/tax"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

const (
	streamClassified  = "stream:classified"
	streamQuoted      = "stream:quoted"
	consumerGroup     = "cg_alpha"
	consumerName      = "alpha-1"
	backpressureLimit = 50000
	quoteTTL          = 300 * time.Second
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
		slog.Error("phase6: redis connection failed", "error", err)
		os.Exit(1)
	}
	defer rdb.Close()
	slog.Info("phase6: redis connected")

	pgURL := envOrDefault("DATABASE_URL", "postgres://cardex:cardex_dev_only@127.0.0.1:5432/cardex?sslmode=disable")
	pool, err := pgxpool.New(ctx, pgURL)
	if err != nil {
		slog.Error("phase6: pgxpool connect failed", "error", err)
		os.Exit(1)
	}
	defer pool.Close()
	if err := pool.Ping(ctx); err != nil {
		slog.Error("phase6: postgres ping failed", "error", err)
		os.Exit(1)
	}
	slog.Info("phase6: postgres connected")

	if err := rdb.XGroupCreateMkStream(ctx, streamClassified, consumerGroup, "0").Err(); err != nil && !strings.Contains(err.Error(), "BUSYGROUP") {
		slog.Warn("phase6: xgroup create", "stream", streamClassified, "error", err)
	}

	spainCalc := &tax.SpainCalculator{}
	franceCalc := &tax.FranceCalculator{}
	netherlandsCalc := &tax.NetherlandsCalculator{}
	nlcCalc := nlc.New(rdb, spainCalc, franceCalc, netherlandsCalc)
	quoteGen := quote.New(envOrDefault("QUOTE_SECRET", "dev-secret-change-me"), rdb, quoteTTL)
	sdiDetector := &sdi.Detector{}

	slog.Info("phase6: alpha engine starting consumer loop")

	runConsumerLoop(ctx, rdb, pool, nlcCalc, quoteGen, sdiDetector)

	slog.Info("phase6: alpha engine stopped")
}

func runConsumerLoop(ctx context.Context, rdb *redis.Client, pool *pgxpool.Pool, nlcCalc *nlc.Calculator, quoteGen *quote.QuoteGenerator, sdiDetector *sdi.Detector) {
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		lenQuoted, err := rdb.XLen(ctx, streamQuoted).Result()
		if err != nil {
			slog.Error("phase6: xlen stream:quoted failed", "error", err)
			time.Sleep(1 * time.Second)
			continue
		}
		if lenQuoted > backpressureLimit {
			slog.Warn("phase6: backpressure", "stream", streamQuoted, "len", lenQuoted, "limit", backpressureLimit)
			time.Sleep(1 * time.Second)
			continue
		}

		streams, err := rdb.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group:    consumerGroup,
			Consumer: consumerName,
			Streams:  []string{streamClassified, ">"},
			Count:    10,
			Block:    2 * time.Second,
		}).Result()
		if err != nil && err != redis.Nil {
			slog.Error("phase6: xreadgroup failed", "stream", streamClassified, "error", err)
			time.Sleep(1 * time.Second)
			continue
		}
		if err == redis.Nil || len(streams) == 0 || len(streams[0].Messages) == 0 {
			continue
		}

		for _, msg := range streams[0].Messages {
			processMessage(ctx, rdb, pool, nlcCalc, quoteGen, sdiDetector, streamClassified, msg)
		}
	}
}

func processMessage(ctx context.Context, rdb *redis.Client, pool *pgxpool.Pool, nlcCalc *nlc.Calculator, quoteGen *quote.QuoteGenerator, sdiDetector *sdi.Detector, stream string, msg redis.XMessage) {
	start := time.Now()

	vehicleULID, _ := msg.Values["vehicle_ulid"].(string)
	taxStatus, _ := msg.Values["tax_status"].(string)
	if vehicleULID == "" {
		slog.Error("phase6: vehicle_ulid missing", "stream", stream, "id", msg.ID)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	if taxStatus == "REQUIRES_HUMAN_AUDIT" {
		slog.Info("phase6: skip REQUIRES_HUMAN_AUDIT", "vehicle_ulid", vehicleULID, "phase", "alpha")
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	var fingerprint string
	var grossPhysicalCost float64
	var originCountry, targetCountry string
	var co2GKM, year, daysOnMarket int

	err := pool.QueryRow(ctx, `
		SELECT fingerprint_sha256, COALESCE(gross_physical_cost_eur, 0), COALESCE(origin_country, 'DE'),
			COALESCE(target_country, origin_country, 'DE'), COALESCE(co2_gkm, 0), COALESCE(year, 0), COALESCE(days_on_market, 0)
		FROM vehicles WHERE vehicle_ulid = $1
	`, vehicleULID).Scan(&fingerprint, &grossPhysicalCost, &originCountry, &targetCountry, &co2GKM, &year, &daysOnMarket)
	if err != nil {
		slog.Error("phase6: vehicle query failed", "vehicle_ulid", vehicleULID, "error", err)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	now := time.Now()
	vehicleAgeYears := 0
	vehicleAgeMonths := 0
	if year > 0 {
		vehicleAgeYears = now.Year() - year
		if vehicleAgeYears < 0 {
			vehicleAgeYears = 0
		}
		vehicleAgeMonths = vehicleAgeYears * 12
	}

	nlcInput := nlc.NLCInput{
		GrossPhysicalCostEUR: grossPhysicalCost,
		OriginCountry:        originCountry,
		TargetCountry:        targetCountry,
		CO2GKM:               co2GKM,
		VehicleAgeYears:      vehicleAgeYears,
		VehicleAgeMonths:     vehicleAgeMonths,
	}

	nlcResult, err := nlcCalc.Compute(ctx, nlcInput)
	if err != nil {
		slog.Error("phase6: nlc compute failed", "vehicle_ulid", vehicleULID, "error", err)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	sdiAlert, sdiZone := sdiDetector.Check(daysOnMarket)
	if sdiAlert {
		slog.Warn("phase6: sdi alert", "vehicle_ulid", vehicleULID, "days_on_market", daysOnMarket, "zone", sdiZone)
	}

	qt, err := quoteGen.Generate(ctx, fingerprint, nlcResult.NetLandedCostEUR)
	if err != nil {
		slog.Error("phase6: quote generate failed", "vehicle_ulid", vehicleULID, "error", err)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	_, err = pool.Exec(ctx, `
		UPDATE vehicles SET net_landed_cost_eur = $1, current_quote_id = $2, quote_expires_at = $3, sdi_zone = $4, sdi_alert = $5, lifecycle_status = 'QUOTED'
		WHERE vehicle_ulid = $6
	`, nlcResult.NetLandedCostEUR, qt.ID, qt.ExpiresAt, nullStr(sdiZone), sdiAlert, vehicleULID)
	if err != nil {
		slog.Error("phase6: update vehicles failed", "vehicle_ulid", vehicleULID, "error", err)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	_, err = rdb.XAdd(ctx, &redis.XAddArgs{
		Stream: streamQuoted,
		Values: map[string]interface{}{
			"vehicle_ulid": vehicleULID,
			"quote_id":    qt.ID,
			"nlc":         nlcResult.NetLandedCostEUR,
		},
	}).Result()
	if err != nil {
		slog.Error("phase6: xadd stream:quoted failed", "vehicle_ulid", vehicleULID, "error", err)
		ackMessage(ctx, rdb, stream, msg.ID)
		return
	}

	ackMessage(ctx, rdb, stream, msg.ID)

	slog.Info("phase6: vehicle quoted",
		"phase", "alpha",
		"stream", stream,
		"vehicle_ulid", vehicleULID,
		"quote_id", qt.ID,
		"nlc", nlcResult.NetLandedCostEUR,
		"sdi_zone", sdiZone,
		"latency_ms", time.Since(start).Milliseconds())
}

func ackMessage(ctx context.Context, rdb *redis.Client, stream, id string) {
	if err := rdb.XAck(ctx, stream, consumerGroup, id).Err(); err != nil {
		slog.Error("phase6: xack failed", "stream", stream, "id", id, "error", err)
	}
}

func nullStr(s string) interface{} {
	if s == "" {
		return nil
	}
	return s
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
