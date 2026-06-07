# FAN-OUT 5 COUNTRIES — Execution report (DE · FR · ES · BE · CH)

**Fecha:** 2026-06-07 · **Rama:** `feature/fanout-5countries` (desde `main @ a980b3f`) · NO push · main intacto
**Fuente de verdad:** `SOURCING_STRATEGY_BY_COUNTRY.md` (fuentes verificadas en vivo) + `NL_VERTICAL_REPORT.md` §5 (receta).
**Patrón:** replicado por **configuración** sobre el núcleo NL — un conector de discovery por país (mismo molde que `nl_rdw`), sin tocar el seam/engine. Suite **1274 passed, 0 failed**.

> `[VERIFICADO]` = golpeé el endpoint / corrí E2E. Nada inventado: lo no alcanzable coste-cero
> está **marcado BLOCKED con plan**, nunca rellenado. Lo poblado para validar el seam se purgó.

---

## 1. Resumen por país

| País | Fuente discovery nueva | Dealers cargados | Reach | Seam inventario (limit+purge) |
|---|---|---|---|---|
| **FR** | recherche-entreprises.api.gouv.fr (NAF 45.11Z/45.19Z × departamento) | **518** `[V]` | ✅ vivo | portales sin JSON-LD → E07 (P2) |
| **ES** | OpenMercantil (CNAE 4511/4519) | **17** `[V]` (cobertura CNAE parcial) | ✅ vivo | sin JSON-LD → E07 (P2) |
| **CH** | Zefix vía Open Data Basel (BS), name-filtered de+fr+it | **17** `[V]` (solo cantón BS) | ✅ vivo | sin JSON-LD → E07 (P2) |
| **DE** | OffeneRegister (Handelsregister), name-filtered Autohaus/KFZ | **0 — BLOCKED** | SQL API HTTP 502 | autohero fetch-fail (transient) |
| **BE** | KBO/BCE Open Data CSV (NACEBEL 45.x) | **0 — BLOCKED** | CSV requiere registro | sin JSON-LD → E07 (P2) |

**Veredicto:** las 3 fuentes verificadas-en-vivo (FR/ES/CH) cargaron **dealers reales**, añadiendo
una fuente **ortogonal** por país (rompe la dependencia de fuente única). DE y BE: conector
**construido y transform-testeado**, carga **bloqueada por la fuente** (502 / registro), documentada
con plan — ambos países ya tienen discovery sustancial de otras fuentes (DE ~45k, BE ~4k), no quedan
vacíos. El **seam L1→L2 es mecánicamente correcto en los 5 países** (rutea fetch/parse/dlq bien) y
**rinde E2E en portales con JSON-LD** (NL autotrack/viabovag, control positivo en esta rama:
vehicles 30→31); los portales no-tier-1 disponibles de DE/ES/FR/BE/CH **no exponen JSON-LD estático**
(SPA-JS) → necesitan **E07 playwright-XHR** (la misma brecha de `NL_VERTICAL_REPORT §3.2`, P2).

---

## 2. Frente DISCOVERY (coste-cero, config-driven)

Cada país = un módulo standalone en `scrapers/discovery/sources/` con el patrón `nl_rdw`
(httpx + asyncpg upsert idempotente `ON CONFLICT (source,registry_id,country)` + transform puro
testeable + `__main__` con LIMIT). Sin duplicar el núcleo.

### FR — `fr_recherche_entreprises.py` `[VERIFICADO]`
recherche-entreprises.api.gouv.fr, NAF 45.11Z/45.19Z, segmentado por departamento (cap 10k/query →
< cap por dpto). Carga de muestra: **518 dealers** (4 dptos × 2 NAF × 3 págs); barrido completo =
`FR_DEPTS=all` (101 dptos, ~miles). Rompe la dependencia del SIRENE en bruto (misma base INSEE,
acceso ortogonal geocodificado). registry_id = SIREN, con lat/lng.

### ES — `es_openmercantil.py` `[VERIFICADO]`
openmercantil.es CNAE 4511/4519. Carga: **17** (4511=12, 4519=5). **Hallazgo honesto:** la cobertura
CNAE de OpenMercantil es parcial/sesgada (SOURCING §2) → fuente ortogonal pero **delgada**; el censo
ES grueso necesita OEM-locators/FACONAUTO (P2). registry_id = CIF.

### CH — `ch_zefix_bs.py` `[VERIFICADO]`
data.bs.ch dataset 100330 (Zefix Basel-Stadt, geocodificado), filtrado por **nombre** (Zefix sin NOGA
fiable) con `dealer_terms` trilingüe. Carga: **17 dealers** de 4000 registros BS escaneados
(`Auto Service Garage Franca`, `CG Carrosserie AG`, `DSB Automobile AG`…). **Solo cantón BS**; el CH
completo = mirror `all_cantons/companies_<KT>.csv` (26 cantones, P2). registry_id = company_uid (CHE-).

### DE — `de_offeneregister.py` `[BLOCKED, documentado]`
OffeneRegister SQL API (datasette) filtrado por nombre (Autohaus/KFZ via `dealer_terms` DE).
**LIVE LOAD BLOCKED:** `db.offeneregister.de` devuelve **HTTP 502** (caído); el dump
`daten.offeneregister.de` (773 MB SQLite) es impráctico en sandbox. `run()` sondea y devuelve 0 con
WARNING — **no inventa datos**. Schema datasette (`company.company_number/name/registered_office`)
marcado `[ASUMIDO]` hasta verificar contra la API viva. Plan: correr cuando la API recupere, o
procesar el dump en VPS. DE ya tiene ~45k candidatos de otras fuentes.

### BE — `be_kbo.py` `[BLOCKED, documentado]`
KBO/BCE Open Data CSV (NACEBEL 45.11/45.19/45.20), join enterprise+denomination+address+activity.
**LIVE LOAD BLOCKED:** el bundle CSV requiere cuenta registrada por email (SOURCING §4). `run()`
sin `KBO_DATA_DIR` devuelve 0 con WARNING + instrucciones de registro — **no inventa datos**. El
parser CSV está completo y transform-testeado. Plan: registrar en economie.fgov.be, colocar los CSV
en `KBO_DATA_DIR`, re-correr. BE ya tiene ~4k candidatos de otras fuentes.

### Diccionario de dialectos — `dealer_terms.py` `[VERIFICADO]`
Consolidado `{country:{lang:[terms]}}` (cierra la duplicación anti-DRY del blueprint P1-2): DE(de),
FR(fr), ES(es), NL(nl), **BE(nl+fr)**, **CH(de+fr+it)**. Usado por los filtros-por-nombre (DE/CH).
El token genérico **"auto" se excluyó deliberadamente** (matcheaba "Automation"/"automatique" →
falsos positivos observados en vivo en CH; corregido y recargado). `name_matches` accent/case-insensitive.

---

## 3. Frente INVENTARIO (seam L1→L2, validate-con-límite-y-purgar)

Validado 1 portal no-tier-1 por país (con punteros en `vehicle_index`), `EXTRACT_LIMIT=3`, purga.

| País · portal | A6 | A7 | Δ vehicles | Causa |
|---|---|---|---|---|
| DE · autohero.com | emitted=0 transient=3 | — | 0 | fetch falla (sin identidad elegible / anti-bot) |
| ES · ocasionplus.com | emitted=0 dlq=3 | — | 0 | sin JSON-LD Car (parse missing_critical) |
| ES · clicars.com | emitted=0 dlq=3 | — | 0 | sin JSON-LD |
| FR · simplicicar.com | emitted=0 dlq=3 | — | 0 | sin JSON-LD |
| FR · occasions.jeanlain.com | emitted=0 dlq=3 | — | 0 | sin JSON-LD |
| BE · vroom.be | emitted=0 dlq=3 | — | 0 | sin JSON-LD |
| CH · autolina.ch | emitted=0 dlq=3 | — | 0 | sin JSON-LD (coincide con GUARDIAN) |
| **NL · autotrack.nl (control +)** | **emitted=1** | **persisted=1** | **+1** (SEAT Ateca €16950) | **JSON-LD → rinde** |

**Lectura honesta:** el seam **funciona** (control positivo NL en esta rama: 30→31, DRIFT GATE OK,
purgado — mis cambios P1/fanout no lo rompieron) y es **mecánicamente correcto en los 5 países**
(rutea a `dlq`/`transient` correctamente, sin crashear). Pero **los portales no-tier-1 disponibles
de los 5 países no exponen JSON-LD estático** (son SPA-JS): el inventario por-portal coste-cero a
escala requiere **E07 (playwright-XHR)** — exactamente la brecha ya declarada en `NL_VERTICAL §3.2`.
Los portales tier-1 (mobile.de, coches.net, leboncoin, 2dehands…) siguen en backlog (proxies, P3).

> El frente inventario que SÍ rinde hoy son los portales JSON-LD (NL autotrack/viabovag). Para los
> otros 5 países, el desbloqueo de inventario es **E07** (P2), no más fuentes de discovery.

---

## 4. Calidad y cierre

- **Suite:** 1274 passed, 0 failed (1263 → +11 fanout). Cero regresiones; seam NL re-verificado OK.
- **Discovery cargado [VERIFICADO]:** FR +518, ES +17, CH +17 (fuentes ortogonales reales). DE/BE
  conectores listos, carga bloqueada por la fuente (documentada). Cada uno de los 5 países tiene
  ≥1 fuente nueva entregada (3 cargando, 2 esperando desbloqueo de fuente).
- **Archivos nuevos:** `dealer_terms.py`, `sources/{fr_recherche_entreprises,es_openmercantil,ch_zefix_bs,de_offeneregister,be_kbo}.py`, `tests/test_fanout_sources.py`. Rama `feature/fanout-5countries`; main intacto en `a980b3f`.
- **Estado PG:** discovery_candidates con las nuevas fuentes; vehicles=30 (data de seam purgada).

**Pendiente declarado (no a medias en silencio):**
1. **DE:** correr `de_offeneregister` cuando el SQL API recupere, o procesar el dump 773MB en VPS.
2. **BE:** registrar cuenta KBO, `KBO_DATA_DIR=<bundle>` + re-correr `be_kbo`.
3. **ES/CH censo grueso:** OEM-locators por código postal (devuelven dominio directo) + FACONAUTO(ES)
   / mirror all-cantons(CH). 
4. **Inventario 5 países:** **E07 playwright-XHR** para portales SPA-JS (P2) — es el desbloqueo, no
   más fuentes. Resolución de dominio (A2) sobre las nuevas filas identity para la vía dealer-directa.
5. Barrido completo FR (`FR_DEPTS=all`, 101 dptos) en VPS.

*Fin del reporte de fan-out.*
