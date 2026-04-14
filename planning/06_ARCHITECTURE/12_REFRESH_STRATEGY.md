# Refresh Strategy — Política asimétrica de actualización

## Identificador
- Documento: 12_REFRESH_STRATEGY
- Versión: 1.0
- Fecha: 2026-04-14
- Estado: AUTORITATIVO

## Propósito
Definir la política de refresh de registros del índice CARDEX de forma que la latencia de detección de cambios (baja de listing, cambio de precio, nuevas altas) sea mínima para los vehículos de alto valor de negocio, mientras se respeta el presupuesto de recursos del VPS y los rate limits de las fuentes. La estrategia es **asimétrica por tier**, no uniforme.

## Rationale
Refresh uniforme cada 4-6h (baseline inicial) es óptimo para el coste pero subóptimo para el buyer que está decidiendo sobre un vehículo concreto en ese momento. Un buyer que abre un listing que se vendió hace 3 horas erosiona la confianza en la plataforma. Al mismo tiempo, refrescar cada 15 minutos el stock long-tail completo es prohibitivo en un VPS €22/mes y agresivo con los sources.

La solución: **el recurso de refresh se asigna según el valor de negocio del vehículo en ese momento**, no uniformemente.

## Tiers de refresh

### Tier HOT — high-intent, refresh 5-15 min
**Qué entra:** vehículos con al menos una de estas señales en las últimas 2 horas:
- Click/view en el terminal CARDEX
- Saved/bookmarked por un buyer
- Listing abierto en un terminal ahora mismo (presence detection via SSE)
- Aparece en ≥3 search results recientes

**Volumen esperado:** <5% del índice en cualquier momento (~0.5-2% típico).

**Frecuencia de re-check:** 5 min para listings actualmente abiertos, 15 min para el resto del tier.

**Presupuesto:** ~80 requests/min sostenidos max (within rate limits at source).

### Tier WARM — recent/relevant, refresh 1-2h
**Qué entra:**
- Vehículos listados en los últimos 7 días (nuevos en el índice)
- Vehículos con ≥5 views acumuladas en los últimos 30 días
- Vehículos en segmentos de alta rotación (premium <50k km, compacts <3 años, comerciales light)

**Volumen esperado:** 15-25% del índice.

**Frecuencia:** 60-120 min.

### Tier COLD — long-tail, refresh 4-8h
**Qué entra:** el resto. Vehículos sin actividad reciente, stock antiguo, segmentos de baja rotación.

**Volumen esperado:** 70-80% del índice.

**Frecuencia:** 4-8h según carga del VPS (scheduler ajusta dinámicamente para respetar budget).

### Tier ON-DEMAND — active buyer validation
**Trigger:** buyer abre un listing específico en el terminal CARDEX.

**Comportamiento:**
- Si `last_confirmed_at < 30 min`: servir inmediato, pipeline TTL ya garantiza freshness.
- Si `last_confirmed_at ≥ 30 min` y ≤ TTL: re-fetch sincrónico con timeout 8s antes de servir.
- Si source devuelve `SOLD`/`WITHDRAWN`/`404`: invalidar estado inmediato, mostrar al buyer "vendido" con sugerencia de alternativas similares.

**Impacto esperado:** <2% de listings abiertos necesita re-fetch sincrónico (la mayoría caen en la ventana <30 min por Tier HOT/WARM).

### Tier PUSH — dealer con Edge client instalado
**Qué entra:** vehículos del catálogo de dealers que han instalado el Edge client (Fase P3 del roadmap, bajo EU Data Act delegation).

**Frecuencia:** push realtime desde el DMS del dealer cuando ocurre cambio. Latencia <1 min end-to-end.

**Coste CARDEX:** cero incremental (es el dealer quien push).

**Coste source:** cero (no hay source ajena, es el dealer mismo).

**Objetivo a largo plazo:** migrar máximo dealers posibles a este tier. Meta: ≥30% de dealers activos en Edge tras 12 meses de P3 operativo.

## Promoción/democión entre tiers

Cada vehículo tiene un `tier` campo calculado dinámicamente. Scheduler re-evalúa cada 15 min:

```
if has_signal_last_2h(vehicle):
    tier = HOT
elif age_in_index < 7d or views_30d >= 5 or high_rotation_segment:
    tier = WARM
elif dealer_has_edge_client:
    tier = PUSH
else:
    tier = COLD
```

## Arquitectura técnica

### Componentes nuevos
- **Refresh Scheduler** (nuevo módulo Go en `scheduler/`): corre cada minuto, lee `vehicle_record.tier` + `last_confirmed_at`, decide qué vehículos refetch en este tick, publica jobs a NATS queue `cardex.refresh.{tier}`.
- **Refresh Workers** (poolsize diferenciado por tier): consumen jobs, ejecutan re-extraction (reutilizan strategies E01-E12 con flag `refresh_mode=true` que solo busca deltas, no full catalog).
- **Buyer Activity Tracker** (en API Service): emite events a NATS `cardex.buyer.activity` cuando hay view/click/save. El scheduler consume estos events para promover vehículos a HOT inmediatamente.
- **TTL diferenciado** en `vehicle_record`:
  - HOT: TTL 45 min
  - WARM: TTL 3 h
  - COLD: TTL 12 h
  - PUSH: TTL 24 h (el push es la freshness real; el TTL es solo fallback)

### Schema adicional

```sql
ALTER TABLE vehicle_record ADD COLUMN tier TEXT NOT NULL DEFAULT 'COLD';
ALTER TABLE vehicle_record ADD COLUMN last_buyer_activity_at TIMESTAMP;
ALTER TABLE vehicle_record ADD COLUMN view_count_30d INTEGER DEFAULT 0;
ALTER TABLE vehicle_record ADD COLUMN refresh_priority INTEGER;  -- derived, re-computed every 15min

CREATE INDEX idx_vehicle_tier_ttl ON vehicle_record(tier, ttl_expires_at);

CREATE TABLE refresh_job (
  job_id TEXT PRIMARY KEY,
  vehicle_id TEXT NOT NULL REFERENCES vehicle_record(vehicle_id),
  tier TEXT NOT NULL,
  scheduled_at TIMESTAMP NOT NULL,
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  outcome TEXT,  -- CONFIRMED | CHANGED | EXPIRED | ERROR
  duration_ms INTEGER
);

CREATE INDEX idx_refresh_job_tier_status ON refresh_job(tier, completed_at);
```

### Rate limit budget por tier

Asignación total del VPS: ~150 requests/min efectivos cross-hosts (tras factoring rate limits per host).

| Tier | Budget | Rationale |
|---|---|---|
| HOT | 60 req/min | ~1-2% del índice, refresh 5-15min → ~3000-6000 refreshes/h |
| WARM | 60 req/min | ~20% del índice, refresh 1-2h → ~60k-120k refreshes/día |
| COLD | 30 req/min | ~75% del índice, refresh 4-8h — más lento pero volumen enorme |
| ON-DEMAND | burstable ad-hoc | no counted en budget steady, solo picos |

Budget ajustable dinámicamente: si HOT queue está vacía, el presupuesto libera a WARM/COLD. Scheduler optimiza según carga real.

## Métricas Prometheus nuevas

```
cardex_refresh_job_duration_seconds{tier}  # histogram
cardex_refresh_job_outcome_total{tier, outcome}
cardex_refresh_queue_depth{tier}           # gauge
cardex_refresh_tier_distribution{tier}     # gauge: % del índice en cada tier
cardex_refresh_budget_utilization{tier}    # gauge: % del budget consumido
cardex_refresh_on_demand_latency_seconds   # histogram de re-fetch sincrónico
cardex_refresh_staleness_p99_seconds{tier} # freshness SLA por tier
```

## Alertas

| Regla | Condición | Severity |
|---|---|---|
| RefreshBudgetExceeded | `budget_utilization{tier="HOT"} > 95%` 5min sostenido | WARNING |
| StalenessBreached | `staleness_p99{tier="HOT"} > 1800` (30min) | CRITICAL |
| OnDemandLatencyHigh | `on_demand_latency p99 > 8s` | WARNING |
| ColdTierStarved | `queue_depth{tier="COLD"}` creciendo sostenidamente | WARNING |

## SLA de freshness por tier

| Tier | Freshness p99 objetivo |
|---|---|
| HOT | <20 min |
| WARM | <3 h |
| COLD | <12 h |
| PUSH | <3 min |
| ON-DEMAND (on listing open) | <8 s |

## Fallback ante sobrecarga

Si el VPS no puede sostener el budget total:
1. Demote tier HOT → WARM temporalmente para los vehículos con menor activity score dentro de HOT
2. Alert ColdTierStarved → operador evalúa upgrade a VPS CX51 (€32/mes) según criterios S1 del escalado
3. Circuit breaker: si un host específico está emitiendo 429 repetidamente, scheduler pausa refresh para ese host, flag para investigación (posible cambio en rate limit source)

## Interacción con NLG batch (V19)

El NLG es nocturno batch. Cuando un vehículo tier HOT cambia precio o specs, el pipeline:
1. Actualiza facts en vehicle_record (inmediato)
2. Mantiene description_generated_ml actual (válida si los facts críticos — make/model/year — no cambian)
3. Si cambian facts críticos que invalidan la descripción, marca `description_needs_regen=true` → entra en queue NLG prioritaria
4. Fallback temporal a template determinístico hasta que NLG genera la nueva

Esto evita batches masivos innecesarios y permite que HOT tier tenga descriptions válidas sin re-generar todas las noches.

## Path de evolución

### S0 (actual, lean)
Budget 150 req/min, tiers HOT/WARM/COLD/ON-DEMAND, sin PUSH (todavía no hay Edge dealers onboardeados).

### S1
+PUSH tier al activar Edge client masivamente en Fase P3. Budget scheduler aprende del patrón push para reducir COLD pulls redundantes.

### S2
Budget x2 (VPS upgrade), tier HOT baja a refresh 3 min, se añade tier BURST (sub-minute para buyer actualmente en sesión activa con listing abierto).

### S3
Cluster multi-worker, sharding por país, Edge dealers >30% → mayoría de refresh pasa a push, CARDEX ejecuta principalmente validation/consistency checks y long-tail COLD.

## Criterios de éxito (CS-REF) para Fase P5

```promql
# CS-REF-1: Freshness HOT p99 < 20 min durante 30 días consecutivos
cardex_refresh_staleness_p99_seconds{tier="HOT"} < 1200

# CS-REF-2: On-demand re-fetch p99 < 8s durante 30 días
histogram_quantile(0.99, cardex_refresh_on_demand_latency_seconds) < 8

# CS-REF-4: Budget utilization sostenido <90% en todos los tiers
max(cardex_refresh_budget_utilization) < 0.90
```

```sql
-- CS-REF-3: Zero SOLD vehicles mostrados como ACTIVE por más de 30 min en Tier HOT
SELECT COUNT(*)
FROM vehicle_record
WHERE tier = 'HOT'
  AND status = 'ACTIVE'
  AND last_confirmed_at < DATETIME('now', '-30 minutes');
-- Resultado esperado: 0
```

## Consideraciones éticas y legales

- Rate limits de fuentes respetados siempre. Si source emite 429, retry exponencial + reducción de frecuencia automática para ese host.
- Tier HOT no rompe R1 (legalidad): sigue siendo pull con CardexBot/1.0 UA identificable, simplemente con mayor frecuencia dentro del límite respetuoso.
- Buyer activity tracking es first-party (terminal CARDEX propio), no tracking cross-site. Sin implicaciones GDPR adicionales más allá de las ya documentadas.
- Ningún host recibe carga >1 req/3s sostenida. El tier HOT opera sobre subconjunto distribuido across muchos hosts, no concentrado en un solo source.
