package syndication

import (
	"context"
	"log/slog"
	"time"
)

const (
	syncInterval  = 30 * time.Minute
	retryInterval = 1 * time.Hour
)

// Scheduler runs periodic sync and retry cycles for the SyndicationEngine.
type Scheduler struct {
	engine     *SyndicationEngine
	getListing func(vehicleID string) (PlatformListing, error)
	log        *slog.Logger
}

// NewScheduler constructs a Scheduler.
// getListing is called to load the current listing data for a vehicle during retries.
func NewScheduler(engine *SyndicationEngine, getListing func(vehicleID string) (PlatformListing, error), log *slog.Logger) *Scheduler {
	return &Scheduler{engine: engine, getListing: getListing, log: log}
}

// Run starts the background scheduler and blocks until ctx is cancelled.
func (s *Scheduler) Run(ctx context.Context) {
	syncTicker := time.NewTicker(syncInterval)
	retryTicker := time.NewTicker(retryInterval)
	defer syncTicker.Stop()
	defer retryTicker.Stop()

	s.log.Info("syndication scheduler started",
		"sync_interval", syncInterval,
		"retry_interval", retryInterval,
	)

	for {
		select {
		case <-ctx.Done():
			s.log.Info("syndication scheduler stopped")
			return
		case <-syncTicker.C:
			if err := s.engine.SyncAll(ctx); err != nil {
				s.log.Error("syndication sync_all error", "err", err)
			} else {
				s.log.Info("syndication sync_all complete")
			}
		case <-retryTicker.C:
			if err := s.engine.RetryErrors(ctx, s.getListing); err != nil {
				s.log.Error("syndication retry_errors error", "err", err)
			} else {
				s.log.Info("syndication retry_errors complete")
			}
		}
	}
}

// OnVehicleStateChange should be called whenever a vehicle changes state.
// If the new state is "sold" or "reserved", the engine withdraws all publications.
func (s *Scheduler) OnVehicleStateChange(ctx context.Context, vehicleID, newState string) {
	if newState == "sold" || newState == "reserved" {
		if err := s.engine.WithdrawVehicle(ctx, vehicleID); err != nil {
			s.log.Error("auto-withdraw failed",
				"vehicle_id", vehicleID,
				"state", newState,
				"err", err,
			)
		} else {
			s.log.Info("auto-withdrew syndication",
				"vehicle_id", vehicleID,
				"state", newState,
			)
		}
	}
}
