// Package matraba implements a parser, importer, and SQLite-backed VIN
// index for the Spanish DGT MATRABA microdata feed — the monthly dump of
// every vehicle matriculation (and equivalent dumps for transfers and
// deregistrations: TRANSFE, BAJAS).
//
// The feed is distributed as fixed-width Latin-1 text (714 chars per record,
// 69 fields) under stable public URLs on www.dgt.es — no authentication
// required. See spec:
//
//	https://sedeapl.dgt.gob.es/IEST_INTER/pdfs/disenoRegistro/vehiculos/matriculaciones/MATRICULACIONES_MATRABA.pdf
//
// MATRABA records are keyed by VIN (BASTIDOR_ITV); the plate is NOT present
// in the file. In this project MATRABA is used as a post-lookup enrichment
// source: once comprobarmatricula.com returns a VIN, we query the local
// MATRABA store to augment PlateResult with richer technical fields
// (municipality, homologation number, electric range, wheelbase, etc).
//
// Privacy note: since 2025-02-01 the public MATRABA files mask the final
// 10 chars of the VIN (WMI + first 3 VDS are kept). The parser still decodes
// the masked VINs but enrichment by exact VIN only works for 2014-12..2024-12
// data. For post-2025 data, the store indexes by VIN prefix too.
package matraba

import (
	"fmt"
	"strconv"
	"strings"
	"time"
)

// RecordLength is the fixed-width length of a MATRABA / TRANSFE / BAJAS row
// (excluding the line terminator).
const RecordLength = 714

// Record is a single parsed MATRABA row. Field names mirror the official
// spec (with ASCII normalisation for readability). Empty/blank fields are
// represented as zero values; numeric "*******" or "-" placeholders are
// treated as zero.
type Record struct {
	// Identification & timing
	FecMatricula         time.Time // field 1
	CodClaseMat          string    // field 2 (raw)
	FecTramitacion       time.Time // field 3
	MarcaITV             string    // field 4
	ModeloITV            string    // field 5
	CodProcedenciaITV    string    // field 6
	Bastidor             string    // field 7 — VIN (may be partially masked since 2025-02-01)
	CodTipo              string    // field 8 (raw, e.g. "40" turismo, "50" moto)
	CodPropulsionITV     string    // field 9
	CilindradaCC         int       // field 10
	PotenciaFiscalCVF    float64   // field 11 — fiscal horsepower (CVF)
	TaraKg               int       // field 12 — empty weight
	PesoMaxKg            int       // field 13 — max authorised weight
	NumPlazas            int       // field 14
	IndPrecinto          bool      // field 15 ("SI"/blank)
	IndEmbargo           bool      // field 16
	NumTransmisiones     int       // field 17 — ownership transfers count
	NumTitulares         int       // field 18 — owners count
	LocalidadVehiculo    string    // field 19 — town of domicile (free text)
	CodProvinciaVeh      string    // field 20
	CodProvinciaMat      string    // field 21 — registration province
	ClaveTramite         string    // field 22
	FecTramite           time.Time // field 23
	CodigoPostal         string    // field 24
	FecPrimMatriculacion time.Time // field 25
	IndNuevoUsado        string    // field 26 — "N"/"U"
	PersonaFisicaJurid   string    // field 27 — "D"/"X"
	CodigoITV            string    // field 28
	Servicio             string    // field 29 — e.g. B00, A04
	CodMunicipioINE      string    // field 30 — INE municipality code
	Municipio            string    // field 31 — municipality name
	PotenciaKW           float64   // field 32 — net max power kW
	NumPlazasMax         int       // field 33
	CO2GPerKm            int       // field 34 — g/km
	Renting              bool      // field 35 ("S")
	CodTutela            string    // field 36
	CodPosesion          string    // field 37
	IndBajaDef           string    // field 38 (one of 0/1/2/3/4/5/7/8/9/A/B/C or blank)
	IndBajaTemp          bool      // field 39 ("S")
	IndSustraccion       bool      // field 40 ("S") — vehicle reported stolen
	BajaTelematica       string    // field 41 — "En desguace" or blank
	TipoITV              string    // field 42 — vehicle type description
	VarianteITV          string    // field 43 — variant
	VersionITV           string    // field 44 — full commercial version
	FabricanteITV        string    // field 45 — manufacturer name
	MasaOrdenMarchaKg    int       // field 46
	MasaMaxTecnicaKg     int       // field 47
	CatHomologacionUE    string    // field 48 — e.g. M1, N1, L3e
	Carroceria           string    // field 49 — body code
	PlazasPie            int       // field 50 — standing places (buses)
	NivelEmisionesEURO   string    // field 51 — e.g. EURO6, EURO6d
	ConsumoWhKm          int       // field 52 — Wh/km (electric)
	ClasifReglamento     string    // field 53 — RD 2822 classification code
	CategoriaElectrico   string    // field 54 — PHEV/REEV/HEV/BEV or blank
	AutonomiaElecKm      int       // field 55 — electric range km
	MarcaBase            string    // field 56
	FabricanteBase       string    // field 57
	TipoBase             string    // field 58
	VarianteBase         string    // field 59
	VersionBase          string    // field 60
	DistanciaEjes12Mm    int       // field 61 — wheelbase in mm
	ViaAnteriorMm        int       // field 62 — front track
	ViaPosteriorMm       int       // field 63 — rear track
	TipoAlimentacion     string    // field 64 — M/B/F (mono/bi/flex fuel)
	ContrasenaHomolog    string    // field 65 — type approval number
	EcoInnovacion        string    // field 66 — S/N/blank
	ReduccionEco         string    // field 67 — reserved
	CodigoEco            string    // field 68 — reserved
	FecProceso           time.Time // field 69
}

// fieldOffsets maps field index (1-based per the spec) to (startOffset,length).
// Offsets are 0-based inclusive start (convert from spec's 1-based).
var fieldOffsets = [...]struct{ start, length int }{
	{0, 0}, // unused index 0 (spec fields are 1-based)
	{0, 8},     //  1 FEC_MATRICULA
	{8, 1},     //  2 COD_CLASE_MAT
	{9, 8},     //  3 FEC_TRAMITACION
	{17, 30},   //  4 MARCA_ITV
	{47, 22},   //  5 MODELO_ITV
	{69, 1},    //  6 COD_PROCEDENCIA_ITV
	{70, 21},   //  7 BASTIDOR_ITV
	{91, 2},    //  8 COD_TIPO
	{93, 1},    //  9 COD_PROPULSION_ITV
	{94, 5},    // 10 CILINDRADA_ITV
	{99, 6},    // 11 POTENCIA_ITV
	{105, 6},   // 12 TARA
	{111, 6},   // 13 PESO_MAX
	{117, 3},   // 14 NUM_PLAZAS
	{120, 2},   // 15 IND_PRECINTO
	{122, 2},   // 16 IND_EMBARGO
	{124, 2},   // 17 NUM_TRANSMISIONES
	{126, 2},   // 18 NUM_TITULARES
	{128, 24},  // 19 LOCALIDAD_VEHICULO
	{152, 2},   // 20 COD_PROVINCIA_VEH
	{154, 2},   // 21 COD_PROVINCIA_MAT
	{156, 1},   // 22 CLAVE_TRAMITE
	{157, 8},   // 23 FEC_TRAMITE
	{165, 5},   // 24 CODIGO_POSTAL
	{170, 8},   // 25 FEC_PRIM_MATRICULACION
	{178, 1},   // 26 IND_NUEVO_USADO
	{179, 1},   // 27 PERSONA_FISICA_JURIDICA
	{180, 9},   // 28 CODIGO_ITV
	{189, 3},   // 29 SERVICIO
	{192, 5},   // 30 COD_MUNICIPIO_INE_VEH
	{197, 30},  // 31 MUNICIPIO
	{227, 7},   // 32 KW_ITV
	{234, 3},   // 33 NUM_PLAZAS_MAX
	{237, 5},   // 34 CO2_ITV
	{242, 1},   // 35 RENTING
	{243, 1},   // 36 COD_TUTELA
	{244, 1},   // 37 COD_POSESION
	{245, 1},   // 38 IND_BAJA_DEF
	{246, 1},   // 39 IND_BAJA_TEMP
	{247, 1},   // 40 IND_SUSTRACCION
	{248, 11},  // 41 BAJA_TELEMATICA
	{259, 25},  // 42 TIPO_ITV
	{284, 25},  // 43 VARIANTE_ITV
	{309, 35},  // 44 VERSION_ITV
	{344, 70},  // 45 FABRICANTE_ITV
	{414, 6},   // 46 MASA_ORDEN_MARCHA_ITV
	{420, 6},   // 47 MASA_MAXIMA_TECNICA_ADMISIBLE_ITV
	{426, 4},   // 48 CATEGORIA_HOMOLOGACION_EUROPEA_ITV
	{430, 4},   // 49 CARROCERIA
	{434, 3},   // 50 PLAZAS_PIE
	{437, 8},   // 51 NIVEL_EMISIONES_EURO_ITV
	{445, 4},   // 52 CONSUMO_WH/KM_ITV
	{449, 4},   // 53 CLASIFICACION_REGLAMENTO_VEHICULOS_ITV
	{453, 4},   // 54 CATEGORIA_VEHICULO_ELECTRICO
	{457, 6},   // 55 AUTONOMIA_VEHICULO_ELECTRICO
	{463, 30},  // 56 MARCA_VEHICULO_BASE
	{493, 50},  // 57 FABRICANTE_VEHICULO_BASE
	{543, 35},  // 58 TIPO_VEHICULO_BASE
	{578, 25},  // 59 VARIANTE_VEHICULO_BASE
	{603, 35},  // 60 VERSION_VEHICULO_BASE
	{638, 4},   // 61 DISTANCIA_EJES_12_ITV
	{642, 4},   // 62 VIA_ANTERIOR_ITV
	{646, 4},   // 63 VIA_POSTERIOR_ITV
	{650, 1},   // 64 TIPO_ALIMENTACION_ITV
	{651, 25},  // 65 CONTRASENA_HOMOLOGACION_ITV
	{676, 1},   // 66 ECO_INNOVACION_ITV
	{677, 4},   // 67 REDUCCION_ECO_ITV
	{681, 25},  // 68 CODIGO_ECO_ITV
	{706, 8},   // 69 FEC_PROCESO
}

// field returns the trimmed substring for field index i (1-based).
// Returns "" when the row is shorter than the field end offset.
func field(line string, i int) string {
	if i < 1 || i >= len(fieldOffsets) {
		return ""
	}
	fo := fieldOffsets[i]
	if fo.start+fo.length > len(line) {
		return ""
	}
	return strings.TrimSpace(line[fo.start : fo.start+fo.length])
}

// parseDMY8 parses DDMMYYYY → time.Time. Returns zero time on blank or
// unparseable input.
func parseDMY8(s string) time.Time {
	s = strings.TrimSpace(s)
	if s == "" || s == "00000000" {
		return time.Time{}
	}
	t, err := time.Parse("02012006", s)
	if err != nil {
		return time.Time{}
	}
	return t
}

// parseInt interprets the trimmed string as an integer. Spec-placeholder
// sentinels like "*****" or "-" yield zero.
func parseInt(s string) int {
	s = strings.TrimSpace(s)
	if s == "" || strings.ContainsAny(s, "*-") {
		return 0
	}
	n, err := strconv.Atoi(s)
	if err != nil {
		return 0
	}
	return n
}

// parseFloat like parseInt, but decimal. Accepts both "," and "." as
// separator (the feed uses "." but Spanish locale sometimes leaks).
func parseFloat(s string) float64 {
	s = strings.TrimSpace(s)
	if s == "" || strings.ContainsAny(s, "*") {
		return 0
	}
	s = strings.ReplaceAll(s, ",", ".")
	f, err := strconv.ParseFloat(s, 64)
	if err != nil {
		return 0
	}
	return f
}

// parseBoolSI returns true when the trimmed value is "S" or "SI".
func parseBoolSI(s string) bool {
	s = strings.TrimSpace(strings.ToUpper(s))
	return s == "S" || s == "SI"
}

// Parse decodes a single fixed-width MATRABA row. Rows shorter than
// RecordLength are accepted (missing trailing fields default to zero) to
// tolerate pre-spec-revision historical files that lack some columns.
// Returns an error only when the row is too short to contain the
// identification fields (< 91 bytes — up to and including VIN).
func Parse(line string) (Record, error) {
	// Strip trailing CR (Windows line endings) so offsets line up.
	line = strings.TrimRight(line, "\r\n")
	if len(line) < 91 {
		return Record{}, fmt.Errorf("matraba: line too short: %d bytes", len(line))
	}
	r := Record{
		FecMatricula:         parseDMY8(field(line, 1)),
		CodClaseMat:          field(line, 2),
		FecTramitacion:       parseDMY8(field(line, 3)),
		MarcaITV:             field(line, 4),
		ModeloITV:            field(line, 5),
		CodProcedenciaITV:    field(line, 6),
		Bastidor:             strings.ToUpper(field(line, 7)),
		CodTipo:              field(line, 8),
		CodPropulsionITV:     field(line, 9),
		CilindradaCC:         parseInt(field(line, 10)),
		PotenciaFiscalCVF:    parseFloat(field(line, 11)),
		TaraKg:               parseInt(field(line, 12)),
		PesoMaxKg:            parseInt(field(line, 13)),
		NumPlazas:            parseInt(field(line, 14)),
		IndPrecinto:          parseBoolSI(field(line, 15)),
		IndEmbargo:           parseBoolSI(field(line, 16)),
		NumTransmisiones:     parseInt(field(line, 17)),
		NumTitulares:         parseInt(field(line, 18)),
		LocalidadVehiculo:    field(line, 19),
		CodProvinciaVeh:      field(line, 20),
		CodProvinciaMat:      field(line, 21),
		ClaveTramite:         field(line, 22),
		FecTramite:           parseDMY8(field(line, 23)),
		CodigoPostal:         field(line, 24),
		FecPrimMatriculacion: parseDMY8(field(line, 25)),
		IndNuevoUsado:        field(line, 26),
		PersonaFisicaJurid:   field(line, 27),
		CodigoITV:            field(line, 28),
		Servicio:             field(line, 29),
		CodMunicipioINE:      field(line, 30),
		Municipio:            field(line, 31),
		PotenciaKW:           parseFloat(field(line, 32)),
		NumPlazasMax:         parseInt(field(line, 33)),
		CO2GPerKm:            parseInt(field(line, 34)),
		Renting:              parseBoolSI(field(line, 35)),
		CodTutela:            field(line, 36),
		CodPosesion:          field(line, 37),
		IndBajaDef:           field(line, 38),
		IndBajaTemp:          parseBoolSI(field(line, 39)),
		IndSustraccion:       parseBoolSI(field(line, 40)),
		BajaTelematica:       field(line, 41),
		TipoITV:              field(line, 42),
		VarianteITV:          field(line, 43),
		VersionITV:           field(line, 44),
		FabricanteITV:        field(line, 45),
		MasaOrdenMarchaKg:    parseInt(field(line, 46)),
		MasaMaxTecnicaKg:     parseInt(field(line, 47)),
		CatHomologacionUE:    field(line, 48),
		Carroceria:           field(line, 49),
		PlazasPie:            parseInt(field(line, 50)),
		NivelEmisionesEURO:   field(line, 51),
		ConsumoWhKm:          parseInt(field(line, 52)),
		ClasifReglamento:     field(line, 53),
		CategoriaElectrico:   field(line, 54),
		AutonomiaElecKm:      parseInt(field(line, 55)),
		MarcaBase:            field(line, 56),
		FabricanteBase:       field(line, 57),
		TipoBase:             field(line, 58),
		VarianteBase:         field(line, 59),
		VersionBase:          field(line, 60),
		DistanciaEjes12Mm:    parseInt(field(line, 61)),
		ViaAnteriorMm:        parseInt(field(line, 62)),
		ViaPosteriorMm:       parseInt(field(line, 63)),
		TipoAlimentacion:     field(line, 64),
		ContrasenaHomolog:    field(line, 65),
		EcoInnovacion:        field(line, 66),
		ReduccionEco:         field(line, 67),
		CodigoEco:            field(line, 68),
		FecProceso:           parseDMY8(field(line, 69)),
	}
	return r, nil
}

// VINMasked reports whether the record's VIN appears to be the post-2025-02
// redacted form (last 10 chars replaced with asterisks).
func (r Record) VINMasked() bool {
	return strings.Contains(r.Bastidor, "*")
}

// VINPrefix returns the first 11 chars of the VIN (WMI + first 3 VDS) —
// this is the portion that remains unmasked in post-2025 files, and is
// useful as a fallback index when exact VIN matches aren't possible.
func (r Record) VINPrefix() string {
	v := r.Bastidor
	if len(v) < 11 {
		return v
	}
	return v[:11]
}

// FuelTypeLabel maps COD_PROPULSION_ITV to a human-readable label.
// Source: spec anexo 1.3.5.
func (r Record) FuelTypeLabel() string {
	return fuelLabels[r.CodPropulsionITV]
}

// VehicleTypeLabel maps COD_TIPO to a human-readable Spanish label.
// Source: spec anexo 1.3.4 (~90 codes).
func (r Record) VehicleTypeLabel() string {
	return vehicleTypeLabels[r.CodTipo]
}

// ProvinceLabel maps COD_PROVINCIA_VEH (or COD_PROVINCIA_MAT) to the
// official province name. Both use the same code table.
func ProvinceLabel(code string) string {
	return provinceLabels[code]
}
