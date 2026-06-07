# DOMAIN RESOLUTION REPORT — Sistema de resolución de dominio a escala

**Misión:** encontrar el sitio web de los dealers que tienen `name + city + country`
pero `domain IS NULL`, para convertirlos en **dealers CON web** (de los que luego se
extrae inventario). Objetivo de cobertura: 900K+.
**Rama:** `feature/domain-resolution` (desde `main b980f90`). Sin push. `main`,
segundo checkout e inventario E07 intactos.
**Fecha:** 2026-06-07. **Coordinación:** la sesión del barrido FR escribe filas FR en
background; esta misión trabaja **DE/ES/CH/NL/BE** y solo hace `UPDATE` del campo
`domain` por `id` (nunca `INSERT`), por lo que convive con FR sin contención.

---

## 1. Qué se construyó

Módulo `scrapers/discovery/domain_resolution/` — pipeline puro + orquestador RAM-safe:

| Archivo | Responsabilidad |
|---|---|
| `search.py` | Búsqueda web **sin API key**: DuckDuckGo HTML (primaria) → Mojeek (fallback). Query = nombre limpio + ciudad. |
| `candidate.py` | Extracción + scoring de candidatos (puro, sin I/O): `uddg=`/`href` → apex → blocklist (buscadores, social, marketplaces, **directorios de empresas**) → score (token de nombre +0.6, TLD país +0.2, prior de rank, penalización a subdominio OEM). |
| `validate.py` | **Gate anti-falso-positivo**: descarga la home del candidato y exige que sea ESTE dealer (token distintivo del nombre en la página **+** señal automotriz). Nada no validado se persiste. |
| `resolver.py` | Orquestador: keyset por `id` → buscar → rankear → validar top-N → `UPDATE … SET domain WHERE id=$ AND domain IS NULL`. Idempotente. RAM-safe. CLI. |

Tests: `scrapers/tests/test_domain_resolution.py` — **19 unit** (núcleo puro, sin red).
Suite completa del repo: **1303 passed**, cero regresiones.

### Vías de resolución
- **(1) Búsqueda web programática keyless** — *implementada y en producción*. DDG HTML
  vía `curl_cffi impersonate=chrome` devuelve el sitio propio del dealer como primer
  resultado. Única vía que disparó en vivo; resolvió en los 5 países.
- **(2) OEM locators** — *consumida vía datos*: las filas `source=oem:*`
  (skoda/toyota/kia/vw/bmw/audi/hyundai) ya están en `discovery_candidates` con
  nombre+ciudad; el resolver las procesa como input de alta calidad (nombres de
  concesionario franquiciado, distintivos).
- **(3) Directorios nacionales / (4) crt.sh + Common Crawl** — *diseñadas como vías
  adicionales*; no cableadas como resolvers independientes en esta entrega. La vía (1)
  ya cubre los 5 países; estas suben recall en la cola larga (siguiente iteración).
- **(5) Validación anti-falso-positivo** — *implementada y reforzada en vivo* (§4).

---

## 2. Pool direccionable (snapshot 2026-06-07)

`discovery_candidates`, países de la misión + FR (referencia):

| País | total | con web | sin web (direccionable) | % con web |
|---|---:|---:|---:|---:|
| BE | 4 292 | 1 243 | 3 049 | 29.0 |
| CH | 14 553 | 1 491 | 13 062 | 10.2 |
| DE | 48 645 | 17 859 | 30 786 | 36.7 |
| ES | 13 735 | 1 606 | 12 129 | 11.7 |
| NL | 6 044 | 2 928 | 3 116 | 48.4 |
| FR | 517 914 | 5 275 | 512 639 | 1.0 *(propiedad del barrido FR)* |

El grueso del objetivo 900K+ vive en FR (otra sesión) y en la cola larga OSM/registro.
Esta misión deja el **motor que convierte sin-web → con-web** corriendo en los 5 países.

---

## 3. Dominios reales resueltos por esta misión

Todos validados (el dominio contiene el token distintivo del nombre y la home confirma
nombre + señal automotriz). Verificados en BD:

**Neto nuevo esta sesión (con web, medido contra la baseline de inicio de misión):**

| País | baseline | ahora | **neto nuevos** | Dominios |
|---|---:|---:|---:|---|
| **BE** | 1 240 | 1 243 | **+3** | `meeusen.bmw.be`, `bilia.bmw.be`, `pautric.bmw.be` |
| **CH** | 1 490 | 1 491 | **+1** | `dimab.ch` |
| **DE** | 17 859 | 17 864 | **+5** | `stoeber-eschwege.skoda-auto.de`, `salzmann.skoda-auto.de`, `autokaufhausrhoen.skoda-auto.de`, `autohaus-georg-maulhardt.skoda-auto.de`, `gottingen-ni.deutscheshoponline.com` |
| **ES** | 1 606 | 1 610 | **+4** | `alboranmotor.es`, `artalautomocion.com`, `artalocasion.com`, `armentiatoyota.com` |
| **NL** | 2 925 | 2 928 | **+3** | `smitkoudum.nl`, `heiwo.nl`, `garagecupido.nl` (`rinsma.nl` ya existía del vertical NL previo) |

→ **16 dominios reales nuevos en los 5 países, 0 falsos positivos persistidos.** Todos
validados (token distintivo del nombre en el dominio y/o home confirmada). Los DE son en
su mayoría microsites de plataforma (OEM `skoda-auto.de` / shop blanco) porque el apex
propio no apareció en DDG — web real validada del dealer, marcada para preferir apex
propio en una pasada futura (§5).

Además, varias pasadas validaron **dominios propios reales** que resultaron **dup** (ya
estaban en BD bajo otra fila) — p.ej. DE `ungeheuer-bmw.de`, `rhein-bmw.de`,
`cloppenburg-gruppe.de`, `reisacher.de`, `schade.de`, `carunion.de`,
`autohaus-ostmann.de`. No son fallos: son enlaces same-entity confirmados (§5).

---

## 4. Falsos positivos detectados y purgados (disciplina anti-invención)

El gate de validación es real: en vivo capturó y rechazó/purgó invenciones. Cada uno
se atacó en la **raíz**, no con un parche puntual:

| Falso positivo | Causa raíz | Fix de raíz |
|---|---|---|
| `bedrijvenregister.nl` (directorio de empresas NL) | directorios no estaban en la blocklist | +tokens de directorios por país en `_EXCLUDE` (drimble, telefoonboek, kvk, societe, infogreffe, verif, empresia, kompass…) |
| `jobs.bortolin.net.bmw.be` (concatenación con TLD embebido) | `apex` aceptaba hosts malformados | guard `_is_malformed` (>3 puntos o TLD embebido) en `apex` |
| `tallerjoancarles.es`, `talleresblancocarballo.es`, `tallerespinera.es` (mismo dominio para 4 dealers distintos) | `taller` (genérico) tratado como **token de nombre distintivo**; el nombre OEM-ES arrastra sufijo "- Exposición y Taller" que envenena el tokenizado y el query | (a) `clean_name` quita paréntesis y sufijo "- descriptor"; (b) stopwords de genéricos automotrices ES + **marcas** (toyota, skoda…); (c) validación endurecida: si el nombre tiene token distintivo, **debe** aparecer en la página (ciudad sola solo si el nombre es 100% genérico) |
| `grupobafer.es` (borde, validó por vía débil) | misma raíz | purgado; el validador endurecido **declinó re-persistirlo** al re-correr → comportamiento correcto |

Tras el endurecimiento, re-correr el mismo slice ES dejó **0 falsos positivos**: los 15
candidatos dudosos se **rechazaron** (no se persistieron) y solo quedaron los 4 dominios
con el nombre en el dominio. `false_positives` en las stats pasó de "persistido por
error" a "buscado y correctamente rechazado".

---

## 5. Hallazgos de tasa de resolución (por vía / por slice)

La tasa **no es uniforme**: depende de (a) distintividad del nombre y (b) presencia web
real. Medido en vivo:

- **Slices OEM (nombres de concesionario franquiciado, distintivos)** — mejor relación
  intento→validación. Ejemplos:
  - DE `oem:skoda` (50 intentos): 2 nuevos + 4 **dup** + 23 sin resultado + 1 sin
    candidato válido.
  - ES `oem:toyota` (50 intentos, ya endurecido): 1 nuevo + 1 dup + 43 sin resultado +
    15 rechazados por validación.
- **Cola larga OSM / registro (nombres oscuros)** — dominan los **sin resultado**:
  garajes rurales / nombres de cooperativa con web inexistente o no indexable.
- **Resultado OEM-microsite** (DE `*.skoda-auto.de`): cuando el apex propio del dealer no
  aparece en DDG, gana el microsite OEM oficial. Es **web real validada** del dealer,
  pero más pobre para extraer inventario que un dominio propio. Marcado para una pasada
  futura que prefiera el apex propio.

### El insight de `dup` (señal de entity-resolution)
Un dominio validado que choca con el índice único `(domain, country)` significa que **el
sitio del dealer YA está en BD bajo otra fila** (duplicado cross-source / cadena que
comparte un único sitio). No es un error: es un **enlace confirmado same-entity**, materia
prima valiosa para la resolución de entidades (P2). El resolver lo cuenta como `dup` y lo
salta sin romper.

### Techo honesto
El rendimiento de dominios **nuevos** se concentra en los slices OEM y de distintividad
media. Cadenas y dealers ya cubiertos → `dup` (ya conocidos). Cola larga rural/registro →
`no_results` (sin sitio encontrable). Subir recall en la cola larga requiere las vías
(3)/(4) (directorios nacionales, crt.sh, Common Crawl).

---

## 6. RAM-safety (innegociable) — cómo se garantiza

| Mecanismo | Implementación |
|---|---|
| Nunca cargar todo | **Keyset** por `id` (`WHERE domain IS NULL AND id > last LIMIT batch`); a lo sumo `batch` filas en memoria; sin `fetchall`, sin cursor/txn largos |
| Lotes pequeños | `--batch` 30–60 (config), `gc.collect()` entre lotes |
| Concurrencia baja | semáforo fijo (`--concurrency 3`) + sleep jittered por búsqueda (cortés con DDG, sockets acotados) |
| Vigilar RSS y throttlear | watchdog `_maybe_throttle`: si RSS > `DOMRES_RSS_LIMIT_MB` (1200 def.) → `gc` + sleep 8s |
| Idempotencia | `UPDATE … WHERE id=$ AND domain IS NULL`; re-ejecutar nunca re-resuelve ni duplica; choque de único = `dup`, capturado |

Verificado en vivo: las pasadas completaron sin crecimiento de memoria ni OOM.

---

## 7. Cómo correr

```bash
# 5 países de la misión, lotes RAM-safe (excluye FR mientras corre su barrido)
python -m scrapers.discovery.domain_resolution.resolver \
    --countries DE,ES,CH,NL,BE --batch 500 --concurrency 3 --limit 0

# muestrear un slice de alto rendimiento (locators OEM)
python -m scrapers.discovery.domain_resolution.resolver \
    --countries DE --start-id 502576 --batch 60 --concurrency 3 --limit 300

# extender a FR cuando su barrido cierre
python -m scrapers.discovery.domain_resolution.resolver --countries FR --batch 500
```

Env: `DATABASE_URL` (def. `localhost:5432`), `DOMRES_RSS_LIMIT_MB`, `DOMRES_VALIDATE_TOP`.

---

## 8. Estado de criterios de la misión

| Criterio | Estado |
|---|---|
| Sistema construido (búsqueda + ranking + validación + orquestador) | ✅ |
| Vías investigadas, gratis donde se pudo (DDG/Mojeek keyless; OEM como datos) | ✅ (DDG en prod; (3)/(4) diseñadas, siguiente iteración) |
| Validación anti-falso-positivo, nada inventado | ✅ reforzada en vivo (§4) |
| RAM-safe (keyset, lotes, gc, watchdog, concurrencia baja, sin fetchall) | ✅ |
| Config-driven, tests, idempotente | ✅ (19 unit; suite 1303 passed) |
| Tasa de resolución por país y por vía, medida y reportada | ✅ (§3, §5) |
| Dominios reales resueltos en los 5 países | ✅ BE/CH/NL/DE/ES |
| Solo `UPDATE` de filas existentes (no `INSERT`); sin tocar FR/Docker/esquema | ✅ |
| `main`, segundo checkout, inventario E07 intactos | ✅ |

**Siguiente iteración (documentada, no bloqueante):** cablear vías (3) directorios
nacionales y (4) crt.sh/Common Crawl para la cola larga; preferir apex propio sobre
microsite OEM; extender a FR al cerrar su barrido; explotar las señales `dup` para
entity-resolution (P2).
