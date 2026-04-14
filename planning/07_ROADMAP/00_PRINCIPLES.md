# 00 — Principios del Roadmap

## Identificador
- Fecha: 2026-04-14, Estado: DOCUMENTADO

---

## Principio 1: Sin fechas absolutas — solo criterios cuantitativos

Este roadmap no contiene fechas de entrega, sprints con nombres de semanas ni "Q3 2026". Las estimaciones temporales en software son sistemáticamente incorrectas y crean presión artificial que degrada la calidad. En su lugar, cada fase define **criterios cuantitativos de salida** — condiciones medibles que, cuando se cumplen, declaran la fase cerrada.

**Criterio válido:**
> `SELECT COUNT(*) FROM dealer_entity WHERE status='ACTIVE' AND country='NL'` ≥ 85% del denominador oficial RDW

**Criterio inválido:**
> "Discovery completo en NL para el 15 de mayo"

La duración real de cada fase emergirá de la ejecución, no de la estimación. Se registra *a posteriori* en la retrospectiva como dato histórico para calibrar estimaciones futuras.

---

## Principio 2: Criterio medible instrumentalmente

Todo criterio de salida debe ser verificable con una de estas dos herramientas:

1. **Query SQL sobre SQLite/DuckDB** — para estados del knowledge graph, índice de vehículos, quality pipeline
2. **PromQL sobre Prometheus** — para métricas operativas de servicios en ejecución

Si un criterio no puede expresarse en SQL o PromQL, no es un criterio de salida — es una intención. Debe reescribirse hasta ser instrumentable.

**Ejemplos de expresión instrumental:**

```sql
-- Criterio P2: cobertura cruzada ≥3 fuentes para ≥80% dealers en NL
SELECT
  COUNT(CASE WHEN source_count >= 3 THEN 1 END) * 1.0 / COUNT(*) AS coverage_ratio
FROM (
  SELECT dealer_id, COUNT(DISTINCT family_id) AS source_count
  FROM discovery_record
  WHERE country_code = 'NL'
  GROUP BY dealer_id
)
WHERE coverage_ratio >= 0.80;
```

```promql
# Criterio P5: uptime >99% en 7 días consecutivos
avg_over_time(up{job="cardex-api"}[7d]) >= 0.99
```

---

## Principio 3: Política de "no avanzar sin cerrar"

La fase N+1 no arranca hasta que la fase N haya cumplido **todos** sus criterios cuantitativos de salida y completado su retrospectiva formal.

Excepción documentada: cuando la tabla de dependencias (DEPENDENCIES_GRAPH.md) indica que dos fases son paralelizables, pueden ejecutarse simultáneamente. Pero una fase que depende de otra no puede arrancar hasta que esa dependencia esté en estado `DONE`.

**Antipatrón a evitar:** iniciar una fase nueva con "el 90% de la anterior está hecho". El 10% restante es invariablemente el más difícil y el que contiene los problemas más relevantes. Completar la fase es obligatorio antes de avanzar.

---

## Principio 4: Política de regresión

Si una métrica de una fase `DONE` cae por debajo de su threshold después del cierre, la fase se reabre automáticamente al estado `REGRESSED` y tiene prioridad sobre cualquier otra fase en curso.

**Trigger de regresión:**

```sql
-- Si este query retorna FALSE para una fase DONE, se regresa
SELECT
  CASE
    WHEN metric_value >= threshold THEN 'STABLE'
    ELSE 'REGRESSED'
  END AS phase_health
FROM phase_health_metrics
WHERE phase_id = 'P2' AND metric_id = 'coverage_nl';
```

La regresión no es un fracaso — es el sistema funcionando correctamente. El knowledge graph se degrada si un proveedor de datos cambia su estructura, si un dealer cierra, si un recurso externo desaparece. La regresión detecta esto y fuerza una respuesta activa.

---

## Principio 5: Retrospectiva formal al cierre de fase

Al cerrar una fase (todos los criterios cumplidos), se realiza una retrospectiva con estructura fija:

```markdown
## Retrospectiva — Fase [N]: [nombre]
**Fecha de cierre:** YYYY-MM-DD
**Duración real:** X semanas/meses desde inicio

### Qué funcionó
- [lista de decisiones técnicas que se validaron]

### Qué no funcionó
- [lista de suposiciones incorrectas o caminos descartados]

### Ajustes a criterios de fases futuras
- [si los criterios de fases siguientes deben ajustarse en base a lo aprendido]

### Métricas finales verificadas
- [tabla con todos los criterios de salida y sus valores reales al cierre]
```

La retrospectiva se guarda en el archivo de la fase correspondiente, añadida al final.

---

## Principio 6: Calidad sobre velocidad

CARDEX es un proyecto institucional, no un hackathon. El ritmo correcto es aquel que produce trabajo correcto la primera vez, no trabajo rápido que requiere reescritura. Los incentivos del sistema apuntan a:

- Implementar un validator correctamente > implementar cuatro validators con bugs
- Verificar la cobertura legal de una estrategia antes de implementarla > refactorizar después
- Leer y entender el código existente antes de modificarlo > sobreescribir sin entender

**No hay puntos por velocidad.** Hay puntos por criterios cuantitativos cumplidos.

---

## Principio 7: Planificación adaptativa

Los criterios de salida de fases que están a más de 2 fases de distancia son provisionales. Al llegar a esas fases, los criterios se revisan en base a lo aprendido. Esta revisión debe ser documentada y justificada — no es un mecanismo para relajar estándares, sino para ajustar expectativas cuantitativas a la realidad empírica observada.

**Por ejemplo:** el threshold de BLEU para NLG (PHASE_4) se define provisionalmente como "≥T_BLEU calibrado". El valor real de T_BLEU se determinará cuando se tenga un corpus de referencia de evaluación humana — no antes.

---

## Apéndice: plantilla de criterio de salida

```markdown
### Criterio CS-[N]-[M]: [nombre descriptivo]

**Tipo:** SQL | PromQL | Manual (último recurso)
**Frecuencia de evaluación:** continua | diaria | semanal
**Expresión:**
```sql
-- query exacto que debe retornar TRUE o un valor ≥ threshold
```
**Threshold:** [valor mínimo aceptable]
**Fuente de verdad:** [SQLite main.db | DuckDB olap | Prometheus | manual audit]
**Responsable de verificación:** operador (Salman)
```
