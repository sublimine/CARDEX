package runner

import (
	"context"
	"fmt"
)

// HealthStatus is the outcome of a health check.
type HealthStatus int

const (
	HealthOK      HealthStatus = 0
	HealthDegraded HealthStatus = 1
	HealthDown    HealthStatus = 2
)

// HealthReport aggregates health status across multiple FamilyRunners.
type HealthReport struct {
	Families map[string]HealthStatus
	Errors   map[string]error
}

// CheckAll runs HealthCheck concurrently on every FamilyRunner in families
// and returns a consolidated HealthReport.
func CheckAll(ctx context.Context, families []FamilyRunner) *HealthReport {
	report := &HealthReport{
		Families: make(map[string]HealthStatus, len(families)),
		Errors:   make(map[string]error),
	}

	type result struct {
		id  string
		err error
	}
	ch := make(chan result, len(families))

	for _, f := range families {
		f := f
		go func() {
			err := f.HealthCheck(ctx)
			ch <- result{id: f.FamilyID(), err: err}
		}()
	}

	for range families {
		r := <-ch
		if r.err != nil {
			report.Families[r.id] = HealthDown
			report.Errors[r.id] = fmt.Errorf("family %s: %w", r.id, r.err)
		} else {
			report.Families[r.id] = HealthOK
		}
	}
	return report
}
