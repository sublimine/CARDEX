# 07 — Roadmap

## Estado
Todos los documentos: **DOCUMENTADO** — 2026-04-14

## Índice

### Principios y transversales

| Archivo | Contenido | Estado |
|---|---|---|
| [00_PRINCIPLES.md](00_PRINCIPLES.md) | Principios del roadmap: criterios cuantitativos, política no-avanzar-sin-cerrar, regresión, retrospectiva | DOCUMENTADO |
| [DEPENDENCIES_GRAPH.md](DEPENDENCIES_GRAPH.md) | Grafo de dependencias entre fases (mermaid) + tabla de paralelización | DOCUMENTADO |
| [RISK_REGISTER.md](RISK_REGISTER.md) | Registro de riesgos transversales: legal, técnico, operacional, mercado | DOCUMENTADO |
| [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md) | Criterio global de MVP institucional completo | DOCUMENTADO |

### Fases de ejecución

| Fase | Archivo | Nombre | Estado | Dependencias |
|---|---|---|---|---|
| P0 | [PHASE_0_LEGAL_CLEANUP.md](PHASE_0_LEGAL_CLEANUP.md) | Legal Cleanup — Purga código ilegal | PENDING | — |
| P1 | [PHASE_1_MARKET_INTELLIGENCE.md](PHASE_1_MARKET_INTELLIGENCE.md) | Market Intelligence | PENDING | P0 (paralelo OK) |
| P2 | [PHASE_2_DISCOVERY_BUILDOUT.md](PHASE_2_DISCOVERY_BUILDOUT.md) | Discovery Buildout — 15 familias | PENDING | P0 |
| P3 | [PHASE_3_EXTRACTION_PIPELINE.md](PHASE_3_EXTRACTION_PIPELINE.md) | Extraction Pipeline — E01-E12 | PENDING | P2 |
| P4 | [PHASE_4_QUALITY_PIPELINE.md](PHASE_4_QUALITY_PIPELINE.md) | Quality Pipeline — V01-V20 + NLG | PENDING | P3 parcial |
| P5 | [PHASE_5_INFRASTRUCTURE.md](PHASE_5_INFRASTRUCTURE.md) | Infrastructure — VPS producción | PENDING | P4 (paralelo OK con P4) |
| P6 | [PHASE_6_COUNTRY_ROLLOUT.md](PHASE_6_COUNTRY_ROLLOUT.md) | Country Rollout — NL→DE→FR→ES→BE→CH | PENDING | P2+P3+P4+P5 |
| P7 | [PHASE_7_PUBLIC_LAUNCH.md](PHASE_7_PUBLIC_LAUNCH.md) | Public Launch — soft launch + apertura | PENDING | P6 ≥1 país |
| P8 | [PHASE_8_MAINTENANCE.md](PHASE_8_MAINTENANCE.md) | Maintenance — operación sostenida | PENDING | P7 |

## Visualización del flujo

```
P0 ──────────────────────────────────────────────────────────────────┐
     │                                                               │
P1 ──┤ (paralelo con P0)                                             │
     │                                                               │
     └──► P2 ──► P3 ──► P4 ──► P6 ──► P7 ──► P8
                          │
                          P5 (paralelo con P4)
                          │
                          └──► P6
```

## Convención de estados

| Estado | Significado |
|---|---|
| `PENDING` | No iniciada |
| `IN_PROGRESS` | Activa, criterios en proceso de cumplimiento |
| `DONE` | Todos los criterios cuantitativos verificados, retrospectiva completada |
| `REGRESSED` | Criterio cayó bajo threshold post-DONE — fase reabierta |
