# Cross-Fertilización entre familias de discovery

## Identificador
- Documento: CROSS_FERTILIZATION
- Versión: 1.0
- Fecha: 2026-04-14
- Estado: AUTORITATIVO

## Propósito
Documentar cómo las 15 familias se cruzan para construir el knowledge graph, cómo se resuelve la deduplicación entidad, cómo se calcula el `confidence_score`, y cómo se identifican gaps para iteración hacia exhaustividad.

## Matriz de cross-validation esperada

> **Hipótesis de diseño.** Todos los valores numéricos de esta matriz son estimaciones basadas en razonamiento estructural sobre las fuentes de cada familia. **No son datos empíricos.** Los valores reales se medirán en la primera ejecución completa de discovery y esta matriz se actualizará. Los rangos pueden variar ±30pp respecto a las hipótesis.

| | A | B | C | D | E | F | G | H | I | J | K | L | M | N | O |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **A** | — | 60 | 50 | — | — | 30 | 80 | 25 | 40 | 70 | 40 | 70 | base | bajo | 60 |
| **B** | 60 | — | 70 | — | — | 50 | 40 | 90 | 60 | 80 | 50 | 80 | — | 30 | — |
| **C** | 50 | 70 | — | 80 | 60 | 70 | 30 | 40 | — | — | 60 | 60 | — | 50 | — |
| **D** | — | — | 80 | — | 30 | — | — | — | — | — | — | — | — | — | — |
| **E** | — | — | 60 | 30 | — | 40 | — | — | — | — | — | — | — | 60 | — |
| **F** | 30 | 50 | 70 | — | 40 | — | 60 | 70 | — | — | 30 | — | — | — | — |
| **G** | 80 | 40 | 30 | — | — | 60 | — | 50 | 30 | 30 | — | 40 | — | — | 30 |
| **H** | 25 | 90 | 40 | — | — | 70 | 50 | — | — | — | — | — | — | — | — |
| **I** | 40 | 60 | — | — | — | — | 30 | — | — | — | — | — | — | — | — |
| **J** | 70 | 80 | — | — | — | — | 30 | — | — | — | 20 | — | — | — | — |
| **K** | 40 | 50 | 60 | — | — | 30 | — | — | — | 20 | — | — | — | — | — |
| **L** | 70 | 80 | 60 | — | — | — | 40 | — | — | — | — | — | — | — | — |
| **M** | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| **N** | bajo | 30 | 50 | — | 60 | — | — | — | — | — | — | — | — | — | — |
| **O** | 60 | — | — | — | — | — | 30 | — | — | — | — | — | — | — | — |

Los valores son porcentajes de overlap hipotéticos (basados en análisis estructural de cada familia). "—" indica ortogonalidad relativa sin overlap significativo esperado. Los valores reales se medirán empíricamente y la matriz se actualizará.

**Interpretación clave:**
- Alto overlap entre (A,G) y (B,H) es esperado y saludable (asociación = registrada, OEM = georreferenciada).
- Bajo overlap de N con A es característica: N aporta dimension infra ortogonal.
- M aparece como fila/columna vacía porque M no es discovery primario sino enrichment.

## Función de confidence_score

```
confidence_score(dealer_entity) = min(1.0,
    sum over discovery_record dr:
        base_weight(dr.family) × recency_factor(dr.last_reconfirmed_at)
) × consistency_multiplier(dealer_entity)
```

Donde:
- `base_weight(family)` es el peso intrínseco por familia, **hipótesis de calibración inicial** — estos valores se ajustarán en la primera ejecución real según la calidad observada de cada fuente:
  - A (registros legales): 0.35 (máxima autoridad — hipótesis: fuente legal directa sin intermediario)
  - B (geo): 0.15 (hipótesis)
  - C (web cartography): 0.10 (hipótesis)
  - D: 0.00 (no es discovery primario)
  - E (DMS hosted): 0.10 (hipótesis)
  - F (aggregators): 0.20 (hipótesis)
  - G (asociaciones): 0.20 (hipótesis)
  - H (OEM): 0.25 (hipótesis)
  - I (inspección): 0.05 (hipótesis)
  - J (sub-jurisdicciones): 0.10 (hipótesis)
  - K (buscadores alt): 0.05 (hipótesis)
  - L (social): 0.10 (hipótesis)
  - M: modifier (0.0-1.0 multiplicativo vía consistency_multiplier)
  - N (infra): 0.05 (hipótesis)
  - O (prensa): 0.05 (hipótesis)

Suma de weights máxima teórica = 1.75. min(1.0, ...) truncates.

- `recency_factor` decae exponencialmente: reciente (1.0), hace 1 mes (0.9), 3 meses (0.7), 6 meses (0.5), >12 meses (0.3). **Hipótesis de diseño** — curva a calibrar con tasa de cambio real observada en prime data sources (Sirene, KBO, BORME).

- `consistency_multiplier` es producto de (hipótesis de diseño):
  - M operational signal: `vat_active ? 1.0 : 0.5`
  - No insolvency flagged: `insolvency_detected ? 0.2 : 1.0`
  - Nombre consistente cross-familia: `0.9-1.1`
  - Ubicación consistente cross-familia: `0.9-1.1`

**Thresholds** (hipótesis de diseño — a validar con precision/recall real):
- `confidence_score < 0.30` → UNVERIFIED, no se activa catalog extraction
- `0.30 ≤ confidence_score < 0.60` → LOW_CONFIDENCE, manual review recomendada
- `0.60 ≤ confidence_score < 0.85` → MEDIUM_CONFIDENCE, extraction activa con flag
- `confidence_score ≥ 0.85` → HIGH_CONFIDENCE, extraction plena sin flag

## Deduplicación entre familias

### Pipeline de dedup

1. **Primary key matching:** si dos discovery_records de familias distintas comparten identifier (VAT, SIRET, KvK, etc.) → mismo dealer_id, merge.

2. **Normalized name + geo proximity matching:**
   - `normalized_name` idéntica + ubicación dentro de <500m → match candidate (confirmar con otro signal).
   - `normalized_name` similar (Levenshtein <3) + ubicación dentro <100m + misma ciudad → match probable.

3. **Website matching:** dos dealers con el mismo domain → merge si el domain no es hosting compartido.

4. **Phone matching:** mismo teléfono → merge candidate (confirmar con nombre o dirección).

5. **Social profile matching:** mismo Google Maps Place-ID → merge.

6. **Conflict resolution:** si dos discovery_records disputan campos incompatibles (ej. fundación year diferente), se conserva el de familia con base_weight mayor + última confirmación reciente. Conflicto se logea en `dealer_audit_log`.

### Splitting (caso inverso)

A veces lo que aparenta ser un dealer único son dos operadores diferentes compartiendo espacio (ej. vehículos + repuestos en misma dirección, pero empresas legales distintas). Regla: **si dos VAT distintos, dos dealer_entity distintos, aunque compartan dirección.** El legal VAT es discriminador de última instancia.

## Detección de gaps para iteración (R4)

### Métricas de gap

1. **Families-with-unique-dominance:** una familia que tiene alta `unique_discovery_rate` implica que captura un segmento no cubierto por las demás. Conservar y expandir.

2. **Zero-overlap pairs:** familia X con overlap 0% contra todas las demás → posible ortogonalidad valiosa, expandir.

3. **Sub-region undercovered:** análisis geo del knowledge graph. Si región K tiene 10x menos dealers per capita que región similar → gap de discovery, buscar vector nuevo específico a K.

4. **NACE-code undercovered:** si código NACE específico tiene baja representación, buscar fuentes específicas a ese código.

5. **Long-tail dealer characteristics:** análisis de dealers descubiertos solo por familia K (buscadores) y nunca por F (aggregators) → perfilar esos y buscar fuentes capturando ese perfil antes.

### Ciclo de iteración

```
[ejecutar las N familias activas]
         ↓
[calcular métricas por familia + gap analysis]
         ↓
[identificar huecos cualitativos: ¿qué tipo de dealer queda?]
         ↓
[diseñar vector nuevo específico + integrarlo como sub-técnica]
         ↓
[re-ejecutar las N+1 familias, comparar delta]
         ↓
[si delta>0, repetir; si delta=0 durante T tiempo × 3 ciclos → saturación declarada]
```

## Auditabilidad y reproducibilidad

Cada `discovery_record` tiene `source_url`, `source_record_id`, `last_reconfirmed_at`. Esto permite reproducir cualquier discovery posteriormente, auditar si la fuente sigue válida, y detectar sources rotas/obsoletas.

`dealer_audit_log` registra cambios estructurales (merge, split, status change, confidence recalc) con timestamp y razón. Base para compliance + debug.

## Evolución temporal del graph

El knowledge graph NO es estático. Cambia continuamente con:
- Altas (nuevos dealers)
- Bajas (cierres detectados por M/O)
- Merges (dealers que convergen — cadena compra independiente)
- Splits (dealers que divergen — management buyout)
- Enrichments (campos complementados con nuevas fuentes)

Snapshots mensuales del graph en parquet comprimido → base temporal para análisis longitudinal.
