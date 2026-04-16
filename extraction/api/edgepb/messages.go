// Package edgepb contains the Go types for the CARDEX Edge Push API.
//
// # Generation note
//
// These types are hand-written to match the proto3 contract defined in
// extraction/api/proto/edge_push.proto.  Run `make proto` (once protoc is
// installed) to replace this file with the code-generated version.  The
// struct layout and JSON tags are identical to what protoc-gen-go would
// produce, so the swap is a drop-in replacement.
//
// # Transport codec
//
// For the MVP the gRPC transport uses a JSON codec (see codec.go).  The
// generated protobuf codec replaces it when `make proto` has been run and
// the server is started with EDGE_CODEC=proto.
package edgepb

// ListingBatch is one page of vehicle listings from the dealer's DMS.
type ListingBatch struct {
	DealerID      string            `json:"dealer_id,omitempty"`
	APIKey        string            `json:"api_key,omitempty"`
	Listings      []*VehicleListing `json:"listings,omitempty"`
	TimestampUnix int64             `json:"timestamp_unix,omitempty"`
}

// VehicleListing is one vehicle record from the dealer's DMS.
type VehicleListing struct {
	VIN          string   `json:"vin,omitempty"`
	Make         string   `json:"make,omitempty"`
	Model        string   `json:"model,omitempty"`
	Year         int32    `json:"year,omitempty"`
	PriceCents   int32    `json:"price_cents,omitempty"`
	Currency     string   `json:"currency,omitempty"`
	MileageKm    int32    `json:"mileage_km,omitempty"`
	FuelType     string   `json:"fuel_type,omitempty"`
	Transmission string   `json:"transmission,omitempty"`
	Color        string   `json:"color,omitempty"`
	ImageURLs    []string `json:"image_urls,omitempty"`
	Description  string   `json:"description,omitempty"`
	SourceURL    string   `json:"source_url,omitempty"`
}

// PushResponse summarises a completed PushListings stream.
type PushResponse struct {
	Accepted   int32              `json:"accepted,omitempty"`
	Rejected   int32              `json:"rejected,omitempty"`
	Rejections []*RejectionDetail `json:"rejections,omitempty"`
}

// RejectionDetail explains why a listing was rejected.
type RejectionDetail struct {
	VIN    string `json:"vin,omitempty"`
	Reason string `json:"reason,omitempty"`
}

// HeartbeatRequest carries the dealer ID for logging.
type HeartbeatRequest struct {
	DealerID string `json:"dealer_id,omitempty"`
}

// HeartbeatResponse returns the server clock.
type HeartbeatResponse struct {
	ServerTimeUnix int64 `json:"server_time_unix,omitempty"`
}
