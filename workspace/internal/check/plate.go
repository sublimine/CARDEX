package check

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// ErrPlateResolutionUnavailable is returned when no public API exists for
// plate→VIN resolution in the requested country.
var ErrPlateResolutionUnavailable = errors.New("plate resolution unavailable for this country")

// ErrPlateNotFound is returned when the plate is not present in the registry.
var ErrPlateNotFound = errors.New("plate not found")

// PlateResolver converts a normalized license plate and ISO-3166-1 alpha-2
// country code into a VIN.
type PlateResolver interface {
	Resolve(ctx context.Context, plate, country string) (string, error)
}

// NormalizePlate strips whitespace and dashes then uppercases a license plate.
// "1-ABC-23" → "1ABC23", "ab 12 cd" → "AB12CD".
func NormalizePlate(plate string) string {
	plate = strings.ToUpper(plate)
	plate = strings.ReplaceAll(plate, " ", "")
	plate = strings.ReplaceAll(plate, "-", "")
	return plate
}

// PlateRegistry maps ISO-3166-1 alpha-2 country codes to PlateResolver
// implementations. Only NL has a live resolver; the remaining countries are
// honest scaffolds that return ErrPlateResolutionUnavailable.
type PlateRegistry struct {
	resolvers map[string]PlateResolver
}

// NewPlateRegistry builds the registry. rdwBaseURL is the RDW Open Data
// resource base URL, e.g. "https://opendata.rdw.nl/resource". Pass a custom
// base to override for testing.
func NewPlateRegistry(rdwBaseURL string) *PlateRegistry {
	client := &http.Client{Timeout: 10 * time.Second}
	return &PlateRegistry{
		resolvers: map[string]PlateResolver{
			"NL": &NLPlateResolver{client: client, baseURL: rdwBaseURL},
			// Countries below have no publicly accessible plate→VIN API.
			// See unavailableResolver comments for per-country details.
			"FR": &unavailableResolver{"FR"},
			"BE": &unavailableResolver{"BE"},
			"ES": &unavailableResolver{"ES"},
			"DE": &unavailableResolver{"DE"},
			"CH": &unavailableResolver{"CH"},
		},
	}
}

// NewPlateRegistryFromMap builds a PlateRegistry from an explicit resolver map.
// Intended for tests that need to inject mock resolvers.
func NewPlateRegistryFromMap(resolvers map[string]PlateResolver) *PlateRegistry {
	return &PlateRegistry{resolvers: resolvers}
}

// Resolve normalises plate, selects the resolver for country, and delegates.
func (r *PlateRegistry) Resolve(ctx context.Context, plate, country string) (string, error) {
	resolver, ok := r.resolvers[strings.ToUpper(country)]
	if !ok {
		return "", ErrPlateResolutionUnavailable
	}
	return resolver.Resolve(ctx, NormalizePlate(plate), country)
}

// ── NL resolver ───────────────────────────────────────────────────────────────

// NLPlateResolver resolves Dutch license plates to VINs using the RDW Open
// Data m9d7-ebf2 dataset (Gekentekende voertuigen).
//
// Query: GET {base}/m9d7-ebf2.json?kenteken={PLATE}
// Returns field: voertuigidentificatienummer
//
// Same API used by NLProvider; no API key required.
// Rate-limit: ≤1 req/sec per Socrata terms of service.
type NLPlateResolver struct {
	client  *http.Client
	baseURL string // e.g. "https://opendata.rdw.nl/resource"
}

// NewNLPlateResolverWithBase creates an NLPlateResolver pointing at a custom
// base URL. Use in tests to point at a local httptest.Server.
func NewNLPlateResolverWithBase(baseURL string) *NLPlateResolver {
	return &NLPlateResolver{
		client:  &http.Client{Timeout: 5 * time.Second},
		baseURL: baseURL,
	}
}

// rdwPlateRow is the minimum field set from m9d7-ebf2 needed for plate→VIN.
type rdwPlateRow struct {
	Kenteken string `json:"kenteken"`
	VIN      string `json:"voertuigidentificatienummer"`
}

func (r *NLPlateResolver) Resolve(ctx context.Context, plate, _ string) (string, error) {
	u := fmt.Sprintf("%s/%s.json?kenteken=%s",
		r.baseURL, rdwVehiclesDS, url.QueryEscape(plate),
	)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return "", fmt.Errorf("build rdw plate request: %w", err)
	}
	req.Header.Set("Accept", "application/json")

	resp, err := r.client.Do(req)
	if err != nil {
		return "", fmt.Errorf("rdw plate request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("rdw returned HTTP %d", resp.StatusCode)
	}

	var rows []rdwPlateRow
	if err := json.NewDecoder(resp.Body).Decode(&rows); err != nil {
		return "", fmt.Errorf("decode rdw plate response: %w", err)
	}
	if len(rows) == 0 {
		return "", fmt.Errorf("%w: plate %s not in RDW registry", ErrPlateNotFound, plate)
	}

	vin := strings.ToUpper(strings.TrimSpace(rows[0].VIN))
	if vin == "" {
		return "", fmt.Errorf("%w: no VIN in RDW record for plate %s", ErrPlateNotFound, plate)
	}
	return vin, nil
}

// ── Scaffold resolvers ─────────────────────────────────────────────────────────
//
// The following countries have no publicly accessible API for plate→VIN:
//
//   FR: SIV (Système d'Immatriculation des Véhicules) is restricted to
//       professionals; Histovec requires explicit vehicle-owner consent.
//   BE: DIV (Direction pour l'Immatriculation des Véhicules) is restricted to
//       approved authorities; Car-Pass does not expose plate→VIN.
//   ES: DGT TESTRA requires both licence plate and owner DNI; no public lookup.
//   DE: KBA ZFZR is restricted to authorities; no public plate→VIN API.
//   CH: MOFIS (fedpol) is restricted; cantonal systems have no open API.

type unavailableResolver struct{ country string }

func (r *unavailableResolver) Resolve(_ context.Context, _, _ string) (string, error) {
	return "", ErrPlateResolutionUnavailable
}
