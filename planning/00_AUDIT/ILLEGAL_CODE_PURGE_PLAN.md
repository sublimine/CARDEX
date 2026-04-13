# Plan de purga de código ilegal

**Fecha:** 2026-04-14
**Auditado por:** Claude (sesión institucional — rama `claude/objective-wilbur`)

---

## Contexto

SPEC V6 declara ilegales bajo el régimen institucional CARDEX las siguientes técnicas:
- Spoofing de User-Agent con identidad de browser real o bot conocido (Googlebot)
- TLS impersonation / JA3/JA4 fingerprint cloning (curl_cffi, similares)
- Playwright-stealth / evasión de detección de headless browser
- Resolución automatizada de CAPTCHAs (2captcha, hcaptcha, capsolver)
- Proxy residenciales en tiering de evasión de WAF
- Cualquier técnica cuyo propósito declarado sea eludir controles anti-bot

## Política

**NO eliminar ningún archivo en esta fase.** Solo documentar. La eliminación efectiva se ejecuta en fase posterior una vez que las estrategias sustitutivas E1-E12 (definidas en `04_EXTRACTION_PIPELINE/`) estén operativas y validen cobertura equivalente.

---

## Archivos identificados explícitamente por SPEC V6

### ingestion/cmd/api_crawler/main.go

| Campo | Valor |
|---|---|
| Existe en HEAD | SI |
| Path real | `ingestion/cmd/api_crawler/main.go` |
| Líneas | 203 |
| Nota | Módulo fuera del `go.work` — Go 1.21, dependencias separadas |

**Resumen funcional:** Consume tareas H3 de la cola Redis `queue:h3_tasks` (producidas por `h3_master.py`). Para cada hexágono, instancia un `StealthEngine` que realiza requests HTTP a `suchen.mobile.de` con headers de browser falsificados (Chrome/122), extrae vehículos (`DeepAssetPayload`) y los publica a otro queue Redis. Procesa tareas en goroutines concurrentes.

**Técnicas ilegales identificadas:**

| Línea | Patrón | Severidad |
|---|---|---|
| 45 | `type StealthEngine struct` — naming intencional de evasión | HIGH |
| 50 | `func NewStealthEngine()` | HIGH |
| 55 | `"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)...Chrome/122.0.0.0"` — UA browser real hardcodeado | HIGH |
| 65 | `BaseURL: "https://suchen.mobile.de"` — target hardcodeado | HIGH |
| 71 | `func (e *StealthEngine) PenetrateSector(task H3Task)` — semántica explícita de evasión | HIGH |
| 168 | `engine.PenetrateSector(task)` — llamada en loop de producción | HIGH |

**Cobertura aportada:** Inventario de vehículos en `mobile.de` (Alemania — portal más grande DE). Estimado 60–80% del inventory DE actual en el índice.

**Dependencias ilegales en `ingestion/requirements.txt`:**
- `curl_cffi==0.5.10` — versión antigua de la librería de impersonación TLS

**Plan de reemplazo:** Pendiente. Se asignará en fase `04_EXTRACTION_PIPELINE/` — candidatos: E-sitemap (mobile.de sitemap público), E-API-pública (mobile.de partner API si existe), E-feed-XML.

**Recomendación:** NO eliminar. Marcar LEGACY-TO-PURGE. Aislar del build hasta que sustituto esté validado.

---

### ingestion/cmd/sitemap_vacuum/main.go

| Campo | Valor |
|---|---|
| Existe en HEAD | SI |
| Path real | `ingestion/cmd/sitemap_vacuum/main.go` |
| Líneas | 158 |

**Resumen funcional:** Descarga y parsea un `sitemap.xml` (URL configurable via env), extrae URLs de vehículos y las publica en Redis. Parsea índices de sitemaps y urlsets XML. Útil como base para extracción legal.

**Técnicas ilegales identificadas:**

| Línea | Patrón | Severidad |
|---|---|---|
| 58 | `"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"` — impersonación Googlebot | CRITICAL |
| 120 | Segundo `req.Header.Set("User-Agent", ...)` con mismo UA Googlebot | CRITICAL |

**Análisis:** La impersonación de Googlebot es una violación específica: los servidores web suelen dar acceso privilegiado a Googlebot (sin rate-limiting, rutas completas) porque confían en la identidad de Google. Usar esta identidad falsa es engaño activo y viola términos de servicio de forma agravada respecto a un UA genérico de browser.

**Funcionalidad salvageable:** La lógica de descarga y parseo de sitemap XML (excepto el UA) es completamente legal y valiosa. El fix sería sustituir el UA por `CardexBot/1.0 (+https://cardex.eu/bot)` y verificar compliance con `robots.txt`.

**Plan de reemplazo:** Alta prioridad — la funcionalidad es legal si se corrige el UA. Se referenciará como E-sitemap en `04_EXTRACTION_PIPELINE/`. Candidato a corrección puntual en lugar de purga completa.

**Recomendación:** NO eliminar. Marcar REQUIRES-UA-FIX. Este es el único archivo donde la corrección es un cambio de 2 líneas.

---

### ingestion/cartografo_headless.js

| Campo | Valor |
|---|---|
| Existe en HEAD | **NO** |
| Búsqueda ejecutada | `find ingestion -name "cartografo*"` — sin resultados |

Fue declarado en SPEC V6 pero no existe en el HEAD actual. Puede haber existido en commits anteriores al pull (pre-`42a2c98`) y haber sido eliminado o renombrado. No requiere acción en esta fase.

---

### ingestion/radar_vanguardia.js

| Campo | Valor |
|---|---|
| Existe en HEAD | **NO** |
| Búsqueda ejecutada | `find ingestion -name "radar*"` — sin resultados |

Mismo estado que `cartografo_headless.js`. No existe en HEAD actual.

---

### ingestion/h3_swarm_node.py

| Campo | Valor |
|---|---|
| Existe en HEAD (forma exacta) | **NO** |
| Variante encontrada | `ingestion/orchestrator/h3_master.py` (65 líneas) |

**Análisis de `h3_master.py`:** Script de orquestación puro. Genera hexágonos H3 (resolución 4, ~250 km²) sobre los 6 países objetivo y los siembra en `queue:h3_tasks` Redis. No realiza requests HTTP, no tiene UA spoofing, no tiene técnicas de evasión. Su ilegalidad es **indirecta**: alimenta exclusivamente a `api_crawler` (LEGACY-TO-PURGE).

**Técnicas ilegales directas:** Ninguna.

**Cobertura aportada:** Infraestructura de distribución geográfica de tareas. El modelo H3 en sí es reutilizable (legal) para cualquier estrategia E1-E12 que requiera cobertura geográfica sistemática.

**Recomendación:** NO eliminar. El modelo H3 es valioso. Reclasificar como infraestructura reutilizable. Solo se purga si se purga completamente el pipeline `api_crawler`.

---

## Hallazgo crítico de la auditoría git delta — Commits aedbdf4 y 0630d04

### Commit aedbdf4 — 2026-04-07 11:42 +0200 (Elias)

**Subject:** `feat: motor stealth TLS (curl_cffi), evasiones Playwright, reaper, indexer MeiliSearch`

**Archivos tocados (21 files, 2 043 inserciones):**

| Archivo | Estado en HEAD | Patrones ilegales | Acción |
|---|---|---|---|
| `scrapers/dealer_spider/stealth_http.py` | EXISTE (344 líneas) | curl_cffi, TLS impersonation, JA3/JA4, proxy tiering | LEGACY-TO-PURGE |
| `scrapers/dealer_spider/stealth_browser.py` | EXISTE (600 líneas) | playwright_stealth, 2captcha | LEGACY-TO-PURGE |
| `scrapers/dealer_spider/spider.py` | EXISTE (50 045 bytes) | UA spoofing múltiple | REQUIRES-AUDIT |
| `scrapers/dealer_spider/dms/autentia.py` | EXISTE | StealthHTTPHelper migration | REVIEW |
| `scrapers/dealer_spider/dms/autobiz.py` | EXISTE | StealthHTTPHelper migration | REVIEW |
| `scrapers/dealer_spider/dms/generic_feed.py` | EXISTE | StealthHTTPHelper migration | REVIEW |
| `scrapers/dealer_spider/dms/generic_html.py` | EXISTE | StealthHTTPHelper migration | REVIEW |
| `scrapers/dealer_spider/dms/incadea.py` | EXISTE | StealthHTTPHelper migration | REVIEW |
| `scrapers/dealer_spider/dms/motormanager.py` | EXISTE | StealthHTTPHelper migration | REVIEW |
| `scrapers/dealer_spider/dms/schema_org.py` | EXISTE | StealthHTTPHelper migration | REVIEW |
| `scrapers/inventory_reaper/reaper.py` | EXISTE (usa CardexBot/1.0) | UA honesto — LEGAL | OK |
| `scrapers/search_indexer/indexer.py` | EXISTE | Sin técnicas de evasión | OK |
| `scrapers/common/normalizer.py` | EXISTE | Sin técnicas de evasión | OK |
| `scripts/init-pg.sql` | EXISTE | Sin técnicas de evasión | OK |
| `services/pipeline/cmd/pipeline/main.go` | EXISTE | source_url validation — LEGAL | OK |
| `docker-compose.yml` | EXISTE | Sin técnicas de evasión | OK |

**Conclusión commit aedbdf4:** Introdujo los dos archivos de mayor severidad del repo (`stealth_http.py` + `stealth_browser.py`) y migró 7 adaptadores DMS para usar `StealthHTTPHelper`. La migración de los DMS adapters requiere auditoría específica.

---

### Commit 0630d04 — 2026-04-03 20:15 UTC (Claude agent)

**Subject:** `feat(scrapers): full anti-detection stack for 95%+ inventory coverage`

**Archivos tocados (7 files, 923 inserciones):**

| Archivo | Estado en HEAD | Patrones ilegales | Acción |
|---|---|---|---|
| `scrapers/common/base_scraper.py` | EXISTE (15 993 bytes) | ProxyManager + CaptchaSolver wired in | HIGH |
| `scrapers/common/captcha_solver.py` | **NO EXISTE** | Absorbido en `stealth_browser.py` | N/A |
| `scrapers/common/http_client.py` | EXISTE (137 líneas) | proxy_manager dependency | MEDIUM |
| `scrapers/common/playwright_client.py` | EXISTE (165 líneas) | proxy injection | MEDIUM |
| `scrapers/common/proxy_manager.py` | EXISTE (165 líneas) | rotating proxy pool geolocalizado | HIGH |
| `scrapers/requirements.txt` | EXISTE | `curl_cffi==0.7.4` | HIGH |
| `.env.example` | EXISTE | `CAPTCHA_API_KEY=` (vacío — env-gated) | OK |

**Nota:** `captcha_solver.py` fue añadido en este commit pero no existe en HEAD actual. La funcionalidad fue absorbida directamente en `stealth_browser.py` (commit `aedbdf4`, líneas 171–220). No requiere acción separada.

**Conclusión commit 0630d04:** Estableció la infraestructura de proxy rotativo (`proxy_manager.py`) y contaminó `base_scraper.py` (clase base de TODOS los scrapers) con ProxyManager. Esto implica que todos los scrapers de país heredan potencialmente la infraestructura de evasión, aunque no la usen activamente si `PROXY_POOL` no está configurado.

---

## Búsqueda exhaustiva de patrones en todo el repo

Búsqueda ejecutada sobre `*.go`, `*.js`, `*.ts`, `*.py` (excl. `.git/`, `node_modules/`, `vendor/`).

### Resultados en archivos Go

| Archivo | Línea | Patrón | Contexto | Severidad |
|---|---|---|---|---|
| `ingestion/cmd/api_crawler/main.go` | 45 | `StealthEngine struct` | Tipo principal del crawler | HIGH |
| `ingestion/cmd/api_crawler/main.go` | 50 | `NewStealthEngine()` | Constructor | HIGH |
| `ingestion/cmd/api_crawler/main.go` | 55 | `User-Agent: Mozilla/5.0...Chrome/122` | UA browser real hardcodeado | HIGH |
| `ingestion/cmd/api_crawler/main.go` | 71 | `PenetrateSector` | Nombre de método con semántica explícita | HIGH |
| `ingestion/cmd/sitemap_vacuum/main.go` | 58 | `Googlebot/2.1` UA | Googlebot impersonation | CRITICAL |
| `ingestion/cmd/sitemap_vacuum/main.go` | 120 | `Googlebot/2.1` UA | Segunda ocurrencia | CRITICAL |
| `services/imgproxy/cmd/imgproxy/main.go` | 235 | `Chrome/131.0.0.0` UA | Para fetch de imágenes — gray area | REVIEW |
| `vision/cmd/worker/main.go` | 33 | `// Evasión estandarizada de WAF/CDN` + Chrome UA | Comentario explicita intención de evasión | MEDIUM |

### Resultados en archivos Python

| Archivo | Línea | Patrón | Severidad |
|---|---|---|---|
| `scrapers/dealer_spider/stealth_http.py` | 2 | `TLS-impersonating async HTTP layer` (docstring) | CRITICAL |
| `scrapers/dealer_spider/stealth_http.py` | 5 | `Per-country TLS impersonation (Chrome/Firefox/Safari JA3/JA4 fingerprints)` | CRITICAL |
| `scrapers/dealer_spider/stealth_http.py` | 23 | `from curl_cffi.requests import AsyncSession` | CRITICAL |
| `scrapers/dealer_spider/stealth_http.py` | 31 | `JA3 fingerprint` (comentario en código) | CRITICAL |
| `scrapers/dealer_spider/stealth_http.py` | 44 | `impersonate="chrome124"` | CRITICAL |
| `scrapers/dealer_spider/stealth_http.py` | 54 | `impersonate="firefox120"` | CRITICAL |
| `scrapers/dealer_spider/stealth_http.py` | 64 | `impersonate="safari17_2_ios"` | CRITICAL |
| `scrapers/dealer_spider/stealth_http.py` | 88 | `_PROXY_T2 = os.environ.get("PROXY_T2", "")  # residential backconnect URL` | CRITICAL |
| `scrapers/dealer_spider/stealth_browser.py` | 171 | `_solve_captcha_2captcha()` | CRITICAL |
| `scrapers/dealer_spider/stealth_browser.py` | 183 | `client.post("https://2captcha.com/in.php")` | CRITICAL |
| `scrapers/dealer_spider/stealth_browser.py` | 331 | `from playwright_stealth import stealth_async` | CRITICAL |
| `scrapers/dealer_spider/stealth_browser.py` | 332 | `await stealth_async(self._context)` | CRITICAL |
| `scrapers/dealer_spider/stealth_browser.py` | 355 | `Rotate context after N pages to avoid fingerprint accumulation` | HIGH |
| `scrapers/common/proxy_manager.py` | 102 | `proxy_manager.loaded` (rotating proxy pool con geo-affinity) | HIGH |
| `scrapers/common/base_scraper.py` | ~init | ProxyManager + CaptchaSolver wired en clase base | HIGH |
| `scrapers/dealer_spider/discovery.py` | 1250 | `User-Agent: Chrome/124` hardcodeado en probe | MEDIUM |
| `scrapers/dealer_spider/discovery.py` | 1509 | `User-Agent: Chrome` en probe de maps | MEDIUM |
| `scrapers/dealer_spider/discovery.py` | 1811 | `User-Agent: Chrome` en probe de registro | MEDIUM |
| `scrapers/dealer_spider/discovery.py` | 2159 | `random.choice(self._USER_AGENTS)` — pool de UAs rotativo | MEDIUM |
| `scrapers/dealer_spider/oem_gateway.py` | 861 | `user_agent="Mozilla/5.0...Chrome"` para OEM API | MEDIUM |
| `scrapers/dealer_spider/oem_gateway.py` | 1165 | `User-Agent: Chrome` para OEM API | MEDIUM |
| `scrapers/dealer_spider/recon_oem.py` | 83 | `user_agent="Mozilla/5.0...Chrome"` para reconocimiento OEM | MEDIUM |
| `scrapers/dealer_spider/detector.py` | 2, 96 | `fingerprints a dealer website` — DETECCIÓN DMS (legal, no evasión) | OK |
| `scrapers/inventory_reaper/reaper.py` | 28 | `CardexBot/1.0 (+https://cardex.eu/bot) HealthCheck` — UA honesto | OK |
| `scrapers/common/http_client.py` | 9 | `Honest CardexBot/1.0 User-Agent` (docstring) | OK |

### Resultados en archivos JS/TS

No se encontraron patrones de evasión en `extensions/chrome/` ni en `apps/web/`.

---

## Análisis de dependencias ilegales en requirements.txt

| Archivo | Dependencia ilegal | Versión | Uso |
|---|---|---|---|
| `scrapers/requirements.txt` | `curl_cffi` | 0.7.4 | TLS impersonation en stealth_http.py |
| `ingestion/requirements.txt` | `curl_cffi` | 0.5.10 | api_crawler (Go usa resty, no curl_cffi — posible resto histórico) |

**Nota:** `playwright==1.44.0` en `scrapers/requirements.txt` NO es ilegal por sí mismo — Playwright tiene usos legítimos para rendering de SPAs. La ilegalidad proviene de `playwright_stealth` (importado dinámicamente en `stealth_browser.py:331`), que no aparece en `requirements.txt` y sería una dependencia implícita.

---

## Conclusiones

### Resumen cuantitativo

| Categoría | Cantidad |
|---|---|
| Archivos marcados LEGACY-TO-PURGE | 4 (`stealth_http.py`, `stealth_browser.py`, `api_crawler/main.go`, `sitemap_vacuum/main.go`*) |
| Archivos marcados HIGH (requieren refactor) | 3 (`proxy_manager.py`, `base_scraper.py`, 7 DMS adapters) |
| Archivos marcados MEDIUM (UA spoofing en discovery) | 4+ (`discovery.py`, `oem_gateway.py`, `recon_oem.py`, `vision worker`) |
| Archivos OK con UA honesto | 3 (`inventory_reaper/reaper.py`, `http_client.py`, `discovery/enricher.py`) |
| Total matches CRITICAL | 13 |
| Total matches HIGH | 5 |
| Total matches MEDIUM | 10 |
| Archivos eliminados en esta fase | 0 |

*`sitemap_vacuum/main.go` es candidato a corrección puntual (2 líneas) en lugar de purga.

### Lista priorizada para purga (orden severidad)

1. `scrapers/dealer_spider/stealth_http.py` — TLS impersonation + JA3/JA4 + residential proxy tier
2. `scrapers/dealer_spider/stealth_browser.py` — playwright_stealth + 2captcha
3. `ingestion/cmd/api_crawler/main.go` — StealthEngine + Googlebot/mobile.de
4. `scrapers/common/base_scraper.py` — desconectar ProxyManager de la clase base
5. `scrapers/common/proxy_manager.py` — eliminar o sustituir por gestor legal de throttle
6. `ingestion/cmd/sitemap_vacuum/main.go` — corrección UA (2 líneas) — prioridad baja, impacto alto
7. 7× adaptadores DMS en `scrapers/dealer_spider/dms/` — auditar y migrar de StealthHTTPHelper
8. `scrapers/dealer_spider/discovery.py` — reemplazar UAs de browser por CardexBot en probes

### Archivos declarados en SPEC V6 pero ausentes en HEAD

- `ingestion/cartografo_headless.js` — NO existe
- `ingestion/radar_vanguardia.js` — NO existe

### Hallazgo no anticipado por SPEC V6

`scrapers/common/base_scraper.py` es la clase base de TODOS los scrapers de país (BE/CH/DE/ES/FR/NL). El commit `0630d04` inyectó ProxyManager en `__init__`, lo que significa que aunque los scrapers individuales usen `CardexBot/1.0`, tienen disponible infraestructura de proxy rotativo si se activa. Requiere desacoplamiento antes de considerar limpio cualquier scraper de país.
