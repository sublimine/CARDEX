---
name: project-dealer-inventory-scale
description: Frente C a escala — playwright_xhr + conector DMS desbloquean inventario SPA/widget; ~100-110K coches potenciales cost-zero
metadata: 
  node_type: memory
  type: project
  originSessionId: 4702af55-ddf6-4bc0-950b-c3028e4f4a63
---

Escala de [[project-dealer-scraping-system]]. Rama `feature/dealer-inventory-scale` desde `main 1ca158a` (worktree aislado, commit `b66a8b3`, **NO push**). Produce inventario real de coches a escala desde dealers con web (46.228 con dominio).

**Dos vectores nuevos** (reusan el seam A6/A7 sin reescribir):
- `scrapers/pipeline/playwright_xhr.py` — renderiza SPA, captura el **XHR-JSON del vehículo** (cross-origin incluido), lo normaliza (alias multilingües + **formato número DE `36.900`→36900** + claves underscore `first_registration`) y lo **inyecta como JSON-LD schema.org** → la extracción existente lo consume sin tocar el seam. `PlaywrightXHRFetcher` = superset de `PlaywrightFetcher`.
- `scrapers/dealer_scraping/dms_connector.py` — renderiza el **catálogo**, captura el **feed de inventario del widget DMS** (provider-agnóstico: Playwright captura el XHR cross-origin al proveedor) → N vehículos. `harvest_inventory_multi` prueba rutas comunes (`/gebrauchtwagen`…) cuando la detección de catálogo falla.

**Hallazgo clave VW Group** (audi 1354 + seat 424 + vw 256 ≈ 2.000, plataforma común): el catálogo (`/gebrauchtwagen`) dispara XHR JSON con `manufacturer`/`first_registration`/`price`(formato DE). Validado E2E: `hamburg-nord.seat.de` → 5 coches SEAT reales (Alhambra/Leon/Arona, FX→EUR) persistidos a `vehicles` vía el seam, purgado (30→35→30).

**Números (validar-con-límite-y-purgar):** estático 60 dealers→97.139 potencial; aumentado E07+XHR+DMS 30→109.510. Yield alto en **franquicias de marca `.com`** (sitemap+JSON-LD; audi `.com` 241 coches, vw 214, bovag 51) + **VW Group vía DMS** (SEAT 2/3, antes 0). ~**100-110K coches potenciales cost-zero** (suelo, no techo).

**Why:** futuras sesiones no deben re-derivar dónde está el inventario ni reescribir el seam.
**How to apply:** `harvest_inventory.py`/`verify_dms_seam.py`. Backlog: paginar el feed DMS para sizing íntegro · **ruta de inventario por-plataforma para `.audi`** (1.354, hoy no localiza) · proxies para `unreachable` · ruido OSM. Suite 1453 verde. Ver `DEALER_INVENTORY_REPORT.md`. RAM-safe: E07 conc 2, 1 browser/lote.
