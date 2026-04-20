package check

import (
	"context"
	"strings"

	"cardex.eu/workspace/internal/check/matraba"
)

// matrabaLookup defines the subset of *matraba.Store methods the ES
// resolver consumes. Narrow interface so tests can stub the store with
// a tiny fake instead of wiring a SQLite DB.
type matrabaLookup interface {
	LookupByVIN(ctx context.Context, vin string) (matraba.Record, bool, error)
	LookupByPrefix(ctx context.Context, prefix string, limit int) ([]matraba.Record, error)
}

// WithMATRABA attaches a DGT MATRABA store to the ES resolver. When set,
// the resolver enriches PlateResult after a VIN is known — filling in
// technical fields that CM does not expose (weights, municipality,
// homologation, Euro norm, CO₂, wheelbase, EU category).
//
// The integration is strictly additive: fields already populated by CM
// are preserved, MATRABA fills only the gaps. If the VIN is partially
// masked (post-2025-02 dumps) we fall back to the first 11-char prefix —
// same make/model/variant records back to the same family, so the merge
// is safe even when multiple vehicles share the prefix.
func (r *esPlateResolver) WithMATRABA(store matrabaLookup) *esPlateResolver {
	r.matraba = store
	return r
}

// applyMATRABAToResult merges MATRABA fields into result. Called after
// CM has had first crack at populating the result, so any field CM filled
// is left as-is.
func applyMATRABAToResult(rec matraba.Record, result *PlateResult) {
	if result.VIN == "" && rec.Bastidor != "" {
		result.VIN = rec.Bastidor
	}
	if result.Make == "" && rec.MarcaITV != "" {
		result.Make = rec.MarcaITV
	}
	if result.Model == "" && rec.ModeloITV != "" {
		result.Model = rec.ModeloITV
	}
	if result.Variant == "" && rec.VersionITV != "" {
		result.Variant = rec.VersionITV
	}
	if result.FuelType == "" {
		if label := rec.FuelTypeLabel(); label != "" {
			result.FuelType = label
		}
	}
	if result.DisplacementCC == 0 && rec.CilindradaCC > 0 {
		result.DisplacementCC = rec.CilindradaCC
	}
	if result.PowerKW == 0 && rec.PotenciaKW > 0 {
		result.PowerKW = rec.PotenciaKW
	}
	if result.EmptyWeightKg == 0 {
		// Prefer "masa en orden de marcha" (fully-fuelled running weight,
		// mandatory since WVTA 2007/46). Fall back to the legacy "tara"
		// column for pre-2015 vehicles where MasaOrdenMarchaKg is blank.
		switch {
		case rec.MasaOrdenMarchaKg > 0:
			result.EmptyWeightKg = rec.MasaOrdenMarchaKg
		case rec.TaraKg > 0:
			result.EmptyWeightKg = rec.TaraKg
		}
	}
	if result.GrossWeightKg == 0 {
		switch {
		case rec.MasaMaxTecnicaKg > 0:
			result.GrossWeightKg = rec.MasaMaxTecnicaKg
		case rec.PesoMaxKg > 0:
			result.GrossWeightKg = rec.PesoMaxKg
		}
	}
	if result.NumberOfSeats == 0 && rec.NumPlazas > 0 {
		result.NumberOfSeats = rec.NumPlazas
	}
	if result.EuroNorm == "" && rec.NivelEmisionesEURO != "" {
		result.EuroNorm = rec.NivelEmisionesEURO
	}
	if result.CO2GPerKm == 0 && rec.CO2GPerKm > 0 {
		result.CO2GPerKm = float64(rec.CO2GPerKm)
	}
	if result.EuropeanVehicleCategory == "" && rec.CatHomologacionUE != "" {
		result.EuropeanVehicleCategory = rec.CatHomologacionUE
	}
	if result.VehicleType == "" {
		if label := rec.VehicleTypeLabel(); label != "" {
			result.VehicleType = label
		}
	}
	if result.TypeApprovalNumber == "" && rec.ContrasenaHomolog != "" {
		result.TypeApprovalNumber = rec.ContrasenaHomolog
	}
	if result.WheelbaseCm == 0 && rec.DistanciaEjes12Mm > 0 {
		// MATRABA records wheelbase in millimetres; PlateResult uses cm.
		result.WheelbaseCm = rec.DistanciaEjes12Mm / 10
	}
	if result.District == "" {
		// Prefer the "province of vehicle domicile" (current owner) over
		// the "province of first registration" — the former tracks the
		// vehicle where it lives today.
		if p := matraba.ProvinceLabel(rec.CodProvinciaVeh); p != "" {
			result.District = p
		} else if p := matraba.ProvinceLabel(rec.CodProvinciaMat); p != "" {
			result.District = p
		}
	}
	if result.PreviousOwners == 0 && rec.NumTitulares > 0 {
		result.PreviousOwners = rec.NumTitulares
	}
	if result.FirstRegistration == nil && !rec.FecPrimMatriculacion.IsZero() {
		t := rec.FecPrimMatriculacion
		result.FirstRegistration = &t
	}
}

// enrichWithMATRABA queries the store for the given VIN and, on a hit,
// merges record fields into result. Masked VINs (post-2025-02) fall back
// to prefix-matching — we take the single most recently matriculated
// record whose VIN prefix matches and the make/model agrees, since a WMI
// + VDS3 can still span multiple variants.
//
// enrichWithMATRABA is a no-op when no store is attached or the VIN is
// empty. Errors from the store are non-fatal: we log via the caller and
// continue with the un-enriched result.
func (r *esPlateResolver) enrichWithMATRABA(ctx context.Context, result *PlateResult) error {
	if r.matraba == nil || result.VIN == "" {
		return nil
	}
	vin := strings.ToUpper(result.VIN)

	// 1) exact VIN hit (pre-2025 data + unmasked post-2025 cases).
	if rec, ok, err := r.matraba.LookupByVIN(ctx, vin); err != nil {
		return err
	} else if ok {
		applyMATRABAToResult(rec, result)
		return nil
	}

	// 2) prefix fallback — only meaningful if CM already gave us make/
	// model; otherwise we can't disambiguate multiple prefix hits.
	if len(vin) < 11 {
		return nil
	}
	recs, err := r.matraba.LookupByPrefix(ctx, vin[:11], 20)
	if err != nil {
		return err
	}
	for _, rec := range recs {
		if result.Make != "" && !strings.EqualFold(result.Make, rec.MarcaITV) {
			continue
		}
		applyMATRABAToResult(rec, result)
		return nil
	}
	return nil
}
