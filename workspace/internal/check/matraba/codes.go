package matraba

// Code tables extracted from the MATRABA feed specification
// (`disenoRegistro/vehiculos/matriculaciones/MATRICULACIONES_MATRABA.pdf`).
// Values not present in the published anexos map to the empty string —
// callers should treat an empty label as "unknown".
//
// These tables are the canonical DGT decodings; we keep them in Spanish
// to match the rest of the ES resolver surface (CheckReport localisation
// is handled upstream).

// fuelLabels maps COD_PROPULSION_ITV (anexo 1.3.5) to a human label.
// The underlying field is 1 ASCII character.
var fuelLabels = map[string]string{
	"0": "Gasolina",
	"1": "Diésel",
	"2": "Eléctrico",
	"3": "GLP (gas licuado del petróleo)",
	"4": "GNC (gas natural comprimido)",
	"5": "GNL (gas natural licuado)",
	"6": "Etanol / flex-fuel",
	"7": "Hidrógeno",
	"8": "Híbrido enchufable gasolina-eléctrico",
	"9": "Híbrido no enchufable gasolina-eléctrico",
	"A": "Híbrido enchufable diésel-eléctrico",
	"B": "Híbrido no enchufable diésel-eléctrico",
	"C": "Bifuel gasolina + GLP",
	"D": "Bifuel gasolina + GNC",
	"E": "Bifuel gasolina + GNL",
	"F": "Otros",
}

// vehicleTypeLabels maps COD_TIPO (anexo 1.3.4) to a human label.
// The underlying field is 2 ASCII digits.
var vehicleTypeLabels = map[string]string{
	"10": "Bicicleta",
	"13": "Ciclomotor",
	"14": "Ciclomotor de tres ruedas",
	"15": "Cuadriciclo ligero",
	"16": "Cuadriciclo",
	"17": "Motocicleta",
	"18": "Motocicleta con sidecar",
	"19": "Triciclo",
	"20": "Vehículo especial",
	"21": "Tractor agrícola",
	"22": "Motocultor",
	"23": "Tractocarro",
	"24": "Remolque agrícola",
	"25": "Maquinaria agrícola automotriz",
	"26": "Maquinaria agrícola remolcada",
	"30": "Camión",
	"31": "Furgón / furgoneta",
	"32": "Tractor de camión",
	"33": "Remolque",
	"34": "Semirremolque",
	"39": "Vehículo articulado",
	"40": "Turismo",
	"41": "Autocaravana",
	"43": "Derivado de turismo",
	"44": "Vehículo mixto adaptable",
	"45": "Vehículo vivienda",
	"50": "Motocicleta (L3e)",
	"60": "Trolebús",
	"70": "Tranvía",
	"80": "Autobús / autocar",
	"90": "Otros vehículos especiales",
}

// provinceLabels maps INE province codes (2 digits) to the canonical
// province/city name. Covers the 50 Spanish provinces plus the
// autonomous cities of Ceuta (51) and Melilla (52).
var provinceLabels = map[string]string{
	"01": "Álava",
	"02": "Albacete",
	"03": "Alicante",
	"04": "Almería",
	"05": "Ávila",
	"06": "Badajoz",
	"07": "Illes Balears",
	"08": "Barcelona",
	"09": "Burgos",
	"10": "Cáceres",
	"11": "Cádiz",
	"12": "Castellón",
	"13": "Ciudad Real",
	"14": "Córdoba",
	"15": "A Coruña",
	"16": "Cuenca",
	"17": "Girona",
	"18": "Granada",
	"19": "Guadalajara",
	"20": "Gipuzkoa",
	"21": "Huelva",
	"22": "Huesca",
	"23": "Jaén",
	"24": "León",
	"25": "Lleida",
	"26": "La Rioja",
	"27": "Lugo",
	"28": "Madrid",
	"29": "Málaga",
	"30": "Murcia",
	"31": "Navarra",
	"32": "Ourense",
	"33": "Asturias",
	"34": "Palencia",
	"35": "Las Palmas",
	"36": "Pontevedra",
	"37": "Salamanca",
	"38": "Santa Cruz de Tenerife",
	"39": "Cantabria",
	"40": "Segovia",
	"41": "Sevilla",
	"42": "Soria",
	"43": "Tarragona",
	"44": "Teruel",
	"45": "Toledo",
	"46": "Valencia",
	"47": "Valladolid",
	"48": "Bizkaia",
	"49": "Zamora",
	"50": "Zaragoza",
	"51": "Ceuta",
	"52": "Melilla",
}

// ServicioLabel decodes the SERVICIO field (3 chars) into a human label.
// Only the codes that appear in production dumps are mapped; unknown
// codes fall through to the empty string.
func ServicioLabel(code string) string {
	switch code {
	case "A00":
		return "Particular"
	case "A01":
		return "Alquiler sin conductor"
	case "A02":
		return "Alquiler con conductor"
	case "A04":
		return "Autoescuela"
	case "B00":
		return "Transporte privado de viajeros"
	case "B01":
		return "Taxi"
	case "B02":
		return "VTC (vehículo con conductor)"
	case "B03":
		return "Ambulancia"
	case "C00":
		return "Transporte público de viajeros"
	case "D00":
		return "Transporte privado de mercancías"
	case "E00":
		return "Transporte público de mercancías"
	case "F00":
		return "Servicios oficiales"
	case "F01":
		return "Policía"
	case "F02":
		return "Bomberos"
	case "F03":
		return "Militar"
	}
	return ""
}

// ElectricCategoryLabel decodes CATEGORIA_VEHICULO_ELECTRICO.
func ElectricCategoryLabel(code string) string {
	switch code {
	case "BEV":
		return "Eléctrico puro"
	case "REEV":
		return "Eléctrico con extensor de autonomía"
	case "PHEV":
		return "Híbrido enchufable"
	case "HEV":
		return "Híbrido no enchufable"
	}
	return ""
}
