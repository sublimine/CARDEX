package check

// BE plate resolver — Belgium
//
// No public plate→vehicle source exists in Belgium. This is not a technical
// gap; it is the combined result of three structural facts:
//
//  1. Belgian plates are PERSONAL. The plate is issued to an owner and travels
//     with them when they change car. "Look up this plate" is therefore an
//     under-specified query by construction.
//  2. DIV (Direction pour l'Immatriculation des Véhicules) publishes no
//     anonymous plate interface. Access to myminfin.be / mobilit.belgium.be
//     requires eID or itsme authentication. This complies with GDPR +
//     Belgian implementing law.
//  3. Car-Pass — the one data source that would provide mileage history by
//     chassis number — requires a 3-digit code printed on the paper Car-Pass
//     certificate handed over at purchase. There is no uncredentialled API.
//
// Probes run during investigation (2026-04-20) — all captured under
// /tmp/cardex_probes/be_* and documented in BE_ENDPOINTS.md:
//
//   - goca.be/fr/outil-de-recherche   → 302 → gocavlaanderen.be (informational
//                                            Flanders portal, no lookup form)
//   - car-pass.be/api/report/{plate}  → 404
//   - car-pass.be/ecommerce/report/*  → 404 (endpoint does not exist)
//   - mobilit.belgium.be              → eID-only auth
//   - ecoscore.be                     → manual make/model/year entry, no DB
//   - chassisnummeropzoeken.be        → redirect to NL autoverleden.nl
//   - kentekencheck.be                → parked domain
//   - aibv.be / km.be / autoveiligheid.be → informational sites only
//
// This resolver therefore validates the plate format and returns
// ErrPlateResolutionUnavailable with a detailed explanation referencing the
// specific blockers. If Belgium ever publishes an open API, or if CARDEX
// integrates a paid source (Car-Pass B2B, DIV partner API), add it here.

import (
	"context"
	"fmt"
	"net/http"
)

type bePlateResolver struct{}

func newBEPlateResolver(_ *http.Client) *bePlateResolver { return &bePlateResolver{} }

// validateBEPlate validates Belgian plate format.
// Current format (since 2010): 1 letter + 3 digits + 3 letters → normalised: "1ABC123"
// Old format (pre-2010): 3 letters + 3 digits → "ABC123"
// Personalised: various, up to 8 chars.
func validateBEPlate(plate string) error {
	if len(plate) < 4 || len(plate) > 10 {
		return fmt.Errorf("%w: invalid BE plate length %d", ErrPlateNotFound, len(plate))
	}
	for _, r := range plate {
		if !((r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9')) {
			return fmt.Errorf("%w: invalid character in BE plate", ErrPlateNotFound)
		}
	}
	return nil
}

func (b *bePlateResolver) Resolve(_ context.Context, plate string) (*PlateResult, error) {
	if err := validateBEPlate(plate); err != nil {
		return nil, err
	}

	return nil, fmt.Errorf(
		"%w: Belgium — no public plate→vehicle source. "+
			"DIV (myminfin.be) requires eID/itsme; plates are personal and travel with the owner; "+
			"Car-Pass requires the paper certificate's 3-digit code; "+
			"goca.be redirects to gocavlaanderen.be (informational, no lookup). "+
			"See BE_ENDPOINTS.md for probe evidence.",
		ErrPlateResolutionUnavailable,
	)
}
