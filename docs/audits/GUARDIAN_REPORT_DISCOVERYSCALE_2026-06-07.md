# GUARDIAN — Auditoría "barrido de discovery a escala" (barrido A)

**Auditor:** GUARDIAN · **Conducida:** 2026-06-07 · **Modo:** SOLO LECTURA (barrido A YA cerró → SELECT seguro de `discovery_candidates`, sin escribir; P2-hardening en código aislado, no la toco; sin docker)
**Rama auditada:** `feature/discovery-scale` @ `a2fa819` · **main** @ `6219527` · **merge-base** `6e0be32`
**Relación:** diverge **12/5** (NO FF) · **3-way con main LIMPIO** (merge-tree exit 0, 0 conflictos)
**Fuente:** `DISCOVERY_SCALE_REPORT.md`
**Método:** conteos reales + muestras (SELECT read-only), código de conectores vía `git show` (sin checkout — sesiones activas), suite en worktree detached aislado, 1 subagente read-only, merge-tree. Cada "hecho" atacado.

> `[V]` = VERIFICADO (comando citado). Foco: que los +17.294 con-web sean reales (no inventados) + invariantes INSERT-only.

---

## 0. Resumen ejecutivo — ¿lista para consolidar?

**Sí, vía merge 3-way (limpio).** El barrido cableó **8 conectores reales** que elevaron los dealers-con-web de ~28.570 a **45.887** (**+17.317**, confirma el +17.294), con **dominios reales** (no placeholders), **dedup correcto** (0 dominios duplicados), **INSERT-only + heartbeat condicional** (sin migración de esquema, RAM-safe), **suite 1347 verde** y **backlog honesto**. **Recomendación: MERGE 3-way a `main`.** No lo ejecuto.

**Caveat P2 (NO bloquea):** `gelbeseiten` (la mayor fuente nueva, 7.723 con-web) tiene una **cola de FP baja** (~0,4% nombres obvios no-dealer — ópticos/audio; 1% microsites go1a.de; + algún mismatch nombre↔dominio); `bovag`/`agvs`/`oem` son limpios (asociaciones de dealers). Y `osm_expanded_run` tiene **tests débiles** (solo parsing de env).

| Ítem | Veredicto |
|---|---|
| 1 · +17.294 con-web reales | 🟢 REALES (cola FP menor en gelbeseiten) |
| 2 · Dedup cross-source | 🟢 SOUND (0 dup) |
| 3 · 8 conectores reales + tests | 🟢 8/8 reales, 73 tests |
| 4 · Invariantes (INSERT/heartbeat, no migración, RAM-safe) | 🟢 SOUND |
| 5 · Backlog honesto | 🟢 8/8 bien razonados |
| 6 · Higiene + regresión | 🟢 1347 verde, sin tmp_ |

---

## 1. Los +17.294 con-web son REALES — 🟢 [V]
**Conteo vivo con-web por país (vs claim):** DE **26.676** (claim 26.653, +23), NL **6.898** ✓, FR **5.293** ✓, CH **4.026** ✓, ES **1.747** ✓, BE **1.247** ✓ → **total 45.887** (claim 45.864; +23 tras snapshot, inmaterial). **+17.317 sobre baseline 28.570.**

**Vienen de los conectores nuevos [V]** (with_web por source): `gelbeseiten` 7.723, `bovag` 3.933, `agvs` 2.401, `oem:renault/seat/dacia/vw/hyundai` ~1.654, + `osm` re-fetch (28.124→28.354). Los registros (`recherche_entreprises` 175K, `zefix` 9.8K, `sirene` 360K) expanden el **censo** con domain NULL (necesitan el resolver, ya mergeado) — no inflan with_web.

**Dominios reales, no placeholders [V]** (muestras): **bovag** limpio (Autobedrijf van Gorkum→advg.nl, Auto Huiskes→autohuiskes.nl, Van der Vaart→vandervaartautos.nl); **agvs** limpio (Garage Mösch→garage-moesch.ch, Auto Inderbitzin→auto-inderbitzin.ch); **oem:renault** limpio (Autohaus Fischer→renault-fischer-oberau.de). **Cola FP en gelbeseiten** cuantificada: **28/7.723 (0,4%)** nombres obvios no-dealer (AP Optik→ap-optik.de óptico, Audiovalve→audiovalve.info audio), 75 (1%) microsites `go1a.de`, + algún mismatch (Warresz→optelco.de). **bovag=0, agvs=2/2.401** no-auto → asociaciones de dealers, limpias. **Plan P2:** pasar gelbeseiten por el gate de validación del resolver (validate.py) para podar la cola.

## 2. Dedup cross-source — 🟢 SOUND [V]
**0 dominios `(domain, country)` duplicados** en toda la tabla → los OEM-con-web colapsan contra OSM por el índice único parcial `ux_disc_cand_domain_country`; **sin doble-conteo**. El with_web es neto.

## 3. 8 conectores reales + tests — 🟢 [V, subagente]
Los 8 golpean **endpoints HTTP reales** y parsean name/domain/city de la respuesta viva; **ninguno fabrica filas** (los únicos literales son hosts de portal OEM como endpoint; literales de dealer solo en fixtures de test):

| Conector | Endpoint real | Verdict |
|---|---|---|
| `fr_recherche_entreprises` | `recherche-entreprises.api.gouv.fr/search` × **101 deptos** (NAF 45.11Z/45.19Z) | REAL |
| `ch_zefix_allcantons` | `data-bs.ch/.../all_cantons/companies_{kt}.csv` × **26 cantones** | REAL |
| `ch_agvs` | `agvs-upsa.ch/.../mitgliederverzeichnis` (assoc. CH) | REAL |
| `nl_bovag` | `bovag.nl/sitemap.xml` → `/leden/<slug>` `__NEXT_DATA__` | REAL |
| `de_gelbeseiten` | HTML `/suche/autohandel` + AJAX `/ajaxsuche` (base64 webseiteLink) | REAL |
| `oem_locators` | VW/Audi SDS, Škoda/Toyota/Hyundai/Kia APIs reales | REAL |
| `oem_wave2` | Renault/Dacia `commerce/v2/dealers/locator`, SEAT XML + D'Ieteren BE | REAL |
| `osm_expanded_run` | Overpass con tag-set expandido (13 cláusulas) | REAL |

**73 tests** (= "+73" del claim); aserciones reales (transform-purity + extracción de dominio), **excepto `osm_expanded_run` (6 tests = solo parsing de env)** — el insert-path del conector no se testea aquí (el transform vive en `osm.py`). **Plan P2:** test del insert-path de osm_expanded_run.

## 4. Invariantes — 🟢 SOUND [V]
- **INSERT-only + heartbeat condicional:** `ON CONFLICT (domain,country)/(source,registry_id,country) DO UPDATE SET last_seen=NOW() WHERE last_seen < NOW()-INTERVAL '1 hour'` (o `DO NOTHING` en osm) → **el único UPDATE toca solo `last_seen`** (heartbeat by-design, autolimitado para no churnar dead-tuples), **nunca columnas de datos, nunca DELETE**. Índices únicos parciales reales en `init-pg.sql`.
- **Sin migración de esquema [V]:** `git diff 6e0be32 a2fa819` no contiene `CREATE/ALTER/DROP TABLE` (solo un comentario "No schema migrations"); 0 archivos `.sql` tocados.
- **RAM-safe [V]:** zefix CSV **streaming a temp file** + `csv.DictReader` fila-a-fila (CSV de 40MB no OOMea); bovag `Semaphore(8)`+throttle; oem/gelbeseiten página-a-página throttled; pools `max_size 4-6`; **sin fetchall** de sets grandes.

## 5. Backlog honesto — 🟢 8/8 bien razonados [V, subagente]
Cada ítem diferido nombra un **bloqueador técnico concreto**, no pereza:
- **11880.com (DE):** funciona (52.721) pero web solo en detalle → ~52K GETs sobre Cloudflare 1-IP + **solapa con GelbeSeiten/OSM ya cargados** → VPS. (coste/IP + retornos decrecientes).
- **PagesJaunes (FR):** web en listado solo ~12%; FR-con-web ya cubierto por OSM → VPS.
- **BE/ES:** **Incapsula/Imperva (challenge JS)** desde IP residencial → necesita browser/proxy (coincide con memoria).
- **PSA (Peugeot/Citroën/Opel):** backend `wsrest.servicesgp.mpsa.com` **DNS retirado (502)** — host muerto nombrado.
- **Mercedes/Ford:** Akamai WAF + key de pago. **Fiat:** `dealerlocator.fiat.com` NPE Java en prod.
- **H3 / Overpass por nombre:** "descartado **con datos**": la query por área ya captura todo el OSM tagged; por nombre aporta solo ~80-120 con-web a 18% señal/ruido → **redundancia + bajo yield cuantificado**, no abandono.

## 6. Higiene + regresión — 🟢 [V]
- **Suite 1347 passed, 0 failed** (1274 base + 73). Cero regresiones.
- **Sin `tmp_*` tracked** en `a2fa819` (`git ls-tree` limpio); diff = solo sources + tests + 2 `.md` (+3212/−6). El worktree del barrido fue limpiado por su sesión.
- Auditado en worktree detached propio (eliminado); `discovery_candidates` **solo SELECT**.

---

## 7. Recomendación de consolidación — **GO (merge 3-way limpio)**

**Mergear `feature/discovery-scale` → `main` por merge 3-way.** No lo ejecuto.
- ✅ `[V]` NO es FF (diverge 12/5) pero **3-way LIMPIO** (`merge-tree` exit 0, 0 conflictos). El único archivo compartido (`fr_recherche_entreprises.py`, creado por fanout) lo modificó **solo discovery-scale**; main no lo tocó desde el merge-base → funde sin conflicto. Los demás 7 conectores son archivos nuevos, disjuntos de los módulos ya mergeados (dealer/e07/domain-res).
- ✅ Aditivo, **INSERT-only + heartbeat** (sin migración, sin tocar inventario ni esquema), 8/8 conectores reales, dedup correcto, **1347 verde**, backlog honesto.
- ✅ Sin riesgo de datos para el merge (es código; los conectores en runtime solo INSERT/heartbeat-`last_seen`).

**Caveats P2 (NO bloquean):** (1) podar la cola FP de `gelbeseiten` (~0,4% no-dealer + mismatches) pasándola por el gate `validate.py` del resolver; (2) test del insert-path de `osm_expanded_run` (hoy solo 6 tests de env); (3) operativo: los registros (recherche_entreprises 175K, zefix, sirene) añaden censo masivo domain-NULL → drenar con el `worker.py` del resolver (ya en main) para convertirlos en con-web.

**Nota de techo:** el censo creció a ~685K filas (FR 568K vía recherche_entreprises full 175K + sirene; DE 70K; CH 17K) — el "techo libre" era más alto de lo estimado (~460K) gracias a los full-sweeps de registro. El cuello sigue siendo **resolver dominios** de ese censo (domain-NULL) y los **gigantes anti-bot** (P3 proxies).

**Mecánica:** main no checked out → mergear en **worktree temporal sobre main** (`git merge feature/discovery-scale`); suite post-merge esperada **~1427** (1354 main + 73). **Última rama tras esta:** `feature/p2-hardening` (`6219527`, en código aislado) → su merge será 3-way (parte de un main previo a discovery-scale).

---

*GUARDIAN — autointerrogatorio: ¿toqué lo prohibido? No — `discovery_candidates` solo SELECT (barrido cerrado), sin docker, sin perturbar worktrees activos (worktree detached propio, eliminado). ¿Verifiqué ejecutando? Sí — conteos con_web por país/source, muestras reales, dedup=0, no-migración en diff, INSERT/heartbeat en SQL, suite 1347, merge-tree. ¿Refuté cada hecho? Sí — +17.294 (reales, cola FP gelbeseiten 0,4% hallada y cuantificada tras corregir mi sobre-reacción de muestra-8), dedup (0), 8/8 reales, invariantes (heartbeat solo last_seen), backlog (8/8 con bloqueador nombrado). Nada cayó como defecto bloqueante. Fin.*
