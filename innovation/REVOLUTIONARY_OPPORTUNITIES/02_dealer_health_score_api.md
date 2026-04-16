# 02 — Dealer Health Score API
**Veredicto:** STRONG  
**Dominio:** Amplificación de lo existente (grafo de dealers)  
**Fecha:** 2026-04-16 · Autorización: Salman

---

## Título
**CARDEX Pulse:** API de salud comercial de dealers B2B europeos derivada de comportamiento de mercado observable — el primer indicador adelantado de estrés financiero de concesionario que existe en EU, basado en datos de inventario live en lugar de estados financieros retrospectivos.

---

## Tesis

Un dealer que empieza a tener problemas de cash flow hace cosas observables antes de que aparezcan en sus cuentas anuales: baja sus precios por debajo del mercado, aumenta su volumen de venta (liquida stock), sus vehículos llevan más días en mercado (no consigue vender), o al contrario empuja volúmenes anormalmente grandes en subastas (necesita liquidez urgente). Estas señales están en los datos CARDEX, extraíbles a partir de 3-6 meses de historia por dealer.

Las financieras que hacen floorplan lending a dealers (BNP Paribas, Santander, BNP Lease), los lessors que firman contratos de suministro con dealers, y los OEM finance arms que extienden crédito de inventario necesitan esta señal desesperadamente. Hoy usan informes anuales de cuentas (6-18 meses de retraso) y visitas presenciales. Un feed de comportamiento de mercado en tiempo real es 6-18 meses más temprano que cualquier otra señal disponible.

---

## Evidencia de demanda

- **BNP Paribas Leasing Solutions:** Arval (BNP) tiene créditos de floorplan expuestos a ~20.000 dealers en EU. Pérdidas por default de dealer en sus carteras: no publicado, pero la industria estima 0.3-0.8% de la cartera anual en defaults. Sobre una cartera de €10B en EU, eso son €30-80M en pérdidas anuales. Una señal de early warning que reduzca defaults en un 20% valdría €6-16M/año en ahorros para BNP.
- **Banco Santander Auto Finance:** hace underwriting de crédito a dealers para inventario en ES/DE/FR. Sus comités de riesgo actualizan los límites de crédito trimestralmente. Un sistema que actualice el risk score mensualmente o semanalmente es un diferencial claro.
- **OEM credit departments:** VW Financial Services, BMW Bank, etc. tienen sus propios equipos de riesgo de dealer, pero sin acceso a datos de comportamiento de mercado cross-platform.
- **Caso análogo:** En el sector de e-commerce, la startup Hokodo (Londres, £30M raised en 2023) vende "B2B credit scoring en tiempo real basado en comportamiento de negocio observable". Hokodo aplica esta lógica a SMBs en general. CARDEX puede hacer lo mismo pero con una vertical específica (dealers) y datos propietarios que Hokodo no tiene.

---

## Competencia actual

| Competidor | Qué hace | Por qué no resuelve el problema |
|---|---|---|
| **D&B / Moody's / Bureau van Dijk** | Credit scores basados en cuentas anuales | Retrospectivo 6-18 meses. Sin datos de comportamiento de mercado |
| **Creditreform (DE/EU)** | Credit scoring SMB EU | Mismo problema — sin datos de inventario/mercado |
| **Hokodo** | B2B trade credit en tiempo real | No tiene datos de inventario vehicular; foco en e-commerce B2B genérico |
| **Indicata Analytics** | Dealer performance analytics | Vende a dealers para que se auto-evalúen, no a financieras para que evalúen dealers. Sin score de riesgo |

**Nadie tiene el scoring de salud de dealer desde comportamiento de mercado de inventario.** El gap es real.

---

## Lo que hace falta construir

### Señales de la data CARDEX para el health score

| Señal observable | Indicador de qué |
|---|---|
| Variación de volumen de listings semana sobre semana (>30% aumento repentino) | Liquidación de stock urgente → estrés de liquidez |
| Precio medio de listings del dealer vs. mediana de mercado comparable (descuento creciente) | Presión de venta → necesita cash |
| Tiempo-en-mercado promedio del dealer vs. mercado (aumento sostenido >15%) | Stock no se mueve → demanda débil o precios fuera de mercado |
| Concentración de modelos (dealer empieza a vender marcas que no vende habitualmente) | Comprando oportunísticamente o cambiando de nicho → inestabilidad |
| Desaparición repentina de listings sin transacciones visibles | Posible cierre o transferencia de stock en bloque |
| VIN recycling: mismo VIN reaparece en múltiples momentos → dealer actúa como agente sin stock propio | Modelo de negocio frágil (sin inventario propio = sin colateral) |

### Stack técnico
```
dealer_health/
├── signal_extractor.go     # Computa las 6 señales semanalmente por dealer
├── score_model.py          # Composite score [0-100]: weighted combination de señales
│                           # Con lookback window configurable (4-12 semanas)
├── anomaly_detector.go     # Alertas cuando score cae >20 puntos en 2 semanas
├── health_api.go           # REST API: GET /dealers/{dealer_id}/health → {score, signals, trend, alert_level}
├── portfolio_api.go        # GET /portfolio/health?portfolio_id=X → resumen de cartera de dealers
└── webhook_alerts.go       # Push webhook a cliente cuando dealer en cartera entra en zona de riesgo
```

**Estimación de desarrollo:** 6-8 semanas con 1 ingeniero backend + 1 data scientist.

**Prerequisito:** 3-6 meses de historia de listings por dealer para calibrar las señales. Con el lanzamiento de la plataforma de ingesta, la historia empieza a acumularse desde el día 1. El producto se activa cuando hay suficiente histórico.

---

## Monetización

### Modelo: API por dealer monitorizado + alertas premium

| Tier | Descripción | Precio |
|---|---|---|
| **Screening** | Score puntual por dealer, sin historial ni alertas | €0.50/consulta |
| **Monitor** | Score continuo + alertas push para cartera de dealers | €15-30/dealer/mes |
| **Portfolio** | Hasta 500 dealers monitorizados + dashboard de cartera + API integración | €3.000-8.000/mes |
| **Enterprise** | Integración en sistema de riesgo interno (core banking, sistema de crédito) | €20.000-50.000/año |

### ARPU estimado

Un banco con cartera de 500 dealers en el mercado CARDEX (DE/FR/ES/NL):
- Tier Portfolio: €5.000/mes = €60.000 ARR por cliente banco.
- Si CARDEX tiene 20 clientes institucionales (financieras, OEM credit, insurance): €1.2M ARR.

Un OEM credit department (VW Financial, BMW Bank) con 5.000 dealers en cartera en 6 países:
- Tier Enterprise integrado: €40.000/año = €40K ARR.
- Si 10 OEM finance arms: €400K ARR adicional.

**TAM/SAM/SOM:**

| | Valor |
|---|---|
| **TAM** | ~200.000 dealers B2B EU con algún tipo de financiación activa × €100-200/año scoring = €20-40M ARR |
| **SAM** | Dealers en 6 países CARDEX con relación con financieras accesibles | ~€8-15M ARR |
| **SOM (3 años)** | 30 clientes institucionales × €100.000 ARR medio | **~€3M ARR** |

---

## Moat post-lanzamiento

1. **Datos propietarios de comportamiento:** ninguna agencia de crédito tiene datos de comportamiento de inventario de dealer en tiempo real. CARDEX los genera de forma natural como subproducto del indexado.

2. **Validación empírica con el tiempo:** cada default de dealer en la cartera de un cliente que CARDEX alertó con 3 meses de antelación es una referencia de ventas que multiplica. El track record construye el moat.

3. **Efecto red con el portfolio del cliente:** cuanto más dealers monitoriza un cliente, más granular el benchmark de mercado que permite calibrar los scores. Los clientes más grandes obtienen mejores scores — incentivo para ampliar el portfolio en CARDEX.

---

## Tiempo a MVP y coste

| Hito | Semanas |
|---|---|
| Signal extraction engine (6 señales) | 1-3 |
| Score model v1 (composite, no ML) | 3-5 |
| REST API + webhook alerts | 5-7 |
| Piloto con 1 cliente institucional (1 cartera de 100 dealers) | 7-10 |
| **MVP a cliente piloto** | **10 semanas** |

**Coste:** 1 ingeniero + 1 data scientist × 2.5 meses = ~€30.000.

---

## Riesgos principales

| Riesgo | Probabilidad | Severidad | Mitigación |
|---|---|---|---|
| El score no predice defaults mejor que el crédito tradicional (sin valor añadido) | MEDIA | ALTA | Backtesting contra defaults históricos conocidos en los 6 países antes de comercializar. Si el lift sobre credit scores convencionales es <15%, KILL. |
| Dealer impugna un score bajo como difamatorio | BAJA | MEDIA | El score es "internal use only" para el cliente financiero. No se publica al dealer ni a terceros. Estructura idéntica a los credit bureaus. |
| GDPR: los datos de comportamiento de una empresa (dealer) son datos corporativos, no personales — sin restricción GDPR para personas jurídicas | BAJA | BAJA | Verificar con asesoría legal: si el dealer es autónomo (persona física), sus datos de negocio pueden ser personales. Mitigación: score solo para personas jurídicas (S.A., S.R.L., GmbH, BV, SARL, etc.) |
| Cobertura insuficiente de dealers pequeños (long-tail) para el score | MEDIA | MEDIA | El cliente financiero entiende que el score requiere un mínimo de listings históricos. Dealers sin suficiente historia reciben "insufficient data" flag — honesto y operacionalmente útil. |

**Kill criteria:**
- Precision en detección de estrés financiero <60% en backtest contra datos históricos de defaults conocidos: revisitar señales o KILL.
- Ningún cliente institucional acepta piloto en 4 meses: mercado incorrecto o go-to-market incorrecto.
