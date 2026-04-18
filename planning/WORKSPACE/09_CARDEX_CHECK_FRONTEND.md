# Sprint 50 — CARDEX Check Frontend

**Branch:** `main` (atomic commits)
**Module:** `workspace/web/src/pages/Check.tsx` + associated components
**Build:** zero TS errors · zero warnings

---

## Overview

Public-facing vehicle history report interface. Requires no authentication — accessible at `/check` and `/check/:vin` for direct linking. Integrates with the future `GET /api/v1/check/{vin}` backend endpoint.

---

## File Map

```
workspace/web/src/
├── types/
│   └── check.ts                    — VehicleReport, CheckError, DataSource etc.
├── hooks/
│   └── useCheck.ts                 — Fetch + state machine for VIN lookups
├── components/
│   ├── VINInput.tsx                — Real-time validated VIN input
│   ├── AlertCard.tsx               — Alert card (critical/warning/info)
│   ├── Timeline.tsx                — Reusable vertical timeline
│   ├── ScoreGauge.tsx              — SVG semicircular gauge (0-100)
│   └── SourceBadge.tsx             — Data source row with status icon
├── pages/
│   ├── Check.tsx                   — Public page shell + routing logic
│   └── check/
│       ├── CheckLanding.tsx        — Hero + VIN input + VIN guide
│       └── CheckReport.tsx         — Full report display
└── layout/
    ├── Shell.tsx                   — + VIN Check in sidebar nav
    └── MobileNav.tsx               — + Check tab (replaces More)
```

---

## Routes

| Path | Auth | Description |
|---|---|---|
| `/check` | Public | Landing page with VIN input |
| `/check/:vin` | Public | Auto-fetches report for VIN in URL |

Both routes render `CheckPage` outside the `ProtectedRoute` wrapper.

---

## Data Flow

```
URL param :vin
    │
    ▼
useCheck(initialVin)
    │  GET /api/v1/check/{vin}
    │  → loading, report, error states
    ▼
CheckPage
    ├── loading  → ReportSkeleton (animated pulse)
    ├── error    → RateLimitError (countdown) | GenericError
    ├── report   → CheckReport
    └── idle     → CheckLanding
```

---

## VehicleReport Schema

```typescript
interface VehicleReport {
  vin: string
  generatedAt: string             // RFC3339
  overallStatus: 'clean' | 'attention' | 'alerts'
  vinDecode: VINDecodeResult      // Make, model, year, fuel, body…
  alerts: VehicleAlert[]          // stolen, recall_open, mileage_inconsistency
  inspections: InspectionRecord[] // Date, pass/fail, km, next date
  recalls: RecallEntry[]          // Campaign, component, open/closed
  mileageHistory: MileageRecord[] // Date + km + isAnomaly flag
  mileageConsistencyScore?: number // 0-100; undefined if <3 records
  dataSources: DataSource[]       // success/partial/unavailable/requires_owner
}
```

---

## Components

### VINInput
- Strips non-VIN characters on input (no I, O, Q)
- Forces uppercase
- Green check icon when valid · Red X with char count when invalid
- `onSubmit` fires on Enter if valid

### ScoreGauge
- Pure SVG semicircle, no external library
- Colour: green (≥80) / yellow (≥50) / red (<50)
- CSS transition on `stroke-dashoffset` for smooth animation
- Shows score centred inside arc

### Timeline
- Dot + vertical line pattern
- Accent colour per item (green/red/yellow/blue/gray)
- Empty-state message when no items

### AlertCard
- Three severity levels with distinct colour schemes
- Type icon (car=stolen, rotate=recall, trending-down=mileage)
- Source attribution footer

### SourceBadge
- Four status icons: ✅ success / ⚠ partial / ✗ unavailable / 🔒 requires_owner
- Shows record count when available
- Transparency note below the list

---

## Error Handling

| HTTP Status | Code | UI |
|---|---|---|
| 400 | `invalid_vin` | Inline error on landing |
| 404 | `not_found` | GenericError + landing below |
| 429 | `rate_limit` | Countdown timer; retry button unlocks at 0 |
| 5xx / network | `server_error` | GenericError + landing |

---

## Navigation Integration

- **Desktop sidebar:** "VIN Check" entry with `FileSearch` icon (between Finance and Settings)
- **Mobile bottom tabs:** Replaces "More" tab with "Check" + `FileSearch` icon — keeps 5 tabs

Note: `/check` is outside `ProtectedRoute`, so clicking "VIN Check" from the authenticated shell navigates to the public page without triggering the auth guard.

---

## SEO / Shareability

- `document.title` updated: `{Make} {Model} {Year} — CARDEX Check` when report is loaded
- URL updates via React Router `navigate()` when search is triggered
- Clipboard copy of shareable URL via `Share2` button
- Download PDF button present but disabled (TODO: backend endpoint)

---

## Internationalisation

Strings are hardcoded in Spanish (primary market). Structure is ready for future i18n:
- Dates via `Intl.DateTimeFormat` with `navigator.language`
- Numbers via `Intl.NumberFormat`
- All UI strings are literals, not interpolated — easy extraction via i18n tooling

---

## Pending (backend)

- `GET /api/v1/check/{vin}` — not yet implemented
- Rate-limiting middleware
- PDF generation endpoint (`/api/v1/check/{vin}/pdf`)
