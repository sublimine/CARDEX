# CARDEX — STATUS

<!-- Estado vivo del sistema. Volátil. Commits propios, prefijo status: -->
<!-- Snapshot 2026-04-27. Bugs verificados contra el repo. Memoria histórica conservada como hipótesis a re-validar. -->
<!-- Última actualización por owner: pendiente. -->

---

## Bugs activos (verificados contra el repo 2026-04-27)

| ID | Componente | Síntoma | Workaround temporal | Prioridad |
|---|---|---|---|---|
| BUG-001 | `e2e/go.mod` y `services/api/go.mod` | `replace github.com/cardex/alpha => ../alpha` ambiguo: desde `e2e/` resuelve a `CARDEX/alpha` (path inexistente), desde `services/api/` resuelve a `services/alpha/` (correcto). `go build` reporta `conflicting replacements for github.com/cardex/alpha` | Ajustar el replace en `e2e/go.mod` a `=> ../services/alpha` para alinear con la estructura real | **Crítica — bloquea build cross-module** |
| BUG-002 | `services/pipeline/cmd/pipeline/main.go:12` | Import `"fmt"` declarado. Verificar si está sin uso una vez resuelto BUG-001 y el módulo compile | Eliminar import si efectivamente sin uso | Baja |
| BUG-003 | Pipeline Go (memoria institucional) | Drop silencioso de payloads OEM en algunos paths del pipeline | Bypass directo a PG via INSERT explícito | Alta — re-validar contra el código actual tras BUG-001 |
| BUG-004 | Componente conceptual "Reaper" (purga de listings obsoletos) | Hangs intermitentes documentados en sello 2026-04-10. Nota: no existe directorio `reaper/`; función ejecutada por uno de los workers de `services/pipeline/cmd/worker/` o `scheduler` | Reinicio manual del consumer afectado | Media — re-validar y mapear a su componente real |

## Bloqueadores

Ninguno declarado a fecha 2026-04-27. Auditar contra el estado del repo y abrir entradas si aplica.

## Deuda técnica priorizada

| ID | Área | Descripción | Impacto cuantificado |
|---|---|---|---|
| TECH-001 | Observabilidad | Auditoría pendiente: qué consumers tienen `slog` implementado y cuáles no | Sin correlación distribuida hasta resolver |
| TECH-002 | ADRs | 8 ADRs declarados en CLAUDE.md §31 pendientes de redacción formal | Memoria institucional ausente |
| TECH-003 | Tests de integración | Cobertura por debajo de los umbrales declarados (70% dominio / 50% consumers) | Riesgo de regresión en cambios al pipeline |
| TECH-004 | RUNBOOKS | Procedimientos operativos no formalizados | Recovery ante incidente requiere reconstrucción |
| TECH-005 | Schemas de eventos | Versionado de eventos publicados a Redis Streams sin contrato formal | Cambio breaking sin migración planificada |

## Pipeline — estado conocido

- Última tirada productiva referenciada: 2026-04-10 — 1,55M vehículos indexados.
- 9 fuentes nuevas añadidas en ventana autónoma 2026-04-10.
- Enricher v3.1 en operación.
- 26 tests añadidos en la ventana sellada.
- Lista de paths abandonados documentada en el sello de 2026-04-10.

## Restricciones operativas activas

- **Windows + Application Control**: prohibido compilar a `.exe`. Ejecutar siempre con `go run ./cmd/<módulo>/`.
- **MVCC PG**: solo `INSERT` nuevo + `DELETE` stale. `UPDATE` de filas no mutadas prohibido (genera dead tuples).
- **Redis**: solo Streams. Estado de inventario en Redis prohibido.
- **ClickHouse**: OLAP-only. Sin escritura directa desde flujo crítico.
- **JA3 coherence**: mismo fingerprint TLS de página 1 a N en cada sesión de scraping.
- **Browsers**: solo con stealth activo. Sin stealth = ban.

## Dependencias externas críticas

- Proveedores de scraping de listings (rotación 90d).
- llama.cpp local en :8081 (Qwen2.5-Coder-7B Q5_K_M) — clasificación fiscal.
- nomic-embed-text local en :8082 — embeddings.
- PostgreSQL 16, Redis Streams, ClickHouse vía Docker Compose.

## Trabajo en curso

Pendiente de declarar por owner. Esta sección se actualiza al inicio y al cierre de cada sesión.
