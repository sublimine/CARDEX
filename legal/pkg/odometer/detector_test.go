package odometer

import (
	"context"
	"testing"
)

type mockMileageQuerier struct {
	maxMileage int
	found     bool
	err       error
}

func (m *mockMileageQuerier) QueryMax(ctx context.Context, vin string) (int, bool, error) {
	if m.err != nil {
		return 0, false, m.err
	}
	return m.maxMileage, m.found, nil
}

func TestDetector_CheckRollback(t *testing.T) {
	tests := []struct {
		name           string
		mockMax        int
		mockFound      bool
		mockErr        error
		currentMileage int
		wantDetected   bool
		wantDelta      int
		wantHistorical int
		wantErr        bool
	}{
		{
			name:           "no history",
			mockMax:        0,
			mockFound:      false,
			currentMileage: 80000,
			wantDetected:   false,
			wantDelta:      0,
			wantHistorical: 0,
		},
		{
			name:           "rollback detected",
			mockMax:        150000,
			mockFound:      true,
			currentMileage: 80000,
			wantDetected:   true,
			wantDelta:      70000,
			wantHistorical: 150000,
		},
		{
			name:           "normal wear",
			mockMax:        80000,
			mockFound:      true,
			currentMileage: 85000,
			wantDetected:   false,
			wantDelta:      0,
			wantHistorical: 80000,
		},
		{
			name:           "within tolerance 500km",
			mockMax:        80400,
			mockFound:      true,
			currentMileage: 80000,
			wantDetected:   false,
			wantDelta:      0,
			wantHistorical: 80400,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			mock := &mockMileageQuerier{maxMileage: tt.mockMax, found: tt.mockFound, err: tt.mockErr}
			det := NewWithQuerier(mock)
			ctx := context.Background()

			got, err := det.CheckRollback(ctx, "WBA123", tt.currentMileage)
			if tt.wantErr {
				if err == nil {
					t.Errorf("CheckRollback() expected error, got nil")
				}
				return
			}
			if err != nil {
				t.Errorf("CheckRollback() unexpected error: %v", err)
				return
			}
			if got.Detected != tt.wantDetected {
				t.Errorf("CheckRollback() Detected = %v, want %v", got.Detected, tt.wantDetected)
			}
			if got.Delta != tt.wantDelta {
				t.Errorf("CheckRollback() Delta = %d, want %d", got.Delta, tt.wantDelta)
			}
			if got.HistoricalMax != tt.wantHistorical {
				t.Errorf("CheckRollback() HistoricalMax = %d, want %d", got.HistoricalMax, tt.wantHistorical)
			}
		})
	}
}
