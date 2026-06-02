# CARDEX — CLAUDE.md
<!-- Deltas de repo. Hereda la doctrina global (~/.claude/CLAUDE.md). No la repite. -->
<!-- Comportamiento: lo dicta el global. Arquitectura: la dicta CONTEXT_FOR_AI.md. -->

## Autoridad
- **Comportamiento** (cómo trabajo): la doctrina global manda.
- **Arquitectura y qué existe**: `CONTEXT_FOR_AI.md` es la fuente de verdad —
  léelo antes de tocar nada. Tras él, en orden: el código, `deploy/`,
  `planning/`, y `SPEC.md` (visión original, parcialmente superada).
- Este archivo **no describe arquitectura**. Si alguna vez lo hiciera,
  `CONTEXT_FOR_AI.md` gana. No hay precedencia invertida.

## Entorno — no negociable
- **Windows + Application Control**: nunca compiles a `.exe`. Ejecuta con
  `go run ./cmd/<módulo>/`.
- **Build/test de los módulos core** (`discovery`, `extraction`, `quality`):
  siempre `GOWORK=off`. Nunca dependas de la resolución del workspace.
- **Constraints operativas** (UA por capa, robots.txt, rate limit, integridad
  SQLite, secretos fuera de git): `CONTEXT_FOR_AI.md` §"Non-negotiable
  constraints". No se duplican aquí.

## Estado vivo
Bugs activos, bloqueadores y deuda priorizada: `STATUS.md`. Léelo en el
handshake de inicio de sesión.
