# W1 — DESCUBRIR

> Censa el dealer, le resuelve la web, le asigna identidad estable (cdx_code) y
> jerarquía geo. Es el frente que multiplica el universo scrapeable: hoy el cuello
> real (no el scraping, el DESCUBRIMIENTO).

## Contrato
- **Input:** territorio (país, o país+provincia/ciudad).
- **Output:** ficha de dealer con **URL de stock confirmada** + `cdx_code` + geo
  (país→provincia→ciudad), escrita en `discovery_candidates` y materializada en
  `/dealers/{ISO}/{PROV}/{CIUDAD}/{cdx_code}/ficha.json`.

## Sub-fases y átomos reales (main @ 3adc857)

1. **Censo multi-fuente** — `scrapers/discovery/sources/*` (35+ conectores reales):
   - Registros oficiales: `nl_rdw` (RDW erkende bedrijven), `fr_sirene` /
     `fr_sirene_v311`, `be_kbo`, `de_offeneregister`, `es_openmercantil`,
     `ch_zefix_allcantons`, `mass_registry`.
   - Directorios: `de_gelbeseiten`, `de_11880`, `fr_pagesjaunes`, `nl_bovag`, `bovag`.
   - Mapas: `osm_full`, `osm_expanded_run`, `osm_nametail`.
   - Plataformas: `as24_dealers` (AS24, 5 países), `oem_locators` + `oem_*` (10 marcas).
   - Web descubierta: `common_crawl`, `ct_logs` (Certificate Transparency).
2. **Resolución de web** — `scrapers/discovery/domain_resolution/worker.py`:
   cola atómica `domain IS NULL AND name IS NOT NULL` (FOR UPDATE SKIP LOCKED),
   multi-vía en orden de COSTE: (1) email-apex → (2) directorio nacional →
   (3) búsqueda web (DDG→Mojeek, STRICT). Validador de homepage automotriz.
   LLM local opt-in `DOMRES_LLM_VERIFY` (Ollama) para matar falsos positivos.
   Resuelto → `domain,url` + `sitemap_status='pending'` (entra a W2/W3).
3. **Identidad + geo** — `scrapers/intelligence/cdx_code.py` (CDX-<ISO2>-<8>,
   derivado del dominio, inmutable) + geo de migr. `0004` (6 países / 20.661 ciudades).

## Comando piloto (ES)
```
DATABASE_URL=postgresql://cardex:cardex_dev_only@localhost:5432/cardex \
DOMRES_LLM_VERIFY=1 \
python -m scrapers.discovery.domain_resolution.worker --countries ES --limit 0
```

## GATE W1 (binario)
**PASA** si y solo si:
- [ ] la ficha tiene `domain` resuelto Y validado como homepage automotriz viva,
- [ ] tiene `cdx_code` único (sin colisión en `entity_xref`),
- [ ] tiene geo país→provincia→ciudad poblada (no NULL la cadena),
- [ ] la URL de stock está confirmada (sitemap o catálogo localizado, no la raíz).

**NO PASA** → se marca `ddg_error`/motivo y se aísla (no bloquea la línea); el
dealer reentra a la cola tras `MAX_ATTEMPTS` o queda en cuarentena en `state/SOURCES.md`.

## V1 — Verificador independiente (cadena separada)
- **Cruce ≥2 fuentes**: el dealer aparece en ≥2 conectores ortogonales (p.ej.
  registro + OSM, o AS24 + directorio). `scripts/verify_discovery.py --fill`.
- **Densidad por ciudad vs población**: `capture_recapture.py` (estimador Chapman)
  da el universo esperado; una ciudad con densidad anómala (muy baja vs población,
  o picos) se audita UNA A UNA.
- **Anomalías**: ceros, duplicados de dominio entre fuentes, y saltos bruscos se
  re-verifican siempre (lección 2026-06-10).
- Veredicto a `verification_verdicts` (quórum ≥2, CHECK DB).
