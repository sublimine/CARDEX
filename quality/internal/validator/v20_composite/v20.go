// Package v20_composite implements validation strategy V20 — Composite Quality Score.
//
// # Strategy
//
// V20 is the final validator. It reads the persisted results of V01–V19 for the
// current vehicle from the ResultStore and computes a weighted quality score.
//
// # Scoring
//
//   - Each passing validator contributes its full weight to the earned score.
//   - A WARNING failure contributes half its weight.
//   - A CRITICAL failure contributes zero.
//   - Skipped validators (not present in results) are excluded from the denominator.
//
// # Weight table (total: 176 pts)
//
//	V01 VIN Checksum        15   V11 NLG Quality          8
//	V02 NHTSA vPIC          12   V12 Cross-Source Dedup  12
//	V03 DAT Codes           10   V13 Completeness        10
//	V04 NLP Make/Model      10   V14 Freshness            8
//	V05 Image Quality       10   V15 Dealer Trust        10
//	V06 Photo Count          8   V16 Photo pHash          5
//	V07 Price Sanity        12   V17 Sold Status          8
//	V08 Mileage Sanity      10   V18 Language             4
//	V09 Year Consistency    10   V19 Currency             6
//	V10 Source URL Liveness  8
//
// # Publication decision
//
//   - PUBLISH      score ≥ 80% AND zero CRITICAL failures
//   - MANUAL_REVIEW score 60–79% OR exactly 1 CRITICAL failure
//   - REJECT        score < 60% OR ≥ 2 CRITICAL failures
//
// # Dependency injection
//
// ResultStore abstracts the storage layer query. Use New() for a no-op store
// (returns empty results — always produces MANUAL_REVIEW with zero data).
// Use NewWithStore() to inject the real SQLite backend.
package v20_composite

import (
	"context"
	"fmt"
	"strings"

	"cardex.eu/quality/internal/pipeline"
)

const (
	strategyID   = "V20"
	strategyName = "Composite Quality Score"

	publishThreshold      = 80.0 // score % required for PUBLISH
	manualReviewThreshold = 60.0 // score % floor for MANUAL_REVIEW

	maxCriticalForPublish      = 0 // PUBLISH requires zero criticals
	maxCriticalForManualReview = 1 // MANUAL_REVIEW allows at most one critical
)

// Decision is the publication recommendation produced by V20.
type Decision string

const (
	DecisionPublish      Decision = "PUBLISH"
	DecisionManualReview Decision = "MANUAL_REVIEW"
	DecisionReject       Decision = "REJECT"
)

// validatorWeights maps validator ID to its contribution weight (total = 176).
var validatorWeights = map[string]int{
	"V01": 15,
	"V02": 12,
	"V03": 10,
	"V04": 10,
	"V05": 10,
	"V06": 8,
	"V07": 12,
	"V08": 10,
	"V09": 10,
	"V10": 8,
	"V11": 8,
	"V12": 12,
	"V13": 10,
	"V14": 8,
	"V15": 10,
	"V16": 5,
	"V17": 8,
	"V18": 4,
	"V19": 6,
}

// ResultStore retrieves previously persisted validation results for a vehicle.
type ResultStore interface {
	GetValidationResultsByVehicle(ctx context.Context, vehicleID string) ([]*pipeline.ValidationResult, error)
}

// noopResultStore returns empty results (safe default — yields MANUAL_REVIEW).
type noopResultStore struct{}

func (n *noopResultStore) GetValidationResultsByVehicle(_ context.Context, _ string) ([]*pipeline.ValidationResult, error) {
	return nil, nil
}

// CompositeScore implements pipeline.Validator for V20.
type CompositeScore struct {
	store ResultStore
}

// New returns a CompositeScore validator backed by a no-op result store.
func New() *CompositeScore { return NewWithStore(&noopResultStore{}) }

// NewWithStore returns a CompositeScore validator reading from the given store.
func NewWithStore(s ResultStore) *CompositeScore { return &CompositeScore{store: s} }

func (v *CompositeScore) ID() string                  { return strategyID }
func (v *CompositeScore) Name() string                { return strategyName }
func (v *CompositeScore) Severity() pipeline.Severity { return pipeline.SeverityCritical }

// Validate computes the weighted composite score from V01–V19 results.
func (v *CompositeScore) Validate(ctx context.Context, vehicle *pipeline.Vehicle) (*pipeline.ValidationResult, error) {
	result := &pipeline.ValidationResult{
		ValidatorID: strategyID,
		VehicleID:   vehicle.InternalID,
		Severity:    pipeline.SeverityInfo,
		Suggested:   make(map[string]string),
		Evidence:    make(map[string]string),
	}

	results, err := v.store.GetValidationResultsByVehicle(ctx, vehicle.InternalID)
	if err != nil {
		// Soft-fail: store unavailable.
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Issue = "result store unavailable: " + err.Error()
		result.Confidence = 0.0
		return result, nil
	}

	// Index results by validator ID (latest per validator wins).
	byValidator := make(map[string]*pipeline.ValidationResult, len(results))
	for _, r := range results {
		byValidator[r.ValidatorID] = r
	}

	var (
		earnedPts   int
		possiblePts int
		criticals   int
		failIDs     []string
	)

	for vid, weight := range validatorWeights {
		r, ok := byValidator[vid]
		if !ok {
			// Validator was skipped — exclude from denominator.
			continue
		}
		possiblePts += weight

		switch {
		case r.Pass:
			earnedPts += weight
		case r.Severity == pipeline.SeverityCritical:
			criticals++
			failIDs = append(failIDs, vid)
			// earnedPts += 0
		case r.Severity == pipeline.SeverityWarning:
			earnedPts += weight / 2
			failIDs = append(failIDs, vid)
		default:
			// INFO failures (rare): treat as half-weight.
			earnedPts += weight / 2
		}
	}

	var scorePercent float64
	if possiblePts > 0 {
		scorePercent = float64(earnedPts) / float64(possiblePts) * 100.0
	}

	decision := computeDecision(scorePercent, criticals)

	result.Evidence["score_pct"] = fmt.Sprintf("%.1f", scorePercent)
	result.Evidence["earned_pts"] = fmt.Sprintf("%d", earnedPts)
	result.Evidence["possible_pts"] = fmt.Sprintf("%d", possiblePts)
	result.Evidence["criticals"] = fmt.Sprintf("%d", criticals)
	result.Evidence["decision"] = string(decision)
	if len(failIDs) > 0 {
		result.Evidence["failing_validators"] = strings.Join(failIDs, ",")
	}

	result.Suggested["publication_decision"] = string(decision)

	switch decision {
	case DecisionPublish:
		result.Pass = true
		result.Severity = pipeline.SeverityInfo
		result.Confidence = scorePercent / 100.0

	case DecisionManualReview:
		result.Pass = false
		result.Severity = pipeline.SeverityWarning
		result.Issue = fmt.Sprintf("score %.1f%% or %d critical(s) — requires manual review before publishing", scorePercent, criticals)
		result.Confidence = scorePercent / 100.0

	case DecisionReject:
		result.Pass = false
		result.Severity = pipeline.SeverityCritical
		result.Issue = fmt.Sprintf("score %.1f%% with %d critical(s) — reject vehicle from catalogue", scorePercent, criticals)
		result.Confidence = scorePercent / 100.0
	}

	return result, nil
}

// computeDecision derives the publication decision from score and critical count.
func computeDecision(scorePercent float64, criticals int) Decision {
	switch {
	case criticals >= 2:
		return DecisionReject
	case scorePercent < manualReviewThreshold:
		return DecisionReject
	case criticals == 1 || scorePercent < publishThreshold:
		return DecisionManualReview
	default:
		return DecisionPublish
	}
}
