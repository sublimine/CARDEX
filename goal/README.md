# `goal/` — Contexto del proyecto integrado al repositorio

Esta carpeta vuelca a Git, en Markdown, el contexto de CARDEX que hasta ahora
vivía solo en la memoria persistente del agente. Objetivo: que la **misión, el
estado y los estándares de trabajo** viajen con el repositorio y no dependan de
una memoria externa.

> La fuente de verdad de la **arquitectura y qué existe** sigue siendo
> `CONTEXT_FOR_AI.md` + el código. Esto es contexto de **objetivo/estado/método**,
> no una redefinición de la arquitectura.

## Estructura

```
goal/
├── GOAL.md                 Síntesis: GOAL #1, estado, estándares, arquitectura, refs
├── README.md               (este fichero)
└── memory/
    ├── core/               Contexto duradero (objetivo, estándares, arquitectura, refs)
    │   ├── INDEX.md
    │   ├── goal_cardex_total_coverage.md   ← el GOAL en bruto
    │   ├── project_cardex_*.md             (estado, arquitectura, resiliencia, guardian, infra, …)
    │   ├── feedback_*.md                   (15 ficheros: cómo se opera)
    │   ├── reference_*.md                  (repo, heartbeat, APIs [redactado])
    │   └── user_salman_cardex.md           (atribución del operador)
    └── fronts/             Estado por frente de trabajo + auditorías GUARDIAN
        ├── MEMORY.md                       índice detallado del set
        ├── project_p0_execution_state.md … project_p2_hardening.md
        ├── project_*_audit_2026_06_07.md   (veredictos GUARDIAN por frente)
        ├── project_stealth_giants_free.md, project_discovery_*, project_dealer_*, …
        └── feedback_execute_dont_ask.md
```

## Procedencia

Dos sets de memoria complementarios, copiados **verbatim** salvo las redacciones
indicadas abajo:

- **`memory/core/`** ← memoria del agente (`agent/memory/`). El contexto
  duradero: el objetivo, los estándares (feedback), la arquitectura objetivo, la
  estrategia de infraestructura y las referencias.
- **`memory/fronts/`** ← memoria de proyecto del repo
  (`.claude/projects/.../memory/`). El registro de ejecución por frente
  (P0, P1, fan-out, E07, dealer-scraping, domain-resolution, discovery-scale,
  P2, stealth, ollama, …) con sus auditorías GUARDIAN adversariales.

`GOAL.md` y `memory/core/INDEX.md` son material **nuevo de síntesis** escrito al
integrar; el resto es copia fiel de las memorias.

## Exclusiones (honestidad sobre lo que NO está aquí)

Se han **excluido a propósito** 3 ficheros de la memoria del agente que
pertenecen a **otro proyecto** (Habana Legacy — CRM de un distribuidor suizo de
relojes, repo `sublimine/habana-legacy`): `project_habana_legacy.md`,
`project_habana_pending.md`, `reference_repo_habana.md`. No son contexto de
CARDEX e introducirían información de otro repositorio.

## Redacciones de seguridad

Antes de integrar se escaneó todo el volcado en busca de secretos. Redactado:

- **Dev-password de desarrollo** → `<REDACTED-dev-password>` en
  `memory/fronts/project_discovery_scraping_runtime.md` y
  `memory/fronts/project_storage_reality.md`. (Es un *default* de desarrollo que
  ya figura en `docker-compose.yml` del repo; se redacta en estas copias por
  higiene, para no multiplicar su aparición.)
- **Identificadores personales** en `memory/core/reference_api_credentials.md`:
  cuenta de email, GCP project id y token id → `<REDACTED-…>`. Ese fichero nunca
  contuvo claves de API en texto plano (los valores reales viven en vault/env);
  se preserva **qué API existe y su estado**, nunca el secreto.

Verificación: `grep` sobre las copias de memoria (`goal/memory/`) no devuelve
ninguna ocurrencia del dev-password ni direcciones de email.
