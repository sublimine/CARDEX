# V19 — NLG description generation

## Identificador
- ID: V19, Nombre: NLG description generation, Severity: BLOCKING
- Phase: Enrichment, Dependencies: V06 PASS, V15 PASS (opcional), V18 PASS (opcional)
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
CARDEX no copia las descripciones de los dealers — son contenido protegido por derechos de autor. En su lugar, CARDEX genera su propia descripción de cada vehículo basada exclusivamente en los hechos estructurados del registro (make, model, year, mileage, fuel, transmission, equipment normalizado, precio). Esta descripción es contenido original CARDEX, generado localmente sin transmitir datos a servicios externos.

V19 es BLOCKING porque publicar un vehículo sin descripción propia de CARDEX violaría la política editorial de la plataforma — el comprador B2B necesita una descripción neutral y factual generada por CARDEX, no el texto de marketing del dealer.

La especificación completa de NLG (prompt templates, modelo, gramática, detección de alucinaciones) está en `05_QUALITY_PIPELINE/NLG_SPEC.md`.

## Input esperado
- `record.MakeCanonical`, `record.ModelCanonical`, `record.YearCanonical` (de V06)
- `record.Mileage`, `record.FuelType`, `record.Transmission`, `record.PowerKW`
- `record.BodyType`, `record.ColorExterior`
- `record.PriceNetEUR` (de V15, opcional)
- `record.EquipmentNormalized []NormalizedEquipmentItem` (de V18, opcional)
- `record.DealerCountry` → idioma de la descripción (DE→de, FR→fr, ES→es, NL→nl, CH→de)

## Algoritmo de alto nivel

```go
func (v *V19Validator) Validate(ctx context.Context, record *VehicleRecord, graph *KnowledgeGraph) *ValidationResult {
    // 1. Construir facts struct desde el registro
    facts := v.buildFacts(record)

    // 2. Determinar idioma objetivo
    lang := v.resolveLanguage(record.DealerCountry)

    // 3. Intentar generación LLM (Llama 3 8B Q4_K_M via llama.cpp)
    desc, method, err := v.generate(ctx, facts, lang)
    if err == nil && desc != "" {
        // 4. Validar descripción generada
        if validationErr := v.validateOutput(desc, facts); validationErr != nil {
            // Alucinación detectada → fallback a template
            desc, method = v.templateFallback(facts, lang), "TEMPLATE_FALLBACK"
            record.Annotations["nlg_hallucination_detected"] = validationErr.Error()
        }

        // 5. Grammar check via LanguageTool self-hosted
        if grammarIssues := v.grammarCheck(desc, lang); len(grammarIssues) > 0 {
            // Intentar corrección automática; si falla → template fallback
            corrected, err := v.correctGrammar(desc, grammarIssues)
            if err != nil {
                desc, method = v.templateFallback(facts, lang), "TEMPLATE_FALLBACK"
            } else {
                desc = corrected
            }
        }

        record.DescriptionGeneratedML = &desc
        record.DescriptionType = method        // "LLM_GENERATED" | "TEMPLATE_FALLBACK"
        record.DescriptionLanguage = lang
        record.DescriptionGeneratedAt = time.Now()

        return &ValidationResult{
            Status:   PASS,
            Severity: BLOCKING,
            Annotations: map[string]interface{}{
                "description_type":     method,
                "description_language": lang,
                "description_length":   len(desc),
                "facts_used":           facts.FieldCount(),
            },
            ConfidenceDelta: confidenceDeltaForMethod(method),
        }
    }

    // 6. LLM no disponible (timeout, OOM, error de contexto) → template fallback obligatorio
    desc = v.templateFallback(facts, lang)
    if desc == "" {
        // Template también falló (facts insuficientes) → FAIL BLOCKING
        return failBlocking("V19", "insufficient_facts_for_template", map[string]interface{}{
            "facts_available": facts.FieldCount(),
            "minimum_required": 3, // make + model + year mínimo
        })
    }

    record.DescriptionGeneratedML = &desc
    record.DescriptionType = "TEMPLATE_FALLBACK"
    record.DescriptionLanguage = lang

    return &ValidationResult{
        Status:   PASS,
        Severity: BLOCKING,
        Annotations: map[string]interface{}{
            "description_type":     "TEMPLATE_FALLBACK",
            "description_language": lang,
            "llm_error":            err.Error(),
        },
        ConfidenceDelta: +0.01, // template es menos valioso que LLM
    }
}
```

## Construcción de facts

```go
type DescriptionFacts struct {
    Make            string
    Model           string
    Year            int
    Mileage         *int     // km
    FuelType        *string
    Transmission    *string
    PowerKW         *int
    BodyType        *string
    ColorExterior   *string
    PriceNetEUR     *float64
    Equipment       []string // display names localizados del vocabulario V18
}

func (v *V19Validator) buildFacts(record *VehicleRecord) DescriptionFacts {
    facts := DescriptionFacts{
        Make:  safeStr(record.MakeCanonical),
        Model: safeStr(record.ModelCanonical),
        Year:  safeInt(record.YearCanonical),
    }
    // ... población desde campos del registro
    // Equipment: usar display_* del idioma objetivo de V18.NormalizedEquipmentItem
    return facts
}
```

## Prompt template (referencia — ver NLG_SPEC.md para templates completos)

```
[SYSTEM]
Eres un redactor de fichas técnicas de vehículos de ocasión para compradores
profesionales B2B. Genera una descripción factual en {LANG} basada ÚNICAMENTE
en los datos proporcionados. No inventes especificaciones. No uses lenguaje
de marketing. Máximo 120 palabras.

[USER]
Vehículo: {MAKE} {MODEL} ({YEAR})
Kilometraje: {MILEAGE} km
Motor: {FUEL_TYPE}, {POWER_KW} kW
Transmisión: {TRANSMISSION}
Equipamiento: {EQUIPMENT_LIST}

Genera una descripción neutral y factual para un comprador profesional.
```

## Detección de alucinaciones

El output del LLM se valida contra los facts de entrada:

```go
func (v *V19Validator) validateOutput(desc string, facts DescriptionFacts) error {
    // Extraer entidades numéricas del output
    mentionedYears   := extractYears(desc)
    mentionedPowers  := extractKW(desc)
    mentionedMileage := extractMileage(desc)

    // Verificar que no mencionan valores que no están en los facts
    for _, year := range mentionedYears {
        if math.Abs(float64(year - facts.Year)) > 1 {
            return fmt.Errorf("hallucinated year: %d (facts: %d)", year, facts.Year)
        }
    }
    for _, kw := range mentionedPowers {
        if facts.PowerKW != nil && math.Abs(float64(kw - *facts.PowerKW)) > 5 {
            return fmt.Errorf("hallucinated power: %d kW (facts: %d)", kw, *facts.PowerKW)
        }
    }
    // ... verificaciones adicionales para mileage, precio
    return nil
}
```

## Template fallback

Cuando el LLM no está disponible o produce output inválido, se usa un template determinístico:

```go
// Template DE (ejemplo)
const templateDE = `{{.Year}} {{.Make}} {{.Model}}` +
    `{{if .Mileage}}, {{.Mileage}} km{{end}}` +
    `{{if .FuelType}}, {{.FuelType}}{{end}}` +
    `{{if .Transmission}}, {{.Transmission}}{{end}}` +
    `{{if .PowerKW}}, {{.PowerKW}} kW{{end}}` +
    `{{if .Equipment}}. Ausstattung: {{join .Equipment ", "}}{{end}}.`
```

El template garantiza una descripción mínima incluso cuando make + model + year son los únicos facts disponibles.

## Procesamiento asíncrono (NATS batch queue)

La generación NLG es costosa (Llama 3 8B ~2-8 segundos por descripción en CPU). El pipeline no espera síncronamente:

1. V19 verifica si ya existe una descripción válida en el registro → si sí, PASS inmediato
2. Si no existe, publica el job en la cola NATS `nlg.generate.{priority}`
3. El registro se marca como `PENDING_NLG` y se almacena en estado intermedio
4. El worker NLG (proceso nocturno separado) consume la cola y actualiza el registro
5. El registro no es publicado hasta que `DescriptionGeneratedML` está poblado

```go
// Flujo asíncrono simplificado
if record.DescriptionGeneratedML != nil && record.DescriptionType != "" {
    // Descripción ya generada por worker nocturno → validar y PASS
    return v.validateExistingDescription(record)
}

// Descripción pendiente → encolar
priority := v.computePriority(record) // por importancia del dealer
v.natsQueue.Publish("nlg.generate."+priority, record.VehicleID)
record.Status = "PENDING_NLG"
return &ValidationResult{Status: SKIP, NextAction: DEFER}
```

## Librerías y dependencias
- `llama.cpp` Go bindings (CGO) — inferencia local Llama 3 8B Q4_K_M
- `nats.go` — cola de procesamiento asíncrono
- LanguageTool self-hosted (REST API local puerto 8010) — grammar check
- `text/template` stdlib — template fallback
- Sin llamadas a APIs externas de LLM

## Umbral de PASS
- Descripción LLM generada sin alucinaciones + grammar OK → PASS +0.03
- Descripción LLM con corrección gramatical → PASS +0.02
- Template fallback con facts suficientes → PASS +0.01
- Facts insuficientes (sin make/model/year) → FAIL BLOCKING → DLQ

## Severity y justificación
**BLOCKING** — CARDEX no puede publicar un vehículo sin descripción propia. La descripción original es el principal valor añadido editorial de CARDEX (no copia el contenido del dealer). Un registro sin descripción no está listo para publicación.

## Interacción con otros validators
- V06: dependency — la descripción usa make/model/year canónico de V06
- V15: opcional — el precio normalizado puede incluirse en la descripción si disponible
- V18: opcional — el equipamiento normalizado alimenta la lista de features en la descripción
- V20: V20 usa la descripción generada como parte del coherence check final

## Tasa de fallo esperada
- Facts insuficientes: <1% (V06 BLOCKING garantiza make+model+year)
- Template fallback activado (LLM no disponible): variable según disponibilidad del worker

## Action on fail
- `NextAction: DLQ` si facts insuficientes

## Contribution a confidence_score
- PASS (LLM): +0.03
- PASS (LLM + corrección gramatical): +0.02
- PASS (template): +0.01
- FAIL: pipeline detiene

## Riesgos y false positives
- **Alucinación no detectada:** el LLM inventa un equipamiento no listado en los facts. Mitigación: la lista de checks de alucinación cubre valores numéricos (año, km, kW, precio) y nombres canónicos de make/model.
- **Template demasiado corto:** descripción de solo "2019 BMW 3er" sin detalles. Mitigación: el template fallback requiere mínimo 3 campos; si solo hay make+model+year, la descripción se genera pero recibe baja confianza.
- **Idioma incorrecto:** dealer CH registrado en DE pero con listing en FR. Mitigación: si `LanguageDetected` del listing difiere del idioma por defecto del país, usar `LanguageDetected`.

## AI Act Compliance (Art. 50 Reg. UE 2024/1689)

A partir del 2 de agosto de 2026, el AI Act exige que el contenido generado por IA sea identificable como tal mediante metadata machine-readable + disclosure visible al usuario final.

### Implementación obligatoria

1. **Metadata structured en el output del NLG**:
```json
{
  "description_text": "...",
  "ai_disclosure": {
    "generated_by_ai": true,
    "model_name": "Llama-3-8B-Instruct",
    "model_provider": "Meta",
    "model_quantization": "Q4_K_M",
    "training_cutoff_date": "2023-12",
    "generation_timestamp": "ISO 8601",
    "facts_source": "structured_data_from_validators_V01_to_V18",
    "post_edit": "LanguageTool grammar check + hallucination filter"
  }
}
```

2. **Persistencia en `vehicle_record`**: añadir columna `description_ai_disclosure_json TEXT NOT NULL DEFAULT '{}'` en migration v4.

3. **Disclosure UI obligatorio en terminal buyer**: badge "Descripción generada por IA" visible junto al texto. Tooltip con detalles del modelo bajo demanda.

4. **Auditoría externa**: cada release del modelo NLG documentada en `planning/00_AUDIT/AI_ACT/model_release_log.md` (crear).

5. **Hallucination rate metric**: exposición vía Prometheus `cardex_nlg_hallucination_rate{model_version}` con alerta si >0.5%.

### Excepción
Si el operador decide migrar a un modelo proprietary (ej. API third-party con disclosure equivalente), el campo `model_name` se actualiza pero la estructura del disclosure se mantiene.

### Penalty
Incumplimiento Art. 50: hasta 6% del turnover anual o €30M (lo mayor). Aplica desde 2 agosto 2026.

## Iteración futura
- Soporte de generación multilingüe simultánea (una descripción por idioma por registro)
- Fine-tuning de Llama 3 8B sobre corpus de descripciones de vehículos profesionales verificadas
- A/B test de descripción LLM vs template para medir impacto en CTR del comprador B2B
