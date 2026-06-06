# NL VERTICAL — Reference pattern (validated, measurable, fan-out ready)

**Fecha:** 2026-06-06 · **Rama:** `feature/p0-rewiring-canon` (NO `main`)
**Principio:** validar-con-límite-y-purgar (el disco local es banco de pruebas, no almacén).
**Base:** cierra el seam P0 (`P0_EXECUTION_REPORT.md`) y lo lleva al vertical NL completo.

> Cada cifra es `[VERIFICADO]` (salida de comando) o `[ASUMIDO]` (declarado). Nada inventado.
> El inventario poblado para validar se **purgó**; la discovery (censo, ligera) se mantiene.

---

## 0. Resumen ejecutivo

El vertical NL se valida en **dos frentes que se enlazan por el dominio del dealer**:

| Frente | Pieza | Estado | Evidencia |
|---|---|---|---|
| **Discovery (censo)** | `nl_rdw` (RDW Erkende Bedrijven) | ✅ VERIFICADO vivo | 300 dealers reales upserted; coste-cero, rompe monocultivo FR |
| **Discovery (dominios)** | OSM (ya en prod) | ✅ presente | 2 913 dealers NL con dominio |
| **Domain resolution (A2)** | `name_to_domain` (crt.sh) | 🟡 cableado, bajo rendimiento | crt.sh:5432 alcanzable; 0/10 en long-tail (lento ~10s/q) |
| **Inventario (L1→L2)** | seam A4→A5→A6→A7 | ✅ VERIFICADO vivo ×2 | autotrack.nl + viabovag.nl → `vehicles` reales, purgado |
| **Inventario dealer-directo** | `generic_extractor` | 🟡 cableado; gap E07 | dealer SPAs son JS/XHR → estático no alcanza el detalle |

**Conclusión accionable:** para NL la cobertura coste-cero de inventario se logra por **portales con JSON-LD** (autotrack/viabovag/autoweek/autowereld/autokopen), no por gaspedaal (meta-agregador) ni por dealer-sites directos (SPAs JS). La discovery de dealers (RDW+OSM) está resuelta. El patrón es **country-agnostic en su núcleo** → fan-out por config.

---

## 1. Frente A — Discovery (censo coste-cero)

### 1.1 `nl_rdw` — RDW Erkende Bedrijven `[VERIFICADO]`
Nueva source: `scrapers/discovery/sources/nl_rdw.py`. Datasets Socrata sin clave:
- `5k74-3jha` (Erkende Bedrijven): `volgnummer`, `naam_bedrijf`, `gevelnaam`, dirección. **Sin web.**
- `nmwb-dqkz` (Erkenningen): `volgnummer` + `erkenning` (tipo). Join por `volgnummer`.

**Filtro dealer** (precisión, no todo el censo): `erkenning in (Bedrijfsvoorraad, Handelaarskenteken)`
— stock de vehículos + matrícula de comerciante = dealer/trader real. Excluye fotógrafos,
fabricantes de placas, etc. (verificado vía `$group=erkenning`: Bedrijfsvoorraad=24 694,
Handelaarskenteken=24 887; ruido como `Fotograaf Bemand`=1 155 queda fuera).

**Run vivo (RDW_LIMIT=300):**
```
rdw dealers (Bedrijfsvoorraad/Handelaarskenteken) = 300
rdw companies resolved = 300
DONE nl_rdw upserted=300
muestra: Garage Kemker (KOUDUM 8723EA), Garagebedrijf Smit V.O.F., Garage Rinsma Berlikum B.V.
```
Filas-identidad (`domain=NULL`, `registry_id=volgnummer`, `source='rdw_erkende_bedrijven'`,
layer 3); idempotentes por `ON CONFLICT (source, registry_id, country)`. **300 dealers NL
reales persistidos** (censo, no inventario → se mantienen). `discovery_candidates` NL: 5 430 → 5 730.

Tests: `test_nl_rdw.py` (3) — transform puro + filtro dealer.

> Capacidad total disponible: 30 678 empresas RDW; ~24 700 con `Bedrijfsvoorraad`. El run
> completo (`python -m scrapers.discovery.sources.nl_rdw` sin RDW_LIMIT) las trae todas.

### 1.2 OSM (ya en producción)
2 913 dealers NL **con dominio** ya presentes (source `osm`). Es la vía de alta cobertura de
*dominios* para NL (OSM trae `website` directamente, a diferencia de RDW).

---

## 2. Frente intermedio — Domain resolution (A2) `[VERIFICADO, hallazgo honesto]`

RDW no trae web → para enlazar censo→inventario hay que resolver `name → domain`.
- `name_to_domain` (extendido aquí para incluir `rdw_erkende_bedrijven`) usa **crt.sh Postgres**
  (`guest@crt.sh:5432/certwatch`) — **alcanzable** desde este host (`crt.sh:5432 OPEN`).
- Demo acotada (N2D_LIMIT=10 sobre dealers RDW): **0/10 resueltos en 101s**. crt.sh es lento
  (~10 s/consulta) y de bajo rendimiento para el long-tail (garajes pequeños sin certificado
  por nombre). DDG está baneado en esta IP (memoria).

**Implicación:** la resolución de dominio del long-tail es el cuello de botella real (coherente
con blueprint P1-3, ratio con-dominio 6,2 %). **Vías de mayor ROI para dominios NL** (P1):
(a) **locators OEM** (`?postcode=`) que devuelven el dominio del concesionario directamente;
(b) **BOVAG** (directorio de socios con web); (c) OSM (ya da dominio). crt.sh queda como
complemento desde IP de producción, no como vía principal.

---

## 3. Frente B — Inventario (L1→L2, validate-with-limit-purge)

### 3.1 Patrón probado: portales NL con JSON-LD `[VERIFICADO ×2]`
El seam P0 (A4→A5 `enrich_pending` → A6 `enrich_worker` → `ingestion_raw` → A7 `rich_consumer`
→ `vehicles` + `meili_sync`) se valida E2E vivo sobre **dos** fuentes NL reales, con redis
throwaway y purga por igualdad exacta de URL (H2):

```
autotrack.nl (limit 3): A6 emitted=3 → A7 persisted=3 → vehicles 30→33
  Peugeot 2008 2020 €20700 · Mazda CX-3 2019 €19395 · SEAT Ateca 2019 €16950 · PURGED→30
viabovag.nl  (limit 3): A6 emitted=3 → A7 persisted=3 → vehicles 30→33
  Fiat Panda 2014 €4950 · Audi A3 2020 €21950 · BMW X1 2020 €27950 (source_id UUID) · PURGED→30
```
Datos ricos correctos (make/model/year/EUR), `source_id` no-null (H1), `meili_sync` emitido,
disco restaurado. **El patrón de inventario NL funciona y es repetible.**

Harness: `scripts/verify_seam_redis.py --domain <portal> --country NL --limit N`.

### 3.2 Negativos verificados (qué NO sirve para NL)
- **gaspedaal.nl** → `missing_critical:make,model,images`: es meta-agregador, sus detalles no
  llevan JSON-LD `Car`. No usar como fuente de inventario directa.
- **Dealer-sites directos** (nefkens.nl, munsterhuis.nl, autobedrijfedelman.nl, boermangroep.nl)
  → `generic_extractor` descubre **páginas-categoría** (`/voorraad/occasions`), no detalles por
  vehículo. Diagnóstico de `nefkens.nl/alfa-romeo/voorraad/occasions` (698 KB): **0 `@type` Car/
  ItemList**, 92 hints api/xhr (Next.js `/_next/`, fetch/axios). → **inventario JS/XHR (SPA)**;
  el path estático (E01 JSON-LD / E03 sitemap) no alcanza el detalle. Necesita **E07
  (playwright-XHR)** o consumir el feed JSON del CMS por dealer. `scripts/verify_dealer_vertical.py`
  deja el mecanismo cableado y medible para cuando E07 entre (P1/P2).

### 3.3 Estado del dealer-path (`generic_extractor`, blueprint P2-1)
**Cableado y corriendo** por primera vez (antes: `dealer_inventory=0`, 0 invocadores):
`verify_dealer_vertical.py` lo ejecuta E2E (discover→engine fetch→A6→A7). El mecanismo es
correcto; el rendimiento sobre dealer-SPAs es bajo por la razón de §3.2. La vía de inventario
NL que rinde HOY es la de portales (§3.1).

---

## 4. Medición del vertical NL (antes / después) `[VERIFICADO]`

| Métrica | Antes | Después | Nota |
|---|---|---|---|
| `discovery_candidates` NL | 5 430 | **5 730** | +300 RDW (capacidad ~24 700 dealers) |
| sources NL distintas | 2 (osm, ct_logs) | **3** (+rdw_erkende_bedrijven) | ≥3 ortogonales = criterio de paridad |
| NL con dominio | 2 913 | 2 913 | OSM; RDW pendiente de A2/OEM |
| Inventario seam probado | 0 fuentes | **2 portales** (autotrack, viabovag) | E2E, purgado |
| `vehicles` (estado) | 30 | 30 | poblado-y-purgado (banco de pruebas) |
| Suite de tests | 1 232 | **1 235** | +3 (`test_nl_rdw`) |

---

## 5. Fan-out a los otros 5 países (por configuración)

El **núcleo es country-agnostic**: el seam (A6/A7), el engine anti-detección y las identidades
warmed existen para los 6 países (BE/CH/DE/ES/FR/NL, 18 identidades). Replicar el vertical a un
país = **config + source de discovery**, no código nuevo del seam:

| Eje | NL (referencia) | Fan-out (config por país) |
|---|---|---|
| **Discovery anchor** | `nl_rdw` (RDW) | CH→Zefix (`ch_zefix`), FR→recherche-entreprises (`fr_sirene`), DE→OSM+OffeneRegister, ES→OSM+OEM, BE→KBO+OEM (SOURCING_STRATEGY §7.3) |
| **Dominios** | OSM + (A2 crt.sh) | OEM locators `?postcode=` (todos los países) — vía recomendada |
| **Inventario** | portales NL JSON-LD (autotrack, viabovag) | portales del país ya en `PORTAL_REGISTRY`; el seam corre igual con su `source_key` + identidad del país |
| **Identidad** | NL warmed (3) | ya existen warmed por país |
| **Comando** | `verify_seam_redis --country NL` | mismo harness con `--country {cc}` y los portales del país |

**Receta de fan-out (por país `cc`):**
1. Activar la discovery anchor del país (registrar su source en el orquestador, gate `c=='cc'`).
2. (Recom.) Generalizar locators OEM por código postal → dominios de dealer.
3. Correr el seam sobre los portales JSON-LD del país bajo `EXTRACT_LIMIT`, verificar, purgar.
4. Criterio de "país clavado": `verify_seam_redis` PASS en ≥1 portal del país + discovery con ≥3 fuentes ortogonales.

---

## 6. Cierre y honestidad

**Validado:** RDW discovery (real, 300, capacidad 24,7K) · A2 cableado (crt.sh alcanzable) ·
seam de inventario E2E en 2 portales NL · dealer-path cableado · suite 1 235 verde · disco
restaurado (purga exacta).

**Gaps declarados (no a medias en silencio):**
- A2 long-tail: crt.sh lento/bajo rendimiento; DDG baneado → usar OEM locators (P1).
- Dealer-directo: SPAs JS/XHR → requiere E07 playwright-XHR (P1/P2); hoy la vía que rinde son portales.
- Lo de pago (proxies tier-1: marktplaats, etc.): backlog P3.

**Pendiente operativo (no de código):** ejecutar `nl_rdw` completo (24,7K), barrer OEM por
postcode, correr el seam sostenido sobre los portales NL en VPS (volcado íntegro, sin purga).

*Fin del reporte del vertical NL.*
