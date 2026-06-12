# ADR-0007 — Separación estricta Spider / Reaper / Indexer como microservicios independientes

**Fecha**: 2026-04-27 (redacción retroactiva de decisión vigente)
**Estado**: Superseded por la realidad (2026-06-12) — ver nota de estado
**Owner**: Salman Karrouch

---

> **NOTA DE ESTADO (2026-06-12) — NO IMPLEMENTADO tal como se describe.** Los tres
> binarios Go (`cmd/spider`, `cmd/reaper`, `cmd/indexer`) nunca existieron como código
> (cf. `STATUS.md`, BUG-004: el "Reaper" jamás existió). El concepto de separación de
> responsabilidades sobrevive dentro de la flota Python viva (ingesta del coordinator
> y portales; purga vía harnesses slice-then-purge; enriquecimiento vía Redis Streams),
> pero no como microservicios Go. Se conserva este ADR como registro inmutable de la
> decisión, superado por la realidad. Verdad viva: `README.md` + `STATUS.md`.

---

## Contexto

El pipeline de CARDEX maneja tres responsabilidades fundamentalmente distintas sobre el inventario de listings:
- **Ingestión** desde fuentes externas (scraping y normalización).
- **Purga** de listings obsoletos o duplicados.
- **Sincronización** y deduplicación entre fuentes.

Combinar dos o tres de estas responsabilidades en un único servicio produce:
- Acoplamiento entre escalado de scraping y escalado de purga (operaciones con perfiles de carga distintos).
- Bugs de cross-contamination: un fallo en purga afecta ingestión.
- Dificultad de razonar sobre invariantes (cuándo un listing debe existir, cuándo debe purgarse).
- Complejidad de testing aislado por responsabilidad.

## Opciones evaluadas

**Servicio monolítico de pipeline**:
- Pros: menor footprint operativo, una sola unidad de despliegue.
- Contras: acoplamiento de responsabilidades, escalado uniforme aunque las cargas sean asimétricas, bugs de interferencia.

**Microservicios por responsabilidad**:
- Pros: cada servicio escala según su perfil de carga, invariantes claras por boundary, testing aislado, recuperación independiente ante crash.
- Contras: más servicios que orquestar, comunicación vía Redis Streams en lugar de llamadas in-process.

## Decisión

Adoptar **separación estricta en tres microservicios**:
- **Spider**: solo ingesta de listings desde fuentes externas. Publica eventos a stream `listings.scraped`.
- **Reaper**: solo purga de listings obsoletos o duplicados. Consume `listings.indexed`, publica `listings.reaped`.
- **Indexer**: solo sincroniza y deduplica. Consume `listings.scraped`, publica `listings.indexed`.

Boundary inviolable: ningún consumer importa código de otro consumer. La comunicación es exclusivamente vía streams.

## Consecuencias aceptadas

- Escalado independiente: si Spider necesita más throughput, se escala solo Spider.
- Crash de un servicio no detiene los otros (ver RUNBOOKS RB-002 sobre recovery).
- Anti-patrón en CLAUDE.md §27: mezclar responsabilidades entre los tres es violación inmediata flaggeable.
- Tests de integración: cada microservicio se testea contra streams reales, no contra los otros servicios.
- Despliegue: tres binarios Go separados (`go run ./cmd/spider/`, `./cmd/reaper/`, `./cmd/indexer/`).
- ADR vinculado: ADR-0001 (Redis Streams como bus que conecta los tres).

## Fecha de revisión

No procede revisión salvo que un perfil de carga radicalmente nuevo justifique fusión. La separación es estructural.
