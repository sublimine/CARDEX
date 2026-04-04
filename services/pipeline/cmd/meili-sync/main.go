// Package main implements the MeiliSearch sync worker.
// Consumes stream:meili_sync (written by pipeline after each vehicle upsert)
// and indexes/updates documents in MeiliSearch index "vehicles".
//
// MeiliSearch index schema (set at startup):
//   - primaryKey: vehicle_ulid
//   - searchableAttributes: make, model, variant, color, fuel_type, transmission
//   - filterableAttributes: make, model, year, mileage_km, price_eur, source_country,
//                           fuel_type, transmission, listing_status, h3_res4
//   - sortableAttributes: price_eur, mileage_km, year
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/meilisearch/meilisearch-go"
	"github.com/redis/go-redis/v9"
)

const (
	streamMeiliSync  = "stream:meili_sync"
	consumerGroup    = "cg_meili_indexer"
	consumerName     = "meili-sync-1"
	meiliIndex       = "vehicles"
	batchSize        = 100
	flushInterval    = 5 * time.Second
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	rdb := redis.NewClient(&redis.Options{
		Addr:     envOrDefault("REDIS_ADDR", "127.0.0.1:6379"),
		Password: envOrDefault("REDIS_PASS", ""),
		PoolSize: 10,
	})
	if err := rdb.Ping(ctx).Err(); err != nil {
		slog.Error("meili-sync: redis connection failed", "error", err)
		os.Exit(1)
	}
	defer rdb.Close()

	if err := rdb.XGroupCreateMkStream(ctx, streamMeiliSync, consumerGroup, "0").Err(); err != nil && !strings.Contains(err.Error(), "BUSYGROUP") {
		slog.Warn("meili-sync: xgroup create", "error", err)
	}

	meiliURL := envOrDefault("MEILI_URL", "http://localhost:7700")
	meiliKey := envOrDefault("MEILI_MASTER_KEY", "")
	client := meilisearch.New(meiliURL, meilisearch.WithAPIKey(meiliKey))

	if err := ensureIndex(client); err != nil {
		slog.Error("meili-sync: ensure index failed", "error", err)
		os.Exit(1)
	}
	slog.Info("meili-sync: index ready", "index", meiliIndex)

	index := client.Index(meiliIndex)
	runSyncLoop(ctx, rdb, index)
	slog.Info("meili-sync: stopped")
}

func ensureIndex(client meilisearch.ServiceManager) error {
	// Create index if it doesn't exist
	task, err := client.CreateIndex(&meilisearch.IndexConfig{
		Uid:        meiliIndex,
		PrimaryKey: "vehicle_ulid",
	})
	if err != nil && !strings.Contains(err.Error(), "already exists") && !strings.Contains(err.Error(), "index_already_exists") {
		return fmt.Errorf("create index: %w", err)
	}
	if task != nil {
		client.WaitForTask(task.TaskUID, 30*time.Second)
	}

	idx := client.Index(meiliIndex)

	// Searchable attributes
	t, err := idx.UpdateSearchableAttributes(&[]string{
		"make", "model", "variant", "color", "fuel_type", "transmission",
	})
	if err != nil {
		return fmt.Errorf("searchable attrs: %w", err)
	}
	client.WaitForTask(t.TaskUID, 30*time.Second)

	// Filterable attributes (for faceted search)
	t, err = idx.UpdateFilterableAttributes(&[]string{
		"make", "model", "year", "mileage_km", "price_eur",
		"source_country", "fuel_type", "transmission", "listing_status", "h3_res4",
	})
	if err != nil {
		return fmt.Errorf("filterable attrs: %w", err)
	}
	client.WaitForTask(t.TaskUID, 30*time.Second)

	// Sortable attributes
	t, err = idx.UpdateSortableAttributes(&[]string{
		"price_eur", "mileage_km", "year",
	})
	if err != nil {
		return fmt.Errorf("sortable attrs: %w", err)
	}
	client.WaitForTask(t.TaskUID, 30*time.Second)

	return nil
}

func runSyncLoop(ctx context.Context, rdb *redis.Client, index meilisearch.IndexManager) {
	var batch []map[string]interface{}
	ticker := time.NewTicker(flushInterval)
	defer ticker.Stop()

	flush := func() {
		if len(batch) == 0 {
			return
		}
		task, err := index.AddDocuments(batch, "vehicle_ulid")
		if err != nil {
			slog.Error("meili-sync: add documents failed", "count", len(batch), "error", err)
		} else {
			slog.Info("meili-sync: flushed batch", "count", len(batch), "task_uid", task.TaskUID)
		}
		batch = batch[:0]
	}

	for {
		select {
		case <-ctx.Done():
			flush()
			return
		case <-ticker.C:
			flush()
		default:
		}

		streams, err := rdb.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group:    consumerGroup,
			Consumer: consumerName,
			Streams:  []string{streamMeiliSync, ">"},
			Count:    int64(batchSize),
			Block:    2 * time.Second,
		}).Result()
		if err != nil && err != redis.Nil {
			slog.Error("meili-sync: xreadgroup failed", "error", err)
			time.Sleep(1 * time.Second)
			continue
		}
		if err == redis.Nil || len(streams) == 0 || len(streams[0].Messages) == 0 {
			continue
		}

		var ackIDs []string
		for _, msg := range streams[0].Messages {
			payloadStr, _ := msg.Values["payload"].(string)
			op, _ := msg.Values["op"].(string)

			if op == "delete" {
				vehicleULID, _ := msg.Values["vehicle_ulid"].(string)
				if vehicleULID != "" {
					index.DeleteDocument(vehicleULID)
				}
				ackIDs = append(ackIDs, msg.ID)
				continue
			}

			if payloadStr == "" {
				ackIDs = append(ackIDs, msg.ID)
				continue
			}

			var doc map[string]interface{}
			if err := json.Unmarshal([]byte(payloadStr), &doc); err != nil {
				slog.Warn("meili-sync: invalid payload", "id", msg.ID, "error", err)
				ackIDs = append(ackIDs, msg.ID)
				continue
			}
			batch = append(batch, doc)
			ackIDs = append(ackIDs, msg.ID)

			if len(batch) >= batchSize {
				flush()
			}
		}

		if len(ackIDs) > 0 {
			rdb.XAck(ctx, streamMeiliSync, consumerGroup, ackIDs...)
		}
	}
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
