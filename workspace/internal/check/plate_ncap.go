package check

// EuroNCAP resolver — fetches safety ratings from Euro NCAP's public API.
//
// Endpoint: GET https://www.euroncap.com/api/CarListRoute?path=%2Fassessments&limit=600
// No authentication required. Returns all 566 assessments.
// Ratings are model-level (same for all vehicles of a generation), not per-VIN.
//
// Data fetched once and cached in memory for ttl (default 24h).
// On cache miss the full list is re-downloaded (~70KB JSON).

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"
)

const ncapBaseHost = "https://www.euroncap.com/api/CarListRoute?path=%2Fassessments&limit=100&offset="

// ncapScore holds the normalised percentage score for one rating dimension.
type ncapScore struct {
	NormalisedScore float64 `json:"normalisedScore"`
}

// ncapCarSafety holds the car safety nested block returned by the list endpoint.
type ncapCarSafety struct {
	SafetyRatingStars int `json:"safetyRatingStars"`
}

// ncapAssessment mirrors the subset of fields we extract from CarListRoute.
// The list endpoint returns carSafety.safetyRatingStars; detailed percentage scores
// (adultOccupant.normalisedScore etc.) are only available in the detail endpoint.
type ncapAssessment struct {
	ID                  string        `json:"id"`
	RatingYear          int           `json:"ratingYear"`
	ResultApplicability string        `json:"resultApplicability"`
	CarSafety           ncapCarSafety `json:"carSafety"`
	AdultOccupant       ncapScore     `json:"adultOccupant"`
	ChildOccupant       ncapScore     `json:"childOccupant"`
	VulnerableRoadUser  ncapScore     `json:"vulnerableRoadUser"`
	SafetyAssist        ncapScore     `json:"safetyAssist"`
	Make                struct {
		Name string `json:"name"`
	} `json:"make"`
	Model struct {
		Name string `json:"name"`
	} `json:"model"`
}

// NCAPResult holds the resolved EuroNCAP data for a make/model.
type NCAPResult struct {
	Stars                 int
	AdultOccupantPct      float64
	ChildOccupantPct      float64
	VulnerableRoadUserPct float64
	SafetyAssistPct       float64
	RatingYear            int
	ResultApplicability   string
}

// NCAPResolver downloads and caches EuroNCAP assessments in memory.
type NCAPResolver struct {
	client      *http.Client
	mu          sync.RWMutex
	assessments []ncapAssessment
	fetchedAt   time.Time
	ttl         time.Duration
}

// NewNCAPResolver returns an NCAPResolver with a 24-hour cache TTL.
func NewNCAPResolver() *NCAPResolver {
	return &NCAPResolver{
		client: &http.Client{Timeout: 15 * time.Second},
		ttl:    24 * time.Hour,
	}
}

// Resolve looks up the most recent EuroNCAP rating for a given make and model.
// make and model are matched case-insensitively; partial model name matches succeed.
// Returns nil, nil when no NCAP data exists for this make/model.
func (r *NCAPResolver) Resolve(ctx context.Context, make, model string) (*NCAPResult, error) {
	assessments, err := r.getAssessments(ctx)
	if err != nil {
		return nil, err
	}

	makeLower := strings.ToLower(strings.TrimSpace(make))
	modelLower := strings.ToLower(strings.TrimSpace(model))

	var best *ncapAssessment
	for i := range assessments {
		a := &assessments[i]
		if !strings.Contains(strings.ToLower(a.Make.Name), makeLower) {
			continue
		}
		if !strings.Contains(strings.ToLower(a.Model.Name), modelLower) &&
			!strings.Contains(modelLower, strings.ToLower(a.Model.Name)) {
			continue
		}
		if best == nil || a.RatingYear > best.RatingYear {
			best = a
		}
	}

	if best == nil {
		return nil, nil
	}

	return &NCAPResult{
		Stars:                 best.CarSafety.SafetyRatingStars,
		AdultOccupantPct:      best.AdultOccupant.NormalisedScore,
		ChildOccupantPct:      best.ChildOccupant.NormalisedScore,
		VulnerableRoadUserPct: best.VulnerableRoadUser.NormalisedScore,
		SafetyAssistPct:       best.SafetyAssist.NormalisedScore,
		RatingYear:            best.RatingYear,
		ResultApplicability:   best.ResultApplicability,
	}, nil
}

// getAssessments returns the cached list, refreshing when the TTL has expired.
func (r *NCAPResolver) getAssessments(ctx context.Context) ([]ncapAssessment, error) {
	r.mu.RLock()
	if len(r.assessments) > 0 && time.Since(r.fetchedAt) < r.ttl {
		out := r.assessments
		r.mu.RUnlock()
		return out, nil
	}
	r.mu.RUnlock()

	r.mu.Lock()
	defer r.mu.Unlock()
	// Double-check after acquiring write lock.
	if len(r.assessments) > 0 && time.Since(r.fetchedAt) < r.ttl {
		return r.assessments, nil
	}

	// Use an independent background context — the download must not be
	// cancelled when the triggering HTTP request context expires.
	dlCtx, dlCancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer dlCancel()

	// The EuroNCAP API caps responses at 100 items per page; paginate until done.
	var list []ncapAssessment
	for offset := 0; ; offset += 100 {
		url := fmt.Sprintf("%s%d", ncapBaseHost, offset)
		req, err := http.NewRequestWithContext(dlCtx, http.MethodGet, url, nil)
		if err != nil {
			break
		}
		req.Header.Set("User-Agent", plateUA)
		req.Header.Set("Referer", "https://www.euroncap.com/ratings-rewards/latest-safety-ratings/")
		req.Header.Set("Accept", "application/json, text/plain, */*")
		req.Header.Set("sec-ch-ua", "?1")
		req.Header.Set("sec-ch-ua-mobile", "?0")
		req.Header.Set("sec-ch-ua-platform", `"Windows"`)

		resp, err := r.client.Do(req)
		if err != nil {
			break
		}
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 5*1024*1024))
		resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			break
		}

		var envelope struct {
			Meta struct {
				TotalCount int `json:"totalCount"`
				Count      int `json:"count"`
			} `json:"meta"`
			Items []ncapAssessment `json:"items"`
		}
		if err := json.Unmarshal(body, &envelope); err != nil || len(envelope.Items) == 0 {
			break
		}
		list = append(list, envelope.Items...)
		if len(list) >= envelope.Meta.TotalCount || envelope.Meta.Count < 100 {
			break
		}
	}

	if len(list) == 0 {
		return nil, fmt.Errorf("%w: EuroNCAP returned no assessments", ErrPlateResolutionUnavailable)
	}

	r.assessments = list
	r.fetchedAt = time.Now()
	return list, nil
}
