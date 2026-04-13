# CARDEX — Estado del repositorio

## Fecha de auditoría
2026-04-14 01:23 CET — HEAD `4bd6536` (rama `claude/objective-wilbur`)

## Commit HEAD

| Campo | Valor |
|---|---|
| Hash largo | `4bd65365ad608420115a17bc5d4b81df56183a9c` |
| Fecha | 2026-04-14 01:21:31 +0200 |
| Autor | Elias |
| Subject | `planning: bootstrap workspace institucional + delta git documentado` |

---

## Estructura top-level

```
total 20111
drwxr-xr-x  .
drwxr-xr-x  ..
drwxr-xr-x  .claude/
-rw-r--r--  .cursorrules                (6 429 bytes)
-rw-r--r--  .env.example               (4 242 bytes)
-rw-r--r--  .git                       (worktree pointer)
-rw-r--r--  .gitignore                 (181 bytes)
-rw-r--r--  ARCHITECTURE.md            (34 935 bytes)
-rw-r--r--  CARDEX PROJECT.pdf         (1 055 057 bytes)
-rw-r--r--  CARDEX QUANTUM EDGE.pdf    (681 873 bytes)
-rw-r--r--  CARDEX v1.pdf              (4 865 826 bytes)
-rw-r--r--  CARDEX.pdf                 (4 834 419 bytes)
-rw-r--r--  CARDEXXX.pdf               (8 800 776 bytes)
-rw-r--r--  DISCOVERY-ENGINE-v3.md     (29 547 bytes)
-rw-r--r--  DISCOVERY-ENGINE.md        (35 215 bytes)
-rw-r--r--  Makefile                   (7 222 bytes)
-rw-r--r--  README.md                  (3 639 bytes)
-rw-r--r--  SPEC.md                    (148 065 bytes)
drwxr-xr-x  apps/                      (Next.js web frontend)
-rw-r--r--  docker-compose.yml         (24 092 bytes)
drwxr-xr-x  e2e/                       (E2E test suite Go)
drwxr-xr-x  extensions/chrome/         (Browser extension)
-rw-r--r--  go.work                    (workspace Go: 12 módulos)
drwxr-xr-x  ingestion/                 (crawler Go + orchestrador Python — fuera del go.work)
drwxr-xr-x  internal/shared/           (librería compartida Go)
drwxr-xr-x  monitoring/                (Prometheus config)
drwxr-xr-x  nginx/                     (reverse proxy config)
drwxr-xr-x  planning/                  (este directorio — creado 2026-04-14)
drwxr-xr-x  scrapers/                  (90 scripts Python por país + módulos comunes)
drwxr-xr-x  scripts/                   (SQL init + seed scripts)
drwxr-xr-x  services/                  (11 microservicios Go)
drwxr-xr-x  vision/                    (microservicio pHash Go)
```

**Nota:** El directorio `ingestion/` está excluido del `go.work` y gestiona su propio `go.mod` independiente. Los PDFs en la raíz (~20 MB totales) son documentación de producto, no deben existir en el repositorio de código.

---

## Servicios Go

El `go.work` agrupa 12 módulos bajo un mismo workspace (excluye `ingestion`).

| Path | Module | Líneas .go | Archivos .go | Tests | Archivo más reciente | Estado |
|---|---|---|---|---|---|---|
| `e2e` | `github.com/cardex/e2e` | 387 | 1 | SI | `chain_test.go` | SKELETON |
| `ingestion` | `github.com/cardex/ingestion` | 435 | 3 | NO | `pkg/lexicon/normalizer.go` | LEGACY-TO-PURGE |
| `internal/shared` | `github.com/cardex/shared` | 25 | 2 | NO | `pkg/config/config.go` | SKELETON |
| `services/alpha` | `github.com/cardex/alpha` | 1 085 | 14 | SI | `pkg/tax/spain.go` | IN-DEVELOPMENT |
| `services/api` | `github.com/cardex/api` | 9 245 | 20 | NO | `internal/middleware/ratelimit.go` | PRODUCTION-READY |
| `services/census` | `github.com/cardex/census` | 2 261 | 10 | NO | `pkg/sources/source.go` | IN-DEVELOPMENT |
| `services/forensics` | `github.com/cardex/forensics` | 864 | 7 | SI | `pkg/vies/client_test.go` | IN-DEVELOPMENT |
| `services/frontier` | `github.com/cardex/frontier` | 812 | 2 | NO | `pkg/scoring/composite.go` | IN-DEVELOPMENT |
| `services/gateway` | `github.com/cardex/gateway` | 904 | 7 | SI | `pkg/ratelimit/bucket_test.go` | IN-DEVELOPMENT |
| `services/imgproxy` | `github.com/cardex/imgproxy` | 554 | 1 | NO | `cmd/imgproxy/main.go` | IN-DEVELOPMENT |
| `services/legal` | `github.com/cardex/legal` | 670 | 7 | SI | `pkg/stolen/checker_test.go` | IN-DEVELOPMENT |
| `services/pipeline` | `github.com/cardex/pipeline` | 1 592 | 10 | SI | `pkg/h3/index.go` | IN-DEVELOPMENT |
| `services/scheduler` | `github.com/cardex/scheduler` | 1 264 | 3 | NO | `cmd/scheduler/main.go` | IN-DEVELOPMENT |
| `vision` | `github.com/cardex/vision` | 107 | 1 | NO | `cmd/worker/main.go` | SKELETON |

**Distribución de estados:**
- PRODUCTION-READY: 1 (`services/api`)
- IN-DEVELOPMENT: 9
- SKELETON: 3 (`e2e`, `internal/shared`, `vision`)
- LEGACY-TO-PURGE: 1 (`ingestion`)

**Criterios aplicados:**
- PRODUCTION-READY: >5 000 líneas, estructura `cmd/+internal/`, Dockerized, sin tests (deuda técnica conocida)
- IN-DEVELOPMENT: estructura completa, código funcional, cobertura de tests parcial o ausente
- SKELETON: <400 líneas o <3 archivos, funcionalidad mínima
- LEGACY-TO-PURGE: contiene patrones declarados ilegales en SPEC V6 (ver `ILLEGAL_CODE_PURGE_PLAN.md`)

---

## Frontends

### apps/web/

- **Stack:** Next.js 14.2.29 / React 18.3 / TypeScript 5.6 / Tailwind CSS 3.4 / pnpm
- **Tamaño src/:** 43 archivos `.tsx`/`.ts`; estimado ~15 000–18 000 líneas (no calculado; `pnpm-lock.yaml` es 6 467 líneas)
- **Dependencias principales (top 10):**
  | Paquete | Versión |
  |---|---|
  | `next` | 14.2.29 |
  | `react` / `react-dom` | ^18.3.1 |
  | `typescript` | ^5.6.3 |
  | `@deck.gl/core` + layers | ^9.0.0 / ^9.2.11 |
  | `lightweight-charts` | ^5.1.0 |
  | `maplibre-gl` | ^4.7.1 |
  | `meilisearch` | ^0.41.0 |
  | `zustand` | ^4.5.5 |
  | `h3-js` | ^4.1.0 |
  | `swr` | ^2.2.5 |
- **Archivo más reciente (en commit HEAD):** `apps/web/src/app/(dealer)/dashboard/crm/inventory/page.tsx` (estimado)
- **Estado:** IN-DEVELOPMENT — estructura App Router completa, páginas de dealer/analytics/VIN/CRM; sin suite de tests; Dockerfile presente

### extensions/chrome/

- **Stack:** Vanilla JS / Chrome Extension Manifest V3
- **Archivos:** `background.js`, `content.js`, `popup.js`, `settings.js`, `manifest.json` (no confirmado — solo directorio `chrome/` encontrado)
- **Estado:** SKELETON — extensión básica sin tests, sin build system

---

## Workers Python

### scrapers/ (principal — 90 archivos .py)

Módulo principal del sistema de discovery y scraping. Organizado en submódulos por país y función.

| Submódulo | Archivos .py | Descripción |
|---|---|---|
| `common/` | 11 | Clases base: http_client, playwright_client, proxy_manager, models, normalizer, robots_checker, sitemap_parser, gateway_client, frontier_client |
| `dealer_spider/` | 13 | Spider principal: discovery.py (2 320+ líneas), oem_gateway.py, stealth_http.py, stealth_browser.py, recon_oem.py, detector.py, dms/ adapters |
| `discovery/` | 7 | Orchestrator H3, OSM/Overpass, enricher, registros mercantiles (BE/CH/DE/ES/FR/NL) |
| `de/` `fr/` `es/` `be/` `nl/` `ch/` | ~7 cada uno | Scrapers por país: AutoScout24, mobile.de, leboncoin, coches.com, etc. |
| `google_maps/` | 2 | Crawler Google Maps |
| `inventory_reaper/` | 3 | HEAD-check batch 404→SOLD lifecycle |
| `search_indexer/` | 3 | PG→MeiliSearch sync watermark |

**Dependencias** (`scrapers/requirements.txt`):
```
httpx[http2]==0.27.2
playwright==1.44.0
redis==5.0.7
tenacity==8.3.0
pydantic==2.7.4
python-ulid==2.7.0
h3==3.7.7
structlog==24.2.0
python-dotenv==1.0.1
asyncpg==0.29.0
aiohttp==3.9.5
curl_cffi==0.7.4          ← DEPENDENCIA ILEGAL
```

**Estado:** IN-DEVELOPMENT — cobertura geográfica amplia, sin tests unitarios, presencia de módulos con técnicas ilegales (ver `ILLEGAL_CODE_PURGE_PLAN.md`)

### ingestion/orchestrator/

- **Scripts:** `h3_master.py` (65 líneas)
- **Función:** Siembra hexágonos H3 en `queue:h3_tasks` Redis para consumo por `api_crawler`. Orquestador puro (no extrae datos directamente).
- **Dependencias** (`ingestion/requirements.txt`):
  ```
  h3>=4.0.0
  curl_cffi==0.5.10      ← DEPENDENCIA ILEGAL (versión antigua)
  redis==5.0.1
  orjson==3.9.15
  ```
- **Estado:** LEGACY (habilita infraestructura para `api_crawler` que es LEGACY-TO-PURGE)

### services/forensics/

- **Scripts:** `tax_hunter.py` (líneas desconocidas — no auditado en detalle)
- **Función:** Complemento Python al servicio Go `forensics`; búsqueda de información fiscal
- **Estado:** REVIEW pendiente

### scripts/

- **Scripts:** `seed-vehicles.py` (16 051 bytes) — scripts de seed de datos de demo con HMAC dev hardcodeado. Excluido de producción.

---

## Stack monitoring + scripts + bin

### monitoring/

| Archivo | Descripción |
|---|---|
| `prometheus.yml` | Configuración Prometheus (1 674 bytes). Único archivo del directorio. Sin Grafana dashboards en repo. |

### scripts/

| Archivo | Tipo | Tamaño |
|---|---|---|
| `init-ch.sql` | SQL — schema ClickHouse | 18 028 bytes |
| `init-meili.sh` | Shell — índices MeiliSearch | 14 687 bytes |
| `init-pg.sql` | SQL — schema PostgreSQL principal | 46 555 bytes |
| `init-redis.sh` | Shell — config Redis | 8 458 bytes |
| `seed-demo.sql` | SQL — datos demo | 12 398 bytes |
| `seed-vehicles.py` | Python — seed 5 000 vehículos demo con HMAC dev | 16 051 bytes |

### bin/

Directorio no encontrado en HEAD actual.

### nginx/

| Archivo | Descripción |
|---|---|
| `nginx.conf` | Configuración reverse proxy (8 070 bytes) |
| `placeholder.svg` | SVG placeholder (753 bytes) |

---

## Dependencias inter-servicio Go

Basado en análisis de `go.mod` con directivas `replace` internas:

| Servicio | Importa de (internal) | Es importado por |
|---|---|---|
| `services/api` | `cardex/alpha`, `cardex/shared` | — |
| `services/frontier` | `cardex/shared` | — |
| `services/census` | `cardex/shared` | — |
| `services/scheduler` | `cardex/shared` | — |
| `internal/shared` | — | api, frontier, census, scheduler |
| `services/alpha` | — | api |
| `services/forensics` | — | — |
| `services/gateway` | — | — |
| `services/imgproxy` | — | — |
| `services/legal` | — | — |
| `services/pipeline` | — | — |
| `ingestion` | — (módulo independiente, fuera de go.work) | — |
| `e2e` | — | — |
| `vision` | — | — |

**Patrón arquitectónico:** La mayoría de servicios son independientes. La única dependencia compartida explícita es `cardex/shared` (25 líneas — config básica) consumida por 4 servicios. `services/api` es el único que importa lógica de negocio de otro módulo (`cardex/alpha` — tax calculation).

---

## Síntesis ejecutiva

**Madurez general.** El repositorio está en una fase de desarrollo activo avanzado con marcada asimetría entre componentes. El backend Go (`services/api`) es el único módulo que puede considerarse production-ready por volumen de código y completitud de estructura, aunque carece de tests unitarios. El resto de servicios Go tienen estructura correcta (`cmd/` + `pkg/`) y código funcional, pero requieren cobertura de tests y revisión de configuración antes de despiegue. El worktree contiene además documentación PDF (~20 MB) que no pertenece a un repositorio de código fuente.

**Servicios production-ready vs. en desarrollo.** Solo `services/api` (9 245 líneas, 20 archivos, Dockerized, JWT, RBAC, ClickHouse+PG+Redis+MeiliSearch) alcanza nivel de producción. Servicios como `services/pipeline`, `services/census` y `services/scheduler` muestran arquitectura sólida pero cobertura funcional incompleta. Los módulos `internal/shared`, `vision` y `e2e` son esqueletos funcionales.

**Deuda técnica visible.** La ausencia de tests unitarios es sistemática: 9 de 14 módulos Go no tienen ningún test. Los 5 que tienen tests (`alpha`, `forensics`, `gateway`, `legal`, `pipeline`) los tienen en paquetes específicos, no como cobertura end-to-end. El módulo `ingestion` (fuera del workspace, con su propio `go.mod` desactualizado — Go 1.21 vs. 1.24 del workspace) acumula deuda: StealthEngine con UA spoofing y estructura de H3 swarm, todo marcado LEGACY-TO-PURGE.

**Áreas estables.** El stack de infraestructura está bien definido: PostgreSQL (esquema principal en `init-pg.sql` 46 KB), ClickHouse (OHLCV + analytics), Redis (queues + rate-limiting), MeiliSearch (búsqueda full-text), Prometheus (métricas). `docker-compose.yml` (24 KB) muestra orquestación completa con todos los servicios. La capa Python de scrapers tiene cobertura geográfica correcta (6 países, >15 portales por país), aunque con dependencias ilegales.

**Riesgos arquitectónicos.** El riesgo principal es la presencia en producción de técnicas de evasión TLS (curl_cffi, playwright_stealth, 2captcha) en el módulo Python y del crawler Go con StealthEngine. Estos componentes exponen al proyecto a violaciones de términos de servicio y potencialmente a responsabilidad legal. Secundariamente, `ingestion` está desacoplado del workspace Go, lo que implica gestión de dependencias independiente y riesgo de divergencia silenciosa. La ausencia de tests en `services/api` — el componente más crítico — es un riesgo operacional significativo.
