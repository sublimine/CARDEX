# GUARDIAN — Verificación de gobernanza Tier-1 (conteo independiente)

**Auditor:** GUARDIAN · **Fecha:** 2026-06-07 · **Modo:** SOLO LECTURA, conteo propio
**Sujeto:** afirmaciones del supervisor (rama `feature/stealth-camoufox` @ `6a0b632`): mobile.de 100% (1.586.022), leboncoin 100% (~900K), coches.net 95,4% (238.411/249.963).
**Método:** recompute propio sobre la evidencia del supervisor (`stealth/evidence/*.json`) + conteo del store auditado (`vehicle_index`) + work_queue + configs/portals/.

> **Regla del encargo:** no marcar verde lo que no reconcile. Distingo explícitamente
> **reconciliación de CONTEO** (enumeración: ¿la Σ por faceta = total anunciado?) de
> **COBERTURA REAL** (¿inventario recuperado y persistido en el store auditado?).

---

## 0. Veredicto global

El trabajo anti-bot del supervisor es **real y notable** (Camoufox vence Akamai/DataDome; ejes de faceteo descubiertos; conteo de mobile.de reconciliado a la cifra viva). Pero "100% cobertura" **sobre-declara**: es **reconciliación de conteo / viabilidad de enumeración**, NO inventario cosechado.

**Hecho que gobierna todo [V, mi conteo]:** `vehicle_index` (store auditado) tiene **0 filas** de mobile.de, leboncoin y coches.net. work_queue: los tres en `pending`. **Ninguna** config en `configs/portals/` (solo siguen las 3 previas: autolina/autotrack/viabovag). `seam_writer.py` está **cableado de verdad** (INSERT `vehicle_index` ON CONFLICT + XADD `stream:enrich_pending` + DELETE/GONE) pero **no ha fluido al store** (0 filas). El propio tablero del supervisor lo marca «pendiente de verificación», no verde — coherente.

| Portal | Conteo reconcilia | Cobertura real (cosechada) | Veredicto ≥99% cosechado |
|---|---|---|---|
| mobile.de | ✅ 100,00% (Σ178 marcas = root) | ❌ 0 filas; 20 URLs volcadas | **NO** |
| leboncoin.fr | ⚠️ estimación, no Σ contada | ❌ 0 filas; 60 URLs muestra | **NO** |
| coches.net | 🟡 95,38% (worker vivo, 98/121 marcas) | ❌ 0 filas | **NO** |

---

## 1. mobile.de — conteo 100% ✅ / cobertura ❌
**Mi reconciliación [V]** (`stealth/evidence/facet/mobilede_coverage.json`):
- `root` (numResultsTotal sin filtros, `vc=Car`) = **1.586.022**.
- **MI Σ de 178 marcas** (recomputada, no la del fichero) = **1.586.026** → **100,00%** (delta +4 = 0,0003%, solapamiento trivial de facetas). Top: VW 258.494, Mercedes 171.880, BMW 135.825, Audi 130.367.
- → **La enumeración por marca SÍ reconcilia al total**: ningún segmento-marca falta. Reconciliación de conteo **verificada al 100%**.

**Pero NO es cobertura cosechada [V]:**
1. **`mobilede_enum_snapshot.json` = 20 URLs volcadas** (no 1,586M). El "dump" real es una muestra.
2. **`vehicle_index` = 0 filas** de mobile.de. Nada persistido en el store auditado.
3. **Recuperabilidad bajo el cap de paginación NO probada para marcas grandes.** El `deepdive` del propio fichero: Volkswagen `make_count=258.494` vs `sum_over_years=239.016` → el sub-faceteo por **año** solo recupera **92,5%** de VW; falta 19.478 (7,5%). Las marcas que exceden el CAP (VW/Mercedes/BMW/Audi/Ford/Opel, todas >95K) requieren sub-faceteo recursivo más profundo (año×km×…) que **no está probado que cierre al 100%**. RESULTS.md lo admite ("Top marcas >CAP, requieren subdivisión").
4. `root=1.586.022` es **sourced por el supervisor**; no puedo re-fetchearlo (Akamai bloquea esta IP) — verifico la reconciliación INTERNA (Σ=root), no la cifra viva en origen.

**Config en configs/portals/:** ❌ no. Hay `scrapers/mobile_re/` (client/interceptor/mapper) + `seam_writer.py`, no una config versionada.
**Veredicto:** conteo reconciliado 100% (mío) ✅; **cobertura cosechada ≥99% = NO** (0 filas, 20 URLs, recuperación de marcas-grandes sin probar).

## 2. leboncoin.fr — estimación, no reconciliación ⚠️/❌
**Mi inspección [V]** (`stealth/evidence/sitemap_recon.json` + `dumps/leboncoin_snapshot.json`):
- "~900.000" = `listing_url_estimate=900000` = **18 listing-sitemaps × ~50.000** extrapolado de **una** hoja muestreada (`auto-voitures-adview-1.xml`, `sample_url_count=50000`). **No es una Σ de hojas contadas** — es una extrapolación 18×50K.
- `leboncoin_snapshot.json` = **60 URLs** realmente volcadas. `vehicle_index` = 0.
**Config:** ❌. **Veredicto:** **NO verificado** — total es estimación de sitemap (no Σ contada), 60 de muestra, 0 cosechado. No ≥99% reconciliado ni cosechado.

## 3. coches.net — 95,38% confirmado, EN CURSO 🟡/❌
**Mi verificación [V]** (`stealth/evidence/tier1_progress.json`):
- `{total_oficial: 249963, cobertura: 238411, pct: 95.38, makes_done: 98, estado: "midiendo cobertura (worker vivo)"}`. **Confirmo 238.411/249.963 = 95,38%** (aritmética verificada).
- **Qué falta:** `coches_brands.json` = **121 marcas**; `makes_done=98` → **23 marcas aún sin medir** (el worker sigue VIVO). El gap 11.552 (4,62%) = esas 23 marcas pendientes + posibles listings con marca fuera de la refdata de 121. **No es un techo estructural** sino trabajo en curso.
- `vehicle_index` = 0; **config** ❌; coches.net en work_queue `pending`.
**Veredicto:** 95,38% **confirmado como progreso de enumeración en curso**; **NO 100%, NO ≥99%, NO cosechado**.

---

## 4. Brechas de gobernanza (comunes a los 3)
1. **Cobertura cosechada = 0** en el store auditado (`vehicle_index`): la enumeración no ha fluido. El delta SEEN/GONE existe como JSON (`*_delta.json`: current/prev/seen_new/gone) y `seam_writer.py` puede empujarlo (INSERT+XADD reales), pero **no se ha ejecutado contra el store auditado** (o fue demo). 
2. **Config no versionada:** ninguna `configs/portals/{mobile.de,leboncoin.fr,coches.net}.json`. El patrón de resiliencia (config-driven + drift baseline) NO se aplica a estos tier-1; viven en scripts ad-hoc (`stealth/*.py`, `scrapers/mobile_re/`).
3. **Dependencia de proxy/anti-bot no resuelta a escala:** el cracking es por Camoufox 1-IP; cosechar 1,586M (mobile.de) exige flota de proxies + almacenamiento (P3) — sigue siendo el techo conocido.

## 5. Recomendación
- **mobile.de:** aceptar como **enumeración de conteo reconciliada (100%)**, NO como cobertura. Antes de marcar verde: (a) probar que el sub-faceteo recursivo cierra las marcas >CAP (VW year×km…) al ≥99%; (b) fluir el delta por `seam_writer` al `vehicle_index` y reconciliar filas reales; (c) guardar `configs/portals/mobile.de.json` con su baseline. 
- **leboncoin:** sustituir la estimación 18×50K por una **Σ real de las 18 hojas** (contar cada sitemap), luego volcar+fluir.
- **coches.net:** dejar terminar el worker (23 marcas), reconciliar al cierre, y decidir el destino del 4,62% (marcas fuera de refdata). 
- **Transversal:** versionar las 3 configs + ejecutar `seam_writer` contra el store auditado para que GUARDIAN pueda contar filas reales, no JSON de evidencia.

**Nada marcado verde.** Reconciliación de CONTEO verificada solo para mobile.de (100,00%, mi suma); las tres tienen **cobertura cosechada = 0** y configs sin versionar. El supervisor ya las tenía como «pendiente de verificación» — confirmo que así deben seguir hasta que el inventario fluya al store y se cuente.

---

*GUARDIAN — conteo propio: Σ178 marcas mobile.de=1.586.026 (=root, 100,00%); leboncoin=estimación 18×50K + 60 muestra; coches.net=238.411/249.963 (95,38%, 98/121 marcas, worker vivo). vehicle_index de los 3 = 0. Sin tocar datos. Fin.*
