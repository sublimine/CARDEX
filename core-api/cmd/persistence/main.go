package main

import (
    "context"
    "database/sql"
    "encoding/json"
    "log/slog"
    "os"
    "strconv"
    "time"

    _ "github.com/lib/pq"
    "github.com/redis/go-redis/v9"
)

var ctx = context.Background()

func main() {
    slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo})))

    redisAddr := os.Getenv("REDIS_ADDR")
    if redisAddr == "" {
        redisAddr = "127.0.0.1:6379"
    }
    rdb := redis.NewClient(&redis.Options{Addr: redisAddr, PoolSize: 100})

    connStr := os.Getenv("DATABASE_URL")
    if connStr == "" {
        connStr = "os.Getenv("DATABASE_URL")"
    }

    db, err := sql.Open("postgres", connStr)
    if err != nil {
        slog.Error("phase:persistence postgres connection failed", "error", err)
        os.Exit(1)
    }
    defer db.Close()

    upsertQuery := `
        INSERT INTO assets (shadow_id, nlc_price, deep_payload, status)
        VALUES ($1, $2, $3, 'AVAILABLE')
        ON CONFLICT (shadow_id) DO UPDATE SET
            nlc_price = EXCLUDED.nlc_price,
            deep_payload = EXCLUDED.deep_payload;
    `
    stmt, err := db.Prepare(upsertQuery)
    if err != nil {
        slog.Error("phase:persistence prepare failed", "error", err)
        os.Exit(1)
    }
    defer stmt.Close()

    slog.Info("phase:persistence daemon online", "stream", "stream:darkpool_ready")

    lastID := "$"
    for {
        streams, err := rdb.XRead(ctx, &redis.XReadArgs{
            Streams: []string{"stream:darkpool_ready", lastID},
            Count:   10,
            Block:   0,
        }).Result()

        if err != nil {
            time.Sleep(1 * time.Second)
            continue
        }

        for _, msg := range streams[0].Messages {
            lastID = msg.ID

            vin, _ := msg.Values["vin"].(string)
            if vin == "" {
                slog.Warn("phase:persistence missing vin", "id", msg.ID)
                continue
            }

            nlcStr, _ := msg.Values["nlc"].(string)
            var nlcPrice float64
            if nlcStr != "" {
                nlcPrice, _ = strconv.ParseFloat(nlcStr, 64)
            }

            deepPayload := map[string]interface{}{
                "legal_status": msg.Values["legal_status"],
                "source_url":   msg.Values["source_url"],
                "image_url":    msg.Values["image_url"],
                "quote_id":     msg.Values["quote_id"],
                "capture_time": time.Now().UTC().Format(time.RFC3339),
            }
            
            jsonPayload, _ := json.Marshal(deepPayload)

            _, err = stmt.Exec(vin, nlcPrice, jsonPayload)
            if err != nil {
                slog.Error("phase:persistence upsert failed", "vin", vin, "error", err)
                continue
            }

            slog.Info("phase:persistence upsert ok", "vin", vin, "nlc", nlcPrice)
        }
    }
}
