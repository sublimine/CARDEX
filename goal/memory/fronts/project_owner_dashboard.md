---
name: project-owner-dashboard
description: Panel de control del dueño (HTML autocontenido) + tarea de auto-refresco viva en el host
metadata: 
  node_type: memory
  type: project
  originSessionId: 407ff08f-21d5-47a2-8f14-958c42950f27
---

Panel de control para el dueño en `dashboard/` (rama `feature/p0-rewiring`, commits 35fc841 + 8cb6e57).

**Qué es:** HTML autocontenido (`dashboard/cardex_control.html`, gitignored) generado por `dashboard/generate.py`, que lee el estado REAL en vivo: PG (`docker exec psql`), Redis (`redis-cli`), SQLite `scrapers/engine.db` (solo-lectura), y `docker ps`. Módulos: `collectors.py` (datos), `render.py` (HTML), `reference.py` (hechos citados del audit: gigantes, topes, estrategias). Sin deps (solo stdlib Py3), sin secretos hardcodeados (credenciales autodescubiertas del contenedor).

**Auto-refresco:** tarea Windows `CARDEX Dashboard Refresh` REGISTRADA y ACTIVA en el host (`register_refresh.ps1`, cada 15 min, P3650D, verificada LastTaskResult=0x0). Parar: `unregister_refresh.ps1`. Vista on-demand: `open_dashboard.ps1`. NO usa scheduler de Cowork (aislado, no llega a la DB).

**Por qué HTML y no Grafana:** Prometheus solo se scrapea a sí mismo (`/api/v1/targets` = 1 target) → Grafana no ve datos de negocio sin construir exporters; además `work_queue`/crawler viven en SQLite del host que Grafana no lee. Grafana/Prometheus quedan como capa ops complementaria.

**Hallazgo clave que muestra el panel:** el monocultivo FR NO está en listings (ahí domina CH 42%, FR es el menor 2,2%) sino en discovery_candidates (FR 84%, fuente SIRENE). El seam L1→L2 está commiteado pero INERTE (vehicles=30 seed, streams Redis vacíos). Ver [[project_blueprint_target_arch]] y [[project_audit_2026_06_06]].
