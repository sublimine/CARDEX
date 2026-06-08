# DISCOVERY SCALE — PLAN / PROGRESO

Rama: `feature/discovery-scale` (worktree aislado `cardex-discovery-scale`, desde main 6e0be32). NO push. Solo escribo `discovery_candidates`. Runtime compartido (E07+Guardian) — no reinicio Docker, no migro esquema.

## Frentes
- [ ] **F1-FR** recherche-entreprises 101 deptos × NAF 45.11Z/45.19Z (FR_DEPTS=all)
- [ ] **F1-CH** Zefix 26 cantones vía mirror Basel all-cantons CSV, filtro trilingüe de/fr/it (CÓDIGO NUEVO + tests)
- [ ] **F2-OEM** locators: BMW(existe) + Mercedes, VW/Audi/SEAT/Škoda, Stellantis, Renault/Dacia, Toyota, Ford, Hyundai/Kia (research+verify+impl)
- [ ] **F2-OSM** Overpass shop=car/car_repair/car_parts × 6 países (existe, ejecutar desde host IP residencial)

## Invariantes
- DATABASE_URL=postgresql://cardex:cardex_dev_only@localhost:5432/cardex (host → localhost:5432)
- Dedup: ON CONFLICT (domain,country) [domain-ful] | (source,registry_id,country) [identity]. NO migrar esquema.
- Research-first: probar cada endpoint con curl antes de cargar; lo no verificado → marcado, no cargado.
- Tests donde añada código. Reporte de conteos reales → DISCOVERY_SCALE_REPORT.md.

## Baseline (2026-06-07, pre-trabajo)
total=460.930 · con_dominio=28.570 · FR 388.941 / DE 45.103 / ES 12.835 / NL 5.730 / CH 4.273 / BE 4.048
fuentes: sirene 360.162, osm 98.865, oem:bmw 606, recherche_entreprises 518, ct_logs 367, rdw 300, name2dom 78, openmercantil 17, zefix_bs 17

## Progreso
- [x] **F2-OEM** oem_locators.py (VW/Audi/Škoda/Toyota/Hyundai/Kia) — 6 países, endpoints curl-verificados. Cargado. 15 tests. Kia keyword-based (lat/lng capada). Renault/Dacia/SEAT/Fiat verificados→deferred (geo-sweep); Mercedes/Ford (Akamai) + PSA (DNS muerto) bloqueados.
- [x] **F1-CH** ch_zefix_allcantons.py — 26 cantones mirror Basel, filtro de/fr/it. DONE: scanned 784.930 → **9.806 dealers**. CH 4.273→~14K.
- [~] **F1-FR** recherche-entreprises FR_DEPTS=all (101) NAF 45.11Z/45.19Z — EN CURSO (background b1d8zn8ry), ~35K y subiendo.
- [x] **F2-OSM** ya completo (98.865); vigencia confirmada CH/BE live≈PG; no re-fetch full (riesgo OOM host compartido) → recomendado desde VPS.
- código commiteado: 582de77 (rama feature/discovery-scale, sin push). Suite 1289 verde.
