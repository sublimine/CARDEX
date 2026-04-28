# Syndication Engine — Multi-Platform Publishing

**Sprint:** 41  
**Package:** `workspace/internal/syndication/`  
**Status:** Complete

## Problem

Dealers need to publish vehicle listings to multiple European platforms simultaneously.
Each platform has its own data format (XML feed, REST API, CSV import) and validation rules.
Manual management across 6+ platforms is error-prone and slow.

## Architecture

```
SyndicationEngine
├── PublishVehicle(ctx, vehicleID, listing, []platformNames)
│     └── Platform.Publish() → external_id, external_url
│           ├── mobile_de        → XML feed (ADD action)
│           ├── autoscout24      → XML feed (insert action)
│           ├── autoscout24_be   → XML feed (insert action, BE variant)
│           ├── autoscout24_ch   → XML feed (insert action, CH/CHF variant)
│           ├── leboncoin        → CSV export + no-op API stub
│           ├── coches_net       → XML feed
│           ├── universal_csv    → generic CSV fallback
│           └── universal_xml    → generic XML fallback
│
├── WithdrawVehicle(ctx, vehicleID)   ← also called on sold/reserved state
├── SyncAll(ctx)                       ← Scheduler: every 30 min
└── RetryErrors(ctx, getListing)       ← Scheduler: every 1 hour (max 3 retries)

Scheduler
├── Run(ctx) — background goroutine
└── OnVehicleStateChange(ctx, vehicleID, newState)
      → withdraws on "sold" or "reserved"

crm_syndication table
  UNIQUE(vehicle_id, platform)
  status: pending | published | withdrawn | error
  retry_count, next_retry_at (exponential backoff: 1h → 2h → 4h)

crm_syndication_activity table
  event: published | syndication_withdrawn | publish_error | retry_published
```

## Supported Platforms

| Platform         | Country | Format     | Notes |
|-----------------|---------|------------|-------|
| mobile.de       | DE, AT  | XML feed   | ADD/CHANGE/DELETE actions; max 30 photos |
| AutoScout24     | DE      | XML feed   | insert/update/delete; max 50 photos |
| AutoScout24 BE  | BE      | XML feed   | Same adapter, Belgian variant |
| AutoScout24 CH  | CH      | XML feed   | Same adapter, Swiss variant; CHF currency |
| leboncoin       | FR      | CSV export | No public dealer API; CSV portal import |
| coches.net      | ES      | XML export | No public dealer API; XML portal import |
| universal_csv   | *       | CSV        | Fallback for any platform |
| universal_xml   | *       | XML        | Fallback for any platform |

## Data Flow

```
CRM vehicle record
        │
        ▼
  formatter.go  ←  NormaliseFuelType, NormaliseTransmission, TruncatePhotos
        │
        ▼
  description.go ← GenerateDescription(lang, data)
        │            templates: DE/FR/ES/NL/EN
        │            AI override field reserved for future NLG
        ▼
  PlatformListing
        │
        ├──► ValidateListing()  — pre-flight check before API call
        │
        └──► Platform.Publish() → (external_id, external_url)
                    │
                    ▼
           crm_syndication  (upsert)
           crm_syndication_activity (append)
```

## Retry Strategy

Failed publications use exponential backoff:
- Attempt 1: retry after 1 hour
- Attempt 2: retry after 2 hours  
- Attempt 3: retry after 4 hours
- After 3 attempts: record stays `status=error`, no further retries

## Auto-Withdraw

When `Scheduler.OnVehicleStateChange(ctx, vehicleID, "sold")` is called:
1. Query all `status=published` rows for the vehicle
2. Call `Platform.Withdraw()` for each
3. Update `status=withdrawn`, set `withdrawn_at`
4. Log activity event `syndication_withdrawn`

## Prometheus Metrics

| Metric | Type | Labels |
|--------|------|--------|
| `workspace_syndication_published_total` | Counter | platform, status |
| `workspace_syndication_errors_total`    | Counter | platform, error_type |
| `workspace_syndication_latency_seconds` | Histogram | platform |
| `workspace_syndication_active_listings` | Gauge | platform |

## Integration with Sprint 40

Sprint 40 provides `workspace/internal/model/`, `storage/`, `handler/`.
The syndication engine depends only on `*sql.DB` and a `getListing` callback,
so it integrates with Sprint 40 without code changes to existing adapters.

Wiring point in Sprint 40's workspace service:
```go
engine, _ := syndication.NewEngine(store.DB(), log)
scheduler := syndication.NewScheduler(engine, func(id string) (syndication.PlatformListing, error) {
    v, err := store.GetVehicle(ctx, id)
    // ... map CRM vehicle to PlatformListing
    return listing, err
}, log)
go scheduler.Run(ctx)
// Hook into CRM state changes:
scheduler.OnVehicleStateChange(ctx, vehicleID, newState)
```

## Roadmap

- **Live API integration:** When mobile.de and AutoScout24 grant API access, replace the XML
  feed generation in `Publish()` with authenticated REST calls; the adapter interface stays unchanged.
- **NLG descriptions:** When AI description generation is available, populate
  `PlatformListing.Description` via `DescriptionData.AIGeneratedDescription` before calling
  the adapter.
- **More platforms:** marktplaats.nl (NL), autovit.ro (RO), otomoto.pl (PL) — add adapters,
  register in `init()`.
- **Webhook ingestion:** Receive sold/delisted callbacks from platforms to keep status in sync
  without polling.
