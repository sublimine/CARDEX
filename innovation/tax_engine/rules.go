package tax

import "fmt"

// IsEUCountry returns true for the 5 EU countries in the matrix.
func IsEUCountry(c string) bool { return EUCountries[c] }

// IsNewVehicle applies Art. 2(2)(b) EU VAT Directive 2006/112/CE.
// A vehicle qualifies as a "new means of transport" when EITHER condition holds:
//   - supplied ≤ 6 months after first entry into service, OR
//   - has traveled ≤ 6 000 km.
//
// A zero value for either parameter means "unknown" and is ignored.
func IsNewVehicle(ageMonths, km int) bool {
	if ageMonths > 0 && ageMonths <= 6 {
		return true
	}
	if km > 0 && km <= 6000 {
		return true
	}
	return false
}

// Routes returns all VAT routes applicable to a directional pair.
//
//   - hasValidVATIDs: both seller and buyer passed VIES validation.
//     If false, intra-community zero-rating is unavailable.
//   - isNew: vehicle is a new means of transport per Art. 2(2)(b).
//     If true, margin scheme is unavailable and intra-community requires
//     destination-country VAT.
func Routes(from, to string, hasValidVATIDs, isNew bool) []VATRoute {
	switch {
	case IsEUCountry(from) && IsEUCountry(to):
		return euToEURoutes(from, to, hasValidVATIDs, isNew)
	case IsEUCountry(from) && to == "CH":
		return euToCHRoutes(from)
	case from == "CH" && IsEUCountry(to):
		return chToEURoutes(to)
	default:
		return nil
	}
}

func euToEURoutes(from, to string, hasValidVATIDs, isNew bool) []VATRoute {
	fromRate := NationalVATRates[from]
	toRate := NationalVATRates[to]

	if isNew {
		// Art. 2(2)(b): new means of transport — mandatory destination taxation.
		// Margin scheme only covers "second-hand goods" (Art. 311(1)(1)); new
		// vehicles are excluded. Intra-community supply of a new means of transport
		// is always taxed in the destination member state (Art. 138(2)(a)).
		return []VATRoute{{
			FromCountry: from,
			ToCountry:   to,
			Regime:      RegimeIntraCommunity,
			VATRate:     toRate,
			Conditions: []string{
				"Vehículo nuevo (Art. 2(2)(b) Dir. IVA): ≤ 6 meses o ≤ 6 000 km",
				"Tributación OBLIGATORIA en país de destino — aplica también a particulares",
				fmt.Sprintf("Tipo IVA destino %s: %.0f%% sobre precio completo", to, toRate*100),
				"Régimen de margen EXCLUIDO (Art. 311 Dir. IVA: solo bienes de segunda mano)",
			},
			LegalBasis: "Art. 2(2)(b), Art. 138(2)(a), Art. 311 Directiva IVA 2006/112/CE",
		}}
	}

	routes := make([]VATRoute, 0, 2)

	if hasValidVATIDs {
		routes = append(routes, VATRoute{
			FromCountry: from,
			ToCountry:   to,
			Regime:      RegimeIntraCommunity,
			VATRate:     0.0,
			Conditions: []string{
				"Ambas partes poseen NIF-IVA válido y verificado en VIES",
				"Vendedor emite factura sin IVA indicando NIF-IVA del comprador",
				"Comprador presenta declaración de adquisición intracomunitaria (AI) en país destino",
				"Comprador realiza reverse-charge y deduce íntegramente (neto 0€ para operador)",
				"Vendedor presenta declaración recapitulativa (ES: mod. 349 / DE: ZM / FR: DES)",
			},
			LegalBasis: "Art. 20, 138, 262 Dir. IVA 2006/112/CE; § 6a UStG (DE); Art. 39 bis CGI (FR); Art. 25 LIVA (ES); Art. 39-bis VAT Code (BE); Art. 9 Wet OB (NL)",
		})
	}

	_ = fromRate
	routes = append(routes, VATRoute{
		FromCountry: from,
		ToCountry:   to,
		Regime:      RegimeMarginScheme,
		VATRate:     fromRate,
		Conditions: []string{
			"Vendedor adquirió el vehículo sin derecho a deducción de IVA (compra a particular o bajo régimen de margen)",
			"IVA calculado ÚNICAMENTE sobre el margen bruto (precio venta − precio compra)",
			"Vendedor no puede desglosar IVA en factura (factura sin IVA desglosado)",
			"Comprador NO puede deducir IVA (no hay IVA desglosado en factura)",
			"Si NIF-IVA no verificado en VIES: único régimen disponible para B2B intra-UE",
			fmt.Sprintf("Tipo IVA origen %s: %.0f%%", from, fromRate*100),
		},
		LegalBasis: "Art. 313-332 Dir. IVA 2006/112/CE; § 25a UStG (DE); Art. 297A-297F CGI (FR); Art. 135-139 LIVA (ES); Art. 58 CTVA (BE); Art. 28b-g Wet OB (NL)",
	})

	return routes
}

func euToCHRoutes(from string) []VATRoute {
	return []VATRoute{{
		FromCountry: from,
		ToCountry:   "CH",
		Regime:      RegimeExportImport,
		VATRate:     NationalVATRates["CH"],
		Conditions: []string{
			"Exportación exenta en país UE de origen (justificante aduanero EX-A / DAE / SAD)",
			"Mercancía debe salir físicamente del territorio aduanero UE",
			"IVA suizo (MWST/TVA) 8.1% liquidado en aduana CH sobre valor CIF (precio + flete + seguro)",
			"Comprador CH inscrito en MWST: IVA importación deducible como impuesto previo",
			"Despacho aduanero CH: formulario de declaración única (Import Declaration) obligatorio",
			"Impuesto sobre automóviles CH (Automobilsteuer 4%) aplica adicionalmente si vehículo < 3 años",
		},
		LegalBasis: "Art. 146(1)(a) Dir. IVA 2006/112/CE (exención exportación UE); Art. 50-57 LTVA-CH / Art. 45 ss MWSTG (importación CH); Reg. UE 952/2013 Código Aduanero de la Unión",
	}}
}

func chToEURoutes(to string) []VATRoute {
	toRate := NationalVATRates[to]
	return []VATRoute{{
		FromCountry: "CH",
		ToCountry:   to,
		Regime:      RegimeExportImport,
		VATRate:     toRate,
		Conditions: []string{
			"Exportación exenta de MWST suizo (Art. 23 MWSTG): exportador inscrito o declaración simplificada",
			"Despacho aduanero UE obligatorio: declaración DUA/SAD en frontera",
			fmt.Sprintf("IVA importación %s %.0f%% sobre base imponible (valor aduanero CIF)", to, toRate*100),
			fmt.Sprintf("Comprador UE-VAT inscrito en %s: IVA importación 100%% recuperable como input tax", to),
			"Coste neto para concesionario IVA-registrado ≈ precio CH (IVA importación neutral en flujo de caja)",
		},
		LegalBasis: "Art. 23 MWSTG / LTVA-CH (exención exportación CH); Art. 200-203 Dir. IVA 2006/112/CE (importación UE); Reg. UE 952/2013 CAU; Reg. Delegado UE 2015/2446",
	}}
}
