# E12 — Manual review queue

## Identificador
- ID: E12, Nombre: Manual review queue, Categoría: Human-review
- Prioridad: 0 (última en cascada — solo cuando todo lo demás falla)
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
E12 es el receptor final de todos los dealers para los cuales E01-E11 han fallado o producido datos insuficientes. Su propósito es triple: (1) asegurar que ningún dealer de valor quede definitivamente sin indexar por razón técnica solucionable, (2) documentar estructuralmente los casos de fallo para informar el diseño de E13+ (nuevas estrategias), (3) mantener la integridad del knowledge graph descartando formalmente los dealers no indexables.

E12 no es un workaround temporal: es una componente permanente del sistema que garantiza que la cobertura continúa mejorando iterativamente y que los gaps se convierten en información accionable.

## Target de dealers
- Dealers que rechazaron E11 (no desean presencia en CARDEX actualmente)
- Dealers con site completamente bloqueado a cualquier acceso automatizado
- Dealers con situaciones inusuales (múltiples entidades legales bajo mismo dominio, dispute de identidad)
- Dealers donde la clasificación automática es incierta (¿es este operador un dealer o solo un particular?)
- Dealers en E11 con contrato en revisión legal
- Estimado: 3-8% del universo dealer necesita E12 en algún momento de su ciclo

## Sub-técnicas

### E12.1 — Queue management y priorización

Los dealers llegan a E12 desde:
- DLQ post-E11 (no contactado, no respondió, rechazó)
- Orquestador cuando todas las estrategias devuelven `FullFailure`
- Operador humano que crea una entrada manual

Atributos de priorización en la queue:
- `operational_score` del dealer (dealers activos tienen más urgencia)
- `estimated_vehicle_count` (dealers con más stock primero)
- `source_families_count` (dealers descubiertos por muchas familias = alta confianza de existencia)
- `SLA_deadline` (calculado como `entered_queue_at + 72h`)

### E12.2 — Investigación por revisor humano

El revisor recibe un briefing automático del dealer:

```
DEALER BRIEF — E12 REVIEW
─────────────────────────────────────────
Dealer ID: [ULID]
Nombre: Autohaus Müller GmbH
País: DE | Ciudad: München
Fuentes discovery: A (Handelsregister), B (OSM), G (ZDK), F (mobile.de)
Confidence score: 0.72
Operational score: 0.85
Estrategias intentadas: E01(FAILED), E02(NA), E03(FAILED), E07(BLOCKED)
Razón de fallo E03: sitemap.xml no contiene URLs vehicle
Razón de fallo E07: HTTP 403 con header "Access-Denied: automated-client"
E11 status: email enviado 2026-04-07, abierto, no respondido
Sitio web: https://autohaus-mueller.de
Google Maps: 4.6★ (312 reseñas), perfil activo
Estimado vehículos: ~80 (basado en reseñas mencionando stock)
─────────────────────────────────────────
```

El revisor investiga:
1. Visita manual del site (browser real, no bot): ¿hay inventario visible?
2. Verifica si hay estrategia no intentada (ej: link a PDF no detectado, feed en subdomain)
3. Determina si hay razón técnica solucionable o si el dealer ha decidido no ser indexado

### E12.3 — Categorías de resolución

Al concluir la revisión, el revisor registra una de las siguientes categorías:

| Código | Descripción | Acción |
|---|---|---|
| `RESOLVED_E01` | Revisor encontró JSON-LD no detectado automáticamente | Actualiza extractor E01 + indexa |
| `RESOLVED_E02` | Encontró endpoint REST no en el registry | Añade al registry E02 + indexa |
| `RESOLVED_E03` | Encontró sitemap en path no estándar | Actualiza E03 discovery paths + indexa |
| `RESOLVED_E07` | El site permite acceso manual pero bloqueó bot | Escalar a E11 con nota "site permite humanos" |
| `RESOLVED_E11` | E11 aceptado después de seguimiento manual adicional | Transferir a E11 flow |
| `DEALER_OPTED_OUT` | Dealer explícitamente solicitó no ser indexado | Añadir a `opted_out_list`, no contactar más |
| `DEALER_INACTIVE` | No hay evidencia de actividad actual | Marcar dealer como DORMANT, no indexar |
| `NO_PUBLIC_INVENTORY` | Dealer opera B2B cerrado sin catálogo público de ningún tipo | Marcar como `PRIVATE_ONLY`, escalar a E11 prospectivo |
| `NEEDS_E13` | Caso que requiere una nueva estrategia no existente | Documentar características del caso para diseño E13 |
| `CLASSIFICATION_ERROR` | No es un dealer (particular, empresa de otro sector) | Eliminar del knowledge graph |

### E12.4 — Documentación de NEEDS_E13

Los casos `NEEDS_E13` son el insumo más valioso de E12. El revisor documenta:
- Qué tipo de dealer es
- Por qué las 12 estrategias actuales no aplican
- Qué datos serían necesarios para indexarlo
- Qué fuente o técnica podría cubrir este tipo

Esta documentación alimenta el backlog de nuevas estrategias. Cuando N casos `NEEDS_E13` con características similares acumulan (umbral: 10 dealers del mismo tipo), se propone formalmente E13 como nueva estrategia.

### E12.5 — SLA y alertas

- SLA: 72 horas desde entrada en queue hasta resolución
- Alerta automática si un dealer lleva >48h sin revisor asignado
- Escalada a operador senior si revisor no puede determinar categoría en 1h de investigación
- Dashboard de métricas de queue: backlog size, SLA compliance, distribución de categorías de resolución

### E12.6 — Opted-out registry

La lista `opted_out_list` es un registro permanente de dealers que han solicitado no ser indexados. El sistema verifica este registro antes de cualquier intento de extracción futura y antes de cualquier intento de outreach E11. GDPR y buenas prácticas B2B requieren respetar estas solicitudes indefinidamente (o hasta que el dealer revoque el opt-out).

## Formato de datos esperado
E12 no extrae datos de vehículos directamente. El output de E12 son:
- Resolución categorizada del caso (ver categorías E12.3)
- Nuevos datos de extracción si el revisor encontró una vía (delegados a la estrategia correspondiente)
- Documentación para E13 si aplica

## Base legal
- La revisión manual no implica violación de ningún ToS: el revisor usa un browser normal, igual que cualquier usuario
- `DEALER_OPTED_OUT` se honra indefinidamente como obligación moral y de buenas prácticas B2B
- La documentación de casos informa diseño futuro sin usar datos del dealer sin consentimiento

## Métricas de éxito
- `e12_sla_compliance` — % casos resueltos en <72h
- `e12_resolution_distribution` — distribución de categorías de resolución
- `e12_e13_backlog` — número de casos `NEEDS_E13` acumulados (input para roadmap)
- `e12_classification_error_rate` — % dealers que resultaron ser falsos positivos del knowledge graph
- `e12_opted_out_rate` — % dealers que optan por exclusión (señal de percepción del producto)

## Implementación
- Módulo Go: `services/pipeline/extraction/strategies/e12_manual_review/`
- Sub-módulo: `queue_manager.go` — ingesta, priorización, asignación de revisores, SLA tracking
- Sub-módulo: `dealer_brief_generator.go` — generación automática del briefing para el revisor
- Sub-módulo: `resolution_handler.go` — procesamiento de categorías + trigger de acciones
- Sub-módulo: `opted_out_registry.go` — gestión del registro de opted-out permanente
- UI: panel web interno para revisores (React + API interna)
- Coste: humano — el coste es el tiempo del revisor (no compute)
- SLA: <72h por caso

## Fallback strategy
E12 no tiene fallback — es el final de la cascada. Si E12 no puede resolver un caso, el dealer queda en uno de los estados finales (DORMANT, PRIVATE_ONLY, OPTED_OUT, NEEDS_E13) hasta nuevo ciclo o nueva estrategia.

## Riesgos y mitigaciones
- R-E12-1: queue creciente sin suficientes revisores. Mitigación: priorización estricta por valor estimado + batch processing de casos similares (un revisor resuelve todos los `DMS=X bloqueado` en una sesión).
- R-E12-2: revisor comete error de clasificación (marca como OPTED_OUT un dealer que no lo solicitó). Mitigación: double-review para casos `DEALER_OPTED_OUT` + log de evidencia.
- R-E12-3: `opted_out_list` no se propaga correctamente a todos los módulos del sistema. Mitigación: chequeo centralizado en el orquestador antes de cualquier extracción; opted_out es una hard-block global.
- R-E12-4: acumulación de `NEEDS_E13` sin acción. Mitigación: alerta semanal cuando backlog E13 supera umbral → trigger de diseño de nueva estrategia.

## Iteración futura
- ML-assisted triage: clasificador de resolución probable basado en las características del dealer (reducir carga del revisor a solo los casos ambiguos)
- Integración con Familia O (press signals): si hay noticias recientes del dealer, incluirlas en el briefing
- Feedback loop: las resoluciones E12 se usan para mejorar `Applicable()` checks de E01-E11 (reducir número de dealers que llegan a E12 en primer lugar)
