package documents

// invoice.go — EU-compliant invoice with VAT scheme support.
//
// VAT schemes:
//   standard      — standard VAT (show rate and amount)
//   reverse_charge — intra-EU B2B, Art. 196 VAT Directive (IVA 0%)
//   margin         — margin scheme for used goods, Art. 313 VAT Directive

import (
	"bytes"
	"fmt"
	"strings"
)

// GenerateInvoice produces an EU-compliant invoice PDF.
func GenerateInvoice(req InvoiceRequest) ([]byte, error) {
	pdf := newPDF()
	docID := req.InvoiceNumber

	// Header
	drawHeader(pdf, "INVOICE / FACTURA / RECHNUNG / FACTUUR", req.Seller.Name, req.Seller.Address)

	// Invoice metadata
	drawSectionTitle(pdf, "Invoice Details")
	drawTwoColumnRow(pdf, "Invoice No.", req.InvoiceNumber)
	drawTwoColumnRow(pdf, "Invoice Date", req.Date.Format("02 January 2006"))
	drawTwoColumnRow(pdf, "Due Date", req.DueDate.Format("02 January 2006"))
	pdf.Ln(2)

	// Seller / Buyer
	drawPartiesRow(pdf, "Seller / Vendeur / Verkaeufer", "Buyer / Acheteur / Kaeufer", req.Seller, req.Buyer)

	// Vehicle line item
	drawSectionTitle(pdf, "Description")
	setFont(pdf, "B", 8)
	pdf.SetFillColor(230, 236, 245)
	pdf.CellFormat(contentWidth*0.55, 6, " Description", "1", 0, "L", true, 0, "")
	pdf.CellFormat(contentWidth*0.15, 6, "Qty", "1", 0, "C", true, 0, "")
	pdf.CellFormat(contentWidth*0.15, 6, "Unit Price", "1", 0, "R", true, 0, "")
	pdf.CellFormat(contentWidth*0.15, 6, "Amount", "1", 1, "R", true, 0, "")
	pdf.SetFillColor(255, 255, 255)

	setFont(pdf, "", 8)
	desc := fmt.Sprintf("%s %s %d — VIN: %s — %d km",
		req.Vehicle.Make, req.Vehicle.Model, req.Vehicle.Year,
		req.Vehicle.VIN, req.Vehicle.Mileage)
	pdf.CellFormat(contentWidth*0.55, 6, " "+desc, "1", 0, "L", false, 0, "")
	pdf.CellFormat(contentWidth*0.15, 6, "1", "1", 0, "C", false, 0, "")
	pdf.CellFormat(contentWidth*0.15, 6, formatPrice(req.NetAmount, req.Currency), "1", 0, "R", false, 0, "")
	pdf.CellFormat(contentWidth*0.15, 6, formatPrice(req.NetAmount, req.Currency), "1", 1, "R", false, 0, "")

	// VAT line
	switch req.VATScheme {
	case "reverse_charge":
		pdf.CellFormat(contentWidth*0.70, 6, " VAT — Reverse charge, Art. 196 Directive 2006/112/EC", "1", 0, "L", false, 0, "")
		pdf.CellFormat(contentWidth*0.15, 6, "0%", "1", 0, "R", false, 0, "")
		pdf.CellFormat(contentWidth*0.15, 6, formatPrice(0, req.Currency), "1", 1, "R", false, 0, "")
	case "margin":
		pdf.CellFormat(contentWidth*0.70, 6, " Margin scheme — Art. 313 Directive 2006/112/EC", "1", 0, "L", false, 0, "")
		pdf.CellFormat(contentWidth*0.15, 6, "N/A", "1", 0, "R", false, 0, "")
		pdf.CellFormat(contentWidth*0.15, 6, "—", "1", 1, "R", false, 0, "")
	default:
		vatLabel := fmt.Sprintf(" VAT %.0f%%", req.VATRate)
		pdf.CellFormat(contentWidth*0.70, 6, vatLabel, "1", 0, "L", false, 0, "")
		pdf.CellFormat(contentWidth*0.15, 6, fmt.Sprintf("%.0f%%", req.VATRate), "1", 0, "R", false, 0, "")
		pdf.CellFormat(contentWidth*0.15, 6, formatPrice(req.VATAmount, req.Currency), "1", 1, "R", false, 0, "")
	}

	// Total
	pdf.Ln(1)
	setFont(pdf, "B", 9)
	pdf.SetFillColor(220, 230, 245)
	pdf.CellFormat(contentWidth*0.85, 7, " TOTAL", "1", 0, "R", true, 0, "")
	pdf.CellFormat(contentWidth*0.15, 7, formatPrice(req.TotalAmount, req.Currency), "1", 1, "R", true, 0, "")
	pdf.SetFillColor(255, 255, 255)

	// VAT scheme notice
	pdf.Ln(4)
	setFont(pdf, "I", 7.5)
	pdf.SetTextColor(80, 80, 80)
	switch req.VATScheme {
	case "reverse_charge":
		pdf.MultiCell(contentWidth, 4,
			"Reverse charge: VAT liability transferred to the buyer pursuant to Art. 196 of Council Directive 2006/112/EC.", "", "L", false)
	case "margin":
		pdf.MultiCell(contentWidth, 4,
			"Margin scheme for second-hand goods pursuant to Art. 313–325 of Council Directive 2006/112/EC. "+
				"Input VAT is not deductible by the buyer.", "", "L", false)
	default:
		pdf.MultiCell(contentWidth, 4,
			"VAT charged in accordance with applicable national legislation.", "", "L", false)
	}
	pdf.SetTextColor(0, 0, 0)

	// Payment details
	pdf.Ln(3)
	drawSectionTitle(pdf, "Payment Information")
	setFont(pdf, "", 8)
	pdf.MultiCell(contentWidth, 4.5,
		"Please transfer the total amount to the bank account indicated by the seller. "+
			"Reference: "+req.InvoiceNumber, "", "L", false)

	// Seller VAT & legal notice
	pdf.Ln(3)
	setFont(pdf, "", 7)
	pdf.SetTextColor(120, 120, 120)
	var legalLines []string
	if req.Seller.VATID != "" {
		legalLines = append(legalLines, "Seller VAT ID: "+req.Seller.VATID)
	}
	if req.Buyer.VATID != "" {
		legalLines = append(legalLines, "Buyer VAT ID: "+req.Buyer.VATID)
	}
	if len(legalLines) > 0 {
		pdf.MultiCell(contentWidth, 4, strings.Join(legalLines, " | "), "", "L", false)
	}
	pdf.SetTextColor(0, 0, 0)

	drawFooter(pdf, docID)

	var buf bytes.Buffer
	if err := pdf.Output(&buf); err != nil {
		return nil, fmt.Errorf("documents: invoice render: %w", err)
	}
	return buf.Bytes(), nil
}
