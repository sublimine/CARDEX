---
name: feedback-worktree-cleanup
description: Always clean up worktrees after code tasks finish — never leave zombie sessions or accumulated worktrees
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f40b2fe4-7b98-4b15-bea1-af705c3e870f
---

NUNCA dejar worktrees acumulados. Después de cada code task que termine, limpiar el worktree y la branch correspondiente. El usuario tuvo que borrar manualmente 65+ worktrees TRES VECES porque Dispatch no los limpiaba.

**Why:** Los worktrees acumulados saturan el sistema y bloquean nuevas code tasks. El usuario perdió horas borrando sesiones zombie manualmente. Esto es inaceptable.

**How to apply:** 
1. Después de que una code task termine, verificar que su worktree se limpió
2. Si quedan worktrees huérfanos, incluir `git worktree prune` y `Remove-Item .claude\worktrees\<name>` en la siguiente code task
3. Nunca lanzar más de 3 code tasks simultáneas — el sistema se satura
4. Configurar `--dangerously-skip-permissions` en el PC del usuario para eliminar prompts de permisos
5. La limpieza de worktrees es responsabilidad MÍA, no del usuario

Related: [[feedback_full_perms_no_ask]], [[feedback_total_hands_off]]
