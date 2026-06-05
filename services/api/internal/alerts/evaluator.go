package alerts

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"log/slog"
	"sort"
	"strings"
	"time"

	"cardex.eu/api/internal/arbitrage"
	"cardex.eu/api/internal/metrics"
	"cardex.eu/api/internal/redisx"
	"cardex.eu/api/internal/store"
)

// Evaluator periodically scans active alerts for arbitrage opportunities and
// dispatches notifications when the opportunity set changes.
type Evaluator struct {
	store    *Store
	arb      *arbitrage.Service
	redis    *redisx.Client
	notifier *Notifier
	interval time.Duration
	log      *slog.Logger
	now      func() time.Time
}

// NewEvaluator builds an Evaluator.
func NewEvaluator(s *Store, arb *arbitrage.Service, r *redisx.Client, n *Notifier, interval time.Duration, log *slog.Logger) *Evaluator {
	return &Evaluator{
		store: s, arb: arb, redis: r, notifier: n,
		interval: interval, log: log, now: time.Now,
	}
}

// Run evaluates alerts on a ticker until ctx is cancelled. It runs one pass
// immediately so freshly-created alerts are not delayed by a full interval.
func (e *Evaluator) Run(ctx context.Context) {
	e.log.Info("alert evaluator started", "interval", e.interval.String())
	ticker := time.NewTicker(e.interval)
	defer ticker.Stop()

	e.evaluateOnce(ctx)
	for {
		select {
		case <-ctx.Done():
			e.log.Info("alert evaluator stopped")
			return
		case <-ticker.C:
			e.evaluateOnce(ctx)
		}
	}
}

// evaluateOnce runs a single evaluation pass over all active alerts.
func (e *Evaluator) evaluateOnce(ctx context.Context) {
	metrics.AlertEvalRuns.Inc()
	alerts, err := e.store.ListActive(ctx)
	if err != nil {
		e.log.Error("alert evaluation: list active failed", "err", err)
		return
	}
	for _, a := range alerts {
		if err := e.evaluateAlert(ctx, a); err != nil {
			e.log.Warn("alert evaluation failed", "alert_id", a.ID, "err", err)
		}
	}
}

// evaluateAlert evaluates one alert and notifies if a new opportunity set is found.
func (e *Evaluator) evaluateAlert(ctx context.Context, a Alert) error {
	f := store.Filter{
		Make:       a.Make,
		Model:      a.Model,
		YearMin:    a.YearMin,
		YearMax:    a.YearMax,
		Fuel:       a.Fuel,
		MileageMin: a.MileageMin,
		MileageMax: a.MileageMax,
	}
	opts := arbitrage.Options{
		MinMarginPct:  a.MinMarginPct,
		BuyCountries:  a.BuyCountries,
		SellCountries: a.SellCountries,
	}

	resp, err := e.arb.Find(ctx, f, nil, opts)
	if err != nil {
		return fmt.Errorf("find opportunities: %w", err)
	}
	if len(resp.Opportunities) == 0 {
		return nil // nothing to notify
	}

	sig := signature(resp.Opportunities)
	prev, err := e.redis.AlertSignature(ctx, a.ID)
	if err != nil {
		e.log.Warn("alert signature read failed (will notify)", "alert_id", a.ID, "err", err)
	}
	if sig == prev {
		return nil // already notified this exact opportunity set
	}

	payload := NotificationPayload{
		AlertID:       a.ID,
		Make:          a.Make,
		Model:         a.Model,
		MinMarginPct:  a.MinMarginPct,
		GeneratedAt:   e.now().UTC(),
		Opportunities: resp.Opportunities,
	}

	delivered := e.dispatch(ctx, a, payload)
	if !delivered {
		return fmt.Errorf("no channel delivered the notification")
	}

	if err := e.redis.SetAlertNotified(ctx, a.ID, sig, e.now()); err != nil {
		e.log.Warn("persist alert signature failed", "alert_id", a.ID, "err", err)
	}
	return nil
}

// dispatch sends the notification on every configured channel, returning true if
// at least one succeeded.
func (e *Evaluator) dispatch(ctx context.Context, a Alert, payload NotificationPayload) bool {
	delivered := false
	if a.WebhookURL != "" {
		if err := e.notifier.Webhook(ctx, a.WebhookURL, payload); err != nil {
			e.log.Warn("webhook dispatch failed", "alert_id", a.ID, "err", err)
			metrics.AlertNotificationsSent.WithLabelValues("webhook", "error").Inc()
		} else {
			delivered = true
			metrics.AlertNotificationsSent.WithLabelValues("webhook", "ok").Inc()
		}
	}
	if a.Email != "" {
		if err := e.notifier.Email(a.Email, payload); err != nil {
			e.log.Warn("email dispatch failed", "alert_id", a.ID, "err", err)
			metrics.AlertNotificationsSent.WithLabelValues("email", "error").Inc()
		} else {
			delivered = true
			metrics.AlertNotificationsSent.WithLabelValues("email", "ok").Inc()
		}
	}
	return delivered
}

// signature is a deterministic fingerprint of an opportunity set, used to dedup
// notifications. It is stable regardless of result ordering.
func signature(opps []arbitrage.Opportunity) string {
	keys := make([]string, 0, len(opps))
	for _, op := range opps {
		keys = append(keys, fmt.Sprintf("%s|%s|%s|%.0f",
			op.BuyCountry, op.SellCountry, op.Listing.ID, op.NetMarginEUR))
	}
	sort.Strings(keys)
	sum := sha256.Sum256([]byte(strings.Join(keys, ";")))
	return hex.EncodeToString(sum[:16])
}
