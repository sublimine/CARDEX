package pipeline

import (
	"context"
	"fmt"
	"log/slog"
	"sort"
)

// Orchestrator composes extraction strategies in priority order and runs the
// cascade: attempt each applicable strategy from highest to lowest priority
// until one succeeds.
type Orchestrator struct {
	strategies []ExtractionStrategy
	storage    Storage
	log        *slog.Logger
}

// New constructs an Orchestrator with the given strategies and storage.
// Strategies are automatically sorted by Priority() descending.
func New(storage Storage, strategies ...ExtractionStrategy) *Orchestrator {
	o := &Orchestrator{
		strategies: strategies,
		storage:    storage,
		log:        slog.Default().With("component", "orchestrator"),
	}
	o.sortByPriority()
	return o
}

// sortByPriority orders strategies highest Priority first.
func (o *Orchestrator) sortByPriority() {
	sort.Slice(o.strategies, func(i, j int) bool {
		return o.strategies[i].Priority() > o.strategies[j].Priority()
	})
}

// ExtractForDealer runs the strategy cascade for a single dealer.
// Returns the first FullSuccess or PartialSuccess result.
// If no strategy succeeds, returns a result with NextFallback="E11".
func (o *Orchestrator) ExtractForDealer(ctx context.Context, dealer Dealer) (*ExtractionResult, error) {
	o.log.Info("extraction cascade starting",
		"dealer_id", dealer.ID,
		"domain", dealer.Domain,
		"strategies_count", len(o.strategies),
	)

	var lastResult *ExtractionResult

	for _, strategy := range o.strategies {
		if ctx.Err() != nil {
			return lastResult, ctx.Err()
		}
		if !strategy.Applicable(dealer) {
			continue
		}

		o.log.Debug("attempting strategy",
			"strategy", strategy.ID(),
			"dealer_id", dealer.ID,
		)

		result, err := strategy.Extract(ctx, dealer)
		if err != nil {
			o.log.Warn("strategy failed",
				"strategy", strategy.ID(),
				"dealer_id", dealer.ID,
				"err", err,
			)
			continue
		}

		classifyResult(result)
		lastResult = result

		if result.FullSuccess || result.PartialSuccess {
			o.log.Info("strategy succeeded",
				"strategy", strategy.ID(),
				"dealer_id", dealer.ID,
				"vehicles", len(result.Vehicles),
				"full_success", result.FullSuccess,
			)
			if o.storage != nil && len(result.Vehicles) > 0 {
				n, persErr := o.storage.PersistVehicles(ctx, dealer.ID, result.Vehicles)
				if persErr != nil {
					o.log.Warn("PersistVehicles failed",
						"dealer_id", dealer.ID,
						"err", persErr,
					)
				} else {
					o.log.Debug("vehicles persisted", "dealer_id", dealer.ID, "new", n)
				}
			}
			return result, nil
		}

		// Strategy returned data but nothing usable — honour its suggested fallback.
		if result.NextFallback != nil {
			if next := o.findByID(*result.NextFallback); next != nil && next.Applicable(dealer) {
				fbResult, fbErr := next.Extract(ctx, dealer)
				if fbErr == nil {
					classifyResult(fbResult)
					if fbResult.FullSuccess || fbResult.PartialSuccess {
						return fbResult, nil
					}
				}
			}
		}
	}

	// All automatic strategies exhausted → route to dead-letter / E11.
	if lastResult == nil {
		lastResult = &ExtractionResult{
			DealerID: dealer.ID,
			Strategy: "none",
		}
	}
	e11 := "E11"
	lastResult.NextFallback = &e11
	lastResult.Errors = append(lastResult.Errors, ExtractionError{
		Code:    "NO_STRATEGY_SUCCEEDED",
		Message: fmt.Sprintf("all applicable strategies exhausted for dealer %s", dealer.ID),
		Fatal:   true,
	})
	return lastResult, nil
}

// findByID returns the strategy with the given ID, or nil.
func (o *Orchestrator) findByID(id string) ExtractionStrategy {
	for _, s := range o.strategies {
		if s.ID() == id {
			return s
		}
	}
	return nil
}

// Strategies returns the sorted strategy list (for inspection/testing).
func (o *Orchestrator) Strategies() []ExtractionStrategy {
	out := make([]ExtractionStrategy, len(o.strategies))
	copy(out, o.strategies)
	return out
}
