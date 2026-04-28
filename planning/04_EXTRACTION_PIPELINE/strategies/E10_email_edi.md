# E10 — Email-Based Inventory (EDI/attachment ingestion)

## Identificador
- ID: E10, Nombre: Email-Based Inventory, Categoría: Email-EDI
- Prioridad: 200
- Fecha: 2026-04-16, Estado: IMPLEMENTADO (skeleton — Phase 4 completa la integración IMAP)

> **Nota:** El doc anterior de E10 (`E10_mobile_app_api.md`) describía una estrategia de Mobile App API
> que no se implementó. La estrategia real implementada es Email-Based Inventory (EDI).
> Mobile App API queda como trabajo futuro no priorizado (sin ID de estrategia reservado actualmente).

## Propósito y rationale

Algunos micro-dealers y dealers independientes sin presencia web envían actualizaciones de inventario
por email, adjuntando un CSV o Excel exportado de su DMS o elaborado manualmente. E10 actúa como
receptor de ese canal, procesando los adjuntos via la misma lógica de normalización que E09 (CSV/Excel).

E10 es de prioridad baja (200) porque:
- Cubre un segmento pequeño (micro-dealers sin web ni DMS con API)
- Requiere configuración previa por dealer (mapeo de email remitente ↔ dealer_id)
- La alternativa (E11 Tauri) es más robusta para este segmento

## Target de dealers

- Micro-dealers sin website de inventario online
- Dealers que ya envían CSVs a otras plataformas y pueden añadir CARDEX como destinatario
- Dealers con DMS que tiene función "export vía email" pero sin API REST
- Estimado: <3% del universo dealer total, típicamente catálogos <100 vehículos

## Arquitectura (implementada en Sprint 18 skeleton — Phase 4 completa IMAP)

```
Dealer → email con adjunto CSV/Excel → inventory@cardex.eu
       ↓
IMAP Poller (servicio separado — Phase 4)
       ↓
email_inventory_staging(dealer_id, filename, content, received_at)
       ↓
E10.Extract() — lee staging table, delega parsing a E09 logic, marca processed
```

### Identificación dealer ↔ email remitente

El knowledge graph almacena `dealer_entity.contact_email`. El IMAP poller matchea
el `From:` header del email contra este campo. Sin match → email ignorado (no enqueued).

### Parsing de adjuntos

E10 reutiliza la lógica de normalización de E09 (CSV/Excel feeds). Formatos soportados:
- CSV (UTF-8, Latin-1, delimitador configurable)
- Excel (.xlsx, .xls)
- Attached text/plain con formato tabular

### Applicable() check

E10 aplica a dealers con el hint `email_inventory` en `extraction_hints`, o cuyo
`contact_email` haya sido matcheado previamente por el IMAP poller.

## Formato de datos esperado

CSV/Excel con columnas propietarias del dealer. Normalización via YAML field mapper
(mismo patrón que E05/E09). El mapeo de columnas se define por dealer en el knowledge graph.

## Campos extraíbles típicamente

Con CSV bien estructurado: Make, Model, Year, Price, VIN, Mileage, FuelType, Transmission.
Imagen URLs: raramente incluidas en CSV; complementar con E01/E07 si el dealer también tiene web.

## Base legal

- Email enviado voluntariamente por el dealer: consentimiento implícito en el envío
- No hay scraping ni acceso no autorizado
- Retención: adjunto eliminado del staging tras procesamiento exitoso (GDPR Art. 5(1)(e))
- Base: `dealer_voluntary_submission`

## Estado de implementación

| Componente | Estado |
|---|---|
| `e10_email.go` — strategy wrapper | ✅ Implementado (Sprint 18 skeleton) |
| `Applicable()` — hint check | ✅ Implementado |
| `Extract()` — reads staging table | ✅ Implementado (returns stub when no staging rows) |
| IMAP poller (servicio separado) | 🔲 Phase 4 |
| `email_inventory_staging` DDL | 🔲 Phase 4 |
| Field mapper YAML per-dealer | 🔲 Phase 4 |

## Métricas de éxito

- `e10_emails_processed` — adjuntos de email procesados exitosamente
- `e10_vehicles_per_email` — media de vehículos por adjunto
- `e10_parse_failure_rate` — % adjuntos que no se pueden parsear (formato inesperado)
- `e10_dealer_match_rate` — % emails entrantes matcheados a un dealer conocido

## Implementación

- Módulo Go: `extraction/internal/extractor/e10_email/`
- Archivo principal: `email.go` — strategy wrapper + Applicable/Extract
- Dependencia: misma lógica de parsing que `e09_excel/`
- Coste cómputo: bajo (CSV parsing es O(n) lineal, sin red)
- Cron: extracción cada hora cuando staging table tiene filas pendientes

## Fallback strategy

Si E10 no produce resultado (staging vacío o parse failure):
- E11 (Edge Tauri): dealers que envían CSV manualmente son candidatos para el cliente Tauri,
  que automatiza el mismo flujo sin intervención manual del dealer

## Riesgos y mitigaciones

- R-E10-1: Formato CSV cambia sin previo aviso (dealer regenera con diferente DMS version).
  Mitigación: campo mapper flexible + alerta automática cuando parse_failure_rate > 20%.
- R-E10-2: Email de dealer no matcheado (cambio de dirección remitente).
  Mitigación: email de alerta al dealer pidiendo confirmación del nuevo remitente.
- R-E10-3: Adjunto con datos de clientes (PII) mezclados con inventario.
  Mitigación: PII sanitizer del pipeline corre sobre todos los AdditionalFields antes de persistir.
- R-E10-4: SPAM / phishing usando email de dealer legítimo.
  Mitigación: IMAP poller verifica DKIM/SPF; adjuntos solo de remitentes pre-registrados.
