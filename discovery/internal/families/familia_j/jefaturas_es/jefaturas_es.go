// Package jefaturas_es implements sub-technique J.ES.2 — Spanish DGT Jefatura
// Provincial classifier.
//
// # Purpose
//
// Maps Spanish postal codes to the 52 DGT (Dirección General de Tráfico)
// Jefaturas Provinciales and stores the ISO 3166-2:ES-{CC} province code on
// dealer_location.region. Also provides the DGT Jefatura Provincial URL for
// each province via JefaturaURL().
//
// # Mapping
//
// Spanish postal codes (5 digits): the first 2 digits encode the province.
// Province codes 01–52 map 1:1 to the 52 traffic provinces:
//   - 01–50: 50 provincias (Spanish provinces)
//   - 51: Ceuta (autonomous city)
//   - 52: Melilla (autonomous city)
//
// CCAA membership is also provided via CCAForProvince() for regional classification.
//
// # Source
//
// Province list from Real Decreto 1690/1986 (nomenclator de municipios).
// DGT Jefatura URLs from https://sede.dgt.gob.es/es/jefaturas-provinciales/
// (verified 2026-04-16).
//
// # BLOCKER_VERIFY
//
//	DGT Jefatura URL structure may change. Verify annually against
//	https://sede.dgt.gob.es/es/jefaturas-provinciales/
//	Last verified: 2026-04-16.
//
// BaseWeights["J"] = 0.05.
package jefaturas_es

import (
	"context"
	"fmt"
	"log/slog"
	"strconv"
	"strings"
	"time"

	"cardex.eu/discovery/internal/kg"
	"cardex.eu/discovery/internal/runner"
)

const (
	familyID    = "J"
	subTechID   = "J.ES.2"
	subTechName = "ES PLZ → DGT Jefatura Provincial classifier"
	countryES   = "ES"
)

// province holds metadata for one Spanish traffic province.
type province struct {
	Code        string // 2-digit code as string, e.g. "28"
	ISOCode     string // ISO 3166-2:ES code, e.g. "ES-M"
	Name        string // province name in Spanish
	CCACode     string // CCAA ISO code, e.g. "ES-MD"
	JefaturaURL string // DGT Jefatura Provincial URL
}

// provinces is the canonical list of 52 Spanish DGT Jefaturas Provinciales.
// Source: sede.dgt.gob.es/es/jefaturas-provinciales/ (verified 2026-04-16).
//
//nolint:gochecknoglobals // deliberate static registry
var provinces = []province{
	{Code: "01", ISOCode: "ES-VI", Name: "Álava / Araba", CCACode: "ES-PV", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/alava/"},
	{Code: "02", ISOCode: "ES-AB", Name: "Albacete", CCACode: "ES-CM", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/albacete/"},
	{Code: "03", ISOCode: "ES-A", Name: "Alicante / Alacant", CCACode: "ES-VC", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/alicante/"},
	{Code: "04", ISOCode: "ES-AL", Name: "Almería", CCACode: "ES-AN", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/almeria/"},
	{Code: "05", ISOCode: "ES-AV", Name: "Ávila", CCACode: "ES-CL", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/avila/"},
	{Code: "06", ISOCode: "ES-BA", Name: "Badajoz", CCACode: "ES-EX", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/badajoz/"},
	{Code: "07", ISOCode: "ES-PM", Name: "Illes Balears", CCACode: "ES-IB", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/baleares/"},
	{Code: "08", ISOCode: "ES-B", Name: "Barcelona", CCACode: "ES-CT", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/barcelona/"},
	{Code: "09", ISOCode: "ES-BU", Name: "Burgos", CCACode: "ES-CL", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/burgos/"},
	{Code: "10", ISOCode: "ES-CC", Name: "Cáceres", CCACode: "ES-EX", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/caceres/"},
	{Code: "11", ISOCode: "ES-CA", Name: "Cádiz", CCACode: "ES-AN", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/cadiz/"},
	{Code: "12", ISOCode: "ES-CS", Name: "Castellón / Castelló", CCACode: "ES-VC", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/castellon/"},
	{Code: "13", ISOCode: "ES-CR", Name: "Ciudad Real", CCACode: "ES-CM", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/ciudad-real/"},
	{Code: "14", ISOCode: "ES-CO", Name: "Córdoba", CCACode: "ES-AN", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/cordoba/"},
	{Code: "15", ISOCode: "ES-C", Name: "A Coruña", CCACode: "ES-GA", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/coruna/"},
	{Code: "16", ISOCode: "ES-CU", Name: "Cuenca", CCACode: "ES-CM", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/cuenca/"},
	{Code: "17", ISOCode: "ES-GI", Name: "Girona", CCACode: "ES-CT", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/gerona/"},
	{Code: "18", ISOCode: "ES-GR", Name: "Granada", CCACode: "ES-AN", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/granada/"},
	{Code: "19", ISOCode: "ES-GU", Name: "Guadalajara", CCACode: "ES-CM", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/guadalajara/"},
	{Code: "20", ISOCode: "ES-SS", Name: "Gipuzkoa", CCACode: "ES-PV", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/guipuzcoa/"},
	{Code: "21", ISOCode: "ES-H", Name: "Huelva", CCACode: "ES-AN", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/huelva/"},
	{Code: "22", ISOCode: "ES-HU", Name: "Huesca", CCACode: "ES-AR", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/huesca/"},
	{Code: "23", ISOCode: "ES-J", Name: "Jaén", CCACode: "ES-AN", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/jaen/"},
	{Code: "24", ISOCode: "ES-LE", Name: "León", CCACode: "ES-CL", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/leon/"},
	{Code: "25", ISOCode: "ES-L", Name: "Lleida", CCACode: "ES-CT", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/lerida/"},
	{Code: "26", ISOCode: "ES-LO", Name: "La Rioja", CCACode: "ES-RI", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/rioja/"},
	{Code: "27", ISOCode: "ES-LU", Name: "Lugo", CCACode: "ES-GA", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/lugo/"},
	{Code: "28", ISOCode: "ES-M", Name: "Madrid", CCACode: "ES-MD", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/madrid/"},
	{Code: "29", ISOCode: "ES-MA", Name: "Málaga", CCACode: "ES-AN", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/malaga/"},
	{Code: "30", ISOCode: "ES-MU", Name: "Murcia", CCACode: "ES-MC", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/murcia/"},
	{Code: "31", ISOCode: "ES-NA", Name: "Navarra / Nafarroa", CCACode: "ES-NC", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/navarra/"},
	{Code: "32", ISOCode: "ES-OR", Name: "Ourense", CCACode: "ES-GA", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/orense/"},
	{Code: "33", ISOCode: "ES-O", Name: "Asturias", CCACode: "ES-AS", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/asturias/"},
	{Code: "34", ISOCode: "ES-P", Name: "Palencia", CCACode: "ES-CL", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/palencia/"},
	{Code: "35", ISOCode: "ES-GC", Name: "Las Palmas", CCACode: "ES-CN", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/las-palmas/"},
	{Code: "36", ISOCode: "ES-PO", Name: "Pontevedra", CCACode: "ES-GA", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/pontevedra/"},
	{Code: "37", ISOCode: "ES-SA", Name: "Salamanca", CCACode: "ES-CL", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/salamanca/"},
	{Code: "38", ISOCode: "ES-TF", Name: "Santa Cruz de Tenerife", CCACode: "ES-CN", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/tenerife/"},
	{Code: "39", ISOCode: "ES-S", Name: "Cantabria", CCACode: "ES-CB", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/cantabria/"},
	{Code: "40", ISOCode: "ES-SG", Name: "Segovia", CCACode: "ES-CL", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/segovia/"},
	{Code: "41", ISOCode: "ES-SE", Name: "Sevilla", CCACode: "ES-AN", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/sevilla/"},
	{Code: "42", ISOCode: "ES-SO", Name: "Soria", CCACode: "ES-CL", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/soria/"},
	{Code: "43", ISOCode: "ES-T", Name: "Tarragona", CCACode: "ES-CT", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/tarragona/"},
	{Code: "44", ISOCode: "ES-TE", Name: "Teruel", CCACode: "ES-AR", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/teruel/"},
	{Code: "45", ISOCode: "ES-TO", Name: "Toledo", CCACode: "ES-CM", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/toledo/"},
	{Code: "46", ISOCode: "ES-V", Name: "Valencia / València", CCACode: "ES-VC", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/valencia/"},
	{Code: "47", ISOCode: "ES-VA", Name: "Valladolid", CCACode: "ES-CL", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/valladolid/"},
	{Code: "48", ISOCode: "ES-BI", Name: "Bizkaia", CCACode: "ES-PV", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/vizcaya/"},
	{Code: "49", ISOCode: "ES-ZA", Name: "Zamora", CCACode: "ES-CL", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/zamora/"},
	{Code: "50", ISOCode: "ES-Z", Name: "Zaragoza", CCACode: "ES-AR", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/zaragoza/"},
	{Code: "51", ISOCode: "ES-CE", Name: "Ceuta", CCACode: "ES-CE", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/ceuta/"},
	{Code: "52", ISOCode: "ES-ML", Name: "Melilla", CCACode: "ES-ML", JefaturaURL: "https://sede.dgt.gob.es/es/jefaturas-provinciales/melilla/"},
}

// provinceByCode is a compiled lookup map for O(1) access.
//
//nolint:gochecknoglobals // computed from provinces at init
var provinceByCode map[string]province

func init() {
	provinceByCode = make(map[string]province, len(provinces))
	for _, p := range provinces {
		provinceByCode[p.Code] = p
	}
}

// ProvinceForPLZ returns the province for a 5-digit Spanish postal code.
// Returns the province and true if mappable, zero value and false otherwise.
func ProvinceForPLZ(plz string) (province, bool) {
	plz = strings.TrimSpace(plz)
	if len(plz) < 2 {
		return province{}, false
	}
	prefix := fmt.Sprintf("%02s", plz[:2])
	// Validate prefix is all digits.
	if _, err := strconv.Atoi(prefix); err != nil {
		return province{}, false
	}
	p, ok := provinceByCode[prefix]
	return p, ok
}

// JefaturaURL returns the DGT Jefatura Provincial URL for a province code
// string (2-digit, e.g. "28"), or "" if not found.
func JefaturaURL(provinceCode string) string {
	provinceCode = strings.TrimLeft(provinceCode, "0")
	if len(provinceCode) == 1 {
		provinceCode = "0" + provinceCode
	}
	p, ok := provinceByCode[provinceCode]
	if !ok {
		return ""
	}
	return p.JefaturaURL
}

// Count returns the total number of registered provinces (always 52).
func Count() int { return len(provinces) }

// JefaturasES classifies ES dealers in the KG by DGT Jefatura Provincial.
type JefaturasES struct {
	graph kg.KnowledgeGraph
	log   *slog.Logger
}

// New constructs a JefaturasES classifier.
func New(graph kg.KnowledgeGraph) *JefaturasES {
	return &JefaturasES{
		graph: graph,
		log:   slog.Default().With("sub_technique", subTechID),
	}
}

// ID returns the sub-technique identifier.
func (j *JefaturasES) ID() string { return subTechID }

// Name returns the human-readable sub-technique label.
func (j *JefaturasES) Name() string { return subTechName }

// Run classifies all ES dealers in the KG that are missing a province sub-region
// by mapping their postal code to the appropriate ISO 3166-2:ES province code.
func (j *JefaturasES) Run(ctx context.Context) (*runner.SubTechniqueResult, error) {
	start := time.Now()
	result := &runner.SubTechniqueResult{SubTechniqueID: subTechID, Country: countryES}

	candidates, err := j.graph.ListDealersByCountry(ctx, countryES)
	if err != nil {
		result.Errors++
		result.Duration = time.Since(start)
		return result, err
	}

	for _, d := range candidates {
		if ctx.Err() != nil {
			break
		}
		if d.PostalCode == nil || *d.PostalCode == "" {
			continue
		}
		prov, ok := ProvinceForPLZ(*d.PostalCode)
		if !ok {
			continue
		}
		if err := j.graph.UpdateDealerSubRegion(ctx, d.DealerID, prov.ISOCode); err != nil {
			j.log.Warn("jefaturas_es: update sub-region error", "dealer", d.DealerID, "err", err)
			result.Errors++
			continue
		}
		result.Discovered++
	}

	result.Duration = time.Since(start)
	j.log.Info("jefaturas_es: done", "classified", result.Discovered, "errors", result.Errors)
	return result, nil
}
