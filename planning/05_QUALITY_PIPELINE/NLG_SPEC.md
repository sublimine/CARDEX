# NLG Specification — V19 Description Generation

## Identificador
- Documento: NLG_SPEC
- Versión: 1.0
- Fecha: 2026-04-14
- Estado: AUTORITATIVO

## Propósito
Especificación técnica detallada del subsistema de generación de descripciones en lenguaje natural (NLG) que alimenta el validator V19. Las descripciones son el único contenido generativo de CARDEX — el único activo IP propio en términos de texto — y por tanto su calidad determina directamente la percepción del producto.

## Modelo

### Selección
- **Llama 3 8B Instruct** cuantizado **Q4_K_M** via llama.cpp
- Justificación: mejor relación calidad/CPU en la gama 7-8B (superior a Mistral 7B en seguimiento de instrucciones estructuradas según benchmarks comunidad). Q4_K_M punto óptimo de quantization — "pérdida de calidad < 2% vs FP16" es claim de benchmarks comunidad llama.cpp sin fuente primaria citada; hipótesis aceptable pero pendiente validación con el modelo real en hardware target
- Tamaño en disco: ~4.9 GB (GGUF format)
- RAM requerida: ~5-6 GB estimados para el modelo; **VPS CX42 tiene 16 GB RAM** (no 8 GB — la confusión es con el plan CX22). Deja ~10 GB para servicios concurrentes [verificado vs tabla 05_VPS_SPEC.md]
- Velocidad en CPU: ~2-12 tokens/s en Hetzner CX42 (AMD EPYC 4 vCPU) — rango hipotético; 06_STACK_DECISIONS.md estima ~2-8 tok/s. Benchmark propio pendiente post-aprovisionamiento

### Alternativas evaluadas y descartadas
- Mistral 7B: inferior en seguimiento de instrucciones multilingüe
- Phi-3 Mini 3.8B: calidad insuficiente para FR/DE técnico
- Llama 3 70B: incompatible con VPS €0 OPEX
- GPT-4/Claude API: viola R2 (coste operativo) y crea dependencia externa

## Prompt template por idioma

### Patrón estructural común

El prompt tiene siempre dos partes:
1. **System prompt** — rol + restricciones + vocabulario
2. **User prompt** — structured facts del vehículo a describir

```
[SYSTEM]
Eres un redactor especializado en vehículos de ocasión B2B.
Escribe una descripción factual, concisa y profesional del vehículo.
REGLAS ESTRICTAS:
- Solo usa datos proporcionados. NUNCA inventes características no mencionadas.
- Longitud: 80-120 palabras.
- Tono: profesional B2B, neutro, sin superlativos vacíos ("increíble", "espectacular").
- Vocabulario técnico correcto en {idioma}.
- No menciones el nombre del dealer.
- No incluyas precio (lo muestra el sistema).
- Termina con las características de equipamiento más relevantes.

[USER]
Vehículo:
Marca: {make}
Modelo: {model}
Año: {year}
Carrocería: {body_type}
Combustible: {fuel_type}
Transmisión: {transmission}
Potencia: {power_kw} kW ({power_hp} CV)
Kilometraje: {mileage_km:,} km
Color exterior: {color}
Equipamiento destacado: {equipment_top5}

Genera la descripción en {idioma}:
```

### Template ES (Español)

```
[SYSTEM]
Eres un redactor especializado en vehículos de ocasión para el mercado B2B europeo.
Escribe una descripción factual, concisa y profesional del vehículo en español castellano.
REGLAS:
- Solo usa los datos proporcionados. NUNCA inventes ni especules características.
- Longitud: entre 80 y 120 palabras.
- Tono: profesional y neutro. Evita adjetivos vacíos como "impecable", "excelente estado".
- Usa terminología técnica automovilística correcta en español.
- No menciones concesionario, vendedor ni precio.
- Incluye al final las características de equipamiento más relevantes.
```

### Template FR (Français)

```
[SYSTEM]
Vous êtes un rédacteur spécialisé en véhicules d'occasion pour le marché B2B européen.
Rédigez une description factuelle, concise et professionnelle du véhicule en français.
RÈGLES STRICTES:
- Utilisez uniquement les données fournies. N'inventez jamais de caractéristiques.
- Longueur: 80 à 120 mots.
- Ton: professionnel et neutre. Évitez les adjectifs vides ("impeccable", "parfait état").
- Terminologie technique automobile correcte en français.
- Ne mentionnez pas le concessionnaire, le vendeur ni le prix.
- Concluez avec les équipements les plus pertinents.
```

### Template DE (Deutsch)

```
[SYSTEM]
Sie sind ein spezialisierter Texter für Gebrauchtfahrzeuge im europäischen B2B-Markt.
Schreiben Sie eine sachliche, prägnante und professionelle Fahrzeugbeschreibung auf Deutsch.
STRENGE REGELN:
- Verwenden Sie nur die angegebenen Daten. Erfinden Sie niemals Eigenschaften.
- Länge: 80 bis 120 Wörter.
- Ton: professionell und sachlich. Keine leeren Adjektive wie "einwandfrei", "erstklassig".
- Korrekte Kfz-Fachterminologie auf Deutsch.
- Erwähnen Sie weder Händler noch Verkäufer noch Preis.
- Schließen Sie mit den wichtigsten Ausstattungsmerkmalen ab.
```

### Template NL (Nederlands)

```
[SYSTEM]
U bent een gespecialiseerde copywriter voor gebruikte voertuigen op de Europese B2B-markt.
Schrijf een feitelijke, beknopte en professionele voertuigbeschrijving in het Nederlands.
STRENGE REGELS:
- Gebruik alleen de verstrekte gegevens. Verzin nooit eigenschappen.
- Lengte: 80 tot 120 woorden.
- Toon: professioneel en neutraal. Geen lege bijvoeglijke naamwoorden.
- Correcte technische automobielterminologie in het Nederlands.
- Vermeld geen dealer, verkoper of prijs.
- Sluit af met de meest relevante uitrustingskenmerken.
```

### Template EN (English — fallback universal)

```
[SYSTEM]
You are a specialist copywriter for used vehicles in the European B2B market.
Write a factual, concise, and professional vehicle description in English.
STRICT RULES:
- Use only the provided data. Never invent or speculate about features.
- Length: 80 to 120 words.
- Tone: professional and neutral. No empty adjectives.
- Correct automotive technical terminology.
- Do not mention dealer, seller, or price.
- Conclude with the most relevant equipment features.
```

### Template IT (Italiano — dealers fronterizos FR/CH)

```
[SYSTEM]
Siete un copywriter specializzato in veicoli usati per il mercato B2B europeo.
Scrivete una descrizione fattuale, concisa e professionale del veicolo in italiano.
REGOLE RIGOROSE:
- Utilizzate solo i dati forniti. Non inventate mai caratteristiche.
- Lunghezza: 80-120 parole.
- Tono: professionale e neutro. Evitate aggettivi vuoti.
- Terminologia tecnica automobilistica corretta in italiano.
- Non menzionate il concessionario, il venditore né il prezzo.
- Concludete con le caratteristiche di allestimento più rilevanti.
```

## Pipeline de generación

```
1. Enqueue
   VehicleRecord (post-V18) → NATS queue "nlg.pending"
   Priority = f(dealer_importance, vehicle_price)

2. Batch processing (nocturno — 02:00-06:00 UTC)
   Worker Go lee de NATS → construye prompt → llama.cpp CLI subprocess
   Batch size: 50 registros concurrentes en goroutines (limitado por RAM)

3. Post-processing
   a. Length check: 80 ≤ words ≤ 150 (tolerancia 25% sobre target)
   b. Hallucination detection (ver sección)
   c. Grammar check (ver sección)
   d. Tone check (ver sección)
   e. On success: actualizar VehicleRecord.description_generated_ml
   f. On fail: TEMPLATE_FALLBACK (ver sección)

4. Store
   description_generated_ml = texto final
   description_type = "NLG" | "TEMPLATE_FALLBACK"
   description_language = idioma generado
   description_generated_at = timestamp
```

## Hallucination detection

Un "hallucination" en este contexto es cualquier afirmación factual en la descripción que NO está respaldada por los structured facts del input. Es el riesgo más crítico del NLG.

### Método: cross-checking extractivo

```python
def detect_hallucinations(description: str, facts: VehicleFacts) -> List[Hallucination]:
    hallucinations = []

    # 1. Named entity extraction sobre la descripción
    entities = extract_entities(description)  # spaCy NER

    # 2. Para cada entidad de tipo ORG/PRODUCT/NUMBER/DATE:
    for entity in entities:

        # Verificar que la entidad está en los facts
        if entity.type == "MAKE" and entity.text.lower() != facts.make.lower():
            hallucinations.append(Hallucination(
                type="WRONG_MAKE",
                found=entity.text,
                expected=facts.make
            ))

        if entity.type == "MODEL" and not fuzzy_match(entity.text, facts.model):
            hallucinations.append(Hallucination(type="WRONG_MODEL", ...))

        if entity.type == "YEAR":
            year = parse_year(entity.text)
            if abs(year - facts.year) > 0:
                hallucinations.append(Hallucination(type="WRONG_YEAR", ...))

        if entity.type == "NUMBER" and looks_like_mileage(entity.text):
            km = parse_km(entity.text)
            if abs(km - facts.mileage) / facts.mileage > 0.05:
                hallucinations.append(Hallucination(type="WRONG_MILEAGE", ...))

    # 3. Equipment hallucination: equipamiento mencionado no en la lista
    for equipment_mentioned in extract_equipment_mentions(description):
        if not fuzzy_match_any(equipment_mentioned, facts.equipment):
            hallucinations.append(Hallucination(type="INVENTED_EQUIPMENT", ...))

    return hallucinations
```

Si `len(hallucinations) > 0` → re-generación con prompt reforzado (hasta 2 reintentos). Si persiste → TEMPLATE_FALLBACK.

## Grammar check

LanguageTool self-hosted (Docker, ~512 MB RAM):
- Endpoint: `http://localhost:8081/v2/check`
- Input: descripción generada + idioma
- Output: lista de errores gramaticales
- Umbral de aceptación: `grammar_errors < 3 AND no_critical_errors`
- Si falla umbral: re-generación con temperatura reducida (0.3)

## Tone check

Regex patterns de términos prohibidos (inapropiados para B2B):
```
PROHIBIDOS:
  ES: increíble, impecable, perfecto, espectacular, excepcional, oportunidad única
  FR: incroyable, impeccable, parfait, exceptionnel, opportunité unique
  DE: unglaublich, makellos, perfekt, außergewöhnlich, einmalige Gelegenheit
  NL: ongelooflijk, makeloos, perfect, buitengewoon
```

Si alguno aparece → re-generación con temperatura 0.2 y recordatorio explícito en prompt.

## Template fallback

Cuando NLG falla (>2 reintentos sin éxito), el sistema genera una descripción template-based:

```go
func templateDescription(r *VehicleRecord, lang string) string {
    templates := map[string]string{
        "es": "{make} {model} del año {year}. Carrocería {body_type}, motor {fuel_type} de {power_kw} kW. Kilometraje: {mileage:,} km. Transmisión {transmission}. Color {color}. Equipamiento: {equipment_joined}.",
        "fr": "{make} {model} de l'année {year}. Carrosserie {body_type}, moteur {fuel_type} de {power_kw} kW. Kilométrage: {mileage:,} km. Transmission {transmission}. Couleur {color}. Équipements: {equipment_joined}.",
        "de": "{make} {model}, Baujahr {year}. Karosserie {body_type}, Motor {fuel_type} mit {power_kw} kW. Kilometerstand: {mileage:,} km. Getriebe {transmission}. Farbe {color}. Ausstattung: {equipment_joined}.",
        "nl": "{make} {model} uit {year}. Carrosserie {body_type}, motor {fuel_type} met {power_kw} kW. Kilometerstand: {mileage:,} km. Versnellingsbak {transmission}. Kleur {color}. Uitrusting: {equipment_joined}.",
    }
    return format(templates[lang], r)
}
```

La descripción template es factualmente correcta pero no fluida. Se marca `description_type = "TEMPLATE_FALLBACK"` para priorización en human eval.

## Métricas de calidad

### BLEU score automático
- Corpus de referencia: 500 descripciones escritas por humanos por idioma (2 idiomas iniciales: ES, FR)
- Cálculo: sacrebleu contra las referencias
- Target: BLEU ≥ 0.35 (en rango "inteligible y factualmente correcto")
- Medición mensual sobre muestra de 100 descripciones nuevas por idioma

### Human eval mensual
- Muestra estratificada: 50 descripciones por idioma × 4 idiomas = 200/mes
- Evaluadores: freelancers nativos con conocimiento automovilístico
- Escala: 1-5 en 3 dimensiones (facticidad, fluidez, adecuación B2B)
- Target: media ≥ 4.0/5 en todas las dimensiones
- Resultado → input para prompt refinement o fine-tuning futuro

### Tasas operativas
- `nlg_success_rate` — % registros con descripción NLG (vs TEMPLATE_FALLBACK)
- `hallucination_rate` — % primeros intentos con hallucination detectada
- `template_fallback_rate` — % registros que caen a template (target: <5%)
- `grammar_error_rate` — % descripciones con errores gramaticales pre-corrección
- `avg_generation_time_ms` — latencia batch por descripción

## Batch mode — arquitectura

```
[NATS queue "nlg.pending"]
         ↓
[NLG Worker goroutine pool]
  - 3 workers concurrentes (limitado por RAM)
  - cada worker: fetch job → build prompt → llama.cpp subprocess → post-process → ack
         ↓
[llama.cpp subprocess]
  - CLI: `./llama-cli -m llama3-8b-q4_k_m.gguf -p "{prompt}" -n 200 --temp 0.5`
  - stdin/stdout communication
  - Timeout: 30s por descripción (CPU bound)
         ↓
[Post-processor]
  hallucination_check → grammar_check → tone_check → store
         ↓
[vehicle_record UPDATE]
  description_generated_ml = texto
  description_type = "NLG" | "TEMPLATE_FALLBACK"
  validators_passed += "V19"
```

El batch nocturno procesa ~1.000-3.000 descripciones por noche dependiendo de CPU load (hipótesis — depende de throughput real de llama.cpp en CX42; ver 06_STACK_DECISIONS.md). Para el lanzamiento inicial, la latencia entre indexación y descripción disponible puede ser de hasta 24h. Post-madurez, la queue se mantiene con backlog <1h (hipótesis a validar en operación real).
