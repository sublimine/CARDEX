package documents

// contract.go — Purchase/sale contracts for DE, FR, ES, NL.
//
// Country-specific templates:
//   DE — Kaufvertrag für Gebrauchtwagen (ADAC-style)
//   FR — Bon de Commande véhicule d'occasion
//   ES — Contrato de compraventa de vehículo usado
//   NL — Koopovereenkomst gebruikte auto

import (
	"bytes"
	"fmt"
)

type contractLocale struct {
	title          string
	sellerLabel    string
	buyerLabel     string
	vehicleSection string
	priceSection   string
	clausesSection string
	signatureLeft  string
	signatureRight string
	clauses        []string
	currency       string
	dateLabel      string
	placeLabel     string
}

var contractLocales = map[string]contractLocale{
	"DE": {
		title:          "Kaufvertrag fuer Gebrauchtwagen",
		sellerLabel:    "Verkaeufer (Haendler)",
		buyerLabel:     "Kaeufer",
		vehicleSection: "Fahrzeugdaten",
		priceSection:   "Kaufpreis",
		clausesSection: "Vertragsklauseln",
		signatureLeft:  "Verkaeufer",
		signatureRight: "Kaeufer",
		dateLabel:      "Datum",
		placeLabel:     "Ort",
		clauses: []string{
			"Das Fahrzeug wird verkauft wie besichtigt und im gegenwärtigen Zustand, soweit nicht ausdrücklich anders vereinbart.",
			"Für gebrauchte Kraftfahrzeuge, die von Unternehmern an Verbraucher verkauft werden, gilt eine gesetzliche Gewährleistungspflicht von 12 Monaten ab Übergabe (§ 476 BGB).",
			"Der Eigentumsübergang erfolgt erst nach vollständiger Bezahlung des Kaufpreises.",
			"Das Fahrzeug wird bei Übergabe mit den vereinbarten Schlüsseln, Zulassungsbescheinigungen und Serviceheften übergeben.",
			"Mündliche Nebenabreden bestehen nicht. Änderungen bedürfen der Schriftform.",
		},
	},
	"FR": {
		title:          "Bon de Commande - Vehicule d'Occasion",
		sellerLabel:    "Vendeur (Professionnel)",
		buyerLabel:     "Acheteur",
		vehicleSection: "Description du Vehicule",
		priceSection:   "Prix de Vente",
		clausesSection: "Conditions Generales",
		signatureLeft:  "Le Vendeur",
		signatureRight: "L'Acheteur",
		dateLabel:      "Date",
		placeLabel:     "Lieu",
		clauses: []string{
			"Le vehicule est vendu en l'etat, tel que vu et accepte par l'acheteur lors de sa visite.",
			"Conformement aux articles L. 217-1 et suivants du Code de la consommation, le vendeur est tenu a une garantie legale de conformite de 12 mois.",
			"Le transfert de propriete n'intervient qu'apres paiement integral du prix.",
			"Le vehicule est livre avec l'ensemble des documents de bord, cles et equipements convenus.",
			"Toute modification du present contrat doit faire l'objet d'un avenant ecrit signe par les deux parties.",
		},
	},
	"ES": {
		title:          "Contrato de Compraventa de Vehiculo Usado",
		sellerLabel:    "Vendedor (Empresa)",
		buyerLabel:     "Comprador",
		vehicleSection: "Datos del Vehiculo",
		priceSection:   "Precio de Venta",
		clausesSection: "Clausulas Contractuales",
		signatureLeft:  "El Vendedor",
		signatureRight: "El Comprador",
		dateLabel:      "Fecha",
		placeLabel:     "Lugar",
		clauses: []string{
			"El vehiculo se vende en el estado en que se encuentra, tal y como ha sido visto por el comprador.",
			"De conformidad con el Real Decreto Legislativo 1/2007 y el articulo 136 de la Ley de Garantias, el vendedor ofrece una garantia legal minima de 12 meses.",
			"La transmision de la propiedad se producira una vez abonado el precio total.",
			"El vehiculo se entregara con la documentacion, llaves y accesorios acordados.",
			"Cualquier modificacion de este contrato debera realizarse por escrito y estar firmada por ambas partes.",
		},
	},
	"NL": {
		title:          "Koopovereenkomst Gebruikte Auto",
		sellerLabel:    "Verkoper (Handelaar)",
		buyerLabel:     "Koper",
		vehicleSection: "Voertuiggegevens",
		priceSection:   "Koopprijs",
		clausesSection: "Algemene Voorwaarden",
		signatureLeft:  "Verkoper",
		signatureRight: "Koper",
		dateLabel:      "Datum",
		placeLabel:     "Plaats",
		clauses: []string{
			"Het voertuig wordt verkocht in de staat zoals gezien en geaccepteerd door de koper.",
			"Conform het Burgerlijk Wetboek (art. 7:23 BW) geldt een wettelijke garantie van 12 maanden voor consumentenkoop.",
			"Eigendomsoverdracht vindt pas plaats na volledige betaling van de koopprijs.",
			"Het voertuig wordt afgeleverd met alle overeengekomen sleutels, kentekenbewijzen en serviceboekjes.",
			"Wijzigingen in deze overeenkomst zijn slechts geldig indien schriftelijk overeengekomen.",
		},
	},
}

// GenerateContract produces a PDF purchase/sale contract for the given country.
// The PDF bytes are returned; callers are responsible for persisting to disk.
func GenerateContract(req ContractRequest) ([]byte, error) {
	locale, ok := contractLocales[req.Country]
	if !ok {
		return nil, fmt.Errorf("documents: unsupported contract country %q (supported: DE FR ES NL)", req.Country)
	}

	pdf := newPDF()
	docID := "CONTRACT-" + req.VehicleID + "-" + req.Country

	// Header
	drawHeader(pdf, locale.title, req.Seller.Name, req.Seller.Address)

	// Parties
	drawPartiesRow(pdf, locale.sellerLabel, locale.buyerLabel, req.Seller, req.Buyer)

	// Vehicle section
	drawSectionTitle(pdf, locale.vehicleSection)
	drawTwoColumnRow(pdf, "Make / Model", req.Vehicle.Make+" "+req.Vehicle.Model)
	drawTwoColumnRow(pdf, "Year", fmt.Sprintf("%d", req.Vehicle.Year))
	drawTwoColumnRow(pdf, "VIN", req.Vehicle.VIN)
	if req.Vehicle.Registration != "" {
		drawTwoColumnRow(pdf, "Registration", req.Vehicle.Registration)
	}
	drawTwoColumnRow(pdf, "Mileage", fmt.Sprintf("%d km", req.Vehicle.Mileage))
	drawTwoColumnRow(pdf, "Fuel", req.Vehicle.Fuel)
	if req.Vehicle.Color != "" {
		drawTwoColumnRow(pdf, "Color", req.Vehicle.Color)
	}
	if req.Vehicle.Power > 0 {
		drawTwoColumnRow(pdf, "Power", fmt.Sprintf("%d kW", req.Vehicle.Power))
	}

	// Price section
	drawSectionTitle(pdf, locale.priceSection)
	drawTwoColumnRow(pdf, "Net Amount", formatPrice(req.Price/(1+req.VATRate/100), req.Currency))

	switch req.VATScheme {
	case "reverse_charge":
		drawTwoColumnRow(pdf, "VAT", "0% — Reverse charge, Art. 196 VAT Directive")
	case "margin":
		drawTwoColumnRow(pdf, "VAT", "Margin scheme — Art. 313 VAT Directive")
	default:
		if req.VATRate > 0 {
			vatAmount := req.Price * req.VATRate / (100 + req.VATRate)
			drawTwoColumnRow(pdf, fmt.Sprintf("VAT %.0f%%", req.VATRate), formatPrice(vatAmount, req.Currency))
		}
	}
	drawTwoColumnRow(pdf, "Total Price", formatPrice(req.Price, req.Currency))

	// Date / Place
	drawSectionTitle(pdf, "")
	drawTwoColumnRow(pdf, locale.placeLabel, req.Place)
	drawTwoColumnRow(pdf, locale.dateLabel, req.Date.Format("02.01.2006"))

	// Clauses
	drawSectionTitle(pdf, locale.clausesSection)
	setFont(pdf, "", 7.5)
	for i, clause := range locale.clauses {
		pdf.MultiCell(contentWidth, 4.5, fmt.Sprintf("%d. %s", i+1, clause), "", "L", false)
		pdf.Ln(1)
	}

	// Signatures
	drawSignatureBlock(pdf, locale.signatureLeft, locale.signatureRight)
	drawFooter(pdf, docID)

	var buf bytes.Buffer
	if err := pdf.Output(&buf); err != nil {
		return nil, fmt.Errorf("documents: contract render: %w", err)
	}
	return buf.Bytes(), nil
}
