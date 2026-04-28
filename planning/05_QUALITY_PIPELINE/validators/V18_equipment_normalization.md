# V18 — Equipment normalization

## Identificador
- ID: V18, Nombre: Equipment normalization, Severity: INFO
- Phase: Enrichment, Dependencies: ninguna
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Los dealers publican equipamiento en texto libre y en múltiples idiomas: "Climatizador automático", "Automatische Klimaanlage", "Climatisation automatique", "Airco automatisch". V18 normaliza estas cadenas a un vocabulario controlado cross-language — el mismo ítem de equipamiento tiene un único código canónico independientemente del idioma de publicación.

Esto habilita:
1. Filtrado cross-language en búsquedas B2B ("dammi tutti i veicoli con climatizador automático" independientemente de si se publicó en DE, FR o ES)
2. Comparación de equipamiento entre fuentes para V16 (cross-source convergence)
3. Input para modelo de precio hedónico (V13 iteración futura)
4. Renderizado localizado en la ficha del vehículo

V18 es INFO porque la normalización fallida no invalida el vehículo — solo empobrece las capacidades de búsqueda.

## Input esperado
- `record.Equipment []string` — lista de strings de equipamiento extraídos en texto libre
- `record.LanguageDetected` — ISO 639-1 del idioma del listing (si disponible)

## Vocabulario controlado

El vocabulario canónico se organiza en categorías. Cada ítem tiene:
- `code` — identificador canónico estable (e.g. `CLIMATE_AUTO`)
- `category` — categoría (COMFORT, SAFETY, MULTIMEDIA, etc.)
- `display_*` — traducción por idioma para renderizado

```yaml
# Excerpt del vocabulario (completo en /data/equipment_vocabulary.yaml)
- code: CLIMATE_AUTO
  category: COMFORT
  display_de: "Klimaautomatik"
  display_fr: "Climatisation automatique"
  display_es: "Climatizador automático"
  display_nl: "Automatische airco"
  display_en: "Automatic climate control"
  display_it: "Climatizzatore automatico"
  aliases:
    - "automatische klimaanlage"
    - "klimatisierung automatisch"
    - "climatisation bi-zone"       # variante que mapea a mismo código
    - "dual zone climate"
    - "climatizador bizona"
    - "airco automatisch"
    - "automatische airconditioning"

- code: NAVI_INTEGRATED
  category: MULTIMEDIA
  display_de: "Navigationssystem integriert"
  display_fr: "Navigation intégrée"
  display_es: "Navegador integrado"
  aliases:
    - "navi"
    - "navigation"
    - "gps intégré"
    - "sat nav"
    - "navigationssystem"
    - "navegación"

- code: PARKING_REAR_SENSORS
  category: SAFETY
  display_de: "Einparkhilfe hinten"
  display_fr: "Capteurs de stationnement arrière"
  display_es: "Sensores de aparcamiento traseros"
  aliases:
    - "pdc"
    - "park distance control"
    - "aide au stationnement"
    - "einparkhilfe"
    - "parkeerhulp"

# ... ~250 ítems en vocabulario completo
```

## Algoritmo

```go
func (v *V18Validator) Validate(ctx context.Context, record *VehicleRecord, graph *KnowledgeGraph) *ValidationResult {
    if len(record.Equipment) == 0 {
        return skip("V18")
    }

    normalized := []NormalizedEquipmentItem{}
    unrecognized := []string{}

    for _, rawItem := range record.Equipment {
        code, confidence := v.normalizer.Normalize(rawItem)
        if code != "" {
            normalized = append(normalized, NormalizedEquipmentItem{
                Code:           code,
                OriginalText:   rawItem,
                Confidence:     confidence,
                MatchMethod:    v.normalizer.LastMatchMethod(), // "exact", "alias", "fuzzy"
            })
        } else {
            unrecognized = append(unrecognized, rawItem)
        }
    }

    recognitionRate := float64(len(normalized)) / float64(len(record.Equipment))

    // Almacenar output en el registro
    record.EquipmentNormalized = normalized
    record.EquipmentUnrecognized = unrecognized

    annotations := map[string]interface{}{
        "items_total":        len(record.Equipment),
        "items_recognized":   len(normalized),
        "items_unrecognized": len(unrecognized),
        "recognition_rate":   recognitionRate,
    }

    if len(unrecognized) > 0 {
        annotations["unrecognized_items"] = unrecognized
    }

    // Alta recognition rate → pequeño boost de confianza
    if recognitionRate >= 0.80 {
        return &ValidationResult{
            Status:          PASS,
            Severity:        INFO,
            Annotations:     annotations,
            ConfidenceDelta: +0.01,
        }
    }

    // Recognition rate baja → pass pero sin bonus, log para revisión de vocabulario
    return &ValidationResult{
        Status:          PASS,
        Severity:        INFO,
        Annotations:     annotations,
        ConfidenceDelta: 0.0,
    }
}

// Normalizer con tres capas: exact match, alias match, fuzzy match
func (n *EquipmentNormalizer) Normalize(raw string) (code string, confidence float64) {
    normalized := strings.ToLower(strings.TrimSpace(raw))

    // Capa 1: exact match contra display names (multiidioma)
    if code, ok := n.exactIndex[normalized]; ok {
        return code, 1.0
    }

    // Capa 2: alias match (lowercase)
    if code, ok := n.aliasIndex[normalized]; ok {
        return code, 0.95
    }

    // Capa 3: fuzzy match con Levenshtein distance ≤2 sobre alias index
    best, bestDist := "", 3
    for alias, code := range n.aliasIndex {
        dist := levenshteinDistance(normalized, alias)
        if dist < bestDist {
            best, bestDist = code, dist
        }
    }
    if bestDist <= 2 {
        return best, 0.75
    }

    // No match
    return "", 0
}
```

## Vocabulario fuente y mantenimiento

- **Base inicial:** ~250 ítems cubriendo los equipamientos más frecuentes en el mercado EU (basado en análisis de listings de AutoScout24/mobile.de)
- **Ampliación continua:** los ítems `unrecognized` con frecuencia alta (>50 apariciones en 7 días) se añaden semiautomáticamente al vocabulario con validación humana
- **Versionado:** el vocabulario se versiona en `/data/equipment_vocabulary.yaml` con semver; cambios de `code` (renombrado) son breaking changes → incremento de major version

## Librerías y dependencias
- `gopkg.in/yaml.v3` para parseo del vocabulario YAML
- Levenshtein distance implementado en Go puro (stdlib `unicode/utf8`)
- Sin dependencias externas en runtime

## Umbral de PASS
- Siempre PASS (severity INFO — normalización fallida no bloquea publicación)
- Recognition rate ≥80% → +0.01 confidence
- Recognition rate <80% → +0.00 confidence

## Severity y justificación
**INFO** — el equipamiento normalizado es un enriquecimiento de datos que mejora la buscabilidad y la comparación cross-source. Un vehículo con equipamiento no normalizado sigue siendo publicable; solo pierde parte de su discoverabilidad.

## Interacción con otros validators
- V13: en iteración futura, los ítems de equipamiento normalizados serán covariables del modelo de precio
- V16: el output de V18 es comparado entre fuentes para detectar divergencias de equipamiento (iteración futura)
- NLG: el generador de descripciones usa `EquipmentNormalized` para incluir equipamiento en el texto generado

## Tasa de fallo esperada
- N/A — siempre PASS

## Contribution a confidence_score
- PASS (≥80% recognition): +0.01
- PASS (<80% recognition): +0.00

## Riesgos y false positives
- **False positive conceptual:** alias muy corto ("ABS") que colisiona con otro ítem. Mitigación: alias de ≤3 caracteres requieren coincidencia exacta, no fuzzy.
- **Vocabulario incompleto inicial:** en los primeros meses, recognition rate puede ser <80% para dealers de países con convenciones de nomenclatura peculiares (BE/NL). Mitigación: pipeline de retroalimentación de `unrecognized_items` para ampliar vocabulario.

## Iteración futura
- **Modelo de embeddings:** sustituir fuzzy Levenshtein por sentence-transformers multilingual (ONNX INT8) para matching semántico ("asientos calefactados" ↔ "heated seats" ↔ "Sitzheizung")
- **Equipamiento como covariable de precio:** integrar con V13 para ajustar precio esperado según equipamiento (vehículo base vs. full-options)
- **Equipamiento normalizado como filtro de búsqueda:** publicar `EquipmentNormalized` en el índice DuckDB para queries tipo "dame todos los BMW 3 con ACC < 20.000€"
