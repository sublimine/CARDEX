package handlers

import (
	"fmt"
	"net/http"
	"regexp"
	"strconv"
	"strings"
)

var vinRe = regexp.MustCompile(`^[A-HJ-NPR-Z0-9]{17}$`)

type vinEvent struct {
	EventType   string   `json:"event_type"`
	EventDate   string   `json:"event_date"`
	MileageKM   *int     `json:"mileage_km,omitempty"`
	Country     *string  `json:"country,omitempty"`
	Source      *string  `json:"source_platform,omitempty"`
	PriceEUR    *float64 `json:"price_eur,omitempty"`
	Description *string  `json:"description,omitempty"`
	Confidence  float32  `json:"confidence"`
}

type vinSummary struct {
	FirstSeen       *string   `json:"first_seen_date,omitempty"`
	LastSeen        *string   `json:"last_seen_date,omitempty"`
	OwnerCount      int       `json:"ownership_changes"`
	AccidentCount   int       `json:"accident_records"`
	ImportCount     int       `json:"import_records"`
	ListingCount    int       `json:"times_listed"`
	MinMileageKM    *int      `json:"min_mileage_km,omitempty"`
	MaxMileageKM    *int      `json:"max_mileage_km,omitempty"`
	Countries       []string  `json:"countries_seen_in"`
	PriceHistoryEUR []float64 `json:"price_history_eur"`
}

// VINHistory handles GET /api/v1/vin/{vin}
// Free vehicle history report — CarVertical killer.
func (d *Deps) VINHistory(w http.ResponseWriter, r *http.Request) {
	vin := strings.ToUpper(r.PathValue("vin"))
	if !vinRe.MatchString(vin) {
		writeError(w, http.StatusBadRequest, "invalid_vin", "VIN must be 17 alphanumeric chars (no I, O, Q)")
		return
	}

	rows, err := d.DB.Query(r.Context(), `
		SELECT event_type, event_date, mileage_km, country, source_platform,
		       price_eur, description, confidence_score
		FROM vin_history_cache
		WHERE vin = $1
		ORDER BY event_date ASC
	`, vin)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "db_error", err.Error())
		return
	}
	defer rows.Close()

	var events []vinEvent
	for rows.Next() {
		var e vinEvent
		if err := rows.Scan(
			&e.EventType, &e.EventDate, &e.MileageKM, &e.Country, &e.Source,
			&e.PriceEUR, &e.Description, &e.Confidence,
		); err != nil {
			continue
		}
		events = append(events, e)
	}
	if events == nil {
		events = []vinEvent{}
	}

	summary := buildVINSummary(events)
	mileageOK, mileageWarning := checkMileageConsistency(events)

	stolenStatus := "NOT_CHECKED"
	for _, e := range events {
		if e.EventType == "STOLEN_CHECK" && e.Description != nil {
			stolenStatus = *e.Description
		}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"vin":             vin,
		"events":          events,
		"event_count":     len(events),
		"summary":         summary,
		"mileage_ok":      mileageOK,
		"mileage_warning": mileageWarning,
		"stolen_status":   stolenStatus,
		"data_sources":    []string{"cardex_scraping", "rdw_nl"},
		"disclaimer":      "Free report from public sources. Not a substitute for a mechanical inspection.",
	})
}

func buildVINSummary(events []vinEvent) vinSummary {
	s := vinSummary{
		Countries:       []string{},
		PriceHistoryEUR: []float64{},
	}
	seen := map[string]bool{}
	for i := range events {
		e := &events[i]
		if s.FirstSeen == nil {
			d := e.EventDate
			s.FirstSeen = &d
		}
		d := e.EventDate
		s.LastSeen = &d

		switch e.EventType {
		case "OWNERSHIP":
			s.OwnerCount++
		case "ACCIDENT":
			s.AccidentCount++
		case "IMPORT":
			s.ImportCount++
		case "LISTING":
			s.ListingCount++
		case "PRICE_CHANGE":
			if e.PriceEUR != nil {
				s.PriceHistoryEUR = append(s.PriceHistoryEUR, *e.PriceEUR)
			}
		}
		if e.MileageKM != nil {
			km := *e.MileageKM
			if s.MinMileageKM == nil || km < *s.MinMileageKM {
				s.MinMileageKM = &km
			}
			if s.MaxMileageKM == nil || km > *s.MaxMileageKM {
				s.MaxMileageKM = &km
			}
		}
		if e.Country != nil && !seen[*e.Country] {
			seen[*e.Country] = true
			s.Countries = append(s.Countries, *e.Country)
		}
	}
	return s
}

func checkMileageConsistency(events []vinEvent) (bool, string) {
	type point struct {
		date string
		km   int
	}
	var pts []point
	for _, e := range events {
		if e.MileageKM != nil && *e.MileageKM > 0 {
			pts = append(pts, point{e.EventDate, *e.MileageKM})
		}
	}
	for i := 1; i < len(pts); i++ {
		prev, curr := pts[i-1], pts[i]
		if curr.date > prev.date && curr.km < prev.km {
			return false, fmt.Sprintf(
				"ROLLBACK: %s (%s km) → %s (%s km)",
				prev.date, strconv.Itoa(prev.km),
				curr.date, strconv.Itoa(curr.km),
			)
		}
	}
	return true, ""
}
