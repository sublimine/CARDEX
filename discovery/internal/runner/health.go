package runner

import (
	"context"
	"fmt"
	"runtime/debug"
	"sync"
)

// HealthStatus is the outcome of a health check.
type HealthStatus int

const (
	HealthOK       HealthStatus = 0
	HealthDegraded HealthStatus = 1
	HealthDown     HealthStatus = 2
)

// HealthReport aggregates health status across multiple FamilyRunners.
type HealthReport struct {
	Families map[string]HealthStatus
	Errors   map[string]error
}

// CheckAll runs HealthCheck concurrently on every FamilyRunner in families
// and returns a consolidated HealthReport.
//
// Concurrency model:
//   - One goroutine per family, bounded by len(families).
//   - Each goroutine recovers from panics; panics are reported as errors.
//   - A WaitGroup closes the channel once all goroutines finish so callers
//     can range over the channel without blocking indefinitely.
func CheckAll(ctx context.Context, families []FamilyRunner) *HealthReport {
	report := &HealthReport{
		Families: make(map[string]HealthStatus, len(families)),
		Errors:   make(map[string]error),
	}

	if len(families) == 0 {
		return report
	}

	type result struct {
		id  string
		err error
	}
	ch := make(chan result, len(families))

	var wg sync.WaitGroup
	for _, f := range families {
		f := f
		wg.Add(1)
		go func() {
			defer wg.Done()
			defer func() {
				if r := recover(); r != nil {
					ch <- result{
						id:  f.FamilyID(),
						err: fmt.Errorf("panic in HealthCheck: %v\n%s", r, debug.Stack()),
					}
				}
			}()
			err := f.HealthCheck(ctx)
			ch <- result{id: f.FamilyID(), err: err}
		}()
	}

	// Close the channel once all goroutines have finished so the range loop
	// below terminates without relying on an exact count.
	go func() {
		wg.Wait()
		close(ch)
	}()

	for r := range ch {
		if r.err != nil {
			report.Families[r.id] = HealthDown
			report.Errors[r.id] = fmt.Errorf("family %s: %w", r.id, r.err)
		} else {
			report.Families[r.id] = HealthOK
		}
	}
	return report
}
