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

## Baseline (rellenar)
## Progreso (rellenar)
