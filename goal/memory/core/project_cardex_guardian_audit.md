---
name: project_cardex_guardian_audit
description: Sistema permanente de auditoría continua y anti-fugas de CARDEX (Guardian) — se despliega al cerrar las tareas activas y corre tras cada tarea larga
metadata: 
  node_type: memory
  type: project
  originSessionId: 020fe92e-3d59-49f4-9abe-f0ad36acb37d
---

Directiva de Salman (2026-06-06): montar y desplegar un **sistema integral de supervisión anti-fugas** ("Guardian"). Es el "trabajo extra" (como barrer la tienda cuando no hay clientes): se construye con calma cuando no hay faena urgente y queda desplegado para SIEMPRE.

**Cuándo corre:** tras CADA tarea larga, auditoría integral automática; además, supervisión activa permanente (no se desactiva aunque el Guardian exista).

**Qué audita — con LÓGICA, no solo wiring:**
1. **Integridad de cobertura (la clave):** por portal/fuente, comparar extraído vs total real anunciado. Si hay gap (p.ej. 20K extraídos cuando el portal tiene 500K), razonar el porqué (paginación capada, anti-bot, filtro mal puesto, segmentación incompleta) y proponer/ejecutar la vía para cerrar los 480K que faltan. Esto se aplica a cada portal y cada fuente.
2. **Integridad de datos:** probar muestras de listings — ¿se extraen todos los campos? ¿corrupción, duplicados, nulos, normalización correcta?
3. **Integridad de pipeline:** cada etapa conectada sin fugas productor↔consumidor (tipo bug enrich_worker/streams).
4. **Eficiencia y organización:** ¿se puede filtrar/indexar/organizar mejor? ¿estructuras y consultas eficientes?
5. **No regresión:** tests verdes, nada roto.
6. **Higiene:** worktrees/ramas/artefactos limpios, disco bajo validar-límite-purgar.

**Cómo:** equipo de subagentes auditores (uno por dimensión) + orquestador que consolida en informe con veredicto por componente y remediación priorizada; razonamiento adversarial (un agente intenta refutar "está completo"). Nada inventado; lo no verificable, marcado. Modelo justo por auditor; criterio crítico en Opus.

**Estado:** diseño entregado a Salman (doc `GUARDIAN_AUDIT_SYSTEM.md`). Implementación PENDIENTE: desplegar cuando terminen las tareas actuales (P0, NL, dashboard). Ver [[feedback_zero_excuses_ownership]], [[goal_cardex_total_coverage]], [[project_cardex_architecture]].
