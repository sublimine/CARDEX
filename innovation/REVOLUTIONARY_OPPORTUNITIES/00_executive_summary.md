# CARDEX — Wave 2: Revolutionary Opportunities
**Executive Summary · Equipo de Innovación**  
**Fecha:** 2026-04-16 · Autorización: Salman  
**Política:** R1 — cero atajos. Solo oro real. Si no pasa el filtro, no existe en este documento.

---

## Metodología de sweep

Se barrieron exhaustivamente 6 dominios: (1) amplificación de lo existente, (2) necesidades desatendidas B2B EU, (3) plays cross-sector, (4) data-as-a-service, (5) AI-native, (6) moats defendibles. 

**Descartados silenciosamente (no pasan el filtro REVOLUTIONARY/STRONG):**
- Insurance risk feed genérica → mercado indirecto, competidores con más track record
- OEM warranty analytics → exposición legal inaceptable (defamación + securities law)
- Floorplan lending (fintech embebida) → requiere licencia de crédito; regulatoriamente prohibitivo en plazo
- Stripe-for-cars → play de 10 años, no de 24 meses; múltiples licencias regulatorias por país
- Visual search foto→arbitrage → feature del terminal, no producto standalone
- Voice/chat interface → ya planeado como RAG (Innovation #3); no es nuevo
- OEM benchmarks per segment → Indicata Analytics lo vende; sin ventaja diferencial temprana
- API publica priced per call → es el producto core, no una innovación
- Predictive matching → feature del terminal premium; no standalone
- Macro dashboards para hedge funds → needs 18+ months de data; 2027 play
- VAT tool genérico → Taxdoo/Avalara existen; la diferenciación es el embedding, no la lógica (cubierto en #03)

---

## Oportunidades seleccionadas

### REVOLUTIONARY

| ID | Título | Por qué es REVOLUTIONARY |
|---|---|---|
| **01** | Fleet Disposition Intelligence (CARDEX Routes) | Nadie conecta el vehículo específico retornado + precio live cross-canal + recomendación de disposición óptima en EU. Los OEM finance arms gastan €1.500-3.500/vehículo en disposición subóptima. ARR potencial con 1 cliente grande: €2M+ |

### STRONG

| ID | Título | Por qué es STRONG |
|---|---|---|
| **02** | Dealer Health Score API (CARDEX Pulse) | Leading indicator de estrés financiero de dealer desde comportamiento de mercado. No existe pan-EU. Data propietaria inreplicable. Compradores claros (bancos, OEM credit, lessors). |
| **03** | Cross-border VAT Routing Optimizer | Embedded en punto de compra — nadie lo hace. Synergy total con VIES ya implementado. Pain point documentado (€500-3.000/vehículo en VAT mal optimizado). MVP en 8 semanas. |
| **04** | Dealer KYB + Portable Trust Score (CARDEX Trust) | Trust score portátil cross-platform, combinando identidad mercantil + VIES + comportamiento observable. Moat de datos propietarios + potencial eIDAS 2 compliant. |
| **05** | EV Battery Anomaly Signal (CARDEX EV Watch) | Timing perfecto: ola de retornos EV 2020-2022 en 2025-2027. Proxy estadístico de SoH sin medir físicamente. Abre puerta a second-life battery economy (€4B EU 2030). |

---

## Priorización por impacto × velocidad de ejecución

```
          ████████████████████████████████████
 IMPACTO  █                                  █
 ALTO     █  01 Routes    04 Trust           █
          █                                  █
          █              02 Pulse            █
 MEDIO    █  03 VAT    05 EV Watch           █
          █                                  █
          ████████████████████████████████████
               RÁPIDO          LENTO
            (≤10 semanas)  (>12 semanas)
```

**Secuenciación recomendada:**

| Orden | Producto | Semanas MVP | Razón de orden |
|---|---|---|---|
| **1º** | #03 VAT Optimizer | 8 semanas | Menor esfuerzo, mayor synergy inmediata con SPEC existente. Aumenta valor tier Pro en curso. |
| **2º** | #05 EV Watch | 7 semanas | El tiempo apremia — la ola EV ya está en curso. Bajo coste de desarrollo. |
| **3º** | #04 KYB Trust | 10 semanas | Incrementa trust + retention en el ecosistema. Build in parallel con #03/#05. |
| **4º** | #02 Dealer Pulse | 10 semanas | Requiere GNN (Innovation #1) para el componente fraud-flag. Lanzar cuando GNN esté en producción. |
| **5º** | #01 Fleet Disposition | 14 semanas | Mayor esfuerzo, mayor payoff. Requiere B2B webhook enrichment negotiations. El flagship para 2027. |

---

## Tabla de métricas consolidadas

| ID | ARR SOM 3 años | Coste desarrollo est. | Semanas MVP | Prerequisito crítico |
|---|---|---|---|---|
| **01** | ~€7.5M | ~€60.000 | 14 | B2B webhook enrichment con Arval/LeasePlan |
| **02** | ~€3M | ~€30.000 | 10 | GNN activo (Innovation #1) + 6 meses histórico |
| **03** | ~€525K | ~€15.000 | 8 | Ninguno (VIES ya existe en SPEC) |
| **04** | ~€2M | ~€22.500 | 10 | APIs registros mercantiles (5 países) |
| **05** | ~€500K | ~€12.000 | 7 | Mínimo de EVs en índice (alcanzable en 2-3 meses) |
| **TOTAL** | **~€13.5M** | **~€139.500** | — | — |

**ROI del portfolio:** €13.5M ARR potencial en 3 años contra €139.500 de inversión de desarrollo total (~97x ROI en escenario base SOM). Incluso con 20% de SOM capturado, el ROI es >19x.

---

## Interdependencias con el stack existente

```
SPEC existente          Wave 2 Innovations
──────────────          ──────────────────
VIES Validator    ──→   #03 VAT Optimizer  ──→  #01 Fleet Disposition
NLC Engine        ──→   #01 Fleet Routes   
GNN (Innovation   ──→   #02 Dealer Pulse
 #1 planning)     
EV listings +     ──→   #05 EV Watch
 price history    
Mercantile APIs   ──→   #04 KYB Trust
 (familia A DS)   
```

Todas las innovaciones Wave 2 son extensiones del stack existente, no proyectos paralelos. No hay deuda técnica nueva — son capas sobre la infraestructura ya planificada o construida.

---

## Horizonte 2 (2027+) — Señalar pero no ejecutar aún

**Pan-EU Residual Value Index (institucional):** Una vez que CARDEX acumule 12-18 meses de histórico de precios por segmento/país, tiene el activo para publicar un índice de valor residual similar al Manheim Used Vehicle Value Index (US). Los compradores: hedge funds que tradean OEM stocks, bancos con exposición a carteras de leasing, OEM finance arms calibrando sus tasas de residual guarantee. ARR potencial: €500K-2M de 30-50 suscriptores institucionales. **No iniciar hasta M12 de operaciones.**

---

## Nota final

Todos los números de ARR en este documento son SOM conservador (escenario base), no TAM. El TAM real de estas categorías combinadas supera los €100M. La disciplina es capturar el SOM antes de apuntar al TAM.

El orden de ejecución sugerido optimiza por: (1) velocidad de llegada al mercado, (2) synergy con stack existente, (3) generación de datos que alimentan los productos subsiguientes. El #01 (Fleet Disposition) es el producto de mayor upside individual — pero es el último en lanzar porque requiere las fundaciones que los otros construyen primero.
