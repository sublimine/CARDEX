# PHASE_6 — Country Rollout

## Identificador
- ID: P6, Nombre: Country Rollout — Activación secuencial NL→DE→FR→ES→BE→CH
- Estado: PENDING
- Dependencias de fases previas: P2 (DONE), P3 (DONE), P4 (DONE), P5 (DONE)
- Fecha de documentación: 2026-04-14

## Propósito y rationale

P6 activa CARDEX país por país bajo gates de calidad estrictos. Cada país solo se activa cuando cumple el estándar completo — no hay países "en beta" ni "parcialmente activos" en el índice público. La activación secuencial permite aprender de cada país antes de abordar el siguiente.

El orden de activación no es arbitrario:
1. **NL (primero)** — RDW provee denominadores VIN-level que permiten medir cobertura con precisión única; NL es el mejor laboratorio de medición
2. **DE (segundo)** — mayor mercado, mayor volumen, mayor complejidad; aprovechar lo aprendido en NL
3. **FR (tercero)** — leboncoin dominante, complejidad lingüística (NLG FR)
4. **ES (cuarto)** — mercado significativo, denominadores DGT disponibles
5. **BE (quinto)** — bilingüe FR/NL, hereda las soluciones de ambos
6. **CH (sexto)** — fuera de EU (sin E11), CHF (requiere V15), bilingüe DE/FR; más complejo

## Objetivos concretos

Para **cada país**, en orden:
1. Ejecutar discovery completo (todas las familias aplicables) hasta saturation level ≥2
2. Ejecutar extracción completa con todas las estrategias aplicables
3. Pasar todos los vehículos por el pipeline V01-V20 y NLG
4. Verificar cobertura contra denominador oficial
5. Verificar que error_rate, freshness SLA y 0 incidentes legales se cumplen durante 30 días consecutivos
6. Solo entonces activar el siguiente país

## Gate de activación por país

Un país entra en estado `ACTIVE` en el índice cuando cumple **todos** los siguientes criterios simultáneamente durante **30 días consecutivos**:

### CS-6-A: Coverage Score ≥ threshold por país

```sql
-- Coverage Score: vehículos ACTIVE / denominador oficial del país
SELECT
  country_code,
  ROUND(
    COUNT(CASE WHEN status = 'ACTIVE' THEN 1 END) * 100.0
    / (SELECT denominator_vehicles FROM market_denominator WHERE country_code = de.country_code),
    2
  ) AS coverage_pct
FROM dealer_entity de
JOIN vehicle_record vr ON de.dealer_id = vr.dealer_id
GROUP BY country_code;
```

Thresholds por país (provisionales — ajustar en P1 con denominadores reales):

| País | Coverage mínimo | Fuente denominador |
|---|---|---|
| NL | ≥40% | RDW dataset público |
| DE | ≥25% | KBA Fahrzeugzulassungen |
| FR | ≥25% | ANTS / CCFA |
| ES | ≥20% | DGT / ANFAC |
| BE | ≥20% | DIV |
| CH | ≥15% | ASTRA (mercado más cerrado) |

### CS-6-B: Error Rate <0.5% — 30 días consecutivos

```promql
# Error rate de quality pipeline por país (últimos 30 días)
sum(rate(cardex_quality_validator_fail_total{severity="BLOCKING",country="NL"}[30d]))
/ sum(rate(cardex_quality_validator_pass_total{country="NL"}[30d]))
< 0.005
```

### CS-6-C: Freshness SLA — TTL ≤72h cumplido ≥99% de listings

```sql
-- Verificar que el TTL de 72h se está renovando correctamente
SELECT
  ROUND(
    COUNT(CASE WHEN ttl_expires_at > DATETIME('now') THEN 1 END) * 100.0
    / COUNT(*), 2
  ) AS pct_fresh
FROM vehicle_record
WHERE status = 'ACTIVE'
  AND dealer_id IN (SELECT dealer_id FROM dealer_entity WHERE country_code = 'NL');
-- Resultado esperado: ≥99.0
```

### CS-6-D: 0 incidentes legales abiertos en el país

```sql
SELECT COUNT(*)
FROM legal_incident_log
WHERE country_code = 'NL'
  AND status = 'OPEN'
  AND created_at > DATETIME('now', '-30 days');
-- Resultado esperado: 0
```

### CS-6-E: 0 quejas de dealer válidas sin resolver

```sql
SELECT COUNT(*)
FROM dealer_complaint_log
WHERE country_code = 'NL'
  AND status = 'OPEN'
  AND is_valid = 1
  AND created_at > DATETIME('now', '-30 days');
-- Resultado esperado: 0
```

### CS-6-F: NLG descriptions cubren ≥95% de vehículos ACTIVE

```sql
SELECT
  ROUND(
    COUNT(CASE WHEN description_generated_ml IS NOT NULL AND description_type != '' THEN 1 END) * 100.0
    / COUNT(*), 2
  ) AS pct_with_description
FROM vehicle_record
WHERE status = 'ACTIVE'
  AND dealer_id IN (SELECT dealer_id FROM dealer_entity WHERE country_code = 'NL');
-- Resultado esperado: ≥95.0
```

## Secuencia de activación con gating

```
NL activo 30 días → verificar CS-6-A/B/C/D/E/F
    │ PASS
    ▼
Iniciar DE discovery+extraction+quality
DE activo 30 días → verificar CS-6-A/B/C/D/E/F (thresholds DE)
    │ PASS
    ▼
Iniciar FR discovery+extraction+quality
... (idem FR → ES → BE → CH)
```

**Regla de puerta:** si un país falla cualquier criterio durante su ventana de 30 días, el conteo se reinicia. No se activa el siguiente país hasta que el actual haya mantenido todos los criterios 30 días corridos sin fallo.

## Particularidades por país

### NL — País piloto
- RDW provee datos VIN-level públicos — la cobertura es la más medible
- Familia B (KvK) — cámara de comercio NL tiene API de acceso
- Idioma NLG: `nl` — LanguageTool soporte completo
- Sin particularidades E11 (EU Data Act aplica)

### DE — Mayor mercado
- KBA ofrece estadísticas de stock por marca/modelo/año — útil para V13 (price outlier calibration)
- Handelsregister.de tiene API — familia B
- Idioma NLG: `de` — mayor corpus de referencia disponible
- Volumen mayor: ajustar NATS queue depth y DuckDB OLAP size

### FR — leboncoin dominante
- leboncoin tiene robots.txt restrictivo — E07 prioritario, respetar rate limits
- INFOGREFFE (registros mercantiles FR) — acceso limitado en free tier
- Idioma NLG: `fr` — verificar calidad con nativos
- régime de la marge (V14) muy frecuente en FR

### ES — DGT denominadores
- DGT publica estadísticas de parque de vehículos por provincia
- Idioma NLG: `es` — idioma nativo del operador Salman
- IVA ES 21% (VAT mode detection V14 ajustar para convención española de precio con IVA)

### BE — Bilingüe FR/NL
- DIV (Direction pour l'Immatriculation) — denominadores BE
- NLG: `fr` o `nl` según el listing; detectar idioma del listing (V19)
- Hereda las soluciones de NL y FR en la mayoría de casos

### CH — Caso especial
- **Sin E11** (EU Data Act no aplica en Suiza)
- **CHF** — V15 obligatorio, ECB FX rate diario
- IVA CH 8.1% (estándar 2024) — vatRates map actualizado
- Familia M (VIES) no aplica (CH no es EU) — usar UID-Register.ch para VAT-equivalent
- Idioma NLG: `de` (Deutsch suizo, con variaciones)

## Métricas de progreso intra-fase

| Métrica | Expresión | Objetivo |
|---|---|---|
| Países ACTIVE | `SELECT COUNT(DISTINCT country_code) FROM dealer_entity WHERE country_code IN (...) AND status='ACTIVE'` | Aumenta 1-a-1 secuencialmente |
| Coverage por país | CS-6-A | ≥threshold por país |
| Error rate por país | CS-6-B | <0.5% |
| Freshness SLA por país | CS-6-C | ≥99% |
| Incidentes legales abiertos | CS-6-D | 0 por país activo |
| Descripciones NLG | CS-6-F | ≥95% por país |

## Dependencias externas

- P2, P3, P4, P5 todos DONE
- Denominadores oficiales de cada país (de P1)
- ECB FX feed operativo (para CH)
- UID-Register.ch accesible (para CH)

## Riesgos específicos de la fase

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Plataforma nacional cambia robots.txt o estructura mid-rollout (ej. leboncoin FR) | MEDIA | ALTA | Monitor de cambios en robots.txt y en estructura HTML (hash de page structure); alertar y adaptar |
| Incidente legal en un país activo (cease and desist de plataforma) | BAJA | ALTA | Protocolo de respuesta en 48h documentado en runbook; robots.txt compliance es primera línea de defensa |
| CH es más difícil de lo esperado sin E11 (pocos dealers indexables via E01-E10) | MEDIA | MEDIA | Threshold CH más bajo (15%); E12 manual más activo; considerar ampliar E11 si CH cambia su posición legal respecto al EU Data Act |
| VPS S0 insuficiente cuando llegan 4-5 países simultáneamente | BAJA | MEDIA | Trigger automático de evaluación de escala S1 cuando RAM >75% 7 días; P6 puede forzar migración a S1 |
| Dealer activo en múltiples países (dealer importador cross-border) | BAJA | BAJA | Knowledge graph maneja `country_code` por dealer_location, no por dealer_entity — un dealer puede tener listings en múltiples países |

## Retrospectiva esperada (al activar cada país)

Para cada país al cerrar su gate:
- ¿Qué coverage real se obtuvo vs threshold? ¿El denominador oficial era preciso?
- ¿Qué estrategias de extracción fueron dominantes? ¿Cambió respecto a NL?
- ¿Hubo incidentes legales durante el período de gate? ¿Se resolvieron correctamente?
- ¿El NLG produce descripciones de calidad comparable a NL? ¿Algún idioma es más problemático?
- ¿Qué se aprendió de este país que hay que incorporar al siguiente?
