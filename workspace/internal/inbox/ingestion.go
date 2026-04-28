package inbox

import (
	"context"
	"log/slog"
	"sync"
	"time"
)

// IngestionEngine polls all registered InquirySources and feeds RawInquiries into the Processor.
type IngestionEngine struct {
	sources   []InquirySource
	processor *Processor
	log       *slog.Logger

	mu       sync.Mutex
	lastPoll map[string]time.Time
}

// NewIngestionEngine creates an engine that polls the given sources.
func NewIngestionEngine(proc *Processor, log *slog.Logger, sources ...InquirySource) *IngestionEngine {
	lp := make(map[string]time.Time, len(sources))
	for _, s := range sources {
		// default look-back: 24 hours on first poll
		lp[s.Name()] = time.Now().UTC().Add(-24 * time.Hour)
	}
	return &IngestionEngine{
		sources:   sources,
		processor: proc,
		log:       log,
		lastPoll:  lp,
	}
}

// PollOnce polls every source once and processes any new inquiries.
func (e *IngestionEngine) PollOnce(ctx context.Context, tenantID string) error {
	for _, src := range e.sources {
		e.mu.Lock()
		since := e.lastPoll[src.Name()]
		e.mu.Unlock()

		raw, err := src.Poll(ctx, since)
		if err != nil {
			e.log.Warn("poll failed", "source", src.Name(), "err", err)
			continue
		}

		now := time.Now().UTC()
		for _, r := range raw {
			if _, err := e.processor.Process(ctx, tenantID, r); err != nil {
				e.log.Warn("process failed", "source", src.Name(), "external_id", r.ExternalID, "err", err)
			}
		}

		e.mu.Lock()
		e.lastPoll[src.Name()] = now
		e.mu.Unlock()
	}
	return nil
}

// RunLoop polls all sources on the given interval until ctx is cancelled.
func (e *IngestionEngine) RunLoop(ctx context.Context, tenantID string, interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			_ = e.PollOnce(ctx, tenantID)
		}
	}
}
