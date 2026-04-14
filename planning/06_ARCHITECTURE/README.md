# 06 — Architecture

## Estado
Todos los documentos: **DOCUMENTADO** — 2026-04-14

## Índice

| # | Archivo | Contenido | Estado |
|---|---------|-----------|--------|
| 01 | [01_SYSTEM_CONTEXT.md](01_SYSTEM_CONTEXT.md) | C4 Context: actores externos, boundaries, interacciones | DOCUMENTADO |
| 02 | [02_CONTAINER_ARCHITECTURE.md](02_CONTAINER_ARCHITECTURE.md) | C4 Container: servicios Go/Python, data stores, colas, diagrama mermaid | DOCUMENTADO |
| 03 | [03_COMPONENT_DETAIL.md](03_COMPONENT_DETAIL.md) | Componentes internos por servicio, interfaces Go exportadas, paquetes | DOCUMENTADO |
| 04 | [04_DATA_FLOW.md](04_DATA_FLOW.md) | End-to-end flow discovery→extraction→quality→index→API, sequence diagrams | DOCUMENTADO |
| 05 | [05_VPS_SPEC.md](05_VPS_SPEC.md) | Vendor comparison, recomendación Hetzner CX41, OS, particionado, backup, coste €22.25/mes | DOCUMENTADO |
| 06 | [06_STACK_DECISIONS.md](06_STACK_DECISIONS.md) | Tooling matrix capa por capa con alternativas y justificación cuantitativa | DOCUMENTADO |
| 07 | [07_DEPLOYMENT_TOPOLOGY.md](07_DEPLOYMENT_TOPOLOGY.md) | systemd units, Docker compose, Caddy reverse proxy, Unix sockets, secrets | DOCUMENTADO |
| 08 | [08_OBSERVABILITY.md](08_OBSERVABILITY.md) | Catálogo Prometheus, dashboards Grafana, alerting rules, log schema, tracing | DOCUMENTADO |
| 09 | [09_SECURITY_HARDENING.md](09_SECURITY_HARDENING.md) | Debian CIS, UFW, SSH Ed25519, fail2ban, TLS, auditd, AppArmor, secrets rotation | DOCUMENTADO |
| 10 | [10_SCALING_PATH.md](10_SCALING_PATH.md) | Fases S0-S3 con criterios cuantitativos, GPU path para NLG, K8s endgame | DOCUMENTADO |
| 11 | [11_CI_CD_PIPELINE.md](11_CI_CD_PIPELINE.md) | Forgejo self-hosted, illegal-pattern linter blocker, test gates, deploy in-place | DOCUMENTADO |

## Principios rectores de arquitectura

### 1. Single-VPS lean
Todo corre en un único VPS Hetzner CX41 (€18/mes). No hay dependencias de servicios cloud gestionados, APIs de pago, ni SaaS de terceros. El sistema es autocontenido: puede arrancarse desde cero en un VPS nuevo en <30 minutos.

### 2. €0 OPEX de licencias
Stack 100% open-source. Sin licencias de software, sin APIs de pago en runtime. Herramientas de pago (e.g. Hetzner Cloud, Storage Box) son infraestructura, no software. La única excepción admitida es un free tier verificado con fallback.

### 3. Observable desde el día uno
Métricas Prometheus + dashboards Grafana están en el plan de despliegue inicial, no como "to-do futuro". Un sistema no observable no puede mantenerse en producción sin personal a tiempo completo.

### 4. Resumable y tolerante a fallos
Cada pipeline (discovery, extraction, quality, NLG) es idempotente. Se puede matar y reanudar en cualquier punto sin pérdida de datos. Los dead-letter queues (DLQ) conservan todos los registros fallados para reintentos.

### 5. Escalable vertical y horizontal
El diseño S0 (single VPS) puede evolucionar a S3 (cluster K8s) sin reescritura de la lógica de negocio. Los boundaries entre servicios están definidos desde el inicio. Los datos están en formatos estándar (SQLite→Postgres, DuckDB→ClickHouse).

### 6. Identidad legal en todas las comunicaciones
CardexBot/1.0 User-Agent en todos los crawlers. Sin técnicas de evasión (curl_cffi, playwright-stealth, JA3/JA4, proxies residenciales). Documentado en ILLEGAL_CODE_PURGE_PLAN.md, enforced en CI.

### 7. Open-source only
Todos los modelos ML son públicos (ONNX from HuggingFace, llama.cpp with Llama 3). Todas las dependencias tienen licencias OSI-approved. Ningún componente propietario en el path crítico de datos.
