# ADR-0001 — Redis Streams como bus de eventos sobre Kafka y NATS

**Fecha**: 2026-04-27 (redacción retroactiva de decisión vigente)
**Estado**: Vigente
**Owner**: Salman Karrouch

---

## Contexto

CARDEX necesita un bus de eventos para desacoplar Spider, Reaper, Indexer, classifier y gateway. Los requisitos:
- At-least-once delivery con consumers idempotentes.
- Consumer groups con tracking de mensajes pendientes.
- Reintentos automáticos con backoff y dead-letter queue.
- Operación local en Docker Compose sin orquestación pesada.
- Throughput sostenido de decenas de miles de eventos por minuto en pico de scraping.
- Coste operativo cero en fase pre-MVP.

## Opciones evaluadas

**Apache Kafka**:
- Pros: estándar industrial, throughput superior, particionado avanzado, ecosistema maduro.
- Contras: complejidad operativa (Zookeeper o KRaft), coste de infraestructura, sobreingeniería para el volumen actual, curva de aprendizaje.

**NATS JetStream**:
- Pros: ligero, Go-nativo, persistencia opcional, baja latencia.
- Contras: ecosistema más pequeño, menos battle-tested para el caso de uso, herramientas de inspección menos maduras.

**Redis Streams**:
- Pros: ya tenemos Redis para otros usos, consumer groups con XACK/XPENDING, operación trivial en Docker, herramientas de inspección estándar (`redis-cli`), throughput suficiente para el horizonte.
- Contras: persistencia atada al modelo de Redis, no soporta nativamente exactly-once.

## Decisión

Adoptar **Redis Streams** como bus de eventos para todo el pipeline.

## Consecuencias aceptadas

- Garantía declarada: at-least-once. Todo consumer es idempotente por contrato.
- Reintentos exponenciales con tope; tras N fallos → stream `*.dlq`. DLQ no se reprocesa automáticamente.
- Cambio breaking de schema exige nuevo topic, no mutación. Consumers en flight no se rompen.
- Migración a Kafka queda como opción de futuro si el throughput supera la capacidad de Redis.

## Fecha de revisión

2026-10-27 o cuando el throughput sostenido supere 50K eventos/minuto.
