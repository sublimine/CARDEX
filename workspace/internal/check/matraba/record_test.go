package matraba

import (
	"fmt"
	"strings"
	"testing"
)

// fieldLengths is derived from fieldOffsets — used by tests to assemble
// a fixed-width row at the exact spec layout without hard-coding 69 magic
// numbers in each test.
func fieldLengths() []int {
	out := make([]int, len(fieldOffsets))
	for i := range fieldOffsets {
		out[i] = fieldOffsets[i].length
	}
	return out
}

// buildRow renders a 714-byte MATRABA row from a map of 1-based field
// indices to their raw values. Missing indices are left blank-padded.
// The helper right-pads to the exact field length and concatenates; the
// resulting row can be fed to Parse directly.
func buildRow(t *testing.T, vals map[int]string) string {
	t.Helper()
	lens := fieldLengths()
	var b strings.Builder
	for i := 1; i < len(lens); i++ {
		v := vals[i]
		if len(v) > lens[i] {
			t.Fatalf("field %d value %q exceeds length %d", i, v, lens[i])
		}
		b.WriteString(v + strings.Repeat(" ", lens[i]-len(v)))
	}
	if b.Len() != RecordLength {
		t.Fatalf("assembled row has %d bytes, want %d", b.Len(), RecordLength)
	}
	return b.String()
}

func TestRecordLengthMatchesOffsets(t *testing.T) {
	lens := fieldLengths()
	total := 0
	for _, n := range lens {
		total += n
	}
	if total != RecordLength {
		t.Fatalf("sum of field lengths = %d, want %d", total, RecordLength)
	}
}

// fullSampleRow returns a representative MATRABA line for a 2009 VW Tiguan
// registered in Madrid — matches the exemplar from ES_ENDPOINTS.md.
func fullSampleRow(t *testing.T) (string, map[int]string) {
	t.Helper()
	vals := map[int]string{
		1:  "02092009",           // FEC_MATRICULA DDMMYYYY
		2:  "M",                  // COD_CLASE_MAT
		3:  "02092009",           // FEC_TRAMITACION
		4:  "VOLKSWAGEN",         // MARCA_ITV
		5:  "TIGUAN",             // MODELO_ITV
		6:  "0",                  // COD_PROCEDENCIA_ITV
		7:  "WVGZZZ5NZAW021819",  // BASTIDOR_ITV
		8:  "40",                 // COD_TIPO (turismo)
		9:  "1",                  // COD_PROPULSION_ITV (Diésel)
		10: "01968",              // CILINDRADA
		11: "015.50",             // POTENCIA (CVF)
		12: "001660",             // TARA
		13: "002300",             // PESO_MAX
		14: "005",                // NUM_PLAZAS
		17: "03",                 // NUM_TRANSMISIONES
		18: "03",                 // NUM_TITULARES
		19: "MADRID",             // LOCALIDAD_VEHICULO
		20: "28",                 // COD_PROVINCIA_VEH
		21: "28",                 // COD_PROVINCIA_MAT
		22: "M",                  // CLAVE_TRAMITE
		23: "02092009",           // FEC_TRAMITE
		24: "28001",              // CODIGO_POSTAL
		25: "02092009",           // FEC_PRIM_MATRICULACION
		26: "N",                  // IND_NUEVO_USADO
		27: "D",                  // PERSONA_FISICA_JURIDICA
		28: "E12000456",          // CODIGO_ITV
		29: "A00",                // SERVICIO
		30: "28079",              // COD_MUNICIPIO_INE_VEH
		31: "MADRID",             // MUNICIPIO
		32: "0125.00",            // KW
		33: "005",                // NUM_PLAZAS_MAX
		34: "00185",              // CO2
		42: "TURISMO",            // TIPO_ITV
		43: "V1",                 // VARIANTE_ITV
		44: "2.0 TDI 4MOTION",    // VERSION_ITV
		45: "VOLKSWAGEN AG",      // FABRICANTE_ITV
		46: "001700",             // MASA_ORDEN_MARCHA
		47: "002300",             // MASA_MAX_TECNICA
		48: "M1",                 // CATEGORIA_HOMOLOGACION_EU
		49: "AC",                 // CARROCERIA
		50: "000",                // PLAZAS_PIE
		51: "EURO5",              // NIVEL_EMISIONES
		52: "0000",               // CONSUMO_WH
		53: "1000",               // CLASIF_REGLAMENTO
		55: "000000",             // AUTONOMIA_ELEC
		61: "2604",               // DISTANCIA_EJES (mm)
		62: "1540",               // VIA_ANTERIOR
		63: "1565",               // VIA_POSTERIOR
		64: "M",                  // TIPO_ALIMENTACION
		65: "E12*0048*01",        // CONTRASENA_HOMOLOGACION
		66: "N",                  // ECO_INNOVACION
		69: "15102009",           // FEC_PROCESO
	}
	return buildRow(t, vals), vals
}

func TestParseFullRow(t *testing.T) {
	row, _ := fullSampleRow(t)
	rec, err := Parse(row)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}

	checks := []struct {
		name string
		got  any
		want any
	}{
		{"Bastidor", rec.Bastidor, "WVGZZZ5NZAW021819"},
		{"MarcaITV", rec.MarcaITV, "VOLKSWAGEN"},
		{"ModeloITV", rec.ModeloITV, "TIGUAN"},
		{"CodTipo", rec.CodTipo, "40"},
		{"CodPropulsionITV", rec.CodPropulsionITV, "1"},
		{"CilindradaCC", rec.CilindradaCC, 1968},
		{"PotenciaFiscalCVF", rec.PotenciaFiscalCVF, 15.5},
		{"TaraKg", rec.TaraKg, 1660},
		{"PesoMaxKg", rec.PesoMaxKg, 2300},
		{"NumPlazas", rec.NumPlazas, 5},
		{"NumTransmisiones", rec.NumTransmisiones, 3},
		{"NumTitulares", rec.NumTitulares, 3},
		{"LocalidadVehiculo", rec.LocalidadVehiculo, "MADRID"},
		{"CodProvinciaVeh", rec.CodProvinciaVeh, "28"},
		{"CodProvinciaMat", rec.CodProvinciaMat, "28"},
		{"CodigoPostal", rec.CodigoPostal, "28001"},
		{"IndNuevoUsado", rec.IndNuevoUsado, "N"},
		{"PersonaFisicaJurid", rec.PersonaFisicaJurid, "D"},
		{"CodigoITV", rec.CodigoITV, "E12000456"},
		{"Servicio", rec.Servicio, "A00"},
		{"CodMunicipioINE", rec.CodMunicipioINE, "28079"},
		{"Municipio", rec.Municipio, "MADRID"},
		{"PotenciaKW", rec.PotenciaKW, 125.0},
		{"NumPlazasMax", rec.NumPlazasMax, 5},
		{"CO2GPerKm", rec.CO2GPerKm, 185},
		{"TipoITV", rec.TipoITV, "TURISMO"},
		{"VarianteITV", rec.VarianteITV, "V1"},
		{"VersionITV", rec.VersionITV, "2.0 TDI 4MOTION"},
		{"FabricanteITV", rec.FabricanteITV, "VOLKSWAGEN AG"},
		{"MasaOrdenMarchaKg", rec.MasaOrdenMarchaKg, 1700},
		{"MasaMaxTecnicaKg", rec.MasaMaxTecnicaKg, 2300},
		{"CatHomologacionUE", rec.CatHomologacionUE, "M1"},
		{"Carroceria", rec.Carroceria, "AC"},
		{"NivelEmisionesEURO", rec.NivelEmisionesEURO, "EURO5"},
		{"DistanciaEjes12Mm", rec.DistanciaEjes12Mm, 2604},
		{"ViaAnteriorMm", rec.ViaAnteriorMm, 1540},
		{"ViaPosteriorMm", rec.ViaPosteriorMm, 1565},
		{"TipoAlimentacion", rec.TipoAlimentacion, "M"},
		{"ContrasenaHomolog", rec.ContrasenaHomolog, "E12*0048*01"},
	}
	for _, c := range checks {
		if fmt.Sprint(c.got) != fmt.Sprint(c.want) {
			t.Errorf("%s = %v, want %v", c.name, c.got, c.want)
		}
	}

	if rec.FecMatricula.IsZero() {
		t.Errorf("FecMatricula should parse DDMMYYYY")
	}
	if y, m, d := rec.FecMatricula.Date(); y != 2009 || m != 9 || d != 2 {
		t.Errorf("FecMatricula = %v, want 2009-09-02", rec.FecMatricula)
	}
	if rec.VINMasked() {
		t.Errorf("full VIN should not report as masked")
	}
	if rec.VINPrefix() != "WVGZZZ5NZAW" {
		t.Errorf("VINPrefix = %q, want WVGZZZ5NZAW", rec.VINPrefix())
	}
}

func TestParseNumericSentinels(t *testing.T) {
	row := buildRow(t, map[int]string{
		7:  "XXX123YYY456ZZZ78",
		10: "*****", // DGT's "unknown" sentinel
		11: "-",     // another placeholder
		12: "  -  ", // padded placeholder
		32: "",
	})
	rec, err := Parse(row)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if rec.CilindradaCC != 0 {
		t.Errorf("CilindradaCC = %d, want 0 for ***** sentinel", rec.CilindradaCC)
	}
	if rec.PotenciaFiscalCVF != 0 {
		t.Errorf("PotenciaFiscalCVF = %v, want 0 for - sentinel", rec.PotenciaFiscalCVF)
	}
	if rec.TaraKg != 0 {
		t.Errorf("TaraKg = %d, want 0 for blank+dash", rec.TaraKg)
	}
}

func TestParseMaskedVIN(t *testing.T) {
	row := buildRow(t, map[int]string{
		7: "WVGZZZ5NZ**********",
	})
	rec, err := Parse(row)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if !rec.VINMasked() {
		t.Errorf("post-2025 masked VIN should report as masked")
	}
	if rec.VINPrefix() != "WVGZZZ5NZ**" {
		t.Errorf("VINPrefix = %q, want WVGZZZ5NZ**", rec.VINPrefix())
	}
}

func TestParseRejectsShortLine(t *testing.T) {
	_, err := Parse("too short")
	if err == nil {
		t.Fatal("expected error for short line")
	}
}

func TestParseTolerantOfTruncation(t *testing.T) {
	row, _ := fullSampleRow(t)
	// Truncate to 200 bytes — past the VIN but missing most fields.
	truncated := row[:200]
	rec, err := Parse(truncated)
	if err != nil {
		t.Fatalf("parse truncated: %v", err)
	}
	if rec.Bastidor != "WVGZZZ5NZAW021819" {
		t.Errorf("VIN survived truncation: got %q", rec.Bastidor)
	}
	// Fields past the truncation point fall back to zero values.
	if rec.MasaOrdenMarchaKg != 0 {
		t.Errorf("MasaOrdenMarcha = %d, want 0 when row truncated before it", rec.MasaOrdenMarchaKg)
	}
}

func TestFuelTypeLabel(t *testing.T) {
	row := buildRow(t, map[int]string{9: "1"})
	rec, _ := Parse(row)
	if got := rec.FuelTypeLabel(); got != "Diésel" {
		t.Errorf("FuelTypeLabel = %q, want Diésel", got)
	}
}

func TestVehicleTypeLabel(t *testing.T) {
	row := buildRow(t, map[int]string{8: "40"})
	rec, _ := Parse(row)
	if got := rec.VehicleTypeLabel(); got != "Turismo" {
		t.Errorf("VehicleTypeLabel = %q, want Turismo", got)
	}
}

func TestProvinceLabel(t *testing.T) {
	cases := map[string]string{
		"28": "Madrid",
		"08": "Barcelona",
		"46": "Valencia",
		"07": "Illes Balears",
		"zz": "",
	}
	for code, want := range cases {
		if got := ProvinceLabel(code); got != want {
			t.Errorf("ProvinceLabel(%q) = %q, want %q", code, got, want)
		}
	}
}

func TestServicioLabel(t *testing.T) {
	if ServicioLabel("B01") != "Taxi" {
		t.Errorf("B01 should decode to Taxi")
	}
	if ServicioLabel("ZZZ") != "" {
		t.Errorf("unknown code should return empty")
	}
}
