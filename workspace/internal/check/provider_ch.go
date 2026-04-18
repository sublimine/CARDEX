package check

// CH provider — Switzerland
//
// What IS publicly accessible:
//   - ASTRA (Bundesamt für Strassen): publishes recall campaigns at
//     https://www.astra.admin.ch — HTML pages, not a REST API.
//     RAPEX data includes Swiss-sourced safety recalls via the EU harmonised database.
//
// What is NOT available without professional access:
//   - MFK (Motorfahrzeugkontrolle): Switzerland's periodic vehicle inspection is
//     administered at the cantonal level. Each of the 26 cantons runs its own system.
//     No centralised API exists. Consumer access is via cantonal portals (e.g. mfk.zh.ch).
//   - MOFIS (Motorfahrzeug-Informationssystem): federal vehicle registration database,
//     restricted to cantonal authorities and accredited professionals.
//   - Fahrzeugausweis data: owner-consent required; no third-party access without
//     a formal delegation from the registered owner.
//
// To enable CH data in production:
//  1. Contact ASTRA for structured recall data feed (astra.admin.ch/kontakt).
//  2. Negotiate per-canton MFK data access — must repeat for all 26 cantons.
//  3. MOFIS professional access: requires CH business registration and cantonal approval.

import "context"

// CHProvider scaffolds the Swiss registry — returns ErrProviderUnavailable.
type CHProvider struct{}

func NewCHProvider() *CHProvider { return &CHProvider{} }

func (p *CHProvider) Country() string         { return "CH" }
func (p *CHProvider) SupportsVIN(_ string) bool { return false }

func (p *CHProvider) FetchHistory(_ context.Context, _ string) (*RegistryData, error) {
	return nil, ErrProviderUnavailable
}
