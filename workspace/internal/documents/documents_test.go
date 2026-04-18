package documents_test

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"cardex.eu/workspace/internal/documents"
	_ "modernc.org/sqlite"
)

// ── helpers ─────────────────────────────────────────────────────────────────

func openTestDB(t *testing.T) *sql.DB {
	t.Helper()
	db, err := sql.Open("sqlite", ":memory:")
	if err != nil {
		t.Fatalf("open test db: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	return db
}

func testService(t *testing.T) *documents.Service {
	t.Helper()
	db := openTestDB(t)
	dir := t.TempDir()
	svc, err := documents.NewService(context.Background(), db, dir)
	if err != nil {
		t.Fatalf("NewService: %v", err)
	}
	return svc
}

func sampleVehicle() documents.VehicleInfo {
	return documents.VehicleInfo{
		Make:    "BMW",
		Model:   "320d",
		Year:    2020,
		VIN:     "WBA1234567890ABCD",
		Mileage: 45000,
		Fuel:    "Diesel",
		Color:   "Alpine White",
		Power:   140,
	}
}

func sampleParty(name string) documents.Party {
	return documents.Party{
		Name:    name,
		Address: "123 Main St",
		City:    "Berlin",
		Country: "DE",
		VATID:   "DE123456789",
	}
}

// ── contract ─────────────────────────────────────────────────────────────────

func TestGenerateContract_DE(t *testing.T) {
	req := documents.ContractRequest{
		TenantID:  "tenant1",
		VehicleID: "v-001",
		Country:   "DE",
		Seller:    sampleParty("Auto Müller GmbH"),
		Buyer:     sampleParty("Hans Schmidt"),
		Vehicle:   sampleVehicle(),
		Price:     24500,
		Currency:  "EUR",
		VATRate:   19,
		VATScheme: "standard",
		Place:     "Berlin",
		Date:      time.Date(2026, 4, 18, 0, 0, 0, 0, time.UTC),
	}
	data, err := documents.GenerateContract(req)
	if err != nil {
		t.Fatalf("GenerateContract DE: %v", err)
	}
	if len(data) < 100 {
		t.Fatalf("PDF too small: %d bytes", len(data))
	}
	if !bytes.HasPrefix(data, []byte("%PDF")) {
		t.Fatal("output is not a PDF")
	}
}

func TestGenerateContract_FR(t *testing.T) {
	req := documents.ContractRequest{
		TenantID:  "tenant1",
		VehicleID: "v-002",
		Country:   "FR",
		Seller:    sampleParty("AutoFrance SARL"),
		Buyer:     sampleParty("Jean Dupont"),
		Vehicle:   sampleVehicle(),
		Price:     22000,
		Currency:  "EUR",
		VATRate:   20,
		VATScheme: "standard",
		Place:     "Paris",
		Date:      time.Date(2026, 4, 18, 0, 0, 0, 0, time.UTC),
	}
	data, err := documents.GenerateContract(req)
	if err != nil {
		t.Fatalf("GenerateContract FR: %v", err)
	}
	if !bytes.HasPrefix(data, []byte("%PDF")) {
		t.Fatal("output is not a PDF")
	}
}

func TestGenerateContract_ES(t *testing.T) {
	req := documents.ContractRequest{
		TenantID:  "tenant1",
		VehicleID: "v-003",
		Country:   "ES",
		Seller:    sampleParty("AutoEspaña SL"),
		Buyer:     sampleParty("Carlos García"),
		Vehicle:   sampleVehicle(),
		Price:     21500,
		Currency:  "EUR",
		VATRate:   21,
		VATScheme: "standard",
		Place:     "Madrid",
		Date:      time.Date(2026, 4, 18, 0, 0, 0, 0, time.UTC),
	}
	data, err := documents.GenerateContract(req)
	if err != nil {
		t.Fatalf("GenerateContract ES: %v", err)
	}
	if !bytes.HasPrefix(data, []byte("%PDF")) {
		t.Fatal("output is not a PDF")
	}
}

func TestGenerateContract_NL(t *testing.T) {
	req := documents.ContractRequest{
		TenantID:  "tenant1",
		VehicleID: "v-004",
		Country:   "NL",
		Seller:    sampleParty("AutoNL BV"),
		Buyer:     sampleParty("Jan de Vries"),
		Vehicle:   sampleVehicle(),
		Price:     20000,
		Currency:  "EUR",
		VATRate:   21,
		VATScheme: "standard",
		Place:     "Amsterdam",
		Date:      time.Date(2026, 4, 18, 0, 0, 0, 0, time.UTC),
	}
	data, err := documents.GenerateContract(req)
	if err != nil {
		t.Fatalf("GenerateContract NL: %v", err)
	}
	if !bytes.HasPrefix(data, []byte("%PDF")) {
		t.Fatal("output is not a PDF")
	}
}

func TestGenerateContract_UnsupportedCountry(t *testing.T) {
	req := documents.ContractRequest{
		TenantID:  "t1",
		VehicleID: "v-x",
		Country:   "XX",
		Seller:    sampleParty("Seller"),
		Buyer:     sampleParty("Buyer"),
		Vehicle:   sampleVehicle(),
	}
	_, err := documents.GenerateContract(req)
	if err == nil {
		t.Fatal("expected error for unsupported country")
	}
	if !strings.Contains(err.Error(), "unsupported") {
		t.Errorf("unexpected error: %v", err)
	}
}

// ── invoice ──────────────────────────────────────────────────────────────────

func TestGenerateInvoice_Standard(t *testing.T) {
	req := documents.InvoiceRequest{
		TenantID:      "tenant1",
		DealID:        "deal-001",
		InvoiceNumber: "DEALER1-2026-00001",
		Seller:        sampleParty("Auto Müller GmbH"),
		Buyer:         sampleParty("Hans Schmidt"),
		Vehicle:       sampleVehicle(),
		NetAmount:     20588.24,
		VATRate:       19,
		VATAmount:     3911.76,
		TotalAmount:   24500,
		Currency:      "EUR",
		VATScheme:     "standard",
		Date:          time.Date(2026, 4, 18, 0, 0, 0, 0, time.UTC),
		DueDate:       time.Date(2026, 5, 18, 0, 0, 0, 0, time.UTC),
	}
	data, err := documents.GenerateInvoice(req)
	if err != nil {
		t.Fatalf("GenerateInvoice standard: %v", err)
	}
	if !bytes.HasPrefix(data, []byte("%PDF")) {
		t.Fatal("output is not a PDF")
	}
}

func TestGenerateInvoice_ReverseCharge(t *testing.T) {
	req := documents.InvoiceRequest{
		TenantID:      "tenant1",
		DealID:        "deal-002",
		InvoiceNumber: "DEALER1-2026-00002",
		Seller:        sampleParty("Auto Müller GmbH"),
		Buyer: documents.Party{
			Name:    "AutoBelgique SA",
			Address: "Rue de la Loi 1",
			City:    "Brussels",
			Country: "BE",
			VATID:   "BE0123456789",
		},
		Vehicle:     sampleVehicle(),
		NetAmount:   24500,
		VATRate:     0,
		VATAmount:   0,
		TotalAmount: 24500,
		Currency:    "EUR",
		VATScheme:   "reverse_charge",
		Date:        time.Date(2026, 4, 18, 0, 0, 0, 0, time.UTC),
		DueDate:     time.Date(2026, 5, 18, 0, 0, 0, 0, time.UTC),
	}
	data, err := documents.GenerateInvoice(req)
	if err != nil {
		t.Fatalf("GenerateInvoice reverse_charge: %v", err)
	}
	if !bytes.HasPrefix(data, []byte("%PDF")) {
		t.Fatal("output is not a PDF")
	}
}

func TestGenerateInvoice_MarginScheme(t *testing.T) {
	req := documents.InvoiceRequest{
		TenantID:      "tenant1",
		DealID:        "deal-003",
		InvoiceNumber: "DEALER1-2026-00003",
		Seller:        sampleParty("Auto Müller GmbH"),
		Buyer:         sampleParty("Hans Schmidt"),
		Vehicle:       sampleVehicle(),
		NetAmount:     20000,
		VATRate:       0,
		VATAmount:     0,
		TotalAmount:   20000,
		Currency:      "EUR",
		VATScheme:     "margin",
		Date:          time.Date(2026, 4, 18, 0, 0, 0, 0, time.UTC),
		DueDate:       time.Date(2026, 5, 18, 0, 0, 0, 0, time.UTC),
	}
	data, err := documents.GenerateInvoice(req)
	if err != nil {
		t.Fatalf("GenerateInvoice margin: %v", err)
	}
	if !bytes.HasPrefix(data, []byte("%PDF")) {
		t.Fatal("output is not a PDF")
	}
}

// ── vehicle sheet ─────────────────────────────────────────────────────────────

func TestGenerateVehicleSheet(t *testing.T) {
	v := sampleVehicle()
	v.Features = []string{"Panoramic Roof", "Heated Seats", "Navigation", "LED Lights", "Parking Assist"}
	v.ListingURL = "https://cardex.eu/vehicles/v-001"

	req := documents.VehicleSheetRequest{
		TenantID:    "tenant1",
		VehicleID:   "v-001",
		Vehicle:     v,
		Price:       24500,
		Currency:    "EUR",
		DealerName:  "Auto Müller GmbH",
		DealerPhone: "+49 30 1234567",
		DealerEmail: "info@automueller.de",
	}
	data, err := documents.GenerateVehicleSheet(req)
	if err != nil {
		t.Fatalf("GenerateVehicleSheet: %v", err)
	}
	if len(data) < 100 {
		t.Fatalf("PDF too small: %d bytes", len(data))
	}
	if !bytes.HasPrefix(data, []byte("%PDF")) {
		t.Fatal("output is not a PDF")
	}
}

func TestGenerateVehicleSheet_MinimalFields(t *testing.T) {
	req := documents.VehicleSheetRequest{
		TenantID:   "tenant1",
		VehicleID:  "v-002",
		Vehicle:    sampleVehicle(),
		Price:      15000,
		Currency:   "EUR",
		DealerName: "Simple Auto",
	}
	data, err := documents.GenerateVehicleSheet(req)
	if err != nil {
		t.Fatalf("GenerateVehicleSheet minimal: %v", err)
	}
	if !bytes.HasPrefix(data, []byte("%PDF")) {
		t.Fatal("output is not a PDF")
	}
}

// ── transport doc ─────────────────────────────────────────────────────────────

func TestGenerateTransportDoc(t *testing.T) {
	req := documents.TransportRequest{
		TenantID:    "tenant1",
		VehicleID:   "v-001",
		Vehicle:     sampleVehicle(),
		Sender:      sampleParty("Auto Müller GmbH"),
		Recipient:   sampleParty("AutoBelgique SA"),
		Carrier:     "FastTrans GmbH",
		Origin:      "Berlin, DE",
		Destination: "Brussels, BE",
		Date:        time.Date(2026, 4, 18, 0, 0, 0, 0, time.UTC),
		Notes:       "Handle with care. Deliver to rear loading dock.",
	}
	data, err := documents.GenerateTransportDoc(req)
	if err != nil {
		t.Fatalf("GenerateTransportDoc: %v", err)
	}
	if !bytes.HasPrefix(data, []byte("%PDF")) {
		t.Fatal("output is not a PDF")
	}
}

func TestGenerateTransportDoc_NoNotes(t *testing.T) {
	req := documents.TransportRequest{
		TenantID:    "tenant1",
		VehicleID:   "v-005",
		Vehicle:     sampleVehicle(),
		Sender:      sampleParty("Sender Co"),
		Recipient:   sampleParty("Recipient Co"),
		Carrier:     "CarrierX",
		Origin:      "Paris, FR",
		Destination: "Madrid, ES",
		Date:        time.Date(2026, 4, 18, 0, 0, 0, 0, time.UTC),
	}
	data, err := documents.GenerateTransportDoc(req)
	if err != nil {
		t.Fatalf("GenerateTransportDoc no notes: %v", err)
	}
	if !bytes.HasPrefix(data, []byte("%PDF")) {
		t.Fatal("output is not a PDF")
	}
}

// ── service + persistence ─────────────────────────────────────────────────────

func TestService_GenerateContract_StoresFile(t *testing.T) {
	svc := testService(t)

	req := documents.ContractRequest{
		TenantID:  "tenant1",
		VehicleID: "v-001",
		Country:   "DE",
		Seller:    sampleParty("Seller"),
		Buyer:     sampleParty("Buyer"),
		Vehicle:   sampleVehicle(),
		Price:     20000,
		Currency:  "EUR",
		VATScheme: "standard",
		VATRate:   19,
		Place:     "Berlin",
		Date:      time.Now(),
	}

	result, err := svc.GenerateContract(context.Background(), req)
	if err != nil {
		t.Fatalf("Service.GenerateContract: %v", err)
	}

	if result.DocumentID == "" {
		t.Error("DocumentID is empty")
	}
	if result.DownloadURL == "" {
		t.Error("DownloadURL is empty")
	}
	if _, err := os.Stat(result.FilePath); err != nil {
		t.Errorf("PDF file not on disk: %v", err)
	}
}

func TestService_GetDocumentFile(t *testing.T) {
	svc := testService(t)

	req := documents.VehicleSheetRequest{
		TenantID:   "tenant1",
		VehicleID:  "v-sheet-1",
		Vehicle:    sampleVehicle(),
		Price:      18000,
		Currency:   "EUR",
		DealerName: "Test Dealer",
	}

	result, err := svc.GenerateVehicleSheet(context.Background(), req)
	if err != nil {
		t.Fatalf("GenerateVehicleSheet: %v", err)
	}

	doc, err := svc.GetDocumentFile(context.Background(), result.DocumentID)
	if err != nil {
		t.Fatalf("GetDocumentFile: %v", err)
	}
	if doc.ID != result.DocumentID {
		t.Errorf("got ID %q, want %q", doc.ID, result.DocumentID)
	}
	if doc.FilePath != result.FilePath {
		t.Errorf("got FilePath %q, want %q", doc.FilePath, result.FilePath)
	}
}

func TestService_GetDocumentFile_NotFound(t *testing.T) {
	svc := testService(t)
	_, err := svc.GetDocumentFile(context.Background(), "nonexistent-id")
	if err == nil {
		t.Fatal("expected error for nonexistent document")
	}
}

// ── invoice sequencing ────────────────────────────────────────────────────────

func TestNextInvoiceNumber_Unique(t *testing.T) {
	db := openTestDB(t)
	ctx := context.Background()
	if err := documents.EnsureSchema(ctx, db); err != nil {
		t.Fatalf("EnsureSchema: %v", err)
	}

	seen := make(map[string]bool)
	for i := 0; i < 10; i++ {
		num, err := documents.NextInvoiceNumber(ctx, db, "tenant1", "DLR")
		if err != nil {
			t.Fatalf("NextInvoiceNumber iter %d: %v", i, err)
		}
		if seen[num] {
			t.Fatalf("duplicate invoice number: %q", num)
		}
		seen[num] = true
	}
}

func TestNextInvoiceNumber_Format(t *testing.T) {
	db := openTestDB(t)
	ctx := context.Background()
	if err := documents.EnsureSchema(ctx, db); err != nil {
		t.Fatalf("EnsureSchema: %v", err)
	}

	num, err := documents.NextInvoiceNumber(ctx, db, "tenant1", "INV")
	if err != nil {
		t.Fatalf("NextInvoiceNumber: %v", err)
	}
	year := time.Now().Year()
	expected := "INV-" + itoa(year) + "-00001"
	if num != expected {
		t.Errorf("got %q, want %q", num, expected)
	}
}

func TestNextInvoiceNumber_MultiTenant(t *testing.T) {
	db := openTestDB(t)
	ctx := context.Background()
	if err := documents.EnsureSchema(ctx, db); err != nil {
		t.Fatalf("EnsureSchema: %v", err)
	}

	n1, _ := documents.NextInvoiceNumber(ctx, db, "tenantA", "A")
	n2, _ := documents.NextInvoiceNumber(ctx, db, "tenantB", "B")
	n3, _ := documents.NextInvoiceNumber(ctx, db, "tenantA", "A")

	year := time.Now().Year()
	wantA1 := "A-" + itoa(year) + "-00001"
	wantB1 := "B-" + itoa(year) + "-00001"
	wantA2 := "A-" + itoa(year) + "-00002"

	if n1 != wantA1 {
		t.Errorf("n1: got %q, want %q", n1, wantA1)
	}
	if n2 != wantB1 {
		t.Errorf("n2: got %q, want %q", n2, wantB1)
	}
	if n3 != wantA2 {
		t.Errorf("n3: got %q, want %q", n3, wantA2)
	}
}

// ── HTTP handler ──────────────────────────────────────────────────────────────

func TestHandlerContract_Created(t *testing.T) {
	svc := testService(t)
	h := documents.Handler(svc)

	body, _ := json.Marshal(documents.ContractRequest{
		TenantID:  "tenant1",
		VehicleID: "v-h-001",
		Country:   "DE",
		Seller:    sampleParty("Seller GmbH"),
		Buyer:     sampleParty("Buyer"),
		Vehicle:   sampleVehicle(),
		Price:     20000,
		Currency:  "EUR",
		VATScheme: "standard",
		VATRate:   19,
		Place:     "Berlin",
		Date:      time.Now(),
	})

	req := httptest.NewRequest(http.MethodPost, "/api/v1/documents/contract", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)

	if rr.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d: %s", rr.Code, rr.Body.String())
	}

	var result documents.GenerateResult
	if err := json.NewDecoder(rr.Body).Decode(&result); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if result.DocumentID == "" {
		t.Error("DocumentID empty in response")
	}
	if !strings.HasPrefix(result.DownloadURL, "/api/v1/documents/") {
		t.Errorf("unexpected DownloadURL: %q", result.DownloadURL)
	}
}

func TestHandlerContract_MissingCountry(t *testing.T) {
	svc := testService(t)
	h := documents.Handler(svc)

	body, _ := json.Marshal(map[string]string{"vehicle_id": "v-001"})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/documents/contract", bytes.NewReader(body))
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)

	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rr.Code)
	}
}

func TestHandlerDownload_ServesFile(t *testing.T) {
	svc := testService(t)
	h := documents.Handler(svc)

	// First generate a document.
	reqBody, _ := json.Marshal(documents.VehicleSheetRequest{
		TenantID:   "t1",
		VehicleID:  "v-dl-1",
		Vehicle:    sampleVehicle(),
		Price:      15000,
		Currency:   "EUR",
		DealerName: "DL Dealer",
	})
	genReq := httptest.NewRequest(http.MethodPost, "/api/v1/documents/vehicle-sheet", bytes.NewReader(reqBody))
	genReq.Header.Set("Content-Type", "application/json")
	genRec := httptest.NewRecorder()
	h.ServeHTTP(genRec, genReq)
	if genRec.Code != http.StatusCreated {
		t.Fatalf("generate: expected 201, got %d: %s", genRec.Code, genRec.Body.String())
	}

	var result documents.GenerateResult
	_ = json.NewDecoder(genRec.Body).Decode(&result)

	// Now download it.
	dlReq := httptest.NewRequest(http.MethodGet, result.DownloadURL, nil)
	dlRec := httptest.NewRecorder()
	h.ServeHTTP(dlRec, dlReq)

	if dlRec.Code != http.StatusOK {
		t.Fatalf("download: expected 200, got %d: %s", dlRec.Code, dlRec.Body.String())
	}
	if ct := dlRec.Header().Get("Content-Type"); ct != "application/pdf" {
		t.Errorf("Content-Type: got %q, want %q", ct, "application/pdf")
	}
	if !bytes.HasPrefix(dlRec.Body.Bytes(), []byte("%PDF")) {
		t.Error("downloaded file is not a valid PDF")
	}
}

func TestHandlerDownload_NotFound(t *testing.T) {
	svc := testService(t)
	h := documents.Handler(svc)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/documents/nonexistent/download", nil)
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)

	if rr.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", rr.Code)
	}
}

// ── schema ────────────────────────────────────────────────────────────────────

func TestEnsureSchema_Idempotent(t *testing.T) {
	db := openTestDB(t)
	ctx := context.Background()
	for i := 0; i < 3; i++ {
		if err := documents.EnsureSchema(ctx, db); err != nil {
			t.Fatalf("EnsureSchema call %d: %v", i, err)
		}
	}
}

// ── file layout ───────────────────────────────────────────────────────────────

func TestService_FilesStoredUnderTenantDir(t *testing.T) {
	svc := testService(t)

	req := documents.ContractRequest{
		TenantID:  "myTenant",
		VehicleID: "v-dir-1",
		Country:   "NL",
		Seller:    sampleParty("Verkoper BV"),
		Buyer:     sampleParty("Koper"),
		Vehicle:   sampleVehicle(),
		Price:     18000,
		Currency:  "EUR",
		VATScheme: "standard",
		VATRate:   21,
		Place:     "Amsterdam",
		Date:      time.Now(),
	}
	result, err := svc.GenerateContract(context.Background(), req)
	if err != nil {
		t.Fatalf("GenerateContract: %v", err)
	}

	// File must be under {baseDir}/myTenant/documents/
	if !strings.Contains(result.FilePath, filepath.Join("myTenant", "documents")) {
		t.Errorf("file not under tenant dir: %s", result.FilePath)
	}
}

// ── util ──────────────────────────────────────────────────────────────────────

func itoa(n int) string {
	return fmt.Sprintf("%d", n)
}
