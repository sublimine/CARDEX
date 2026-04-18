# CARDEX Web Dashboard — Sprint 47

## Overview

Full-featured React 18 SPA deployed as a PWA, providing mobile-native-first
dealer CRM access. Targets the workspace-service REST API at `:8506`.

**Location:** `workspace/web/`
**Build:** `npm run build` → `dist/` (static files, serve from Caddy)
**Dev proxy:** `vite dev` proxies `/api/` → `localhost:8506`

---

## Stack

| Layer | Technology |
|---|---|
| Framework | React 18.3 + TypeScript 5.5 |
| Styling | Tailwind CSS 3.4 (utility-first, dark mode via `class`) |
| Routing | React Router v6 (client-side, BrowserRouter) |
| Build | Vite 5.3 + `@vitejs/plugin-react` |
| HTTP | Native Fetch API (no axios), JWT in module memory |
| Charts | recharts 2.12 |
| Drag & drop | @dnd-kit/core + @dnd-kit/sortable |
| Icons | lucide-react |
| PWA | manifest.json + sw.js (offline shell + API network-first) |

---

## Architecture

```
src/
├── api/client.ts        — Typed fetch wrapper, JWT in-memory, auto-logout on 401
├── auth/                — AuthContext (JWT memory), LoginPage, ProtectedRoute
├── layout/              — Shell (sidebar+topbar), MobileNav (bottom tabs)
├── components/          — 11 shared UI primitives
├── hooks/               — 6 domain hooks (useApi, useVehicles, useDeals, …)
└── pages/               — 9 full pages
```

---

## Authentication

- `POST /api/v1/auth/login` → `{ token, user }` 
- Token stored **only in module memory** (`api/client.ts`) — never localStorage
- `setAccessToken(null)` + `auth:unauthorized` event on 401 → auto-logout
- `ProtectedRoute` redirects to `/login` with `state.from` for post-login redirect

---

## Pages

| Route | Page | Key features |
|---|---|---|
| `/` | Dashboard | 4 KPI cards, 6-month AreaChart (recharts), activity table |
| `/vehicles` | Vehicles | Filterable table, thumbnail, status badge, detail modal with 5 tabs |
| `/kanban` | Kanban | DnD columns (lead→won/lost), WIP limit red alert, DragOverlay |
| `/contacts` | Contacts | List+detail split, activity timeline |
| `/deals` | Deals | Pipeline columns with value totals, stage filter, advance button |
| `/inbox` | Inbox | Split-view thread, quick reply (Cmd+Enter), unread badge |
| `/calendar` | Calendar | Custom month grid, day event list, event type badges |
| `/finance` | Finance | BarChart P&L, negative-margin alert cards, top-10 table |
| `/settings` | Settings | Profile, workspace, platform connect/disconnect, templates |

---

## Mobile-Native-First UX

- **Bottom nav** (mobile <768px): Dashboard / Vehicles / Inbox / Deals / More
- **Sidebar** (desktop ≥768px): collapsible, persistent
- **Touch targets**: all interactive elements ≥44px
- **Skeleton loaders**: `PageSkeleton` component on initial page load
- **Toast notifications**: `ToastProvider` (success/error/warning/info), 4 s auto-dismiss
- **Dark mode**: Tailwind `class` strategy, `localStorage` persistence, toggle in topbar
- **Safe area**: `env(safe-area-inset-bottom)` for notched phones

---

## PWA

- **manifest.json**: standalone display, theme #2563eb, SVG icons 192/512
- **sw.js**: install → cache shell (`/`, `/index.html`); fetch → navigation serves shell, API is network-first w/ cache fallback, static assets cache-first
- **Service worker registration**: in `main.tsx` on `load` event

---

## Build Output

```
dist/index.html          1.06 kB  (gzip: 0.53 kB)
dist/assets/*.css       33.58 kB  (gzip: 6.41 kB)
dist/assets/vendor.js  164.13 kB  (gzip: 53.56 kB)  — React + Router
dist/assets/charts.js  383.35 kB  (gzip: 105.67 kB) — recharts
dist/assets/dnd.js      48.38 kB  (gzip: 16.05 kB)  — @dnd-kit
dist/assets/index.js    86.67 kB  (gzip: 22.30 kB)  — App code
```

Total gzip: **~204 kB** — well within 300 kB target for initial load.

---

## Deployment

```nginx
# Caddy config (append to existing Caddyfile)
workspace.cardex.eu {
    root * /srv/cardex/workspace/web/dist
    try_files {path} /index.html
    file_server
    reverse_proxy /api/* localhost:8506
}
```

Build step in CI:
```bash
cd workspace/web && npm ci && npm run build
```

---

## Not included (future sprints)

- Unit/integration tests (planned for sprint QA)
- E2E tests with Playwright
- Photo upload UI (sprint 48)
- Real-time notifications via WebSocket
- Offline data sync beyond API cache
