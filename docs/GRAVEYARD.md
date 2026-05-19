# SCRAPING GRAVEYARD

<!-- Registro de lo que existía antes de la limpieza 2026-05-19 -->
<!-- Eliminado por: errores en producción, patrones rotos, arquitectura pre-Strategy-B -->
<!-- No restaurar. El nuevo sistema está en scrapers/engine/ + SCRAPING_ENGINE.md -->

## Portal scrapers v1 — eliminados 2026-05-19

Eran 32 scrapers distribuidos en directorios por país. Probados en producción: fallos generalizados.
Causa raíz: patrones JSON/DOM desactualizados, sin retry, sin detección de softblock, sin Camoufox.

### Inventario de lo que había

**BE:** autoscout24_be.py, gocar.py, tweedehands.py
**CH:** autoscout24_ch.py, comparis.py, tutti.py
**DE:** autohero.py, automobile_de.py, autoscout24_de.py, heycar.py, kleinanzeigen_de.py, mobile_de.py, pkw_de.py
**ES:** autocasion.py, autoscout24_es.py, coches_com.py, coches_net.py, flexicar.py, milanuncios.py, motor_es.py, wallapop.py
**FR:** autoscout24_fr.py, caradisiac.py, lacentrale.py, largus.py, leboncoin.py, ouestfrance_auto.py, paruvendu.py
**NL:** autoscout24_nl.py, autotrack.py, gaspedaal.py, marktplaats.py

**Scripts de diagnóstico (obsoletos):**
diag.py, diag2.py, diag3.py, diag4.py, diag5.py, diag6.py, diag7.py,
diag_all.py, diag_apis.py, diag_autotrack_sitemap.py, diag_corrected.py,
diag_group_a.py, diag_pw.py

**Runners (obsoletos):**
run_all.py, run_as24.py, run_scraper.py

**Otros:**
- sitemap_indexer.py — bug XADD hang en sitemaps >500k URLs (documentado BACKLOG)
- enrich_worker.py — roto en producción

## Lo que se conservó (el oro)

| Archivo | Por qué |
|---|---|
| `scrapers/common/pw_base.py` | Motor Camoufox + stealth JS — reescrito 2026-05-19 |
| `scrapers/common/autoscout24.py` | Strategy B: chrome136 + retry + jitter — reescrito 2026-05-19 |
| `scrapers/common/indexer.py` | Delta MVCC correcto: INSERT new + DELETE stale, Redis Streams |
| `scrapers/requirements.txt` | Strategy B: curl_cffi≥0.15.1, camoufox, capsolver |
| `scrapers/discovery/` | Pipeline de descubrimiento de dealers — sistema separado, funcional |

## Sistema de reemplazo

Ver: `docs/SCRAPING_ENGINE.md` — arquitectura definitiva 360°
Implementación target: `scrapers/engine/` (esqueleto listo, desarrollo pendiente)
