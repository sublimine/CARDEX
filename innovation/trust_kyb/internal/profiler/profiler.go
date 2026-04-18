// Package profiler computes weighted DealerTrustProfile scores from dealer signals.
//
// Weight breakdown (must sum to 100):
//
//	VIES verification      20 %
//	Registry status        15 %
//	V15 Trust Score        20 %  (capped 50 % for first 30 days — trust ramp-up)
//	Behavioral signals     25 %  (volume 8 + quality 10 + tenure 7)
//	Anomaly absence        20 %
package profiler

import (
	"math"
	"time"

	"cardex.eu/trust/internal/model"
)

// Input carries all raw signals needed to compute a DealerTrustProfile.
// All numeric fields should be non-negative.
type Input struct {
	DealerID          string
	DealerName        string
	Country           string
	VATID             string
	VIESStatus        string  // "valid" | "invalid" | "unchecked"
	RegistryStatus    string  // "registered" | "not_found" | "unchecked"
	RegistryAge       int     // years since commercial registration
	V15Score          float64 // 0–100
	ListingVolume     int
	AvgCompositeScore float64 // 0–100
	IndexTenureDays   int
	AnomalyCount      int
	BadgeBaseURL      string    // e.g. "http://localhost:8505"
	Now               time.Time // injectable for tests; zero = time.Now().UTC()
}

// Compute scores a DealerTrustProfile from the provided signals.
// All five weight components are bounded; total is clamped to [0, 100].
func Compute(in Input) *model.DealerTrustProfile {
	if in.Now.IsZero() {
		in.Now = time.Now().UTC()
	}

	vies := viesPoints(in.VIESStatus)
	reg := registryPoints(in.RegistryStatus, in.RegistryAge)
	v15 := v15Points(in.V15Score, in.IndexTenureDays)
	behav := behavioralPoints(in.ListingVolume, in.AvgCompositeScore, in.IndexTenureDays)
	anomaly := anomalyPoints(in.AnomalyCount)

	total := math.Max(0, math.Min(100, vies+reg+v15+behav+anomaly))
	tier := model.TierFromScore(total)
	issuedAt := in.Now
	expiresAt := issuedAt.Add(90 * 24 * time.Hour)
	hash := model.ComputeHash(in.DealerID, total, issuedAt)
	badgeURL := in.BadgeBaseURL + "/trust/badge/" + in.DealerID + ".svg"

	return &model.DealerTrustProfile{
		DealerID:          in.DealerID,
		DealerName:        in.DealerName,
		Country:           in.Country,
		VATID:             in.VATID,
		VIESStatus:        in.VIESStatus,
		RegistryStatus:    in.RegistryStatus,
		RegistryAge:       in.RegistryAge,
		V15Score:          in.V15Score,
		ListingVolume:     in.ListingVolume,
		AvgCompositeScore: in.AvgCompositeScore,
		IndexTenureDays:   in.IndexTenureDays,
		AnomalyCount:      in.AnomalyCount,
		TrustScore:        total,
		TrustTier:         tier,
		BadgeURL:          badgeURL,
		IssuedAt:          issuedAt,
		ExpiresAt:         expiresAt,
		ProfileHash:       hash,
	}
}

// ScoreBreakdown returns the per-component point allocations for a given Input.
// Useful for audit trails and CLI display.
type ScoreBreakdown struct {
	VIESPoints      float64
	RegistryPoints  float64
	V15Points       float64
	BehavioralPoints float64
	AnomalyPoints   float64
	Total           float64
}

// Breakdown returns the per-component breakdown without building the full profile.
func Breakdown(in Input) ScoreBreakdown {
	v := viesPoints(in.VIESStatus)
	r := registryPoints(in.RegistryStatus, in.RegistryAge)
	v15 := v15Points(in.V15Score, in.IndexTenureDays)
	b := behavioralPoints(in.ListingVolume, in.AvgCompositeScore, in.IndexTenureDays)
	a := anomalyPoints(in.AnomalyCount)
	return ScoreBreakdown{
		VIESPoints:       v,
		RegistryPoints:   r,
		V15Points:        v15,
		BehavioralPoints: b,
		AnomalyPoints:    a,
		Total:            math.Max(0, math.Min(100, v+r+v15+b+a)),
	}
}

// ── component functions ───────────────────────────────────────────────────────

// viesPoints returns 0–20 based on EU VAT VIES verification status.
// valid=20, unchecked=10 (partial credit — VAT present but not live-checked), invalid=0.
func viesPoints(status string) float64 {
	switch status {
	case "valid":
		return 20
	case "unchecked":
		return 10
	default:
		return 0
	}
}

// registryPoints returns 0–15 based on commercial registry verification.
// Base 12 pts for "registered", up to +3 pts for registry age (full at 5+ years).
// "unchecked" = 7 (company exists but not yet verified), "not_found" = 0.
func registryPoints(status string, ageYears int) float64 {
	switch status {
	case "registered":
		ageBonus := math.Min(3, float64(ageYears)/5.0*3)
		return 12 + ageBonus
	case "unchecked":
		return 7
	default:
		return 0
	}
}

// v15Points maps the V15 quality-pipeline trust score (0–100) to 0–20 pts.
// Trust ramp-up: for dealers indexed fewer than 30 days the contribution is
// capped at 10 pts (50 % of maximum) to prevent score gaming via fresh accounts.
func v15Points(score float64, tenureDays int) float64 {
	pts := score / 100.0 * 20.0
	if tenureDays < 30 {
		pts = math.Min(pts, 10)
	}
	return pts
}

// behavioralPoints returns 0–25 from three index-derived signals:
//   - Volume (0–8 pts): 50 active listings = full
//   - Composite quality (0–10 pts): avg composite score maps linearly
//   - Index tenure (0–7 pts): 365 days = full
func behavioralPoints(volume int, avgComposite float64, tenureDays int) float64 {
	volPts := math.Min(8, float64(volume)/50.0*8)
	qualPts := avgComposite / 100.0 * 10
	tenurePts := math.Min(7, float64(tenureDays)/365.0*7)
	return volPts + qualPts + tenurePts
}

// anomalyPoints returns 0–20: starts at 20 and deducts 4 per anomaly signal,
// floored at 0. Anomalies include EV Watch battery flags, bulk rejections, and
// publish-then-withdraw patterns detected by the quality pipeline.
func anomalyPoints(count int) float64 {
	return math.Max(0, 20-float64(count)*4)
}
