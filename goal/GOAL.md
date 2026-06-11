# CARDEX — GOAL

> **STALE (2026-06-12).** Historical synthesis of an earlier era; its references
> are outdated (`CONTEXT_FOR_AI.md` was deleted from main). Operative truth:
> code in `main` + `docs/master-plan/`. Kept as institutional memory alongside
> `goal/memory/`.

> Documento de síntesis. Vuelca a Git el contexto que vivía solo en la memoria
> del agente, para que la misión, el estado y los estándares viajen con el
> repositorio. Fuente de verdad de la **arquitectura y qué existe**:
> `CONTEXT_FOR_AI.md` y el código. Este documento captura el **objetivo, el
> estado y cómo se trabaja**.
>
> Procedencia y exclusiones: ver `README.md`. Detalle íntegro por frente:
> `memory/core/` (contexto duradero) y `memory/fronts/` (estado por frente +
> auditorías GUARDIAN).

---

## 1. GOAL #1 — Cobertura 100% del territorio + 900K+ dealers CON WEB

**Qué.** Dos frentes simultáneos hasta cobertura total en **DE / FR / ES / NL /
BE / CH**:

1. **Portales agregadores.** 65 scrapers despachables implementados (T0/T1
   cerrado; cifra verificada en §2). Mantener y llevar
   los 73 portales tier-1 al 100%, guardando la **config de scraping de cada
   portal** (estrategia, faceteo, endpoints, anti-bot, paginación) en
   `configs/portals/<portal>.json`, versionada y reproducible.
2. **Discovery Crawler: TODOS los dealers individuales (~900K+ estimados).** No
   75K, no 140K — TODOS. Cada concesionario, garaje, taller de VO, importador o
   broker con presencia web debe quedar indexado.

**Sin techo (directiva 2026-06-07).** 900K es un **piso, no un techo**. Tres
frentes en paralelo, todos máxima prioridad:
- **(A) DESCUBRIR** más dealers — OSM-full, geo-sweep H3, todos los OEM,
  directorios, registros mercantiles.
- **(B) CONVERTIR** — resolución de dominio `name+ciudad → web` a escala sobre
  los ~520K dealers identificados sin web.
- **(C) SCRAPING A MEDIDA** por dealer — config guardada por web + detección de
  drift + auto-remediación.

### Métrica de éxito (NO confundir)

El objetivo son **dealers CON WEB resuelta** (de los que se puede scrapear
inventario), **NO** filas brutas en `discovery_candidates`. 3M de dealers sin web
no valen nada. **Reportar SIEMPRE "dealers con dominio web", nunca el total
bruto.**

| País | Universo estimado (registros + long tail) |
|------|-------------------------------------------|
| DE | ~36K (KBA/ZDK) + independientes |
| FR | ~38K (SIRENE NAF 4511Z/4519Z) + independientes |
| ES | ~25K (CNAE 4511/4519) + importadores |
| NL | ~12K (KVK/RDW) + importadores |
| BE | ~8K (BCE) + importadores |
| CH | ~5K (ZEFIX) + independientes |
| Long tail | brokers online, importadores sin establecimiento, marketplace sellers → potencialmente 2-3× más |

### Fuentes de discovery (agotar TODAS)

Registros mercantiles (SIRENE, ZEFIX, KVK, BCE, CNAE/DGT, Handelsregister /
OffeneRegister) · OpenStreetMap (car_dealer, car_repair, used_car_dealer) ·
Certificate Transparency · Common Crawl · dealers listados en portales
agregadores · OEM dealer locators · Google Maps Places (car_dealer) · Trustpilot
automotive · asociaciones (BOVAG NL, FEGARBEL BE, AGVS CH, VDA DE) · sitemaps de
portales grandes · búsqueda DDG/Mojeek por ciudad · yellow-pages (PagesJaunes,
GelbeSeiten, Gouden Gids, Páginas Amarillas).

### Pipeline objetivo

`Census → discovery_candidates (PG) → clasificación (CMS, inventario, tier) →
crawl frontier (Thompson Sampling, rate limits, robots.txt) → extracción
multi-strategy (JSON-LD, microdata, OG, body, Next.js/Nuxt, dealerK) → entity
resolution (Fellegi-Sunter dedup cross-source) → delta pipeline → vehicle_index
(altas/bajas) → cadencia adaptiva (scheduler_pg)`.

Detalle completo: [`memory/core/goal_cardex_total_coverage.md`](memory/core/goal_cardex_total_coverage.md).

---

## 2. Estado actual (verificado 2026-06-08)

**Git.** `main` consolidado en **`1ca158a`** con los **8 frentes** —
P0 + P1 + fan-out 5 países + E07 (inventario SPA) + dealer-scraping a medida +
domain-resolution + discovery-scale + P2-hardening. **Suite 1.439 verde**
(de 1.246 → 1.439, cero regresiones). Cada frente auditado por GUARDIAN
(revisión adversarial + rollback armado; `main` nunca roto).

> **2026-06-08:** `main` (`1ca158a`) **pusheado a `origin/main`** (estaba en
> `6e084a5`). El push era la única acción irreversible pendiente; ejecutado con
> autorización explícita del propietario. Este `goal/` se integra a continuación.

> **MÉTRICAS VERIFICADAS 2026-06-08 (autoritativas, vía Postgres `cardex-pg`
> read-only).** Reemplazan cifras previas de snapshot de memoria que resultaron
> infladas/falsas (ver «Corrección» al final del bloque). Cada métrica lleva su query.

| Métrica | Valor REAL | Query / comando |
|---------|-----------|-----------------|
| Portales implementados | **65** scrapers despachables | `awk '/_PORTAL_CLASSES/{f=1} f{print} /^)/{if(f)exit}' scrapers/portals/__init__.py \| grep -cE 'Scraper,?\s*$'` |
| Specs de routing | 69 | `grep -cE 'PortalSpec\(' scrapers/engine/router/domain_map.py` |
| Tiers (primario) | T0=12 · T1=45 · T2=8 · T3=4 | `grep PortalSpec domain_map.py \| sed -E 's/can_escalate_to=Tier\.T[0-9]//' \| grep -cE 'Tier\.Tn'` |
| Origen del "71" | 71 filas en `portal_cadence` (≠ scrapers) | `SELECT count(*) FROM portal_cadence;` |
| Cobertura real | **19 portales con cosecha** (26,8%), **52 en cero** | `SELECT count(DISTINCT source_domain) FROM vehicle_index;` |
| Punteros `vehicle_index` | 436.114 — TODOS de portales libres T0/T1 | `SELECT count(*) FROM vehicle_index;` |
| Gateados T2/T3 | **12, los 12 a 0 filas** (mobile.de, leboncoin, lacentrale, autoscout24.*, kleinanzeigen, coches.net… Akamai/DataDome/CF) | `grep PortalSpec … \| grep -cE 'Tier\.T[23]'` |
| Dealers con web | **≈48,7K** (48.740 a 2026-06-08, **contador vivo**; ≈48,6K dominios únicos) en `discovery_candidates.domain` — tabla `dealers` **VACÍA (0)** | `SELECT count(*) FROM discovery_candidates WHERE domain IS NOT NULL AND domain<>'';` |
| Dealers con web / país | DE 28.971 · NL 6.980 · FR 5.411 · CH 4.135 · ES 1.924 · BE 1.319 | `… GROUP BY country` |
| `vehicles` (store rico) | 563 filas; mobile.de = 6 (todas SEED_DEMO → real 0) | `SELECT count(*) FROM vehicles;` |

**Veredicto (sin maquillaje).** CARDEX es un **esqueleto VALIDADO, no un producto
poblado**: la cosecha real (436.114 punteros) viene ÍNTEGRA de **19 portales
libres T0/T1**; los **12 gateados (los gigantes) están a 0** — el cuello es la
capa **browser/proxy**, no el código. La tabla `dealers` está vacía; los
dealers-con-web viven en `discovery_candidates.domain`.

**Cuello para seguir hacia 900K:** (1) capa **browser/proxy** para los 12 gateados
(mobile.de/leboncoin/lacentrale/AS24/kleinanzeigen/coches.net), hoy a 0;
(2) **conversión a escala** del censo domain-NULL (FR es el mayor yacimiento) con
el `worker.py` del resolver ya en `main`.

> **Corrección — las cifras previas eran snapshot de memoria, infladas:**
> «71 portales implementados» → **65** (el 71 eran filas de `portal_cadence`).
> «45.864 dealers con web» → **≈48,7K y subiendo**, y viven en
> `discovery_candidates`, no en la tabla `dealers` (vacía). «51 de 71 en cero /
> 26,7% de 20 activos» → **52 en cero / 19 con cosecha (26,8%)**. «Censo 685.572 /
> vehicles 30» → `discovery_candidates` ≈764K filas, `vehicles` 563. Las cifras en
> `goal/memory/fronts/*` son snapshots CON FECHA (registro histórico); esta tabla
> las supersede.

**Worktrees aislados** (cada frente en su worktree; `main` intacto):

| Worktree | Rama |
|----------|------|
| `C:\Users\elias\projects\cardex` | (operativo; aquí vive `main`) |
| `C:\Users\elias\projects\cardex-dealer-scraping` | feature/dealer-scraping-system |
| `C:\Users\elias\projects\cardex-discovery-mega` | feature/discovery-mega |
| `C:\Users\elias\projects\cardex-discovery-scale` | feature/discovery-scale |
| `C:\Users\elias\projects\cardex-domain-scale` | feature/domain-scale |
| `C:\Users\elias\projects\cardex-inventory-scale` | feature/dealer-inventory-scale |
| `C:\Users\elias\projects\cardex-p2-hardening` | feature/p2-hardening |
| `C:\Users\elias\projects\cardex-stealth` | feature/stealth-camoufox |
| `C:\Users\elias\cardex-ollama` | feature/ollama-decision-layer |

**Block0 hazard (VIVO).** Segundo checkout `C:\Users\elias\CARDEX` @ `42dec67`
con frontend único sin commitear, protegido con bundle de rescate; consolidación
pendiente del propietario. **No se toca.**

**Cautelas operativas vigentes:**
- Ruido CRLF↔LF del mount → **nunca** `git add .`; añadir rutas concretas y
  revisar el diff.
- `.git/index.lock` huérfano → se borra solo desde el host; no forzar.
- `core.autocrlf=true`; remote `https://github.com/sublimine/CARDEX.git`
  (privado), credential helper `manager`.

Estado por frente, con auditorías GUARDIAN incluidas, en
[`memory/fronts/`](memory/fronts/) (ver su [`MEMORY.md`](memory/fronts/MEMORY.md)).

---

## 3. Estándares de trabajo (cómo se opera)

Resumen; el detalle vive en `memory/core/feedback_*.md` y en la doctrina global.

- **Antialucinación tolerancia cero.** Cada afirmación es `[VERIFICADO]` (leí la
  fuente) o `[ASUMIDO]`. Si el código contradice la memoria, gana el código.
- **Cero atajos.** Sin placeholders, TODOs, stubs ni parches que tapan el
  síntoma. Atacar siempre la causa raíz.
- **Ejecutar hasta cerrar.** Autorización amplia: no pedir permiso para lo
  reversible; confirmar solo lo irreversible/alto coste. No parar a preguntar si
  la directiva es clara; tomar la decisión más ambiciosa y reportar con
  evidencia.
- **NUNCA defaultear a "no se puede".** Agotar toda vía técnica; preferir
  gratis/open-source; aparcar lo de pago en backlog, nunca bloquearse por dinero
  (presupuesto ~300 CHF/mes, preferir cero coste).
- **Esfuerzo sin techo.** Cuando se pide investigar/cubrir, abarcar el universo
  completo, no una muestra. Persistir hallazgos a `.md`/`.json` por fases.
- **Research-first.** Antes de implementar: buscar implementaciones existentes
  (GitHub, registros de paquetes, docs primarias), probar endpoints reales,
  documentar; solo entonces codear.
- **Resiliencia.** Nunca perder un portal por un cambio de HTML: config-driven
  por web + drift + auto-remediación trazable.
- **Higiene.** Limpiar worktrees siempre; máximo de tareas de código en
  paralelo; nada de zombies.
- **Idioma.** Respuesta en español; código y comentarios en inglés.
- **Modelos.** Orquestador en Opus; subagentes en el modelo justo a la tarea.

Estándares completos: [`memory/core/INDEX.md`](memory/core/INDEX.md) §"Estándares de trabajo".

---

## 4. Arquitectura objetivo (resumen)

- **Microagentes, no monolitos.** Un agente fresco por microtarea (descubridor →
  localizador de catálogo → extractor de HTML → parser/scraper → entity
  resolution …).
- **Paralelización horizontal por país** — pero **primero clavar y validar el
  patrón en un portal/país, luego abanicar a los 6**. Paralelizar solo lo
  aislado en datos (`country=XX` con fuentes/endpoints propios); serializar lo
  que toca estado global mutable (migraciones, reinicios Docker, tablas
  compartidas).
- **Resiliencia anti-ruptura** — config versionada por web, detección de drift
  contra baseline, alertas trazables por origen, equipo de auto-remediación
  (re-detect → regenerate → revalidate, bajo validar-límite-purgar).
- **Dashboard de control total** — supervisión de tiers, crawling, portales y
  descubrimiento de dealers desde un panel.
- **Infra** — local = test (validar el pipeline E2E y purgar listings para no
  saturar disco); producción en VPS o en el terminal 24/7 del propietario, con
  toda la config **plug & play** (`docker compose up -d` sin tocar nada).

Detalle: [`memory/core/project_cardex_architecture.md`](memory/core/project_cardex_architecture.md),
[`memory/core/project_cardex_resilience.md`](memory/core/project_cardex_resilience.md),
[`memory/core/project_cardex_infra_strategy.md`](memory/core/project_cardex_infra_strategy.md).

---

## 5. Referencias

- **Repo:** `github.com/sublimine/CARDEX` (privado). Path local:
  `C:\Users\elias\projects\cardex`. Backend `:8506`, frontend dev `:5173`.
- **APIs externas** (estado, sin claves): [`memory/core/reference_api_credentials.md`](memory/core/reference_api_credentials.md)
  — VIES, INSEE SIRENE, YouTube Data, Shodan, Censys activos; NHTSA vPIC / RDW
  públicas; Pappers y KvK-prod pendientes. Valores reales en vault/env.
- **Fuentes de verdad del repo:** `CONTEXT_FOR_AI.md` (arquitectura), luego el
  código, `deploy/`, `planning/`, `SPEC.md` (visión original, parcialmente
  superada), `STATUS.md` (bugs/bloqueadores vivos).
- **Atribución:** CARDEX = Elias (operador que dirige estas sesiones y da las
  directrices del goal/estado). Cobrix = Salman. Mantener la separación. Ver
  [`memory/core/user_salman_cardex.md`](memory/core/user_salman_cardex.md).
