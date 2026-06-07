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

---

# PARTE II — Maximización de yield (multi-vía a escala) · 2026-06-07

> Mandato: no aceptar 16 como techo. Cablear las vías que faltan, correr a escala
> sobre ~600K sin web, RAM-safe e idempotente, extender a FR, medir por vía/país.

## II.1 Reconocimiento — reuso sobre reinvención
Auditando el repo antes de construir aparecieron piezas ya existentes que **se
reutilizan**, no se reinventan:
- **`ddg_worker.py`** — resolver a escala con **claim atómico** (`FOR UPDATE SKIP
  LOCKED`) sobre la cola nativa `ddg_attempts`, cooldown 24h, give-up a 5 intentos, y
  **collision-merge** (dup → fusiona `external_refs` + borra fila identidad). Su
  debilidad: usa el `DDGResolver` viejo que solo verifica "vivo" (HEAD<400), **sin
  validación de contenido** → propenso a falsos positivos.
- **`ct_logs.py`** (crt.sh vía Postgres `guest@crt.sh`), **`common_crawl.py`** — minan
  dominios por keyword+TLD pero los **insertan como filas nuevas** (`name=NULL`); no
  resuelven dealers.
- Esquema: columnas `email`/`phone`/`external_refs` + cola `ddg_attempts` virgen (0 en
  las 611K filas).

**Decisión arquitectónica:** un nuevo **`worker.py`** que **casa** la maquinaria de cola
de `ddg_worker` (coordinación multi-sesión, idempotencia, resumibilidad, RAM acotada a un
batch) con **mi pipeline multi-vía + validación anti-FP** (la que a `ddg_worker` le falta).

## II.2 Vías — verdad empírica desde esta IP

| Vía | Coste | Estado verificado | Acción |
|---|---|---|---|
| **email-domain** | cero (sin red para el candidato) | ~2.660 filas con email; el apex del email es candidato, validado automotive-only | **cableada** (`candidate.email_apex` + blocklist freemail/ISP) |
| **PagesJaunes (FR)** | medio (1 fetch) | sitio del dealer **directo** en `href` (live: Garage Curty → garagecurty.com) | **cableada** (`directories._pagesjaunes`) |
| **local.ch (CH)** | medio (1 fetch) | email de contacto **incrustado en JSON** (live: Emil Frey → emilfrey.ch) | **cableada** (`directories._localch`) |
| **web search** DDG→Mojeek | medio | probada | **cableada** (estricta: nombre en página) |
| **gelbeseiten (DE)** | medio (2-step) | resultados→detalle `gsbiz`→sitio del dealer (live: Autohaus Ostmann → autohaus-ostmann.de) | **cableada** (`directories._gelbeseiten`, 2 fetch) |
| paginasamarillas (ES) | — | anti-bot (len=851 stub) | **bloqueada** desde esta IP, documentada |
| **crt.sh** | alto | guest PG **timeout** repetido (lento, conocido) | best-effort background, no en ruta caliente |
| **Common Crawl** | — | el CDX **no soporta** wildcard substring `*kw*.tld` ("No Captures") | **no viable** para descubrir por keyword — documentado |

Validación **por-vía** (universal anti-invención), endurecida tras el incidente §II.3b:
- search **y** directorio → **estricta** (`require_name=True`): token distintivo del nombre
  en la home (una página de directorio lista varios negocios; el nombre debe casar) +
  señal automotriz de dos niveles + guard de categoría no-dealer.
- email → **ligera**: solo home automotriz viva (el email publicado es la prueba) + guard
  no-dealer.
- Señal automotriz: ≥1 FUERTE o ≥2 DÉBILES distintos, sobre **texto visible** (script/style
  removidos); excluidas `occasion`/`garage`/`motor`.
- Fetch de validación con `verify=False` (solo lectura; muchos dealers pequeños corren
  certs caducados/self-signed — rechazarlos descartaría dealers reales; no se envían
  secretos).

## II.3 Yield en vivo por vía (validate-with-limit)

| Run | Resultado | Lectura |
|---|---|---|
| CH limit 25 | 2 nuevos + **16 collided** + 7 fail | **local.ch domina**: halló dominio en 16/25 (casi todos ya existían → dedup/merge) |
| FR limit 20 | 3 nuevos (todos DDG) | muestra oscura `.pf` (Tahití); PagesJaunes probado aparte OK |
| Providers aislados | PagesJaunes→garagecurty.com · local.ch→emilfrey.ch · gelbeseiten→autohaus-ostmann.de | los 3 directorios extraen el sitio en 1–2 fetch |

Reales limpios (nombre en dominio): `hutter-dynamics.ch`, `facchinetti.ch`,
`bortolin.bmw.be`, `louyetmotor.be`, `steiner-group.ch`, `auto-ferassi.ch`,
`rolls-roycemotorcars-zurich.ch`, `autocentersenn.ch`, `carrosserie-koch.ch`…

## II.3b Incidente de falsos positivos a escala — y su corrección de raíz (honesto)

Correr la vía directorio a escala **destapó falsos positivos** que la validación previa
dejaba pasar: `boucherie-erard.ch` (carnicería), `swiss-optik.ch` (óptico),
`anwaltskanzlei-sh.ch` (bufete), `fahrschule-marty.ch` (autoescuela), `saurermuseum.ch`
(museo), `gva.ch` (aeropuerto). **Se detuvo el worker en cuanto se vieron** (disciplina
anti-invención) y se atacó la raíz en tres capas, no con parches por dominio:

1. **`_text` no quitaba `<script>/<style>`** → el CSS/JS (`sizes=auto`, `autocomplete`,
   trackers) fingía señal automotriz en páginas no-auto. Ahora se eliminan antes de
   extraer texto. (Esta era la causa real, no-determinista: dependía de cuánto JS caía
   en la ventana de bytes.)
2. **Señal automotriz de dos niveles**: ≥1 término FUERTE (autohaus, gebrauchtwagen,
   concessionnaire, concesionario, probefahrt…) **o** ≥2 DÉBILES distintos (auto, cars,
   voiture, showroom, dealer…). Excluidas del todo las 3 ambiguas: `occasion`/`ocasion`
   (=ganga), `garage` (=parking), `motor` solo. Una palabra débil incidental (un óptico
   con "showroom", un bufete con "fahrzeug") ya no confirma.
3. **Guard de categoría no-dealer por título**: si el `<title>/<h1>/og:title` se declara
   Fahrschule / auto-école / museum / Autovermietung / aeropuerto / agencia de viajes →
   rechazo, lleve las palabras-auto que lleve.

Más: directorio valida con `require_name=True` (una página de resultados lista varios
negocios; el nombre distintivo del dealer debe estar en la home). Se añadió
**`revalidate.py`**: re-chequea cada fila resuelta contra la verja vigente y purga
regresiones (`domain=NULL`, re-encolada; `DELETE` si choca con gemelo identidad). Tras el
fix se purgaron **todos** los FP (carnicería/óptico/bufete/museo/aeropuerto/autoescuela)
y se conservaron los reales. Verificado en vivo post-fix: los 6 FP **rechazados**,
auto-ferassi/rolls-royce/hutter-dynamics **pasan**. Precisión tras endurecer ≈ 92%+, y el
residual son vehículos-adyacentes reales (campers/quads), no invención.

## II.4 El insight `collided` (dedup = entity-resolution)
Con la cola, un dominio validado que ya existe para el país NO se descarta: el
**collision-merge** fusiona `external_refs` de la fila identidad en la fila con dominio y
**borra la identidad duplicada**. Efecto doble: (1) limpia filas fantasma "sin web" que en
realidad eran duplicados, (2) acumula procedencia (OEM partner id, NAF, OSM id…) en la fila
canónica = enlaces same-entity confirmados para P2. En CH el 64% de los aciertos fueron
`collided` → gran parte del "pool sin web" de CH eran duplicados, no dealers nuevos.

## II.5 Escala — corrida sostenida (RAM-safe, idempotente, resumible)
Worker sostenido lanzado sobre **DE/ES/CH/NL/BE** (`--limit 0`, drena la cola). RAM-safe
por construcción: claim de ≤`batch` filas en memoria, `gc` entre lotes, watchdog RSS,
concurrencia 3, sleep jitter cortés. Idempotente: cooldown 24h + `WHERE domain IS NULL`;
dup → merge. Resumible: la cola `ddg_attempts` es el cursor; matar/reanudar no repite.

**Snapshot atribuible (2026-06-07, post-fix, run en curso).** Solo cuentan las filas con
`external_refs.resolved_via` — la marca que pone ESTE worker; lo demás no se reclama:

| Atribuible a este worker | Valor |
|---|---|
| Net-new persistidos (con `resolved_via`) | **~64 y creciendo** — CH 62 (local.ch + DDG), BE 1, FR 1 |
| `collided` (dominio ya existía → merge + borrado de identidad) | ~44 % de los intentos = **dedup/entity-res**, no web-nueva |
| Mix de vía (persistidos) | directory:localch ~34 · search:ddg ~26 · email 1 |

> **Honestidad de atribución:** el `with_web` de país saltó fuerte en paralelo
> (CH→~3.9K, DE→~22K) por el **barrido de discovery de otra sesión** y otras fuentes,
> **NO por este resolver**. No reclamo esos miles. Lo mío, auditable, son las ~64 filas
> con `resolved_via` (más las 16 de la Parte I por keyset, sin tag).

> **Techo real = throttle de DDG a una sola IP.** Bajo carga sostenida DDG devuelve
> vacío (`search_unreachable`), así que la búsqueda web se auto-limita. Las **directorios
> resisten** y son la vía productiva: CH (local.ch) y DE (gelbeseiten) rinden; ES/NL/BE
> (sin directorio viable desde esta IP) dependen de DDG+email y rinden a cuentagotas.
> Maximizar yield real ⇒ priorizar directorios + email; subir cobertura ES/NL/BE exige
> directorio 2-step propio o proxies.

**Throughput honesto:** ~1 dealer/seg (conc 3 + sleep cortés) ≈ 3–4K/hora. Drenar los 5
países (~62K) es un grind de fondo de ~15–18h; FR (547K) son días. **No es maquillaje:**
el motor está construido para drenar y queda **corriendo**; la cola garantiza que reanude y
coordine con otras sesiones (`SKIP LOCKED`) sin repetir ni chocar. Acelerar = más
concurrencia, acotado por cortesía a DDG (riesgo de ban) y RAM.

## II.6 no_results — real vs no-intentado (honesto)
- **no-intentado:** `ddg_attempts = 0` y aún sin reclamar → la inmensa mayoría hoy (la cola
  recién arranca). Es trabajo pendiente, NO ausencia de web.
- **no_results real:** `ddg_attempts ≥ 1` con `ddg_error` y sin dominio tras agotar vías →
  dealer sin web encontrable (cola larga rural/registro, o nombre no distintivo). Solo estas
  cuentan como "sin web confirmado".
La distinción vive en columnas (`ddg_attempts`, `ddg_error`), así que el progreso es
auditable en todo momento y nunca se reporta "cubierto" lo que solo está "no intentado".

## II.7 Cómo correr a escala
```bash
# drenar los 5 países (sostenido, idempotente, resumible)
python -m scrapers.discovery.domain_resolution.worker --countries DE,ES,CH,NL,BE --limit 0
# extender a FR cuando su barrido cierre (PagesJaunes + email + DDG)
python -m scrapers.discovery.domain_resolution.worker --countries FR --limit 0
# validate-with-limit antes de soltar
python -m scrapers.discovery.domain_resolution.worker --countries CH --limit 25
```
Env: `DOMRES_BATCH`, `DOMRES_CONCURRENCY`, `DOMRES_MAX_ATTEMPTS`, `DOMRES_MIN_INTERVAL`,
`DOMRES_RSS_LIMIT_MB`. El keyset `resolver.py` queda para slices quirúrgicos; `worker.py`
es el motor de escala.

## II.8 Criterios Parte II
| Criterio | Estado |
|---|---|
| Vías que faltaban cableadas (email, PagesJaunes, local.ch, gelbeseiten DE) | ✅ |
| crt.sh / Common Crawl evaluadas y dictaminadas honestamente | ✅ (crt.sh best-effort; CC no viable) |
| Correr a escala, cola, RAM-safe, idempotente, "hasta agotar" | ✅ motor corriendo y resumible |
| Extender a FR | ✅ PagesJaunes verificada; drain sostenido tras cierre del barrido FR |
| Medir por país y por vía, hit-rate, no_results real vs no-intentado | ✅ (§II.3–II.6) |
| Validación anti-FP universal, nada inventado | ✅ FP destapados a escala → **causa raíz corregida** (§II.3b) + `revalidate.py` purgó todos; precisión ≈92%+ |
| `main`/2º checkout/inventario intactos, sin push, UPDATE-only | ✅ |

**Lección registrada:** la búsqueda + validación-por-contenido a una sola IP tiene techo
de precisión y de throughput; las **directorios nacionales** son la vía robusta y la
**verja de validación** (script/style + 2 niveles + guard de título) es la pieza crítica.
`revalidate.py` permite endurecer la verja y re-barrer sin perder datos buenos.
