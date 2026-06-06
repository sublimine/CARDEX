# BLOCK 0 — GIT HAZARD: diagnóstico y recomendación de consolidación

**Fecha:** 2026-06-06 · **Autor:** sesión de implementación P0 (read-only sobre el segundo checkout)
**Repo autoritativo:** `C:\Users\elias\projects\cardex` (`main @ 6e084a5`)
**Segundo checkout:** `C:\Users\elias\CARDEX` (`main @ 42dec67`)
**Naturaleza:** SOLO diagnóstico + protección. NO se tocó, borró ni mergeó el segundo checkout.
La decisión de borrado/merge es del dueño (§Recomendación). Cada cifra es `[VERIFICADO]` por comando git.

---

## 1. Veredicto en una línea

El segundo checkout **NO puede pisar `main`** (está 68 commits por detrás, **0 commits únicos** → su git rastreado es un subconjunto de `origin/main`). El riesgo real es **perder trabajo SIN commitear** que solo vive ahí: un redesign de frontend (`workspace/web`), **1 stash**, y una rama local. **Eso hay que rescatar antes de retirar el checkout.**

---

## 2. Evidencia verificada

### 2.1 Relación de historiales `[VERIFICADO]`

| Pregunta | Comando | Resultado |
|---|---|---|
| ¿`main` autoritativo contiene `42dec67`? | `git cat-file -t 42dec67` | `commit` (sí) |
| ¿`42dec67` es ancestro de `6e084a5`? | `git rev-list 42dec67..main` → contiene `6e084a5`; `merge-base 42dec67 main` = `42dec67` | **SÍ, ancestro directo** |
| Commits en `main` que NO están en `42dec67` | `git rev-list --count main..42dec67`... | **68** (el 2º está 68 detrás) |
| Commits únicos del 2º checkout (en `42dec67` y NO en `main`) | `git rev-list --count main..42dec67` | **0** |

**Conclusión:** la rama `main` del segundo checkout está **puramente rezagada**. Un `git push origin main` desde ahí sería **rechazado (non-fast-forward)**; no hay forma de que sobreescriba `origin/main` salvo un `--force` explícito (que ninguna automatización del repo ejecuta — ver §3).

### 2.2 Trabajo NO rastreado en riesgo `[VERIFICADO git status/stash/branch]`

El segundo checkout tiene contenido **que no existe en `origin`** y se perdería ante un `reset --hard`, `checkout .` o borrado de carpeta:

**Modificados (tracked, sin commitear) — redesign de la landing:**
```
 M workspace/web/src/index.css
 M workspace/web/src/pages/Landing.tsx
 M workspace/web/src/pages/landing-sections.tsx
 M workspace/web/src/pages/landing/Preloader.tsx
 M workspace/web/src/pages/landing/ShaderBackground.tsx
 M workspace/web/src/styles/tokens.css
 M workspace/web/tailwind.config.js
```

**Untracked (docs de diseño/competencia):**
```
?? workspace/web/COMPETENCIA.md
?? workspace/web/DESIGN.md
?? workspace/web/MOTIONSITES_AUDIT.md
?? workspace/web/PINTEREST_AUDIT.md
?? workspace/web/PROGRESO.md
```

**Stash:** `stash@{0}: WIP on main: 92e2bd8 chore: limpieza integral del repo`

**Rama local:** `claude/fix-critical-issue-JZ9QY` (`ecb5b65`, `[origin/claude/fix-critical-issue-JZ9QY: behind 13]`) — ya está en origin, solo rezagada. (HEAD actual del 2º checkout = `main @ 42dec67` `[VERIFICADO rev-parse]`; la rama `claude/…` coexiste pero no está checked-out.)

> El foco del segundo checkout es **frontend (`workspace/web`)**; el de este repo es **scrapers/discovery/pipeline**. No compiten por los mismos archivos → el merge del trabajo frontend es **aditivo**, no conflictivo.

### 2.2.1 Protección YA aplicada — bundle de rescate `[VERIFICADO]`

Antes de que el dueño decida, el trabajo único en riesgo se capturó en una ubicación **neutral fuera de ambos repos** (acción puramente aditiva; el árbol del 2º checkout NO se tocó):

```
C:\Users\elias\AUDIT_SCRATCH\block0_rescue\
  ├─ uncommitted_tracked.patch   (git diff HEAD — 855 líneas; los 7 .tsx/.css)
  ├─ stash_0.patch               (git stash show -p stash@{0} — 697 líneas)
  ├─ COMPETENCIA.md DESIGN.md MOTIONSITES_AUDIT.md PINTEREST_AUDIT.md PROGRESO.md  (886 líneas)
  └─ PROVENANCE.txt              (HEAD origen 42dec67, rama, fecha, contenido)
```
Restaurable con `git apply uncommitted_tracked.patch` sobre cualquier checkout. Esto **garantiza que el frontend no se pierde** aunque alguien ejecute un `reset --hard`/`pull` sucio mientras la consolidación (§4) sigue pendiente de decisión.

### 2.3 Mecanismo de auto-commit `[VERIFICADO]`

- `auto_commit_check.ps1` **solo existe en el repo autoritativo** (`projects/cardex`); **NO** en el segundo checkout (`diff` confirma ausencia). El segundo checkout no se auto-pushea.
- El script (hardcodea `cd C:\Users\elias\projects\cardex`) hace, sin intervención:
  1. `Remove-Item -Recurse -Force .claude\worktrees\*` → **borra cualquier worktree bajo `.claude\worktrees`**.
  2. `git worktree prune` + borra ramas que matcheen `claude/`.
  3. `git add scrapers/portals/... ; git add -u scrapers/portals/ ; git commit ; git push origin main`.
- No hay git hook nativo (`.git/hooks` sin hooks no-`.sample` `[VERIFICADO ls]`). El "auto-commit" es **este script PS**, no un hook.
- **Gatillo:** `schtasks /query /fo LIST /v | grep -i auto_commit` → **vacío** `[VERIFICADO]`: hoy NO hay tarea programada que lo dispare → ejecución **manual**, no automatizada. Es un arma cargada, no un disparo en curso. (También existe el doble `.pre-commit-config.{yaml,yml}` que el blueprint §0.4 marca para unificar.)

**Dos peligros operativos reales del script (independientes del 2º checkout):**
1. **Push a `main` sin review** (línea `git push origin main`), aunque acotado a `scrapers/portals`.
2. **Destrucción de worktrees** `.claude\worktrees\*` y ramas `claude/` → cualquier trabajo en curso bajo esas rutas se pierde.

---

## 3. Cómo esta sesión protege su propio trabajo

Para no caer en los peligros del §2.3, esta sesión P0:
- Trabaja **in-place en una rama dedicada `feature/p0-rewiring`** (no `claude/`, no worktree bajo `.claude\worktrees`).
- Razón doble: (a) si `auto_commit_check.ps1` se dispara, su `git commit` cae en la rama actual y su `git push origin main` empuja el **`main` local sin cambios → no-op**, así `main` queda intacto; (b) un worktree perdería los **archivos operativos untracked críticos** (`engine.db`, `.env`, contexto docker) imprescindibles para validar E2E contra el runtime vivo.
- **No commitea a `main`.** `main` permanece en `6e084a5` `[VERIFICADO git rev-parse main]`.

---

## 4. Recomendación de consolidación (decisión del dueño)

**Objetivo:** un único working-copy autoritativo, sin perder el trabajo frontend del segundo checkout.

### Paso 1 — Rescatar el trabajo no rastreado del segundo checkout (ANTES de retirar nada)
En `C:\Users\elias\CARDEX`, preservar en una rama empujable:
```powershell
cd C:\Users\elias\CARDEX
git checkout -b rescue/web-landing-redesign
git add workspace/web
git commit -m "feat(web): landing redesign + design/competition docs (rescued from 2nd checkout)"
git stash show -p stash@{0} > ../cardex-2nd-stash.patch   # exportar el stash por si acaso
git push origin rescue/web-landing-redesign
```
Luego, en el repo autoritativo, traer ese trabajo:
```powershell
cd C:\Users\elias\projects\cardex
git fetch origin
git checkout -b integrate/web-landing origin/rescue/web-landing-redesign   # revisar y mergear a main vía PR
```

### Paso 2 — Declarar un único autoritativo
`C:\Users\elias\projects\cardex` es el autoritativo (commits más recientes, todo el trabajo de scraping/pipeline, a donde apuntan sesión/CLAUDE.md/memoria). Una vez rescatado el frontend (Paso 1), `C:\Users\elias\CARDEX` puede **retirarse** (renombrar a `CARDEX.archive` o borrar) — **decisión del dueño**.

### Paso 3 — Neutralizar/gate el auto-commit (peligro persistente)
`auto_commit_check.ps1` no debería **pushear a `main` desatendido** ni **borrar worktrees** a ciegas. Opciones (elige el dueño):
- Quitar la línea `git push origin main` (commitea local, push manual tras review), **o**
- Sustituir push directo por apertura de PR, **o**
- Como mínimo, restringir el `Remove-Item .claude\worktrees\*` para que no destruya trabajo en curso.

### Paso 4 — Higiene menor (de `STATUS.md`/audit, no bloqueante)
`.fuse_hidden*` (WAL-shm huérfanos de `engine.db`), `coordinator.out.log.old`, y el doble `.pre-commit-config.{yaml,yml}` se pueden limpiar en el bloque de higiene (blueprint §Bloque 0.3/0.4), fuera del alcance de esta nota.

---

## 5. Lo que esta sesión NO hizo (por diseño)

- ❌ No borró ni movió `C:\Users\elias\CARDEX`.
- ❌ No mergeó ni pusheó su contenido.
- ❌ No ejecutó ni modificó `auto_commit_check.ps1`.
- ✅ Solo auditó (read-only), documentó, y se protegió con rama dedicada.

*Fin de la nota de Bloque 0.*
