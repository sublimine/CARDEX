# W4 — API + DELTA

> Carga a la base viva, calcula el delta (altas/bajas/precio/foto) con historial
> solo-append, y sirve por API con health endpoint por dealer.

## Contrato
- **Input:** stock canónico cageado (output de W3).
- **Output:** inventario servido vivo por la API per-entidad, con su delta y su
  historial. Endpoint de salud por dealer.

## Sub-fases y átomos reales (main @ 3adc857)

1. **Base viva** — PostgreSQL 16 (`cardex-pg`). Doctrina MVCC: **INSERT nuevo +
   DELETE stale, JAMÁS UPDATE de filas no mutadas** (dead tuples = fatal). Vista
   `entity_inventory` (migr. `0007`, dedup pointer/rich) = la única verdad servida.
2. **Delta solo-append** — `scrapers/delta/delta_worker.py` (always-on): aplica
   SEEN/GONE en tiempo real sobre `vehicle_events`; historial timestampeado que
   solo crece (altas, bajas, cambios de precio y de foto).
3. **API per-entidad** — `services/entity_api/app.py` (FastAPI :8088):
   - `GET /v1/entities?country=&kind=&tier=` — catálogo con `inventory_count` vivo.
   - `GET /v1/entities/{ulid}` — ficha + `inventory_count` + `delta_24h`.
   - `GET /v1/entities/{ulid}/inventory` — **el stock vendible de UN dealer**.
   - `GET /v1/entities/{ulid}/delta?since=` — altas/bajas de ese dealer.
   - `GET /v1/health` — liveness + conteo de entidades (health global).
4. **Alertas + auto-reparación** — tabla `operator_alerts` + dispatcher de
   remediación: si un dealer cae, salta alerta con el ORIGEN exacto y se intenta
   re-detectar la receta (W2) sin tumbar la línea.

## GATE W4 (binario)
**PASA** si y solo si:
- [ ] el dealer responde por `/v1/entities/{ulid}/inventory` con su stock real,
- [ ] el `inventory_count` del catálogo == el servido por la ficha == el de psql
      (quórum triple — ya validado hoy: pouw.nl 1727, autohoogenboom.nl 857),
- [ ] el delta refleja altas/bajas reales, no artefactos de scraping,
- [ ] **cero falsos "baja"**: un fallo de extracción NO marca coches como vendidos.

**NO PASA** → alerta en `operator_alerts` con origen exacto; el dealer se congela
en su último estado bueno (no se borra inventario por un fallo de scraping).

## V4 — Verificador independiente
- **Cero falsos baja** (el invariante crítico): `scripts/verify_entity_caging.py`
  + observación directa de una muestra. Una "baja" solo es real si el coche
  desapareció del portal, NO si la extracción falló. Se valida contra la web real
  en una muestra antes de confiar en cualquier GONE masivo.
- **Quórum triple del conteo**: API catálogo == API ficha == psql vista.
- Veredicto a `verification_verdicts`.
