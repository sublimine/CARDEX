# CARDEX — Criterios de éxito

## Identificador
- Documento: 02_SUCCESS_CRITERIA
- Versión: 1.0
- Fecha: 2026-04-14
- Estado: AUTORITATIVO

Definiciones operacionales cuantitativas. Ninguna metáfora, ningún "aproximadamente". Cada criterio es verificable mediante query SQL o medición instrumentada.

## Definición operacional de "100% del territorio"

### Denominador
Conjunto de empresas legalmente registradas con código NACE 45.11 (o equivalente nacional 4511/4511Z/SBI 4511) en los seis países, descubiertas exhaustivamente mediante el sistema de discovery 15-familias. La cardinalidad N de este conjunto se determina empíricamente al ejecutar las familias hasta saturación, no se asume a priori.

### Numerador
Subconjunto del denominador para el cual CARDEX tiene al menos una estrategia E1-E12 exitosa de extracción de catálogo y al menos una unidad de inventario indexada en los últimos T_freshness días.

### Métrica de cobertura
Coverage_Score(país, fecha) = |numerador(país, fecha)| / |denominador(país, fecha)| × 100

### Métrica de exhaustividad de discovery
Discovery_Saturation(país) = TRUE si en los últimos 3 ciclos completos de las N familias activas no se descubrió ningún dealer nuevo durante el T_search calibrado para ese país.

### Métrica de profundidad de inventario por dealer
Inventory_Depth_Score(dealer) = vehículos_indexados(dealer) / vehículos_publicados_estimados(dealer)

donde vehículos_publicados_estimados se infiere por Vector 7 (perfil del dealer en aggregator que declara stock total) o por scrape inicial de su propia web (count de listings).

## Definición operacional de "zero-error"

### Métricas por vehículo publicado
- Validators_Passed = número de los 20 validadores V01-V20 que el registro pasó
- Validators_Failed = número que falló
- Manual_Review_Required = booleano
- Manual_Review_Verdict ∈ {APPROVED, REJECTED, FIXED}
- Confidence_Score = función ponderada de las fuentes y validaciones

### Estándar de publicación
Un vehículo está en el índice live si y solo si:
1. Validators_Passed = 20 OR (Manual_Review_Required AND Manual_Review_Verdict ∈ {APPROVED, FIXED})
2. Confidence_Score ≥ T_publish (calibrado, inicial 0.85)
3. Foto_URL devuelve HTTP 200 con content-type image/* en última verificación
4. NLG_Description está generada y pasa coherence check
5. Freshness_Age < TTL de la fuente

### Métricas agregadas de calidad
- Error_Rate(periodo) = |publicados con error reportado por usuario / total publicados|
- Manual_Review_Queue_Size_Trend
- Validator_Failure_Distribution(V01..V20) — cuáles fallan más
- NLG_Quality_Score (BLEU + human eval mensual sobre muestra)

### Objetivo
Error_Rate sostenido < 0.5% medido sobre ventana móvil 30 días.

## Criterios cuantitativos de salida por fase

### Fase 0 — Auditoría y limpieza legal
- 100% de archivos identificados como LEGACY-TO-PURGE están documentados con plan de reemplazo asignado
- 0 commits en main que introduzcan nuevos patrones ilegales (CI bloqueante operativo)
- STATE_OF_REPO.md y ILLEGAL_CODE_PURGE_PLAN.md aprobados por el operador

### Fase 1 — Inteligencia de mercado
- Censo demográfico-comercial de cada país documentado con fuentes oficiales
- Análisis de ≥20 competidores documentados (modelo, fuentes, cobertura, debilidades)
- Benchmark de ≥3 herramientas open-source candidatas por capa funcional con métricas cuantitativas
- MARKET_CENSUS, COMPETITIVE_LANDSCAPE, TOOLING_BENCHMARK aprobados

### Fase 2 — Cartografía dealer (discovery)
- 15 familias documentadas exhaustivamente con sub-técnicas
- Knowledge graph dealer construido con N entidades descubiertas (N empírico, no objetivo)
- Discovery_Saturation = TRUE por al menos 1 país (NL recomendado por verificabilidad)
- Cobertura cruzada ≥3 fuentes para ≥80% de los dealers en al menos 1 país

### Fase 3 — Pipeline de extracción E1-E12
- Cada estrategia implementada como módulo independiente
- ≥95% de dealers en knowledge graph con al menos una estrategia exitosa
- ≥80% de campos críticos extraídos por vehículo procesado
- Tests sobre dataset estratificado de muestra

### Fase 4 — Pipeline de calidad V01-V20
- 20 validadores implementados como módulos independientes
- Error_Rate < 0.5% sobre dataset de validación
- NLG_Quality_Score: BLEU ≥ T_BLEU calibrado, human eval ≥ 4/5
- Manual review queue UI funcional

### Fase 5 — Arquitectura de producción
- Sistema corriendo 7 días consecutivos sin intervención manual
- Métricas de calidad estables
- Backup automático verificado
- Runbook operacional aprobado

### Fase 6 — Rollout país por país
Por cada país activado:
- Coverage_Score ≥ 95% del knowledge graph dealer del país
- Error_Rate < 0.5% sobre vehículos publicados
- Freshness SLA cumplido durante 30 días consecutivos
- 0 incidentes legales reportados

### Fase 7 — Lanzamiento público
- Soft launch con N buyers piloto seleccionados
- NPS ≥ T_NPS calibrado
- Métricas operativas estables
- Feedback iterado e integrado

## Métricas de salud continua post-lanzamiento

- Daily Active Buyers
- Search-to-Lead conversion ratio
- Time-to-First-Result en queries del terminal
- Cross-source dedup ratio (mismo VIN en N fuentes)
- New dealers discovered per week
- Inventory turnover rate por país
- Latencia p50/p95/p99 del fan-out SSE
- Uptime del VPS

## Política de cumplimiento

Ningún hito declarado cumplido sin verificación instrumentada de su criterio. Ningún criterio modificado retroactivamente sin documento de cambio (CHANGELOG en este archivo). La disciplina cuantitativa es no negociable bajo el régimen institucional.
