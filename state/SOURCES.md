# Fuentes de descubrimiento — activas / cuarentena

> Estado de los conectores `scrapers/discovery/sources/*`. Verificado 2026-06-10.

## Activas y productivas (con filas reales en `discovery_candidates`)
| Fuente | Países | Filas (orden de magnitud) | Resuelve web propia |
|--------|--------|---------------------------|---------------------|
| `nl_rdw` (RDW erkende bedrijven) | NL | 26.856 | NO (sólo name+city → cola W1) |
| `mass_registry` / `de_offeneregister` | DE | ~20k (AS24+OEM) | parcial |
| `osm_full` / `osm_expanded` | 6 países | ~30k | ~40% trae web |
| `as24_dealers` | 5 países | ~34k perfiles | NO (perfil de portal) |
| `oem_locators` + `oem_*` (10 marcas) | 6 países | ~12k | sí cuando la marca lo expone |
| `fr_sirene` / `fr_sirene_v311` | FR | ~12k | NO (identidad legal → cola W1) |
| `ch_zefix_allcantons`, `ch_agvs` | CH | ~5k | parcial |
| `de_gelbeseiten`, `de_11880`, `fr_pagesjaunes`, `nl_bovag` | DE/FR/NL | directorios | sí (directorio = web) |

## En cuarentena / con freno
| Fuente | Motivo | Vía robusta alternativa |
|--------|--------|-------------------------|
| `fr_recherche_entreprises` (API gov FR) | baneó la IP por concurrencia (2026-04) | **opendatasoft SIRENE v3** (host distinto, no penalizado) — `scripts/sirene_ods_load.py` |
| Transporte `aiohttp` en el probe | epidemia de falsos-DEAD por degradación de sesión | **curl_cffi** (`CurlProbeSession`, default desde 2026-06-10) |

## Reglas operativas grabadas (lección 2026-06-10)
- **Nunca solapar corridas de probe**: saturan el resolver/NAT doméstico local.
  En VPS este constraint no aplica (anotar al abrir esa fase).
- **DNS público** (1.1.1.1/8.8.8.8) en los connectors de red intensiva.
- **Muestra adversarial obligatoria** de cualquier lote DEAD antes de darlo por bueno.
- **API gov de lookup → usar DUMPS descargables** + token-bucket global, no machacar.
