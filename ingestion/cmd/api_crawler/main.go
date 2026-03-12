package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"regexp"
	"time"

	"github.com/go-resty/resty/v2"
	"github.com/redis/go-redis/v9"
)

var rdb *redis.Client
var ctx = context.Background()
var cdnOptimizerRegex = regexp.MustCompile(`(?i)(rule=mo-)[0-9]+(\.jpg)`)

func init() {
	addr := os.Getenv("REDIS_ADDR")
	if addr == "" {
		addr = "127.0.0.1:6379"
	}
	rdb = redis.NewClient(&redis.Options{Addr: addr, PoolSize: 100})
}

type H3Task struct {
	Country    string `json:"country"`
	H3Index    string `json:"h3_index"`
	Resolution int    `json:"resolution"`
}

type DeepAssetPayload struct {
	ShadowID       string  `json:"shadow_id"`
	CreationDate   string  `json:"creation_date"`
	DealerUUID     string  `json:"dealer_uuid"`
	Price          float64 `json:"price"`
	TargetMarket   string  `json:"target_market"`
	SourceURL      string  `json:"source_url"`
	OptimizedImage string  `json:"optimized_image_url"`
	RawPayload     string  `json:"raw_payload"`
}

type StealthEngine struct {
	Client  *resty.Client
	BaseURL string
}

func NewStealthEngine() *StealthEngine {
	client := resty.New().
		SetTimeout(12 * time.Second).
		SetRetryCount(2).
		SetHeaders(map[string]string{
			"User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
			"Accept":          "application/json, text/plain, */*",
			"Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
			"Referer":         "https://suchen.mobile.de/fahrzeuge/search.html",
			"Connection":      "keep-alive",
			"Sec-Fetch-Dest":  "empty",
			"Sec-Fetch-Mode":  "cors",
			"Sec-Fetch-Site":  "same-origin",
		})

	return &StealthEngine{
		Client:  client,
		BaseURL: "https://suchen.mobile.de",
	}
}

func (e *StealthEngine) PenetrateSector(task H3Task) ([]DeepAssetPayload, int, error) {
	queryParams := map[string]string{
		"isSearchRequest": "true",
		"s":               "Car",
		"vc":              "Car",
		"cn":              task.Country,
		"sb":              "doc",
		"od":              "down",
	}

	resp, err := e.Client.R().
		SetQueryParams(queryParams).
		Get(e.BaseURL + "/vc/api/search")

	if err != nil {
		return nil, 0, fmt.Errorf("fallo de red: %w", err)
	}

	if resp.StatusCode() == 403 || resp.StatusCode() == 401 || resp.StatusCode() == 429 {
		return nil, 0, fmt.Errorf("DATADOME WAF BLOQUEO (HTTP %d). Rotación de IP requerida", resp.StatusCode())
	}

	if resp.StatusCode() != 200 {
		return nil, 0, fmt.Errorf("servidor rechazó el payload (HTTP %d)", resp.StatusCode())
	}

	var rawResponse struct {
		Result struct {
			TotalItems int `json:"totalItems"`
			Items      []struct {
				ID       string  `json:"id"`
				DealerID string  `json:"sellerId"`
				Price    float64 `json:"priceGross"`
				Title    string  `json:"title"`
				Images   []struct {
					URL string `json:"url"`
				} `json:"images"`
			} `json:"items"`
		} `json:"result"`
	}

	if err := json.Unmarshal(resp.Body(), &rawResponse); err != nil {
		return nil, 0, fmt.Errorf("fallo de parseo JSON. El portal ha mutado la API")
	}

	var assets []DeepAssetPayload
	for _, item := range rawResponse.Result.Items {
		optImg := ""
		if len(item.Images) > 0 {
			optImg = cdnOptimizerRegex.ReplaceAllString(item.Images[0].URL, "${1}320${2}")
		}

		assets = append(assets, DeepAssetPayload{
			ShadowID:       fmt.Sprintf("M_DE_%s", item.ID),
			CreationDate:   time.Now().UTC().Format(time.RFC3339),
			DealerUUID:     item.DealerID,
			Price:          item.Price,
			TargetMarket:   task.Country,
			SourceURL:      fmt.Sprintf("https://suchen.mobile.de/fahrzeuge/details.html?id=%s", item.ID),
			OptimizedImage: optImg,
			RawPayload:     "PAYLOAD_OMITIDO_RAM",
		})
	}

	return assets, rawResponse.Result.TotalItems, nil
}

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo})))

	if err := rdb.Ping(ctx).Err(); err != nil {
		slog.Error("phase:ingestion redis unreachable", "error", err)
		os.Exit(1)
	}

	slog.Info("phase:ingestion stealth_hft online", "motor", "real HTTP")

	engine := NewStealthEngine()

	for {
		result, err := rdb.BLPop(ctx, 0, "queue:h3_tasks").Result()
		if err != nil {
			slog.Error("phase:ingestion blpop failed", "error", err)
			select {
			case <-time.After(2 * time.Second):
			}
			continue
		}

		var task H3Task
		if err := json.Unmarshal([]byte(result[1]), &task); err != nil {
			slog.Warn("phase:ingestion invalid task", "error", err)
			continue
		}

		slog.Info("phase:ingestion attacking sector", "h3_index", task.H3Index, "country", task.Country)

		assets, _, err := engine.PenetrateSector(task)
		if err != nil {
			slog.Error("phase:ingestion waf_block", "h3_index", task.H3Index, "error", err)
			select {
			case <-time.After(5 * time.Second):
			}
			continue
		}

		for _, raw := range assets {
			payload := map[string]interface{}{
				"vin":          raw.ShadowID,
				"nlc":          raw.Price,
				"legal_status": "PENDING_NLP",
				"quote_id":     raw.ShadowID,
				"source_url":   raw.SourceURL,
				"image_url":    raw.OptimizedImage,
			}
			dataJSON, _ := json.Marshal(payload)

			if err := rdb.XAdd(ctx, &redis.XAddArgs{
				Stream: "stream:darkpool_ready",
				Values: map[string]interface{}{"data": string(dataJSON)},
			}).Err(); err != nil {
				slog.Error("phase:ingestion xadd failed", "shadow_id", raw.ShadowID, "error", err)
				continue
			}
		}

		slog.Info("phase:ingestion sector penetrated", "h3_index", task.H3Index, "assets", len(assets))

		select {
		case <-time.After(800 * time.Millisecond):
		}
	}
}
