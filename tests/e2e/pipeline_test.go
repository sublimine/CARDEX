//go:build e2e

// Package e2e_test exercises the full Discovery → Extraction → Quality → storage
// pipeline using three real dealer HTML fixtures (DE, FR, ES).
//
// Run with:
//
//	go test ./tests/e2e/... -tags=e2e -v
//
// No external network calls are made: the fixture HTTP servers serve all
// content locally, including the synthetic JPEG images used by V05/V16.
package e2e_test

import (
	"bytes"
	"context"
	"database/sql"
	"fmt"
	"image"
	"image/color"
	"image/jpeg"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"testing"
	"time"

	discoveryrun "cardex.eu/discovery/run"
	extractionrun "cardex.eu/extraction/run"
	qualityrun "cardex.eu/quality/run"
)

// fixtureDealer bundles the seed data and fixture path for one test dealer.
type fixtureDealer struct {
	id      string
	name    string
	country string
	// fixture is the path relative to this file's directory.
	fixture string
}

var testDealers = []fixtureDealer{
	{
		id:      "e2e-dealer-de-0001",
		name:    "BMW Autohaus München",
		country: "DE",
		fixture: "../fixtures/e2e/de_bmw_dealer.html",
	},
	{
		id:      "e2e-dealer-fr-0001",
		name:    "Garage Renault Lyon",
		country: "FR",
		fixture: "../fixtures/e2e/fr_renault_dealer.html",
	},
	{
		id:      "e2e-dealer-es-0001",
		name:    "Concesionario SEAT Barcelona",
		country: "ES",
		fixture: "../fixtures/e2e/es_seat_dealer.html",
	},
}

// TestPipeline_EndToEnd runs a full Discovery → Extraction → Quality cycle for
// each of the three seeded dealers, asserting:
//   - At least one listing extracted per dealer
//   - V01 (VIN checksum) passes for each listing
//   - V07 (price sanity) passes for each listing
//   - Composite score >= 60 % for each valid listing
//   - Prometheus VehiclesValidated counter is incremented
func TestPipeline_EndToEnd(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping e2e test in short mode")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	defer cancel()

	// ── 1. Initialise shared SQLite DB with full discovery + quality schema ──
	dbPath := filepath.Join(t.TempDir(), "cardex_e2e.db")
	sqlDB, err := discoveryrun.InitDB(dbPath)
	if err != nil {
		t.Fatalf("InitDB: %v", err)
	}
	defer sqlDB.Close()

	// ── 2. Build a synthetic JPEG served to V05/V16 validators ──────────────
	// V05 requires Content-Length ≥ 30 KB and valid JPEG magic bytes.
	// A 256×256 noise image encoded at quality 95 exceeds this threshold.
	testJPEG := generateTestJPEG(t)

	// ── 3. Run pipeline for each dealer ─────────────────────────────────────
	var totalListings int
	prometheusBaseline := qualityrun.VehiclesValidatedCount()

	for _, d := range testDealers {
		d := d // capture loop variable
		t.Run(d.country, func(t *testing.T) {
			html := readFixture(t, d.fixture)

			// Start a local HTTP server that serves:
			//   /           → fixture HTML (for E01 extraction)
			//   /*.jpg etc. → synthetic JPEG (for V05 image quality + V16 pHash)
			//   anything else → 200 OK (for V10 URL liveness + V17 sold check)
			srv := httptest.NewServer(dealerHandler(html, testJPEG))
			defer srv.Close()

			// Seed dealer into dealer_entity + dealer_web_presence.
			seedDealer(t, sqlDB, d.id, d.name, d.country, srv.URL)

			// ── Extraction ────────────────────────────────────────────────
			dealer := &extractionrun.Dealer{
				ID:              d.id,
				Domain:          strings.TrimPrefix(strings.TrimPrefix(srv.URL, "http://"), "https://"),
				URLRoot:         srv.URL,
				CountryCode:     d.country,
				PlatformType:    "UNKNOWN",
				ExtractionHints: []string{"schema_org_detected"},
			}

			result, err := extractionrun.ExtractE01(ctx, dealer, srv.Client())
			if err != nil {
				t.Fatalf("ExtractE01: %v", err)
			}
			if len(result.Vehicles) == 0 {
				t.Fatalf("no vehicles extracted for %s dealer (errors: %v)", d.country, result.Errors)
			}
			t.Logf("[%s] extracted %d vehicle(s) via %s", d.country, len(result.Vehicles), result.Strategy)

			// Persist vehicles to vehicle_record.
			persisted, err := extractionrun.PersistVehicles(ctx, dbPath, d.id, result.Vehicles)
			if err != nil {
				t.Fatalf("PersistVehicles: %v", err)
			}
			if persisted == 0 {
				t.Fatal("PersistVehicles: 0 rows inserted")
			}
			totalListings += persisted

			// ── Quality pipeline ──────────────────────────────────────────
			for _, raw := range result.Vehicles {
				vehicle := vehicleFromRaw(raw, d.id, d.country)

				qr, err := qualityrun.RunPipeline(ctx, dbPath, vehicle, srv.Client())
				if err != nil {
					t.Fatalf("RunPipeline: %v", err)
				}

				// Assertion: V01 VIN checksum must pass.
				assertValidatorPass(t, qr, "V01")

				// Assertion: V07 price sanity must pass.
				assertValidatorPass(t, qr, "V07")

				// Assertion: composite score must be ≥ 60 % for a valid listing.
				if qr.ScorePercent < 60.0 {
					t.Errorf("[%s] composite score %.1f%% < 60%% (decision=%s, critical=%v)",
						d.country, qr.ScorePercent, qr.Decision, qr.HasCritical)
					for _, vr := range qr.ValidatorResults {
						if !vr.Pass {
							t.Logf("  FAIL %s (%s): %s", vr.ValidatorID, vr.Severity, vr.Issue)
						}
					}
				}

				t.Logf("[%s] VIN=%-17s score=%.1f%% decision=%-14s critical=%v",
					d.country, derefStr(raw.VIN), qr.ScorePercent, qr.Decision, qr.HasCritical)
			}
		})
	}

	// ── 4. Global assertions ─────────────────────────────────────────────────

	// Assertion: total listings across all dealers must be > 0.
	if totalListings == 0 {
		t.Fatal("no listings persisted across all 3 dealers")
	}
	t.Logf("total listings persisted: %d", totalListings)

	// Assertion: Prometheus VehiclesValidated counter must have incremented.
	newCount := qualityrun.VehiclesValidatedCount()
	if newCount <= prometheusBaseline {
		t.Errorf("prometheus VehiclesValidated not incremented (was %.0f, now %.0f)", prometheusBaseline, newCount)
	}
	t.Logf("prometheus VehiclesValidated: %.0f → %.0f", prometheusBaseline, newCount)
}

// ── Helpers ──────────────────────────────────────────────────────────────────

// dealerHandler returns an http.Handler that:
//   - Serves fixtureHTML at "/" (E01 JSON-LD extraction page)
//   - Serves testJPEG for any path ending in an image extension
//   - Returns 200 OK for all other paths (V10 liveness, V17 sold check)
func dealerHandler(fixtureHTML, testJPEG []byte) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		p := r.URL.Path
		switch {
		case p == "/" || p == "":
			w.Header().Set("Content-Type", "text/html; charset=utf-8")
			if r.Method != http.MethodHead {
				w.Write(fixtureHTML) //nolint:errcheck
			}
		case isImagePath(p):
			w.Header().Set("Content-Type", "image/jpeg")
			w.Header().Set("Content-Length", strconv.Itoa(len(testJPEG)))
			if r.Method != http.MethodHead {
				w.Write(testJPEG) //nolint:errcheck
			}
		default:
			w.Header().Set("Content-Type", "text/html; charset=utf-8")
			w.WriteHeader(http.StatusOK)
		}
	})
}

// isImagePath returns true for paths whose extension suggests an image file.
func isImagePath(p string) bool {
	p = strings.ToLower(p)
	for _, ext := range []string{".jpg", ".jpeg", ".png", ".webp", ".avif"} {
		if strings.HasSuffix(p, ext) {
			return true
		}
	}
	return false
}

// readFixture reads a fixture file relative to this test file's directory.
func readFixture(t *testing.T, relPath string) []byte {
	t.Helper()
	_, testFile, _, _ := runtime.Caller(0)
	abs := filepath.Join(filepath.Dir(testFile), relPath)
	b, err := os.ReadFile(abs)
	if err != nil {
		t.Fatalf("readFixture(%q): %v", relPath, err)
	}
	return b
}

// seedDealer inserts a minimal dealer_entity + dealer_web_presence row so
// that extraction.PersistVehicles can resolve the foreign key constraint.
func seedDealer(t *testing.T, db *sql.DB, id, name, country, urlRoot string) {
	t.Helper()
	now := time.Now().UTC().Format(time.RFC3339)
	domain := strings.TrimPrefix(strings.TrimPrefix(urlRoot, "http://"), "https://")

	_, err := db.Exec(`
		INSERT OR IGNORE INTO dealer_entity
		  (dealer_id, canonical_name, normalized_name, country_code,
		   status, confidence_score, first_discovered_at, last_confirmed_at)
		VALUES (?, ?, ?, ?, 'ACTIVE', 0.9, ?, ?)`,
		id, name, strings.ToUpper(name), country, now, now,
	)
	if err != nil {
		t.Fatalf("seedDealer entity %s: %v", id, err)
	}

	webID := "wp-" + id
	_, err = db.Exec(`
		INSERT OR IGNORE INTO dealer_web_presence
		  (web_id, dealer_id, domain, url_root, discovered_by_families)
		VALUES (?, ?, ?, ?, 'e2e')`,
		webID, id, domain, urlRoot,
	)
	if err != nil {
		t.Fatalf("seedDealer web_presence %s: %v", id, err)
	}
}

// vehicleFromRaw maps an extraction VehicleRaw to a quality Vehicle.
func vehicleFromRaw(raw *extractionrun.VehicleRaw, dealerID, country string) *qualityrun.Vehicle {
	v := &qualityrun.Vehicle{
		InternalID:    "e2e-" + derefStr(raw.VIN),
		VIN:           derefStr(raw.VIN),
		Make:          derefStr(raw.Make),
		Model:         derefStr(raw.Model),
		DealerID:      dealerID,
		SourceCountry: country,
		SourceURL:     raw.SourceURL,
		PhotoURLs:     raw.ImageURLs,
		ExtractedAt:   time.Now(),
		Metadata:      map[string]string{"source": "e2e-test"},
	}
	if raw.Year != nil {
		v.Year = *raw.Year
	}
	if raw.Mileage != nil {
		v.Mileage = *raw.Mileage
	}
	if raw.FuelType != nil {
		v.Fuel = *raw.FuelType
	}
	if raw.Transmission != nil {
		v.Transmission = *raw.Transmission
	}
	if raw.PriceGross != nil {
		v.PriceEUR = int(*raw.PriceGross)
	}
	v.Title = fmt.Sprintf("%s %s %d", v.Make, v.Model, v.Year)
	v.Description = fmt.Sprintf(
		"E2E fixture: %s %s (%d), %d km, %s, %s.",
		v.Make, v.Model, v.Year, v.Mileage, v.Fuel, country,
	)
	return v
}

// assertValidatorPass fails the test if the named validator result is absent
// or did not pass.
func assertValidatorPass(t *testing.T, qr *qualityrun.RunResult, validatorID string) {
	t.Helper()
	for _, r := range qr.ValidatorResults {
		if r.ValidatorID == validatorID {
			if !r.Pass {
				t.Errorf("[%s] %s expected PASS, got FAIL (severity=%s issue=%q)",
					qr.VehicleID, validatorID, r.Severity, r.Issue)
			}
			return
		}
	}
	t.Errorf("[%s] validator %s not found in results", qr.VehicleID, validatorID)
}

// generateTestJPEG returns a JPEG-encoded 256×256 image with enough visual
// complexity to exceed V05's 30 KB minimum size threshold at quality=95.
// Trailing zero bytes (after FF D9) pad to exactly 50 KB; Go's jpeg.Decode
// stops at FF D9 and ignores trailing bytes, so V16 pHash still works.
func generateTestJPEG(t *testing.T) []byte {
	t.Helper()
	const w, h = 256, 256
	img := image.NewNRGBA(image.Rect(0, 0, w, h))
	// Fill with a gradient-and-noise pattern to defeat JPEG compression.
	for y := 0; y < h; y++ {
		for x := 0; x < w; x++ {
			// Deterministic per-pixel variation using simple arithmetic.
			r := uint8((x*3 + y*7) % 256)
			g := uint8((x*7 + y*3 + 128) % 256)
			b := uint8((x*5 + y*11 + 64) % 256)
			img.SetNRGBA(x, y, color.NRGBA{R: r, G: g, B: b, A: 255})
		}
	}

	var buf bytes.Buffer
	if err := jpeg.Encode(&buf, img, &jpeg.Options{Quality: 95}); err != nil {
		t.Fatalf("generateTestJPEG: encode: %v", err)
	}

	// Pad to 50 KB so V05 Content-Length check always passes (≥ 30 KB).
	// JPEG decoders stop at the FF D9 end-of-image marker; trailing zeros
	// do not affect decoding correctness.
	const target = 50 * 1024
	b := buf.Bytes()
	if len(b) < target {
		b = append(b, make([]byte, target-len(b))...)
	}
	return b
}

// derefStr safely dereferences a *string, returning "" for nil.
func derefStr(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}
