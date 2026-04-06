package scoring

import (
	"math"
	"math/rand/v2"
	"time"
)

// CompositeScorer computes crawl priority scores using multiple signals.
//
// The composite priority formula:
//   priority = w1×info_gain + w2×econ_value + w3×freshness + w4×demand + w5×thompson
//
// Where:
//   info_gain    = -log2(coverage) if coverage < 1.0, normalized to [0,1]
//   econ_value   = economic value of unseen listings, normalized to [0,1]
//   freshness    = 1 - exp(-λ × hours_since_last_crawl), λ=0.05
//   demand       = normalized search/alert count from ClickHouse (0 if unavailable)
//   thompson     = sample from Beta(alpha+1, beta+1) distribution
type CompositeScorer struct {
	W1 float64 // Information gain weight
	W2 float64 // Economic value weight
	W3 float64 // Freshness decay weight
	W4 float64 // Demand signal weight
	W5 float64 // Thompson Sampling weight

	FreshnessLambda float64 // Decay constant for freshness
}

// NewCompositeScorer creates a scorer with default weights.
func NewCompositeScorer() *CompositeScorer {
	return &CompositeScorer{
		W1:              0.30,
		W2:              0.25,
		W3:              0.20,
		W4:              0.15,
		W5:              0.10,
		FreshnessLambda: 0.05, // ~14h half-life
	}
}

// InformationGain computes the information gain from crawling a cell with given coverage.
// Higher gain for lower coverage: a cell with 10% coverage has much more to discover than one at 90%.
// Returns a value in [0, 1].
func (s *CompositeScorer) InformationGain(coverage float64) float64 {
	if coverage <= 0 {
		return 1.0 // maximum gain — we know nothing
	}
	if coverage >= 1.0 {
		return 0.0 // no gain — fully covered
	}
	// -log2(coverage) ranges from 0 (coverage=1) to ∞ (coverage→0)
	// We cap at ~3.32 bits (coverage=0.10) and normalize to [0,1]
	gain := -math.Log2(coverage)
	maxGain := -math.Log2(0.10) // 3.32 bits
	if gain > maxGain {
		gain = maxGain
	}
	return gain / maxGain
}

// FreshnessDecay computes how stale a crawl is.
// Returns 0 for just-crawled, approaches 1.0 for very stale data.
func (s *CompositeScorer) FreshnessDecay(sinceLast time.Duration) float64 {
	hours := sinceLast.Hours()
	if hours <= 0 {
		return 0
	}
	return 1.0 - math.Exp(-s.FreshnessLambda*hours)
}

// ThompsonSample draws a sample from Beta(alpha, beta) distribution.
// Higher alpha (more successes) → higher expected sample.
// This implements the explore/exploit tradeoff:
// - Sources that found new listings (high alpha) get exploited
// - Sources with few observations (low alpha+beta) get explored due to variance
func (s *CompositeScorer) ThompsonSample(alpha, beta int) float64 {
	a := float64(alpha)
	b := float64(beta)
	if a < 1 {
		a = 1
	}
	if b < 1 {
		b = 1
	}
	// Use the Jöhnk algorithm for Beta distribution sampling
	return betaSample(a, b)
}

// Composite computes the final priority score from all components.
// All inputs should be in [0, 1].
func (s *CompositeScorer) Composite(infoGain, econValue, freshness, demand, thompson float64) float64 {
	return s.W1*clamp(infoGain) +
		s.W2*clamp(econValue) +
		s.W3*clamp(freshness) +
		s.W4*clamp(demand) +
		s.W5*clamp(thompson)
}

func clamp(v float64) float64 {
	if v < 0 {
		return 0
	}
	if v > 1 {
		return 1
	}
	return v
}

// betaSample generates a random sample from Beta(a, b) using the gamma distribution method.
func betaSample(a, b float64) float64 {
	x := gammaSample(a)
	y := gammaSample(b)
	if x+y == 0 {
		return 0.5
	}
	return x / (x + y)
}

// gammaSample generates a random sample from Gamma(shape, 1) using Marsaglia and Tsang's method.
func gammaSample(shape float64) float64 {
	if shape < 1 {
		// For shape < 1, use the property: Gamma(a) = Gamma(a+1) * U^(1/a)
		return gammaSample(shape+1) * math.Pow(rand.Float64(), 1.0/shape)
	}
	d := shape - 1.0/3.0
	c := 1.0 / math.Sqrt(9.0*d)
	for {
		var x, v float64
		for {
			x = rand.NormFloat64()
			v = 1.0 + c*x
			if v > 0 {
				break
			}
		}
		v = v * v * v
		u := rand.Float64()
		if u < 1.0-0.0331*(x*x)*(x*x) {
			return d * v
		}
		if math.Log(u) < 0.5*x*x+d*(1.0-v+math.Log(v)) {
			return d * v
		}
	}
}
