# V04 — Title NLP make/model inference

## Identificador
- ID: V04, Nombre: Title NLP make/model inference, Severity: WARNING
- Phase: Convergence, Dependencies: ninguna (corre en paralelo con V02/V03)
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
El título de un listing ("BMW 320d xDrive 2021 Automatik 45.000km") contiene la señal más directa del vendedor sobre qué vehículo ofrece. Es independiente del VIN (que puede estar ausente) y del decodificador (que puede fallar en WMIs europeos). V04 extrae Make/Model/Year del título usando NLP multilingüe, proporcionando un tercer vector de identidad para V06.

La ventaja de V04 es su independencia: no depende de ningún decodificador externo, funciona para cualquier idioma, y captura correctamente los modelos EU-only que vPIC puede desconocer.

## Input esperado
- `record.VIN.Title` o título del listing extraído por el extraction pipeline (campo `AdditionalFields["title"]`)
- Fallback: `record.Model` combinado con `record.Make` si ya están extraídos por la estrategia

## Algoritmo

### Paso 1 — Diccionario de marcas y modelos

```python
# Diccionario propio: marca → lista de modelos
# Compilado de múltiples fuentes open-source + manual
CAR_DICTIONARY = {
    "volkswagen": ["golf", "polo", "passat", "tiguan", "touareg", "sharan", "caddy", "t-roc", "t-cross", "id.3", "id.4"],
    "bmw": ["1 series", "2 series", "3 series", "4 series", "5 series", "7 series", "x1", "x3", "x5", "x6", "m3", "m5"],
    "mercedes": ["a-class", "b-class", "c-class", "e-class", "s-class", "glc", "gle", "glb", "cla", "amg"],
    "renault": ["clio", "megane", "kadjar", "captur", "trafic", "master", "zoe", "arkana"],
    "peugeot": ["208", "308", "3008", "508", "5008", "2008", "partner", "expert"],
    "ford": ["fiesta", "focus", "puma", "kuga", "explorer", "transit", "ranger"],
    # ... ~60 marcas × ~15 modelos promedio = ~900 entries
}

# Aliases y variantes (manejo de typos y nombres abreviados)
MAKE_ALIASES = {
    "vw": "volkswagen", "benz": "mercedes", "merc": "mercedes",
    "MB": "mercedes", "Alfa": "alfa romeo", "2CV": "citroen",
    "seat": "seat", "skoda": "skoda", "cupra": "cupra"
}
```

### Paso 2 — spaCy multilingüe

```python
import spacy

# Modelo multilingüe: spacy.load("xx_ent_wiki_sm")
# Detecta entidades en DE/FR/ES/NL/EN/IT sin modelo por idioma
nlp = spacy.load("xx_ent_wiki_sm")

def extract_make_model_year(title: str, lang: str = "auto") -> VehicleIdentity:
    # Normalización
    title_lower = title.lower().strip()

    # 1. Búsqueda de marca (priority: diccionario propio > NER)
    make = None
    for canonical_make, aliases in ALL_MAKES.items():
        if any(alias in title_lower for alias in aliases):
            make = canonical_make
            break

    # 2. NER spaCy como fallback para marcas no en diccionario
    if make is None:
        doc = nlp(title)
        for ent in doc.ents:
            if ent.label_ in ("ORG", "PRODUCT") and is_car_brand(ent.text):
                make = normalize_make(ent.text)
                break

    # 3. Búsqueda de modelo (solo si se encontró la marca)
    model = None
    if make:
        for m in CAR_DICTIONARY.get(make, []):
            if m in title_lower:
                model = m
                break

    # 4. Año: regex sobre 4 dígitos en rango razonable
    year_match = re.search(r'\b(19[8-9]\d|20[0-2]\d)\b', title)
    year = int(year_match.group(0)) if year_match else None

    return VehicleIdentity(make=make, model=model, year=year, source="V04_NLP")
```

## Librerías y dependencias
- `spacy` (Python, `xx_ent_wiki_sm` modelo multilingüe ~50 MB)
- Diccionario propio `assets/car_dictionary.yaml` (~200 KB)
- `regex` (stdlib Python)
- Módulo Go wrapper: `services/pipeline/quality/validators/v04_title_nlp/` → subprocess Python

## Umbral de PASS
- Make extraída del título con confianza > 0.7 → PASS
- Make extraída pero no coincide con `record.Make` (si presente) → FAIL WARNING
- Make no extraíble del título → SKIP (título no informativo para esta validación)

## Severity y justificación
**WARNING** — el título puede ser truncado, en idioma desconocido, o con abreviaturas no estándar. La no extracción de Make del título no implica que el registro sea incorrecto.

## Interacción con otros validators
- V06: V04 aporta el tercer vector de identidad (junto a V02, V03, V05)
- V05: complementario — V04 usa texto, V05 usa imagen

## Tasa de fallo esperada
- SKIP (título no informativo): ~10% (títulos muy cortos o sin marca explícita)
- FAIL WARNING (divergencia título vs campos extraídos): ~5%

## Action on fail
- `NextAction: CONTINUE`

## Contribution a confidence_score
- PASS: +0.04
- FAIL: -0.04
- SKIP: +0.00

## Riesgos y false positives
- **False positive:** "Ford Transit" detectado como Make=Ford cuando en realidad es un rebadging local con otra marca. Mitigación: el diccionario de modelos por marca evita mayoría de casos.
- **False positive:** títulos que incluyen el nombre del dealer que coincide con una marca ("BMW Autohaus München" → Make=BMW correcto accidentalmente). Mitigación: el NER spaCy distingue ORG (concesionario) de PRODUCT (marca).

## Iteración futura
- Fine-tuning del modelo spaCy sobre corpus de títulos dealer europeos anotados
- Soporte de títulos en húngaro, polaco (para dealers fronterizos)
- Auto-expansión del diccionario de marcas/modelos cuando aparecen nuevos WMIs en V02/V03
