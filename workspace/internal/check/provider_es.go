package check

// ES provider — Spain
//
// What IS publicly accessible:
//   - RAPEX EU recall database: includes ES-sourced recalls (handled by aggregator).
//   - Type-approval data via European Type Approval (WVTA) is public but per model, not per VIN.
//
// What is NOT available without owner involvement:
//   - DGT (Dirección General de Tráfico): vehicle lookup requires matrícula (plate) AND
//     the DNI/NIE of the registered owner. No public API without owner consent.
//     Professionals (dealers, insurers) may apply for DGT-SCC B2B access.
//   - ITV (Inspección Técnica de Vehículos): inspection data is managed per-community
//     (Spain's 17 autonomous communities each run their own ITV system). No centralised
//     public API exists. Empresa gestora ITV access varies by community.
//   - Historial de vehículo (DGT informe): available to vehicle owner via sede.dgt.gob.es,
//     requires Cl@ve/certificado digital — no machine-readable API for third parties.
//
// To enable ES data in production:
//  1. DGT B2B: contact dgt.es for professional access agreement (requires Spanish CIF/NIF).
//  2. Community ITV APIs: negotiate separately per community; no unified access point exists.

import "context"

// ESProvider scaffolds the Spanish registry — returns ErrProviderUnavailable.
type ESProvider struct{}

func NewESProvider() *ESProvider { return &ESProvider{} }

func (p *ESProvider) Country() string         { return "ES" }
func (p *ESProvider) SupportsVIN(_ string) bool { return false }

func (p *ESProvider) FetchHistory(_ context.Context, _ string) (*RegistryData, error) {
	return nil, ErrProviderUnavailable
}
