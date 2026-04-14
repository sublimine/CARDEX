# Pipeline de Extracción — 04_EXTRACTION_PIPELINE

## Propósito
Documentación institucional del pipeline de extracción de catálogos dealer para CARDEX. Define las 12 estrategias E01-E12, su orquestación en cascada, las interfaces Go unificadas y los criterios de éxito por estrategia.

## Índice de estrategias

| ID | Archivo | Descripción | Estado |
|---|---|---|---|
| E01 | `strategies/E01_jsonld_schema_org.md` | JSON-LD Schema.org Vehicle inline — parse estructurado sin requests adicionales | DOCUMENTADO |
| E02 | `strategies/E02_cms_rest_endpoint.md` | REST endpoint CMS/plugin identificado — API nativa del CMS (WP Car Manager, DealerPress, etc.) | DOCUMENTADO |
| E03 | `strategies/E03_sitemap_xml.md` | Sitemap.xml + robots.txt directives — crawl estructurado desde índice oficial | DOCUMENTADO |
| E04 | `strategies/E04_rss_atom_feeds.md` | RSS/Atom feeds expuestos — ingesta de inventory vía feeds autodescubiertos | DOCUMENTADO |
| E05 | `strategies/E05_dms_hosted_api.md` | DMS hosted-site API — endpoints JSON de plataformas DMS (DealerSocket, CDK, Autobiz, Kerridge) | DOCUMENTADO |
| E06 | `strategies/E06_microdata_rdfa.md` | Microdata/RDFa fallback — structured data pre-JSON-LD en HTML5 | DOCUMENTADO |
| E07 | `strategies/E07_playwright_xhr_discovery.md` | XHR/AJAX endpoint discovery — Playwright transparente para identificar endpoint JSON del frontend | DOCUMENTADO |
| E08 | `strategies/E08_pdf_catalog.md` | PDF inventory catalog — pdfplumber + tabula + OCR tesseract para catálogos PDF | DOCUMENTADO |
| E09 | `strategies/E09_csv_excel_feeds.md` | CSV/Excel feeds — feeds de inventario descargables para agregadores | DOCUMENTADO |
| E10 | `strategies/E10_mobile_app_api.md` | Mobile app API — endpoints JSON de apps dealer identificables vía APK analysis | DOCUMENTADO |
| E11 | `strategies/E11_dealer_edge_onboarding.md` | Dealer Edge onboarding — cliente Tauri gratuito + EU Data Act delegation | DOCUMENTADO |
| E12 | `strategies/E12_manual_review.md` | Manual review queue — cola humana SLA <72h para dealers no cubiertos por E01-E11 | DOCUMENTADO |

## Documentos transversales

| Documento | Contenido |
|---|---|
| `OVERVIEW.md` | Arquitectura del pipeline, matriz estrategia×cobertura×complejidad, flujo decisional |
| `INTERFACES.md` | Interfaces Go unificadas: `ExtractionStrategy`, `ExtractionResult`, `VehicleRaw`, `ExtractionOrchestrator` |

## Principio de operación
Cascada descendente por prioridad: E01 (mayor calidad estructural, menor coste) → E12 (mayor coste, menor automatización). La primera estrategia que devuelve `PartialSuccess=true` o `FullSuccess=true` para un dealer detiene la cascada. E11 y E12 son estrategias de última milla activas por outreach.

## Restricción absoluta
Ninguna estrategia usa evasión de controles, fingerprint spoofing, TLS impersonation, proxies residenciales, servicios anti-captcha, ni User-Agents de terceros. Todo acceso bajo `CardexBot/1.0` identificable y `robots.txt` respetado.
