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

const cardexUA = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"

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

type VehicleAsset struct {
	ListingID    string  `json:"listing_id"`
	CreationDate string  `json:"creation_date"`
	DealerID     string  `json:"dealer_id"`
	Price        float64 `json:"price"`
	Country      string  `json:"country"`
	SourceURL    string  `json:"source_url"`
	ImageURL     string  `json:"image_url"`
}

type CardexHTTPClient struct {
	Client  *resty.Client
	BaseURL string
}

func NewCardexHTTPClient() *CardexHTTPClient {
	client := resty.New().
		SetTimeout(12 * time.Second).
		SetRetryCount(2).
		SetHeaders(map[string]string{
			"User-Agent": cardexUA,
			"Accept":     "application/json, text/plain, */*",
		})

	return &CardexHTTPClient{
		Client:  client,
		BaseURL: "https://suchen.mobile.de",
	}
}

func (c *CardexHTTPClient) FetchSector(task H3Task) ([]VehicleAsset, int, error) {
	queryParams := map[string]string{
		"isSearchRequest": "true",
		"s":               "Car",
		"vc":              "Car",
		"cn":              task.Country,
		"sb":              "doc",
		"od":              "down",
	}

	resp, err := c.Client.R().
		SetQueryParams(queryParams).
		Get(c.BaseURL + "/vc/api/search")

	if err != nil {
		return nil, 0, fmt.Errorf("network error: %w", err)
	}

	if resp.StatusCode() == 429 {
		return nil, 0, fmt.Errorf("rate limited (HTTP 429) — backing off")
	}

	if resp.StatusCode() == 403 || resp.StatusCode() == 401 {
		return nil, 0, fmt.Errorf("access denied (HTTP %d) — source may require review", resp.StatusCode())
	}

	if resp.StatusCode() != 200 {
		return nil, 0, fmt.Errorf("unexpected status %d", resp.StatusCode())
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
		return nil, 0, fmt.Errorf("JSON parse error: %w", err)
	}

	var assets []VehicleAsset
	for _, item := range rawResponse.Result.Items {
		imgURL := ""
		if len(item.Images) > 0 {
			imgURL = cdnOptimizerRegex.ReplaceAllString(item.Images[0].URL, "${1}320${2}")
		}

		assets = append(assets, VehicleAsset{
			ListingID:    fmt.Sprintf("M_DE_%s", item.ID),
			CreationDate: time.Now().UTC().Format(time.RFC3339),
			DealerID:     item.DealerID,
			Price:        item.Price,
			Country:      task.Country,
			SourceURL:    fmt.Sprintf("https://suchen.mobile.de/fahrzeuge/details.html?id=%s", item.ID),
			ImageURL:     imgURL,
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

	slog.Info("phase:ingestion crawler online", "ua", cardexUA)

	engine := NewCardexHTTPClient()

	for {
		result, err := rdb.BLPop(ctx, 0, "queue:h3_tasks").Result()
		if err != nil {
			slog.Error("phase:ingestion blpop failed", "error", err)
			select {
			case <-time.After(2 * time.Second):
			}
			continue
		}

		if len(result) < 2 {
			continue
		}

		var task H3Task
		if err := json.Unmarshal([]byte(result[1]), &task); err != nil {
			slog.Error("phase:ingestion task parse failed", "error", err)
			continue
		}

		assets, total, err := engine.FetchSector(task)
		if err != nil {
			slog.Error("phase:ingestion fetch failed",
				"h3", task.H3Index,
				"country", task.Country,
				"error", err,
			)
			continue
		}

		pipe := rdb.Pipeline()
		for _, asset := range assets {
			b, _ := json.Marshal(asset)
			pipe.RPush(ctx, "queue:vehicle_raw", b)
		}
		if _, err := pipe.Exec(ctx); err != nil {
			slog.Error("phase:ingestion redis push failed", "error", err)
			continue
		}

		slog.Info("phase:ingestion sector complete",
			"h3", task.H3Index,
			"country", task.Country,
			"fetched", len(assets),
			"total_available", total,
		)
	}
}
