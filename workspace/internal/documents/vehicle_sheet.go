package documents

// vehicle_sheet.go — 1-page vehicle technical sheet.
// Layout: title + dealer block at top, vehicle data two-column table,
// features list, price box, QR placeholder at bottom-right.

import (
	"bytes"
	"fmt"
	"strings"
)

// GenerateVehicleSheet produces a 1-page A4 PDF vehicle technical sheet.
func GenerateVehicleSheet(req VehicleSheetRequest) ([]byte, error) {
	pdf := newPDF()

	// Coloured title banner
	pdf.SetFillColor(30, 50, 80)
	pdf.SetTextColor(255, 255, 255)
	pdf.SetFont("Helvetica", "B", 14)
	pdf.CellFormat(contentWidth, 12, "  "+req.Vehicle.Make+" "+req.Vehicle.Model+" ("+fmt.Sprintf("%d", req.Vehicle.Year)+")",
		"", 1, "L", true, 0, "")

	// Dealer sub-banner
	pdf.SetFillColor(60, 80, 120)
	pdf.SetFont("Helvetica", "", 8)
	dealerLine := req.DealerName
	if req.DealerPhone != "" {
		dealerLine += "  |  " + req.DealerPhone
	}
	if req.DealerEmail != "" {
		dealerLine += "  |  " + req.DealerEmail
	}
	pdf.CellFormat(contentWidth, 6, "  "+dealerLine, "", 1, "L", true, 0, "")

	pdf.SetTextColor(0, 0, 0)
	pdf.Ln(4)

	// Two-column tech data table
	pdf.SetFont("Helvetica", "B", 9)
	pdf.SetFillColor(240, 244, 250)
	pdf.CellFormat(contentWidth, 6, " Technical Specifications", "", 1, "L", true, 0, "")
	pdf.Ln(1)

	type specRow struct{ label, value string }
	specs := []specRow{
		{"Make", req.Vehicle.Make},
		{"Model", req.Vehicle.Model},
		{"Year", fmt.Sprintf("%d", req.Vehicle.Year)},
		{"Mileage", fmt.Sprintf("%d km", req.Vehicle.Mileage)},
		{"Fuel Type", req.Vehicle.Fuel},
		{"VIN", req.Vehicle.VIN},
	}
	if req.Vehicle.Color != "" {
		specs = append(specs, specRow{"Color", req.Vehicle.Color})
	}
	if req.Vehicle.Power > 0 {
		specs = append(specs, specRow{"Power", fmt.Sprintf("%d kW / %d hp", req.Vehicle.Power, int(float64(req.Vehicle.Power)*1.341))})
	}
	if req.Vehicle.BodyType != "" {
		specs = append(specs, specRow{"Body Type", req.Vehicle.BodyType})
	}
	if req.Vehicle.Registration != "" {
		specs = append(specs, specRow{"Registration", req.Vehicle.Registration})
	}

	colW := contentWidth / 2
	for i := 0; i < len(specs); i += 2 {
		pdf.SetFont("Helvetica", "B", 8)
		pdf.Cell(colW*0.38, 5.5, specs[i].label+":")
		pdf.SetFont("Helvetica", "", 8)
		pdf.Cell(colW*0.62, 5.5, specs[i].value)

		if i+1 < len(specs) {
			pdf.SetFont("Helvetica", "B", 8)
			pdf.Cell(colW*0.38, 5.5, specs[i+1].label+":")
			pdf.SetFont("Helvetica", "", 8)
			pdf.Cell(colW*0.62, 5.5, specs[i+1].value)
		}
		pdf.Ln(5.5)
	}

	// Features
	if len(req.Vehicle.Features) > 0 {
		pdf.Ln(3)
		pdf.SetFont("Helvetica", "B", 9)
		pdf.SetFillColor(240, 244, 250)
		pdf.CellFormat(contentWidth, 6, " Equipment & Features", "", 1, "L", true, 0, "")
		pdf.Ln(1)

		pdf.SetFont("Helvetica", "", 8)
		featureCols := 3
		colW2 := contentWidth / float64(featureCols)
		for i, f := range req.Vehicle.Features {
			pdf.Cell(colW2, 5, "- "+f)
			if (i+1)%featureCols == 0 {
				pdf.Ln(5)
			}
		}
		if len(req.Vehicle.Features)%featureCols != 0 {
			pdf.Ln(5)
		}
	}

	// Price box
	pdf.Ln(4)
	pdf.SetFillColor(30, 50, 80)
	pdf.SetTextColor(255, 255, 255)
	pdf.SetFont("Helvetica", "B", 16)
	priceStr := formatPrice(req.Price, req.Currency)
	pdf.CellFormat(contentWidth*0.6, 14, "  Price: "+priceStr+" (incl. VAT)", "", 0, "L", true, 0, "")

	// QR placeholder box
	pdf.SetFillColor(240, 244, 250)
	pdf.SetTextColor(80, 80, 80)
	pdf.SetFont("Helvetica", "", 7)
	qrText := "QR"
	if req.Vehicle.ListingURL != "" {
		// Truncate for display
		url := req.Vehicle.ListingURL
		if len(url) > 30 {
			url = url[:27] + "..."
		}
		qrText = "Scan for online listing\n" + url
	}
	pdf.MultiCell(contentWidth*0.4, 7, qrText, "1", "C", true)

	pdf.SetTextColor(0, 0, 0)

	// Footer note
	pdf.SetY(pageHeight - 20)
	pdf.SetFont("Helvetica", "I", 7)
	pdf.SetTextColor(150, 150, 150)
	note := "This sheet is for informational purposes only. Prices and specifications subject to change without notice. " +
		"VIN: " + req.Vehicle.VIN
	pdf.MultiCell(contentWidth, 3.5, note, "", "C", false)

	// Dealer branding bar
	pdf.SetY(pageHeight - 10)
	pdf.SetFillColor(30, 50, 80)
	pdf.SetTextColor(255, 255, 255)
	pdf.SetFont("Helvetica", "B", 7)
	pdf.CellFormat(contentWidth, 5, "  "+strings.ToUpper(req.DealerName)+"  —  "+req.DealerPhone+"  —  "+req.DealerEmail,
		"", 1, "L", true, 0, "")
	pdf.SetTextColor(0, 0, 0)

	var buf bytes.Buffer
	if err := pdf.Output(&buf); err != nil {
		return nil, fmt.Errorf("documents: vehicle sheet render: %w", err)
	}
	return buf.Bytes(), nil
}
