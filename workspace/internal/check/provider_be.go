package check

// BE provider — Belgium
//
// What IS publicly accessible:
//   - RAPEX EU recall database (ec.europa.eu/safety-gate): includes BE-sourced recalls,
//     accessible via the RAPEX API (implemented in the aggregator for all countries).
//
// What is NOT available without owner involvement:
//   - Car-Pass (car-pass.be): Belgian mileage certification system.
//     Verification requires the 9-character numéro de châssis (chassis number, last 9 of VIN)
//     AND a paid per-query fee (€2/report for individuals, B2B API available for dealers).
//     API docs: https://api.car-pass.be (requires registration and approved B2B contract).
//   - DIV (Direction pour l'Immatriculation des Véhicules): registration data restricted
//     to official authorities and accredited professionals.
//   - Technical inspection (GOCA): no public individual lookup API.
//
// To enable BE data in production:
//  1. Car-Pass B2B API: contact car-pass.be, sign B2B agreement, receive API token.
//     Then implement: POST https://api.car-pass.be/check with {vin, token} → mileage records.
//  2. DIV access: requires formal request through Belgian government.

import "context"

// BEProvider scaffolds the Belgian registry — returns ErrProviderUnavailable.
type BEProvider struct{}

func NewBEProvider() *BEProvider { return &BEProvider{} }

func (p *BEProvider) Country() string         { return "BE" }
func (p *BEProvider) SupportsVIN(_ string) bool { return false }

func (p *BEProvider) FetchHistory(_ context.Context, _ string) (*RegistryData, error) {
	return nil, ErrProviderUnavailable
}
