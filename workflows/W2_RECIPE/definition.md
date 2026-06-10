# W2 — RECETA

> Caza la configuración óptima de extracción de ESE dealer/portal. El multiplicador
> vive aquí: 1 receta de familia cierra N dealers de la misma plataforma.

## Contrato
- **Input:** ficha de dealer con URL de stock (output de W1).
- **Output:** receta versionada — descubrimiento (sitemap/catálogo/API), anti-bot
  (impersonación, proxy, cadencia), parser (JSON-LD/selector/API), frecuencia.
  Persistida en `configs/dealers/{domain}.json` o `configs/families/{cms}.json`.

## Sub-fases y átomos reales (main @ 3adc857)

1. **Fingerprint de plataforma** — `scrapers/dealer_scraping/cms_fingerprint.py`:
   clasifica la familia (datamotive, wordpress, dealer_com, drupal, joomla,
   autosociaal, gerente_tidi, craftcms, audi_partner, izmocars, modix, dealerk…)
   desde el HTML+headers de la home, puro/sin red.
2. **Resolución de receta** — `scrapers/dealer_scraping/harvester.py`
   (`resolve_or_detect_config`): receta guardada tuned > **receta de FAMILIA que
   acepta el verdict** (instanciada con el host = el multiplicador) > detección
   per-dealer (`build_config`). Reglas en `scrapers/portals/config.py`.
3. **Tier-1 (defensas duras)** — cuando el portal tiene WAF (DataDome/PerimeterX/
   Akamai/Cloudflare): reconocer la defensa → **matriz navegador×proxy×cadencia×
   entrada** (Camoufox + curl_cffi + Playwright E07 + proxies cuando se abre el
   gate de gasto). Investigación en GitHub/foros/Reddit registrada en
   `recipes/RESEARCH_{portal}.md` (ya existe el patrón: `recipes/RESEARCH_audi_partner.md`).

## GATE W2 (binario)
**PASA** si y solo si:
- [ ] la receta enumera la superficie de stock (no la raíz; sitemap/catálogo/API real),
- [ ] **dos ejecuciones independientes** extraen el **mismo conteo** de stock visible,
- [ ] ese conteo == el stock visible declarado por el portal (cuando lo declara),
- [ ] la receta está versionada y guardada (config o family file).

**NO PASA** → si es Tier-1 atascado, escala a investigación (matriz + web) y se
registra en `RESEARCH_{portal}.md` con TODAS las alternativas probadas (qué,
config, resultado). "No se puede" no existe sin ese registro completo.

## V2 — Verificador independiente
- **Doble corrida consistente**: dos ejecuciones de la receta, separadas en el
  tiempo, con el MISMO resultado de conteo y de campos clave (no flaky).
- **100% del stock visible**: el conteo de la receta == el visible por una vía
  ortogonal a la suya (si la receta usa sitemap → verificar por paginación/filtros).
- Veredicto a `verification_verdicts`. Una receta que rinde en ≥10 dealers de su
  familia cierra el gate §9.1 (multiplicador probado).

## Estado del multiplicador (verificado 2026-06-10, vía psql)
| Familia | Dealers rindiendo | Punteros |
|---------|-------------------|----------|
| datamotive | 53 | 11.750 |
| wordpress  | 230 | 5.807 |

Frente abierto (dossier, sin receta a medias): `audi_partner` — stock por API
GraphQL PSS (no sitemap); conector E-DMS pendiente de capturar la query real.
