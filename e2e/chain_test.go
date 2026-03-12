//go:build e2e

package e2e

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/cardex/alpha/pkg/nlc"
	"github.com/cardex/alpha/pkg/quote"
	"github.com/cardex/alpha/pkg/sdi"
	"github.com/cardex/alpha/pkg/tax"
	"github.com/cardex/forensics/pkg/ahocorasick"
	"github.com/cardex/forensics/pkg/taxhunter"
	"github.com/cardex/forensics/pkg/vies"
	"github.com/cardex/gateway/pkg/handlers"
	cardexhmac "github.com/cardex/gateway/pkg/hmac"
	"github.com/cardex/gateway/pkg/ratelimit"
	"github.com/cardex/pipeline/pkg/bloom"
	"github.com/cardex/pipeline/pkg/fx"
	"github.com/cardex/pipeline/pkg/h3"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/oklog/ulid/v2"
	"github.com/redis/go-redis/v9"
)

const (
	redisAddr    = "localhost:6379"
	pgURL       = "postgres://cardex:cardex_dev_only@localhost:5432/cardex?sslmode=disable"
	hmacSecret  = "e2e-secret"
	partnerID   = "e2e"
	testVIN     = "WBA11111111111111"
	bloomKey    = "bloom:e2e_test"
	xreadTimeout = 5 * time.Second
)

func TestChain_FullCARDEXFlow(t *testing.T) {
	ctx := context.Background()
	var pool *pgxpool.Pool
	var err error

	// (0) Pre-cleanup in case of previous failed run
	t.Logf("step 0: pre-cleanup")
	pool, err = pgxpool.New(ctx, pgURL)
	if err != nil {
		t.Fatalf("pgxpool new (pre-cleanup): %v", err)
	}
	_, _ = pool.Exec(ctx, `DELETE FROM vehicles WHERE vin = $1`, testVIN)
	pool.Close()

	rdb := redis.NewClient(&redis.Options{Addr: redisAddr, PoolSize: 10})
	if err := rdb.Del(ctx, bloomKey).Err(); err != nil {
		t.Fatalf("redis del bloom (pre-cleanup): %v", err)
	}

	// (1) Connect to Redis and PostgreSQL
	t.Logf("step 1: connecting to Redis and PostgreSQL")
	if err := rdb.Ping(ctx).Err(); err != nil {
		t.Fatalf("redis ping failed: %v", err)
	}
	defer rdb.Close()

	pool, err = pgxpool.New(ctx, pgURL)
	if err != nil {
		t.Fatalf("pgxpool new failed: %v", err)
	}
	defer pool.Close()
	if err := pool.Ping(ctx); err != nil {
		t.Fatalf("postgres ping failed: %v", err)
	}
	t.Logf("step 1: connected")

	// (2) Create httptest server with WebhookHandler
	t.Logf("step 2: creating httptest server with WebhookHandler")
	streamAdapter := &handlers.RedisStreamAdapter{RDB: rdb}
	limiter := ratelimit.New(rdb)
	secrets := map[string]string{partnerID: hmacSecret}
	wh := handlers.NewWebhookHandler(streamAdapter, limiter, secrets, 60*time.Second)
	mux := http.NewServeMux()
	mux.HandleFunc("POST /v1/ingest", wh.HandleIngest)
	srv := httptest.NewServer(mux)
	defer srv.Close()
	t.Logf("step 2: server ready at %s", srv.URL)

	// (3) Send valid POST /v1/ingest
	t.Logf("step 3: sending POST /v1/ingest")
	vehicle := handlers.Vehicle{
		VIN:         testVIN,
		SourceID:    "e2e-WBA11111111111111",
		Make:        "BMW",
		Model:       "330i",
		Year:        2023,
		MileageKM:   15000,
		Color:       "black",
		CO2GKM:      150,
		PriceRaw:    25000,
		CurrencyRaw: "EUR",
		SellerType:  "DEALER",
		SellerVATID: "DE123456789",
	}
	payload := handlers.IngestPayload{
		PartnerID: partnerID,
		Timestamp: time.Now(),
		Vehicles:  []handlers.Vehicle{vehicle},
	}
	body, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}
	signature := cardexhmac.Sign(body, hmacSecret)

	req, err := http.NewRequest("POST", srv.URL+"/v1/ingest", bytes.NewReader(body))
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	req.Header.Set("X-Partner-ID", partnerID)
	req.Header.Set("X-HMAC-SHA256", signature)
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("do request: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusAccepted {
		t.Fatalf("expected 202, got %d: %s", resp.StatusCode, readBody(resp))
	}
	t.Logf("step 3: got 202")

	// (4) Read from stream:ingestion_raw via XREAD (block for new message)
	t.Logf("step 4: reading from stream:ingestion_raw")
	streams, err := rdb.XRead(ctx, &redis.XReadArgs{
		Streams: []string{"stream:ingestion_raw", "0"},
		Count:   100,
		Block:   xreadTimeout,
	}).Result()
	if err != nil {
		t.Fatalf("xread stream:ingestion_raw: %v", err)
	}
	if len(streams) == 0 || len(streams[0].Messages) == 0 {
		t.Fatal("no message in stream:ingestion_raw")
	}
	msgs := streams[0].Messages
	msg := msgs[len(msgs)-1]
	payloadStr, ok := msg.Values["payload"].(string)
	if !ok {
		t.Fatal("payload not string")
	}
	t.Logf("step 4: message arrived: %s", msg.ID)

	// (5) Process vehicle manually (pipeline logic)
	t.Logf("step 5: processing vehicle (bloom, fx, h3, INSERT)")
	var v struct {
		VIN         string  `json:"vin"`
		SourceID    string  `json:"source_id"`
		Make        string  `json:"make"`
		Model       string  `json:"model"`
		Year        int     `json:"year"`
		MileageKM   int     `json:"mileage_km"`
		Color       string  `json:"color"`
		CO2GKM      int     `json:"co2_gkm"`
		PriceRaw    float64 `json:"price_raw"`
		CurrencyRaw string  `json:"currency_raw"`
		SellerType  string  `json:"seller_type"`
		SellerVATID string  `json:"seller_vat_id"`
		Lat         float64 `json:"lat"`
		Lng         float64 `json:"lng"`
	}
	if err := json.Unmarshal([]byte(payloadStr), &v); err != nil {
		t.Fatalf("unmarshal payload: %v", err)
	}

	fingerprint := computeFingerprint(v.VIN, v.Color, v.MileageKM)
	b := bloom.New(rdb, bloomKey)
	exists, err := b.Exists(ctx, fingerprint)
	if err != nil {
		t.Fatalf("bloom exists: %v", err)
	}
	if exists {
		t.Fatal("bloom: fingerprint already exists (duplicate)")
	}
	if err := b.Add(ctx, fingerprint); err != nil {
		t.Fatalf("bloom add: %v", err)
	}

	fxBuf := fx.New(rdb)
	if err := fxBuf.Refresh(ctx); err != nil {
		t.Fatalf("fx refresh: %v", err)
	}
	priceEUR, err := fxBuf.ToEUR(ctx, v.PriceRaw, v.CurrencyRaw)
	if err != nil {
		t.Fatalf("fx toeur: %v", err)
	}

	idx := &h3.Indexer{}
	var h3Res4, h3Res7 string
	if v.Lat != 0 || v.Lng != 0 {
		h3Res4, h3Res7, err = idx.Compute(v.Lat, v.Lng)
		if err != nil {
			t.Logf("h3 compute skipped: %v", err)
		}
	}

	vehicleULID := ulid.Make().String()
	source, _ := msg.Values["source"].(string)
	channel, _ := msg.Values["channel"].(string)
	if source == "" {
		source = "UNKNOWN"
	}
	if channel == "" {
		channel = "B2B_WEBHOOK"
	}

	_, err = pool.Exec(ctx, `
		INSERT INTO vehicles (
			vehicle_ulid, fingerprint_sha256, vin, source_id, source_platform, ingestion_channel,
			make, model, year, mileage_km, color, fuel_type, transmission, co2_gkm, power_kw,
			price_raw, currency_raw, gross_physical_cost_eur, lat, lng, h3_index_res4, h3_index_res7,
			raw_description, origin_country, seller_type, seller_vat_id, lifecycle_status
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27)
	`,
		vehicleULID, fingerprint, nullStr(v.VIN), v.SourceID, source, channel,
		v.Make, v.Model, v.Year, v.MileageKM, nullStr(v.Color), nil, nil, v.CO2GKM, 0,
		v.PriceRaw, v.CurrencyRaw, priceEUR, nil, nil, nullStr(h3Res4), nullStr(h3Res7),
		"", "DE", nullStr(v.SellerType), nullStr(v.SellerVATID), "INGESTED",
	)
	if err != nil {
		t.Fatalf("insert vehicles: %v", err)
	}
	t.Logf("step 5: vehicle inserted, ulid=%s", vehicleULID)

	// (6) Classify (forensics)
	t.Logf("step 6: classifying vehicle (ahocorasick, vies mock, taxhunter)")
	scanner := ahocorasick.New()
	mockVIES := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/xml; charset=utf-8")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`<?xml version="1.0" encoding="UTF-8"?>` +
			`<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">` +
			`<soapenv:Body><checkVatResponse><valid>true</valid><name>TEST AG</name></checkVatResponse></soapenv:Body>` +
			`</soapenv:Envelope>`))
	}))
	defer mockVIES.Close()

	viesClient := vies.New(200 * time.Millisecond)
	viesClient.BaseURL = mockVIES.URL
	classifier := taxhunter.New(scanner, viesClient, rdb)

	var rawDesc, sellerType, sellerVatID, originCountry string
	err = pool.QueryRow(ctx, `SELECT COALESCE(raw_description,''), COALESCE(seller_type,''), COALESCE(seller_vat_id,''), COALESCE(origin_country,'DE') FROM vehicles WHERE vehicle_ulid = $1`, vehicleULID).Scan(&rawDesc, &sellerType, &sellerVatID, &originCountry)
	if err != nil {
		t.Fatalf("query vehicle for classify: %v", err)
	}

	taxResult, err := classifier.Classify(ctx, taxhunter.VehicleInput{
		VehicleULID:   vehicleULID,
		Description:   rawDesc,
		SellerType:    sellerType,
		SellerVATID:   sellerVatID,
		OriginCountry: originCountry,
	})
	if err != nil {
		t.Fatalf("classify: %v", err)
	}

	_, err = pool.Exec(ctx, `UPDATE vehicles SET tax_status = $1, tax_confidence = $2, tax_method = $3, lifecycle_status = 'CLASSIFIED' WHERE vehicle_ulid = $4`,
		taxResult.Status, taxResult.Confidence, taxResult.Method, vehicleULID)
	if err != nil {
		t.Fatalf("update vehicles (classified): %v", err)
	}
	t.Logf("step 6: classified, tax_status=%s", taxResult.Status)

	// (7) NLC, quote, SDI (alpha)
	t.Logf("step 7: computing NLC, generating quote")
	spainCalc := &tax.SpainCalculator{}
	franceCalc := &tax.FranceCalculator{}
	netherlandsCalc := &tax.NetherlandsCalculator{}
	nlcCalc := nlc.New(rdb, spainCalc, franceCalc, netherlandsCalc)
	quoteGen := quote.New(hmacSecret, rdb, 300*time.Second)
	sdiDetector := &sdi.Detector{}

	var grossCost float64
	var co2GKM, year, daysOnMarket int
	var targetCountry string
	err = pool.QueryRow(ctx, `SELECT COALESCE(gross_physical_cost_eur,0), COALESCE(co2_gkm,0), COALESCE(year,0), COALESCE(days_on_market,0), COALESCE(target_country, origin_country, 'DE') FROM vehicles WHERE vehicle_ulid = $1`, vehicleULID).Scan(&grossCost, &co2GKM, &year, &daysOnMarket, &targetCountry)
	if err != nil {
		t.Fatalf("query vehicle for nlc: %v", err)
	}

	now := time.Now()
	ageYears := 0
	ageMonths := 0
	if year > 0 {
		ageYears = now.Year() - year
		if ageYears < 0 {
			ageYears = 0
		}
		ageMonths = ageYears * 12
	}

	nlcResult, err := nlcCalc.Compute(ctx, nlc.NLCInput{
		GrossPhysicalCostEUR: grossCost,
		OriginCountry:        "DE",
		TargetCountry:        targetCountry,
		CO2GKM:               co2GKM,
		VehicleAgeYears:      ageYears,
		VehicleAgeMonths:     ageMonths,
	})
	if err != nil {
		t.Fatalf("nlc compute: %v", err)
	}

	_, sdiZone := sdiDetector.Check(daysOnMarket)
	qt, err := quoteGen.Generate(ctx, fingerprint, nlcResult.NetLandedCostEUR)
	if err != nil {
		t.Fatalf("quote generate: %v", err)
	}

	_, err = pool.Exec(ctx, `UPDATE vehicles SET net_landed_cost_eur = $1, current_quote_id = $2, quote_expires_at = $3, sdi_zone = $4, lifecycle_status = 'QUOTED' WHERE vehicle_ulid = $5`,
		nlcResult.NetLandedCostEUR, qt.ID, qt.ExpiresAt, nullStr(sdiZone), vehicleULID)
	if err != nil {
		t.Fatalf("update vehicles (quoted): %v", err)
	}
	t.Logf("step 7: quoted, nlc=%.2f, quote_id=%s", nlcResult.NetLandedCostEUR, qt.ID)

	// (8) Final assertion
	t.Logf("step 8: final assertion")
	var lifecycleStatus, taxStatus string
	var netLandedCost float64
	var currentQuoteID *string
	err = pool.QueryRow(ctx, `SELECT lifecycle_status, tax_status, COALESCE(net_landed_cost_eur,0), current_quote_id FROM vehicles WHERE vin = $1`, testVIN).Scan(&lifecycleStatus, &taxStatus, &netLandedCost, &currentQuoteID)
	if err != nil {
		t.Fatalf("final select: %v", err)
	}

	if lifecycleStatus != "QUOTED" {
		t.Fatalf("lifecycle_status = %q, want QUOTED", lifecycleStatus)
	}
	if strings.TrimSpace(taxStatus) == "" {
		t.Fatalf("tax_status is empty")
	}
	if netLandedCost <= 0 {
		t.Fatalf("net_landed_cost_eur = %.2f, want > 0", netLandedCost)
	}
	if currentQuoteID == nil || strings.TrimSpace(*currentQuoteID) == "" {
		t.Fatalf("current_quote_id is empty")
	}
	t.Logf("step 8: assertions passed")

	// (9) Cleanup
	t.Logf("step 9: cleanup")
	_, err = pool.Exec(ctx, `DELETE FROM vehicles WHERE vin = $1`, testVIN)
	if err != nil {
		t.Fatalf("cleanup delete: %v", err)
	}
	t.Logf("step 9: cleanup done")
}

func computeFingerprint(vin, color string, mileageKM int) string {
	lower := strings.ToLower(color)
	input := fmt.Sprintf("%s%s%d", vin, lower, mileageKM)
	hash := sha256.Sum256([]byte(input))
	return hex.EncodeToString(hash[:])
}

func nullStr(s string) interface{} {
	if s == "" {
		return nil
	}
	return s
}

func readBody(resp *http.Response) string {
	var b bytes.Buffer
	b.ReadFrom(resp.Body)
	return b.String()
}
