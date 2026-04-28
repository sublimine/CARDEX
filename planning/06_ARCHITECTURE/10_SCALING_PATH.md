# 10 — Scaling Path

## Identificador
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Principio

El diseño de CARDEX está pensado para comenzar en un único VPS (S0) y escalar sin reescritura de lógica de negocio. Los boundaries entre servicios están definidos desde el inicio; los datos están en formatos portables (SQLite→Postgres, DuckDB→ClickHouse). Cada transición de fase tiene criterios cuantitativos de entrada — no se escala por anticipación, sino por necesidad medida.

---

## Fase S0 — Single VPS (estado actual)

**Configuración:**
```
1× Hetzner CX42 (4 vCPU, 16 GB RAM, 240 GB NVMe) — plan renombrado de CX41 en 2024
Todo co-located: Discovery + Extraction + Quality + NLG + Index + API
SQLite OLTP (WAL) + DuckDB OLAP
NATS embedded
OPEX: ~€22.25/mes (estimado — verificar precios actuales en hetzner.com/cloud)
```

**Capacidad estimada (hipótesis de diseño — a validar en S0 real):**
- Dealers indexados: hasta ~15.000 ACTIVE
- Vehículos ACTIVE: hasta ~100.000
- Queries B2B: hasta ~500 req/min (hipótesis — DuckDB columnar eficiente; a medir con carga real)
- NLG throughput: ~500-1.300 descripciones/noche (hipótesis — ver 06_STACK_DECISIONS.md: ~2-8 tok/s en CX42)
- Crawling: ~50.000 listings/día respetando rate limits (hipótesis — depende de distribución de rate limits por fuente)

**Criterios de salida a S1 (CUALQUIERA de los siguientes):**
```
□ RAM media >75% durante >7 días consecutivos (excluida ventana NLG)
□ CPU media >70% durante >7 días consecutivos
□ SQLite WAL checkpoint latency p99 >200ms de forma sostenida (>24h)
□ DuckDB query p99 >1s en búsquedas B2B típicas
□ NLG queue acumula >3 noches de backlog sin reducirse
□ Disco /srv >75% lleno
□ >15.000 dealers ACTIVE (saturación de índice SQLite single-file)
```

---

## Fase S1 — Dos VPS (Web + Backend)

**Trigger cuantitativo:** 2+ criterios de salida S0 activos durante >7 días.

**Configuración:**
```
VPS-A (Web + API):      Hetzner CX42 — API Service, SSE Gateway, Caddy, Manual Review UI
                        DuckDB OLAP read replica (parquet files copiados via rsync cada 5min)
                        OPEX: ~€18/mes (estimado)

VPS-B (Backend):        Hetzner CX52 (8 vCPU, 32 GB RAM) — Discovery, Extraction, Quality, NLG
                        SQLite OLTP (WAL) escrituras
                        NATS broker (exposición TCP entre VPS via WireGuard VPN)
                        OPEX: ~€32/mes (estimado — verificar en hetzner.com/cloud)

Storage Box: 1 TB       Backup + parquet OLAP sync (rsync VPS-B → Storage Box → VPS-A)
                        OPEX: ~€3/mes (estimado)

WireGuard VPN:          Tunnel privado VPS-A ↔ VPS-B (cifrado, sin exposición pública)
                        10.10.0.1 (VPS-A) ↔ 10.10.0.2 (VPS-B)

TOTAL OPEX S1: ~€53/mes (estimado)
```

**Cambios de arquitectura en S1:**
- NATS: embedded → servidor TCP en VPS-B, accesible desde VPS-A via WireGuard
- DuckDB OLAP: write en VPS-B, rsync diferencial cada 5min a VPS-A para queries API
- SQLite OLTP: sigue en VPS-B; API service en VPS-A usa DuckDB para queries y NATS para invalidaciones
- NLG service: VPS-B tiene 32 GB RAM → llama.cpp con 8 vCPU, throughput ~2× S0

**Capacidad S1:**
- Dealers indexados: hasta ~50.000 ACTIVE
- Vehículos ACTIVE: hasta ~500.000
- Queries B2B: ~2.000 req/min
- NLG: ~2.500-3.000 descripciones/noche

**Criterios de salida a S2:**
```
□ SQLite OLTP write throughput >500 writes/s sostenido
□ Parquet OLAP sync lag >5min de forma habitual
□ RAM VPS-B >80% durante >7 días (excluida ventana NLG)
□ >50.000 dealers ACTIVE
□ NLG queue acumula >5 noches de backlog
```

---

## Fase S2 — Tres VPS + OLAP dedicado

**Trigger cuantitativo:** 2+ criterios de salida S1 activos durante >14 días.

**Configuración:**
```
VPS-A (Web + API):      Hetzner CX42 — API Service, SSE Gateway, Caddy
VPS-B (Pipelines):      Hetzner CX52 — Discovery, Extraction, Quality
VPS-C (Data):           Hetzner EX44 (dedicated, 64 GB RAM, 2×512 GB NVMe)
                        - DuckDB OLAP queries (sin rsync lag — VPS-A conecta directo)
                        - PostgreSQL OLTP (migración desde SQLite)
                        - NATS JetStream cluster (2 nodes: VPS-B + VPS-C)
                        OPEX: €45/mes (bare metal)

NLG: continúa en VPS-B (CX52, 32 GB)

TOTAL OPEX S2: €98/mes
```

**Migración SQLite → PostgreSQL (evento crítico S2):**
```
1. Mantener SQLite en paralelo como read-only durante 7 días de transición
2. Dual-write: quality service escribe en SQLite Y en Postgres simultáneamente
3. Verificar consistencia con checksums periódicos
4. API service empieza a leer de Postgres (con fallback a SQLite si error)
5. Cortar lectura de SQLite cuando 0 errores durante 48h
6. SQLite se mantiene como backup cold por 30 días
```

**Capacidad S2:**
- Dealers indexados: hasta ~200.000 ACTIVE
- Vehículos ACTIVE: hasta ~2.000.000
- Queries B2B: ~10.000 req/min (DuckDB en bare metal EX44)
- NLG: ~5.000 descripciones/noche

**Criterios de salida a S3:**
```
□ PostgreSQL OLTP p99 write >500ms sostenido
□ DuckDB en VPS-C no suficiente para queries <200ms con >5M vehículos
□ NATS 2-node cluster con split-brain events registrados
□ >200.000 dealers ACTIVE
□ >3 países en saturación S3 (≥6 meses nivel 3)
```

---

## Fase S3 — Cluster Kubernetes + OLAP ClickHouse

**Trigger cuantitativo:** 2+ criterios de salida S2 activos durante >30 días.

**Configuración:**
```
K8s cluster (Hetzner Cloud Kubernetes o bare metal k3s):
  - 3 control plane nodes (CX31, €12/mes cada uno)
  - 4-8 worker nodes (CX42, €18/mes cada uno, autoscaling)
  - Load balancer Hetzner (€5/mes)

Datos:
  - PostgreSQL HA (Patroni cluster, 3 nodes CX42)
  - ClickHouse cluster (3 shards × 2 replicas, EX44 dedicated)
  - NATS cluster (3 nodes, JetStream, clustering nativo)
  - Redis cluster (sesiones API, cache de queries frecuentes)

6 Worker Pools independientes (sharding por país):
  discovery-DE, discovery-FR, discovery-ES, discovery-BE, discovery-NL, discovery-CH
  Cada pool: 2-4 pods, escala independientemente

OPEX estimado S3: ~€400-800/mes (hipótesis — variable con escala y precios cloud vigentes en el momento)
```

**Cambios de arquitectura en S3:**
- K8s deployments para cada servicio con HPA (Horizontal Pod Autoscaler)
- PostgreSQL → ClickHouse para queries OLAP (ClickHouse es ~10× más rápido para agregaciones columnares a escala)
- NATS JetStream en cluster real (no embedded) con replicación entre zonas
- CI/CD: Forgejo self-hosted → ArgoCD para GitOps en K8s
- NLG: pool de workers con GPU (ver sección GPU path)
- Monitoring: Prometheus federation + Thanos para long-term storage

**Capacidad S3:**
- Dealers indexados: ilimitado (sharding por país)
- Vehículos ACTIVE: 10.000.000+
- Queries B2B: 100.000+ req/min
- NLG: 50.000+ descripciones/noche (con GPU workers)

---

## GPU Path para NLG (fase S2+)

**Trigger cuantitativo:**
```
NLG queue backlog sostenido >72h (3 noches sin poder procesar cola)
Y/O descriptions pending >20% del total de vehículos ACTIVE
```

**Opción 1 — Hetzner GEX44 (GPU dedicada)**
```
Hardware:  Intel i9-13900 + RTX 3080 12 GB VRAM (verificar disponibilidad y specs actuales en hetzner.com)
Precio:    ~€118/mes (estimado — verificar en hetzner.com/dedicated/gpu)
NLG boost: llama.cpp con CUDA → ~60-120 tokens/s vs ~2-8 tokens/s en CPU (hipótesis, ver benchmarks llama.cpp)
           → ~4-8s por descripción vs 15-60s → ~10× throughput (hipótesis)
Capacidad: ~30.000-50.000 descripciones/noche (hipótesis)
```

**Opción 2 — Hetzner EX44 + eGPU (experimental)**
```
EX44 bare metal (€45/mes) + GPU Cloud tiempo compartido
Útil como step intermedio antes de dedicar GEX44 completo
```

**Configuración llama.cpp con CUDA:**
```bash
# Build llama.cpp con CUDA support
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release -j$(nproc)

# Variables de entorno para el servicio
Environment=LLAMA_CUDA_LAYERS=35   # offload 35 layers a GPU (de 32 total → full offload)
Environment=CUDA_VISIBLE_DEVICES=0
```

---

## Criterios cuantitativos de transición — resumen

| Métrica | S0→S1 | S1→S2 | S2→S3 |
|---|---|---|---|
| RAM media (steady) | >75% 7d | >80% 7d | >85% 14d |
| CPU media (steady) | >70% 7d | >75% 7d | >80% 14d |
| Dealers ACTIVE | >15.000 | >50.000 | >200.000 |
| Vehículos ACTIVE | >100.000 | >500.000 | >2.000.000 |
| DB write p99 | >200ms (SQLite WAL) | >500ms (SQLite) | >500ms (Postgres) |
| Query p99 (DuckDB) | >1s | >500ms | >200ms (necesita ClickHouse) |
| NLG queue backlog | >3 noches | >5 noches | — |
| Disco /srv | >75% | >70% total | — |

**Principio de transición:** los criterios son umbrales de alarma, no objetivos de diseño. Si el sistema puede continuar estable en S0 con 200.000 dealers porque la carga real es menor de la esperada, se permanece en S0. La escala se realiza por evidencia, no por anticipación.

---

## Costes por fase

> Todos los OPEX y capacidades son estimaciones hipotéticas. Verificar precios actuales en hetzner.com/cloud antes de planificar presupuesto.

| Fase | Dealers estimados (hipótesis) | OPEX/mes estimado | Coste/dealer/mes hipotético |
|---|---|---|---|
| S0 | 0-15.000 | ~€22 | ~€0.0015 |
| S1 | 15.000-50.000 | ~€53 | ~€0.0011 |
| S2 | 50.000-200.000 | ~€98 | ~€0.0005 |
| S3 | 200.000+ | ~€400-800 | ~€0.0020-0.0040 |

La eficiencia de coste por dealer mejora de S0 a S2 por economías de escala. S3 invierte la tendencia por el overhead de cluster, pero es justificable cuando el negocio tiene revenue proporcional.
