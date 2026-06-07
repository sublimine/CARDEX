---
name: project-p2-hardening
description: "P2 cabos-sueltos cerrados (rama feature/p2-hardening) — remediación, anti-FP, cola worker, reclaim, migración"
metadata: 
  node_type: memory
  type: project
  originSessionId: 3580463c-4ae4-408a-9d01-af8872ba2a62
---

P2 hardening: 5 cabos sueltos que Guardian documentó, cerrados con tests. Rama
`feature/p2-hardening` desde main `6219527`, **worktree aislado**
`C:/Users/elias/projects/cardex-p2-hardening`, commit `d331f49`, **NO push** (main lo
mueve otra sesión; ya iba por 7a03433). Solo código; NO toca `discovery_candidates`
(barrido A activo), docker, ni corre la migración en vivo. Suite **1366 passed, 0 failed**
(1354 + 12). Reporte: `P2_HARDENING_REPORT.md`.

1. **Auto-remediación dealer-scraping** estaba dormida: `harvest_dealer` calculaba drift
   pero nunca llamaba `remediate()`. Fix: callback **`remediator` inyectable** en
   harvest_dealer (evita ciclo import harvester↔remediation y recursión: `remediate`
   llama harvest_dealer SIN remediator) + `remediation.make_remediator()` + cableado en
   `scripts/run_dealer_scraping.py`.
2. **Anti-FP domain-resolution**: `_NON_DEALER_RE` ampliado a 6 idiomas + parts/body
   shops (rijschool/scuola guida/ricambi/recambios/ersatzteile…); y **name match
   substring→palabra completa `\b`** cierra el FP `Artcar→bmwartcarcollection.com`.
3. **Cobertura cola worker** (lo más sensible, antes sin tests): collision-merge con pool
   fake (UniqueViolation→merge, no crash) + **SKIP LOCKED disjoint** contra PG real en
   tabla **throwaway aislada** (`_p2_claim_probe`, nunca discovery_candidates).
4. **P1 reclaim A6** (`enrich_worker`): cap de entregas vía XPENDING → **DLQ anti-churn**
   (`MAX_DELIVERIES`, def 5) + **try/except por-mensaje** (paridad con A7). Migración
   `scripts/migrate_vehicle_events_partition.sql` envuelta en **`BEGIN;/COMMIT;`**
   explícitos → abort-safety independiente de `--single-transaction`.
5. **Docs stale**: los conteos de los reportes de misión son point-in-time (no se
   falsifican); lo realmente stale eran dos docs de auditoría que afirmaban "1 failed"
   pre-existente (ya resuelto) → anotados con el estado actual (1366/0).

Tests de integración (PG) usan tablas throwaway aisladas; `discovery_candidates` jamás
tocada. Relacionado: [[project_dealer_scraping_system]], [[project_domain_resolution_runtime]],
[[project_p1_hardening]].
