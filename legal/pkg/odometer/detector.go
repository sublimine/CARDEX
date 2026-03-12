// Package odometer implements odometer rollback detection via ClickHouse mileage history.
package odometer

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	_ "github.com/ClickHouse/clickhouse-go/v2"
)

const (
	rollbackThreshold = 500
	queryTimeout      = 5 * time.Second
)

// RollbackResult holds the result of rollback detection.
type RollbackResult struct {
	Detected     bool
	HistoricalMax int
	Delta        int
}

// MileageQuerier queries historical mileage from storage. Implemented by ClickHouse; mock for tests.
type MileageQuerier interface {
	QueryMax(ctx context.Context, vin string) (maxMileage int, found bool, err error)
}

// clickHouseMileageQuerier implements MileageQuerier using ClickHouse.
type clickHouseMileageQuerier struct {
	db *sql.DB
}

func (c *clickHouseMileageQuerier) QueryMax(ctx context.Context, vin string) (int, bool, error) {
	queryCtx, cancel := context.WithTimeout(ctx, queryTimeout)
	defer cancel()

	var historicalMax sql.NullInt64
	err := c.db.QueryRowContext(queryCtx,
		"SELECT max(mileage) AS historical_max FROM cardex_forensics.mileage_history WHERE vin = ?",
		vin,
	).Scan(&historicalMax)
	if err == sql.ErrNoRows {
		return 0, false, nil
	}
	if err != nil {
		return 0, false, fmt.Errorf("odometer: %w", err)
	}
	if !historicalMax.Valid {
		return 0, false, nil
	}
	return int(historicalMax.Int64), true, nil
}

// Detector detects odometer rollback via historical mileage comparison.
type Detector struct {
	querier MileageQuerier
}

// New creates a Detector connected to ClickHouse at the given DSN.
func New(chDSN string) (*Detector, error) {
	db, err := sql.Open("clickhouse", chDSN)
	if err != nil {
		return nil, fmt.Errorf("odometer: %w", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(ctx); err != nil {
		db.Close()
		return nil, fmt.Errorf("odometer: %w", err)
	}
	return &Detector{querier: &clickHouseMileageQuerier{db: db}}, nil
}

// NewWithQuerier creates a Detector with explicit querier (for testing).
func NewWithQuerier(querier MileageQuerier) *Detector {
	return &Detector{querier: querier}
}

// CheckRollback queries ClickHouse for historical max mileage and detects rollback.
// If historical_max > currentMileage + 500, returns Detected=true with Delta.
func (d *Detector) CheckRollback(ctx context.Context, vin string, currentMileage int) (RollbackResult, error) {
	historicalMax, found, err := d.querier.QueryMax(ctx, vin)
	if err != nil {
		return RollbackResult{}, err
	}
	if !found {
		return RollbackResult{Detected: false}, nil
	}
	if historicalMax > currentMileage+rollbackThreshold {
		return RollbackResult{
			Detected:     true,
			HistoricalMax: historicalMax,
			Delta:        historicalMax - currentMileage,
		}, nil
	}
	return RollbackResult{
		Detected:     false,
		HistoricalMax: historicalMax,
		Delta:        0,
	}, nil
}
