---
name: feedback_zero_excuses_ownership
description: "Cero excusas, responsabilidad total del orquestador; auto-monitoring, alertas y auto-recuperación que YO monto"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 020fe92e-3d59-49f4-9abe-f0ad36acb37d
---

Salman exige **cero excusas** ("se cayó el agente", "se desactivó tal", "perdimos 4 horas" están prohibidos como justificación). El orquestador asume la **responsabilidad total** de que todo funcione.

**Implicación concreta:** al diseñar el workflow, YO mismo monto el sistema de **alertas/monitoring** de modo que cuando algo se cae, se detecte, se audite la causa raíz y se resuelva — idealmente con auto-recuperación. La supervisión "activa 24/7" se materializa como **procesos automatizados (watchdogs, healthchecks, cron, reintentos, logging)** que construyo en la máquina/VPS, NO como mi atención literal continua (matiz honesto: entre mensajes yo no proceso; la vigilancia continua la dan los sistemas que monto).

**Why:** un proyecto institucional no puede depender de babysitting manual ni morir por un fallo no detectado.
**How to apply:** toda arquitectura nueva incluye desde el diseño: healthchecks, reintentos con backoff, dead-letter/cola de fallos, logging estructurado y alertas. Ver [[feedback_orchestration_active]] y [[project_cardex_architecture]].
