// Package documents generates PDF documents for CARDEX Workspace:
// purchase/sale contracts (DE/FR/ES/NL), EU invoices, vehicle technical sheets,
// and simplified CMR transport documents.
package documents

import "time"

// DocType classifies what kind of document was generated.
type DocType string

const (
	DocTypeContract      DocType = "contract"
	DocTypeInvoice       DocType = "invoice"
	DocTypeVehicleSheet  DocType = "vehicle_sheet"
	DocTypeTransportDoc  DocType = "transport_doc"
)

// Document is the persisted record of a generated PDF.
type Document struct {
	ID        string    `json:"id"`
	TenantID  string    `json:"tenant_id"`
	Type      DocType   `json:"type"`
	VehicleID string    `json:"vehicle_id,omitempty"`
	DealID    string    `json:"deal_id,omitempty"`
	FilePath  string    `json:"file_path"`
	CreatedAt time.Time `json:"created_at"`
}

// Party represents either a dealer (seller) or a buyer.
type Party struct {
	Name    string `json:"name"`
	Address string `json:"address"`
	City    string `json:"city"`
	Country string `json:"country"`
	VATID   string `json:"vat_id,omitempty"`
	Phone   string `json:"phone,omitempty"`
	Email   string `json:"email,omitempty"`
}

// VehicleInfo holds the vehicle data fields used across all document types.
type VehicleInfo struct {
	Make         string  `json:"make"`
	Model        string  `json:"model"`
	Year         int     `json:"year"`
	VIN          string  `json:"vin"`
	Registration string  `json:"registration,omitempty"`
	Mileage      int     `json:"mileage_km"`
	Fuel         string  `json:"fuel_type"`
	Color        string  `json:"color,omitempty"`
	Power        int     `json:"power_kw,omitempty"`
	BodyType     string  `json:"body_type,omitempty"`
	Features     []string `json:"features,omitempty"`
	ImageURL     string  `json:"image_url,omitempty"`
	ListingURL   string  `json:"listing_url,omitempty"`
}

// ContractRequest is the input for generating a purchase/sale contract.
type ContractRequest struct {
	TenantID  string      `json:"tenant_id"`
	VehicleID string      `json:"vehicle_id"`
	ContactID string      `json:"contact_id"`
	Country   string      `json:"country"` // DE | FR | ES | NL
	Seller    Party       `json:"seller"`
	Buyer     Party       `json:"buyer"`
	Vehicle   VehicleInfo `json:"vehicle"`
	Price     float64     `json:"price"`
	Currency  string      `json:"currency"` // EUR
	VATRate   float64     `json:"vat_rate"`  // 0 = exempt / reverse charge
	VATScheme string      `json:"vat_scheme"` // "standard"|"reverse_charge"|"margin"
	Place     string      `json:"place"`
	Date      time.Time   `json:"date"`
}

// InvoiceRequest is the input for generating an EU invoice.
type InvoiceRequest struct {
	TenantID      string      `json:"tenant_id"`
	DealID        string      `json:"deal_id"`
	InvoiceNumber string      `json:"invoice_number"` // {prefix}-{year}-{seq}
	Seller        Party       `json:"seller"`
	Buyer         Party       `json:"buyer"`
	Vehicle       VehicleInfo `json:"vehicle"`
	NetAmount     float64     `json:"net_amount"`
	VATRate       float64     `json:"vat_rate"`
	VATAmount     float64     `json:"vat_amount"`
	TotalAmount   float64     `json:"total_amount"`
	Currency      string      `json:"currency"`
	VATScheme     string      `json:"vat_scheme"` // "standard"|"reverse_charge"|"margin"
	Date          time.Time   `json:"date"`
	DueDate       time.Time   `json:"due_date"`
}

// VehicleSheetRequest is the input for a 1-page vehicle technical sheet.
type VehicleSheetRequest struct {
	TenantID  string      `json:"tenant_id"`
	VehicleID string      `json:"vehicle_id"`
	Vehicle   VehicleInfo `json:"vehicle"`
	Price     float64     `json:"price"`
	Currency  string      `json:"currency"`
	DealerName string     `json:"dealer_name"`
	DealerPhone string    `json:"dealer_phone,omitempty"`
	DealerEmail string    `json:"dealer_email,omitempty"`
}

// TransportRequest is the input for a simplified CMR-like transport document.
type TransportRequest struct {
	TenantID    string      `json:"tenant_id"`
	VehicleID   string      `json:"vehicle_id"`
	Vehicle     VehicleInfo `json:"vehicle"`
	Sender      Party       `json:"sender"`
	Recipient   Party       `json:"recipient"`
	Carrier     string      `json:"carrier"`
	Origin      string      `json:"origin"`
	Destination string      `json:"destination"`
	Date        time.Time   `json:"date"`
	Notes       string      `json:"notes,omitempty"`
}

// GenerateResult is returned after successful PDF generation.
type GenerateResult struct {
	DocumentID string `json:"document_id"`
	FilePath   string `json:"file_path"`
	DownloadURL string `json:"download_url"`
}
