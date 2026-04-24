# Deep Audit — Sistema de Indexación (A→Z)

Fecha: 2026-04-24
Alcance: `discovery/` (familias A–O, KG SQLite, orquestación, métricas, health, pulse)

## 1) Veredicto ejecutivo

- **No está al 100%** en sentido institucional estricto. Está **muy avanzado** para enfoque “free-first”, pero aún presenta gaps críticos de resiliencia y gobernanza técnica.
- **Nota global institucional (1–10): 7.8/10**.
  - Arquitectura y cobertura de señales: muy alta.
  - Robustez operativa bajo fallos y dependencia externa: media.
  - Modelo de confianza/riesgo: bueno pero aún heurístico.

## 2) Fortalezas de nivel alto

1. **Cobertura multivector real (15 familias A–O)** con principio de redundancia por diseño.
2. **Knowledge Graph persistente bien estructurado** (entidad dealer, identificadores, web presence, discovery log, vehículos) con índices y constraints útiles.
3. **Migrations incrementales versionadas** y apertura idempotente DB.
4. **Instrumentación Prometheus amplia** (ciclos, requests, errores, WAL, backup timestamp).
5. **Modo “free-first” pragmático**: múltiples integraciones opcionales por API key y degradación parcial.
6. **Protocolo de saturación formal** (evita “falso 100%”).

## 3) Hallazgos críticos (prioridad alta)

### C1 — Orquestación secuencial sin timeouts por familia/subtécnica
- El servicio ejecuta familias por país en secuencia y depende de cancelación global por señal de proceso.
- Riesgo: una subtécnica lenta/bloqueada puede prolongar o congelar el ciclo completo.
- Impacto: degradación de SLA, huecos temporales en indexación y observabilidad engañosa.
- Recomendación:
  - `context.WithTimeout` por familia y por subtécnica.
  - scheduler con budget por ciclo y cola de reintentos exponencial.
  - circuit-breakers por proveedor/fuente.

### C2 — Confianza de entidades aún heurística (no bayesiana)
- El score actual suma pesos por familia y clampa a 1.0.
- El propio código reconoce que es una aproximación y que falta el modelo bayesiano con dependencia entre fuentes.
- Riesgo: sobreestimación cuando señales correlacionadas se cuentan como independientes.
- Recomendación:
  - modelo bayesiano/graphical con penalización por correlación entre familias.
  - calibración con dataset etiquetado y curvas de confiabilidad.

### C3 — Riesgo de ownership ambiguo en dominio web
- `UpsertWebPresence` hace conflicto por `domain`, pero al colisionar sólo actualiza `url_root` y `discovered_by_families`.
- Riesgo: si un dominio cambia de dealer (M&A, cesión, error inicial), el `dealer_id` puede quedar desalineado con la realidad.
- Recomendación:
  - estrategia explícita de re-asignación con reglas (evidencia mínima + historial).
  - tabla de historial de ownership de dominio con vigencia temporal.

### C4 — Readiness de tests dependiente de red externa en este entorno
- El test run no pudo completarse por descarga bloqueada de módulos Go.
- Riesgo: sin test pass recurrente en CI aislado, aumenta probabilidad de drift funcional.
- Recomendación:
  - proxy/cache interno de módulos o vendoring para entornos restringidos.

## 4) Hallazgos importantes (prioridad media)

1. **Health checks existen pero falta “gate” duro pre-ciclo** para evitar contar ciclos parcialmente degradados como sanos.
2. **Dependencia fuerte de SQLite + single writer** (correcto para MVP) pero requiere disciplina de batch/locks al crecer.
3. **Rate-limit tuning por familia existe**, muy positivo, pero falta estrategia adaptativa automática por telemetría.
4. **Objetivo de saturación está muy bien definido**, aunque necesita dashboard operativo para validarlo automáticamente.

## 5) Qué está muy bien (institucional)

- Diseño de descubrimiento por **capas ortogonales** (legal, geo, web, infra, asociaciones, OEM, social, fiscal, prensa).
- Separación clara de responsabilidades: config, runner, KG, familias, pulse.
- Esquema SQL con base sólida y migraciones controladas.
- Documentación estratégica inusualmente fuerte para una plataforma free-first.

## 6) Roadmap recomendado (90 días)

### Fase 1 (0–30 días)
- Timeouts y budgets por familia/subtécnica.
- Retry policy estandarizada (transient vs permanent errors).
- Health gate obligatorio antes de declarar ciclo válido.

### Fase 2 (31–60 días)
- Confidence model v2 (dependencias entre fuentes).
- Ownership temporal de dominios y reconciliación automática asistida.
- SLOs formales: freshness, completeness proxy, source reliability.

### Fase 3 (61–90 días)
- Auto-throttling por familia con feedback de error-rate/latencia.
- Pipeline de validación de saturación automatizado con reporte firmado.
- Paquete “institutional hardening” (runbooks de incidente + game days).

## 7) Respuesta a tus preguntas (directa)

- **¿Funciona al 100%?**
  - No en términos institucionales. Sí funciona a nivel muy competente para etapa actual, pero tiene deuda crítica de resiliencia y scoring probabilístico.

- **¿Qué veo crítico?**
  - Timeouts/retries/circuit breaking en orquestación.
  - Modelo de confianza aún simplificado.
  - Resolución de ownership en colisiones de dominio.

- **¿Qué es bueno?**
  - Cobertura A–O, arquitectura KG, métricas, documentación de saturación, enfoque free-first bien planteado.

- **¿Qué se puede mejorar?**
  - Operación robusta (SRE), confiabilidad estadística (Bayesian confidence), gobierno de identidad temporal.

- **¿Entiendo la lógica?**
  - Sí: discovery multifuente → consolidación KG → scoring/confianza → observabilidad/saturación → mantenimiento.

- **¿Está a niveles superiores/institucionales (1–10)?**
  - **7.8/10 hoy**.
  - Con el roadmap propuesto, **8.8–9.2/10** en 1–2 trimestres.

## 8) Contexto “solo vías gratis”

Para estrategia free-first, el sistema está **por encima de la media**: combina fuentes públicas, diseño de redundancia y disciplina documental. El salto a “institucional premium” no exige pagar más fuentes primero; exige fortalecer la capa operativa y probabilística.
