# CARDEX — RUNBOOKS

<!-- Procedimientos operativos. Cada runbook: trigger, precondiciones, pasos verificables, criterio de éxito, rollback. -->
<!-- Esqueleto inicial. Cada runbook se completa al primer ejecutarlo en producción real. -->

---

## RB-001 — Arranque limpio del stack local

**Trigger**: tras reboot del host, tras cambio en docker-compose.yml, o al iniciar sesión de desarrollo.

**Precondiciones**:
- Docker Desktop arrancado.
- Variables de entorno cargadas en el shell (consultar fichero local de configuración).
- Puertos 8081 y 8082 libres para llama.cpp y nomic.

**Pasos**:
1. `docker compose down --remove-orphans` para limpiar contenedores residuales.
2. `docker compose up -d` para arrancar PG, Redis, ClickHouse, llama.cpp, nomic.
3. Verificar healthchecks: `docker compose ps` — todos en `healthy`.
4. Verificar llama.cpp: `curl http://localhost:8081/health` debe responder 200.
5. Verificar nomic: `curl http://localhost:8082/health` debe responder 200.
6. Arrancar consumers en orden: gateway → ingestion → classifier → reaper → indexer.
7. Cada consumer: `go run ./cmd/<módulo>/` en terminal separada.

**Criterio de éxito**: todos los servicios responden a healthchecks y los consumers no producen errores en los primeros 60 segundos.

**Rollback**: `docker compose down`, identificar el servicio que falla, revisar logs.

---

## RB-002 — Recovery tras crash de consumer

**Trigger**: consumer Go cae con panic, hang, o exit no controlado.

**Precondiciones**: el resto de consumers siguen operando.

**Pasos**:
1. Identificar el consumer caído por logs estructurados (correlation_id, último mensaje procesado).
2. Verificar el estado del consumer group: `redis-cli XINFO GROUPS <stream>`.
3. Si hay mensajes pendientes (PEL no vacío): registrar IDs antes de reiniciar.
4. Reiniciar el consumer: `go run ./cmd/<módulo>/`.
5. Verificar que el consumer reanuda desde el último ACK, no desde 0.
6. Si el panic fue por dato malformado: ese mensaje debe llegar a `*.dlq` tras N reintentos, no bloquear el consumer.

**Criterio de éxito**: consumer procesa nuevos mensajes y el lag del stream decrece.

**Rollback**: si el panic se repite con el mismo mensaje, mover manualmente el mensaje a `*.dlq` y registrar en INCIDENTS.md.

---

## RB-003 — Procesamiento manual de DLQ

**Trigger**: crecimiento sostenido de un stream `*.dlq` o alerta operativa.

**Precondiciones**: causa raíz del fallo identificada y corregida en código.

**Pasos**:
1. Listar mensajes en DLQ: `redis-cli XRANGE <stream>.dlq - +`.
2. Identificar patrón común: schema corrupto, dato inválido, o bug ya corregido.
3. Si el bug está corregido en código y desplegado: re-publicar mensajes al stream original.
4. Si el dato es genuinamente irrecuperable: documentar en INCIDENTS.md y borrar del DLQ.
5. Verificar que los mensajes re-publicados se procesan correctamente.

**Criterio de éxito**: DLQ vacío o reducido al subset de mensajes con datos genuinamente irrecuperables.

**Rollback**: si el reproceso vuelve a generar fallos, devolver al DLQ y abrir incidente.

---

## RB-004 — Rotación del modelo de clasificación fiscal

**Trigger**: actualización del modelo Qwen, prueba de modelo alternativo, o ajuste de cuantización.

**Precondiciones**:
- ADR redactado justificando el cambio.
- Banco de pruebas con clasificaciones de referencia preparado.
- Ventana de mantenimiento declarada.

**Pasos**:
1. Backup del modelo actual y de los prompts en su versión vigente.
2. Ejecutar el banco de pruebas contra el modelo nuevo en puerto alternativo (no :8081).
3. Comparar precisión contra la baseline: divergencia > 2% requiere análisis antes de proceder.
4. Drenar el stream de clasificación hasta lag = 0.
5. Detener llama.cpp en :8081 y arrancar el modelo nuevo en :8081.
6. Reanudar el classifier consumer.
7. Monitorizar tasa de error y divergencia durante las primeras 1000 clasificaciones.

**Criterio de éxito**: tasa de error igual o inferior a baseline, divergencia clasificatoria documentada y aceptada.

**Rollback**: detener llama.cpp, restaurar modelo previo desde backup, reanudar consumer.

---

## RB-005 — Investigación de listing con clasificación fiscal anómala

**Trigger**: usuario reporta clasificación incorrecta o auditoría detecta divergencia.

**Pasos**:
1. Recuperar el listing por ID: `SELECT * FROM listings WHERE id = ?`.
2. Recuperar la `FiscalClassification` asociada con su trazabilidad: prompt exacto, modelo, fecha, score.
3. Re-ejecutar el clasificador contra el listing original para comprobar reproducibilidad.
4. Si la clasificación cambia entre ejecuciones: bug de no-determinismo. Abrir incidente SEV-2.
5. Si la clasificación es estable pero incorrecta: bug en prompt o en modelo. Abrir issue de prompt-engineering.

**Criterio de éxito**: causa raíz identificada y registrada como bug en STATUS.md o como incidente en INCIDENTS.md.

---

## Pendientes de redactar

- RB-006: Onboarding de nueva fuente de scraping.
- RB-007: Sustitución de proveedor de datos tras ban.
- RB-008: Migración de schema PG con consumers en flight.
- RB-009: Restauración de PG desde backup.
- RB-010: Auditoría de coherencia entre PG y ClickHouse.
