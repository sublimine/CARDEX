# V15 — Currency normalization to EUR

## Identificador
- ID: V15, Nombre: Currency normalization to EUR, Severity: BLOCKING
- Phase: Price, Dependencies: ninguna
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
CARDEX opera en 6 países de los cuales 5 usan EUR y 1 (Suiza) usa CHF. Para que el sistema de comparación de precios, outlier detection (V13) y cross-source convergence (V16) funcionen correctamente, todos los precios deben estar normalizados a EUR. V15 determina la moneda del precio y convierte a EUR si es necesario.

Si la moneda no puede determinarse, el campo de precio no puede publicarse — publicar un precio sin moneda conocida sería engañoso para el comprador B2B.

## Input esperado
- `record.PriceNet`, `record.PriceGross` — valor numérico del precio
- `record.Currency` — ISO 4217 si está disponible en los datos de extraction
- `record.CountryCode` — fuente de default por país

## Algoritmo

```go
func (v *V15Validator) Validate(ctx context.Context, record *VehicleRecord, graph *KnowledgeGraph) *ValidationResult {
    // Sin precio → SKIP (no es obligatorio tener precio para publicar)
    if record.PriceNet == nil && record.PriceGross == nil {
        return skip("V15")
    }

    // 1. Determinar moneda
    currency := determineCurrency(record)
    if currency == "" {
        return failBlocking("V15", "currency_unknown", map[string]interface{}{
            "price_net":    record.PriceNet,
            "country_code": record.CountryCode,
        })
    }

    // 2. Si ya es EUR → normalización trivial
    if currency == "EUR" {
        record.PriceNetEUR = record.PriceNet
        record.PriceGrossEUR = record.PriceGross
        return pass("V15", +0.04)
    }

    // 3. CHF → EUR (único caso no-EUR en los 6 países)
    if currency == "CHF" {
        rate := v.fxRates.GetRate("CHF", "EUR") // tasa diaria
        if rate == 0 {
            return failBlocking("V15", "fx_rate_unavailable", "CHF_EUR")
        }
        if record.PriceNet != nil {
            netEUR := *record.PriceNet * rate
            record.PriceNetEUR = &netEUR
        }
        if record.PriceGross != nil {
            grossEUR := *record.PriceGross * rate
            record.PriceGrossEUR = &grossEUR
        }
        record.Annotations["fx_rate_chf_eur"] = rate
        record.Annotations["fx_date"] = v.fxRates.LastUpdated()
        return pass("V15", +0.04)
    }

    // 4. Moneda desconocida o inesperada (GBP, USD si dealer cross-border)
    return failBlocking("V15", "unsupported_currency", currency)
}

func determineCurrency(record *VehicleRecord) string {
    // Fuente 1: campo Currency explícito
    if record.Currency != nil && *record.Currency != "" {
        return normalizeCurrencyCode(*record.Currency)
    }

    // Fuente 2: símbolo en el texto del precio (€, CHF, Fr.)
    if record.Annotations["price_raw"] != nil {
        raw := record.Annotations["price_raw"].(string)
        if strings.Contains(raw, "€") || strings.Contains(raw, "EUR") { return "EUR" }
        if strings.Contains(raw, "CHF") || strings.Contains(raw, "Fr.") { return "CHF" }
        if strings.Contains(raw, "£") { return "GBP" }
    }

    // Fuente 3: default por país
    switch record.CountryCode {
    case "CH": return "CHF"
    case "DE", "FR", "ES", "BE", "NL": return "EUR"
    }

    return ""
}
```

## Fuente de tipos de cambio

Dos opciones gratuitas:

### Opción A (preferida): ECB XML Feed
```
URL: https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml
Actualización: diaria a las 16h CET
Formato: XML con todos los tipos respecto a EUR
Sin límite de rate
```

### Opción B: fxratesapi.com (free tier)
```
URL: https://fxratesapi.com/v1/latest?currencies=CHF&base=EUR
Free tier: 100 req/día (suficiente para actualización diaria)
```

El servicio descarga el feed ECB diariamente y cachea los rates en SQLite. El pipeline no hace llamadas HTTP en runtime — solo lee de SQLite.

## Librerías y dependencias
- `encoding/xml` stdlib — parsing del feed ECB
- `modernc.org/sqlite` — cache de FX rates
- Sin dependencias externas para el cálculo

## Umbral de PASS
- Moneda determinada y es EUR → PASS trivial
- Moneda determinada, es CHF, FX rate disponible → PASS + campos EUR computados
- Moneda no determinable → FAIL BLOCKING
- FX rate no disponible (servicio ECB caído) → FAIL BLOCKING (con retry antes de declarar fallo)

## Severity y justificación
**BLOCKING** — publicar un precio sin moneda conocida o sin conversión a EUR es un error objetivo que confundiría al comprador B2B. El precio es el dato más crítico en una transacción comercial.

`NextAction: DLQ` — esperar a que el FX rate esté disponible o a que se pueda determinar la moneda.

## Interacción con otros validators
- V13: V13 depende de V15 para comparar precios en EUR
- V16: V16 depende de V15 para comparación cross-source en EUR
- V14: complementario — V14 detecta modo IVA, V15 normaliza moneda

## Tasa de fallo esperada
- Moneda no determinable: ~1% (mayormente dealers CH con precio sin símbolo explícito)
- FX rate no disponible: <0.1% (ECB es muy fiable)

## Action on fail
- `NextAction: DLQ`

## Contribution a confidence_score
- PASS: +0.04
- FAIL: pipeline detiene

## Riesgos y false positives
- **False positive:** dealer suizo que publica en EUR voluntariamente. Mitigación: si `CountryCode=CH` pero Currency explícitamente `EUR` → aceptar como EUR sin conversión.
- **False positive:** FX rate muy volátil (crisis económica). Mitigación: FX rate del día anterior si el actual no está disponible; annotation `fx_rate_date` en el registro para trazabilidad.

## Iteración futura
- Soporte de GBP si CARDEX expande a UK
- Soporte de precios en múltiples monedas simultáneos (algunos dealers CH publican en CHF y EUR)
