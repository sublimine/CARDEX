# E07 — Browser-rendered extractor (Playwright) — Execution report

**Fecha:** 2026-06-07 · **Rama:** `feature/e07-playwright-xhr` (desde `main @ a980b3f`) · NO push · main intacto
**Desbloqueo:** los portales no-tier-1 de los 5 países + dealer-sites son SPAs JS que la
extracción estática (E01/E03) no ve. E07 renderiza la página en un navegador y extrae la ficha.
Suite **1273 passed, 0 failed**.

> `[VERIFICADO]` = corrido en vivo. La muestra poblada se purgó. Tier-1 con anti-bot fuerte
> (Akamai/DataDome) sigue en backlog (proxies, P3): E07 abre la brecha de render-JS, no la de challenge.

---

## 1. Qué rinde ahora que antes daba 0 `[VERIFICADO E2E]`

**autolina.ch** — con el seam ESTÁTICO daba `dlq=3` (0 vehicles); con E07:
```
A6(E07) emitted=3 dlq=0 transient=0  →  A7 persisted=3  →  vehicles 30 → 33  →  PURGED → 30
  ficha: AUDI Q5    2020  37900 CHF → EUR 39795
  ficha: SKODA Kamiq 2025 29500 CHF → EUR 30975
  ficha: VW Polo    2022  18100 CHF → EUR 19005
```
Fichas reales, marca/modelo/año/precio correctos, **moneda CHF** (el fix P1.2) convertida a EUR
(FX_RATE_CHF=1.05), contrato idéntico al estático, purgado. **E07 funciona end-to-end sobre un SPA real.**

---

## 2. El hallazgo: SEO-meta como vector genérico

Diagnóstico en vivo (autolina/autohero/gowago): estos SPAs **no** traen JSON-LD, **ni** state-blob
(`__NEXT_DATA__`/`__INITIAL_STATE__`), **ni** un XHR de datos limpio capturable — renderizan al DOM.
Pero **todos pueblan el SEO meta** (lo necesitan para previews/búsqueda). autolina, tras render:
```
og:title    = "SKODA Kamiq 1.5 TSI … gebraucht für CHF 29'500,- auf AUTOLINA"
description  = "… Kilometer: 10'600 km, Leistung: 150 PS, Preis: CHF 29'500,
                Erstzulassung: 01.09.2025, Farbe: Silber, Inserat-ID: 4997584"
```
→ E07 parsea `og:title`+`<title>`+meta-description (multilingüe DE/FR/ES/NL/IT/EN) al MISMO raw-dict
que el path estático. **Genérico, sin selectores CSS por-portal** — funciona en cualquier SPA con
SEO meta poblado (la mayoría). Para SPAs sin meta útil, el config admite `playwright_xhr`
(intercepción) como evolución.

---

## 3. Implementación (config-driven, una estrategia MÁS, sin reescribir el seam)

| Pieza | Archivo | Naturaleza |
|---|---|---|
| Núcleo de extracción | `scrapers/pipeline/playwright_extractor.py` | `parse_rendered_meta` + `record_from_rendered` (PUROS, unit-tested) |
| Navegador | mismo módulo: `PlaywrightFetcher` | headless Chromium reusado; `domcontentloaded`+settle (no `networkidle`: los ads nunca idlean) |
| Dispatch | `enrich_worker.enrich_one` (+ `_is_playwright_source`) | si `configs/portals/<s>.json` selecciona estrategia `playwright_*` Y hay `e07_fetcher` → E07; si no → estático |
| Estrategia | `portals/config.py` (`playwright_meta`/`playwright_xhr`, `PLAYWRIGHT_STRATEGIES`) | activación por config, no hardcode |
| Config de referencia | `configs/portals/autolina.ch.json` | `strategy=playwright_meta` + drift_baseline |
| Harness E2E | `scripts/verify_seam_e07.py` | seed→A6(E07)→A7→vehicles→verify→purge |

- **Reusa el seam:** E07 produce un `VehicleRecord` por la MISMA ruta `to_record`+`quality`+`record_to_payload`
  → `ingestion_raw` → A7 → `vehicles`. El A6 no se reescribió: E07 es opt-in (config + `e07_fetcher` inyectado).
- **Merge meta-gana:** sobre un SPA el cascade estático devuelve ruido heurístico (cogía "600" para un
  coche de 10'600 km); el meta etiquetado es autoritativo → meta gana, estático rellena huecos.
- **Multilingüe + ambas órdenes de moneda:** "CHF 29'500" (prefijo, CH) y "14 990 EUR" (sufijo, FR);
  separadores de millar ' (CH) y . , (EU) tolerados; etiquetas Kilometer/Kilométrage/Kilómetros…,
  Preis/Prix/Precio…, Erstzulassung/Mise en circulation/Matriculación…

---

## 4. Resiliencia / drift para E07 `[VERIFICADO]`

E07 hereda el subsistema de resiliencia sin código nuevo: el drift-gate es **strategy-agnostic** y
lee el `drift_baseline` de la config. `check_volume_drift("autolina.ch", 5)` → `drift:volume(5<100)`
(el coordinator alerta por origen si un harvest E07 cae bajo el piso de la config). El schema-fp drift
(`intelligence/schema.py`) aplica igual a la salida E07 en `verify_seam_redis`.

---

## 5. Tests + calidad

- `scrapers/tests/test_playwright_extractor.py` (10): `parse_rendered_meta` CH/FR, `record_from_rendered`,
  dispatch `enrich_one` (rutea playwright→E07, estático→estático), `_is_playwright_source`. Núcleo
  PURO (sin navegador); la parte de navegador validada por el E2E en vivo.
- **Suite: 1273 passed, 0 failed** (1263 → +10). Cero regresiones (seam estático intacto: el path
  estático sigue corriendo para fuentes sin config playwright).

---

## 6. Estado y pendiente declarado

**Vivo y verificado:** E07 extrae fichas reales de autolina.ch (0→3), config-driven, contrato idéntico,
CHF→EUR, drift por config, purgado. Núcleo unit-testeado.

**Pendiente (no a medias en silencio):**
1. **Más portales SPA:** añadir `configs/portals/<dom>.json` con `playwright_meta` para autohero/gowago/
   ocasionplus/clicars/simplicicar/vroom (los que dieron 0 estático) — es config, no código. Verificar
   por-portal que el SEO meta trae los campos (algunos pueden necesitar `playwright_xhr`).
2. **`playwright_xhr`:** implementar la intercepción de XHR/JSON para SPAs sin meta útil (la estrategia
   está registrada; el extractor de intercepción es el siguiente incremento).
3. **Rendimiento a escala:** un navegador por worker; para volumen, pool de páginas + concurrencia
   acotada. El `e07_fetcher` ya reusa un Chromium; tunear `ENRICH_CONCURRENCY` para E07.
4. **Tier-1 anti-bot** (Akamai/DataDome: mobile.de, coches.net, 2dehands…): E07 renderiza pero el
   challenge necesita proxies residenciales → backlog P3 (E07 no resuelve el anti-bot, solo el JS).
5. **Wire del `e07_fetcher` en producción:** el contenedor `enrich-worker` debe construir un
   PlaywrightFetcher y pasarlo a `a6.run(e07_fetcher=...)` cuando haya fuentes playwright en cola
   (Camoufox/Chromium ya en la imagen Dockerfile).

*Fin del reporte E07.*
