# CAPA LLM LOCAL (Ollama) — capa de decisión difusa del pipeline

**Fecha:** 2026-06-07 · **Rama:** `feature/ollama-decision-layer` (worktree aislado desde `main 1ca158a`) · NO push
**Objetivo:** micro-decisiones difusas del pipeline con un LLM **local y gratis**, de modo que el régimen sostenido **no consuma tokens de Claude**. Heurísticas deterministas primero; Ollama solo en la banda dudosa.

> Cada cifra es `[V]` = VERIFICADA (salida de comando). Nada concluido sin evidencia. Lo poblado para evaluar se midió en vivo.

---

## 0. Resumen ejecutivo

**Montado, integrado, probado y MEDIDO en vivo.** Sobre una muestra real de 20 dominios (incluyendo los FP que mencionaste: taller de motos, neumáticos, chapa/pintura), la capa LLM en modo **economy** sube la **precisión 0,750 → 0,900** y la **accuracy 0,800 → 0,900** con **cero pérdida de recall (0,900)**, usando solo **3 llamadas LLM locales de 20** (el resto lo resuelve la heurística, gratis). Coste en Claude: **cero** (todo local).

| Sistema (muestra real, 20 dominios) | Precisión | Recall | Accuracy | Llamadas LLM |
|---|---|---|---|---|
| Heurística sola (P2-endurecida) | 0,750 | 0,900 | 0,800 | 0 |
| **+ Ollama economy (default)** | **0,900** | **0,900** | **0,900** | **3 / 20** |
| + Ollama precision (experimental) | 1,000 | 0,600 ⚠️ | 0,800 | 10 / 20 |

**economy arregló exactamente los FP del tipo objetivo:** `manu-motos.ch` (taller de motos → no-coche ✓) y `carrosserie-palmieri.ch` (chapa/pintura → no-coche ✓), **sin tumbar ningún dealer real**.

---

## 1. Stack montado [V]
- **Ollama 0.30.6** instalado (winget), servidor **persistente** en `127.0.0.1:11434` (proceso de fondo gestionado por el instalador; PID 30456 escuchando, verificado `{"version":"0.30.6"}`).
- **Modelo:** `qwen2.5:3b` (1,8 GB, Q4) — elegido por la RAM (host de 15,3 GB con ~2,4 GB libres bajo el stack Docker; 7b no cabía). Carga bajo demanda, descarga tras `keep_alive`.
- **RAM medida [V]:** baseline 2,38 GB libres → **0,64 GB con el modelo cargado** (~1,74 GB residentes) → **recupera a 4,24 GB tras descargar** (`keep_alive=120s`). La presión es **transitoria**: entre ráfagas el host recupera su RAM. Como la capa es fallback (bajo volumen), los picos son intermitentes.
- **Latencia medida [V]:** carga en frío ~25 s; clasificación **warm ~8–12 s** (3b en CPU, sin GPU). En la eval: economy avg 25,7 s (incluye una llamada fría), precision avg 18,0 s.

## 2. Arquitectura (`scrapers/llm/`)
- **`ollama_client.py`** — cliente fino **sin dependencias nuevas** (stdlib `urllib`). `format=json`/JSON-schema, `temperature=0` (idempotente), `num_ctx=2048`, semáforo proceso-wide (1 generación a la vez → nunca dos contextos cargados, techo de RAM), health cacheado. **Fail-open:** cualquier fallo (server caído/timeout/JSON roto) → `None` → el llamante usa su heurística. El pipeline nunca se bloquea ni cae por el LLM.
- **`decisions.py`** — tres decisiones difusas, **heurística-primero**:
  1. `classify_is_car_dealer` — refina el gate anti-FP (`validate.confirms_dealer`). La heurística decide los casos claros (coste cero); el LLM arbitra **solo la banda ambigua**.
  2. `extract_vehicle_fields` — rellena make/model/precio/año que el parser estructurado dejó vacíos (solo si faltan).
  3. `disambiguate_domain` — elige entre candidatos de dominio **solo en empate** (top-2 dentro de un margen).
- **Política `LLM_DECISION_MODE`** (env, override por llamada): `economy` (default — solo banda dudosa), `precision` (verifica todo positivo — experimental, ver §4), `off`.
- **Guard de consistencia:** si el LLM dice `is_car_dealer=False` pero el `kind` es "dealership/concesionario" (auto-contradicción del modelo pequeño) → se ignora y manda la heurística.

## 3. Banda dudosa (cuándo entra el LLM, modo economy)
- **Positivo heurístico** apoyado solo en evidencia débil: city-only, weak-only, o palabra fuerte de chapa/parts (`carrosserie`/`carrozzeria`) → FP-prone → LLM.
- **Negativo heurístico** por tecnicismo de nombre/ciudad **en una página automotriz** (`name_not_on_page`/`no_name_or_city`) → FN-prone → LLM puede rescatar un dealer real.
- **Nunca** se llama al LLM en: positivos con palabra de venta clara (gebrauchtwagen/occasion/autohaus…), ni rechazos duros (página vacía / categoría no-dealer declarada / sin señal automotriz).

## 4. Evidencia empírica [V] (`scripts/eval_llm_classifier.py`)
Muestra real de 21 dominios (20 alcanzables, 1 DNS muerto), etiquetada desde la evidencia de auditorías previas: dealers reales (dacia/nissan/mercedes/AMAG/BOVAG/AGVS) + no-dealers (museo BMW art, ópticos, audio, **taller de motos, neumáticos, chapa**). Se fetchea cada homepage en vivo (curl_cffi Chrome-impersonate) y se compara heurística-sola vs LLM-asistida.

- **economy: precisión 0,750→0,900, accuracy 0,800→0,900, recall 0,900 intacto, 3 llamadas LLM.** Flips correctos: `manu-motos.ch` (moto) y `carrosserie-palmieri.ch` (chapa) → False. **Es la victoria: más precisión, sin perder dealers, casi sin coste.**
- **precision (experimental): NETO DAÑINO — recall 0,600.** El 3b sobre 1.500 chars de homepage (cookie/nav) es demasiado conservador para **anular positivos bien fundados**: tumbó dacia/advg/AMAG (dealers reales) a "car_parts_shop". → **No recomendado; queda off.** *(Hallazgo honesto: el LLM pequeño NO debe sobrescribir positivos heurísticos en bloque; solo arbitrar la banda dudosa.)*
- Residual no cubierto por economy: `ap-optik.de` resultó ser **software B2B para concesionarios** (lleno de "gebrauchtwagen/autohaus") — FP rico-en-vocab que solo precision detecta (a costa del recall). Documentado, no oculto.
- FN fuera de alcance del LLM: `autohuiskes.nl` es un SPA de 1.814 chars (shell JS) → sin contenido que clasificar; necesita render E07, no LLM.

## 5. Integración en el pipeline (opt-in, fail-open)
- **`worker.py` (domain-resolution)** cableado: cuando `DOMRES_LLM_VERIFY=1`, un dominio que **pasa** la heurística se re-verifica por la capa difusa (un solo fetch; heurística-primero + LLM-en-duda) antes de persistir. **Default OFF → comportamiento idéntico al actual** (cero cambio en prod salvo activación explícita). Fail-open: si Ollama no está, cae a la heurística.
- La capa es además librería lista para los otros call-sites (detector de dealers, extractor de campos, desambiguación), con el mismo patrón heurística-primero.

## 6. Tests + no-regresión [V]
- `scrapers/tests/test_llm_decisions.py` — **19 tests**: routing (claro→sin LLM, dudoso→LLM, hard-reject→sin LLM), fail-open (server muerto, JSON roto, no disponible), guard de consistencia, modos economy/precision/off, extract/disambiguate, + **1 integración en vivo** (óptico→no-dealer contra Ollama real).
- **Suite completa: 1458 passed, 0 failed** (1439 base + 19). Cero regresión.

## 7. Limitaciones honestas + siguientes pasos
- **Latencia 8–25 s/llamada** (3b en CPU). Aceptable para fallback de bajo volumen; no apto para clasificar en masa. Si se quisiera volumen, GPU o un modelo más pequeño/cuantizado.
- **RAM:** 0,64 GB libres con el modelo cargado en este host — transitorio (recupera tras `keep_alive`), pero conviene no correr el LLM y el coordinator pesado a la vez. `keep_alive=120s` lo mitiga.
- **precision mode dañino** con 3b+texto-truncado → off por defecto.
- **Siguiente:** activar `DOMRES_LLM_VERIFY=1` en un drain controlado para medir el FP-reduction a escala sobre la cola real; cablear `extract_vehicle_fields` en el seam E07 (HTML caótico) y `disambiguate_domain` en el resolver; evaluar dar al clasificador más texto (no solo 1.500 chars) para recuperar parte del recall en precision mode.

---

*Capa Ollama montada, integrada (opt-in), testeada (1458 verde) y medida en vivo (precisión 0,750→0,900 con cero pérdida de recall, 3 llamadas LLM, coste Claude cero). Persistente y fail-open. Sin push, main intacto.*
