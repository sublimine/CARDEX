package pipeline

// Router selects and orders strategies for a specific dealer based on its hints,
// producing a priority-ordered slice of applicable strategies.
//
// The router encodes the routing logic from the extraction pipeline overview:
//
//	DMS_HOSTED + DMSProvider set     → try E05 first, then E03, E07, E12
//	CMS_WORDPRESS + vehicle plugin   → try E02 first, then E01, E03, E07, E12
//	CMS_SHOPIFY / modern CMS         → try E01 first, then E03, E07, E12
//	UNKNOWN / NATIVE                 → try E01, E03, E06, E07 in order
//
// The router is advisory: the Orchestrator's natural priority sort produces the
// same ordering in most cases. Router.ForDealer can be used when you want
// strategy selection logic separated from ordering logic.
type Router struct {
	all []ExtractionStrategy
}

// NewRouter constructs a Router from all registered strategies.
func NewRouter(strategies ...ExtractionStrategy) *Router {
	return &Router{all: strategies}
}

// ForDealer returns the strategies applicable to the given dealer,
// sorted by priority (highest first). This is a filter+sort over r.all.
func (r *Router) ForDealer(dealer Dealer) []ExtractionStrategy {
	var applicable []ExtractionStrategy
	for _, s := range r.all {
		if s.Applicable(dealer) {
			applicable = append(applicable, s)
		}
	}
	// strategies are already sorted in r.all if loaded through Orchestrator,
	// but sort defensively here too.
	sortStrategiesByPriority(applicable)
	return applicable
}

// sortStrategiesByPriority sorts strategies highest-priority first (in-place).
func sortStrategiesByPriority(ss []ExtractionStrategy) {
	for i := 1; i < len(ss); i++ {
		for j := i; j > 0 && ss[j].Priority() > ss[j-1].Priority(); j-- {
			ss[j], ss[j-1] = ss[j-1], ss[j]
		}
	}
}
