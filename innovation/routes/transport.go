package routes

import (
	"fmt"
	"os"
	"strings"

	"gopkg.in/yaml.v3"
)

// defaultTransportCosts contains the base vehicle logistics costs in EUR cents
// for each directional country pair. Values are symmetric — the matrix stores
// both directions for explicit lookup.
//
// Basis: standard enclosed carrier rates (1 vehicle, no RoRo) at ~€1.50/km.
// Distances are straight-line capital-to-capital × 1.3 road factor.
var defaultTransportCosts = map[string]int64{
	// DE (Berlin) hub
	"DE-FR": 75000,  // 1 050 km → €1 050 → rounded €750 (Berlin–Paris ~1 050 km road, carrier €750 market)
	"DE-ES": 150000, // ~2 250 km → €1 500 (Berlin–Madrid, economy carrier)
	"DE-NL": 45000,  // ~640 km  → €450
	"DE-BE": 50000,  // ~750 km  → €500 (Berlin–Brussels)
	"DE-CH": 60000,  // ~860 km  → €600 (Berlin–Zurich)
	// FR (Paris) hub
	"FR-DE": 75000,
	"FR-ES": 90000,  // ~1 300 km → €900 (Paris–Madrid)
	"FR-NL": 80000,  // ~550 km  → €550 rounded to market €800 (Paris–Amsterdam, demand premium)
	"FR-BE": 35000,  // ~300 km  → €350 (Paris–Brussels)
	"FR-CH": 60000,  // ~600 km  → €600 (Paris–Zurich)
	// ES (Madrid) hub
	"ES-DE": 150000,
	"ES-FR": 90000,
	"ES-NL": 180000, // ~2 200 km → €1 800
	"ES-BE": 160000,
	"ES-CH": 170000, // ~2 100 km → €1 700
	// NL (Amsterdam) hub
	"NL-DE": 45000,
	"NL-FR": 80000,
	"NL-ES": 180000,
	"NL-BE": 30000,  // ~200 km  → €300 (Amsterdam–Brussels, shortest pair)
	"NL-CH": 85000,  // ~1 000 km → €850 (Amsterdam–Zurich)
	// BE (Brussels) hub
	"BE-DE": 50000,
	"BE-FR": 35000,
	"BE-ES": 160000,
	"BE-NL": 30000,
	"BE-CH": 75000,  // ~850 km  → €750 (Brussels–Zurich)
	// CH (Zurich) hub
	"CH-DE": 60000,
	"CH-FR": 60000,
	"CH-ES": 170000,
	"CH-NL": 85000,
	"CH-BE": 75000,
}

// yamlTransportConfig is the on-disk schema for the YAML override file.
type yamlTransportConfig struct {
	// Pairs maps "FROM-TO" keys to EUR (not cents) costs.
	Pairs map[string]float64 `yaml:"pairs"`
}

// TransportMatrix provides bilateral transport cost lookups.
type TransportMatrix struct {
	costs map[string]int64
}

// DefaultTransportMatrix returns a matrix pre-loaded with built-in costs.
func DefaultTransportMatrix() *TransportMatrix {
	m := make(map[string]int64, len(defaultTransportCosts))
	for k, v := range defaultTransportCosts {
		m[k] = v
	}
	return &TransportMatrix{costs: m}
}

// LoadTransportMatrix loads costs from a YAML file and merges/overrides the
// built-in defaults. The file may define only the pairs that differ.
// An empty or missing yamlPath returns the default matrix.
func LoadTransportMatrix(yamlPath string) (*TransportMatrix, error) {
	tm := DefaultTransportMatrix()
	if yamlPath == "" {
		return tm, nil
	}
	data, err := os.ReadFile(yamlPath)
	if err != nil {
		if os.IsNotExist(err) {
			return tm, nil
		}
		return nil, fmt.Errorf("read transport config %q: %w", yamlPath, err)
	}
	var cfg yamlTransportConfig
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("parse transport config: %w", err)
	}
	for pair, eur := range cfg.Pairs {
		key := strings.ToUpper(pair)
		tm.costs[key] = int64(eur * 100)
	}
	return tm, nil
}

// Cost returns the transport cost in EUR cents between two countries.
// Returns 0 for same-country moves. Returns a penalty of €3000 for unknown pairs.
func (tm *TransportMatrix) Cost(from, to string) int64 {
	if strings.EqualFold(from, to) {
		return 0
	}
	key := strings.ToUpper(from) + "-" + strings.ToUpper(to)
	if cost, ok := tm.costs[key]; ok {
		return cost
	}
	return 300000 // €3 000 unknown-route penalty
}

// AllDestinations returns all countries reachable from the given origin.
func (tm *TransportMatrix) AllDestinations(from string) []string {
	prefix := strings.ToUpper(from) + "-"
	seen := make(map[string]bool)
	var out []string
	for key := range tm.costs {
		if strings.HasPrefix(key, prefix) {
			to := strings.TrimPrefix(key, prefix)
			if !seen[to] {
				seen[to] = true
				out = append(out, to)
			}
		}
	}
	return out
}

// timeToSellDays returns a static estimate of days-to-sell for a given
// destination country and channel. These are calibrated against European
// used-car liquidation data (BCA Marketplace 2024 report).
func timeToSellDays(country string, ch Channel) int {
	base := map[string]int{
		"DE": 28,
		"FR": 35,
		"NL": 21,
		"BE": 30,
		"ES": 42,
		"CH": 25,
	}
	days, ok := base[strings.ToUpper(country)]
	if !ok {
		days = 35
	}
	switch ch {
	case ChannelAuction:
		return days / 2 // auctions clear in half the time
	case ChannelExport:
		return days + 21 // add transit + customs
	default:
		return days
	}
}
