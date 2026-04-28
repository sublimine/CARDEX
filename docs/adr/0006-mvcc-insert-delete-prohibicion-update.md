# ADR-0006 — Política MVCC: INSERT nuevo + DELETE stale, prohibición de UPDATE

**Fecha**: 2026-04-27 (redacción retroactiva de decisión vigente)
**Estado**: Vigente
**Owner**: Salman Karrouch

---

## Contexto

PostgreSQL implementa MVCC creando una nueva versión de fila en cada UPDATE y marcando la anterior como dead tuple, recolectada por VACUUM. En tablas de alto volumen con UPDATEs frecuentes, esto produce:
- Bloat acumulado entre VACUUMs.
- Degradación de planes de query.
- Carga sostenida sobre VACUUM autovacuum.
- Coste de I/O amplificado.

CARDEX procesa volúmenes de listings que crecen con la cobertura territorial (objetivo: 100% de 6 países UE). Las tablas centrales (`listings`, `vehicles`, `fiscal_classifications`) están sometidas a presión de actualización constante: cambios de precio, cambios de estado, deduplicación.

Adicionalmente, la trazabilidad fiscal exige auditoría completa: una `FiscalClassification` no se sobrescribe — toda decisión queda registrada con su prompt y modelo (CLAUDE.md §17).

## Opciones evaluadas

**UPDATE estándar**:
- Pros: semántica intuitiva, una fila por entidad lógica.
- Contras: dead tuples masivos, bloat, pérdida de auditoría histórica, coste creciente con el volumen.

**UPDATE con tabla de auditoría aparte**:
- Pros: auditoría preservada.
- Contras: mantiene el problema de dead tuples en la tabla principal, duplica writes.

**INSERT + soft-delete (DELETE lógico vía `deleted_at`)**:
- Pros: cero UPDATE de filas no mutadas, auditoría completa por construcción, dead tuples solo en operaciones de DELETE de stale.
- Contras: queries deben filtrar por `deleted_at IS NULL` por convención.

## Decisión

Adoptar **política INSERT-only con soft-delete por `deleted_at`** para entidades de dominio (`listings`, `vehicles`, `fiscal_classifications`, `nlc_quotes`, `sdi_signals`):
- Cambio de estado o de campo: nuevo INSERT con timestamp, fila anterior marcada con `deleted_at`.
- `last_seen` obligatorio en toda entidad que pueda quedar obsoleta.
- UPDATE permitido solo en columnas explícitamente declaradas mutables (ej. flags operacionales internos), nunca en columnas de dominio.
- UPDATE de filas no mutadas: prohibido absoluto. Si una operación generaría una fila idéntica a la existente, es no-op explícita.

## Consecuencias aceptadas

- Convención de query: filtros por `deleted_at IS NULL` o vista materializada que lo encapsule.
- Borrado físico solo en operaciones administrativas declaradas, nunca en flujo de dominio.
- Auditoría histórica completa por construcción: cada cambio queda como nueva fila trazable.
- Anti-patrón en CLAUDE.md §27: cualquier UPDATE de fila no mutada se flaggea como violación.
- Hook de enforcement (PreToolUse) detecta patrones `UPDATE\s+\w+\s+SET` en código Go nuevo.

## Fecha de revisión

Cuando una entidad concreta demuestre coste de soft-delete superior al de UPDATE controlado, evaluar excepción documentada en su propio ADR. No revisar la política global.
