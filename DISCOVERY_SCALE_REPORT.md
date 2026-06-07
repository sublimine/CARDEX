# DISCOVERY SCALE REPORT — frente A (descubrimiento de dealers)

**Rama:** `feature/discovery-scale` (worktree aislado, desde `main 6e0be32`). **Sin push. main intacto. Segundo checkout e inventario E07 no tocados. Solo escrituras en `discovery_candidates`. Sin reinicio de Docker ni migración de esquema.**
**Fecha:** 2026-06-07 · **Método:** research-first; cada endpoint probado con curl antes de cargar; lo no verificado se marca y NO se carga. Conteos = `SELECT count(*)` reales sobre PG.
**Métrica rectora:** **dealers CON WEB** (dominio no-NULL = puente directo a extracción de inventario E01/E03).

---

## 1. Resultado global (VERIFICADO)

| Métrica | Baseline (pre-trabajo) | Final | Δ |
|---|---:|---:|---:|
| `discovery_candidates` total | 460.930 | **685.572** | **+224.642** |
| **dealers CON WEB** | 28.570 | **45.864** | **+17.294 (+60,5 %)** |

> El total creció +224K (registros nacionales sin web: FR `recherche_entreprises` +174.7K, CH `zefix` +9.8K). Pero el objetivo declarado era **dealers con web**, y ahí está el salto real: **+17.294**, vía directorios sectoriales (GelbeSeiten/AGVS/BOVAG) + OEM con `dwsLink`/`url`/`website` + re-fetch OSM. El dedup cross-source por dominio evita doble conteo.

---

## 2. Incremento de dealers CON WEB por país (la métrica) — VERIFICADO

| País | Con web (baseline → final) | Δ con web | Total filas (baseline → final) |
|---|---|---:|---|
| **DE** | 16.575 → **26.653** | **+10.078** | 45.103 → 70.198 |
| **NL** | 2.913 → **6.898** | **+3.985** | 5.730 → 10.480 |
| **CH** | 1.393 → **4.026** | **+2.633** | 4.273 → 17.479 |
| **ES** | 1.463 → **1.747** | +284 | 12.835 → 14.435 |
| **FR** | 5.044 → **5.293** | +249 | 388.941 → 568.355 |
| **BE** | 1.182 → **1.247** | +65 | 4.048 → 4.625 |
| **TOTAL** | 28.570 → **45.864** | **+17.294** | 460.930 → 685.572 |

**DE, NL y CH transformados.** ES/FR/BE crecen poco en con-web: FR porque sus dealers-con-web ya estaban en OSM y lo nuevo son registros sin web; ES/BE porque sus directorios nacionales están bloqueados (§5) y solo entraron OEM+OSM.

---

## 3. Desglose por fuente (VERIFICADO, final)

| Fuente | Filas | Con web | Wave |
|---|---:|---:|---|
| sirene | 360.162 | 0 | pre-existente |
| **recherche_entreprises** (FR, 101 deptos) | 175.263 | 0 | **W1 NUEVO** |
| osm | 98.507 | 28.329 | pre-existente (+re-fetch W2) |
| **gelbeseiten** (DE directorio) | 19.069 | **7.723** | **W2 NUEVO ★** |
| **zefix** (CH 26 cantones) | 9.806 | 0 | **W1 NUEVO** |
| **bovag** (NL directorio) | 4.333 | **3.933** | **W2 NUEVO ★** |
| **oem:dacia** | 3.037 | 280 | **W2 NUEVO** |
| **agvs** (CH federación) | 2.839 | **2.401** | **W2 NUEVO ★** |
| **oem:renault** | 2.714 | 479 | **W2 NUEVO** |
| oem:skoda | 2.050 | 5 | W1 NUEVO |
| **oem:seat** | 1.681 | 424 | **W2 NUEVO** |
| oem:toyota | 1.426 | 4 | W1 NUEVO |
| oem:audi | 1.376 | 1.354 | W1 NUEVO |
| oem:kia | 1.037 | 0 | W1 NUEVO |
| oem:bmw | 570 | 13 | pre-existente |
| oem:vw | 502 | 256 | W1 NUEVO |
| oem:hyundai | 421 | 215 | W1 NUEVO |
| ct_logs / rdw / name2dom / openmercantil / zefix_bs | 367/300/78/17/17 | 367/3/78/0/0 | pre-existente |

Top aportadores de con-web NUEVO: **GelbeSeiten 7.723 (DE) · BOVAG 3.933 (NL) · AGVS 2.401 (CH) · Audi 1.354 · Renault 479 · SEAT 424 · Dacia 280 · VW 256 · Hyundai 215**. (Los OEM con web aportan menos de lo "fetched" porque colapsan por dominio contra dealers que OSM ya tenía — dedup cross-source real.)

---

## 4. Código entregado (rama `feature/discovery-scale`, +73 tests, suite 1347 verde)

| Archivo | Fuente | Verificación |
|---|---|---|
| `fr_recherche_entreprises.py` (endurecido) | FR 101 deptos NAF 45.11Z/45.19Z | 175.263 filas; retry 429/5xx + throttle anti-truncación; `DONE upserted=196169` |
| `ch_zefix_allcantons.py` | CH 26 cantones (mirror Basel CSV) | scanned 784.930 → 9.806; streaming a disco anti-OOM |
| `oem_locators.py` | VW/Audi/Škoda/Toyota/Hyundai/Kia × 6 | endpoints curl-verificados; Kia keyword (lat/lng capada) |
| `ch_agvs.py` | CH AGVS/UPSA (1 GET) | 3.661 miembros, 3.223 con web |
| `de_gelbeseiten.py` | DE GelbeSeiten Autohandel | ~26.7K parsed, website base64 + gsbiz uuid |
| `nl_bovag.py` | NL BOVAG (sitemap → /leden/) | 8.007 procesados, 7.028 auto, filtro por categoría |
| `oem_wave2.py` | Renault/Dacia (dwsLink) + SEAT (url/Dieteren) geo-sweep | re-verificado en vivo |
| `osm_expanded_run.py` (+`OSM_COUNTRIES`) | OSM re-fetch BE/NL/CH/ES/FR | +532 con-web netos |

Todo conforme al upsert existente (`domain,country` | `source,registry_id,country`). **Sin migración de esquema.**

---

## 5. Fuentes restantes — BACKLOG honesto (no cargadas, con razón)

Las fuentes libres de **alto ROI de con-web y RAM/host-friendly están agotadas**. Lo que queda:

| Fuente | País | Estado | Por qué no se carga ahora |
|---|---|---|---|
| **11880.com** | DE | verificado, 52.721 dealers | web solo en página de detalle → ~52K GETs (horas) sobre Cloudflare desde 1 IP residencial; solapa fuerte con GelbeSeiten+OSM ya cargados. **Dedicar a VPS**, no martillear el host compartido. |
| **PagesJaunes** | FR | verificado | web en listing solo ~12 %; el resto exige crawl de detalle (pesado, bajo rendimiento). FR-con-web ya cubierto por OSM. **Backlog VPS.** |
| GoudenGids/PagesdOr | BE | **bloqueado** | Incapsula/Imperva (challenge JS) desde IP residencial → requiere navegador/proxy. **Backlog (presupuesto).** |
| PáginasAmarillas/QDQ/Axesor | ES | **bloqueado** | Incapsula/Cloudflare/Varnish → requiere navegador/proxy. **Backlog (presupuesto).** |
| **Mercedes / Ford** | 6 | **bloqueado** | Akamai WAF (SSL-renegotiation loop), API con key de pago. |
| **PSA Peugeot/Citroën/Opel** | 6 | **caído** | backend `wsrest.servicesgp.mpsa.com` DNS retirado (502). |
| **Fiat** | 6 | **caído** | `dealerlocator.fiat.com` NPE Java en producción (los 6 países, 2026-06-07). |
| **H3 / name-based Overpass** | — | descartado con datos | redundante: la query por área ya captura todo el OSM tagged; name-based aporta ~80-120 con-web con 18 % señal/ruido. |

**Conclusión:** el techo de con-web por fuentes libres-y-host-safe está alcanzado en esta ventana. Subir más requiere (a) un runner dedicado en VPS para 11880-DE/PagesJaunes-FR (sin compartir host), o (b) presupuesto de proxy/navegador para los directorios BE/ES y los OEM Akamai.

---

## 6. Coordinación / invariantes respetadas
- Solo INSERT/heartbeat en `discovery_candidates`. Dedup cross-source por índices únicos parciales existentes: `(domain,country)` y `(source,registry_id,country)`. **Sin migración de esquema.**
- Otra sesión resuelve dominios (UPDATE name→domain) y otra scrapea inventario (E07): no tocadas; estos inserts les amplían la superficie.
- Sin reinicio de Docker. Cargas por lotes RAM-safe (CH/BOVAG/OSM a disco o streaming; OEM 1 país/llamada; BOVAG concurrencia 8 + throttle).
- Tests donde se añadió código (+73). Suite completa: **1347 passed**.

## 7. Reproducibilidad
```
FR : FR_DEPTS=all FR_NAF=45.11Z,45.19Z FR_MAX_PAGES=400 python -m scrapers.discovery.sources.fr_recherche_entreprises
CH : CH_CANTONS=all python -m scrapers.discovery.sources.ch_zefix_allcantons
CH : python -m scrapers.discovery.sources.ch_agvs
DE : python -m scrapers.discovery.sources.de_gelbeseiten
NL : python -m scrapers.discovery.sources.nl_bovag
OEM: python -m scrapers.discovery.sources.oem_locators
OEM: python -m scrapers.discovery.sources.oem_wave2
OSM: OSM_COUNTRIES=BE,NL,CH,ES,FR python -m scrapers.discovery.sources.osm_expanded_run
DSN: DATABASE_URL=postgresql://cardex:cardex_dev_only@localhost:5432/cardex
```
Research wave-2: `C:\Users\elias\AUDIT_SCRATCH\{dir_national,oem_wave2,osm_h3_value}.md`.
