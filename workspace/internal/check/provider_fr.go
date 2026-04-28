package check

// FR provider — France
//
// What IS publicly accessible:
//   - data.gouv.fr open datasets: some vehicle statistics, but NOT individual vehicle history
//
// What is NOT available without professional access or owner consent:
//   - Histovec (histovec.interieur.gouv.fr): interactive portal that requires license plate
//     AND the vehicle's identification details (SIV registration certificate data).
//     No public API exists. Dealers and professionals may apply for ANTS/SIV access.
//   - SIV (Système d'Immatriculation des Véhicules): restricted to accredited professionals.
//   - Contrôle Technique (CT) history: managed by UTAC-OTC, no public individual lookup API.
//     Professionals may access via utac.com with subscription.
//
// To enable FR data in production:
//  1. ANTS professional API: apply at api.gouv.fr for SIV access (requires SIRET + justification)
//  2. UTAC CT data: commercial subscription at utac.com
//  3. If/when Histovec publishes a public API, implement FetchHistovec() here.

import "context"

// FRProvider scaffolds the French registry — returns ErrProviderUnavailable.
// No public API exists for individual vehicle history in France as of 2025.
type FRProvider struct{}

func NewFRProvider() *FRProvider { return &FRProvider{} }

func (p *FRProvider) Country() string      { return "FR" }
func (p *FRProvider) SupportsVIN(_ string) bool { return false }

func (p *FRProvider) FetchHistory(_ context.Context, _ string) (*RegistryData, error) {
	return nil, ErrProviderUnavailable
}
