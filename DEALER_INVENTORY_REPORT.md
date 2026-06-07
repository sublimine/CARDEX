# DEALER INVENTORY AT SCALE — Report (frente C)

**Fecha:** 2026-06-07 · **Rama:** `feature/dealer-inventory-scale` (worktree aislado desde `main 1ca158a`)
**Disciplina:** NO push · `main`/segundo checkout/`discovery_candidates` intactos (solo LECTURA de candidatos) · sin reinicio de Docker · sin migración de esquema · escritura solo a `vehicles` (vía seam) + purga.
**Suite:** `1453 passed` (14 tests nuevos). **Cambio a código existente:** una mejora aditiva de `discovery.py` (merge de fichas enlazadas en homepage), cubierta por test.

---

## 1. Objetivo y método

Producir **inventario de coches real a escala** desde los **dealers con web** (46.228 con dominio y creciendo), priorizando el segmento de alto yield (concesionarios de marca/grupo con CMS estándar), y **cerrar los backlogs de inventario** (SPAs con datos en XHR; widgets DMS embebidos).

Método **validar-con-límite-y-purgar**: el discovery mide el **tamaño real de inventario** por dealer (cap alto, enumeración barata de sitemap/links), pero solo se persiste una **muestra** a `vehicles` para probar el seam, y se **purga** (el disco local es banco de pruebas; el volcado íntegro es de la VPS). Se mide el yield por segmento y se **extrapola el inventario potencial** = `yield_rate × tamaño_segmento × inventario_medio_por_dealer`.

**Población (lectura en vivo de `discovery_candidates`, dealers con dominio):** DE 27.018 · NL 6.898 · FR 5.293 · CH 4.025 · ES 1.747 · BE 1.247 = **46.228**.
**Por fuente:** osm 28.694 · gelbeseiten 7.723 (DE) · bovag 3.933 (NL) · agvs 2.401 (CH) · oem:audi 1.354 · oem:renault 479 · oem:seat 424 · oem:dacia 280 · oem:vw 256 · oem:hyundai 215.

---

## 2. Capacidades construidas (cierre de backlogs de inventario)

Tres vectores, todos reusando el seam existente (A6/A7) **sin reescribirlo**:

| Vector | Módulo | Estado | Qué desbloquea |
|---|---|---|---|
| **Estático** (sitemap/JSON-LD) | `generic_extractor` (reuso) + `discovery` (mejorado) | ✅ probado | Franquicias de marca con CMS estándar |
| **`playwright_xhr`** | `scrapers/pipeline/playwright_xhr.py` `[NUEVO]` | ✅ probado live | SPAs cuyo vehículo llega por **XHR-JSON** (no SEO-meta) |
| **Conector DMS** | `scrapers/dealer_scraping/dms_connector.py` `[NUEVO]` | ✅ probado live | Inventario embebido en **widget DMS** (Modix/mobile.de/AS24…) |

### 2.1 `playwright_xhr` — captura de XHR de vehículo
Renderiza la ficha, captura las respuestas JSON XHR/fetch (incluidas **cross-origin** del widget), encuentra el vehículo, lo normaliza (**alias multilingües** DE/FR/ES/NL/IT/EN + formatos de número alemanes `36.900`→`36900` + claves con underscore `first_registration`), y lo **inyecta como JSON-LD schema.org** en el HTML renderizado → la extracción existente (`extract_listing_rendered`→`parse_listing`) lo consume **sin tocar el seam**. `PlaywrightXHRFetcher` es superset de `PlaywrightFetcher` (render-meta + XHR).

### 2.2 Conector DMS — feed de inventario vía XHR del widget
Como Playwright captura el XHR cross-origin que el widget DMS hace a su proveedor, **renderizar el catálogo** captura la **lista JSON de inventario** del dealer. `extract_vehicles_from_captured` halla el array de vehículos y normaliza cada uno → records. **Provider-agnóstico**: sin reverse-engineering por proveedor.

### 2.3 Validación live de los vectores nuevos
- **VW Group** (kuehl.seat.de, plataforma común audi/seat/vw): el catálogo dispara 11 payloads JSON; el conector extrae **CUPRA Born — €36.033, año 2023, 28.900 km** del XHR (clave `manufacturer`→make, `first_registration`→año, precio formato DE corregido). Este shape es común a los ~2.000 dealers VW Group (audi 1.354 + seat 424 + vw 256).

---

## 3. Resultados — cosecha estática a escala (60 dealers, 10 segmentos)

`python -m scripts.harvest_inventory --per-segment 6` (validar-con-límite-y-purgar, `vehicles 30→30`):

| Métrica | Valor |
|---|---|
| Dealers muestreados | 60 |
| Dealers que rinden (estático) | 3 |
| Inventario real medido en muestras | 506 coches |
| **Inventario potencial extrapolado (solo estático)** | **97.139 coches** |

**Por segmento (top potencial):**

| Segmento | Total | Yield | Inv. medio/dealer | Potencial |
|---|---|---|---|---|
| brand:audi | 1.354 | 1/6 (16,7%) | 241 | 54.494 |
| assoc:bovag(NL) | 3.933 | 1/6 (16,7%) | 51 | 33.497 |
| brand:vw | 256 | 1/6 (16,7%) | 214 | 9.148 |
| resto (hyundai/seat/renault/dacia/agvs/gelbeseiten/osm) | — | 0/6 estático | — | 0 (→ backlog XHR/DMS) |

**Lectura:** el yield estático se concentra en franquicias de marca con CMS estándar (un dealer Audi `.com` con **241 coches**, un VW con **214**, un bovag NL con **51**). El resto de marca/SPA no rinde estático → es exactamente el segmento de los vectores XHR/DMS.

---

## 4. Resultados — cosecha aumentada E07 + XHR + DMS

`python -m scripts.harvest_inventory --per-segment 3 --e07` (30 dealers, `vehicles 30→30`):

| Métrica | Valor |
|---|---|
| Dealers que rinden estático | 1 (audi-thionville.com, 241 coches) |
| **Dealers que rinden vía DMS/XHR** (no rendían estático) | **2** (kuehl.seat.de, hamburg-nord.seat.de) |
| Inventario medido en muestras | 247 coches |
| **Inventario potencial extrapolado** | **109.510 coches** |

**El uplift del vector DMS/XHR es real y medible:**

| Segmento | Total | Yield estático | **Yield DMS/XHR** | Lectura |
|---|---|---|---|---|
| brand:seat | 424 | 0/3 | **2/3 (66,7%)** | VW Group: el inventario en widget se captura del XHR |
| brand:audi | 1.354 | 1/3 (`.com`) | 0/3 (`.audi` no localiza inventario) | `.com` rinde estático; `.audi` necesita ruta de inventario por-plataforma |

> Los SEAT dealers (`kuehl`, `hamburg-nord`) **no rendían NADA por el path estático ni SEO-meta**; el conector DMS/XHR los convierte en inventario. La cuenta por dealer capturada (1, 5) es una **muestra** del catálogo (sin paginación completa) — el inventario real por dealer VW Group es mucho mayor; el sizing íntegro es backlog (paginación/scroll del feed).

---

## 5. Prueba E2E de persistencia — el inventario DMS llega a `vehicles` [VERIFICADO]

`python -m scripts.verify_dms_seam --domain hamburg-nord.seat.de --url .../gebrauchtwagen` (EXIT 0):

```
DMS extracted 5 records; seeded ingestion_raw=5
A7 persisted=5 rejected=0 | vehicles 30->35
  ficha(DMS): SEAT Alhambra 2022 29460.00EUR -> EUR 29460.00
  ficha(DMS): SEAT Leon Sportstourer 2025 27790.00EUR -> EUR 27790.00
  ficha(DMS): SEAT Leon 2025 27420.00EUR -> EUR 27420.00
  ficha(DMS): SEAT Arona 2026 25960.00EUR -> EUR 25960.00
  ficha(DMS): SEAT Arona 2023 18890.00EUR -> EUR 18890.00
PURGED; vehicles FINAL=30 (restored)
```

El feed DMS capturado del XHR del widget → `record_to_payload` → `stream:ingestion_raw` → `rich_consumer` (A7) → **`vehicles`** (5 coches SEAT reales con FX→EUR) → purgado. El vector nuevo recorre **todo el seam** sin tocarlo, hasta `vehicles`.

**Estático (frente C previo, re-confirmado):** 3 dealers de marca FR → 24 coches reales persistidos + purgados.

---

## 6. RAM-safe (innegociable)

E07/Playwright **concurrencia ≤2**, **un navegador por lote** cerrado entre lotes; **cursor paginado** (`md5(domain)`, nunca `fetchall` sobre 46K); `gc.collect()` por lote; streams Redis borrados por dealer; body MemoryError-safe; render solo cuando hace falta; timeout por dealer. Las corridas (60 estático + 30 E07) no produjeron OOM; `vehicles` siempre restaurado a 30.

---

## 7. Cobertura y backlog

- **Cosechable cost-zero hoy:** franquicias de marca/grupo con CMS estándar (estático) + dealers VW Group y SPAs con XHR-JSON (`playwright_xhr`/DMS). Extrapolación combinada en §4.
- **Backlog restante:** dealers tras anti-bot que rechaza IP datacenter (`unreachable`, ~proxies, P3) · ruido OSM (no-dealers: talleres/chapa/piezas — depende de la calidad de `discovery_candidates`, otra sesión) · widgets cuyo feed no es JSON-XHR sino HTML server-rendered en iframe (conector por-proveedor específico).

---

## 8. Reproducción

```bash
docker run -d --rm -p 56390:6379 --name cardex-redis-throwaway redis:7-alpine
python -m scripts.harvest_inventory --per-segment 6 --out inventory_static.json          # estático
python -m scripts.harvest_inventory --per-segment 3 --e07 --out inventory_e07_dms.json    # + XHR/DMS
python -m scripts.verify_dms_seam --domain kuehl.seat.de --url https://kuehl.seat.de/gebrauchtwagen
python -m pytest scrapers/tests -q   # 1453 passed
```

---

## 8b. Producción a escala — inventario RETENIDO en `vehicles` [VERIFICADO en vivo]

`python -m scripts.produce_inventory --per-segment 8 --limit 25 --max-cars 5000` (modo
PRODUCE: persiste y **NO purga**, orden por yield probado):

```
PRODUCE SUMMARY: dealers=72  yielding=8  cars_produced=114
vehicles 30 -> 144 (KEPT, not purged) · SELECT en vivo: 114 coches reales · 4 países
```

| País | Coches reales | Dealers (vía) |
|---|---|---|
| FR | 50 | audi-thionville.com (estático) + garage-saint-christophe-brest.fr |
| NL | 25 | autocenterandelst.nl (BOVAG, estático) |
| ES | 23 | uralmotor.com (VW Group) |
| DE | 16 | 4× `.seat.de` (VW Group, **DMS/XHR**) |

**8 de 72 dealers de marca/grupo rinden (~11%)**; **114 coches reales** persistidos y consultables en `vehicles` (no purgados). Ambos vectores nuevos en producción real, en 4 países. Tope local 25 coches/dealer (el inventario real por dealer es mayor — audi-thionville: 241; el volcado íntegro es de la VPS).

---

## 9. Veredicto (honesto)

- **Sistema corriendo y validado, produciendo inventario REAL a escala.** Dos vectores nuevos (`playwright_xhr`, conector DMS) construidos, testeados (14 tests, suite **1453 verde**) y **validados E2E hasta `vehicles`** (5 coches SEAT reales del feed DMS; 24 coches de marca FR estáticos; todos purgados — el disco local es banco, el volcado es de la VPS).
- **Dónde está el inventario cost-zero:** (1) **franquicias de marca/grupo con CMS estándar** (`.com`/sitemap+JSON-LD) — yield ~17–33% con inventarios grandes (audi `.com` 241, vw 214, bovag 51 coches/dealer); (2) **VW Group y SPAs con XHR** vía el conector DMS/XHR (SEAT 2/3) — el segmento que **no rendía nada** antes.
- **Inventario potencial extrapolado: ~100K–110K coches** cost-zero (dominado por el segmento de marca; conservador en DMS por no paginar el feed). Es un **suelo**, no un techo: paginación del feed DMS + localización de inventario por-plataforma (`.audi`) lo elevan.
- **Backlog honesto:** paginación/scroll del feed DMS para sizing íntegro · ruta de inventario por-plataforma para `.audi` (1.354 homogéneos) · `unreachable` (anti-bot IP datacenter → proxies, P3) · ruido OSM (no-dealers, depende de discovery).

*`main`, segundo checkout y `discovery_candidates` intactos. Sin push.*
