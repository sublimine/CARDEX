// CARDEX Phase 2: Neural Engine Consumer Loop
//
// This is the Go-side orchestrator that:
// 1. Ensures stream:l3_pending consumer group exists
// 2. Consumes messages dispatched by the Cascade classifier
// 3. Calls the L3 HTTP client (llama-server /completion)
// 4. Applies fail-closed (confidence < 0.95 → REQUIRES_HUMAN_AUDIT)
// 5. Injects results back into L1 cache (and optionally L2)
//
// The Python worker (ai/worker.py) is an alternative implementation
// using llama_cpp Python bindings. This Go consumer uses the HTTP API.
//
// Execution: GOMAXPROCS=4, pinned to cores 28-31 via numactl.
package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"runtime"
	"syscall"
	"time"

	"github.com/redis/go-redis/v9"

	"cardex/neural/internal/cascade"
	"cardex/neural/internal/l1"
	"cardex/neural/internal/l3"
)

const (
	streamL3Pending = "stream:l3_pending"
	consumerGroup   = "cg_qwen_workers"
	consumerName    = "go_neural_worker"

	readCount   = 1  // Process one at a time (L3 is expensive)
	blockTimeMS = 5000
)

func main() {
	runtime.GOMAXPROCS(4) // Cores 28-31

	redisAddr := envOrDefault("REDIS_ADDR", "127.0.0.1:6379")
	llamaURL := envOrDefault("LLAMA_URL", "http://127.0.0.1:8081")
	grammarPath := envOrDefault("GRAMMAR_PATH", "/opt/grammars/institutional_scoring.gbnf")

	slog.Info("phase2: starting Neural Engine consumer",
		"redis", redisAddr,
		"llama_url", llamaURL,
		"grammar", grammarPath,
	)

	rdb := redis.NewClient(&redis.Options{
		Addr:     redisAddr,
		PoolSize: 10,
	})

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	if err := rdb.Ping(ctx).Err(); err != nil {
		slog.Error("phase2: redis connect failed", "error", err)
		os.Exit(1)
	}

	// Load GBNF grammar
	grammarStr := loadGrammar(grammarPath)

	// Initialize L3 client
	l3Client := l3.NewClient(llamaURL, grammarStr)

	// Initialize L1 cache (for result injection)
	l1Cache := l1.NewCache(rdb)

	// Ensure consumer group exists
	ensureConsumerGroup(ctx, rdb)

	// Check L3 health (non-fatal — worker starts even if llama-server is down)
	if l3Client.Healthy(ctx) {
		slog.Info("phase2: llama-server healthy")
	} else {
		slog.Warn("phase2: llama-server NOT reachable — will retry on each message")
	}

	slog.Info("phase2: consumer loop starting",
		"stream", streamL3Pending,
		"group", consumerGroup,
	)

	// Main consumer loop
	for {
		select {
		case <-ctx.Done():
			slog.Info("phase2: shutdown")
			return
		default:
		}

		msgs, err := rdb.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group:    consumerGroup,
			Consumer: consumerName,
			Streams:  []string{streamL3Pending, ">"},
			Count:    readCount,
			Block:    blockTimeMS * time.Millisecond,
		}).Result()

		if err != nil {
			if ctx.Err() != nil {
				return // graceful shutdown
			}
			if err.Error() != "redis: nil" {
				slog.Warn("phase2: xreadgroup error", "error", err)
				time.Sleep(1 * time.Second)
			}
			continue
		}

		for _, stream := range msgs {
			for _, msg := range stream.Messages {
				processMessage(ctx, rdb, l3Client, l1Cache, msg)
			}
		}
	}
}

func processMessage(ctx context.Context, rdb *redis.Client, l3Client *l3.Client, l1Cache *l1.Cache, msg redis.XMessage) {
	vehicleULID := getField(msg.Values, "vehicle_ulid")
	source := getField(msg.Values, "source")
	description := getField(msg.Values, "description")
	sellerType := getField(msg.Values, "seller_type")
	sellerVAT := getField(msg.Values, "seller_vat")
	country := getField(msg.Values, "country")

	if vehicleULID == "" {
		slog.Warn("phase2: message missing vehicle_ulid, skipping", "msg_id", msg.ID)
		ack(ctx, rdb, msg.ID)
		return
	}

	slog.Info("phase2: processing", "vehicle", vehicleULID, "source", source)

	// Call L3 (Qwen2.5 via llama-server HTTP)
	classCtx, classCancel := context.WithTimeout(ctx, 30*time.Second)
	defer classCancel()

	result, err := l3Client.Classify(classCtx, l3.ClassificationInput{
		VehicleULID: vehicleULID,
		Source:      source,
		Description: description,
		SellerType:  sellerType,
		SellerVAT:   sellerVAT,
		Country:     country,
	})

	if err != nil {
		slog.Error("phase2: L3 classification failed",
			"vehicle", vehicleULID,
			"error", err,
		)
		// Do NOT ack → message remains in pending for retry via XPENDING/XCLAIM
		return
	}

	// Apply fail-closed
	effectiveStatus := result.TaxStatus
	if result.Confidence < cascade.ConfidenceThreshold {
		effectiveStatus = "REQUIRES_HUMAN_AUDIT"
	}

	// Inject into L1
	err = l1Cache.Set(ctx, vehicleULID, l1.Result{
		TaxStatus:  effectiveStatus,
		Confidence: result.Confidence,
	})
	if err != nil {
		slog.Error("phase2: L1 cache set failed",
			"vehicle", vehicleULID,
			"error", err,
		)
		return // retry
	}

	// ACK only after successful L1 injection
	ack(ctx, rdb, msg.ID)

	slog.Info("phase2: classified",
		"vehicle", vehicleULID,
		"raw_status", result.TaxStatus,
		"effective_status", effectiveStatus,
		"confidence", fmt.Sprintf("%.2f", result.Confidence),
	)
}

func ensureConsumerGroup(ctx context.Context, rdb *redis.Client) {
	err := rdb.XGroupCreateMkStream(ctx, streamL3Pending, consumerGroup, "$").Err()
	if err != nil && err.Error() != "BUSYGROUP Consumer Group name already exists" {
		slog.Warn("phase2: create consumer group", "error", err)
	}
}

func ack(ctx context.Context, rdb *redis.Client, msgID string) {
	_ = rdb.XAck(ctx, streamL3Pending, consumerGroup, msgID).Err()
}

func getField(values map[string]interface{}, key string) string {
	v, ok := values[key]
	if !ok {
		return ""
	}
	s, ok := v.(string)
	if !ok {
		return ""
	}
	return s
}

func loadGrammar(path string) string {
	data, err := os.ReadFile(path)
	if err != nil {
		slog.Warn("phase2: grammar file not found, GBNF enforcement disabled",
			"path", path,
			"error", err,
		)
		return ""
	}
	slog.Info("phase2: GBNF grammar loaded", "path", path, "bytes", len(data))
	return string(data)
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
