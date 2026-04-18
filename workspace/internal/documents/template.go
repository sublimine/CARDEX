package documents

// template.go — PDF generation engine using github.com/go-pdf/fpdf
//
// Library decision: go-pdf/fpdf (active fork of jung-kurt/gofpdf).
// Rationale:
//   - Pure Go — no CGO, no external binaries (no wkhtmltopdf, no Chromium)
//   - Built-in Latin-1 fonts (Helvetica, Times) cover DE/FR/ES/NL character sets
//   - Supports UTF-8 via AddUTF8Font; multi-page, tables, images
//   - Mature: 5k+ stars, actively maintained as of 2025
//   - Zero external system dependencies → runs in any container

import (
	"fmt"
	"strings"

	"github.com/go-pdf/fpdf"
)

const (
	marginLeft   = 15.0
	marginRight  = 15.0
	marginTop    = 20.0
	pageWidth    = 210.0 // A4
	pageHeight   = 297.0
	contentWidth = pageWidth - marginLeft - marginRight
)

// newPDF creates a configured A4 portrait PDF with standard margins.
func newPDF() *fpdf.Fpdf {
	pdf := fpdf.New("P", "mm", "A4", "")
	pdf.SetMargins(marginLeft, marginTop, marginRight)
	pdf.SetAutoPageBreak(true, 20)
	pdf.AddPage()
	return pdf
}

// setFont sets font with sensible fallback; all docs use Helvetica (Latin-1 safe).
func setFont(pdf *fpdf.Fpdf, style string, size float64) {
	pdf.SetFont("Helvetica", style, size)
}

// drawHeader renders a two-column header: title on left, dealer info on right.
func drawHeader(pdf *fpdf.Fpdf, title, dealerName, dealerAddress string) {
	setFont(pdf, "B", 16)
	pdf.SetTextColor(30, 50, 80)
	pdf.Cell(contentWidth/2, 10, title)

	setFont(pdf, "", 8)
	pdf.SetTextColor(80, 80, 80)
	pdf.SetXY(marginLeft+contentWidth/2, marginTop)
	pdf.MultiCell(contentWidth/2, 4, dealerName+"\n"+dealerAddress, "", "R", false)

	pdf.SetTextColor(0, 0, 0)
	pdf.SetY(pdf.GetY() + 4)
	drawHRule(pdf)
}

// drawHRule draws a full-width horizontal rule.
func drawHRule(pdf *fpdf.Fpdf) {
	pdf.SetDrawColor(180, 180, 180)
	pdf.SetLineWidth(0.3)
	pdf.Line(marginLeft, pdf.GetY(), marginLeft+contentWidth, pdf.GetY())
	pdf.SetDrawColor(0, 0, 0)
	pdf.SetLineWidth(0.2)
	pdf.Ln(4)
}

// drawSectionTitle renders a bold section heading with light background.
func drawSectionTitle(pdf *fpdf.Fpdf, title string) {
	pdf.Ln(3)
	pdf.SetFillColor(240, 244, 250)
	setFont(pdf, "B", 9)
	pdf.SetTextColor(30, 50, 80)
	pdf.CellFormat(contentWidth, 6, " "+title, "", 1, "L", true, 0, "")
	pdf.SetTextColor(0, 0, 0)
	pdf.Ln(1)
}

// drawTwoColumnRow renders a label-value pair in two columns.
func drawTwoColumnRow(pdf *fpdf.Fpdf, label, value string) {
	setFont(pdf, "B", 8)
	pdf.Cell(55, 5, label+":")
	setFont(pdf, "", 8)
	pdf.MultiCell(contentWidth-55, 5, value, "", "L", false)
}

// drawPartyBox renders a Party's details inside a border box.
func drawPartyBox(pdf *fpdf.Fpdf, label string, p Party) {
	setFont(pdf, "B", 8)
	pdf.Cell(contentWidth/2-3, 5, label)
	pdf.Ln(1)

	yStart := pdf.GetY()
	xStart := pdf.GetX()

	lines := []string{p.Name, p.Address, p.City, p.Country}
	if p.VATID != "" {
		lines = append(lines, "VAT: "+p.VATID)
	}
	if p.Phone != "" {
		lines = append(lines, "Tel: "+p.Phone)
	}

	setFont(pdf, "", 8)
	for _, l := range lines {
		if l == "" {
			continue
		}
		pdf.Cell(contentWidth/2-3, 4.5, l)
		pdf.Ln(4.5)
	}
	yEnd := pdf.GetY() + 2

	pdf.SetDrawColor(180, 180, 180)
	pdf.Rect(xStart-1, yStart-1, contentWidth/2-1, yEnd-yStart+2, "D")
	pdf.SetDrawColor(0, 0, 0)
	pdf.SetY(yEnd + 2)
}

// drawPartiesRow renders seller and buyer side-by-side.
func drawPartiesRow(pdf *fpdf.Fpdf, sellerLabel, buyerLabel string, seller, buyer Party) {
	yBefore := pdf.GetY()

	// Seller (left column)
	pdf.SetX(marginLeft)
	drawPartyBox(pdf, sellerLabel, seller)
	yAfterLeft := pdf.GetY()

	// Buyer (right column) — reset Y to same start
	pdf.SetXY(marginLeft+contentWidth/2+3, yBefore)
	drawPartyBox(pdf, buyerLabel, buyer)
	yAfterRight := pdf.GetY()

	// Move past whichever column was taller.
	if yAfterLeft > yAfterRight {
		pdf.SetY(yAfterLeft)
	} else {
		pdf.SetY(yAfterRight)
	}
}

// drawSignatureBlock renders two signature lines side by side.
func drawSignatureBlock(pdf *fpdf.Fpdf, leftLabel, rightLabel string) {
	pdf.Ln(10)
	setFont(pdf, "", 8)
	half := contentWidth/2 - 5

	pdf.Cell(half, 4, leftLabel)
	pdf.Cell(10, 4, "")
	pdf.Cell(half, 4, rightLabel)
	pdf.Ln(10)

	pdf.SetDrawColor(0, 0, 0)
	pdf.SetLineWidth(0.3)
	pdf.Line(marginLeft, pdf.GetY(), marginLeft+half, pdf.GetY())
	pdf.Line(marginLeft+half+10, pdf.GetY(), marginLeft+contentWidth, pdf.GetY())
	pdf.Ln(3)

	setFont(pdf, "", 7)
	pdf.SetTextColor(120, 120, 120)
	pdf.Cell(half, 4, "(Signature / Unterschrift / Signature)")
	pdf.Cell(10, 4, "")
	pdf.Cell(half, 4, "(Signature / Unterschrift / Signature)")
	pdf.SetTextColor(0, 0, 0)
	pdf.Ln(6)
}

// drawFooter renders page number + doc ID in grey at the bottom.
func drawFooter(pdf *fpdf.Fpdf, docID string) {
	pdf.SetY(pageHeight - 12)
	setFont(pdf, "", 7)
	pdf.SetTextColor(150, 150, 150)
	pdf.Cell(contentWidth/2, 4, "Doc: "+docID)
	pdf.CellFormat(contentWidth/2, 4, fmt.Sprintf("Page %d", pdf.PageNo()), "", 0, "R", false, 0, "")
	pdf.SetTextColor(0, 0, 0)
}

// formatPrice formats a price with currency symbol.
func formatPrice(amount float64, currency string) string {
	sym := currencySymbol(currency)
	return fmt.Sprintf("%s %.2f", sym, amount)
}

func currencySymbol(currency string) string {
	switch strings.ToUpper(currency) {
	case "EUR":
		return "EUR"
	case "CHF":
		return "CHF"
	case "GBP":
		return "GBP"
	default:
		return currency
	}
}
