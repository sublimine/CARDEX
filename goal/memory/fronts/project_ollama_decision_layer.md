---
name: project_ollama_decision_layer
description: "Local Ollama LLM fuzzy-decision layer — heuristic-first fallback, zero Claude tokens in steady state"
metadata: 
  node_type: memory
  type: project
  originSessionId: df38bd40-b67d-485b-a1cd-efc4dee5c973
---

Capa LLM local montada en rama `feature/ollama-decision-layer` (worktree `C:\Users\elias\cardex-ollama`, desde main `1ca158a`, commit `bbfff03`, NO push). Reporte: `OLLAMA_LAYER_REPORT.md`. Objetivo: micro-decisiones difusas del pipeline con LLM local gratis → régimen sin tokens Claude.

**Stack [V]:** Ollama 0.30.6 instalado (winget), server **persistente** `127.0.0.1:11434` (proceso del instalador, PID serve+tray). Modelo `qwen2.5:3b` (1,8GB Q4) — elegido por RAM (host 15,3GB, ~2,4GB libres bajo Docker; 7b no cabe). **RAM: 2,38→0,64GB con modelo cargado (~1,74GB), recupera a 4,24GB tras `keep_alive=120s`** → presión transitoria. **Latencia: cold ~25s, warm ~8-12s** (3b en CPU, sin GPU). También hay qwen3:4b/8b de un install previo.

**Arquitectura `scrapers/llm/`:** `ollama_client.py` (stdlib urllib, sin deps nuevas; `format=json`, temp=0, semáforo 1-gen para RAM, health cacheado; **fail-open**: fallo→None→heurística). `decisions.py`: `classify_is_car_dealer` / `extract_vehicle_fields` / `disambiguate_domain` — **heurística-primero, LLM solo banda dudosa**. Modos `LLM_DECISION_MODE`: economy(default)/precision(experimental)/off. Guard de consistencia (LLM dice False pero kind="dealership" → contradicción → manda heurística).

**Banda economy:** positivo heurístico débil (city-only/weak-only/carrosserie-only) o negativo por tecnicismo nombre/ciudad en página automotriz. NUNCA: positivos con palabra de venta clara, ni rechazos duros.

**EVIDENCIA [V]** (`scripts/eval_llm_classifier.py`, 20 dominios reales incl. moto/tyre/body FPs): heurística-sola precisión **0,750**/recall 0,900/acc 0,800 → **economy 0,900/0,900/0,900 con 3 llamadas LLM** (arregló manu-motos.ch=taller-motos y carrosserie-palmieri.ch=chapa, sin perder dealers). **precision mode NETO DAÑINO (recall 0,60: tumba dacia/advg/AMAG reales)→off**. LECCIÓN: el 3b NO debe anular positivos heurísticos en bloque, solo arbitrar la banda dudosa. FP residual `ap-optik.de`=software B2B para concesionarios (vocab-rich, solo precision lo caza). FN `autohuiskes.nl`=SPA shell (necesita E07, no LLM).

**Integración:** `worker.py` (domain-resolution) hook opt-in `DOMRES_LLM_VERIFY=1` (default OFF=comportamiento idéntico; un solo fetch; fail-open). Librería lista para detector/extractor/resolver.

**Tests:** `test_llm_decisions.py` 19 (routing, fail-open, guard, modos, +1 integración viva). **Suite 1458 verde**, cero regresión. main intacto (1ca158a), origin sin push (6e084a5). Continúa [[project_domainres_audit_2026_06_07]] (la heurística que envuelve). Refina [[project_storage_reality]] (host low-RAM: el LLM 3b carga ~1,7GB, transitorio).
