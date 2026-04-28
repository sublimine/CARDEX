package check

// CH plate resolver — Switzerland
//
// Swiss plates have the format [CANTON][NUMBER] — e.g. "ZH 123456" →
// normalised "ZH123456". The canton abbreviation is 1–3 uppercase letters
// followed by 1–6 digits.
//
// Probed 2026-04-20. All 26 cantons fall into one of three categories —
// none of them provide unauthenticated, unpaid plate→vehicle lookup:
//
//  1. viacar-system.ch (SH, AG, LU, ZG) — Vue SPA. Every subdomain serves
//     the same 63 186-byte shell (md5 identical). /api/settings/recaptcha
//     returns a Google reCAPTCHA v3 site key
//     (6Lfy0OInAAAAAGR_vbqirGQla4ngTyAJbtFkvhsW) which POST
//     /api/Vehicle/List/Search requires. Server-side reCAPTCHA v3 cannot be
//     satisfied without either solving a challenge (paid CAPTCHA farm) or
//     obtaining a licensed partner key. Hard block.
//
//  2. eautoindex.ch (ZH, BE, BL, BS, GE, VD, VS, NE, JU, FR, SO, GR, TG,
//     OW, NW, AR, AI — 17 cantons) — Ionic SPA. Plate lookup is gated
//     behind a PostFinance Checkout order (CHF 5–10/query). Excluded per
//     mission's zero-paid rule.
//
//  3. Cantons with no online lookup at all (GL, SZ, UR, TI). Each canton's
//     Strassenverkehrsamt site offers contact details and paper forms only.
//
// Special-use prefixes (CD, CC, A, M, P, Z) identify diplomatic, consular,
// military, police or temporary-export plates, none of which appear in any
// public registry.
//
// See CH_ENDPOINTS.md for probe evidence and raw responses.
//
// This resolver validates the plate, extracts the canton prefix, and returns
// ErrPlateResolutionUnavailable with a per-category explanation. When a
// canton or partnership makes a real API available in the future, add it
// as a new case in Resolve().

import (
	"context"
	"fmt"
	"net/http"
)

type chPlateResolver struct{}

func newCHPlateResolver(_ *http.Client) *chPlateResolver { return &chPlateResolver{} }

// validateCHPlate ensures the plate has a plausible Swiss format:
// 1–3 canton letters followed by 1–6 digits.
func validateCHPlate(plate string) error {
	if len(plate) < 3 || len(plate) > 10 {
		return fmt.Errorf("%w: invalid CH plate length %d", ErrPlateNotFound, len(plate))
	}
	hasLetters := false
	hasDigits := false
	for _, r := range plate {
		switch {
		case r >= 'A' && r <= 'Z':
			hasLetters = true
		case r >= '0' && r <= '9':
			hasDigits = true
		default:
			return fmt.Errorf("%w: invalid character in CH plate", ErrPlateNotFound)
		}
	}
	if !hasLetters || !hasDigits {
		return fmt.Errorf("%w: CH plate must contain both letters and digits", ErrPlateNotFound)
	}
	return nil
}

func (r *chPlateResolver) Resolve(_ context.Context, plate string) (*PlateResult, error) {
	if err := validateCHPlate(plate); err != nil {
		return nil, err
	}

	canton, _ := chExtractCanton(plate)
	if canton == "" {
		return nil, fmt.Errorf("%w: cannot extract canton from CH plate %q", ErrPlateResolutionUnavailable, plate)
	}

	switch canton {
	case "SH", "AG", "LU", "ZG":
		return nil, fmt.Errorf(
			"%w: CH/%s — canton served by viacar-system.ch, which gates plate "+
				"search behind Google reCAPTCHA v3. No server-side bypass exists.",
			ErrPlateResolutionUnavailable, canton,
		)

	case "ZH", "BE", "BL", "BS", "GE", "VD", "VS", "NE", "JU", "FR",
		"SO", "GR", "TG", "OW", "NW", "AR", "AI":
		return nil, fmt.Errorf(
			"%w: CH/%s — canton served by eautoindex.ch, which charges per "+
				"lookup via PostFinance Checkout. Excluded (no paid services).",
			ErrPlateResolutionUnavailable, canton,
		)

	case "GL":
		return nil, fmt.Errorf("%w: CH/GL (Kanton Glarus) — no public online plate lookup", ErrPlateResolutionUnavailable)
	case "SZ":
		return nil, fmt.Errorf("%w: CH/SZ (Kanton Schwyz) — no public online plate lookup", ErrPlateResolutionUnavailable)
	case "UR":
		return nil, fmt.Errorf("%w: CH/UR (Kanton Uri) — no public online plate lookup", ErrPlateResolutionUnavailable)
	case "TI":
		return nil, fmt.Errorf("%w: CH/TI (Cantone Ticino) — no public online plate lookup", ErrPlateResolutionUnavailable)

	// Appenzell Innerrhoden uses "SG" in some data but "AI" is its own canton code; handled above.
	case "SG":
		return nil, fmt.Errorf(
			"%w: CH/SG (Kanton St. Gallen) — routed through eautoindex.ch (paid, excluded).",
			ErrPlateResolutionUnavailable,
		)

	case "CD", "CC":
		return nil, fmt.Errorf("%w: CH/%s is a diplomatic/consular plate — not in any public registry", ErrPlateResolutionUnavailable, canton)
	case "A", "M", "P":
		return nil, fmt.Errorf("%w: CH/%s is a military/police plate — not in any public registry", ErrPlateResolutionUnavailable, canton)
	case "Z":
		return nil, fmt.Errorf("%w: CH/Z is a temporary/export plate — not in any public registry", ErrPlateResolutionUnavailable)

	default:
		return nil, fmt.Errorf(
			"%w: unknown CH canton prefix %q (probed all 26 cantons — see CH_ENDPOINTS.md)",
			ErrPlateResolutionUnavailable, canton,
		)
	}
}

// chExtractCanton extracts the canton abbreviation (leading letters) and the
// number (trailing digits) from a normalised Swiss plate: "ZH123456" → ("ZH", "123456").
func chExtractCanton(plate string) (string, string) {
	i := 0
	for i < len(plate) && plate[i] >= 'A' && plate[i] <= 'Z' {
		i++
	}
	if i == 0 || i == len(plate) {
		return "", ""
	}
	return plate[:i], plate[i:]
}
