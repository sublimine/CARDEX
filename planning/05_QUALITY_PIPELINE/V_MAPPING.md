# Validator Mapping: Planning IDs → Implemented Code

**Status:** Created to resolve CF-06 (naming mismatch between planning validators/ docs and code).

## Background

The `validators/V01-V20_*.md` planning documents were written before implementation and describe
validators in a different order and with different names than what was ultimately built. The code
in `quality/internal/validator/` is the authoritative implementation; the planning docs are
**historical design artifacts** that no longer reflect the current system.

This mapping table is the single source of truth for validator identity.

## Canonical validator table (code is authoritative)

| Code dir | ID | Name | Weight | Severity | Planning doc (historical) |
|---|---|---|---|---|---|
| v01_vin_checksum | V01 | VIN Checksum | 15 | CRITICAL | V01_vin_checksum.md ✓ |
| v02_nhtsa_vpic | V02 | NHTSA vPIC Decode | 12 | CRITICAL | V02_vin_decode_nhtsa.md ≈ |
| v03_dat_codes | V03 | DAT Codes Cross-check | 10 | WARNING | V03_vin_decode_crosscheck.md ≈ |
| v04_nlp_makemodel | V04 | NLP Make/Model | 10 | WARNING | V04_title_nlp_makemodel.md ✓ |
| v05_image_quality | V05 | Image Quality | 10 | WARNING | V07_image_quality.md (diff ID) |
| v06_photo_count | V06 | Photo Count | 8 | INFO | *not in planning* |
| v07_price_sanity | V07 | Price Sanity | 12 | WARNING | V13_price_outlier_detection.md (diff ID) |
| v08_mileage_sanity | V08 | Mileage Sanity | 10 | WARNING | V11_mileage_sanity.md (diff ID) |
| v09_year_consistency | V09 | Year Consistency | 10 | WARNING | V12_year_registration_consistency.md (diff ID) |
| v10_source_url_liveness | V10 | Source URL Liveness | 8 | INFO | *not in planning* |
| v11_nlg_quality | V11 | NLG Quality | 8 | INFO | V19_nlg_description_generation.md (diff ID, diff scope) |
| v12_cross_source_dedup | V12 | Cross-Source Dedup | 12 | CRITICAL | V16_cross_source_convergence.md (diff ID) |
| v13_completeness | V13 | Completeness | 10 | WARNING | *not in planning* |
| v14_freshness | V14 | Freshness | 8 | INFO | *not in planning* |
| v15_dealer_trust | V15 | Dealer Trust Ramp-up | 10 | WARNING | *not in planning* |
| v16_photo_phash | V16 | Photo pHash Dedup | 5 | INFO | V08_image_phash_dedup.md (diff ID) |
| v17_sold_status | V17 | Sold Status Detection | 8 | WARNING | *not in planning* |
| v18_language_consistency | V18 | Language Consistency | 4 | INFO | *not in planning* |
| v19_currency | V19 | Currency Normalization | 6 | INFO | V15_currency_normalization.md (diff ID) |
| v20_composite | V20 | Composite Quality Score | — | — | V20_coherence_final_check.md ≈ |

**Total weight: 176 pts** (V01–V19; V20 computes from results, not weighted itself)

## Weight table for V20 composite scorer

Source of truth: `quality/internal/validator/v20_composite/v20.go:70`

```
V01=15  V02=12  V03=10  V04=10  V05=10
V06=8   V07=12  V08=10  V09=10  V10=8
V11=8   V12=12  V13=10  V14=8   V15=10
V16=5   V17=8   V18=4   V19=6
```

## Planning docs status

The historical planning docs `validators/V05-V19_*.md` describe validators that were:
- Partially implemented under different IDs (e.g., planned V07=image quality → code V05=image_quality)
- Partially superseded by different validators (e.g., planned V06=identity_convergence was not built)
- Some planned validators (V09_watermark, V10_vehicle_classifier, V14_vat_mode, V17_geo, V18_equipment)
  were **not implemented** — deferred to Phase 5+

The planning docs are retained as historical context. For the current system, use this file.
