# CARDEX — Arquitectura de Workflows (W1→W5)

> Orden de construcción del Director Soberano (2026-06-10). Esto es la **capa de
> orquestación** sobre los átomos que YA existen en el repo: no reinventa, los
> encadena con gates binarios y una cadena de verificación SEPARADA (la Inquisición).
> Cada afirmación de este documento mapea a código real verificado, no a teoría.

## La cadena end-to-end por dealer

```
territorio ─▶ W1 DESCUBRIR ─▶ W2 RECETA ─▶ W3 SCRAPEAR ─▶ W4 API+DELTA ─▶ W5 GUARDAR+LIBERAR
              │ V1            │ V2          │ V3 (Inquis.) │ V4            │ V5
              ▼ gate          ▼ gate        ▼ gate         ▼ gate         ▼ gate
           PASA/NO PASA    PASA/NO PASA   PASA/NO PASA   PASA/NO PASA   PASA/NO PASA
```

Regla de oro (no negociable): **ningún resultado se confía**. Cada número se
confirma por una vía DISTINTA a la que lo produjo. El verificador de cada Wn
(`Vn`) es una cadena separada — quien extrae nunca certifica su propio número.

## Mapa workflow → átomos reales (todos [VERIFICADO] en el repo, main @ 3adc857)

| Wn | Qué hace | Átomos de código reales | Verificador independiente |
|----|----------|-------------------------|---------------------------|
| **W1** Descubrir | censar dealer + resolver web + cdx_code + geo | `scrapers/discovery/sources/*` · `scrapers/discovery/domain_resolution/worker.py` · `scrapers/intelligence/cdx_code.py` · migr. `0004_geo_hierarchy` `0005_entity_identity` | `scripts/verify_discovery.py` · `scrapers/intelligence/capture_recapture.py` (Chapman, estimador ortogonal del universo) |
| **W2** Receta | cazar config de extracción óptima | `scrapers/dealer_scraping/cms_fingerprint.py` · `harvester.py` · `scrapers/portals/config.py` · `configs/families/*.json` · `recipes/RESEARCH_*.md` | re-ejecución doble independiente (V2: 2 corridas consistentes = 100% stock visible) |
| **W3** Scrapear | ejecutar receta + normalizar canónico + dedup inter-portal | `scrapers/dealer_scraping/inventory_harvester.py` · `seam.py` · `scrapers/pipeline/parse.py` | `scripts/verify_count.py` (conteo ≥2 vías: paginación vs sitemap vs filtros) — **agente DISTINTO al scraper** |
| **W4** API+Delta | cargar base viva + delta + servir API por dealer | `services/entity_api/app.py` (:8088) · `scrapers/delta/delta_worker.py` · vista `entity_inventory` (migr. 0007) · tabla `operator_alerts` | `scripts/verify_entity_caging.py` · observación directa de muestra (V4: cero falsos "baja") |
| **W5** Guardar+Liberar | persistir receta+estado a git + liberar crudo regenerable | git (main) · `configs/` `recipes/` `dealers/` `state/` · validate-and-purge (`seam.make_live_purger`) | reconstrucción en frío desde repo + checksum del dato estructurado |

## Decisiones de arquitectura (mejoras al método, con su porqué)

### D1 — Código de dealer: cdx_code inmutable + ruta geo navegable
La orden pedía `{ISO}-{PROV}-{CIUDAD}-{SEQ}`. **El SEQ es frágil**: cambia si
cambia el orden de descubrimiento o la fuente, rompiendo la identidad entre
re-consolidaciones. El repo ya tiene `cdx_code` = `CDX-<ISO2>-<8 base32>`
**derivado del dominio** (identidad estable, mismo dealer → mismo código aunque
se redescubra por otra fuente). Decisión:
- **Identidad canónica = `cdx_code`** (inmutable, DB-backed en migr. 0005).
- **Jerarquía geo = ruta de carpeta** `{ISO}/{PROV}/{CIUDAD}` (navegable por humano).
- **Estructura final:** `/dealers/{ISO}/{PROV}/{CIUDAD}/{cdx_code}/` — geo navegable
  + clave estable como hoja. Lo mejor de los dos: jerarquía del jefe + estabilidad.

### D2 — La Inquisición es una cadena de código separada
Los verificadores `Vn` NO comparten transporte, query ni proceso con el productor.
Quórum DB-enforced en `verification_verdicts` (CHECK `chk_quorum`, migr. 0003):
una cifra no es TRUSTWORTHY sin ≥2 vías ortogonales. **Disparadores de re-verificación
SIEMPRE** (lección del 2026-06-10): cifras redondas, conteos idénticos entre dealers,
y CEROS — el día de hoy una epidemia de "0 stock / DEAD" resultó ser un bug de
transporte, no realidad. Ver `state/GAPS.md`.

### D3 — Routing de coste (LLM local para lo masivo)
- **Ollama `qwen2.5:3b` :11434** (local, gratis): clasificar plataforma, parsear
  campos, deduplicar, verificación difusa de dominios (`DOMRES_LLM_VERIFY`).
- **Modelo caro SOLO para decidir**: arquitectura, recetas Tier-1 atascadas,
  auditoría de anomalías. Nada sube de coste sin fallo documentado del nivel inferior.

### D4 — Aislar el dealer bloqueado, nunca parar la línea
Cada dealer es una unidad independiente. Un Tier-1 atascado o un dominio sin
resolver se marca (`ddg_error`, `inventory_tier`, cuarentena en `state/SOURCES.md`)
y la línea sigue. Paralelo sin dependencia, cascada con ella.

### D5 — El sitemap DESCUBRE; el listado/total-declarado dice qué está DISPONIBLE
**Hallazgo de la Inquisición, 2026-06-10 (dificar.com):** el sitemap listaba 235
PDPs pero el catálogo paginado y el total declarado por el portal coincidían en
**123**. Los 112 de más eran coches **VENDIDOS/RESERVADOS** cuya página seguía
devolviendo 200. Consecuencia: contar el stock por el sitemap **sobrecuenta** —
mezcla vendidos con disponibles. Por tanto:
- el **sitemap** es superficie de DESCUBRIMIENTO de URLs (enumera todo),
- la **verdad del stock disponible** es el LISTADO paginado / total declarado,
- **V3 sólo PASA si las dos vías concuerdan**; si divergen, el dealer NO PASA y
  entra a filtrado-de-disponibilidad. CARDEX no sirve un coche vendido como vivo.
Esto invalida como "disponible" parte del inventario cageado hoy por sitemap (ver
`state/GAPS.md` H6) — la Inquisición existe precisamente para cazar esto.

## Modelo de orquestación (jerarquía militar)

```
Director Soberano (modelo principal)
  ├─ General ES ─┬─ Teniente AS24 (Tier-1)      ─ Soldados (shards desechables)
  │              ├─ Teniente coches.net          ─ Soldados
  │              └─ Clúster fuentes menores       ─ Soldados
  ├─ General FR ─ … (×6 países: ES FR BE NL DE CH)
  └─ Inquisición (cadena SEPARADA, transversal) ─ Verificadores V1..V5
```
- **General por país**: dueño de su % de cobertura verificada.
- **Teniente por portal Tier-1** y por clúster de fuentes menores.
- **Soldados**: workers desechables, escalables en horizontal.
- Implementación: `Workflow` (script JS determinista) para fan-out/cascada +
  `Agent` para soldados. Definiciones por Wn en sus carpetas.

## Estado vivo
`state/COVERAGE.md` (cobertura por país, método de cada número) ·
`state/SOURCES.md` (fuentes activas/cuarentena) ·
`state/GAPS.md` (huecos confesados con plan y fecha). Se actualizan cada ciclo.
