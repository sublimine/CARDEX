// Package vies implements sub-technique M.1 — VIES VAT validation batch (EU).
//
// The EU VAT Information Exchange System (VIES) validates whether a VAT number
// is currently registered and active in an EU member state. CARDEX uses VIES as
// a secondary enrichment signal to:
//
//  1. Confirm that a dealer entity has a valid, active VAT registration.
//  2. Cross-validate the registered name/address against the canonical name
//     already stored in the KG. A close match bumps confidence_score by +0.10.
//  3. Transition dealer status from UNVERIFIED → ACTIVE on confirmed valid VAT.
//
// REST endpoint (no auth required):
//
//	GET https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{country_code}/vat/{vat_number}
//
// Response example (valid):
//
//	{"isValid":true,"requestDate":"2026-04-15T10:00:00","userError":"VALID",
//	 "name":"GARAGE DUPONT SA","address":"12 RUE DE LA PAIX\n75001 PARIS"}
//
// Response example (invalid):
//
//	{"isValid":false,"requestDate":"...","userError":"INVALID","name":"---","address":"---"}
//
// Countries covered: DE, FR, ES, BE, NL (all EU VIES members in the 6-country scope).
// CH is NOT covered by VIES — use sub-technique M.2 (ch_uid) for Swiss dealers.
//
// Rate limiting: 1 req / 1 s (conservative; VIES has no published strict limit but
// the EC recommends <10 req/s globally across all member states).
//
// Stale threshold: 30 days — VAT status is re-validated after 30 days.
// ConfidenceContributed: 0.0 (BaseWeights["M"] = 0) — M is enrichment-only;
// confidence bumps are applied as deltas, not as primary discovery weight.
package vies

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/metrics"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID    = "M"
	subTechID   = "M.1"
	subTechName = "VIES VAT validation batch (EU)"

	defaultBaseURL     = "https://ec.europa.eu/taxation_customs/vies/rest-api"
	defaultReqInterval = time.Second
	staleDays          = 30

	// confidenceBump is added to confidence_score when VIES confirms valid VAT
	// AND the registered name contains the KG canonical name (case-insensitive).
	confidenceBump = 0.10

	cardexUA = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
)

// euCountries are the VIES-covered countries within the 6-country cardex scope.
var euCountries = []string{"DE", "FR", "ES", "BE", "NL"}

// VATStatus holds the parsed VIES response for a single VAT number lookup.
type VATStatus struct {
	Valid       bool
	UserError   string // "VALID", "INVALID", "NOT_FOUND", "SERVICE_UNAVAILABLE", etc.
	Name        string
	Address     string
	ValidatedAt time.Time
}

// viesResponse mirrors the VIES REST API JSON response.
type viesResponse struct {
	IsValid     bool   `json:"isValid"`
	RequestDate string `json:"requestDate"`
	UserError   string `json:"userError"`
	Name        string `json:"name"`
	Address     string `json:"address"`
}

// VIES executes the M.1 sub-technique VAT validation batch.
type VIES struct {
	graph       kg.KnowledgeGraph
	client      *http.Client
	baseURL     string
	reqInterval time.Duration
	log         *slog.Logger
}

// New returns a VIES executor with the production EC endpoint.
func New(graph kg.KnowledgeGraph) *VIES {
	return NewWithBaseURL(graph, defaultBaseURL, defaultReqInterval)
}

// NewWithBaseURL returns a VIES executor with a custom base URL and interval
// (use interval=0 in tests).
func NewWithBaseURL(graph kg.KnowledgeGraph, baseURL string, reqInterval time.Duration) *VIES {
	return &VIES{
		graph:       graph,
		client:      &http.Client{Timeout: 15 * time.Second},
		baseURL:     baseURL,
		reqInterval: reqInterval,
		log:         slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (v *VIES) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (v *VIES) Name() string { return subTechName }

// ValidateVAT performs a single VIES lookup. Exported for use in tests and
// from the CH UID package (for cross-validation helper reuse).
func (v *VIES) ValidateVAT(ctx context.Context, countryCode, vatNumber string) (*VATStatus, error) {
	// Strip country prefix if the VAT number already includes it.
	if strings.HasPrefix(strings.ToUpper(vatNumber), strings.ToUpper(countryCode)) {
		vatNumber = vatNumber[len(countryCode):]
	}
	vatNumber = strings.ReplaceAll(vatNumber, " ", "")
	vatNumber = strings.ReplaceAll(vatNumber, ".", "")

	reqURL := fmt.Sprintf("%s/ms/%s/vat/%s", v.baseURL, countryCode, vatNumber)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL, nil)
	if err != nil {
		return nil, fmt.Errorf("vies.ValidateVAT: build req: %w", err)
	}
	req.Header.Set("User-Agent", cardexUA)
	req.Header.Set("Accept", "application/json")

	resp, err := v.client.Do(req)
	if err != nil {
		metrics.SubTechniqueRequests.WithLabelValues(subTechID, "err").Inc()
		return nil, fmt.Errorf("vies.ValidateVAT: http: %w", err)
	}
	defer resp.Body.Close()

	metrics.SubTechniqueRequests.WithLabelValues(subTechID,
		fmt.Sprintf("%dxx", resp.StatusCode/100)).Inc()

	if resp.StatusCode != http.StatusOK {
		return &VATStatus{
			Valid:       false,
			UserError:   fmt.Sprintf("HTTP_%d", resp.StatusCode),
			ValidatedAt: time.Now().UTC(),
		}, nil
	}

	var vr viesResponse
	if err := json.NewDecoder(resp.Body).Decode(&vr); err != nil {
		return nil, fmt.Errorf("vies.ValidateVAT: decode JSON: %w", err)
	}

	status := &VATStatus{
		Valid:       vr.IsValid,
		UserError:   vr.UserError,
		Name:        vr.Name,
		Address:     vr.Address,
		ValidatedAt: time.Now().UTC(),
	}
	if status.UserError == "" {
		if vr.IsValid {
			status.UserError = "VALID"
		} else {
			status.UserError = "INVALID"
		}
	}
	return status, nil
}

// Run fetches all EU dealers with unvalidated or stale VAT numbers and validates
// each against VIES. Results are written back to the KG.
func (v *VIES) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: "EU"}

	candidates, err := v.graph.FindDealersForVATValidation(ctx, euCountries, staleDays)
	if err != nil {
		result.Errors++
		result.Duration = time.Since(start)
		return result, fmt.Errorf("vies.Run: find candidates: %w", err)
	}

	v.log.Info("vies: validation batch started", "candidates", len(candidates))

	for _, c := range candidates {
		if ctx.Err() != nil {
			break
		}

		if v.reqInterval > 0 {
			select {
			case <-ctx.Done():
				goto done
			case <-time.After(v.reqInterval):
			}
		}

		status, err := v.ValidateVAT(ctx, c.CountryCode, c.PrimaryVAT)
		if err != nil {
			v.log.Warn("vies: lookup error",
				"dealer", c.DealerID, "vat", c.PrimaryVAT, "err", err)
			result.Errors++
			// Record ERROR status so we don't retry immediately.
			_ = v.graph.UpdateVATValidation(ctx, c.DealerID, time.Now().UTC(), "ERROR")
			continue
		}

		if err := v.graph.UpdateVATValidation(ctx, c.DealerID, status.ValidatedAt, status.UserError); err != nil {
			v.log.Warn("vies: UpdateVATValidation error", "dealer", c.DealerID, "err", err)
			result.Errors++
			continue
		}

		if status.Valid {
			result.Confirmed++
			v.log.Debug("vies: VAT valid", "dealer", c.CanonicalName, "vat", c.PrimaryVAT)

			// Name match heuristic: VIES name ⊇ KG canonical name (case-insensitive)?
			if nameMatch(status.Name, c.CanonicalName) {
				newScore := c.ConfidenceScore + confidenceBump
				if newScore > 1.0 {
					newScore = 1.0
				}
				if err := v.graph.UpdateConfidenceScore(ctx, c.DealerID, newScore); err != nil {
					v.log.Warn("vies: UpdateConfidenceScore error", "dealer", c.DealerID, "err", err)
				}
			}
		} else {
			v.log.Debug("vies: VAT invalid/not found",
				"dealer", c.CanonicalName, "vat", c.PrimaryVAT, "status", status.UserError)
		}
	}

done:
	result.Duration = time.Since(start)
	metrics.CycleDuration.WithLabelValues(familyID, "EU").Observe(result.Duration.Seconds())
	v.log.Info("vies: done",
		"confirmed", result.Confirmed,
		"errors", result.Errors,
	)
	return result, nil
}

// nameMatch returns true if viesName contains kgName as a substring
// (case-insensitive), or if kgName contains a significant word from viesName.
// "---" is the VIES sentinel for unknown name — always returns false.
func nameMatch(viesName, kgName string) bool {
	if viesName == "" || viesName == "---" || kgName == "" {
		return false
	}
	v := strings.ToLower(strings.TrimSpace(viesName))
	k := strings.ToLower(strings.TrimSpace(kgName))
	return strings.Contains(v, k) || strings.Contains(k, v)
}
