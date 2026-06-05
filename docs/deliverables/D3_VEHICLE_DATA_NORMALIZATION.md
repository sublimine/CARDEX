# CARDEX — Vehicle Data Normalization Framework

**Version:** 1.0
**Date:** 2026-06-05
**Classification:** Internal — Technical
**Scope:** Normalization of vehicle listing data extracted from 84+ portals across DE, ES, FR, NL, BE, CH
**Related code:** `quality/internal/validator/`, extraction strategies E01–E13

---

## 1. The Problem

CARDEX extracts vehicle listings from 84+ portals in 6 countries. Each portal uses its own taxonomy, language, units, and conventions. Without normalization, the same vehicle appears as incomparable entries:

| Field | mobile.de (DE) | leboncoin.fr (FR) | coches.net (ES) | 2dehands.be (NL/FR) |
|-------|---------------|-------------------|-----------------|---------------------|
| Make | BMW | Bmw | BMW | BMW |
| Model | 3er | Série 3 | Serie 3 | 3 Reeks |
| Fuel | Diesel | Diesel | Diésel | Diesel |
| Transmission | Automatik | Automatique | Automático | Automaat |
| Color | Saphirschwarz | Noir saphir | Negro zafiro | Saffierblauw |
| Mileage | 45.000 km | 45 000 km | 45.000 km | 45.000 km |
| Price | €22.500 | 22 500 € | 22.500 € | €22.500 |

The normalization framework converts all of these into a single canonical representation that enables cross-border comparison, deduplication, and pricing analytics.

---

## 2. Canonical Schema

Every vehicle listing, after normalization, conforms to this schema:

```
NormalizedVehicle {
    // Identity
    listing_id:         UUID (CARDEX-generated)
    source_url:         string (original listing URL)
    source_portal:      string (portal identifier, e.g., "mobile_de")
    source_country:     enum {DE, ES, FR, NL, BE, CH}
    fingerprint_sha256: string (dedup key)

    // Vehicle identification
    vin:                string | null (17-char, Luhn-validated by V01)
    canonical_make:     string (from make_taxonomy)
    canonical_model:    string (from model_taxonomy)
    variant:            string | null (e.g., "320d", "2.0 TDI")
    generation:         string | null (e.g., "G20", "8V")

    // Specifications
    year:               int (4-digit, validated by V09: 1980–current+1)
    mileage_km:         int (always kilometers, validated by V08)
    fuel_type:          enum {petrol, diesel, electric, hybrid_petrol, hybrid_diesel, plugin_hybrid, lpg, cng, hydrogen, other}
    transmission:       enum {manual, automatic, semi_automatic}
    body_type:          enum {sedan, wagon, hatchback, suv, coupe, convertible, van, pickup, minivan, other}
    drive_type:         enum {fwd, rwd, awd, 4wd} | null
    doors:              int | null
    seats:              int | null
    power_kw:           int | null (always kilowatts)
    power_hp:           int | null (derived: kw × 1.35962)
    displacement_cc:    int | null (cubic centimeters)
    color:              enum {black, white, silver, grey, blue, red, green, brown, beige, yellow, orange, gold, purple, other}
    emission_class:     enum {euro1, euro2, euro3, euro4, euro5, euro6, euro6d, euro6d_temp, euro7} | null

    // Commercial
    price_eur:          decimal (always EUR, converted if necessary)
    price_original:     decimal (original currency amount)
    currency_original:  enum {EUR, CHF, GBP}
    price_type:         enum {asking, negotiable, fixed, auction}
    vat_deductible:     bool | null
    dealer_id:          string (CARDEX-generated dealer identifier)
    dealer_name:        string
    dealer_country:     enum {DE, ES, FR, NL, BE, CH}
    dealer_city:        string | null

    // Metadata
    first_seen:         timestamp
    last_seen:          timestamp
    listing_status:     enum {active, sold, expired, removed}
    quality_score:      float (0.0–1.0, from V20 composite scorer)
    quality_verdict:    enum {PUBLISH, MANUAL_REVIEW, REJECT}
}
```

---

## 3. Make/Model Normalization

### 3.1 Problem

The same make/model combination appears in dozens of variations across portals and languages:

- "Volkswagen" vs "VW" vs "V.W."
- "3er" (DE) vs "Série 3" (FR) vs "Serie 3" (ES) vs "3 Reeks" (NL) vs "3 Series" (EN)
- "Golf GTI" vs "Golf 8 GTI" vs "Golf VIII GTI" vs "Golf GTI 8"
- "Mercedes-Benz" vs "Mercedes" vs "MB"

### 3.2 Solution: Two-Level Taxonomy

**Level 1 — Make normalization:**

A canonical make dictionary maps all known variants to a single canonical form:

```
make_aliases = {
    "Volkswagen": ["VW", "V.W.", "Volks Wagen", "volkswagen"],
    "Mercedes-Benz": ["Mercedes", "MB", "Merc", "Mercedes Benz"],
    "BMW": ["Bmw", "B.M.W.", "Bayerische Motoren Werke"],
    "Citroën": ["Citroen", "CITROEN", "Citröen"],
    "SEAT": ["Seat", "S.E.A.T."],
    "Škoda": ["Skoda", "SKODA"],
    // ~120 makes with all known aliases
}
```

Matching strategy: case-insensitive, diacritics-normalized (NFD → strip combining marks → NFC), Levenshtein distance ≤ 2 for fuzzy matching on unrecognized makes.

**Level 2 — Model normalization:**

Per-make model dictionaries map portal-specific names to canonical model names:

```
model_aliases["BMW"] = {
    "3 Series": ["3er", "Série 3", "Serie 3", "3 Reeks", "3-Series", "3 Serie"],
    "5 Series": ["5er", "Série 5", "Serie 5", "5 Reeks", "5-Series", "5 Serie"],
    "X3": ["X 3", "X-3"],
    "iX": ["iX xDrive40", "iX xDrive50"],  // variant → parent model
    // ...
}
```

**Variant extraction:** After canonical model identification, the remaining text is parsed as variant:
- "BMW 320d xDrive" → make: BMW, model: 3 Series, variant: 320d xDrive
- "Volkswagen Golf 8 GTI" → make: Volkswagen, model: Golf, variant: 8 GTI

### 3.3 Implementation

The existing V04 validator (NLP make/model consistency check) performs basic validation. The normalization layer extends this:

1. **Pre-processing:** Strip HTML entities, normalize whitespace, normalize diacritics
2. **Make lookup:** Exact match → alias match → fuzzy match (Levenshtein ≤ 2) → UNKNOWN
3. **Model lookup:** Against make-specific dictionary. Same fallback chain.
4. **Variant extraction:** Regex patterns for power indicators (320d, 2.0 TDI, 150 CV), trim levels (Comfortline, AMG, M Sport)
5. **Confidence scoring:** exact=1.0, alias=0.95, fuzzy=0.7, UNKNOWN=0.0. Score < 0.7 → flag for manual review

### 3.4 Coverage Target

| Country | Estimated portal make/model variants | Target normalization rate |
|---------|--------------------------------------|--------------------------|
| DE | ~8,000 (mobile.de alone has extensive taxonomy) | 95%+ |
| FR | ~6,000 | 93%+ |
| ES | ~5,000 | 93%+ |
| NL | ~4,000 | 95%+ |
| BE | ~5,000 (dual FR/NL) | 90%+ |
| CH | ~5,000 (DE/FR/IT variants) | 90%+ |

---

## 4. Fuel Type Normalization

### 4.1 Mapping Table (6 languages → canonical enum)

| Canonical | DE | FR | ES | NL | BE (FR) | CH (DE/FR) |
|-----------|-----|-----|-----|-----|---------|------------|
| petrol | Benzin | Essence | Gasolina | Benzine | Essence | Benzin / Essence |
| diesel | Diesel | Diesel | Diésel, Diesel | Diesel | Diesel | Diesel |
| electric | Elektro | Électrique | Eléctrico | Elektrisch | Électrique | Elektro / Électrique |
| hybrid_petrol | Hybrid (Benzin/Elektro) | Hybride essence | Híbrido gasolina | Hybride benzine | Hybride essence | Hybrid |
| hybrid_diesel | Hybrid (Diesel/Elektro) | Hybride diesel | Híbrido diésel | Hybride diesel | Hybride diesel | Hybrid diesel |
| plugin_hybrid | Plug-in-Hybrid | Hybride rechargeable | Híbrido enchufable | Plug-in hybride | Hybride rechargeable | Plug-in-Hybrid |
| lpg | Autogas (LPG) | GPL | GLP | LPG | GPL | LPG/GPL |
| cng | Erdgas (CNG) | GNV | GNC | CNG / Aardgas | GNC | CNG |
| hydrogen | Wasserstoff | Hydrogène | Hidrógeno | Waterstof | Hydrogène | Wasserstoff |

### 4.2 Ambiguity Resolution

- "Hybrid" without qualifier → inspect model database: if model is known to be petrol hybrid (e.g., Toyota Prius) → `hybrid_petrol`; if known diesel hybrid (e.g., Peugeot 3008 HDi Hybrid) → `hybrid_diesel`; otherwise → `hybrid_petrol` (default, as 85%+ of hybrids are petrol-based)
- "Electrique" can mean BEV or PHEV on some portals → cross-reference with displacement_cc: if displacement > 0 → `plugin_hybrid`; if displacement = 0 or null → `electric`

---

## 5. Transmission Normalization

| Canonical | DE variants | FR variants | ES variants | NL variants |
|-----------|------------|------------|------------|------------|
| manual | Schaltgetriebe, Manuell, Handschaltung | Manuelle, Boîte manuelle | Manual, Mecánica | Handgeschakeld, Manueel |
| automatic | Automatik, Automatisch, Automatikgetriebe | Automatique, BVA, Boîte auto | Automático, Automática | Automaat, Automatisch |
| semi_automatic | Halbautomatik, DSG, PDK, SMG | Semi-automatique, Robotisée | Semiautomático, Secuencial | Semi-automaat |

**Special cases:** DSG, PDK, S-tronic, Tiptronic, SMG → `semi_automatic` (technically automated manual transmissions, distinct from torque-converter automatics, but for market comparison purposes grouped as semi_automatic).

---

## 6. Color Normalization

Vehicle colors are the most linguistically diverse field. Portals use manufacturer-specific color names ("Saphirschwarz Metallic", "Noir Saphir Métal", "Gris Artense") that must map to base colors.

### 6.1 Approach

Two-pass normalization:

**Pass 1 — Keyword extraction:** Strip modifiers (Metallic, Métallisé, Mate, Nacré, Perleffekt) and manufacturer prefixes.

**Pass 2 — Base color mapping:**

| Canonical | Keywords (DE) | Keywords (FR) | Keywords (ES) | Keywords (NL) |
|-----------|--------------|--------------|--------------|--------------|
| black | Schwarz, Dunkel | Noir | Negro | Zwart |
| white | Weiß, Weiss | Blanc | Blanco | Wit |
| silver | Silber | Argent, Gris clair | Plata, Plateado | Zilver |
| grey | Grau | Gris | Gris | Grijs |
| blue | Blau | Bleu | Azul | Blauw |
| red | Rot | Rouge | Rojo | Rood |
| green | Grün | Vert | Verde | Groen |
| brown | Braun | Marron, Brun | Marrón | Bruin |
| beige | Beige | Beige | Beige | Beige |
| yellow | Gelb | Jaune | Amarillo | Geel |
| orange | Orange | Orange | Naranja | Oranje |
| gold | Gold | Or, Doré | Dorado, Oro | Goud |
| purple | Violett, Lila | Violet, Pourpre | Morado, Violeta | Paars |

**Ambiguous mappings:** "Saphirschwarz" → black (not blue). "Grigio" → grey. "Anthrazit" → grey. "Champagner" → beige. "Bordeaux" → red. These require a curated exception dictionary per language.

---

## 7. Unit Conversions

### 7.1 Mileage

All mileage stored as kilometers.

| Source unit | Conversion | Where encountered |
|-------------|------------|-------------------|
| km | None | DE, FR, ES, NL, BE, CH (standard) |
| miles | × 1.60934 | UK-imported vehicles listed on EU portals |
| Meilen | × 1.60934 | Rare, Swiss listings for US imports |

### 7.2 Power

All power stored in kW and HP (derived).

| Source unit | Conversion | Where encountered |
|-------------|------------|-------------------|
| kW | None | DE, NL standard |
| PS (Pferdestärke) | × 0.73549875 → kW | DE listings |
| ch (chevaux) | × 0.73549875 → kW | FR listings |
| CV (caballos) | × 0.73549875 → kW | ES listings |
| hp (horsepower) | × 0.745699872 → kW | Rare, UK imports |
| pk (paardenkracht) | × 0.73549875 → kW | NL/BE listings |

Note: PS, ch, CV, and pk are all metric horsepower (identical value). Only imperial hp differs (by ~1.4%).

### 7.3 Currency

All prices stored in EUR.

| Source currency | Conversion method | Where encountered |
|-----------------|-------------------|-------------------|
| EUR | None | DE, FR, ES, NL, BE |
| CHF | ECB daily reference rate | CH portals |

**Exchange rate source:** ECB reference rates (XML feed, updated daily at ~16:00 CET). Cached locally with 24h TTL. For historical analysis, use the rate at `first_seen` date.

**VAT handling:** CARDEX stores the listed price as-is. VAT-deductible status (Differenzbesteuerung in DE, TVA récupérable in FR) is captured as `vat_deductible: bool` when available. No VAT calculation is performed — that requires fiscal knowledge per jurisdiction that CARDEX does not implement.

---

## 8. Cross-Source Deduplication

### 8.1 The Problem

The same vehicle is often listed on multiple portals simultaneously. A dealer in Frankfurt might list their BMW 320d on mobile.de, AutoScout24, and heycar. Without dedup, this creates 3 entries with potentially different prices, photos, and descriptions.

### 8.2 Fingerprint Strategy

V12 (cross-source dedup) uses `fingerprint_sha256` to detect duplicates. The fingerprint is computed from:

```
fingerprint_input = canonical_make + "|" + canonical_model + "|" + variant + "|" + year + "|" + mileage_km_bucket + "|" + dealer_id + "|" + vin (if available)

where mileage_km_bucket = round(mileage_km / 1000) * 1000  // 1000 km granularity to absorb minor differences
```

**If VIN is available:** VIN alone is sufficient for exact dedup. Two listings with the same VIN are the same physical vehicle, regardless of other field differences.

**If VIN is not available (~60% of listings):** The composite fingerprint catches duplicates with high precision. False positive risk: two identical cars from the same dealer with same mileage bucket — rare but possible. Accepted as low risk.

### 8.3 Merge Strategy

When duplicates are detected:
1. Keep all source records (no data loss)
2. Create a canonical record with merged data: take the most complete version of each field
3. Price: keep all prices with timestamps (enables price history across portals)
4. Photos: union of all photo URLs (deduplicated by V16 perceptual hash)
5. Quality score: max(scores) — the best-validated version wins

---

## 9. Quality Validators in the Normalization Pipeline

The following existing validators directly support normalization:

| Validator | Role in normalization |
|-----------|----------------------|
| V01 | VIN format validation — ensures VIN is usable for dedup |
| V04 | NLP make/model consistency — catches gross mismatches (e.g., "BMW" make with "Golf" model) |
| V07 | Price range plausibility — catches conversion errors (e.g., CHF→EUR applied twice) |
| V08 | Mileage range plausibility — catches unit conversion errors (miles not converted) |
| V09 | Year range plausibility — catches OCR/parsing errors |
| V12 | Cross-source dedup — uses normalized fingerprint |
| V13 | Completeness — ensures required normalized fields are populated |
| V18 | Language consistency — flags listings where language doesn't match dealer country |
| V19 | Currency/price validity — catches zero, negative, and unreasonable prices |
| V20 | Composite scorer — final verdict incorporating all normalization quality signals |

---

## 10. Implementation Status and Roadmap

| Component | Status | Priority |
|-----------|--------|----------|
| Make taxonomy (120 makes, all aliases) | Partially implemented in V04 | HIGH — complete dictionary |
| Model taxonomy (per-make dictionaries) | Partially implemented in V04 | HIGH — expand to cover 90%+ of listings |
| Fuel type mapping (6 languages) | Mapping tables defined | MEDIUM — implement as normalization step |
| Transmission mapping | Mapping tables defined | MEDIUM |
| Color normalization | Not implemented | MEDIUM — high linguistic complexity |
| Mileage unit conversion | Implemented (km default, miles detected) | DONE |
| Currency conversion (CHF→EUR) | Implemented (basic) | LOW — upgrade to ECB daily rates |
| Cross-source dedup (V12) | Implemented | DONE |
| Body type normalization | Not implemented | MEDIUM |
| Power unit conversion | Partially (PS→kW) | LOW — extend to all units |

**Estimated effort for full normalization pipeline:** 40-60 hours of taxonomy curation + 20-30 hours of code implementation. The curation is the bottleneck — each make/model dictionary requires verification against actual portal data.

---

*This framework defines the canonical schema and normalization rules for CARDEX vehicle data. It reflects the actual state of the quality pipeline (20 validators, V01–V20) and identifies gaps requiring implementation. The taxonomy dictionaries described here are specifications to be built — they do not exist as complete data files in the current codebase.*
