# BLUEPRINT DE ARQUITECTURA Y ORQUESTACIÓN — CARDEX
**Fecha:** 2026-06-08 · **Naturaleza:** DISEÑO (no implementación) · **Base de verdad:** `outputs/AUDIT_CONTEXT_2026-06-08.md` (auditoría viva A–D + D.7 hardware)
**Regla del documento:** cada decisión se justifica contra el ORO auditado y contra el hardware real medido. Cero relleno. No se duplica la auditoría: se referencia (§A.x / §B.x / §C / §D.x) y se construye encima.

> **Principio rector (del CEO):** territorio completo ES·FR·DE·BE·NL·CH — toda plataforma y todo dealer, incluido el taller perdido. Suelo de discovery = **2M entidades con web**. El sistema es **wiring, no rewrite** (veredicto §C de la auditoría): se reutiliza el oro y se cablea lo que está huérfano.

---

## RESUMEN EJECUTIVO (12 líneas)
1. **El objetivo no es construir un pipeline, es ACTIVAR y ESCALAR el que ya existe.** El esqueleto (vehicle_index 436K, seam A6/A7, delta SEEN/GONE, config-store, Camoufox bypass) es oro auditado; está idle o sin cablear, no ausente.
2. **Camino crítico real, en orden:** (P0) reactivar el seam dormido → (P1) cablear `seam_writer` para los gigantes T1 → (P2) probar los 49K dominios resueltos (hoy 100% `pending`) → (P3) delta always-on + remediación → (P4) API por entidad → (P5) discovery a 2M.
3. **Nueva taxonomía por DEFENSA reemplaza el `WAF` enum.** Hoy: 13 portales con defensa profunda, 43 sin defensa, 13 UNKNOWN; **49.032 dominios-dealer con defensa e inventario 100% desconocidos** (nunca probados).
4. **El cuello de botella no es discovery de identidad sino resolución name→web:** registros dan 715K identidades con ~0 web; OSM es la mayor fuente de web (31K). La palanca a 2M es escalar name→web, no cargar más registros.
5. **`sitemap_status` de los 49K resueltos = todos `pending`:** el puente domain→inventario nunca corrió. Probarlos es el hito de mayor ROI inmediato (convierte identidad en inventario sin nuevo discovery).
6. **T1 (defendidos) = bucle Camoufox→endpoint interno→Ollama→seam_writer→purga.** El oro (`facet_engine` cuenta, `seam_writer` escribe) existe; falta el worker que los una y persista. Es ~1 worker, no un motor nuevo.
7. **Hardware fija la ley física (§D.7):** 780 MB RAM libre, disco 94% lleno, 12 hilos. **Local = solo validar config por entidad + purgar; escala = VPS.** Ollama corre **secuencial**, nunca solapado con navegador+stack.
8. **Config por entidad ya es real** (portal+dealer versionado en git); el diseño la promueve a fuente única de verdad del “qué funcionó” con historial de drift.
9. **Delta always-on** se logra convirtiendo el coordinator batch en bucle por-entidad de alta frecuencia; el evento `volume_drift` ya se detecta — falta el call-site que dispare `remediate()` (hoy huérfano).
10. **API por entidad** es poblar `entities`+`dealer_inventory` (hoy 0/0), ligar `vehicles`→`entity_ulid`, y exponer `/dealers/{ulid}/inventory` + índice global.
11. **Orquestación:** 7 frentes paralelos con dependencias explícitas; Opus para decisiones irreversibles/threat-modeling por-defensa, Sonnet para implementación/concurrencia, Haiku para parsing determinista. “Hecho” = query verificable + suite verde + cero regresión.
12. **Cada hito del roadmap es un número, no una promesa:** p.ej. `count(*) FROM vehicle_index WHERE source_domain='mobile.de' > 0`, `count(*) FROM entities > 0`, `count(domain) FROM discovery_candidates ≥ 2.000.000`.

---

# §1 — PIPELINE OBJETIVO END-TO-END (oro existente vs construir/cablear)

```
                         ┌─────────────────────────────────────────────────────────────────┐
                         │  CARDEX TARGET PIPELINE   [GOLD]=reusar  [WIRE]=cablear  [BUILD]=nuevo │
                         └─────────────────────────────────────────────────────────────────┘

 (1) DISCOVERY                          (2) CLASIFICACIÓN POR DEFENSA           (3) EXTRACCIÓN POR TIER
 ┌───────────────────────┐             ┌──────────────────────────────┐        ┌──────────────────────────────┐
 │ OSM/Overpass    [GOLD]│             │ defense_classifier    [BUILD]│        │ T1 defended  Camoufox  [GOLD] │
 │ OEM locators    [GOLD]│   identity  │  probe: WAF(headers/cookies) │  tier  │   warm→svc/s endpoint→Ollama  │
 │ Registros merc. [GOLD]│────────────▶│  + sitemap(rinde inventario?)│───────▶│   →seam_writer→PURGA   [WIRE] │
 │ H3 geo-sweep   [BUILD]│  764K rows  │  reemplaza WAF enum    [BUILD]│        │ T2 inventory no-def    [GOLD] │
 │ CT logs/yellow  [GOLD]│             │  T1/T2/T3 por entidad        │        │   curl_cffi JSON-LD/sitemap   │
 └───────────┬───────────┘             └──────────────┬───────────────┘        │ T3 longtail (defer/sample)    │
             │                                        │                        └───────────────┬──────────────┘
             ▼                                        ▼                                        │
 ┌───────────────────────┐             ┌──────────────────────────────┐                        │
 │ name→web resolver[GOLD]│            │ config_registry por entidad   │                        │
 │  email→dir→DDG/Mojeek │             │  [GOLD store] + drift  [WIRE] │◀──── perfecciona ──────┤
 │  ESCALAR a 2M   [WIRE]│             │  versión/historial por entity │     config validada    │
 └───────────────────────┘             └──────────────────────────────┘                        │
                                                                                                ▼
 (4) SEAM L1→L2  [GOLD, idle→WIRE]      (5) DELTA ALWAYS-ON [GOLD batch→WIRE]   (6) API POR ENTIDAD  [BUILD]
 ┌───────────────────────┐             ┌──────────────────────────────┐        ┌──────────────────────────────┐
 │ indexer A5 → SEEN/GONE│             │ compute_delta SEEN/GONE [GOLD]│        │ entities + dealer_inventory   │
 │ vehicle_index   [GOLD]│────────────▶│ always-on por-entidad  [WIRE] │───────▶│  poblar (hoy 0)        [BUILD] │
 │ enrich_pending stream │             │ alert: punto exacto fallo[WIRE]│       │ GET /dealers/{ulid}/inventory │
 │ A6 enrich_worker[GOLD]│             │ trigger→remediate()    [WIRE] │        │ + índice global plataforma    │
 │ A7 rich_consumer[GOLD]│             │  (call-site huérfano hoy)     │        │ vehicles.entity_ulid FK [BUILD]│
 │ → vehicles      [GOLD]│             └──────────────────────────────┘        └──────────────────────────────┘
 └───────────────────────┘
                                       (7) SUBSTRATO DE CÓMPUTO
                                       ┌──────────────────────────────────────────────────────────┐
                                       │ LOCAL (16GB/780MB libre/disco 94%/12T): validar config    │
                                       │   por entidad → PURGAR listings → siguiente      [WIRE]   │
                                       │ VPS plug&play: extracción a escala + Ollama batch [BUILD] │
                                       └──────────────────────────────────────────────────────────┘
```

**Inventario oro-vs-construir (justificación contra auditoría):**

| Etapa | Activo | Estado auditado | Acción |
|---|---|---|---|
| Discovery identidad | OSM/OEM/registros/yellow | §B.4 ORO (8 fuentes reales) | **reusar**; añadir H3 geo-sweep [BUILD] |
| Discovery web | name→web resolver | §B.5 sólido pero techo 1-IP | **escalar** (multi-IP/VPS) [WIRE] |
| Clasificación | WAF enum + tier | §B.1 tier=proxy de defensa, sin capa por-entidad | **reemplazar** por `defense_classifier` por-entidad [BUILD] |
| Extracción T1 | Camoufox bypass + facet_engine | §C ORO probe / 💨 humo cosecha | **cablear** seam_writer [WIRE] |
| Extracción T2 | 19 portales + curl_cffi | §B.2 ORO (436K punteros) | **reusar** |
| Seam L1→L2 | A6+A7+indexer | §B.3 ORO pero **dormido** | **reactivar** [WIRE] |
| Delta | compute_delta SEEN/GONE | §B.3 ORO batch, idle | **always-on** [WIRE] |
| Remediación | remediate()+drift_gate | §B.8 drift live / remediate huérfano | **cablear call-site** [WIRE] |
| API entidad | entities/dealer_inventory | §B.7 GAP (0/0) | **construir** [BUILD] |
| Cómputo | purge-loop + Ollama | §D.7 hardware saturado | **local=validar, VPS=escala** [WIRE+BUILD] |

**Decisión arquitectónica clave:** no se reescribe el seam ni el motor de extracción. Todo lo nuevo es (a) `defense_classifier`, (b) workers que UNEN piezas oro existentes (seam_writer↔facet, remediate↔drift), (c) la capa API por entidad, (d) el runner VPS. Justificación: la auditoría probó que la cadena completa CORRIÓ E2E (533 coches reales en `vehicles`, §A.1/§Apéndice) — el código de transporte es sólido; el déficit es integración y activación, no diseño.

---

# §2 — REGISTRO DE CONFIG POR ENTIDAD (esquema, ubicación, versionado, drift)

**Base oro (§B.6):** ya existe store dual versionado en git — `configs/portals/*.json` (curado) + `configs/dealers/*.json` (auto-generado por detector), loader unificado `portal_config.load()` (portal gana sobre dealer). El blueprint lo eleva a **fuente única de verdad operativa por entidad**, con historial de qué funcionó y drift.

### 2.1 Dónde vive (decisión: git + espejo en PG)
- **Verdad declarativa = git** (`configs/{portals,dealers}/<source_key>.json`): reviewable, diff-able, rollback por `git revert`. Justificación: §B.6 ya lo hace; el versionado por commit es auditoría gratis.
- **Espejo operativo = PG `entity_config`** (nuevo, [BUILD]): para que el orquestador/VPS lean sin clonar el repo y para indexar por estado (drift, last_ok). El JSON de git es la fuente; un sync unidireccional git→PG al arranque del runner.

### 2.2 Esquema (extiende el `ExtractionConfig` existente, no lo reemplaza)
```jsonc
{
  "source_key": "dacia-meaux.fr",          // PK lógica (== entity natural key)
  "entity_ulid": "01J...",                  // [BUILD] FK a entities (hoy ausente)
  "kind": "dealer|portal",
  "country": "FR",
  "defense_tier": "T1|T2|T3",               // [BUILD] reemplaza inferencia por WAF
  "defense_signals": {"vendor":"datadome","level":"high","probed_at":"..."},
  "strategy": "playwright_meta|sitemap_listing|jsonld_detail|faceted_api|playwright_xhr",
  "version": 3,                             // [GOLD] ya se incrementa en remediación
  "endpoints": { "host":"", "listing_url_template":"", "detail_url_re":"", "api_url":"", "warm":[] },
  "drift_baseline": { "expected_min_volume":17, "required_fields":[...], "min_nonnull_ratio":0.6 },
  "history": [                              // [BUILD] historial por entidad
    {"version":1,"ts":"...","result":"ok","volume":17,"strategy":"sitemap_listing"},
    {"version":2,"ts":"...","result":"drift","volume":0,"reason":"selector_changed"},
    {"version":3,"ts":"...","result":"ok","volume":19,"strategy":"jsonld_detail","remediated_by":"auto"}
  ],
  "last_ok": {"ts":"...","volume":19,"vehicle_index_rows":19},
  "purged_at": "..."                        // [WIRE] sello de purga local (modelo VPS §D.7)
}
```
**Campos nuevos [BUILD] justificados:** `entity_ulid` cierra el gap §B.7 (config↔entidad↔inventario); `defense_tier`/`defense_signals` materializan la nueva taxonomía §3-auditoría; `history`+`last_ok` dan el “qué config funcionó” que pide la visión; `purged_at` integra el modelo de coste §D.7.

### 2.3 Versionado y drift
- **Escritura:** solo el detector (`build_config`) y `remediate()` escriben; `version = prev+1` (ya implementado §B.6/§B.8). Cada cambio = un commit (`feat(config): <source_key> v<n> <strategy>`), reviewable.
- **Drift:** `drift_gate.evaluate_volume(cfg, volume)` (ya live en coordinator, §B.8) compara contra `drift_baseline.expected_min_volume`. Al disparar, **escribe `history[] result:drift`** (hoy solo loguea) → ese append es el evento que §5 consume para remediar.
- **Garantía anti-FP:** se conserva el word-boundary anti-FP de P2 (§memoria p2-hardening) en la generación de config para no re-introducir Artcar→bmwartcarcollection.

---

# §3 — BUCLE T1 (Camoufox): warm → endpoint interno → parse (Ollama) → seam_writer → purga local

**Problema (§C):** el frente stealth crackea Akamai/DataDome gratis (oro) pero `facet_engine` solo cuenta y `seam_writer` nunca se invoca → 0 filas de gigantes. **Diseño = un worker que cierra ese circuito**, respetando el hardware (§D.7).

### 3.1 Topología del bucle (1 entidad defendida a la vez, local = validar)
```
 t1_harvest_worker(entity)                                   [BUILD ~80 líneas, une oro existente]
 ├─ 1. CONFIG   = entity_config.load(entity)                 [GOLD §B.6]  (defense_tier=T1, strategy=faceted_api/ssr_state)
 ├─ 2. WARM     = Camoufox warm _abck/_px → svc/s|SSR 200    [GOLD §C stealth/mobilede_probe.py]
 ├─ 3. ENUM     = facet_engine recursive (leaf_cap) → items  [GOLD §C facet_engine.py]  (NO solo count: forzar enum)
 ├─ 4. PARSE    = Ollama qwen2.5:3b SECUENCIAL → VehicleRecord[GOLD ollama-layer + §B.2 normalize]
 │                 (libera navegador ANTES de invocar LLM — §D.7: nunca solapar)
 ├─ 5. PERSIST  = seam_writer → vehicle_index + SEEN + XADD enrich_pending  [GOLD §C seam_writer.py, hoy sin call-site]
 ├─ 6. VALIDATE = ¿volume ≥ drift_baseline? → entity_config.history.append(ok/drift), bump version
 └─ 7. PURGE    = borrar dumps/HTML/caché Camoufox/perfil temporal  [WIRE §D.7]  → sello purged_at
```

### 3.2 Decisiones, justificadas
- **Forzar ENUM, no count:** el “100% coverage” auditado es Σ(counts) (§C 💨). El worker debe materializar URLs reales (el `records` dict que `facet_engine` ya construye en hojas ≤ leaf_cap) y pasarlas a `seam_writer`. Para hojas > cap, subdividir por facet (year/price/region) hasta caer bajo cap — el motor recursivo ya existe.
- **Ollama SECUENCIAL (§D.7):** con 780 MB libres, navegador (~Camoufox 300–600 MB) + Ollama (~1,7 GB) NO coexisten. Orden estricto: cerrar página/contexto → invocar Ollama → liberar. Modo `economy` (LLM solo en banda dudosa, ~3/20 — §memoria ollama) para minimizar invocaciones. En VPS, Ollama batch sin esta restricción.
- **Parse con Ollama solo donde el determinista falla:** JSON-LD/SSR estructurado → parser determinista (cero coste, §B.2 cascade). Ollama entra en SSR semi-estructurado/meta ambiguo. Justificación cost-aware: no se gasta inferencia donde el JSON ya da el campo.
- **Local = validar la config del gigante, no cosechar 1,5M:** mobile.de tiene 1,58M (§C). Cosechar eso en host satura disco (29,5 GB) en una pasada. Local valida que warm+enum+parse+seam funcionan para N=10–25 listings, **graba la config que funcionó**, purga, y delega la cosecha completa al VPS (§7-substrato).
- **Camoufox adaptado por caso (visión):** `defense_signals.vendor` rutea el warm: Akamai (`_abck`, svc/s in-page) vs DataDome (`_px`, comportamiento+capsolver) vs Cloudflare. Cada receta vive en la config de la entidad (§2) → se perfecciona por entidad y se reusa.

### 3.3 Cómo se guarda y perfecciona la config por entidad defendida
Tras un run OK: `entity_config` registra `strategy`, `warm[]`, `leaf_cap`, `defense_signals`, `last_ok.volume`, y `history[] result:ok`. El siguiente run carga esa config (warm exacto, axes de facet probados) → converge más rápido. Si Akamai cambia (warm falla → 403), drift dispara `remediate()` (§5) que re-detecta y bumpea versión. **La config ES el conocimiento acumulado del bypass por entidad.**

---

# §4 — DISCOVERY A 2M (OSM/Overpass + OEM locators + H3 geo-sweep + registros) + palanca name→web

**Realidad medida (no asumida):** censo actual 764.532 entidades / **49.032 con web (6,4%)**. Reparto vivo por país:

| País | Total | Con web | % web | Lectura |
|---|---:|---:|---:|---|
| FR | 570.479 | 5.442 | 1,0% | SIRENE/recherche infló identidad; **web casi sin resolver** (palanca name→web) |
| DE | 115.160 | 29.054 | 25,2% | mejor ratio (gelbeseiten+OSM); OffeneRegister 47K identidad sin web |
| NL | 37.655 | 6.980 | 18,5% | RDW+BOVAG sólidos |
| CH | 18.812 | 4.302 | 22,9% | AGVS/Zefix |
| ES | 17.135 | 1.934 | 11,3% | OpenMercantil flojo |
| BE | 5.291 | 1.320 | 24,9% | KBO identidad |
| **Σ** | **764.532** | **49.032** | **6,4%** | — |

**Fuentes por volumen (live):** sirene 360K (0 web), recherche_entreprises 175K (11 web), **osm 96,7K (31K web ← mayor fuente de web)**, offeneregister 47K (0 web), rdw 26,8K, gelbeseiten 19K (7,7K web), zefix 9,8K, bovag 4,3K (3,9K web), oem:* (audi 1,3K→1,3K web), agvs 2,8K (2,4K web).

### 4.1 Diagnóstico arquitectónico
- **Identidad NO es el cuello de botella; web SÍ.** Los registros (sirene/offeneregister/zefix/rdw) escalan a cientos de miles de identidades con ~0 web. Cargar más registros NO acerca a 2M-con-web.
- **La palanca a 2M-con-web es doble:** (a) **escalar name→web** sobre las 715K identidades sin web (hoy throttle 1-IP, §B.5); (b) **fuentes geo intensivas en web** (OSM ya prueba 31K; H3 geo-sweep lo multiplica).

### 4.2 Diseño de las 4 vías (estimación realista por país)
| Vía | Estado auditado | Diseño | Estimación con-web realista |
|---|---|---|---|
| **OSM/Overpass** [GOLD] | §B.4 real, 31K web | H3-tiled queries (celdas hex, no bounding-box país) para esquivar timeout 502 de Overpass; 13 tags motor-trade | DE/FR/ES densos: ~150–250K nodos con web/contacto a fondo |
| **OEM locators** [GOLD] | §B.4 real (audi 1,3K) | exhaustir 40+ marcas × 6 países (hoy ~11); cada locator da web de concesionario oficial | ~40–60K dealers oficiales con web |
| **H3 geo-sweep** [BUILD] | no existe | particionar territorio en celdas H3 res-7/8; por celda: OSM + reverse-geocode + crawl de directorios locales | multiplicador de OSM; cierra “taller perdido” rural |
| **Registros merc.** [GOLD] | §B.4 (sirene 360K) | mantener como fuente de IDENTIDAD (input de name→web), no de web | 0 web directa; alimentan la palanca |

### 4.3 Palanca name→web a escala (el verdadero camino a 2M)
- **Hoy (§B.5):** worker SKIP-LOCKED, multi-vía email→directorio→DDG/Mojeek, techo = throttle DDG 1-IP. 49K resueltos, todos validados.
- **Diseño de escala:** (a) **multi-IP** (rotación de proxies/VPS, no 1-IP) para romper el throttle DDG — es la restricción dura; (b) **directorios como vía primaria** (PagesJaunes/local.ch/gelbeseiten ya dan web sin search-engine throttle, §B.5); (c) correr en **VPS** (no host: §D.7 no soporta el volumen). Meta: convertir 715K identidades→web a ratio realista 40–60% = **300–450K nuevos con-web**, sumados a OSM/OEM/H3 → suelo 2M plausible solo si se incluye la cola larga europea fuera de los 6 países o se intensifica H3.
- **Honestidad (§B.4):** 2M-con-web en SOLO 6 países es agresivo; el censo de identidad lo soporta (>2M identidades posibles vía registros completos), pero la **conversión a web depende de romper el throttle y de H3 a fondo**. El hito se mide, no se asume (§8).

---

# §5 — DELTA ALWAYS-ON + ALERTA + AUTO-REMEDIACIÓN (call-site concreto)

**Base oro (§B.3/§B.8):** `compute_delta` SEEN/GONE real (467K eventos), `drift_gate.evaluate_volume` live en coordinator, `remediate()` completo pero **huérfano** (sin call-site). El diseño cierra el lazo.

### 5.1 De batch a always-on
- **Hoy:** coordinator hace un ciclo por portal y para; último evento >12h (§B.3 idle). “Segundos” no es real porque no corre en continuo.
- **Diseño:** **scheduler por-entidad con cadencia adaptativa.** Cada entidad tiene un intervalo (`portal_cadence` ya existe en BD, §memoria métricas) función de su volatilidad observada (un dealer con altas/bajas frecuentes → cadencia minutos; cola larga → horas/días). El coordinator pasa de “loop global” a “cola de due-entities” (`SELECT ... WHERE next_due <= now()`); al cosechar, `compute_delta` emite SEEN/GONE en streaming (ya lo hace) → **la latencia alta↔baja es la cadencia de esa entidad, no un batch nocturno.** Para entidades calientes, cadencia → segundos.

### 5.2 Alerta que señala el punto exacto de fallo (event contract)
Evento estructurado (reemplaza el `log.warning` de §B.8), emitido a un stream Redis `stream:operator_events` (ya existe como key, §B.3-redis):
```jsonc
{ "type":"volume_drift", "entity":"dacia-meaux.fr", "entity_ulid":"01J...",
  "stage":"extract",                      // punto EXACTO: discovery|resolve|classify|extract|seam
  "expected_min":17, "observed":0, "config_version":3,
  "signal":"warm_403|selector_empty|sitemap_404|parse_null_ratio",  // causa raíz inferida
  "ts":"..." }
```
**Decisión:** `stage` + `signal` localizan el fallo (warm de Akamai caído ≠ selector cambiado ≠ sitemap 404). Justificación: §B.8 hoy solo dice “DRIFT”; el operador/equipo de remediación necesita el punto exacto.

### 5.3 Call-site concreto que cablea el `remediate()` huérfano
**El consumidor del evento ES el call-site que falta (§B.8):**
```
 remediation_dispatcher  (consumer group sobre stream:operator_events)   [BUILD ~40 líneas]
 ├─ on volume_drift where stage in (extract, seam):
 │    result = await remediate(entity.domain, entity.country,            # [GOLD remediation.py, hoy solo tests]
 │                 static_fetcher, e07_fetcher, seam_runner, purger, save=True)
 │    if result.recovered: entity_config.history.append(ok, remediated_by=auto)   # bump version
 │    else: escalate(entity, "manual_review")   # → cola humana / equipo
 ├─ on volume_drift where stage in (resolve, classify):
 │    requeue para re-resolución / re-clasificación de defensa
 └─ anti-churn: cap MAX_REMEDIATIONS por entidad/ventana → DLQ (patrón A6 reclaim §memoria p1)
```
**Justificación contra el oro:** `remediate()` ya re-detecta, regenera config v+1, revalida por seam (§B.8) — solo le faltaba quién lo llame. Este dispatcher es ese quién. El anti-churn replica el cap MAX_DELIVERIES=5→DLQ ya probado en P2 (§memoria p2-hardening) para no entrar en livelock de remediación.

### 5.4 “Equipo de remediación”
Por ahora **automático** (dispatcher→remediate). Escalado a humano solo cuando `remediate` falla N veces (`escalate→manual_review` cola). **Alertas gestionadas por el orquestador internamente** (sin canal externo email/webhook aún — coherente con la nota del CEO y §B.8); el `stream:operator_events` + el panel `monitor_server` (§C stealth, oro) son el canal interno. Webhook/email = fase posterior, no bloqueante.

---

# §6 — ENCAPSULACIÓN API DEL INVENTARIO POR ENTIDAD (+ índice global)

**Gap auditado (§B.7):** `entities`=0, `dealer_inventory`=0, `vehicles` ligado por string `source_platform` (no FK). cardex-api expone market/arbitrage/alerts, **ningún `/dealers/{ulid}/inventory`**.

### 6.1 Modelo de datos (cerrar el gap)
```
 entities (poblar desde discovery_candidates con dominio)        [BUILD]
   entity_ulid PK · natural_key(source_key) · name · country · domain · defense_tier · registry_id
 vehicles  (ya rico, §storage)                                   [GOLD]
   + entity_ulid FK  ─────────────────┐   [BUILD: backfill desde source_platform→entity]
 dealer_inventory (vista materializada o tabla derivada)         [BUILD]
   = proyección vendible por entidad de vehicles WHERE entity_ulid = X AND listing_status='active'
```
**Decisión:** no duplicar inventario; `dealer_inventory` = proyección de `vehicles` por `entity_ulid` (vista materializada refrescada por el delta). Justificación: §coding-style inmutabilidad/DRY — `vehicles` sigue siendo el store rico único; la API por entidad es una vista, no una copia.

### 6.2 Diseño API (api-design: recursos, versión, paginación)
```
 GET /api/v1/dealers/{entity_ulid}/inventory      → inventario vendible por entidad (paginado, cursor)
 GET /api/v1/dealers/{entity_ulid}                 → ficha entidad (defense_tier, last_ok, volumen)
 GET /api/v1/inventory?country=DE&make=BMW&...     → índice GLOBAL de plataforma (oro vendible agregado)
 GET /api/v1/dealers/{entity_ulid}/delta?since=ts  → altas/bajas por entidad (alimenta clientes en segundos)
```
- **Versionado** `/api/v1/` (ya en cardex-api, §B.7). **Envelope** consistente (`{success,data,error,meta{total,cursor}}`, §patterns). **Paginación** cursor (no offset) sobre `vehicle_ulid`. **Per-entidad = unidad de venta**; índice global = el agregado.
- **Reusa** la defensa SSRF/header-injection ya auditada en `notify.go` (§B.8) para cualquier callback.

---

# §7 — PLAN DE ORQUESTACIÓN (frentes paralelos, modelo, gates, “hecho”)

### 7.1 Descomposición en frentes y grafo de dependencias
```
 F0 Reactivar seam (precondición)
   └─▶ F1 T1 harvest (Camoufox→Ollama→seam_writer)      [dep: F0]
   └─▶ F2 Delta always-on + remediation dispatcher       [dep: F0]
 F3 defense_classifier + probe de los 49K pending        [indep; alimenta F1/F4]
 F4 Discovery 2M (H3 + name→web multi-IP en VPS)         [dep: F6 substrato VPS]
 F5 API por entidad (entities/dealer_inventory/backfill) [dep: F0 datos vivos]
 F6 VPS plug&play runner + purge-loop                     [indep; habilita F1-escala/F4]
 F7 Ollama parsing layer (economy, secuencial)           [dep parcial: integra en F1]
```
Paralelizables sin solapar ficheros: **F3, F6, F7** desde el día 0 (worktrees aislados, patrón §memoria). F1/F2/F5 tras F0. F4 tras F6.

### 7.2 Asignación de modelo (CLAUDE.md routing) — justificada
| Frente | Modelo | Por qué |
|---|---|---|
| F0 reactivar seam | **Sonnet** | wiring/ops sobre código oro; concurrencia streams |
| F1 T1 harvest | **Sonnet** impl + **Opus** threat-model | Opus diseña bypass Akamai/DataDome adaptado por caso (irreversible si bania la IP); Sonnet implementa el worker |
| F2 delta always-on + remediation | **Opus** diseño + **Sonnet** impl | event contract + topología always-on = decisión de arquitectura; impl del dispatcher = Sonnet |
| F3 defense_classifier | **Sonnet** | clasificación sobre headers/cookies; **Haiku** para el probe masivo determinista de los 49K |
| F4 discovery 2M | **Sonnet** impl + **Opus** palanca name→web | romper throttle 1-IP a escala = decisión estructural |
| F5 API por entidad | **Sonnet** (api-design) + **Haiku** backfill | dedup/normalización entidad = Haiku determinista; API = Sonnet |
| F6 VPS plug&play | **Opus** infra + **Sonnet** impl | deployment/purge irreversible (borra listings) → Opus fija invariantes |
| F7 Ollama layer | **Sonnet** + **Haiku** | routing economy ya existe; Haiku para parsing determinista |

### 7.3 Gate antes de cada merge (no negociable)
1. `GOWORK=off go test ./...` verde en módulos Go tocados; `pytest` verde en scrapers (suite ≥ actual, §memoria 1568).
2. **Query de aceptación del frente devuelve el número objetivo** (§8) — no “debería”.
3. Cero regresión: el barrido de §A/§B sigue dando los mismos invariantes (436K no baja, 19 fuentes no desaparecen).
4. JA3 coherente + stack aprobado si tocó superficie de scraping (`security-review`, §cardex-pipeline).
5. Worktree aislado, `main` intacto, NO push sin autorización (§memoria: origin/main solo avanza por orden explícita de Elias).
6. Revisión adversarial (Opus) del diff antes de declarar el frente.

### 7.4 Definición de “HECHO” (puerta de finalización, CLAUDE.md)
Un frente está hecho cuando: (a) su query de hito devuelve el número objetivo verificado en vivo; (b) suite verde sin regresión; (c) config-driven (sin selectores hardcoded por entidad fuera del registro §2); (d) en modelo de coste — local valida+purga, escala documentada a VPS; (e) cero placeholder/TODO; (f) reportado por archivo con evidencia. “Funciona” sin query que lo pruebe = no hecho.

---

# §8 — ROADMAP POR FASES (cada hito = query/número verificable)

| Fase | Objetivo | Frentes | HITO MEDIBLE (query → número) |
|---|---|---|---|
| **P0** | Reactivar seam dormido | F0 | `redis XLEN stream:enrich_pending > 0` durante run **Y** `SELECT max(ts) FROM vehicle_events > now()-interval '60s'` durante un ciclo |
| **P1** | Primer gigante T1 persiste | F1+F7 | `SELECT count(*) FROM vehicle_index WHERE source_domain='mobile.de' > 0` (meta inicial ≥ 1.000; luego ≥ 50.000) ; cada gigante ≥ 1 fila |
| **P2** | Probar los 49K resueltos | F3 | `SELECT count(*) FROM discovery_candidates WHERE sitemap_status='found' > 0` (hoy **0**; meta ≥ 10.000) — convierte identidad en inventario sin nuevo discovery |
| **P3** | Inventario dealer a escala | F1+F5 | `SELECT count(DISTINCT source_platform) FROM vehicles > 500` ; `SELECT count(*) FROM vehicles WHERE source_platform NOT LIKE 'SEED%' > 50.000` |
| **P4** | Delta always-on + remediación | F2 | `SELECT count(*) FROM vehicle_events WHERE event_type='GONE' AND ts > now()-interval '5 min' > 0` ; nº de `volume_drift`→`remediate(recovered=true)` en log del dispatcher > 0 |
| **P5** | API por entidad | F5 | `SELECT count(*) FROM entities > 0` **Y** `SELECT count(*) FROM dealer_inventory > 0` **Y** `GET /api/v1/dealers/{ulid}/inventory` 200 con N filas |
| **P6** | VPS plug&play + purga | F6 | runner VPS cosecha 1 gigante completo (`vehicle_index WHERE source_domain='mobile.de' > 500.000`) **mientras** disco host libre se mantiene > 12 GB (§D.7) |
| **P7** | Discovery hacia 2M | F4 | escalonado: `count(domain) FROM discovery_candidates ≥` 100K → 500K → 1M → **2.000.000** ; `sitemap_status='found' ≥ 500.000` |
| **P8** | Re-clasificación universo por defensa | F3 | `SELECT defense_tier, count(*) FROM entity_config GROUP BY 1` cubre 100% de entidades con-web (hoy: 13 portales clasificados, 49K dealers UNKNOWN → meta UNKNOWN = 0) |

**Reparto actual bajo la nueva taxonomía (punto de partida medido, con incertidumbre):**
| Defense-tier | Hoy | Incertidumbre |
|---|---|---|
| **T1 (defensa profunda)** | 13 portales (4 Akamai+4 DataDome+3 CF-Pro+1 CF-Bus+1 PerimeterX) | + 13 portales UNKNOWN + **49K dealers sin probar (100% incertidumbre)** |
| **T2 (inventario, sin defensa profunda)** | 19 portales cosechando + 43 portales NONE/CF-Free | subconjunto de 49K que resulte rendir inventario (medir en P2) |
| **T3 (sin defensa, sin inventario relevante)** | ~715K identidades sin web | se reduce a medida que name→web (P7) las convierte |

El hito P8 es el que da sentido a la taxonomía: hoy **el 100% de las 49.032 entidades-dealer con web tienen defensa e inventario desconocidos** (todas `pending`). Probarlas (P2) + clasificarlas (P8) es prerequisito para dimensionar T1 real.

---

## Trazabilidad oro→diseño (cierre)
Cada sección se ancla a un activo auditado: §1 reusa esqueleto+seam (§B.2/B.3 ORO); §2 eleva el config-store (§B.6 ORO); §3 cierra el circuito facet→seam_writer (§C oro-sin-cablear); §4 reconoce que la palanca es name→web (§B.5) no más registros (§B.4); §5 cablea el `remediate()` huérfano (§B.8); §6 cierra el gap entities/dealer_inventory (§B.7); §7–8 respetan el hardware real (§D.7: local valida+purga, VPS escala, Ollama secuencial). **Ninguna decisión inventa un motor nuevo donde la auditoría encontró oro.**

**Árbol intacto:** `feature/domain-resolution @ 2bd5cb5`, sin cambios rastreados; único añadido `outputs/` (untracked, sin commit).
