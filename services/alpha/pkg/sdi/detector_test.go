package sdi

import "testing"

func TestDetector_Check(t *testing.T) {
	det := &Detector{}

	tests := []struct {
		name         string
		daysOnMarket int
		wantAlert    bool
		wantZone     string
	}{
		{
			name:         "day 58 triggers 60d cliff",
			daysOnMarket: 58,
			wantAlert:    true,
			wantZone:     "FLOORPLAN_60D_CLIFF",
		},
		{
			name:         "day 65 triggers 60d cliff",
			daysOnMarket: 65,
			wantAlert:    true,
			wantZone:     "FLOORPLAN_60D_CLIFF",
		},
		{
			name:         "day 57 no alert",
			daysOnMarket: 57,
			wantAlert:    false,
			wantZone:     "",
		},
		{
			name:         "day 66 no alert",
			daysOnMarket: 66,
			wantAlert:    false,
			wantZone:     "",
		},
		{
			name:         "day 88 triggers 90d cliff",
			daysOnMarket: 88,
			wantAlert:    true,
			wantZone:     "FLOORPLAN_90D_CLIFF",
		},
		{
			name:         "day 95 triggers 90d cliff",
			daysOnMarket: 95,
			wantAlert:    true,
			wantZone:     "FLOORPLAN_90D_CLIFF",
		},
		{
			name:         "day 96 no alert",
			daysOnMarket: 96,
			wantAlert:    false,
			wantZone:     "",
		},
		{
			name:         "day 0 no alert",
			daysOnMarket: 0,
			wantAlert:    false,
			wantZone:     "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			alert, zone := det.Check(tt.daysOnMarket)
			if alert != tt.wantAlert {
				t.Errorf("Check(%d) alert = %v, want %v", tt.daysOnMarket, alert, tt.wantAlert)
			}
			if zone != tt.wantZone {
				t.Errorf("Check(%d) zone = %q, want %q", tt.daysOnMarket, zone, tt.wantZone)
			}
		})
	}
}
