---
name: project-blueprint-target-arch
description: "BLUEPRINT_CARDEX.md (untracked) define la arquitectura objetivo; el sistema es un problema de cableado, no de reescritura"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4702af55-ddf6-4bc0-950b-c3028e4f4a63
---

`BLUEPRINT_CARDEX.md` (raíz repo, **untracked**, escrito 2026-06-06) es el documento maestro de arquitectura objetivo de CARDEX. Construye ENCIMA del audit [[project-audit-2026-06-06]], no reescribe.

Tesis central: CARDEX **no está podrido, está descableado**. Dos universos paralelos (Python→PG vivo que produce 460K/508K, Go→SQLite dormido que nunca corre) + un seam roto. El target es una malla de 11 microagentes (A1–A11) con contratos de datos versionados sobre **dos tiers de persistencia**: L1 `vehicle_index` (punteros baratos+delta, funciona) y L2 `vehicles` (registro rico, hoy=30 por el gap).

Keystone P0: el puente roto `stream:enrich_pending {h,u,s,c}` (productor `indexer.py`) ↔ `stream:ingestion_raw` (consumidor Go `services/pipeline`). El módulo `enrich_worker` (A6) NO existe pero ya está en compose. Crearlo + mapear `VehicleRecord`(Py schema.py)→`vehiclePayload`(Go) desbloquea toda la cadena rica.

**Why:** futuras sesiones no deben re-derivar que esto es wiring, ni proponer rewrite. El blueprint ya tiene contratos exactos (C1–C9), plan P0→P3, y checklist por bloques.
**How to apply:** antes de tocar el pipeline, leer `BLUEPRINT_CARDEX.md`. Piloto = NL (gaspedaal + dealers NL). Principio: clavar UNO antes de abanicar SEIS; validar-con-límite-y-purgar en local ([[project-storage-reality]], [[project-coordinator-oom-supervisor]]).
