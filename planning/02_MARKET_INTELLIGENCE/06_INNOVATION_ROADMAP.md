# 06 — Innovation Roadmap: 5 Game-Changers
**Estado:** ACTIVO  
**Fecha:** 2026-04-14  
**Scope:** Tecnologías de diferenciación competitiva — horizonte 12 meses post-MVP

---

## Resumen ejecutivo

Cinco tecnologías AI/ML que pueden transformar CARDEX de un aggregator de datos a una plataforma de inteligencia de vehículos sin precedente en el mercado europeo. Todas operan **100% CPU-local** (sin API costs), son open-source (MIT/Apache 2.0), y se integran en la arquitectura modular existente.

| # | Tecnología | Edge | Implementación | Semanas |
|---|-----------|------|---------------|---------|
| 1 | GNN — Detección fraude estructural | 8/10 | PyTorch Geometric + DGL | 8-10w |
| 2 | VLM — Computer Vision de vehículos | 7/10 | Phi-3.5 Vision / LLaVA-CoT ONNX | 6-8w |
| 3 | RAG — Asistente de compra contextual | 8/10 | nomic-embed-text + FAISS + Llama 3.2 | 8-10w |
| 4 | Chronos-2 — Forecast precio series temporales | 8/10 | Amazon Chronos-2 CPU open-source | 6-8w |
| 5 | BGE-M3 — Entity resolution multilingüe | 6/10 | BGE-M3 ONNX + FAISS | 4-6w |

**Secuenciación recomendada:** M1-M3 VLM+BGE → M3-M5 GNN → M5-M8 Chronos → M8-M11 RAG

---

## Game-Changer #1 — GNN: Detección de Fraude Estructural

### Concepto
Graph Neural Network que modela relaciones entre entidades del ecosistema de vehículos: dealers, listings, VINs, dominios, precios históricos, patrones de rotación. Detecta estructuras anómalas (cuentas fake coordinadas, price rings, listings duplicados across markets) que los sistemas heurísticos no pueden capturar.

### Stack técnico
- **Librería:** PyTorch Geometric + DGL (CPU mode, no GPU requerida)
- **Modelo base:** LayoutLMv3 para document understanding (opcional para carfax docs)
- **Módulo:** `familia_p_gnn/` — nuevo módulo en el monorepo
- **Inputs:** grafo bipartito (dealers × listings) con edge features (precio, tiempo, geo, VIN hash)
- **Output:** anomaly score por listing + cluster de entidades sospechosas

### Edge competitivo: 8/10
Ningún aggregator europeo actual tiene detección de fraude a nivel estructural. Los incumbentes (Mobile.de, Autoscout24) tienen heurísticas básicas. Un GNN con 6 meses de datos históricos de CARDEX sería un activo defensible.

### Implementación
```
familia_p_gnn/
├── graph_builder.go      # Construye grafo desde discovery.db
├── feature_extractor.py  # Edge/node features
├── gnn_model.py          # PyG model definition
├── fraud_scorer.py       # Inference + scoring
└── README.md
```

**Estimación:** 8-10 semanas (2 senior ML + 1 backend Go)  
**Dependencias:** PyTorch ≥2.1, torch-geometric ≥2.4, Python 3.11

---

## Game-Changer #2 — VLM: Computer Vision de Vehículos

### Concepto
Visual Language Model para análisis automático de imágenes de vehículos. Detecta daños no declarados, verifica coherencia entre descripción textual e imagen, extrae especificaciones desde fotos del interior (pantalla de instrumentos, etiquetas de eficiencia), y genera quality scores de las fotos.

### Stack técnico
- **Modelo primario:** Phi-3.5 Vision (3.8B params, MIT license) — corre en CPU en ~4-8s/imagen
- **Alternativa:** LLaVA-CoT-11B-Vision-Preview (reasoning explicativo)
- **Runtime:** ONNX Runtime CPU (sin PyTorch en producción)
- **Estrategia:** E13 — solo procesar imágenes portada + 2 imágenes más relevantes por listing
- **Output:** `{damage_detected: bool, damage_areas: [...], photo_quality_score: 0-10, inconsistencies: [...]}`

### Edge competitivo: 7/10
La detección automática de daños en fotos es un diferenciador de confianza para buyers. Ningún aggregator europeo lo ofrece como feature nativa. Permite filtro "solo listings sin daños visibles" — demand altísima.

### Implementación
```
vision/
├── image_extractor.go    # Descarga imágenes desde listings
├── vlm_analyzer.py       # ONNX inference Phi-3.5 Vision
├── damage_detector.py    # Damage classification pipeline
├── photo_scorer.py       # Quality scoring
└── vlm_results.go        # Persist to discovery.db
```

**Estimación:** 6-8 semanas  
**Dependencias:** onnxruntime ≥1.17, transformers ≥4.40, Pillow ≥10.0  
**Constraint hardware:** mínimo 16GB RAM para Phi-3.5 Vision en CPU; 32GB recomendado

---

## Game-Changer #3 — RAG: Asistente de Compra Contextual

### Concepto
Retrieval-Augmented Generation que permite queries en lenguaje natural sobre el inventario de vehículos. "Busco un SUV híbrido de menos de €30k con menos de 80.000km en Bélgica o Países Bajos que no tenga recalls activos" → respuesta estructurada con listings rankeados + reasoning explicativo.

### Stack técnico
- **Embeddings:** `nomic-embed-text` (GGUF, MIT license) — 768 dims, multilingüe
- **Vector store:** FAISS (Facebook AI Similarity Search, MIT) — índice IVF_FLAT en disco
- **LLM:** Llama 3.2 7B Q4_K_M (Meta, LLaMA Community License) via llama.cpp
- **Módulo:** `terminal/internal/rag/` — integrado en el terminal B2B existente
- **Reranking:** BGE-reranker-v2-m3 (complementario con #5)

### Edge competitivo: 8/10
Transforma CARDEX de una tabla de datos en un consultor de compra. Buyres B2C y agentes B2B pueden hacer queries complejas multi-criterio que ningún filtro convencional puede manejar. Defensibilidad: el índice vectorial se enriquece con cada nuevo listing.

### Implementación
```
terminal/internal/rag/
├── embedder.go           # nomic-embed-text wrapper
├── vector_store.go       # FAISS index management
├── retriever.go          # Semantic search + rerank
├── llm_client.go         # llama.cpp HTTP client
├── rag_pipeline.go       # Orchestration
└── query_parser.go       # NL query → structured filters
```

**Estimación:** 8-10 semanas  
**Dependencias:** llama.cpp server, faiss-cpu ≥1.8.0, nomic-embed-text GGUF  
**Infraestructura:** llama.cpp server como systemd unit en VPS; ~6GB RAM for Q4_K_M model

---

## Game-Changer #4 — Chronos-2: Forecast de Precio en Series Temporales

### Concepto
Amazon Chronos-2 es un modelo de foundation para time-series forecasting, open-source, que corre 100% en CPU. Predice precio de mercado futuro de un vehículo específico (make/model/year/km) con intervalos de confianza. Permite a buyers saber si el precio actual es una oportunidad o si esperar.

### Stack técnico
- **Modelo:** Amazon Chronos-2 (Apache 2.0) — versión "small" (46M params, CPU-viable)
- **Módulo:** `forecasting/` — servicio independiente
- **Inputs:** histórico de precios por segmento (extraído de discovery.db, 6+ meses de datos)
- **Output:** precio esperado a 30/60/90 días + intervalo de confianza 80% + tendencia (↑↓→)
- **Granularidad:** por make/model/year/fuel_type/market

### Edge competitivo: 8/10
El precio forecast es información de alto valor para cualquier buyer y dealer. Requiere datos históricos propios — ventaja natural para CARDEX que acumula precios desde el inicio. A 12 meses de operación, el modelo tendrá ~500K datapoints para training fine-tuning.

### Implementación
```
forecasting/
├── price_historian.go    # Extrae series temporales de discovery.db
├── chronos_client.py     # Chronos-2 inference wrapper
├── forecast_service.go   # gRPC service
├── forecast_api.go       # REST endpoint para terminal
└── models/               # Chronos-2 weights (small variant)
```

**Estimación:** 6-8 semanas  
**Dependencias:** chronos-forecasting (Amazon), torch ≥2.1, numpy, pandas  
**Prerequisito:** ≥6 meses de datos históricos de precios en discovery.db

---

## Game-Changer #5 — BGE-M3: Entity Resolution Multilingüe

### Concepto
BGE-M3 (BAAI, MIT license) es el estado del arte en embeddings multilingüe (100+ idiomas). Resuelve el problema de entity resolution entre markets: "Volkswagen Golf 8 GTI" en AutoScout24.de = "VW Golf GTI 2.0 TSI" en Autoscout24.fr = "Golf GTI 245pk" en AutoScout24.nl. Sin entity resolution, los dashboards B2B comparan äppels con oranges.

### Stack técnico
- **Modelo:** BGE-M3 ONNX (FlagEmbedding, MIT license) — 568M params, int8 quantized para CPU
- **Vector store:** FAISS IVF index sobre embedding space de make/model/trim
- **Integración:** V21 — nuevo validator que normaliza make/model/trim antes de almacenar
- **Módulo:** integrado en `discovery/internal/normalizer/` + nuevo validator `V21_entity_resolution.md`

### Edge competitivo: 6/10
Entity resolution es tabla stakes para comparación cross-market precisa. Sin él, los dashboards B2B son imprecisos. El edge no es visible para usuarios finales pero es infraestructura crítica para que los otros 4 game-changers funcionen correctamente (especialmente GNN y Chronos-2).

### Implementación
```
discovery/internal/normalizer/
├── bge_embedder.py       # BGE-M3 ONNX inference
├── entity_index.go       # FAISS index de entidades canónicas
├── resolver.go           # make/model/trim → canonical entity
└── v21_validator.go      # Integration with validator pipeline
```

**Estimación:** 4-6 semanas  
**Dependencias:** onnxruntime ≥1.17, faiss-cpu ≥1.8.0, BGE-M3 ONNX weights (~1.1GB)

---

## Secuenciación e Interdependencias

```
M1  M2  M3  M4  M5  M6  M7  M8  M9  M10 M11
|---|---|---|---|---|---|---|---|---|---|---|
[#2 VLM: Phi-3.5 Vision ONNX      ]
    [#5 BGE-M3 Entity Resolution]
            [#1 GNN Fraud Detection        ]
                    [#4 Chronos-2 Forecast     ]
                                [#3 RAG Assistant            ]
```

**Rationale del orden:**
1. **VLM primero (M1-M3):** Diferenciador visible para users, standalone, menor riesgo técnico. Valida capacidad CPU para inference.
2. **BGE-M3 en paralelo (M1-M3):** Fundación necesaria para GNN y Chronos-2 (entity resolution).
3. **GNN después de BGE-M3 (M3-M5):** Requiere entidades normalizadas para construir grafo limpio.
4. **Chronos-2 después de 6 meses datos (M5-M8):** Necesita histórico de precios suficiente.
5. **RAG último (M8-M11):** Mayor complejidad de infraestructura; se beneficia de todos los datos enriquecidos por #1-#4.

---

## Consideraciones de Infraestructura

### Requisitos hardware mínimos (producción)
| Game-Changer | RAM adicional | Disco adicional | CPU adicional |
|-------------|--------------|----------------|--------------|
| VLM (Phi-3.5) | +16GB | +4GB (weights) | +2 cores |
| BGE-M3 | +4GB | +2GB (ONNX + index) | +1 core |
| GNN | +8GB | +1GB | +2 cores |
| Chronos-2 | +6GB | +1GB (weights) | +1 core |
| RAG (Llama 3.2 7B Q4) | +8GB | +8GB (weights + FAISS) | +2 cores |
| **Total acumulado** | **+42GB** | **+16GB** | **+8 cores** |

**Implicación:** El VPS actual (Hetzner CX41: 8 vCPU, 16GB RAM) es insuficiente para todos los game-changers en producción. Upgrade a CX52 (16 vCPU, 32GB, €50/mes) o CX62 (32 vCPU, 64GB, €90/mes) necesario antes de M8.

### Costes adicionales estimados
| Ítem | Coste mensual |
|------|--------------|
| VPS upgrade CX52 (desde CX41) | +€30-50/mes |
| Hetzner Storage Box (models + índices) | +€5/mes |
| **Incremento total OPEX** | **+€35-55/mes** |

Dentro del presupuesto OPEX revisado (€60-150/mes runtime).

---

## Criterios de Go/No-Go por Game-Changer

| # | Go si… | No-Go si… |
|---|--------|----------|
| VLM | Phi-3.5 <10s/imagen en CX41 | >30s/imagen — buscar modelo más pequeño |
| BGE-M3 | Precision@10 >85% en test set multilingüe | <70% — evaluar alternativas (LaBSE) |
| GNN | F1 >0.80 en fraud detection en holdout set | <0.60 — insuficiente signal en datos |
| Chronos-2 | MAPE <15% en forecast 30d con 6mo histórico | >25% — esperar más datos |
| RAG | Respuesta relevante en >70% de test queries B2B | <50% — revisar chunking + retrieval |

---

## Relación con Planning Existente

- **R-AI-01** (model drift): Cada game-changer requiere monitoreo de drift; ver RISK_REGISTER.md
- **R-AI-02** (hallucination NLG): RAG (#3) mitiga parcialmente al grounding en datos verificados
- **V19 AI Act compliance**: El output del RAG (#3) y VLM (#2) requieren disclosure Art. 50
- **CS-0-3 (CardexBot UA)**: Todo HTTP client en estos módulos debe usar CardexBot UA
- **OPEX €60-150/mes**: La secuenciación permite absorber costes incrementalmente
