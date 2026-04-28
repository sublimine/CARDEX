# V14 — VAT mode detection

## Identificador
- ID: V14, Nombre: VAT mode detection, Severity: INFO
- Phase: Price, Dependencies: ninguna
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
CARDEX es una plataforma B2B donde los compradores son profesionales del sector que necesitan el precio neto (sin IVA) para sus decisiones de compra. Sin embargo, los dealers publican precios en distintos formatos: precio con IVA incluido (gross), precio sin IVA (net), o sin indicación clara. V14 detecta el modo IVA del precio y normaliza para asegurar que el campo `PriceNetEUR` es siempre el precio sin IVA — el que el comprador B2B compara.

## Input esperado
- `record.PriceGross` / `record.PriceNet` / `record.VATMode` — campos del extraction
- Contexto textual extraído del listing (título, descripción raw)
- `record.CountryCode` — tasas de IVA varían por país

## Algoritmo

### Paso 1 — Señales explícitas

```go
// Señales de precio neto (sin IVA):
var netSignals = []string{
    "netto", "net", "ht", "hors taxe", "excl. vat", "excl mwst",
    "+ mwst", "+ iva", "+ tva", "+ btw",
    "excl. btw", "precio sin iva", "prix hors tva",
    "zzgl. mwst", "zzgl mwst",
}

// Señales de precio bruto (con IVA):
var grossSignals = []string{
    "inkl. mwst", "incl. vat", "ttc", "toutes taxes",
    "tvac", "inclusief btw", "precio con iva",
    "brutto", "gross",
}

// Señales de régimen de margen (B2B impuesto diferencial):
var marginSignals = []string{
    "differential taxation", "differenzbesteuerung", "régime de la marge",
    "margeregeling", "régimen del margen",
}
```

### Paso 2 — Detección heurística por valor del precio

```go
func detectVATMode(price float64, signals []string, countryCode string) VATMode {
    // 1. Señal explícita en el texto
    for _, sig := range netSignals {
        if containsIgnoreCase(text, sig) { return VAT_NET }
    }
    for _, sig := range grossSignals {
        if containsIgnoreCase(text, sig) { return VAT_GROSS }
    }

    // 2. Heurística por terminación del precio
    // Precios gross frecuentemente terminan en .00 o .99
    // Precios net frecuentemente tienen céntimos irregulares (21% IVA de 28500 = 23401.24)
    frac := math.Mod(price, 1000)
    if frac == 0.0 || frac == 990.0 || frac == 995.0 {
        // Posiblemente gross (precio redondo)
        return VAT_GROSS_PROBABLE
    }

    // 3. Default por país (algunos países publican convenciones distintas)
    // DE/AT: convención = precio neto para B2B
    // FR/BE: convención = precio TTC o HT indicado
    // ES: convención = precio con IVA (PVP)
    switch countryCode {
    case "DE": return VAT_NET_PROBABLE
    case "ES", "FR": return VAT_GROSS_PROBABLE
    default: return VAT_UNKNOWN
    }
}
```

### Paso 3 — Conversión net↔gross

```go
// Tasas de IVA estándar por país (vehículos de ocasión)
var vatRates = map[string]float64{
    "DE": 0.19, "FR": 0.20, "ES": 0.21,
    "BE": 0.21, "NL": 0.21, "CH": 0.077, // IVA reducido CH
}

func computeNetPrice(grossPrice float64, countryCode string) float64 {
    rate := vatRates[countryCode]
    return grossPrice / (1 + rate)
}
```

## Librerías y dependencias
- Lógica pura Go
- `strings` stdlib para pattern matching
- `math` stdlib para cálculo

## Umbral de PASS
- V14 siempre PASS (severity INFO — no bloquea ni penaliza)
- El output es siempre una annotation con `vat_mode_detected` y `price_net_eur_computed`

## Severity y justificación
**INFO** — la detección de modo IVA es un enriquecimiento del dato, no una validación de error. Si la detección es incierta, el campo se marca `VAT_UNKNOWN` y el buyer lo verá.

## Interacción con otros validators
- V15: V14 se ejecuta antes de V15 para que V15 tenga el `VATMode` ya determinado
- V13: V13 compara `PriceNetEUR` que V14 + V15 habrán normalizado

## Tasa de fallo esperada
- N/A — siempre PASS con distinto nivel de confianza en la detección

## Action on fail
- No aplica (siempre INFO/PASS)

## Contribution a confidence_score
- +0.01 si detección con alta confianza (señal explícita encontrada)
- +0.00 si detección heurística o UNKNOWN

## Riesgos y false positives
- **False positive:** precio de cuota mensual detectado como precio sin IVA. Mitigación: si price < 2000€ para un vehículo de ocasión → flag `possible_monthly_payment`.
- **Régimen de margen:** vehículos de ocasión bajo régimen diferencial (dealer pagó IVA en la compra y no puede recuperarlo). En este caso el precio es siempre gross pero el IVA no es recuperable por el comprador B2B. Señal especial en el output.

## Iteración futura
- Modelo ML fine-tuned sobre corpus de listings etiquetados manualmente para mejorar detección en casos ambiguos
- Soporte de IVA reducido CH (7.7%) vs standard (8.1% desde 2024) y cambios futuros
