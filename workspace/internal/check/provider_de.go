package check

// DE provider — Germany
//
// What IS publicly accessible:
//   - KBA Rückrufdatenbank (kba.de/rueckrufe): published recall data.
//     Available as an HTML page and periodic Excel downloads; no JSON/REST API.
//     RAPEX EU database (handled by aggregator) is a more machine-friendly source
//     and includes KBA-reported recalls.
//
// What is NOT available without professional access:
//   - KBA vehicle registration data (ZFZR): restricted to government authorities.
//   - TÜV/DEKRA inspection history: each organisation holds its own data;
//     no central API. Consumer lookup via tuev-nord.de, tuev-sued.de etc. requires
//     explicit consent flow (HU-report PDF download, not a queryable API).
//   - CARFAX Deutschland / AutoScout24 HU check: commercial services, API requires contract.
//
// To enable DE inspection data in production:
//  1. Negotiate direct data feed with TÜV Nord, TÜV Süd, DEKRA, GTÜ separately.
//  2. Or integrate with a commercial aggregator (Cartell, AutoDNA, CARFAX EU) via their API.
//  3. KBA recalls: if a structured feed becomes available, implement fetchKBARecalls() below.

import "context"

// DEProvider scaffolds the German registry — returns ErrProviderUnavailable.
// See package-level comment for what data would be available and how to enable it.
type DEProvider struct{}

func NewDEProvider() *DEProvider { return &DEProvider{} }

func (p *DEProvider) Country() string         { return "DE" }
func (p *DEProvider) SupportsVIN(_ string) bool { return false }

func (p *DEProvider) FetchHistory(_ context.Context, _ string) (*RegistryData, error) {
	return nil, ErrProviderUnavailable
}
