# CARDEX — HANDOFF (traspaso de estado, intenciones y métodos)

> Escrito 2026-06-10 por Claude Opus 4.8 para que CUALQUIER modelo/herramienta (Fable 5, Codex, etc.)
> continúe sin perder un paso. Todo aquí es [VERIFICADO] contra el repo/DB salvo lo marcado [PLAN].
> Fuentes de verdad: `CARDEX-COMMAND/GOAL.md` (mandato), `docs/master-plan/MASTER_PLAN_AZ.md` (plan A→Z),
> `docs/master-plan/architecture/*` (7 specs), `CARDEX-COMMAND/PROGRESO.md` (bitácora cronológica).

## 0. TL;DR — dónde estamos y qué sigue
- **Master plan A→Z definido y aprobado** (9 fases). **FASE A COMPLETA** (gobierno). **FASE B EN CURSO.**
- Repo: rama `main`, último commit `99d6ef1`. Suite: 1669 verde + 7 nuevos (cdx_code, verificados aislados;
  re-correr suite completa en el próximo checkpoint).
- **Siguiente acción inmediata (FASE B, Bloque 2-3): migración `migrations/0005_*.sql`** que (a) añade
  `dealers.cdx_code text UNIQUE` y (b) crea la tabla `entity_xref` (crosswalk). El generador ya existe
  (`scrapers/intelligence/cdx_code.py`, probado). Ver §5.

## 1. La misión (no negociable — de GOAL.md)
Índice pan-EU de coches usados. Cobertura **100%** de los 6 países (ES·FR·BE·NL·DE·CH) de TODA entidad
con web+inventario (concesionarios, compraventas, garajes, desguaces, plataformas). Por entidad:
descubrir → resolver web → extraer 100% inventario → enjaular en API per-entidad VIVA con delta
(altas/bajas/precio/foto/historial) → verificación adversarial multi-vía → alertas + resiliencia.
Recetas portables por entidad. Estructura país→provincia→ciudad + cdx_code. Fin último: acuerdos legales
(XML/API directo); el scraping es el puente.

## 2. Doctrina de trabajo (CÓMO operar — esto es lo que más se me olvidaba)
- **Sistema, no fragmentos.** El trabajo es EL SISTEMA que cierra países al 100%, no trozos sueltos.
- **Plan A→Z por fases con GATES.** Cada fase se cierra con un criterio medible.
- **Jerarquía de orquestación:** top-orquestador (el modelo principal) → jefe-orquestador por workflow →
  workers + un agente verificador/motivador. Los 7 agentes están en `.agents/cardex/` (portables).
- **Verificación adversarial CO-IGUAL:** NUNCA confiar la 1ª respuesta. Quórum ≥2 vías ORTOGONALES
  (distintas de la productora). Forzado en DB por `verification_verdicts` (CHECK chk_quorum). Verificar
  números Y contenido (completitud/frescura/correctness).
- **NUNCA "no se puede":** agotar todas las vías + agente de investigación web (GitHub/Reddit/foros) para
  herramientas open-source (Camoufox + arsenal). Proxies de pago permitidos cuando aporten.
- **Anti-alucinación absoluta:** cada afirmación [VERIFICADO] (leída) o [ASUMIDO]. **El código/realidad del
  repo MANDA sobre el plan** (ya pasó: el plan asumió migración "0006/.up.down"; el repo real era 0002
  single-.sql → se usó la realidad). Verificar esquema/endpoint/`ls` ANTES de crear o afirmar.
- **Aditivo + reversible + idempotente.** Migraciones con `IF NOT EXISTS` + `-- Rollback:` inline, probadas.
- **Coste-eficiente:** LLM local (Ollama :11434 `qwen2.5:3b`) para clasificación/parsing/dedup; el modelo
  grande para decisiones/arquitectura.
- **Prompts de MÁXIMA calidad** a todo subagente (input pobre = output pobre).
- **main = única fuente de verdad** (push no-force autorizado). Nada "hecho" hasta estar en origin/main verde.
- **Cada bloque:** implementar → verificar real (E2E) → test → commit → push → actualizar PROGRESO.md.
- **Cero maquillaje.** Si está incompleto/roto, decirlo con la evidencia.

## 3. Frenos (gates — confirmar con el owner antes de cruzar)
1. **Gastar dinero** (proxies de pago, captcha, VPS, créditos) — último recurso tras agotar lo libre.
2. **VPS / despliegue público / comunicación externa.** El VPS NO se toca hasta cobertura 100% E2E de los
   6 países probada EN LOCAL, con recetas. Todo se hace y prueba aquí; el VPS solo corre el llenado masivo
   final. Todo lo reversible (código, migraciones, scrapers locales, push no-force a main) se ejecuta sin pedir permiso.
- NUNCA tocar `C:/Users/elias/CARDEX` (es otra cosa; el proyecto vive en `C:/Users/elias/projects/cardex-integration`).

## 4. Entorno (verificado)
- Proyecto: `C:/Users/elias/projects/cardex-integration` (git, rama `main`, remoto github sublimine/CARDEX).
- Python: `/c/Users/elias/AppData/Local/Programs/Python/Python311/python` (3.11.9). Paquetes: asyncpg,
  httpx 0.27, curl_cffi 0.15, playwright, camoufox, browserforge, pyyaml.
- Store REAL: PostgreSQL 16 (docker `cardex-pg`, DSN `postgres://cardex:cardex_dev_only@localhost:5432/cardex`)
  + Redis (docker `cardex-redis-dev` :6379). Throwaway Redis para harness de inventario: `:56390`
  (docker `cardex-redis-throwaway`, levantado por mí; `THROWAWAY_REDIS_URL=redis://localhost:56390`).
- Chromium de Playwright: instalado y lanzable. Ollama LLM local: `:11434` `qwen2.5:3b` (OLLAMA_URL/OLLAMA_MODEL).
- IMPORTANTE: la API gov FR `recherche-entreprises.api.gouv.fr` nos rate-limitó/baneó la IP por exceso de
  concurrencia. NO machacarla. La vía robusta FR = **opendatasoft SIRENE v3** (host distinto, no penalizado):
  `https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/economicref-france-sirene-v3/exports/csv`
  con `?where=activiteprincipaleetablissement="45.11Z" and etatadministratifetablissement="Actif"&limit=-1`
  (delimitador **;**, BOM al inicio). ~505k establecimientos auto FR. Loader: `scripts/sirene_ods_load.py`.

## 5. Estado del repo y de la DB (verificado 2026-06-10)
### Migraciones aplicadas (`migrations/`, convención single-.sql + `-- Rollback:` inline)
- 0001 vehicles_created_at · 0002 discovery_governance (ledger + cols tier/geo) · 0003 verification_verdicts
  (VAM, quórum DB-enforced) · 0004 geo_hierarchy (geo_country=6, geo_city=20.661, geo_region=0).
- **PENDIENTE 0005** (FASE B): `ALTER TABLE dealers ADD COLUMN IF NOT EXISTS cdx_code text;` +
  `CREATE UNIQUE INDEX ... ON dealers(cdx_code) WHERE cdx_code IS NOT NULL;` + tabla `entity_xref`
  (`cdx_code text, ref_table text, ref_key text, country char(2), created_at timestamptz default now(),`
  `UNIQUE(cdx_code, ref_table, ref_key)`). Aplicar E2E (apply→verify→rollback→re-apply→contar filas).
### Tablas clave (filas reales)
- `discovery_candidates` = 114.620 (entidades descubiertas; cols country/city/postcode/province[vacía]/h3_res7).
- `vehicles` = 333.889 (inventario caged: plataformas AS24-FR 92.759 al 98,8% + AS24-ES; entity_ulid, h3).
- `dealers` = 0 (tabla CANÓNICA de entidad consolidada, 36 cols, VACÍA — su pipeline de consolidación es FASE E).
- `source_entities` = 0 (scaffolding engine; entity_ulid/domain/defense_tier). `entity_inventory`/`entity_matches` vacías.
- `geo_country`=6, `geo_city`=20.661, `geo_region`=0. `discovery_runs`/`discovery_source_runs`/`verification_verdicts` vacías (listas).
### Cobertura discovery por país: NL 38.719 · DE 26.122 · ES 17.356 · FR 16.416 · BE 8.456 · CH 5.050.

## 6. Lo que YA funciona y está probado (construir encima, no reescribir)
- **Extracción de plataforma E2E al 98,8%** (AS24-FR 92.759/93.922 declarado, TRUSTWORTHY). Método:
  facet-partition por precio + **multi-pasada + sort estable** (`sort=age&desc=0`) + count-verify.
  Harness: `scripts/run_giant_scraping.py` (--full --keep --passes N; fetching concurrente + rate-limiter).
- **Extracción de dealer E2E al 100%** (dacia-meaux.fr 230/230 vs declarado, purga limpia).
  Harness: `scripts/close_entity.py` (--domain --country --pdp-re). Grind resumable: `scripts/grind_coverage.py`
  (coverage_ledger). Seam: `scrapers/dealer_scraping/seam.py`. Fetcher con retry/backoff: `harvester.make_dealer_fetcher`.
- **Discovery anclas verificadas:** as24_dealers (34.5k, 5 países), OEM 10 marcas, OSM, RDW-NL, SIRENE-ods.
  Gate anti-rot: `scripts/verify_connectors_live.py`. Verificador discovery adversarial: `scripts/verify_discovery.py` (--fill).
- **Capture-recapture** (Chapman): `scrapers/intelligence/capture_recapture.py` (estimador ortogonal del universo).
- **cdx_code**: `scrapers/intelligence/cdx_code.py` (generador inmutable).
- **Scheduler**: `scripts/master_scheduler.py` (incluye discovery_sweep cada 24h, FASE A).

## 7. El plan A→Z (resumen; detalle en MASTER_PLAN_AZ.md)
A Gobierno [HECHO] · B Columna institucional geo+cdx_code+xref [EN CURSO] · C Taxonomía D0-D3×tipo×CMS ·
D Anti-detección Tier-1 (Camoufox+OSS, cerrar mobile.de ≥99%) · E Discovery gobernado piloto FR (matriz +
dedup 3 capas + completitud 3-vías) · F Extracción + multiplicador CMS (receta por familia) · G VAM como
gate (publish_gate) · H API viva+delta+legal · Z Abanico a los 6 países + sello de cobertura (2 KPIs honestos).

## 8. Cómo continuar (receta operativa para el siguiente modelo)
1. Lee GOAL.md + MASTER_PLAN_AZ.md + este HANDOFF + el final de PROGRESO.md.
2. Retoma FASE B Bloque 2-3: escribe `migrations/0005_entity_identity.sql` (cdx_code en dealers + entity_xref),
   aplícala E2E contra PG vivo (patrón: apply → verificar tablas/cols → ejecutar Rollback → verificar limpio →
   re-aplicar → contar 114.620/333.889 preservadas → idempotencia). Commit+push+PROGRESO. Pasa code-reviewer/
   security-reviewer (Agent) sobre la migración.
3. Cierra FASE B (GATE: geo cuadra, cdx_code único, cero huérfanos, 18 tablas comerciales intactas, suite verde).
4. Encadena FASE C. Mantén la cadena de fases con gates. NO entregues fragmentos sueltos.
5. Patrón de verificación de migración E2E (probado): ver `scripts/` y los commits 0002/0003/0004 como ejemplo.

## 9. Lecciones grabadas (no repetir)
- APIs gov de lookup banean → usar DUMPS descargables + rate-limiters globales (token-bucket) desde el inicio.
- Concurrencia sin rate-limiter = ban (pasó 3 veces con la API FR a conc 12→5→4; la cura fue el token-bucket).
- Una sola pasada de plataforma rinde ~88%; multi-pasada + sort estable → ~99%.
- El plan del arquitecto puede asumir cosas falsas (migración 0006/.up.down) — VERIFICAR el repo real siempre.
- Entregar fragmentos (20k+10k+800) NO es el trabajo; el owner mide el SISTEMA que cierra países al 100%.
