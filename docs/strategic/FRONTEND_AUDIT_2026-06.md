# CARDEX Frontend Audit — Junio 2026

**Fecha:** 2026-06-05
**Scope:** `workspace/web/` — React 18 + Vite + TypeScript SPA
**Backend de referencia:** `workspace/cmd/workspace-service/` (Go, SQLite, puerto 8506)

---

## 1. Veredicto ejecutivo

El frontend de CARDEX es un **prototipo de alta fidelidad visual** con un diseño system
glassmorphism propio, ~21 800 LOC de TypeScript, 13 páginas, 22 componentes reutilizables
y 8 custom hooks. La calidad estética es notablemente superior a la media de MVPs B2B en
automoción — el Terminal de mercado y la Landing page están a nivel de producto fintech.

Sin embargo, el frontend **no es vendible hoy**. El diagnóstico central es:

> **Casi toda la aplicación funciona con datos mock hardcodeados.**
> Los hooks de datos están cableados al API real, pero cada página
> declara su propio `MOCK_*` inline y lo usa como fallback o como fuente
> principal. En producción, las páginas mostrarían datos estáticos ficticios.

Esto convierte al frontend en un **clickable prototype**, no en un producto funcional.
La distancia al MVP vendible es significativa pero acotable: la arquitectura de hooks
y tipos está lista para conectar datos reales — falta ejecución, no rediseño.

**Calificación global: 4/10 para producción. 7.5/10 como prototipo visual.**

---

## 2. Estado actual — inventario de superficies

### 2.1 Páginas implementadas

| Ruta | LOC | Datos reales | Mock | Estado |
|------|-----|:---:|:---:|--------|
| `/` (Landing) | ~1 500 (Landing + sections + shader) | — | — | Funcional, solo visual |
| `/login` | ~80 | No | DEV_BYPASS=true | Auth real implementada pero bypassed |
| `/check/:vin` | ~1 400 (Check + CheckReport + DossierReport) | **Sí** | No | **Única página conectada al backend real** |
| `/dashboard` | ~865 | Hook `useApi('/kpi')` | MOCK_KPI, DEALER | Mock domina |
| `/vehicles` | ~536 | Hook `useVehicles()` | MOCK_VEHICLES (20 items) | Mock domina |
| `/kanban` | ~300 | Hook `useKanban()` | MOCK_BOARD | Mock domina, drag-drop funcional |
| `/contacts` | ~300 | Hook `useApi('/contacts')` | MOCK_CONTACTS (10 items) | Mock domina |
| `/deals` | ~300 | Hook `useDeals()` | MOCK_DEALS (6 items) | Mock domina |
| `/inbox` | ~300 | Hook `useInbox()` | MOCK_CONVS (4 items) | Mock domina |
| `/calendar` | ~250 | Ninguno | MOCK_EVENTS (6 items) | Calendar propio, sin hook al API |
| `/finance` | ~250 | Ninguno | MONTHLY, TOP_VEHICLES | 100% mock, sin hook al API |
| `/market` | ~992 | Ninguno | Datos generados proceduralmente | 100% mock, charting funcional |
| `/terminal` | ~581 + ~3 300 (módulos) | Ninguno | Market data simulada | 100% mock, charting de alta calidad |
| `/settings` | ~200 | Parcial (user de AuthContext) | PLATFORMS hardcodeado | Mayoritariamente presentacional |

### 2.2 Componentes reutilizables (22)

Button, Card, Modal, Input, Select, Dropdown, Badge, Avatar, Toast, Tooltip, Table,
Tabs, Switch, Timeline, Skeleton, LoadingSpinner, AlertCard, EmptyState, SourceBadge,
ScoreGauge, VINInput, Breadcrumb.

**Calidad:** Correcta. Usan CVA (class-variance-authority) para variantes, Radix UI
para primitivas accesibles, y Framer Motion para micro-interacciones. Los componentes
son coherentes con el design system.

### 2.3 Layout (Shell)

- Sidebar colapsable con 3 grupos de navegación (Core, CRM, Tools)
- Topbar con breadcrumb, command palette (⌘K), notificaciones, avatar
- Dark/light theme toggle con persistencia en localStorage
- MobileNav: bottom tab bar con 5 ítems, `md:hidden`

---

## 3. Calidad de código

### 3.1 TypeScript

- `strict: true` habilitado en tsconfig — correcto
- `noUnusedLocals: false`, `noUnusedParameters: false` — demasiado permisivo
- Tipos bien definidos en `src/types.ts` y `src/types/` (Vehicle, Deal, Contact,
  Conversation, Message, Template, KpiData, FinanceRow, VehicleReport, VehicleDossier)
- ~60 interfaces/types exportados — cobertura de tipos sólida
- No se usa `any` de forma apreciable — buen signo
- Ausencia de Zod o runtime validation en la capa API — los datos del backend
  se castean directamente con `as Promise<T>`, sin validación de forma

### 3.2 Tests

**Cobertura: prácticamente nula.**

- 0 archivos `.test.tsx` o `.spec.tsx` en `src/`
- 1 archivo de "self-verification" (`indicators.test.ts`) que no usa un test runner;
  es un módulo que exporta `runIndicatorChecks()` para ejecutar en consola
- No hay configuración de Vitest, Jest, ni Playwright
- `puppeteer` está en devDependencies pero sin tests E2E
- **No hay script `test` en package.json**

### 3.3 Patrones

**Positivo:**

- Separación limpia hooks/componentes/páginas/layout/api/types
- `apiRequest<T>()` centralizado con refresh automático, abort controller, y
  manejo de 401 → evento `auth:unauthorized`
- Custom hooks siguen un patrón consistente: `useApi<T>(path, deps)` como base,
  hooks de dominio componen sobre él
- Optimistic updates en Kanban (`moveCard`)
- AbortController en todos los hooks de datos
- Error mapping tipado en `useCheck` y `useDossier`

**Negativo:**

- Mock data hardcodeado dentro de cada página (no en fixtures separados ni en
  un mock server) — imposible de distinguir programáticamente de datos reales
- No hay lazy loading (React.lazy / Suspense) — todo carga en el bundle inicial
- No hay error boundaries
- Estado global solo vía Context (Auth, Toast) — sin solución de cache/sync
  como React Query o SWR
- `DEV_BYPASS = true` hardcodeado — riesgo de ship accidental
- El hook `useApi` usa `eslint-disable-next-line` para suprimir una advertencia
  legítima sobre dependencias en el array de deps

### 3.4 Estilo de código

- Consistente, bien formateado, con secciones delimitadas por comentarios `// ──`
- Archivos grandes pero no excesivos (Dashboard 865, Market 992, Terminal 581)
- Sin console.log en producción (verificado por grep)
- Inline styles prevalecen en Landing y Terminal (comprensible por la complejidad
  visual, pero dificulta el mantenimiento)

---

## 4. Integración frontend ↔ backend

### 4.1 Endpoints que el frontend consume (via hooks)

| Hook | Endpoint | Backend implementado |
|------|----------|:---:|
| `useApi('/kpi')` | `GET /api/v1/kpi` | **Sí** (workspace-service) |
| `useVehicles()` | `GET /api/v1/vehicles` | **Sí** |
| `useDeals()` | `GET /api/v1/deals` | **Sí** |
| `useDealMutations.moveStage()` | `PATCH /api/v1/deals/:id` | **Sí** |
| `useDealMutations.createDeal()` | `POST /api/v1/deals` | **Sí** |
| `useKanban()` | `GET /api/v1/deals` + `PATCH /api/v1/deals/:id` | **Sí** |
| `useInbox()` | `GET /api/v1/inbox` | **Sí** |
| `useConversation()` | `GET /api/v1/inbox/:id` | **Sí** |
| `useInboxMutations.reply()` | `POST /api/v1/inbox/:id/reply` | **Sí** |
| `useInboxMutations.patch()` | `PATCH /api/v1/inbox/:id` | **Sí** |
| `useCheck()` | `GET /api/v1/check/:vin` | **Sí** |
| `useCheck.checkByPlate()` | `GET /api/v1/check/plate/:country/:plate` | **Sí** |
| `useDossier()` | `GET /api/v1/dossier/:country/:plate` | **Sí** (DossierHandler) |
| `useApi('/contacts')` | `GET /api/v1/contacts` | **Sí** |
| `useApi('/auth/me')` | `GET /api/v1/auth/me` | **No encontrado en router** |
| `api.post('/auth/login')` | `POST /api/v1/auth/login` | **Sí** |

### 4.2 Endpoints del backend NO consumidos por el frontend

| Endpoint | Descripción | Impacto |
|----------|-------------|---------|
| `POST /api/v1/auth/register` | Registro de usuarios | Settings no lo usa |
| `POST /api/v1/documents/*` | Generación de PDFs (contrato, factura, ficha, CMR) | Sin UI |
| `GET /api/v1/documents/:id/download` | Descarga de documentos | Sin UI |
| `GET /api/v1/templates` | Plantillas de email | Settings muestra tab pero no conecta |
| `POST /api/v1/ingest/*` | Ingestion de inquiries | Sin UI |
| `PUT /api/v1/vehicles/:id/media/reorder` | Reordenar fotos | Sin UI |
| `GET/POST /api/v1/vehicles/:id/transactions` | Transacciones financieras | Finance usa mock |
| `GET /api/v1/vehicles/:id/pnl` | P&L por vehículo | Finance usa mock |
| `GET /api/v1/fleet/pnl` | P&L de flota | Finance usa mock |
| `GET /api/v1/fleet/alerts` | Alertas financieras | Finance usa mock |
| `GET /api/v1/calendar/events` | Eventos de calendario | Calendar usa mock local |
| `POST /api/v1/calendar/events` | Crear evento | Calendar no conecta |
| `GET /api/v1/kanban/columns` | Columnas de Kanban | Kanban usa stages hardcodeados |

### 4.3 Diagnóstico de integración

**El backend está significativamente más maduro que el frontend.**

El workspace-service expone ~40+ endpoints funcionales con SQLite, JWT auth,
rate limiting, SMTP, generación de PDFs, y un sistema de calendario/kanban
completo. El frontend consume <30% de estos endpoints, y de ese 30%, la
mayoría está eclipsada por datos mock que se muestran en su lugar.

La **única feature plenamente integrada end-to-end** es el VIN Check
(`/check/:vin` y `/check/plate/:country/:plate`), que llama al backend real,
procesa la respuesta, y renderiza un informe detallado con datos de 6 registros
europeos (NL, FR, BE, ES, DE, CH).

---

## 5. UX/UI — ¿Presentable para un dealer B2B?

### 5.1 Fortalezas visuales

- **Design system cohesivo:** glassmorphism con 23KB de CSS tokens, 4 niveles de
  vidrio, paleta de acentos consistente, animaciones suaves
- **Dark mode nativo** con transición a light mode
- **Landing page premium:** WebGL shader background, smooth scroll (Lenis),
  parallax, catálogo de marcas, filtros de búsqueda avanzados
- **Terminal de mercado:** calidad fintech — candlestick charts (lightweight-charts),
  53 indicadores técnicos, 95 herramientas de dibujo, arbitraje cross-border,
  profundidad de mercado, supply demand index
- **Micro-interacciones:** spring animations, animated numbers, hover states,
  drag & drop con feedback visual

### 5.2 Debilidades UX

- **Datos ficticios:** un dealer vería "BMW 320d xDrive 2021, €24.900" como si fuera
  su inventario, pero son datos estáticos que no cambian — experiencia engañosa
- **Idioma inconsistente:** mezcla de español (errores en useCheck, etiquetas en
  Landing) e inglés (navegación, KPIs, nombres de contactos mock)
- **Sin onboarding:** no hay wizard de configuración inicial para el dealer
- **Sin CRUD completo:** Vehicles y Contacts solo son listados (no hay "Add Vehicle"
  funcional), Calendar no persiste eventos, Finance es read-only
- **Sin notificaciones reales:** el NotificationBell es decorativo
- **Sin i18n framework:** los strings están hardcodeados, no hay react-intl/i18next

### 5.3 Responsive

- MobileNav (bottom tab bar, 5 tabs) visible en `< md` (768px)
- Sidebar se oculta en mobile
- Modales usan `items-end sm:items-center` (sheet en mobile, centrado en desktop)
- **Sin testing de responsive real** — se infiere del CSS pero no hay breakpoints
  sistemáticos en las páginas de datos (tablas, grids, charts)
- Terminal y Market **no son responsive** — diseñados para desktop

---

## 6. Performance

### 6.1 Bundle

- Manual chunks configurados: vendor (react/router), charts (recharts), dnd (@dnd-kit)
- `lightweight-charts` (~180KB) no está en chunk separado — carga con el bundle principal
- Sin lazy loading (`React.lazy`) — todas las 13 páginas en el bundle inicial
- Sin code splitting por ruta
- Estimación de bundle: ~300KB gzipped (aceptable pero mejorable)

### 6.2 Runtime

- Framer Motion en cada página — overhead de re-renders en animaciones
- `useApi` no tiene cache ni deduplicación — cada montaje lanza un fetch nuevo
- No hay virtualization en listas (Vehicles con 20 mocks, pero en producción
  podrían ser miles)
- No hay debounce en SearchCommand
- Sin service worker funcional (placeholder presente)
- Sin prefetch de rutas

---

## 7. Seguridad

| Aspecto | Estado | Riesgo |
|---------|--------|--------|
| JWT en localStorage | Implementado | Medio (XSS → token theft) |
| DEV_BYPASS hardcodeado | `const DEV_BYPASS = true` | **Crítico si se deploya** |
| Token refresh | Implementado (5min buffer) | OK |
| CSRF | Sin protección explícita | Bajo (API JSON, no cookies) |
| XSS en inputs | Sin sanitización visible | Medio |
| Rate limit UI | Implementado en Check | OK |
| `allowedHosts: true` en Vite | En dev config | Bajo (solo dev) |

---

## 8. Gap analysis — MVP vendible

### 8.1 Requisitos mínimos de un MVP vendible para dealers B2B

1. **Login funcional** con registro y recuperación de contraseña
2. **Inventario real** conectado al pipeline de extracción/calidad
3. **CRM funcional** con CRUD completo de contacts y deals
4. **Inbox real** conectado a email/marketplace inquiries
5. **Documentos** (contrato, factura, ficha técnica) generables desde la UI
6. **Calendario funcional** con persistencia
7. **Finance conectado** al backend de transacciones
8. **Multi-idioma** (mínimo EN, DE, ES, FR, NL)
9. **Onboarding wizard**
10. **Datos reales** en todas las páginas

### 8.2 Estado actual vs. requisitos

| Requisito | Estado | Esfuerzo estimado |
|-----------|--------|:-:|
| Login funcional | Backend listo, frontend bypassed | 2-3 días |
| Inventario real | Hook listo, quitar mock, ajustar UI | 3-5 días |
| CRM CRUD completo | Hooks parciales, faltan forms de creación/edición | 5-8 días |
| Inbox real | Hook listo, quitar mock | 2-3 días |
| Documentos desde UI | Backend listo, UI inexistente | 5-7 días |
| Calendario funcional | Backend listo, frontend 100% mock | 3-4 días |
| Finance conectado | Backend listo, frontend 100% mock | 3-5 días |
| Multi-idioma | Inexistente, requiere i18n framework | 8-12 días |
| Onboarding wizard | Inexistente | 3-5 días |
| Datos reales globales | Purgar mocks, error states, empty states | 5-8 días |

**Total estimado: 40-60 días-persona para un desarrollador senior fullstack.**

---

## 9. Roadmap priorizado

### Fase 0 — Higiene (Semana 1)

- [ ] `DEV_BYPASS` → variable de entorno, nunca `true` en build de producción
- [ ] Agregar Vitest + configuración mínima
- [ ] Habilitar `noUnusedLocals` y `noUnusedParameters` en tsconfig
- [ ] Mover todos los MOCK_* a `src/__mocks__/` o eliminarlos
- [ ] Agregar `.env.example` con variables documentadas
- [ ] Error boundary global con UI de fallback

### Fase 1 — Conectar datos reales (Semanas 2-4)

- [ ] Activar auth real: login/register/refresh, quitar DEV_BYPASS
- [ ] Dashboard → conectar a `/kpi` real, quitar MOCK_KPI y DEALER
- [ ] Vehicles → quitar MOCK_VEHICLES, paginación real, empty state
- [ ] Contacts → quitar MOCK_CONTACTS, agregar creación/edición
- [ ] Deals → quitar MOCK_DEALS, CRUD completo
- [ ] Inbox → quitar MOCK_CONVS, conectar reply real
- [ ] Kanban → quitar MOCK_BOARD, conectar a deals reales
- [ ] Calendar → conectar a `/calendar/events`, CRUD
- [ ] Finance → conectar a `/fleet/pnl`, `/vehicles/:id/transactions`
- [ ] Instalar React Query o SWR para cache y deduplicación

### Fase 2 — Features de negocio (Semanas 5-7)

- [ ] Generación de documentos: UI para contratos, facturas, fichas técnicas
- [ ] Gestión de fotos de vehículos (upload, reorder, galería)
- [ ] Plantillas de email editables en Settings
- [ ] Conexión a plataformas (mobile.de, AutoScout24) desde Settings
- [ ] Notificaciones reales (WebSocket o polling)
- [ ] Vehicle detail page (ficha completa con historial, fotos, documentos)

### Fase 3 — Pulido para venta (Semanas 8-10)

- [ ] i18n con react-intl o i18next (EN, DE, ES, FR, NL como mínimo)
- [ ] Onboarding wizard (primer login → configurar dealer, importar inventario)
- [ ] Lazy loading por ruta con React.lazy + Suspense
- [ ] Responsive completo en Market y Terminal
- [ ] Tests: componentes críticos (auth flow, check, deals CRUD)
- [ ] E2E con Playwright: login → crear deal → mover en kanban → cerrar
- [ ] PWA funcional con offline cache del inventario
- [ ] Lighthouse audit > 90 en todas las métricas

### Fase 4 — Diferenciación (Post-MVP)

- [ ] Terminal de mercado conectado a datos reales de pricing
- [ ] Market intelligence con datos del pipeline de discovery/extraction
- [ ] Alertas inteligentes (precio, stock, oportunidades de arbitraje)
- [ ] Dashboard configurable (widgets arrastrables)
- [ ] API pública para integraciones de terceros

---

## 10. Archivos clave para el desarrollador

```
workspace/web/
├── src/
│   ├── api/client.ts          ← HTTP client centralizado (JWT, refresh, abort)
│   ├── auth/AuthContext.tsx    ← Provider de auth (DEV_BYPASS aquí)
│   ├── auth/ProtectedRoute.tsx ← Guard de rutas
│   ├── types.ts               ← Tipos core (Vehicle, Deal, Contact, etc.)
│   ├── types/check.ts         ← Tipos del VIN Check (~270 LOC)
│   ├── types/dossier.ts       ← Tipos del Vehicle Dossier (~190 LOC)
│   ├── hooks/useApi.ts        ← Hook base para GET con abort
│   ├── hooks/useVehicles.ts   ← Hook de inventario con filtros
│   ├── hooks/useDeals.ts      ← Hook de deals con mutations
│   ├── hooks/useKanban.ts     ← Hook de kanban con optimistic updates
│   ├── hooks/useInbox.ts      ← Hook de inbox con reply/patch
│   ├── hooks/useCheck.ts      ← Hook de VIN check (mejor implementado)
│   ├── hooks/useDossier.ts    ← Hook de dossier
│   ├── layout/Shell.tsx       ← App shell (sidebar + topbar)
│   ├── styles/tokens.css      ← Design system completo (23KB)
│   └── pages/
│       ├── Terminal.tsx        ← Terminal de mercado (la joya visual)
│       ├── Market.tsx          ← Market overview con charting
│       ├── Dashboard.tsx       ← Dashboard de KPIs
│       ├── Check.tsx           ← VIN Check (única feature end-to-end)
│       └── ...                 ← Resto de páginas CRM
├── vite.config.ts             ← Proxy /api → localhost:8506
├── package.json               ← 35 dependencias, sin test runner
└── tsconfig.json              ← strict: true
```

---

## 11. Conclusión

CARDEX tiene un frontend visualmente excepcional para un proyecto de este tamaño, con un
design system propio de alta calidad y features avanzadas (Terminal de mercado, VIN Check
pan-europeo) que lo diferencian de competidores genéricos. El backend del workspace-service
está sustancialmente más avanzado, con ~40+ endpoints funcionales esperando ser consumidos.

El gap fundamental es operativo, no arquitectónico: la capa de datos del frontend está
desconectada del backend en ~85% de las superficies. Cerrar ese gap es trabajo de integración
mecánico — no requiere rediseño ni cambios de arquitectura.

La inversión de 40-60 días-persona para alcanzar un MVP vendible es razonable para el valor
que el producto ya tiene en su pipeline de backend (discovery → extraction → quality → workspace).

**Prioridad inmediata: Fase 0 (higiene) + conectar las 5 páginas CRM al backend real.**
Eso convierte el prototipo en un producto funcional con datos reales que un dealer puede evaluar.
