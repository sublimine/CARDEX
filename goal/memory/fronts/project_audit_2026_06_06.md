---
name: project-audit-2026-06-06
description: Auditoría adversarial CARDEX 2026-06-06 — verdict empírico de ambos GOALs + riesgo doble-checkout
metadata: 
  node_type: memory
  type: project
  originSessionId: c2212611-b904-4b04-9c35-10a7aa492b10
---

Auditoría integral verificada empíricamente (PG vivo + engine.db + logs + 4 agentes). Informe: `AUDIT_CARDEX_2026-06-06.md` (raíz repo, untracked); detalle en `C:\Users\elias\AUDIT_SCRATCH\{portales,discovery,pipeline,engine_git}.md`.

**Riesgo git no obvio:** existen DOS checkouts divergentes del MISMO `origin/main` — `C:\Users\elias\projects\cardex` (correcto, HEAD 6e084a5, todo el scraping) y `C:\Users\elias\CARDEX` (rezagado @42dec67, frontend `workspace/web`, NO tiene 6e084a5). Un push desde el rezagado pisa trabajo. El "auto-commit" es script untracked `auto_commit_check.ps1` (git add/commit/push origin main), NO un git hook.

**Verdict empírico (2026-06-06):** GOAL #1 NO cumplido — vehicle_index 508K en solo 20 dominios medianos; los 8-10 gigantes (mobile.de, AS24×6, leboncoin, coches.net, milanuncios, kleinanzeigen, lacentrale) en 0 por techo de proxies. GOAL #2 NO cumplido — discovery_candidates 460K (84% FR/SIRENE), solo 6,2% con dominio, sitemap_status todos `pending`, 0 dealers crawleados. Cadena rota: enrich roto (stream:enrich_pending vs stream:ingestion_raw + enrich_worker inexistente), generic_extractor T3 completo pero no cableado, entity resolution V21/V12 en pipeline Go-SQLite muerto. Anti-detect engine REAL (3599 LOC, cableado) pero latente sin proxies. 1188/1188 tests verdes. Recomendación: construir encima, no reescribir. Confirma y amplía [[project-storage-reality]], [[project-discovery-free-source-ceiling]], [[project-scraper-sitemap-discovery]].
