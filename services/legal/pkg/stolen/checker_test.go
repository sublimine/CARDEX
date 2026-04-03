package stolen

import (
	"context"
	"errors"
	"testing"
)

type mockStolenStore struct {
	isMember bool
	err      error
}

func (m *mockStolenStore) IsMember(ctx context.Context, vin string) (bool, error) {
	if m.err != nil {
		return false, m.err
	}
	return m.isMember, nil
}

func TestChecker_Check(t *testing.T) {
	tests := []struct {
		name       string
		mockMember bool
		mockErr    error
		wantFlagged bool
		wantSource  string
		wantErr    bool
	}{
		{
			name:        "clean VIN",
			mockMember:  false,
			wantFlagged: false,
		},
		{
			name:        "stolen VIN",
			mockMember:  true,
			wantFlagged: true,
			wantSource:  "EUROPOL_SIS_II",
		},
		{
			name:    "Redis error",
			mockErr: errors.New("connection refused"),
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			mock := &mockStolenStore{isMember: tt.mockMember, err: tt.mockErr}
			chk := NewWithStore(mock)
			ctx := context.Background()

			got, err := chk.Check(ctx, "WBA1234567890")
			if tt.wantErr {
				if err == nil {
					t.Errorf("Check() expected error, got nil")
				}
				return
			}
			if err != nil {
				t.Errorf("Check() unexpected error: %v", err)
				return
			}
			if got.Flagged != tt.wantFlagged {
				t.Errorf("Check() Flagged = %v, want %v", got.Flagged, tt.wantFlagged)
			}
			if tt.wantSource != "" && got.Source != tt.wantSource {
				t.Errorf("Check() Source = %q, want %q", got.Source, tt.wantSource)
			}
		})
	}
}
