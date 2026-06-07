---
name: cardex-estado-junio-2026
description: "Estado de CARDEX tras la jornada hands-off del 2026-06-06/07; main consolidado en 830bf5d, P0+NL+dashboard+Guardian hechos, P1 en curso"
metadata: 
  node_type: memory
  type: project
  originSessionId: 020fe92e-3d59-49f4-9abe-f0ad36acb37d
---

**Estado a 2026-06-07** (jornada hands-off orquestada por Dispatch). Repo: `C:\Users\elias\projects\cardex`.

**Veredicto Guardian (auditoría adversarial, `GUARDIAN_REPORT_2026-06-06.md`):** CARDEX es un **esqueleto VALIDADO, no un producto poblado**. Fontanería probada; datos del producto ≈0%. "508K listings" = URLs sin atributos; "30 vehicles" = SEED_DEMO; "RDW done" = 1,2% del censo NL; resiliencia = andamiaje sin cablear.

**Git (estado FINAL jornada 2026-06-07):**
- `main` CONSOLIDADO en **`1ca158a`** con los **8 frentes**: P0 + P1 + fan-out 5 países + E07 (inventario SPA) + dealer-scraping a medida + domain-resolution + discovery-scale + P2-hardening. **Suite 1.439 verde** (de 1.246 → 1.439, cero regresiones en toda la cadena).
- **`origin/main` sigue en `6e084a5` — NO pusheado** (le faltan los 8 frentes; push = ÚNICA acción irreversible pendiente, decisión de Salman).
- Cada frente auditado por Guardian (revisión adversarial + rollback armado; main nunca roto). Progresión: 6e084a5→830bf5d(P0)→6e0be32(fanout)→b980f90(E07)→72b31d5(dealer)→6219527(domain-res)→7a03433(discovery-scale)→1ca158a(P2).
- P2-hardening cerró los cabos: trigger auto-remediación cableado, anti-FP 6 idiomas+word-boundary, tests cola worker, reclaim cap/DLQ, migración BEGIN/COMMIT. Fila FP histórica `Artcar` purgada.

**MÉTRICA DEL GOAL — dealers CON WEB: 28.570 → 45.864 (+60,5%)** (DE 26.653 · NL 6.898 · CH 4.026 · ES 1.747 · FR 5.293 · BE 1.247). Censo total: 460.930 → **685.572 filas**. Cuello para seguir a 900K: (1) CONVERSIÓN a escala del censo domain-NULL (FR=568K filas/5.293 web → mayor yacimiento) con el `worker.py` del resolver ya en main; (2) proxies/VPS para directorios protegidos (BE/ES Incapsula) y gigantes anti-bot. Fuentes libres host-safe agotadas.
- **Block0 hazard VIVO:** segundo checkout `C:\Users\elias\CARDEX` @ `42dec67` con frontend único sin commitear; protegido con bundle de rescate; consolidación pendiente de Salman.
- Cautelas vigentes: ruido CRLF↔LF del mount (nunca `git add .`); `.git/index.lock` huérfano se borra solo desde host.

**Hecho esta jornada:** P0 (enrich_worker+streams, API healthy, soft-block fix que corregía corrupción de datos, entity-res); vertical NL clavado (fuente RDW 300 dealers reales de ~24.700; seam L1→L2 verificado E2E en autotrack.nl/viabovag.nl bajo validar-límite-purgar); dashboard abrible (`dashboard/cardex_control.html`, auto-refresh 15min en host); Guardian desplegado. Suite: **1.246 verde**.

**P1 HECHO y consolidado** (reclaim cola Redis/H1, moneda CHF para CH —212.524 filas corregidas—, autovacuum + partición `vehicle_events`, drift-gate cableado al coordinator vivo, 72.225 "camiones" DE purgados). Sistema endurecido: con las fugas cerradas, el backfill de los 436K y el arranque sostenido a escala ya pueden correr (cuando Salman dé la orden / en VPS).

**Cobertura real:** 26,7% de los 20 portales activos; 51 de 71 portales en CERO (gigantes gated por proxy → backlog P3). Discovery aún FR-dominante hasta abanicar NL→5 países (receta en `NL_VERTICAL_REPORT.md`).

**Backlog declarado:** E07 playwright-XHR para dealer-SPAs; OEM locators para dominios; proxies tier-1 (P3, requiere $). Ver [[goal_cardex_total_coverage]], [[project_cardex_guardian_audit]], [[project_cardex_resilience]].
