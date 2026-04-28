// Package main implements the CARDEX Pipeline.
// Consumes stream:ingestion_raw, deduplicates via RedisBloom,
// computes H3 geospatial index, converts FX, writes to PostgreSQL,
// then publishes to stream:meili_sync for MeiliSearch indexing.
package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"net/url"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/cardex/pipeline/pkg/bloom"
	"github.com/cardex/pipeline/pkg/fx"
	"github.com/cardex/pipeline/pkg/h3"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/oklog/ulid/v2"
	"github.com/redis/go-redis/v9"
)

var wg sync.WaitGroup

const (
	streamIngestionRaw = "stream:ingestion_raw"
	streamDbWrite      = "stream:db_write"
	streamMeiliSync    = "stream:meili_sync"
	streamPriceEvents  = "stream:price_events"
	streamThumbReqs    = "stream:thumb_requests"
	consumerGroup      = "cg_pipeline"
	consumerName       = "pipeline-1"
	bloomKey           = "bloom:vehicles"
	backpressureLimit  = 50000
)

// vehiclePayload matches the JSON sent by scrapers → gateway → stream:ingestion_raw.
// New marketplace fields added alongside legacy B2B fields.
type vehiclePayload struct {
	// Identity
	VIN          string `json:"vin,omitempty"`
	SourceID     string `json:"source_id,omitempty"`        // legacy B2B
	SourceURL    string `json:"source_url,omitempty"`       // scraper: canonical listing URL
	SourceListingID string `json:"source_listing_id,omitempty"` // scraper: platform-internal ID

	// Vehicle
	Make         string  `json:"make"`
	Model        string  `json:"model"`
	Variant      string  `json:"variant,omitempty"`
	Year         int     `json:"year"`
	MileageKM    int     `json:"mileage_km"`
	Color        string  `json:"color,omitempty"`
	FuelType     string  `json:"fuel_type,omitempty"`
	Transmission string  `json:"transmission,omitempty"`
	BodyType     string  `json:"body_type,omitempty"`
	CO2GKM       int     `json:"co2_gkm,omitempty"`
	PowerKW      int     `json:"power_kw,omitempty"`

	// Price
	PriceRaw    float64 `json:"price_raw"`
	CurrencyRaw string  `json:"currency_raw"`

	// Location
	Lat           float64 `json:"lat,omitempty"`
	Lng           float64 `json:"lng,omitempty"`
	City          string  `json:"city,omitempty"`
	Region        string  `json:"region,omitempty"`
	SourceCountry string  `json:"source_country,omitempty"` // ISO 3166-1 alpha-2

	// Seller
	SellerType   string `json:"seller_type,omitempty"`
	SellerName   string `json:"seller_name,omitempty"`
	SellerVATID  string `json:"seller_vat_id,omitempty"`

	// Media
	PhotoURLs    []string `json:"photo_urls,omitempty"`
	ThumbnailURL string   `json:"thumbnail_url,omitempty"`

	// Scrape metadata
	Description  string `json:"description_snippet,omitempty"`
	ListingStatus string `json:"listing_status,omitempty"`
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
		slog.Error("pipeline: redis connection failed", "error", err)
		os.Exit(1)
	}
	defer rdb.Close()
	slog.Info("pipeline: redis connected")

	for _, sg := range []struct{ stream, group string }{
		{streamIngestionRaw, consumerGroup},
		{streamMeiliSync, "cg_meili_indexer"},
		{streamPriceEvents, "cg_price_index"},
	} {
		if err := rdb.XGroupCreateMkStream(ctx, sg.stream, sg.group, "0").Err(); err != nil && !strings.Contains(err.Error(), "BUSYGROUP") {
			slog.Warn("pipeline: xgroup create", "stream", sg.stream, "error", err)
		}
	}

	pgURL := envOrDefault("DATABASE_URL", "postgres://cardex:cardex_dev_only@127.0.0.1:5432/cardex?sslmode=disable")
	pool, err := pgxpool.New(ctx, pgURL)
	if err != nil {
		slog.Error("pipeline: pgxpool connect failed", "error", err)
		os.Exit(1)
	}
	defer pool.Close()
	if err := pool.Ping(ctx); err != nil {
		slog.Error("pipeline: postgres ping failed", "error", err)
		os.Exit(1)
	}
	slog.Info("pipeline: postgres connected")

	bloomFilter := bloom.New(rdb, bloomKey)
	fxBuffer := fx.New(rdb)
	if err := fxBuffer.Refresh(ctx); err != nil {
		slog.Error("pipeline: fx buffer refresh failed at startup", "error", err)
		os.Exit(1)
	}
	slog.Info("pipeline: fx buffer refreshed")

	go refreshFXPeriodically(ctx, fxBuffer, time.Hour)

	idx := &h3.Indexer{}

	slog.Info("pipeline: starting consumer loop")
	runConsumerLoop(ctx, rdb, pool, bloomFilter, fxBuffer, idx)

	slog.Info("pipeline: draining in-flight operations...")
	done := make(chan struct{})
	go func() { wg.Wait(); close(done) }()
	select {
	case <-done:
		slog.Info("pipeline: drained successfully")
	case <-time.After(30 * time.Second):
		slog.Warn("pipeline: drain timeout, forcing shutdown")
	}
	slog.Info("pipeline: stopped")
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
				slog.Error("pipeline: fx buffer periodic refresh failed", "error", err)
			} else {
				slog.Info("pipeline: fx buffer refreshed")
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
			slog.Error("pipeline: xlen stream:db_write failed", "error", err)
			time.Sleep(1 * time.Second)
			continue
		}
		if lenDbWrite > backpressureLimit {
			slog.Warn("pipeline: backpressure", "stream", streamDbWrite, "len", lenDbWrite)
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
			slog.Error("pipeline: xreadgroup failed", "error", err)
			time.Sleep(1 * time.Second)
			continue
		}
		if err == redis.Nil || len(streams) == 0 || len(streams[0].Messages) == 0 {
			continue
		}

		for _, msg := range streams[0].Messages {
			wg.Add(1)
			func() {
				defer wg.Done()
				processMessage(ctx, rdb, pool, b, fxBuf, idx, msg)
			}()
		}
	}
}

func processMessage(ctx context.Context, rdb *redis.Client, pool *pgxpool.Pool, b *bloom.Bloom, fxBuf *fx.Buffer, idx *h3.Indexer, msg redis.XMessage) {
	start := time.Now()

	payloadStr, ok := msg.Values["payload"].(string)
	if !ok {
		slog.Error("pipeline: payload missing", "id", msg.ID)
		ackMessage(ctx, rdb, msg.ID)
		return
	}
	source, _ := msg.Values["source"].(string)
	channel, _ := msg.Values["channel"].(string)
	if source == "" {
		source = "UNKNOWN"
	}
	if channel == "" {
		channel = "SCRAPER"
	}

	var v vehiclePayload
	if err := json.Unmarshal([]byte(payloadStr), &v); err != nil {
		slog.Error("pipeline: invalid payload json", "id", msg.ID, "error", err)
		ackMessage(ctx, rdb, msg.ID)
		return
	}

	// Minimum viable vehicle validation — reject garbage early
	if v.Make == "" || v.Model == "" {
		slog.Debug("pipeline: rejected vehicle (missing make/model)", "source", source, "url", v.SourceURL)
		ackMessage(ctx, rdb, msg.ID)
		return
	}
	if v.Year < 1920 || v.Year > 2027 {
		slog.Debug("pipeline: rejected vehicle (unrealistic year)", "year", v.Year, "source", source)
		ackMessage(ctx, rdb, msg.ID)
		return
	}
	// Reject vehicles without a direct listing URL (root domain = garbage)
	if v.SourceURL == "" {
		slog.Debug("pipeline: rejected vehicle (no source_url)", "source", source)
		ackMessage(ctx, rdb, msg.ID)
		return
	}
	if parsedURL, err := url.Parse(v.SourceURL); err == nil {
		if strings.TrimRight(parsedURL.Path, "/") == "" {
			slog.Debug("pipeline: rejected vehicle (root domain URL)", "url", v.SourceURL, "source", source)
			ackMessage(ctx, rdb, msg.ID)
			return
		}
	}

	// Fingerprint: prefer VIN; fall back to URL-based hash for scraper listings
	fingerprint := computeFingerprint(v.VIN, v.SourceURL, v.Color, v.MileageKM)

	exists, err := b.Exists(ctx, fingerprint)
	if err != nil {
		slog.Error("pipeline: bloom exists failed", "fingerprint", fingerprint, "error", err)
		ackMessage(ctx, rdb, msg.ID)
		return
	}
	if exists {
		slog.Debug("pipeline: duplicate skipped", "fingerprint", fingerprint)
		ackMessage(ctx, rdb, msg.ID)
		return
	}

	if err := b.Add(ctx, fingerprint); err != nil {
		slog.Error("pipeline: bloom add failed", "fingerprint", fingerprint, "error", err)
		ackMessage(ctx, rdb, msg.ID)
		return
	}

	priceEUR, err := fxBuf.ToEUR(ctx, v.PriceRaw, v.CurrencyRaw)
	if err != nil {
		slog.Warn("pipeline: fx fail-closed", "fingerprint", fingerprint, "currency", v.CurrencyRaw, "error", err)
		ackMessage(ctx, rdb, msg.ID)
		return
	}

	if priceEUR < 500 || priceEUR > 2_000_000 {
		slog.Info("pipeline: outlier discarded", "reason", "OUTLIER_PRICE", "fingerprint", fingerprint, "price_eur", priceEUR)
		ackMessage(ctx, rdb, msg.ID)
		return
	}

	var h3Res4, h3Res7 string
	if v.Lat != 0 || v.Lng != 0 {
		h3Res4, h3Res7, err = idx.Compute(v.Lat, v.Lng)
		if err != nil {
			slog.Warn("pipeline: h3 compute failed", "fingerprint", fingerprint, "error", err)
		}
	}

	vehicleULID := ulid.Make().String()
	listingStatus := v.ListingStatus
	if listingStatus == "" {
		listingStatus = "ACTIVE"
	}

	var returnedULID string
	var thumbURL *string
	row := pool.QueryRow(ctx, `
		INSERT INTO vehicles (
			vehicle_ulid, fingerprint_sha256, vin, source_id, source_platform, ingestion_channel,
			source_url, source_country, photo_urls, listing_status,
			make, model, variant, year, mileage_km, color, fuel_type, transmission, co2_gkm, power_kw,
			price_raw, currency_raw, gross_physical_cost_eur, lat, lng, h3_index_res4, h3_index_res7,
			raw_description, seller_type, seller_vat_id, lifecycle_status,
			last_price_eur, price_drop_count
		) VALUES (
			$1, $2, $3, $4, $5, $6,
			$7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
			$21, $22, $23, $24, $25, $26, $27,
			$28, $29, $30, 'INGESTED',
			$23, 0
		)
		ON CONFLICT (fingerprint_sha256) DO UPDATE SET
			last_updated_at           = NOW(),
			price_raw                 = EXCLUDED.price_raw,
			currency_raw              = EXCLUDED.currency_raw,
			gross_physical_cost_eur   = EXCLUDED.gross_physical_cost_eur,
			listing_status            = EXCLUDED.listing_status,
			photo_urls                = COALESCE(EXCLUDED.photo_urls, vehicles.photo_urls),
			mileage_km                = EXCLUDED.mileage_km,
			price_drop_count          = CASE
				WHEN EXCLUDED.gross_physical_cost_eur < vehicles.last_price_eur
				THEN vehicles.price_drop_count + 1
				ELSE vehicles.price_drop_count
			END,
			last_price_eur            = EXCLUDED.gross_physical_cost_eur
		RETURNING vehicle_ulid, thumb_url,
		           (xmax = 0) AS is_insert,                    -- true on first insert
		           (gross_physical_cost_eur < last_price_eur
		            AND xmax != 0)                             AS price_dropped,
		           last_price_eur                              AS prev_price_eur
	`,
		vehicleULID, fingerprint, nullStr(v.VIN), nullStr(coalesce(v.SourceID, v.SourceListingID)), source, channel,
		nullStr(v.SourceURL), nullStr(v.SourceCountry), v.PhotoURLs, listingStatus,
		v.Make, v.Model, nullStr(v.Variant), v.Year, v.MileageKM, nullStr(v.Color), nullStr(v.FuelType), nullStr(v.Transmission), v.CO2GKM, v.PowerKW,
		v.PriceRaw, v.CurrencyRaw, priceEUR, nullFloat(v.Lat), nullFloat(v.Lng), nullStr(h3Res4), nullStr(h3Res7),
		nullStr(v.Description), nullStr(v.SellerType), nullStr(v.SellerVATID),
	)
	var isInsert, priceDropped bool
	var prevPriceEUR float64
	err = row.Scan(&returnedULID, &thumbURL, &isInsert, &priceDropped, &prevPriceEUR)
	if err != nil {
		slog.Error("pipeline: insert vehicles failed", "fingerprint", fingerprint, "error", err)
		ackMessage(ctx, rdb, msg.ID)
		return
	}

	// ── Write proprietary history events ────────────────────────────────────
	// vin_history_cache is the CARDEX-owned longitudinal record of every vehicle.
	// We only write when VIN is known (no VIN = can't correlate across listings).
	if v.VIN != "" {
		eventDate := time.Now().UTC().Format("2006-01-02")

		if isInsert {
			// First time this fingerprint is seen: LISTING_START event.
			listingData, _ := json.Marshal(map[string]interface{}{
				"source_platform": source,
				"source_country":  v.SourceCountry,
				"source_url":      v.SourceURL,
				"mileage_km":      v.MileageKM,
				"price_eur":       priceEUR,
				"make":            v.Make,
				"model":           v.Model,
				"year":            v.Year,
			})
			if _, herr := pool.Exec(ctx, `
				INSERT INTO vin_history_cache (vin, event_type, event_date, data, source, confidence)
				VALUES ($1, 'LISTING', $2, $3, $4, 0.95)
			`, v.VIN, eventDate, listingData, source); herr != nil {
				slog.Warn("pipeline: vin_history_cache LISTING insert failed", "vin", v.VIN, "error", herr)
			}
		}

		if priceDropped && prevPriceEUR > 0 {
			// Price reduction detected: PRICE_CHANGE event.
			priceData, _ := json.Marshal(map[string]interface{}{
				"price_eur_prev":    prevPriceEUR,
				"price_eur_new":     priceEUR,
				"price_drop_eur":    prevPriceEUR - priceEUR,
				"source_platform":   source,
				"source_country":    v.SourceCountry,
				"mileage_km":        v.MileageKM,
			})
			if _, herr := pool.Exec(ctx, `
				INSERT INTO vin_history_cache (vin, event_type, event_date, data, source, confidence)
				VALUES ($1, 'PRICE_CHANGE', $2, $3, $4, 1.0)
			`, v.VIN, eventDate, priceData, source); herr != nil {
				slog.Warn("pipeline: vin_history_cache PRICE_CHANGE insert failed", "vin", v.VIN, "error", herr)
			}
		}

		if v.MileageKM > 0 {
			// Record mileage observation — base for odometer consistency checks.
			mileageData, _ := json.Marshal(map[string]interface{}{
				"mileage_km":      v.MileageKM,
				"source_platform": source,
				"source_country":  v.SourceCountry,
				"price_eur":       priceEUR,
			})
			if _, herr := pool.Exec(ctx, `
				INSERT INTO vin_history_cache (vin, event_type, event_date, data, source, confidence)
				VALUES ($1, 'MILEAGE', $2, $3, $4, 0.80)
				ON CONFLICT DO NOTHING
			`, v.VIN, eventDate, mileageData, source); herr != nil {
				slog.Warn("pipeline: vin_history_cache MILEAGE insert failed", "vin", v.VIN, "error", herr)
			}
		}
	}

	// Publish to stream:db_write (forensics consumer) — best-effort
	if err := rdb.XAdd(ctx, &redis.XAddArgs{
		Stream: streamDbWrite,
		Values: map[string]interface{}{
			"vehicle_ulid": returnedULID,
			"fingerprint":  fingerprint,
		},
	}).Err(); err != nil {
		slog.Error("pipeline: publish to stream:db_write failed", "vehicle_ulid", returnedULID, "error", err)
	}

	// Publish to stream:meili_sync (MeiliSearch indexer consumer) — CRITICAL
	meiliPayload, _ := json.Marshal(map[string]interface{}{
		"vehicle_ulid":  returnedULID,
		"make":          v.Make,
		"model":         v.Model,
		"variant":       v.Variant,
		"year":          v.Year,
		"mileage_km":    v.MileageKM,
		"fuel_type":     v.FuelType,
		"transmission":  v.Transmission,
		"color":         v.Color,
		"price_eur":     priceEUR,
		"source_country":  v.SourceCountry,
		"source_platform": source,
		"source_url":      v.SourceURL,
		"thumbnail_url": v.ThumbnailURL,
		"thumb_url":     thumbURL,
		"h3_res4":       h3Res4,
		"listing_status": listingStatus,
	})
	if err := rdb.XAdd(ctx, &redis.XAddArgs{
		Stream: streamMeiliSync,
		Values: map[string]interface{}{
			"vehicle_ulid": returnedULID,
			"payload":      string(meiliPayload),
			"op":           "upsert",
		},
	}).Err(); err != nil {
		slog.Error("pipeline: publish to stream:meili_sync failed", "vehicle_ulid", returnedULID, "error", err)
		return // Do NOT ACK — message will be retried
	}

	// Publish to stream:price_events for ClickHouse price_history — best-effort
	if err := rdb.XAdd(ctx, &redis.XAddArgs{
		Stream: streamPriceEvents,
		Values: map[string]interface{}{
			"vehicle_ulid":  returnedULID,
			"source_url":    v.SourceURL,
			"price_eur":     priceEUR,
			"make":          v.Make,
			"model":         v.Model,
			"year":          v.Year,
			"source_country": v.SourceCountry,
			"source_platform": source,
		},
	}).Err(); err != nil {
		slog.Error("pipeline: publish to stream:price_events failed", "vehicle_ulid", returnedULID, "error", err)
	}

	// Publish thumbnail generation request if vehicle has photos — best-effort
	if len(v.PhotoURLs) > 0 {
		if err := rdb.XAdd(ctx, &redis.XAddArgs{
			Stream: streamThumbReqs,
			Values: map[string]interface{}{
				"vehicle_ulid": returnedULID,
				"image_url":    v.PhotoURLs[0],
			},
		}).Err(); err != nil {
			slog.Error("pipeline: publish to stream:thumb_requests failed", "vehicle_ulid", returnedULID, "error", err)
		}
	}

	ackMessage(ctx, rdb, msg.ID)
	slog.Info("pipeline: vehicle processed",
		"vehicle_ulid", returnedULID,
		"fingerprint", fingerprint,
		"source", source,
		"price_eur", priceEUR,
		"latency_ms", time.Since(start).Milliseconds())
}

func computeFingerprint(vin, sourceURL, color string, mileageKM int) string {
	// If we have a VIN, use it as the primary key
	if vin != "" {
		input := fmt.Sprintf("vin:%s:%s:%d", vin, strings.ToLower(color), mileageKM)
		hash := sha256.Sum256([]byte(input))
		return hex.EncodeToString(hash[:])
	}
	// For scraper listings without VIN: fingerprint by URL (dedup per listing page)
	if sourceURL != "" {
		hash := sha256.Sum256([]byte("url:" + sourceURL))
		return hex.EncodeToString(hash[:])
	}
	// Last resort: make+model+year+mileage+color
	input := fmt.Sprintf("attr:%s:%d:%d", strings.ToLower(color), 0, mileageKM)
	hash := sha256.Sum256([]byte(input))
	return hex.EncodeToString(hash[:])
}

func ackMessage(ctx context.Context, rdb *redis.Client, id string) {
	if err := rdb.XAck(ctx, streamIngestionRaw, consumerGroup, id).Err(); err != nil {
		slog.Error("pipeline: xack failed", "id", id, "error", err)
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

func coalesce(a, b string) string {
	if a != "" {
		return a
	}
	return b
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
