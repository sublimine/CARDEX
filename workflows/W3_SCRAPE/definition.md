# W3 — SCRAPEAR

> Ejecuta la receta, normaliza al esquema canónico y deduplica inter-portal.
> El mismo coche en 3 portales = 1 coche con 3 presencias.

## Contrato
- **Input:** ficha + receta versionada (output de W2).
- **Output:** stock normalizado al esquema canónico, cageado en la base, listo
  para W4. Dedup inter-portal aplicado.

## Esquema canónico (campos del dato de vehículo)
`marca · modelo · versión/variante · año · km · precio · combustible ·
transmisión · fotos · ubicación · dealer_id (cdx_code) · contacto · vin (cuando
existe) · url_original · last_seen`.

## Sub-fases y átomos reales (main @ 3adc857)

1. **Enumeración de stock** — `scrapers/dealer_scraping/inventory_harvester.py`
   (`harvest_t2_dealer`) + `harvester.discover_dealer_urls` (family-aware: camina
   el sitemap pinneado de la receta; fallback a cascada genérica).
2. **Parseo a canónico** — `scrapers/pipeline/parse.py` (`parse_listing`,
   JSON-LD @graph Car + selectores). Guardas de rango (`_year`/`_price`/`_km`:
   el km descontrolado desbordaba int4, ya corregido).
3. **Cage por seam** — `scrapers/dealer_scraping/seam.py` (`make_live_seam`):
   A6 `enrich_worker` → A7 `rich_consumer` → `vehicles`/`vehicle_index` con
   `entity_ulid` (auto-registra la entidad, sirve por API).
4. **Dedup inter-portal** — por `vin` cuando existe; si no, por
   `url_hash` normalizado + huella (marca+modelo+año+km+precio). El coche es la
   unidad; cada portal es una PRESENCIA, no un duplicado.

## GATE W3 (binario)
**PASA** si y solo si:
- [ ] el conteo extraído == el visible por **≥2 vías ortogonales** (paginación vs
      sitemap vs filtros) — diferencia 0,
- [ ] todos los registros validan el esquema canónico (campos obligatorios no NULL:
      marca/modelo/precio mínimo, dentro de rango),
- [ ] dedup aplicado: ningún coche físico contado dos veces dentro del mismo dealer.

**NO PASA** → el dealer se aísla con el motivo (conteo discrepante, parser roto,
defensa nueva → reentra a W2 remediación). No bloquea la línea.

## V3 — INQUISICIÓN (agente DISTINTO al scraper, cadena separada)
- **Conteo por ≥2 vías independientes de la que extrajo**: `scripts/verify_count.py`.
  Si W3 usó sitemap → la Inquisición cuenta por paginación y por filtros.
- **Disparadores de re-verificación SIEMPRE** (lección 2026-06-10):
  - **cifras redondas** (exactamente 100, 500, 1000…) → sospechosas de cap/truncado,
  - **conteos idénticos entre dealers distintos** → sospechoso de bug compartido,
  - **CEROS** → SIEMPRE re-probado por transporte distinto (hoy una epidemia de
    "0 stock / DEAD" era bug de transporte aiohttp, no realidad — 9/10 supuestos
    muertos estaban vivos).
- Veredicto a `verification_verdicts` (quórum ≥2 vías ortogonales, CHECK DB).
  El productor JAMÁS certifica su propio número.
