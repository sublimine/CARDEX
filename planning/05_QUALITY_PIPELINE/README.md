# Pipeline de Calidad — 05_QUALITY_PIPELINE

## Propósito
Especificación institucional del pipeline de calidad de datos V01-V20. Es el gateway obligatorio entre extraction y el índice live de CARDEX. Ningún `vehicle_record` se publica sin pasar todos los validators BLOCKING y sin documentar todos los WARNING.

## Índice de validators

| ID | Archivo | Nombre | Severity | Phase | Dependencies | Estado |
|---|---|---|---|---|---|---|
| V01 | `validators/V01_vin_checksum.md` | VIN checksum ISO 3779 | BLOCKING | Identity | — | DOCUMENTADO |
| V02 | `validators/V02_vin_decode_nhtsa.md` | VIN decode vPIC NHTSA | WARNING | Identity | V01 | DOCUMENTADO |
| V03 | `validators/V03_vin_decode_crosscheck.md` | VIN decode cross-check DAT/EUR | WARNING | Identity | V02 | DOCUMENTADO |
| V04 | `validators/V04_title_nlp_makemodel.md` | Title NLP make/model inference | WARNING | Convergence | — | DOCUMENTADO |
| V05 | `validators/V05_image_classification_ml.md` | Image ML make/model classifier | WARNING | Convergence | — | DOCUMENTADO |
| V06 | `validators/V06_identity_convergence.md` | Identity convergence (3-of-4) | BLOCKING | Convergence | V02,V03,V04,V05 | DOCUMENTADO |
| V07 | `validators/V07_image_quality.md` | Image quality validation | WARNING | Image | — | DOCUMENTADO |
| V08 | `validators/V08_image_phash_dedup.md` | Image pHash deduplication | WARNING | Image | V07 | DOCUMENTADO |
| V09 | `validators/V09_watermark_logo_detection.md` | Watermark/logo detection | WARNING | Image | V07 | DOCUMENTADO |
| V10 | `validators/V10_vehicle_binary_classifier.md` | Vehicle/non-vehicle classifier | BLOCKING | Image | V07 | DOCUMENTADO |
| V11 | `validators/V11_mileage_sanity.md` | Mileage sanity check | WARNING | Data-consistency | V02 | DOCUMENTADO |
| V12 | `validators/V12_year_registration_consistency.md` | Year vs registration consistency | BLOCKING | Data-consistency | V02 | DOCUMENTADO |
| V13 | `validators/V13_price_outlier_detection.md` | Price outlier detection | WARNING | Price | V15 | DOCUMENTADO |
| V14 | `validators/V14_vat_mode_detection.md` | VAT mode detection | INFO | Price | — | DOCUMENTADO |
| V15 | `validators/V15_currency_normalization.md` | Currency normalization to EUR | BLOCKING | Price | — | DOCUMENTADO |
| V16 | `validators/V16_cross_source_convergence.md` | Cross-source convergence | WARNING | Cross-source | V01,V15 | DOCUMENTADO |
| V17 | `validators/V17_geolocation_validation.md` | Geolocation validation | INFO | Geo | — | DOCUMENTADO |
| V18 | `validators/V18_equipment_normalization.md` | Equipment vocabulary normalization | INFO | Equipment | — | DOCUMENTADO |
| V19 | `validators/V19_nlg_description_generation.md` | NLG description generation | BLOCKING | NLG | V06,V15 | DOCUMENTADO |
| V20 | `validators/V20_coherence_final_check.md` | Coherence final check (LLM) | BLOCKING | Final | V01-V19 | DOCUMENTADO |

## Documentos transversales

| Documento | Contenido |
|---|---|
| `OVERVIEW.md` | Arquitectura gateway, severity matrix, flujo de decisiones, dead-letter queue, confidence_score acumulativo |
| `INTERFACES.md` | Interfaces Go: `Validator`, `ValidationResult`, `ValidationPipeline`, `PipelineOutcome` |
| `NLG_SPEC.md` | Spec detallado de V19: Llama 3 8B Q4_K_M, prompts multilingüe, hallucination detection, BLEU eval |

## Principio de operación
Gateway sin excepciones: un `vehicle_record` que falle cualquier validator BLOCKING no se publica. Entra a dead-letter queue (DLQ) o manual review queue (MRQ) según `NextAction`. Los validators WARNING producen flags que pueden desencadenar revisión pero no bloquean la publicación. Los validators INFO solo loguean.

## TTL y freshness

El pipeline de calidad asigna el TTL inicial del registro según el tier de refresh activo en el momento de la ingesta. Los valores de TTL por tier están definidos en `06_ARCHITECTURE/12_REFRESH_STRATEGY.md`:
- HOT: 45 min | WARM: 3 h | COLD: 12 h | PUSH: 24 h

Un registro que expira su TTL sin ser confirmado transiciona a `EXPIRED` automáticamente y vuelve a pasar por el quality gateway si el Refresh Worker obtiene una nueva versión del source.
