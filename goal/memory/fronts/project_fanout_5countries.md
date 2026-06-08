---
name: project_fanout_5countries
description: "Patrón NL replicado a DE/FR/ES/BE/CH por config (rama feature/fanout-5countries); qué fuente por país, qué cargó y qué quedó bloqueado/E07"
metadata: 
  node_type: memory
  type: project
  originSessionId: 3580463c-4ae4-408a-9d01-af8872ba2a62
---

Fan-out del [[project_nl_vertical]] a los 5 países restantes, rama `feature/fanout-5countries` (commit `6e0be32`, desde main `a980b3f`; NO pusheado). Suite **1274 verde**. Ver `FANOUT_5COUNTRIES_REPORT.md`. Patrón = un conector standalone por país en `scrapers/discovery/sources/` con el molde `nl_rdw` (httpx + asyncpg upsert idempotente + transform puro testeable + LIMIT), sin tocar el seam/engine.

**Discovery cargado en vivo:** FR `fr_recherche_entreprises` (recherche-entreprises.api.gouv.fr, NAF 45.11Z/45.19Z × departamento, `FR_DEPTS=all` = 101 dptos) → **518** dealers; ES `es_openmercantil` (CNAE 4511/4519) → **17** (cobertura CNAE parcial, delgada); CH `ch_zefix_bs` (data.bs.ch 100330, filtrado por nombre dealer_terms de+fr+it) → **17** (solo cantón BS; CH completo = mirror all_cantons CSV).

**Discovery BLOCKED (conector listo+testeado, NO inventa datos):** DE `de_offeneregister` → `db.offeneregister.de` da HTTP 502 (dump 773MB impráctico); BE `be_kbo` → CSV requiere cuenta registrada (`KBO_DATA_DIR`). Ambos `run()` devuelven 0 con WARNING. DE ya tiene ~45k, BE ~4k de otras fuentes.

**dealer_terms.py:** diccionario consolidado `{country:{lang:[terms]}}` (DE de, FR fr, ES es, NL nl, BE nl+fr, CH de+fr+it). Token bare **"auto" EXCLUIDO** (matcheaba Automation/automatique → falsos positivos en CH; ya corregido). Usado por filtros-por-nombre (DE/CH, registros sin código de actividad). FR/ES filtran por código (NAF/CNAE), NL por recognition RDW.

**Inventario seam cross-país:** mecánicamente correcto en los 5 (rutea fetch/parse/dlq sin crash), pero **ningún portal no-tier-1 de DE/ES/FR/BE/CH rinde por estático** (autohero transient; ocasionplus/clicars/simplicicar/jeanlain/vroom/autolina dlq=sin JSON-LD) — son SPA-JS. Solo portales JSON-LD rinden (NL autotrack control en esta rama: 30→31 OK). **Desbloqueo = E07 playwright-XHR (P2)**, no más fuentes. Misma brecha que NL §3.2.

**Pendiente:** DE (API recupere / dump VPS), BE (registro KBO), E07 para inventario SPA, OEM-locators para censo grueso ES/CH + dominios, barrido FR completo. Tier-1 = backlog proxies P3.
