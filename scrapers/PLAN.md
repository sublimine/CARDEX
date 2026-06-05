# CARDEX scraping platform — master architecture

> Objetivo: indexar el 100% del inventario de vehículos en venta de DE, FR, ES,
> NL, BE, CH. Desde el marketplace más grande hasta el concesionario WordPress
> más pequeño. Plataforma anti-detección en Python, robustez > velocidad, cero
> invención. Este documento gobierna el diseño; el código es la verdad.

---

## §0 — Honesty ledger (qué es demostrable aquí y qué no)

La regla antialucinación manda. Separo el trabajo en dos clases y no las mezclo.

### Clase A — DETERMINISTA / ABIERTA (demostrable en esta máquina, sin secretos)
- Extractor genérico T3 sobre HTML real: JSON-LD (schema.org Vehicle/Car),
  WordPress `/wp-json`, sitemaps, microdata/OG. Verificable contra fixtures y
  contra sitios abiertos reales.
- Particionado/paginación de portales (AutoScout24 ya probado), normalización
  de campos, dedup por VIN+dealer.
- Discovery sobre fuentes abiertas: OSM Overpass, registros gov (INSEE Sirene,
  Zefix), sitemaps de directorios. Sin login, sin captcha.
- Subsistemas de software puro: health de proxies (lógica EWMA/quarantine),
  self-test de fingerprint, máquina de estados de WAF, daemon de warming.
  Su LÓGICA es testeable; su EFECTO real contra un WAF en vivo no lo es aquí.

### Clase B — ADVERSARIA / GATED (no demostrable aquí; bloqueador declarado)
- `carapis.com` y `auto-api.ch`: son **APIs de pago con API key**. Sin key no
  hay datos reales. Implemento el conector completo + tests con fixtures; marco
  la ejecución viva como `[NEEDS-KEY]`.
- Bypass en vivo de mobile.de / leboncoin.fr / coches.net / AS24-CH: requieren
  **proxies residenciales de pago** + resolución de challenge. Sin ese plano de
  red, el scraper se ejecuta pero el portal responde 403/CF. Marco `[NEEDS-PROXY]`.
- Verificado 2026-04-10 (INTEL.md): solo AS24-DE listings + gov abierto son
  friction-free desde IP de datacenter.

**Compromiso:** nunca presento un resultado Clase B como logrado sin la
credencial/red real. La PoC en vivo se ejecuta contra Clase A con filas reales.

---

## §1 — Topología del sistema

```
                       ┌──────────────────────────┐
                       │      DISCOVERY ENGINE      │
                       │  OSM · gov · directorios · │
                       │  portal_aggregator · AS24  │
                       └─────────────┬──────────────┘
                                     │ dealer/domain candidates
                                     ▼
        ┌────────────────────  DOMAIN MAP (registry)  ────────────────────┐
        │ por dominio: tier (T0..T3) · WAF class · path scheme · estado    │
        └─────────────┬──────────────────────────────────┬────────────────┘
                      │                                   │
         ┌────────────▼────────────┐         ┌────────────▼─────────────┐
         │  PORTAL SCRAPERS (T1)    │         │  GENERIC DEALER (T3)      │
         │  curl_cffi · partition · │         │  JSON-LD→wp-json→sitemap  │
         │  paginate · subdivide    │         │  →microdata→heuristic     │
         └────────────┬────────────┘         └────────────┬─────────────┘
                      │  listing URLs                      │ vehicle rows
                      ▼                                     ▼
         ┌──────────────────  ANTI-DETECT PLANE  ───────────────────┐
         │ proxies · fingerprint(JA3/JA4·H2·canvas) · behavioral ·   │
         │ WAF sensor · warming/identity                              │
         └──────────────────────────┬────────────────────────────────┘
                                     ▼
         ┌──────────────  PERSISTENCE  ──────────────┐
         │ Postgres vehicle_index (url_hash PK)       │
         │ Redis stream:enrich_pending · SQLite engine│
         └────────────────────────────────────────────┘
```

---

## §2 — Modelo de tiers

| Tier | Transporte                         | Cuándo                                  | Coste detección |
|------|------------------------------------|-----------------------------------------|-----------------|
| T0   | API móvil / API oficial            | endpoint JSON estable (aggregators)     | mínimo          |
| T1   | curl_cffi `impersonate=chrome`     | portal grande sin JS, JA3 fijo basta    | bajo            |
| T2   | Camoufox (Firefox JA3 real)        | portal con JS / sensor ligero           | medio           |
| T3   | Camoufox + behavioral + residencial| WAF duro (DataDome/PerimeterX/Akamai)   | alto            |

Escalada por circuit-breaker: arranca en el tier más barato del dominio; ante
softblock sostenido, sube de tier (y de proxy) antes de declarar el dominio caído.

---

## §3 — Matriz de cobertura

### T1 portales (curl_cffi) — esquema de URL VERIFICADO (AS24 + autotrack + autocasión)
| País | Portal              | Tier objetivo | WAF esperado      | Estado URL-scheme |
|------|---------------------|---------------|-------------------|-------------------|
| DE   | autoscout24.de      | T1            | CF (listings OK)  | VERIFICADO        |
| DE   | mobile.de           | T3            | DataDome          | [NEEDS-PROXY]     |
| DE   | kleinanzeigen.de    | T2            | CF                | por confirmar     |
| FR   | autoscout24.fr      | T1            | CF                | VERIFICADO (path) |
| FR   | leboncoin.fr        | T3            | DataDome          | [NEEDS-PROXY]     |
| FR   | lacentrale.fr       | T2            | CF/Akamai         | por confirmar     |
| FR   | largus.fr           | T2            | CF                | por confirmar     |
| ES   | autoscout24.es      | T1            | CF                | VERIFICADO (path) |
| ES   | autocasion.com      | T1            | CF-free           | VERIFICADO        |
| ES   | coches.net          | T3            | DataDome          | [NEEDS-PROXY]     |
| ES   | milanuncios.com     | T3            | DataDome          | [NEEDS-PROXY]     |
| ES   | wallapop.com        | T2 (API móvil)| PerimeterX        | por confirmar     |
| NL   | autoscout24.nl      | T1            | CF                | VERIFICADO (path) |
| NL   | autotrack.nl        | T1            | WAF.NONE          | VERIFICADO        |
| NL   | marktplaats.nl      | T3            | DataDome          | [NEEDS-PROXY]     |
| NL   | gaspedaal.nl        | T2            | CF                | por confirmar     |
| BE   | autoscout24.be      | T1            | CF                | VERIFICADO (path) |
| BE   | 2dehands/2ememain   | T3            | DataDome          | [NEEDS-PROXY]     |
| CH   | autoscout24.ch      | T2            | CF (403 datacenter)| [NEEDS-PROXY]    |
| CH   | comparis.ch         | T2            | CF                | por confirmar     |
| CH   | tutti.ch            | T2            | CF                | por confirmar     |

> "por confirmar" = NO invento el esquema de URL. Antes de codificar cada portal
> se confirma path+params reales (sitemap o navegación), o se deja el scraper
> con el esquema marcado `[UNVERIFIED-URL]` y deshabilitado por defecto.

**Esquemas VERIFICADOS [2026-06-03, curl_cffi impersonate="chrome", HTML vivo]:**
- **autotrack.nl** (T1, WAF.NONE) — pager canónico del sitio:
  `https://www.autotrack.nl/aanbod?data.merkModel.filter.0.slug={brand}&pageNumber={N}&pageSize=30&sortField=relevance&sortOrder=asc`
  (+`&data.merkModel.filter.0.models.0.slug={model}` al subdividir por modelo).
  Detalle: `/a/{slug}-{id}` (id ≥ 5 dígitos). Universo:
  `sitemap_brand_model_auto.xml` (994 locs `/auto/{brand}` y `/auto/{brand}/{model}`).
- **autocasion.com** (T1, CF-free) — pager canónico del sitio:
  page 1 `…/coches-segunda-mano/{cat}-ocasion` (URL desnuda, sin `?page=1`); page N≥2 `…?page={N}`.
  Detalle: `/coches-segunda-mano/{cat}/{slug}-ref{id}`. Universo: leaf urlset
  `uploads/sitemap-ng/coches-segunda-mano/coches-segunda-mano.xml` (30386 locs, deduped).

### T0 aggregators (API key)
- carapis.com, auto-api.ch → conector + fixtures, ejecución `[NEEDS-KEY]`.

### T3 generic dealer — cubre la cola larga (miles de concesionarios)
Cascada de extracción (orden de preferencia, primero que da ≥CriticalFields gana):
1. **JSON-LD** `script[type=application/ld+json]` → Vehicle/Car/MotorVehicle.
2. **WordPress REST** `/wp-json/...` (rutas verificadas en INTEL.md E02).
3. **Sitemap** heurístico (patrones vehicle/auto/voiture/coche/fahrzeug).
4. **Microdata/OG** `og:title`, `product:price:amount`, `og:image`.
5. **Heurística DOM** (regex precio/año/km multilingüe) — último recurso sin LLM.

---

## §4 — Subsistemas 360° (estado actual + qué cerrar)

| Subsistema   | Real hoy (file:line)                          | Falta cerrar                              |
|--------------|-----------------------------------------------|-------------------------------------------|
| Proxies      | health EWMA + quarantine (engine/net)         | auto-reprobe, geo-target, rate per-proxy  |
| Fingerprint  | JA3 vía curl_cffi + Camoufox; canvas/webgl    | self-test endpoint, JA4, H2 order assert  |
| Behavioral   | scroll/mouse base (engine/behavior)           | dwell/typing/navigation realistas         |
| WAF sensor   | sensor.py:96 refresh_token() STUB             | detección por-WAF + token refresh + fallback |
| TCP/IP       | tcp.py:106 apply_profile() THIN               | invocar httpcloak o degradar honesto      |
| Warming      | identidad base                                | daemon 3-fases + persistencia + rotación  |

Cada cierre: implementación real + test de lógica + doc de config + manejo de error.
Lo que no se pueda probar en vivo aquí se prueba a nivel de lógica y se marca.

---

## §5 — Discovery (reutilización verificada)
Building blocks REALES ya en `discovery/`: sitemap_resolver, wp_rest_harvester,
portal_aggregator, osm, fr_sirene, bovag, ch_zefix, as24_curl_cffi. El funnel
unifica: fuentes → candidatos de dominio → clasificación de plataforma
(CMS_WORDPRESS/SHOPIFY/DMS/NATIVE) → router al scraper T1/T3 correcto.

---

## §6 — Benchmarks (realidad)
| Target          | Clase | Demostrable aquí | Plan                                  |
|-----------------|-------|------------------|---------------------------------------|
| auto-api.ch     | B     | NO (API key)     | conector + fixtures, run `[NEEDS-KEY]`|
| carapis.com     | B     | NO (API key)     | conector + fixtures, run `[NEEDS-KEY]`|
| dealer abiertos | A     | SÍ               | PoC en vivo con filas reales          |
| OSM/gov         | A     | SÍ               | discovery en vivo                     |

---

## §7 — Orden de construcción
1. **PLAN.md** (este documento). ✅
2. **Extractor genérico T3** `pipeline/generic_extractor.py` + tests (Clase A, máxima cobertura).
3. **Conectores aggregator** carapis/auto_api (key-gated) + tests fixtures.
4. **Portales T1** nuevos con esquema VERIFICADO; resto `[UNVERIFIED-URL]` deshabilitado.
5. **Discovery funnel** unificado.
6. **Cierre 360°**: proxy reprobe/geo/rate, fingerprint self-test, WAF fallback, warming daemon.
7. **PoC en vivo** Clase A (filas reales) + reporte honesto de bloqueadores Clase B.
8. **INFRASTRUCTURE.md** (research) + **AGGREGATOR_APIS.md**.
9. **Commit + push + parte de entrega**.

---

## §8 — No negociables
- Cero endpoints/selectores inventados. Sin fuente verificada → `[UNVERIFIED-*]` + deshabilitado.
- Robustez > velocidad: retry con backoff, softblock detection, circuit breaker en todo fetch.
- Todo dato externo validado en el borde (schema canónico, enums normalizados).
- Resultado Clase B jamás presentado como logrado sin credencial/red real.
- Inmutabilidad en transformaciones; archivos < 800 líneas; funciones < 50.
