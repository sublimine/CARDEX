package documents

// transport_doc.go — Simplified CMR-like vehicle transport document.
//
// Note: This is an internal transport accompaniment document, NOT an official
// CMR (Convention on the Contract for the International Carriage of Goods by Road).
// Official CMR requires a homologated form. This document serves as an internal
// reference and can accompany vehicle transfers between dealers or export shipments.

import (
	"bytes"
	"fmt"
)

// GenerateTransportDoc produces a simplified transport accompaniment document.
func GenerateTransportDoc(req TransportRequest) ([]byte, error) {
	pdf := newPDF()
	docID := fmt.Sprintf("TRANSPORT-%s", req.VehicleID)

	// Title banner
	pdf.SetFillColor(60, 80, 120)
	pdf.SetTextColor(255, 255, 255)
	pdf.SetFont("Helvetica", "B", 13)
	pdf.CellFormat(contentWidth, 10, "  VEHICLE TRANSPORT DOCUMENT", "", 1, "L", true, 0, "")
	pdf.SetFont("Helvetica", "", 8)
	pdf.CellFormat(contentWidth, 5,
		"  Internal transport accompaniment — not a CMR (Convention on International Carriage of Goods by Road)",
		"", 1, "L", true, 0, "")
	pdf.SetTextColor(0, 0, 0)
	pdf.Ln(5)

	// Document reference
	drawSectionTitle(pdf, "Document Reference")
	drawTwoColumnRow(pdf, "Document ID", docID)
	drawTwoColumnRow(pdf, "Date", req.Date.Format("02 January 2006"))
	pdf.Ln(2)

	// Route
	drawSectionTitle(pdf, "Transport Route")
	drawTwoColumnRow(pdf, "Origin", req.Origin)
	drawTwoColumnRow(pdf, "Destination", req.Destination)
	drawTwoColumnRow(pdf, "Carrier", req.Carrier)
	pdf.Ln(2)

	// Vehicle
	drawSectionTitle(pdf, "Vehicle Details")
	drawTwoColumnRow(pdf, "Make / Model", req.Vehicle.Make+" "+req.Vehicle.Model)
	drawTwoColumnRow(pdf, "Year", fmt.Sprintf("%d", req.Vehicle.Year))
	drawTwoColumnRow(pdf, "VIN", req.Vehicle.VIN)
	if req.Vehicle.Registration != "" {
		drawTwoColumnRow(pdf, "Registration", req.Vehicle.Registration)
	}
	drawTwoColumnRow(pdf, "Mileage at Dispatch", fmt.Sprintf("%d km", req.Vehicle.Mileage))
	if req.Vehicle.Color != "" {
		drawTwoColumnRow(pdf, "Color", req.Vehicle.Color)
	}
	pdf.Ln(2)

	// Parties
	drawPartiesRow(pdf, "Sender / Expediteur", "Recipient / Destinataire", req.Sender, req.Recipient)

	// Notes
	if req.Notes != "" {
		drawSectionTitle(pdf, "Notes / Remarks")
		setFont(pdf, "", 8)
		pdf.MultiCell(contentWidth, 5, req.Notes, "", "L", false)
		pdf.Ln(2)
	}

	// Condition checklist
	drawSectionTitle(pdf, "Vehicle Condition at Handover")
	setFont(pdf, "", 8)
	checks := []string{
		"No visible damage / Sans dommage apparent",
		"Tires in acceptable condition / Pneumatiques en bon etat",
		"All keys handed over / Toutes les cles remises",
		"Documents included / Documents inclus",
		"Fuel level noted: ____",
	}
	for _, c := range checks {
		pdf.Cell(8, 5, "[ ]")
		pdf.Cell(contentWidth-8, 5, c)
		pdf.Ln(5)
	}

	// Signature block
	drawSignatureBlock(pdf, "Sender / Remettant", "Recipient / Destinataire")
	pdf.Ln(3)
	drawSignatureBlock(pdf, "Carrier / Transporteur", "Date of receipt / Date de reception")

	drawFooter(pdf, docID)

	var buf bytes.Buffer
	if err := pdf.Output(&buf); err != nil {
		return nil, fmt.Errorf("documents: transport doc render: %w", err)
	}
	return buf.Bytes(), nil
}
