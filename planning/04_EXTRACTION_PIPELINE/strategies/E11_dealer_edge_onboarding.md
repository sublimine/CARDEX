# E11 — Dealer Edge onboarding (cliente Tauri gratuito)

## Identificador
- ID: E11, Nombre: Dealer Edge onboarding, Categoría: Active-onboarding
- Prioridad: 100
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
E11 es la estrategia de última milla para dealers que las estrategias automatizadas E01-E10 no pueden indexar — ya sea porque no tienen website, porque su site bloquea crawlers, porque su DMS es completamente privado, o porque simplemente no tienen presencia digital estructurada. En lugar de rendirse o violar controles de acceso, CARDEX ofrece al dealer un cliente desktop gratuito (Tauri) que, una vez instalado, actúa como puente entre el DMS local del dealer y la plataforma CARDEX vía EU Data Act data delegation.

El modelo de negocio es mutuamente beneficioso:
- El dealer obtiene visibilidad gratuita en CARDEX sin necesidad de cambiar su DMS ni crear un website
- CARDEX obtiene acceso estructurado y consentido al inventario del dealer
- La base legal es explícita: EU Data Act + consentimiento contractual B2B

**NO aplica en CH:** Suiza no es miembro de la UE. El EU Data Act no tiene efecto en CH. Para dealers suizos en esta situación, E11 se reemplaza por E12 (manual review) o contrato B2B ad hoc sin invocar el EU Data Act.

## Target de dealers
- Dealers sin website o con website estático sin inventario online
- Dealers cuyo site bloquea crawlers (E07 falla por bloqueo)
- Dealers con DMS completamente privado (ninguna API expuesta)
- Dealers que rechazaron ser indexados pero cuyo consentimiento se puede obtener via outreach
- Dealers long-tail descubiertos por Familias K/L/M/O pero no indexados por E01-E10
- Estimado: 15-25% del universo dealer long-tail (dealers más pequeños y menos digitalizados)

## Sub-técnicas

### E11.1 — Dead letter queue processing

El input de E11 es la `dead_letter_queue` del orquestador: dealers para los cuales E01-E10 han fallado. Los dealers en DLQ son priorizados por:
- `operational_score` (dealers activos primero)
- `estimated_vehicle_count` (dealers con más stock primero)
- `country_code` (prioridad por fase de rollout)

### E11.2 — Outreach automatizado via email

Para cada dealer en DLQ:
1. Email discovery: el knowledge graph contiene emails extraídos de sites, directorios, Google Maps
2. Email template en idioma del dealer (DE/FR/ES/NL — detectado por `country_code`)
3. Propuesta de valor concisa: visibilidad gratuita en CARDEX sin cambios en su sistema actual
4. Link único de tracking (saber si el dealer abrió el email)
5. CTA: descarga del cliente Tauri gratuito

Templates de email:
- DE: `"Ihr Fahrzeugbestand kostenlos sichtbar machen"`
- FR: `"Rendez votre stock visible gratuitement"`
- ES: `"Haz visible tu inventario gratis"`
- NL: `"Maak uw voorraad gratis zichtbaar"`

Cadencia: email inicial + 1 follow-up a los 7 días si no hay respuesta. Máximo 2 contactos por dealer antes de escalar a E12.

### E11.3 — Cliente Tauri (desktop application)

El cliente Tauri es una aplicación desktop open-source (Rust backend + webview frontend):

Funcionalidades:
- Autenticación del dealer con CARDEX (OAuth2 PKCE)
- Conexión al DMS local:
  - Lectura directa de base de datos SQLite/Access local del DMS
  - Import de CSV/Excel export manual del DMS
  - Plugin para DMS populares: EasyCar, DealerPoint (common en dealers FR/ES independientes), SalesPoint
- Exportación incremental: solo envía VINs/vehículos nuevos o modificados desde último sync
- Control total del dealer: puede pausar, seleccionar qué vehículos publicar, cancelar en cualquier momento
- Datos transmitidos: solo campos de inventario (no datos de clientes, no datos financieros privados)

Arquitectura del cliente:
- Tauri + SvelteKit (UI)
- Rust (backend: DMS connectors, delta sync, HTTPS push a CARDEX API)
- Payload firmado con dealer's private key (CARDEX verifica)

### E11.4 — EU Data Act consent flow

El onboarding del cliente Tauri incluye:
1. Presentación del Data Sharing Agreement (DSA) en idioma del dealer
2. Firma digital del DSA (checkbox + timestamp + IP)
3. Especificación explícita de qué datos se comparten (inventario de vehículos únicamente)
4. Derecho de revocación en cualquier momento (botón en el cliente)
5. Retención: datos solo mientras el dealer esté activo en CARDEX

Base legal del DSA:
- EU Data Act Art. 4 (Data holder obligation to share data on request of data recipient)
- Contrato B2B explícito con consentimiento informado
- Reglamento (EU) 2023/2854

### E11.5 — Push API del cliente hacia CARDEX

El cliente Tauri hace push via HTTPS POST a la CARDEX Ingestion API:

```
POST /api/v1/dealer/{dealer_id}/inventory
Authorization: Bearer {dealer_token}
Content-Type: application/json

{
  "vehicles": [...VehicleRaw format...],
  "sync_timestamp": "2026-04-14T10:00:00Z",
  "delta_mode": true,
  "removed_vins": ["WBAXXX...", ...]
}
```

La Ingestion API valida la firma, procesa el payload, y actualiza el knowledge graph.

## Formato de datos esperado
JSON push desde el cliente Tauri hacia la CARDEX Ingestion API. Formato: `VehicleRaw` canónico (definido en INTERFACES.md). El cliente Tauri hace la normalización local antes del push.

## Campos extraíbles típicamente
Con DMS connector funcionando: todos los campos que el DMS del dealer tiene, potencialmente el set más completo de todos (incluyendo historial de mantenimiento si el dealer lo tiene en su DMS y decide compartirlo).

## Base legal
- EU Data Act: delegación de acceso a datos de negocio con consentimiento explícito
- Contrato B2B DSA firmado digitalmente
- Consentimiento informado + derecho de revocación
- NO aplica en CH (Suiza fuera de EU)
- Base: `eu_data_act_delegation` + `b2b_contract`

## Métricas de éxito
- `e11_outreach_open_rate` — % dealers que abrieron el email
- `e11_conversion_rate` — % dealers contactados que instalan el cliente
- `e11_retention_rate` — % clientes Tauri activos tras 90 días
- `e11_mean_vehicles_per_client` — catálogo aportado por dealer Edge
- `e11_coverage_contribution` — % del total dealer universe cubierto vía E11

## Implementación
- Módulo Go (Ingestion API): `services/pipeline/extraction/strategies/e11_edge_onboarding/`
- Cliente Tauri: repositorio separado `apps/dealer-edge/` (Rust + SvelteKit)
- Sub-módulo: `dlq_processor.go` — lectura de DLQ + priorización
- Sub-módulo: `outreach_sender.go` — email templates + cadencia + tracking
- Sub-módulo: `ingestion_api.go` — recepción de push del cliente, validación firma, dispatch
- Sub-módulo: `dsa_manager.go` — gestión de DSAs firmados, revocaciones
- Coste cómputo: bajo en CARDEX (push API es lightweight); coste es en outreach + soporte del cliente
- Cron: DLQ processing diario, outreach batch semanal

## Fallback strategy
Si E11 no logra conversión (dealer no responde o rechaza):
- E12 (Manual review queue): análisis humano para determinar si hay alguna vía de acceso no explorada o si el dealer debe quedar fuera del índice temporalmente

## Riesgos y mitigaciones
- R-E11-1: baja tasa de conversión de outreach. Mitigación: A/B testing de templates, mejora continua del copy, prueba social (dealers ya en plataforma como referencia).
- R-E11-2: cliente Tauri con bugs en connectors para DMS poco comunes. Mitigación: soporte por email + DMS agnostic CSV/Excel import como fallback universal.
- R-E11-3: dealer revoca consentimiento (baja del servicio). Mitigación: proceso de baja inmediato en cliente (botón único), TTL en todos los vehículos expirado en 24h post-revocación.
- R-E11-4: EU Data Act invocado incorrectamente. Mitigación: revisión legal del DSA por abogado especializado EU Data Act antes del launch de E11.
- R-E11-5: CH dealers sin cobertura legal EU Data Act. Mitigación: E12 directo para CH dealers + contrato B2B ad hoc si hay interés.

## Iteración futura
- Integraciones DMS adicionales en el cliente Tauri (nuevos connectors por demanda)
- API de webhook opcional para dealers con DMS cloud que prefieren push automático
- White-label del cliente Tauri para asociaciones sectoriales (ej. AGVS CH distribuye el cliente a sus 4.000 miembros)
- Modelo de marketplace inverso: dealers que usan E11 reciben analytics gratuitos de su catálogo via CARDEX
