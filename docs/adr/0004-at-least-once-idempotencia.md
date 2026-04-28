# ADR-0004 — Garantía at-least-once con idempotencia obligatoria en consumers

**Fecha**: 2026-04-27 (redacción retroactiva de decisión vigente)
**Estado**: Vigente
**Owner**: Salman Karrouch

---

## Contexto

El bus de eventos sobre Redis Streams (ADR-0001) ofrece varias opciones de garantía de entrega. La elección impacta el diseño de cada consumer y la complejidad del sistema completo.

Requisitos:
- Cero pérdida de eventos en condiciones de fallo recuperable (consumer caído, reinicio).
- Tolerancia a duplicados controlada por diseño de consumer.
- Operación predecible bajo presión de carga sin requerir coordinación distribuida costosa.

## Opciones evaluadas

**At-most-once**:
- Pros: simple, sin gestión de ACK.
- Contras: pérdida de eventos garantizada en cualquier crash. Inaceptable.

**Exactly-once con coordinador externo**:
- Pros: cada evento procesado exactamente una vez.
- Contras: requiere transacción distribuida entre Redis y PG, complejidad operativa alta, no nativo en Redis Streams.

**At-least-once con consumers idempotentes**:
- Pros: nativo en Redis Streams, simple de implementar, robusto ante crash.
- Contras: cada consumer debe diseñarse para tolerar duplicados — disciplina de diseño obligatoria.

## Decisión

Adoptar **at-least-once con idempotencia obligatoria por contrato**:
- Todo consumer procesa cada mensaje hasta XACK explícito.
- Procesar el mismo mensaje N veces no produce efectos secundarios duplicados.
- Idempotencia se implementa por una de tres vías según el consumer:
  - Identificador único en el mensaje + INSERT con `ON CONFLICT DO NOTHING`.
  - Hash de contenido + lookup previo a la escritura.
  - Operación intrínsecamente idempotente (UPSERT semántico, set-based).

## Consecuencias aceptadas

- Cada consumer nuevo requiere documentación explícita de su mecanismo de idempotencia en el código.
- Tests de idempotencia obligatorios: el suite debe incluir un caso "procesar el mismo mensaje dos veces" y verificar invariancia del estado.
- Dead-letter queue tras N reintentos exponenciales. DLQ no se reprocesa automáticamente; requiere intervención manual y registro en INCIDENTS.md (RUNBOOKS RB-003).
- Mensajes pendientes (PEL) se monitorizan como métrica primaria.

## Fecha de revisión

Cuando se requiera exactly-once para un caso de uso específico (ej. cargo económico), evaluar si justifica coordinador transaccional para ese flujo concreto sin alterar el resto.
