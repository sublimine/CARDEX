# CARDEX — Análisis Delta Git

**Fecha de análisis:** 2026-04-14
**Rama worktree:** `claude/objective-wilbur`
**Ejecutado por:** Claude (sesión institucional bootstrap)

---

## 1. Estado inicial antes del sync

| Parámetro | Valor |
|---|---|
| HEAD inicial | `0061554` |
| Rama local | `claude/objective-wilbur` |
| Commits locales no en origin/main | 0 (sin divergencia) |
| Commits en origin/main no en HEAD | 91 |
| Stash requerido | No (working tree limpio) |

---

## 2. Delta cuantitativo

```
375 files changed, 58350 insertions(+), 13072 deletions(-)
```

---

## 3. Log de commits incorporados (HEAD inicial → origin/main)

Rango: `0061554..fc986b7` — 91 commits en orden cronológico descendente.

| Hash | Fecha | Autor | Subject |
|---|---|---|---|
| `fc986b7` | 2026-04-07 16:07 +0200 | Elias | fix: BMW dealer reconciliation — distributionPartnerId mapping + simplified upsert |
| `96963c6` | 2026-04-07 16:04 +0200 | Elias | diag: publish skip counters — dealer/url/model rejection breakdown |
| `e3e560a` | 2026-04-07 15:15 +0200 | Elias | fix: verbose ingest error logging — first 5 failures show full listing details |
| `a1b7b5b` | 2026-04-07 15:12 +0200 | Elias | fix: BMW fetch body built in Python, escaped for JS — avoids template string corruption |
| `f25a569` | 2026-04-07 15:09 +0200 | Elias | feat: BMW Phase 3 injected fetch loop + RawListing schema fix |
| `8b86ebd` | 2026-04-07 14:58 +0200 | Elias | fix: BMW usedCarImageList is dict not list — handle both types |
| `96d8b63` | 2026-04-07 14:56 +0200 | Elias | fix: BMW year parsing safe_int, handler exception traceback logging |
| `499ebe0` | 2026-04-07 14:54 +0200 | Elias | fix: BMW vehiclesearch returns HTTP 201 not 200 — accept both in interceptor |
| `94d74d8` | 2026-04-07 14:51 +0200 | Elias | fix: BMW response interceptor registered BEFORE navigation — captures first page |
| `feae9f1` | 2026-04-07 14:49 +0200 | Elias | feat: BMW Phase 3 rewrite — response interception + scroll pagination |
| `32779b6` | 2026-04-07 14:46 +0200 | Elias | fix: remove credentials:include — CORS blocks it on cross-origin BMW API |
| `8c40680` | 2026-04-07 14:44 +0200 | Elias | fix: BMW injected fetch — credentials include, console capture, error body logging |
| `6d939cc` | 2026-04-07 14:42 +0200 | Elias | fix: BMW SPA init — keep stylesheets, stealth patches, longer hash wait |
| `5ac09bd` | 2026-04-07 14:40 +0200 | Elias | fix: BMW hash capture — networkidle + scroll trigger + 60s wait + cookie dismissal |
| `32ab675` | 2026-04-07 14:38 +0200 | Elias | feat: BMW hybrid architecture — HTTP dealers + Playwright hash hijack + injected fetch |
| `9923ce2` | 2026-04-07 14:32 +0200 | Elias | fix: BMW handler uses dedicated httpx client with BMW-specific Origin/Referer headers |
| `e996ae8` | 2026-04-07 14:30 +0200 | Elias | feat: BMW Stocklocator real endpoints — verified vehicle extraction pipeline |
| `cb6be17` | 2026-04-07 13:54 +0200 | Elias | fix: vehicles.seller_name column name, reconciliation exception handling |
| `b7b568a` | 2026-04-07 13:48 +0200 | Elias | fix: OEM Gateway diagnostic logging — content-type check, response keys, body snippets |
| `49c0e30` | 2026-04-07 13:45 +0200 | Elias | feat: OEM Gateway espectro completo — 14 marcas × 6 países + servicio Docker |
| `98db546` | 2026-04-07 13:25 +0200 | Elias | feat: OEM Franchise classifier + OEM Gateway — cobertura de concesionarios oficiales |
| `ab1d356` | 2026-04-07 13:01 +0200 | Elias | fix: _PW_SEMAPHORE UnboundLocalError — add global declaration in _process_dealer |
| `97bb112` | 2026-04-07 12:58 +0200 | Elias | feat: modo estrangulado T0 — throttle 3-7s, retirada inmediata sin proxy |
| `fce4997` | 2026-04-07 12:44 +0200 | Elias | fix: GovernmentRegistryBridge init (rdb+session), proxy env pass-through, login API_BASE |
| `96eb7c8` | 2026-04-07 12:05 +0200 | Elias | feat: 3 probes masivos — Portal Aggregator, Google Maps Grid, Gov Registry Bridge |
| `b0212ea` | 2026-04-07 11:49 +0200 | Elias | feat: vector XHR dirigido para SPAs + CAPTCHA resiliente |
| `aedbdf4` | 2026-04-07 11:42 +0200 | Elias | feat: motor stealth TLS (curl_cffi), evasiones Playwright, reaper, indexer MeiliSearch |
| `b6c685c` | 2026-04-07 01:40 +0200 | Elias | feat: validation barriers + JSON-LD parser fix — 20 real vehicles from OcasionPlus |
| `c0cc181` | 2026-04-07 01:26 +0200 | Elias | feat: 4-vector extraction engine — JSON-LD, sitemap, XHR interception, iframe |
| `81f58ca` | 2026-04-06 22:51 +0200 | Elias | fix: spider operational — deadlock fix, decode_responses, logging, false positive filter |
| `2e88695` | 2026-04-06 22:00 +0200 | Elias | feat: event-driven parallel pipeline — URL resolver as stream consumer |
| `2845394` | 2026-04-06 21:45 +0200 | Elias | fix: dealer discovery pipeline operational — unique index, deps, docker config |
| `f615fba` | 2026-04-06 21:16 +0200 | Elias | feat: arrow enrichment pipeline — free URL resolver + Google Places sniper mode |
| `52a6d60` | 2026-04-06 21:08 +0200 | Elias | feat: Full-Spectrum Discovery Protocol — 7 probes, 0 blind spots |
| `9fc28cb` | 2026-04-06 20:41 +0200 | Elias | feat: dealer discovery orchestrator + mobile.de Playwright fix + synthetic data purge |
| `cccc5d7` | 2026-04-06 19:41 +0200 | Elias | docs: complete system architecture document (ARCHITECTURE.md) |
| `769ec3b` | 2026-04-06 19:17 +0200 | Elias | feat: atomic audit — 30 fixes across all subsystems (crash, integrity, robustness, performance) |
| `329cd1a` | 2026-04-04 23:50 +0200 | Elias | docs: CARDEX Discovery Engine — complete architecture for 100% territory coverage |
| `df813aa` | 2026-04-04 21:57 +0200 | Elias | fix(scrapers): resolve import paths, HMAC mismatch, and partner ID header |
| `d1e0d3a` | 2026-04-04 21:43 +0200 | Elias | feat(scrapers): add 6 territory scraper services running continuously in Docker |
| `8bd6c83` | 2026-04-04 21:37 +0200 | Elias | fix(web): extract SortSelect to client component to fix server-side render error |
| `16f6696` | 2026-04-04 19:36 +0000 | Claude | feat(scrapers): add run_all.py multi-scraper orchestrator + Dockerfile support |
| `a66dfed` | 2026-04-04 21:22 +0200 | Elias | feat: populate CARDEX with 5000 vehicles across 6 EU countries |
| `f5966f0` | 2026-04-04 19:18 +0000 | Claude | fix(content): seed demo data + fix SSR API routing + MeiliSearch setup |
| `8f3a7a1` | 2026-04-04 20:45 +0200 | Elias | fix(docker): resolve all build and runtime failures to make CARDEX fully bootable |
| `ecb5b65` | 2026-04-04 20:45 +0200 | Elias | fix(docker): resolve all build and runtime failures to make CARDEX fully bootable |
| `60822b7` | 2026-04-03 21:20 +0000 | Claude | fix(web): add @deck.gl/geo-layers, upgrade lightweight-charts to v5 |
| `4d11ba8` | 2026-04-03 20:58 +0000 | Claude | fix(web): switch to production build (runner stage) for Docker stability |
| `f664095` | 2026-04-03 20:39 +0000 | Claude | fix(web): add .dockerignore — exclude node_modules from build context |
| `092b19a` | 2026-04-03 20:36 +0000 | Claude | fix(web): remove volume mounts from web container — pnpm symlinks break across Docker volume boundary on Windows |
| `c2c7c52` | 2026-04-03 20:29 +0000 | Claude | fix(web): add postcss.config.js (Tailwind requires it) + WATCHPACK_POLLING for Docker/Windows |
| `161ce72` | 2026-04-03 20:27 +0000 | Claude | refactor(scrapers): clean indexer stack — sitemap-first for 100% coverage |
| `0630d04` | 2026-04-03 20:15 +0000 | Claude | feat(scrapers): full anti-detection stack for 95%+ inventory coverage |
| `0a5d58d` | 2026-04-03 19:14 +0000 | Claude | fix(docker): remove go.work from build context, add GOWORK=off to all services |
| `1a811a0` | 2026-04-03 19:12 +0000 | Claude | fix(docker): upgrade Go base image from 1.23 to 1.24 in all service Dockerfiles |
| `70a0c75` | 2026-04-03 18:24 +0000 | Claude | fix(docker): resolve merge conflicts — keep pnpm + GOWORK=off fixes |
| `c3914c2` | 2026-04-03 18:24 +0000 | Claude | fix(docker): use pnpm in web Dockerfile, GOWORK=off in API Dockerfile |
| `97ca84b` | 2026-04-03 20:12 +0200 | sublimine | feat: CARDEX Intelligence Platform — full rebuild |
| `b66e95e` | 2026-04-03 17:53 +0000 | Claude | fix: resolve all compilation errors and make API+web bootable without Docker |
| `ecd181f` | 2026-04-03 16:37 +0000 | Claude | refactor: rewrite VIN valuation + publish pages to premium product level |
| `cf3c874` | 2026-04-03 16:20 +0000 | Claude | feat: implement Gap2 VIN Valuation, Gap3 Residual Forecasting, Gap4 Multipublicación |
| `f94fd21` | 2026-04-03 11:16 +0000 | Claude | fix(backend): critical schema bug, HTML injection, rand.Read, HTTP status codes |
| `53677fe` | 2026-04-03 11:13 +0000 | Claude | fix(frontend): error handling, rollbacks, enumeration guard, password UX |
| `1b50a80` | 2026-04-03 11:10 +0000 | Claude | fix(ext): security hardening — CSP, HTTPS validation, Chrome 103+, scoped resources |
| `af84df1` | 2026-04-03 11:08 +0000 | Claude | fix: critical bugs + institutional UI + XSS fix + optimal pricing page |
| `b42548f` | 2026-04-02 23:26 +0000 | Claude | feat: intelligence engine, admin panel, AI assist, RBAC, browser extension |
| `5866903` | 2026-04-02 14:22 +0000 | Claude | fix: inventario — lifecycle_status correcto, paginación page= en lugar de offset= |
| `d887081` | 2026-04-02 14:21 +0000 | Claude | feat: frontend completo — notificaciones, reset password, inventario real, dashboard KPIs |
| `8ff4bef` | 2026-04-02 14:16 +0000 | Claude | feat: rate limiting, password reset, email verification, FX real parsing |
| `42f526c` | 2026-04-02 08:52 +0000 | Claude | feat: notifications in-app + dashboard layout + infra mejorada |
| `2646710` | 2026-04-02 08:31 +0000 | Claude | fix(frontend): seal 3 bugs found in atomic audit |
| `bccf547` | 2026-04-02 02:44 +0000 | Claude | feat(crm): full CRM backend — vehicle lifecycle, contacts, pipeline, P&L |
| `02491cc` | 2026-04-02 02:14 +0000 | Claude | feat(crm): 5 CRM frontend pages — 2605 lines total |
| `9e7aaf8` | 2026-04-02 01:58 +0000 | Claude | feat(scheduler): nightly price_candles + ticker_stats + hourly arbitrage scanner |
| `a898037` | 2026-04-01 08:08 +0000 | Claude | feat(arbitrage): Bloomberg Terminal interface (756 lines) |
| `2a480ed` | 2026-03-31 23:00 +0000 | Claude | fix(tradingcar): remove unused context import |
| `e413cb0` | 2026-03-31 23:00 +0000 | Claude | feat(tradingcar): TradingView-identical frontend + vin.go schema fix |
| `6f50458` | 2026-03-31 22:59 +0000 | Claude | feat(vin): VIN search landing page |
| `aba2a94` | 2026-03-31 22:58 +0000 | Claude | feat(api): register all new routes — TradingCar, Arbitrage, CRM |
| `9766d38` | 2026-03-31 22:58 +0000 | Claude | feat(vin): complete VIN history report page v2 |
| `4ece168` | 2026-03-31 22:57 +0000 | Claude | feat(crm): full CRM schema + arbitrage handler fixes |
| `8414a4d` | 2026-03-31 22:57 +0000 | Claude | fix(vin): wire EUROPOL SIS-II Redis stolen check (set:stolen_vins) |
| `f800013` | 2026-03-31 22:56 +0000 | Claude | feat: arbitrage API handlers (opportunities, routes, NLC breakdown, booking) |
| `4aaef3d` | 2026-03-31 22:56 +0000 | Claude | feat: VIN History v2, TradingCar candles schema, arbitrage schema foundations |
| `b6ee0e6` | 2026-03-31 21:03 +0000 | Claude | fix: align dealer handlers with actual DB schema + entity_ulid JWT claim |
| `f84f65e` | 2026-03-31 20:36 +0000 | Claude | feat: complete dealer spider, DMS adapters, auth, NLC, and frontend |
| `fed27c2` | 2026-03-31 20:00 +0000 | Claude | fix: audit fixes — model aliases, dedup logic, orchestrator SQL and queue |
| `8645f5d` | 2026-03-31 19:15 +0000 | Claude | feat: 7-layer dealer discovery system + dealer web spider DMS adapters |
| `ea2bac0` | 2026-03-31 08:55 +0000 | Claude | feat: add Go service Dockerfiles, scheduler, 10 scraper adapters, dealer pages |
| `f3d903f` | 2026-03-31 08:43 +0000 | Claude | feat: complete CARDEX platform rebuild — marketplace + analytics + VIN + dealer SaaS |
| `42a2c98` | 2026-03-28 21:56 +0100 | sublimine | Add files via upload |

---

## 4. Resultado del sync

| Parámetro | Valor |
|---|---|
| Método | `git pull --ff-only origin main` |
| Resultado | **Exitoso — fast-forward** |
| Rango incorporado | `0061554..fc986b7` |
| HEAD final | `fc986b7` |
| Conflictos | Ninguno |

---

## 5. git log -3 --oneline (HEAD final)

```
fc986b7 fix: BMW dealer reconciliation — distributionPartnerId mapping + simplified upsert
96963c6 diag: publish skip counters — dealer/url/model rejection breakdown
e3e560a fix: verbose ingest error logging — first 5 failures show full listing details
```

---

## 6. Observaciones

- El grueso del delta (91 commits, 7-8 días) corresponde al periodo 2026-03-28 a 2026-04-07.
- Autores: Elias (commits propios), Claude (sesiones de agente), sublimine (uploads iniciales).
- Actividad concentrada en: ingestion/scraping (BMW, OEM Gateway), dealer discovery, docker, frontend web.
- Presencia confirmada de commits con subjects como "stealth", "anti-detection" — relevante para auditoría ILLEGAL_CODE_PURGE_PLAN.md.
- Ramas worktree locales (`claude/*`) no incorporadas al delta — solo se sincronizó `origin/main`.
