---
name: Repo CARDEX — path Windows
description: Location of CARDEX repository, remote, conventions
type: reference
originSessionId: f40b2fe4-7b98-4b15-bea1-af705c3e870f
---
Repo principal: `C:\Users\elias\projects\cardex` (Windows, máquina de Salman).
Remote: `origin` → github.com/sublimine/cardex (privado).

Convención de ramas:
- `sprint/NN-<slug>` para sprints nuevos
- `audit/track-N-<slug>` para tracks de auditoría
- `fix/<slug>` para correcciones
- Mensajes Conventional Commits (feat, fix, chore, test, docs)

Nota técnica: `start_code_task` en Dispatch tiene timeouts recurrentes en este repo por la cantidad de worktrees. Preferible `send_message` a sesiones idle existentes cuando sea posible.

Backend port: :8506. Frontend dev: :5173 (Vite).
