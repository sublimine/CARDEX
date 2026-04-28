package e09_excel_test

import (
	"bytes"
	"context"
	"encoding/csv"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	excelize "github.com/xuri/excelize/v2"

	"cardex.eu/extraction/internal/extractor/e09_excel"
	"cardex.eu/extraction/internal/pipeline"
)

// buildCSV creates a minimal CSV byte slice with a header row and vehicle rows.
func buildCSV(rows [][]string) []byte {
	var buf bytes.Buffer
	w := csv.NewWriter(&buf)
	_ = w.WriteAll(rows)
	w.Flush()
	return buf.Bytes()
}

// buildXLSX creates a minimal XLSX byte slice with a header row and vehicle rows.
func buildXLSX(rows [][]string) []byte {
	f := excelize.NewFile()
	defer f.Close()
	sheet := "Sheet1"
	for rowIdx, row := range rows {
		for colIdx, cell := range row {
			cellName, _ := excelize.CoordinatesToCellName(colIdx+1, rowIdx+1)
			_ = f.SetCellValue(sheet, cellName, cell)
		}
	}
	var buf bytes.Buffer
	_ = f.Write(&buf)
	return buf.Bytes()
}

// TestE09_CSV_HappyPath verifies that a CSV inventory file with standard
// headers (VIN,Make,Model,Year,Price,Mileage) is correctly parsed.
func TestE09_CSV_HappyPath(t *testing.T) {
	rows := [][]string{
		{"VIN", "Make", "Model", "Year", "Price", "Mileage"},
		{"WBAWBAWBA12345001", "BMW", "320d", "2021", "28500", "45000"},
		{"VF1AAZZZAAZ000002", "Renault", "Clio", "2020", "9500", "35000"},
	}
	csvData := buildCSV(rows)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/inventory.csv":
			w.Header().Set("Content-Type", "text/csv")
			w.Write(csvData)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer srv.Close()

	strategy := e09_excel.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:      "D1",
		Domain:  srv.Listener.Addr().String(),
		URLRoot: srv.URL,
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) < 2 {
		t.Errorf("want >=2 vehicles from CSV, got %d", len(result.Vehicles))
	}
	v := result.Vehicles[0]
	if v.Make == nil || *v.Make == "" {
		t.Error("want Make set from CSV header")
	}
	if v.Year == nil {
		t.Error("want Year set from CSV")
	}
	if result.Strategy != "E09" {
		t.Errorf("want strategy E09, got %q", result.Strategy)
	}
}

// TestE09_XLSX_HappyPath verifies that an XLSX inventory file with
// multi-language headers (Marque/Modele/Annee) is correctly parsed via
// fuzzy column matching.
func TestE09_XLSX_HappyPath(t *testing.T) {
	rows := [][]string{
		{"Marque", "Modele", "Annee", "Prix", "Kilometrage"},
		{"Peugeot", "308", "2019", "12900", "48000"},
		{"Citroen", "C3", "2021", "11500", "22000"},
	}
	xlsxData := buildXLSX(rows)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/voitures.xlsx":
			w.Header().Set("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
			w.Write(xlsxData)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer srv.Close()

	strategy := e09_excel.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:      "D2",
		Domain:  srv.Listener.Addr().String(),
		URLRoot: srv.URL,
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Vehicles) < 2 {
		t.Errorf("want >=2 vehicles from XLSX, got %d", len(result.Vehicles))
	}
}

// TestE09_LinkDiscovery verifies that a homepage with an <a href="*.csv">
// link containing a vehicle keyword is discovered and fetched.
func TestE09_LinkDiscovery(t *testing.T) {
	rows := [][]string{
		{"VIN", "Make", "Model", "Year"},
		{"VF7AAZZZAAZ000001", "Citroen", "Berlingo", "2022"},
	}
	fetched := false

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		host := "http://" + r.Host
		switch r.URL.Path {
		case "/":
			w.Header().Set("Content-Type", "text/html")
			fmt.Fprintf(w, `<html><body>
<a href="%s/feeds/inventory.csv">Download inventory CSV</a>
</body></html>`, host)
		case "/feeds/inventory.csv":
			fetched = true
			w.Header().Set("Content-Type", "text/csv")
			w.Write(buildCSV(rows))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer srv.Close()

	strategy := e09_excel.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:      "D3",
		Domain:  srv.Listener.Addr().String(),
		URLRoot: srv.URL,
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !fetched {
		t.Error("want CSV link discovered and fetched from homepage")
	}
	if len(result.Vehicles) == 0 {
		t.Error("want >=1 vehicle from discovered CSV, got 0")
	}
}

// TestE09_HTTP429_Graceful verifies 429 is handled without panic.
func TestE09_HTTP429_Graceful(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	defer srv.Close()

	strategy := e09_excel.NewWithClient(srv.Client(), 0)
	dealer := pipeline.Dealer{
		ID:      "D4",
		Domain:  srv.Listener.Addr().String(),
		URLRoot: srv.URL,
	}

	result, err := strategy.Extract(context.Background(), dealer)
	if err != nil {
		t.Fatalf("unexpected top-level error: %v", err)
	}
	if len(result.Vehicles) != 0 {
		t.Errorf("want 0 vehicles from 429, got %d", len(result.Vehicles))
	}
}
