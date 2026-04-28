package tax

import (
	"fmt"
	"sort"
)

const defaultMarginFraction = 0.20

// Calculate computes VATCalculation for every applicable route and returns
// a CalculationResponse with routes sorted by effective TotalCost ascending
// (tiebroken by VATAmount ascending — lower irrecoverable VAT ranks first).
// NetSaving is the irrecoverable VAT saved vs the worst route.
func Calculate(req CalculationRequest, viesStatus map[string]bool) CalculationResponse {
	isNew := IsNewVehicle(req.VehicleAgeMonths, req.VehicleKM)

	sellerValid := req.SellerVATID != "" && viesStatus[req.SellerVATID]
	buyerValid := req.BuyerVATID != "" && viesStatus[req.BuyerVATID]
	hasValidVATIDs := sellerValid && buyerValid

	routes := Routes(req.FromCountry, req.ToCountry, hasValidVATIDs, isNew)
	calcs := make([]VATCalculation, 0, len(routes))
	for _, r := range routes {
		calcs = append(calcs, computeRoute(r, req))
	}

	sort.SliceStable(calcs, func(i, j int) bool {
		if calcs[i].TotalCost != calcs[j].TotalCost {
			return calcs[i].TotalCost < calcs[j].TotalCost
		}
		return calcs[i].VATAmount < calcs[j].VATAmount
	})

	// NetSaving = irrecoverable VAT saved vs worst route.
	// For EU→EU: IC VATAmount=0 vs MS VATAmount=embedded → saving = embedded VAT.
	// For single-route cases (CH, new vehicle): saving = 0.
	if len(calcs) > 0 {
		worstVAT := calcs[len(calcs)-1].VATAmount
		for i := range calcs {
			calcs[i].NetSaving = worstVAT - calcs[i].VATAmount
		}
		calcs[0].IsOptimal = true
	}

	resp := CalculationResponse{
		FromCountry:  req.FromCountry,
		ToCountry:    req.ToCountry,
		VehiclePrice: req.VehiclePriceCents,
		IsNewVehicle: isNew,
		VIESStatus:   viesStatus,
		Routes:       calcs,
	}
	if len(calcs) > 0 {
		optimal := calcs[0]
		resp.OptimalRoute = &optimal
	}
	return resp
}

func computeRoute(r VATRoute, req CalculationRequest) VATCalculation {
	price := req.VehiclePriceCents
	margin := req.MarginCents
	if margin <= 0 {
		margin = int64(float64(price) * defaultMarginFraction)
	}

	var taxableBase, vatAmount, totalCost int64
	var explanation string

	switch r.Regime {
	case RegimeMarginScheme:
		taxableBase = margin
		vatAmount = int64(float64(margin) * r.VATRate / (1 + r.VATRate))
		totalCost = price
		explanation = fmt.Sprintf(
			"Régimen de margen (Art. 313 Dir. IVA): IVA %.0f%% sobre margen €%.2f. "+
				"IVA incorporado €%.2f no deducible por el comprador. "+
				"Precio total facturado: €%.2f",
			r.VATRate*100, euroF(margin),
			euroF(vatAmount), euroF(price),
		)

	case RegimeIntraCommunity:
		if r.VATRate == 0 {
			taxableBase = price
			vatAmount = 0
			totalCost = price
			explanation = fmt.Sprintf(
				"Adquisición intracomunitaria 0%% (Art. 20 Dir. IVA): factura sin IVA. "+
					"Comprador aplica reverse-charge %.0f%% en %s y deduce íntegramente. "+
					"Coste IVA neto: €0,00. Precio neto: €%.2f",
				NationalVATRates[r.ToCountry]*100, r.ToCountry, euroF(price),
			)
		} else {
			// New means of transport (Art. 2(2)(b)): destination VAT mandatory.
			taxableBase = price
			vatAmount = int64(float64(price) * r.VATRate)
			totalCost = price + vatAmount
			explanation = fmt.Sprintf(
				"Vehículo nuevo Art. 2(2)(b): IVA %.0f%% OBLIGATORIO en destino %s. "+
					"IVA sobre precio íntegro €%.2f = €%.2f. Total bruto: €%.2f. "+
					"Sujeto pasivo en %s: IVA recuperable como input tax.",
				r.VATRate*100, r.ToCountry,
				euroF(price), euroF(vatAmount),
				euroF(totalCost), r.ToCountry,
			)
		}

	case RegimeExportImport:
		taxableBase = price
		vatAmount = int64(float64(price) * r.VATRate)
		totalCost = price + vatAmount

		if r.ToCountry == "CH" {
			explanation = fmt.Sprintf(
				"Exportación UE→CH (Art. 146 Dir. IVA): 0%% IVA en origen %s. "+
					"Importación suiza MWST %.1f%% sobre valor CIF €%.2f = €%.2f. "+
					"Total bruto: €%.2f. "+
					"Comprador CH inscrito MWST: IVA importación recuperable.",
				r.FromCountry,
				r.VATRate*100, euroF(price),
				euroF(vatAmount), euroF(totalCost),
			)
		} else {
			explanation = fmt.Sprintf(
				"Exportación CH→UE (Art. 23 MWSTG): 0%% MWST en origen. "+
					"IVA importación %s %.0f%% sobre valor declarado €%.2f = €%.2f. "+
					"Total bruto: €%.2f. "+
					"Comprador EU-VAT inscrito en %s: IVA importación recuperable como input tax.",
				r.ToCountry,
				r.VATRate*100, euroF(price),
				euroF(vatAmount), euroF(totalCost), r.ToCountry,
			)
		}
	}

	return VATCalculation{
		Route:        r,
		VehiclePrice: price,
		MarginAmount: margin,
		TaxableBase:  taxableBase,
		VATAmount:    vatAmount,
		TotalCost:    totalCost,
		Explanation:  explanation,
	}
}

func euroF(cents int64) float64 { return float64(cents) / 100 }
