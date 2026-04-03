package h3

import (
	"strings"
	"testing"
)

func TestIndexer_Compute(t *testing.T) {
	idx := &Indexer{}

	tests := []struct {
		name       string
		lat        float64
		lng        float64
		wantErr    bool
		errSub     string
		checkRes4  func(string) bool
		checkRes7  func(string) bool
	}{
		{
			name:    "Berlin",
			lat:     52.52,
			lng:     13.405,
			wantErr: false,
			checkRes4: func(s string) bool {
				return len(s) > 0 && strings.HasPrefix(s, "8")
			},
			checkRes7: func(s string) bool {
				return len(s) > 0 && strings.HasPrefix(s, "8")
			},
		},
		{
			name:    "null island rejected",
			lat:     0,
			lng:     0,
			wantErr: true,
			errSub:  "null island",
		},
		{
			name:    "negative coordinates valid",
			lat:     -33.87,
			lng:     151.21,
			wantErr: false,
			checkRes4: func(s string) bool {
				return len(s) > 0
			},
			checkRes7: func(s string) bool {
				return len(s) > 0
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			res4, res7, err := idx.Compute(tt.lat, tt.lng)
			if tt.wantErr {
				if err == nil {
					t.Errorf("Compute() expected error, got nil")
					return
				}
				if tt.errSub != "" && !strings.Contains(err.Error(), tt.errSub) {
					t.Errorf("Compute() error = %v, want substring %q", err, tt.errSub)
				}
				return
			}
			if err != nil {
				t.Errorf("Compute() unexpected error: %v", err)
				return
			}
			if tt.checkRes4 != nil && !tt.checkRes4(res4) {
				t.Errorf("Compute() res4 = %q, check failed", res4)
			}
			if tt.checkRes7 != nil && !tt.checkRes7(res7) {
				t.Errorf("Compute() res7 = %q, check failed", res7)
			}
		})
	}
}
