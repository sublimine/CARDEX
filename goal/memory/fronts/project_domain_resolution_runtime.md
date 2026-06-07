---
name: project-domain-resolution-runtime
description: Cómo correr el resolver de dominios de dealers + sus hallazgos de rendimiento y techo
metadata: 
  node_type: memory
  type: project
  originSessionId: 3580463c-4ae4-408a-9d01-af8872ba2a62
---

Sistema de resolución de dominio: `scrapers/discovery/domain_resolution/` (rama
`feature/domain-resolution`, commits 72a2a34 + 20d3a7e, NO mergeado a main b980f90).
Convierte dealers `name+city+country` con `domain IS NULL` en "dealers con web".

**Correr** (host, DATABASE_URL=localhost:5432):
`python -m scrapers.discovery.domain_resolution.resolver --countries DE,ES,CH,NL,BE --batch 500 --concurrency 3 --limit 0`
Flags: `--start-id` (keyset, muestrear slice), `--limit` (cap de intentos). Env:
`DOMRES_RSS_LIMIT_MB` (1200), `DOMRES_VALIDATE_TOP` (3). Solo hace `UPDATE` del campo
`domain` por id (nunca INSERT) → convive con el barrido FR si se excluye FR.

**Vía que funciona:** DuckDuckGo HTML keyless vía curl_cffi impersonate (Mojeek fallback).
Devuelve el sitio propio del dealer como primer resultado. Las vías (3) directorios
nacionales y (4) crt.sh/CommonCrawl están diseñadas pero NO cableadas (siguiente iter).

**Rendimiento medido:** mejor yield en slices `source=oem:*` (nombres de concesionario
distintivos). Cola larga OSM/registro (nombres oscuros) → domina `no_results` (sin web
indexable). Resultado frecuente = microsite de plataforma (OEM `skoda-auto.de`, shop
blanco) cuando el apex propio no sale en DDG: web real pero pobre para inventario.

**`dup` = señal de entity-resolution:** un dominio validado que choca con el único
`(domain,country)` significa que el sitio YA está en BD bajo otra fila (cadena/cross-source)
= enlace same-entity confirmado, materia prima para P2. Ver [[project_blueprint_target_arch]].

**Anti-falso-positivo (reforzado en vivo):** `clean_name` quita boilerplate OEM
("(...)", "- Exposición y Taller"); stopwords de marcas + genéricos automotrices evitan
que `taller`/`toyota` posen como token distintivo; la validación exige el token de nombre
EN la página (ciudad sola solo si el nombre es 100% genérico). 16 dominios nuevos validados
(BE+3 CH+1 DE+5 ES+4 NL+3), 0 falsos persistidos. Reporte: `DOMAIN_RESOLUTION_REPORT.md`.
Relacionado: [[project_discovery_free_source_ceiling]], [[project_scraper_sitemap_discovery]].

**PARTE II — worker multi-vía a escala** (commits ca0ed36→2bd5cb5, NO push). `worker.py`
usa la **cola nativa `ddg_attempts`** (claim atómico `FOR UPDATE SKIP LOCKED` + collision-merge
de `ddg_worker.py` que YA existía — reusar, no reinventar) + pipeline multi-vía:
`worker --countries DE,ES,CH,NL,BE --limit 0`. Orden de coste: **email-domain** (apex del
email, `candidate.email_apex`, gratis) → **directorio** (`directories.py`: FR PagesJaunes
sitio en href, CH local.ch email en JSON, DE gelbeseiten 2-step results→gsbiz→sitio) →
**search** DDG→Mojeek. `revalidate.py` re-valida lo persistido contra la verja vigente y purga.

**Techo real = throttle de DDG a una sola IP** (bajo carga sostenida DDG→vacío
`search_unreachable`); las **directorios nacionales son la vía robusta** (CH local.ch, DE
gelbeseiten rinden; ES/NL/BE sin directorio dependen de DDG+email a cuentagotas). Common
Crawl NO viable (CDX no soporta wildcard substring). crt.sh guest PG = timeout (best-effort).

**LECCIÓN crítica de validación (el bug que importó):** los FP a escala (carnicería/óptico/
bufete/museo/aeropuerto/autoescuela) venían de (1) `_text` NO quitaba `<script>/<style>` →
el CSS/JS (`sizes=auto`, trackers) fingía señal auto; (2) palabras sueltas débiles. Fix:
strip script/style + señal auto **de dos niveles** (≥1 FUERTE p.ej. autohaus/concessionnaire,
o ≥2 DÉBILES distintos; excluidas `occasion`/`garage`/`motor`) + guard de **categoría
no-dealer por título** (Fahrschule/museum/Autovermietung/aeroport) + directorio con
`require_name=True` + fetch validación `verify=False`. Atribución honesta: solo cuentan filas
con `external_refs.resolved_via` (las pone este worker); el salto grande de with_web por país
es del barrido de discovery de otra sesión, NO de este resolver.
