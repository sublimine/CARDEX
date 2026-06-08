---
name: project_cardex_supervisor_73
description: Supervisor-daemon 24/7 en el terminal del usuario + goal de 73 portales tier-1 al 100% con config por portal
metadata: 
  node_type: memory
  type: project
  originSessionId: 020fe92e-3d59-49f4-9abe-f0ad36acb37d
---

**Aclaración clave de Salman (2026-06-07):** NO se necesita VPS — su PC está encendido 24/7 y Dispatch también; todo lo que iría a una VPS se ejecuta en SU terminal de forma autónoma. Dejar de poner "techos" y de pedir VPS. La supervisión 24/7 ya está montada como daemon del SO en su máquina.

**Sistema montado (rama feature/stealth-camoufox, worktree C:\Users\elias\projects\cardex-stealth):**
- cardex_supervisor: tarea Windows "CARDEX Supervisor" (healthcheck cada 5 min) + supervisor.py (PID vivo, reinicia workers muertos con backoff, escribe supervisor_state.json). Probado: kill→restart automático funciona.
- tier1_runner.py: avanza la cola de 73 portales autónomo.
- Ledger tier1_progress.json / TIER1_COVERAGE.md.

**GOAL ACTIVO (/goal):** los 73 portales tier-1 al 100%, bien montados, GUARDANDO LA CONFIG DE SCRAPING DE CADA PORTAL en configs/portals/<portal>.json (estrategia, faceteo, endpoints, anti-bot, paginación) — versionada y reproducible. Criterio "completo": Σ hojas faceteo = total oficial (≥99%) + delta cableado + config guardada + verificación independiente de Guardian.

**Cobertura demostrada:** mobile.de 100% (1.586.022, no 4.4M — medido), leboncoin 100% (~900K), coches.net ~95% (afinar make-list). Cola=70 restantes. Habilitador: IP residencial Swisscom CH + camoufox (vence Akamai/DataDome/PerimeterX gratis). Ver [[goal_cardex_total_coverage]], [[goal_cardex_delta_sync]], [[feedback_no_premature_verdicts]].

**Dashboard/panel en tiempo real: DESPRIORIZADO** por Salman (2026-06-07) — foco en los 73, no en UI.
