# DISCOVERY MEGA REPORT — descubrimiento masivo (hacia 2M)

**Rama:** `feature/discovery-mega` (worktree aislado, desde `main 1ca158a`). **Sin push. main intacto. Otros worktrees/sesiones (domain-resolution, dealer-scraping, p2) y el inventario E07 no tocados. Solo escrituras en `discovery_candidates`. Sin reinicio de Docker ni migración de esquema.**
**Fecha:** 2026-06-07 · **Método:** research-first; cada endpoint/dump verificado antes de cargar; lo no verificado se marca y NO se carga. Conteos = `SELECT` reales sobre PG. Ejecutado con flota de 5 agentes paralelos + orquestación.

---

## 1. Resultado global (VERIFICADO)

| Métrica | Baseline (inicio misión) | Actual | Δ |
|---|---:|---:|---:|
| `discovery_candidates` total | 685.096 | **759.766** | **+74.670** |
| dealers CON WEB | 46.225 | **46.526** | +301 (+ name-tail acumulando) |

> **Esta misión movió VOLUMEN, no con-web.** El salto son **registros mercantiles** (DE OffeneRegister, NL RDW completo) = identity rows sin web. Los frentes de con-web (OEM menores, directorios, OSM long-tail) estaban **agotados o bloqueados por rate-limit** esta sesión (detalle §4). El frente con-web vivo restante (OSM name-tail) corre en background.

---

## 2. Por país (VERIFICADO)

| País | Total (baseline → actual) | Δ total | Con web (baseline → actual) | Δ con web |
|---|---|---:|---|---:|
| **DE** | 69.722 → **116.720** | **+46.998** | 27.015 → 27.282 | +267 |
| **NL** | 10.480 → **37.036** | **+26.556** | 6.898 → 6.898 | 0 |
| FR | 568.355 → 569.160 | +805 | 5.293 → 5.306 | +13 |
| ES | 14.435 → 14.593 | +158 | 1.747 → 1.747 | 0 |
| BE | 4.625 → 4.778 | +153 | 1.247 → 1.276 | +29 |
| CH | 17.479 → 17.489 | +10 | 4.025 → 4.025 | 0 |
| **TOTAL** | 685.096 → **759.766** | **+74.670** | 46.225 → 46.526 | +301 |

DE y NL transformados en VOLUMEN (registros). El universo total de candidatos roza **760K**.

---

## 3. Fuentes cargadas esta misión (VERIFICADO)

| Fuente | País | Filas | Con web | Vía |
|---|---|---:|---:|---|
| **offeneregister** | DE | **47.131** | 0 | dump SQLite OffeneRegister, filtro nombre (Autohaus/KFZ/Automobile/Gebrauchtwagen/Motors…) |
| **rdw_erkende_bedrijven** (full) | NL | **26.856** | 3 | RDW Socrata `5k74-3jha`, era 300 → censo completo (Bedrijfsvoorraad/Handelaarskenteken) |
| pagesjaunes | FR | 786 | 5 | listing por dpto (7/96, rate-limited) |
| 11880 | DE | 227 | 0 | listing (rate-limited Cloudflare Retry-After 55min) |
| oem:cupra | 6 países | 126 | 3 | SNW + D'Ieteren (resto colapsó en SEAT por dominio) |
| osm_nametail | (corriendo) | 96+ | 21+ | bbox tiling + name-regex multilingüe |
| osm_full | (corriendo) | — | — | tags expandidos |

Tests: +169 (5 módulos nuevos + registros). **Suite 1568 verde.**

---

## 4. Mapa honesto de agotamiento por frente

**1. Registros mercantiles — EXPRIMIDOS donde es libre:**
- DE OffeneRegister dump 2019 → **+47.131** (la SQL API `db.offeneregister.de` sigue 502; el dump es la única vía libre). 
- NL RDW → censo completo **+26.856**.
- FR SIRENE+recherche (360K+175K) y CH zefix all-cantons (9.8K) ya estaban completos.
- **ES**: OpenMercantil solo cubre cooperativas/recientes (+175 en 5 CNAE); BORME completo = suscripción. **BE KBO**: bulk requiere alta por email + las 3 URLs de descarga dan 404. → conector `be_kbo.py` listo (16 tests) para cuando haya `KBO_DATA_DIR`. **Backlog (alta/pago).**

**2. OEM menores — AGOTADOS (solo Cupra viable):**
- **Cupra** cargado (comparte SNW/D'Ieteren con SEAT). El resto, verificado MUERTO/bloqueado con evidencia HTTP: Mini (STOLO NXDOMAIN), Jeep (Stellantis DNS fail), PSA Peugeot/Citroën/Opel (403 Cloudflare), Volvo (403/DNS), Nissan/Honda/Mitsubishi (sin endpoint público sin JS), Suzuki/Mazda (404/DNS), Mercedes/Ford (Akamai WAF). **No hay más OEM de coste cero.**

**3. Directorios — rate-limited (rerun en cooldown/VPS):**
- 11880-DE (52.721, web en detalle) y PagesJaunes-FR (~12% web): Cloudflare cortó tras el primer burst (Retry-After ~55min). Código correcto+testeado; chips de rerun creados. **Dedicar a VPS** (no martillear host compartido con 4 sesiones).
- BE/ES (GoudenGids/PáginasAmarillas/QDQ): Incapsula → navegador/proxy. **Backlog (presupuesto).**

**4. OSM — corriendo en background:**
- `osm_full` (tags expandidos): MARGINAL (la query por área ya era exhaustiva; BE smoke +8 con-web). 
- `osm_nametail` (long-tail no-tagueado, name-regex multilingüe por celdas bbox): **el frente con-web vivo.** ROI medido: ~68% candidatos nuevos vs tag-based, señal 80%, ~22% con web. Proyección full: ~+1.000–1.500 con-web (DE/FR/ES los mayores). Barrido completo ~7–8h por contención de Overpass → **acumula en PG; reportar al cierre.**

---

## 5. Hacia 2M — diagnóstico honesto
El universo de candidatos pasó a **~760K**. El salto a 2M NO está en más fuentes libres: FR/DE/NL registros ya exprimidos; ES/BE registros tras email/pago; OEM coste-cero agotados; directorios libres ya cargados (AGVS/GelbeSeiten/BOVAG) o rate-limited (11880/PagesJaunes→VPS). Los 2M requieren: (a) registros de pago (BORME-ES suscripción, KBO-BE alta, Handelsregister-DE oficial), (b) directorios tras proxy/navegador (BE/ES Incapsula), (c) completar el long-tail OSM name-tail (en curso), (d) Common Crawl a escala (cómputo). **El techo libre-y-host-safe está esencialmente alcanzado; lo demás es tiempo de ejecución (name-tail) o presupuesto.**

## 6. Invariantes / reproducibilidad
- Solo INSERT/heartbeat en `discovery_candidates`; dedup por índices únicos `(domain,country)` y `(source,registry_id,country)`. **Sin migración de esquema, sin reinicio Docker.** RAM-safe (dump SQLite a disco; OSM por país/celda; concurrencia acotada).
```
DE reg: python -m scrapers.discovery.sources.de_offeneregister   # o dump sqlite (ver registries.md)
NL reg: python -m scrapers.discovery.sources.nl_rdw              # limit=0
OEM   : OEM_BRANDS=cupra python -m scrapers.discovery.sources.oem_brands_ext
OSM   : OSM_COUNTRIES=... python -m scrapers.discovery.sources.osm_full
OSMnt : OSM_NT_COUNTRIES=... python -m scrapers.discovery.sources.osm_nametail
DIR   : python -m scrapers.discovery.sources.{de_11880,fr_pagesjaunes}   # rerun en cooldown
DSN   : DATABASE_URL=postgresql://cardex:cardex_dev_only@localhost:5432/cardex
```
Detalle agentes: `C:\Users\elias\AUDIT_SCRATCH\mega\{osm_full,osm_nametail,oem_brands_ext,dir_full,registries}.md`.
