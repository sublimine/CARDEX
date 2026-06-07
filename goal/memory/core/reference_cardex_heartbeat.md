---
name: reference_cardex_heartbeat
description: Tarea programada heartbeat de supervisión orquestadora de CARDEX (cada 15 min)
metadata: 
  node_type: memory
  type: reference
  originSessionId: 020fe92e-3d59-49f4-9abe-f0ad36acb37d
---

Existe una tarea programada **`cardex-heartbeat-supervisor`** (creada 2026-06-06, cron `*/15 * * * *`) que materializa el hands-off de CARDEX salvando el límite de que Dispatch no procesa entre turnos ([[feedback_dispatch_active_wait]]). Cada latido: audita las sesiones (list_sessions/read_transcript), desbloquea/relanza, limpia worktrees zombies, y avanza el plan maestro (P0 → vertical NL → abanicar 6 países → romper monocultivo FR → dealers). Archivo: `C:\Users\elias\Claude\Scheduled\cardex-heartbeat-supervisor\SKILL.md`.

Caveats: corre solo mientras la app esté abierta (si cerrada, se ejecuta al próximo arranque); la autonomía 24/7 real es terreno de la VPS. Pre-aprobar permisos con "Run now" una vez evita pausas por permisos en latidos futuros. Ver [[project_cardex_architecture]] y [[reference_repo_path]].
