# Esquema de config por portal — `configs/portals/<source_key>.json`

Config versionada, reproducible y reutilizable de scraping por portal. Extiende el
esquema base ya existente en el repo (autotrack.nl / viabovag.nl / autolina.ch) con
los campos que el frente stealth (faceteo + anti-bot + cobertura) necesita.

## Campos base (compatibles con el sistema de scraping existente)
| Campo | Tipo | Qué |
|---|---|---|
| `source_key` | str | dominio canónico del portal (= nombre del fichero) |
| `country` | str(2) | ISO-2 |
| `strategy` | str | `portal_paginated` · `faceted_api` · `faceted_ssr` · `sitemap_then_detail` |
| `version` | int | versión de la config |
| `endpoints` | obj | `host`, `listing_url_template`, `detail_url_re`, `sitemap_url`, `api_url` (+`makes_ref`, `root_url`, `detail_url_template`) |
| `pagination` | obj | `page_size`, `max_pages`, `page_param` (+`cap_results` si hay tope duro) |
| `extraction` | obj | `method` (`jsonld`/`ssr_state`), `state_var`, `listing_path`, `field_map{canónico→ruta}`, `url_base` |
| `drift_baseline` | obj | `extraction_method`, `expected_min_volume`, `required_fields`, `min_nonnull_ratio` |

## Extensiones stealth
| Campo | Qué |
|---|---|
| `anti_bot` | sistema anti-bot (Akamai / DataDome / PerimeterX / Cloudflare) |
| `access` | `engine` (camoufox), `warm[]`, `settle`, `in_page_fetch` |
| `count` | `method` (`internal_api_in_page`/`ssr_total`/`sitemap_count`), `total_path` (ruta al total dentro del estado/JSON) |
| `facet_axes[]` | ejes de subdivisión: `{axis, param, format, values_ref, values_path, id_key}` — orden = recursión make→year→price→region |
| `leaf_cap` | umbral de hoja: subdividir hasta `count <= leaf_cap` (≤ cap de paginación del portal) |
| `coverage` | `total_oficial`, `cobertura`, `pct`, `method`, `evidence` — resultado medido |
| `estado` | gobernanza: `pendiente de verificación` (Guardian audita) / `config parcial …` |
| `verified` | qué está [VERIFICADO] vs [PENDIENTE] |

## Contrato de cobertura ("completo" por portal)
`Σ(conteos por faceta) ≈ total_oficial` con `pct ≥ 99` (el resto justificado con causa, p.ej. listings sin año).
Cuenta vía `count.method`; enumera vía `extraction` paginando bajo `leaf_cap`; normaliza con `field_map` al seam
(`vehicle_index` + `stream:enrich_pending`); delta SEEN/GONE vs snapshot. Nada se marca verde sin auditoría Guardian.

## Consumidores
- `stealth/facet_engine.py` → `load_config(source_key)` (count/faceteo, portales API).
- profilers SSR por portal (p.ej. `stealth/coches_coverage.py`).
- `supervisor/tier1_runner.py` → ingiere `coverage`/`estado` al ledger `tier1_progress.json`.
- sistema de scraping existente → `endpoints`/`pagination`/`extraction`/`drift_baseline`.
