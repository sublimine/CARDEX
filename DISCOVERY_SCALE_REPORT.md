# DISCOVERY SCALE REPORT — frente A (descubrimiento de dealers)

**Rama:** `feature/discovery-scale` (worktree aislado, desde `main 6e0be32`). **Sin push. main intacto. Segundo checkout e inventario E07 no tocados. Solo escrituras en `discovery_candidates`. Sin reinicio de Docker ni migración de esquema.**
**Fecha:** 2026-06-07 · **Método:** research-first, cada endpoint probado con curl antes de cargar; lo no verificado se marca y NO se carga. Conteos = `SELECT count(*)` reales.

---

## 1. Resultado global (wave-1, VERIFICADO)

| Métrica | Baseline (pre-trabajo) | Ahora (wave-1) | Δ |
|---|---:|---:|---:|
| `discovery_candidates` total | 460.930 | **652.261** | **+191.331** |
| con dominio web (puente a inventario) | 28.570 | **30.423** | **+1.853** |

> **Lectura honesta:** el +191K es mayoritariamente **identity-rows sin web** (registros nacionales: FR `recherche_entreprises` +174.745, CH `zefix` +9.789). La métrica que importa —**dealers CON WEB**— solo subió **+1.853** en wave-1, porque (a) los registros no traen web y (b) los OEM que sí la traen (VW/Audi/Hyundai) **colapsan por dominio** contra dealers que OSM ya había descubierto (dedup cross-source funcionando). El salto grande de con-web es el objetivo de **wave-2** (§5), cuyas fuentes ya están verificadas en vivo.

---

## 2. Desglose por país (VERIFICADO)

| País | Filas (baseline → ahora) | Δ filas | Con web (baseline → ahora) | Δ con web |
|---|---|---:|---|---:|
| FR | 388.941 → **565.024** | +176.083 | 5.044 → 5.278 | +234 |
| DE | 45.103 → **48.645** | +3.542 | 16.575 → **17.864** | **+1.289** |
| CH | 4.273 → **14.525** | +10.252 | 1.393 → 1.498 | +105 |
| ES | 12.835 → **13.735** | +900 | 1.463 → 1.610 | +147 |
| NL | 5.730 → **6.044** | +314 | 2.913 → 2.928 | +15 |
| BE | 4.048 → **4.288** | +240 | 1.182 → 1.245 | +63 |

Monocultivo FR sigue dominando en volumen (registros), pero **CH rompió su famine** (+10.252, ×3.4) y DE ganó **+1.289 dealers-con-web** reales (redes OEM alemanas). La paridad de con-web se ataca en wave-2 con directorios DE/NL/CH/FR.

---

## 3. Desglose por fuente (VERIFICADO)

| Fuente | Filas | Con web | Estado |
|---|---:|---:|---|
| sirene | 360.162 | 0 | pre-existente (registro FR bruto) |
| **recherche_entreprises** (FR) | **175.263** | 0 | **NUEVO wave-1** — 101 deptos × NAF 45.11Z(171.777)/45.19Z(3.486) |
| osm | 98.865 | 28.127 | pre-existente (núcleo de dealers-con-web) |
| **zefix** (CH 26 cantones) | **9.806** | 0 | **NUEVO wave-1** — mirror Basel all-cantons, filtro de/fr/it |
| oem:skoda | 2.050 | 5 | NUEVO wave-1 (identity) |
| oem:toyota | 1.426 | 4 | NUEVO wave-1 (identity) |
| oem:audi | 1.376 | 1.354 | NUEVO wave-1 (**con web**) |
| oem:kia | 1.037 | 0 | NUEVO wave-1 (identity) |
| oem:bmw | 574 | 14 | pre-existente |
| oem:vw | 502 | 256 | NUEVO wave-1 (con web; resto colapsó en OSM) |
| oem:hyundai | 421 | 215 | NUEVO wave-1 (**con web**) |
| ct_logs | 367 | 367 | pre-existente |
| rdw_erkende_bedrijven | 300 | 3 | pre-existente (NL) |
| name2dom | 78 | 78 | pre-existente |
| openmercantil / zefix_bs | 17 / 17 | 0 | pre-existente |

---

## 4. Qué se construyó en wave-1 (código, en `feature/discovery-scale`)

| Entregable | Archivo | Verificación |
|---|---|---|
| **FR full sweep** (101 deptos) | `fr_recherche_entreprises.py` (endurecido: retry 429/5xx + throttle anti-truncación) | 175.263 filas; sin 429; `DONE upserted=196169 depts=101` |
| **CH 26 cantones** | `ch_zefix_allcantons.py` (mirror Basel CSV, filtro trilingüe, streaming a disco anti-OOM) | scanned 784.930 → 9.806 dealers; +15 tests |
| **OEM locators** (6 brands) | `oem_locators.py` (config-driven, parsers puros) | VW/Audi/Škoda/Toyota/Hyundai/Kia × 6 países, endpoints curl-verificados; +12 tests |
| Tests | `test_oem_locators.py`, `test_ch_zefix_allcantons.py` | **suite 1289 passed** |

**OEM — endpoints verificados en vivo (2026-06-07):**
- VW/Audi: `oneapi.volkswagen.com/go-sds/search/v2/dealers` (JSON, traen web). VW BE → 204 (no servido).
- Škoda: `/apps/retailers/api/{bid}/{culture}/Dealers/GetDealers` (distance=2000 = censo completo: DE 1251 vs 442@300km).
- Toyota: `dealersAutoSuggestion` (lista completa 1 llamada; sin web → identity).
- Hyundai: SSR `data-js-content` (DE/ES/NL/BE/CH, **con web**) + Uberall (FR).
- Kia: `/api/bin/dealer` con keyword (lat/lng estaba capada: DE 396 vs 92); CH vía slapwl; BE no servido.

---

## 5. Wave-2 — EN EJECUCIÓN (fuentes verificadas, priorizadas por dealers-CON-WEB)

Research-first completado (3 agentes, curl en vivo 2026-06-07). Orden por ROI de con-web:

| Prioridad | Fuente | País | Web del dealer | Volumen verificado | Anti-bot |
|---|---|---|---|---:|---|
| 1 | **GelbeSeiten** (`/Suche/Autohandel/Bundesweit`) | DE | ✅ `webseiteLink` base64 en listing | ~27.455 | abierto |
| 2 | **AGVS/UPSA** (mitgliederverzeichnis) | CH | ✅✅ `url` en 1 GET | 3.661 (3.223 con web) | ninguno |
| 3 | **BOVAG** (sitemap → /leden/*) | NL | ✅ anchor website | 8.007 | ninguno |
| 4 | **11880** (`/suche/autohaendler`) | DE | ✅ `itemprop=url` (página detalle) | ~52.721 | abierto (2 pasos) |
| 5 | **PagesJaunes** (por dept) | FR | ✅ `data-pjlb` base64 (~12%) | ~15-30K | chunked (curl ok) |
| 6 | **Renault+Dacia** wired locator | 6 países | ✅ `dwsLink` (NL ~90%, DE ~55%, ES ~42%) | geo-sweep 60 centros | abierto |
| 7 | **SEAT** SNW + D'Ieteren(BE) | 6 países | ✅ `url` (ES 100%, NL 88%, CH 89%) | geo-sweep | abierto |
| 8 | **OSM re-fetch** BE/NL/FR/ES/CH (DE ya 99.5%) | 5 países | ✅ ~28% con web | +~250-750 con-web netos | Overpass |

**Descartado con evidencia (no inventar):**
- **H3 / name-based Overpass**: redundante — la query por área ya captura todo el OSM tagged (DE PG 44.310 ≈ live 44.500). Name-based añade ~80-120 con-web netos con 18% señal/ruido → no justifica esta iteración.
- **Fiat**: `dealerlocator.fiat.com` con NPE Java en producción (caído los 6 países hoy).
- **Mercedes / Ford**: Akamai WAF (SSL-renegotiation loop) → sin JSON público sin key.
- **PSA Peugeot/Citroën/Opel**: backend `wsrest.servicesgp.mpsa.com` con DNS retirado (502).
- **Directorios BE/ES** (GoudenGids, PáginasAmarillas, QDQ): Incapsula/CF challenge → bloqueados desde IP residencial con curl (requieren navegador → backlog).
- **OSM-full DE**: ya al 99.5% → se omite (sin ganancia).

---

## 6. Coordinación / invariantes respetadas
- Solo INSERT/heartbeat en `discovery_candidates`. Dedup cross-source por los índices únicos parciales existentes: `(domain,country)` y `(source,registry_id,country)`. **Sin migración de esquema.**
- Otra sesión resuelve dominios (UPDATE name→domain) y otra scrapea inventario (E07): no se tocan; los inserts nuevos les dan más superficie.
- Sin reinicio de Docker. Cargas por lotes RAM-safe (CH/OSM a disco; OEM 1 país/llamada).

## 7. Reproducibilidad
```
FR : FR_DEPTS=all FR_NAF=45.11Z,45.19Z FR_MAX_PAGES=400 python -m scrapers.discovery.sources.fr_recherche_entreprises
CH : CH_CANTONS=all python -m scrapers.discovery.sources.ch_zefix_allcantons
OEM: python -m scrapers.discovery.sources.oem_locators   # OEM_BRANDS=, OEM_COUNTRIES= para subset
DSN: DATABASE_URL=postgresql://cardex:cardex_dev_only@localhost:5432/cardex
```
Informes de research wave-2: `C:\Users\elias\AUDIT_SCRATCH\{dir_national,oem_wave2,osm_h3_value}.md`.
