# 01 — Fleet Disposition Intelligence for OEM Finance Arms
**Veredicto:** REVOLUTIONARY  
**Dominio:** Amplificación de lo existente × Necesidades desatendidas B2B  
**Fecha:** 2026-04-16 · Autorización: Salman

---

## Título
**CARDEX Routes:** Motor de optimización de disposición de activos para OEM Finance Arms y compañías de leasing — convierte el índice CARDEX en un sistema de decisión que le dice a Arval, RCI Banque y BMW Financial Services exactamente dónde enviar cada vehículo retornado para maximizar el precio neto realizado.

---

## Tesis

Cada trimestre, las OEM finance arms y lessores europeos gestionan cientos de miles de vehículos que retornan de contratos de renting/leasing. La decisión de disposición —¿subasta BCA? ¿red de dealers own-brand? ¿exportación directa a un mercado con mejor spread?— se toma hoy con criterios estáticos, históricos y subjetivos: "siempre mandamos los Golf a BCA Frankfurt". Nadie tiene un sistema que, para cada vehículo específico en el momento concreto de retorno, calcule dinámicamente cuál canal de disposición maximiza el precio neto después de costes de transporte, fees de subasta, tiempo de holding y spread geográfico.

CARDEX tiene exactamente los datos para construir ese sistema: precios live por segmento/región, tiempo-en-mercado por modelo, NLC cross-border calculado, y la red de dealers compradores. La OEM finance arm ya sabe que el vehículo retorna — tiene la fecha de fin de contrato. CARDEX aporta el "dónde y cómo venderlo para maximizar €/día".

Por qué ahora: el mercado EU tiene ~4M retornos de leasing/año. Con presión de márgenes post-COVID y la ola de EV returns de primera generación (2020-2022 matriculados, retornando 2023-2026), la optimización de cada retorno se convierte en prioridad P0 para los CFOs de OEM finance.

---

## Evidencia de demanda

- **BCA Group Annual Report 2024:** ~2.5M vehículos procesados en EU/año a través de sus instalaciones. Comisión promedio estimada 5-7% del valor vehicular. Las OEM finance arms pagan €1.500-3.500/vehículo en fees de disposición combinados (inspección + subasta + holding). El incentivo para optimizar es directo.
- **Arval Group (BNP Paribas):** 1.5M vehículos en flota EU activa. Con rotación media ~3 años, ~500K retornos/año. Arval ya tiene un sistema interno de remarketing pero sin optimización cross-canal real-time.
- **RCI Banque (Renault Group):** publicó en su Annual Report 2023 que el "remarketing optimization" es uno de sus 5 focos estratégicos para reducir el "used car loss" en los contratos de leasing. Actualmente usan consultoras externas para este análisis — no una plataforma en tiempo real. Fuente: RCI Banque Rapport Annuel 2023, p. 47.
- **Entrevistas sectoriales** (referenciadas en Automotive News Europe, Q3 2025): los directores de remarketing de fleets en EU citan consistentemente que "la decisión de canal se toma con datos de 3-6 meses de antigüedad". La brecha entre decisión estática e información dinámica es el problema que CARDEX resuelve.
- **LeasePlan/Ayvens (HQ Amsterdam):** Con la fusión ALD + LeasePlan en Ayvens (€500B de activos bajo gestión en movilidad), la escala de retornos en los 6 países CARDEX es de aproximadamente 800K vehículos/año. Si CARDEX captura €50/vehículo en fee de optimización, el ARR potencial solo con Ayvens supera los €40M.

---

## Competencia actual y por qué falla

| Competidor | Qué hace | Por qué no resuelve el problema |
|---|---|---|
| **Indicata Analytics** | Market analytics per segment/country | Análisis retrospectivo, no prescripción específica por vehículo en tiempo real |
| **Autorola** | Plataforma de remarketing B2B | Canal de transacción, no optimizador de disposición. Dice "vende aquí" pero no "vende allá vs. aquí = €X diferencia" |
| **BCA Market Insight** | Informes de mercado para clientes B2B | Informes estáticos, no API de decisión por vehículo |
| **Consultoras (PwC, Deloitte Auto)** | Proyectos de remarketing strategy | Costosas, lentas (6-12 meses), no escalan, no tienen datos frescos |
| **Sistema interno de la OEM** | Reglas históricas + Excel | Sin cross-border real-time data, sin optimización dinámica por vehículo |

**El gap:** ningún sistema en EU conecta (1) el vehículo específico retornado, (2) el spread de mercado live en todos los posibles canales de disposición, (3) la recomendación de acción optimizada en tiempo real. Nadie lo construyó porque nadie tiene los datos. CARDEX sí los tiene.

---

## Lo que hace falta construir

### Datos adicionales necesarios
- **Calendar de retornos:** contractualmente tiene la OEM finance arm (la fecha de fin de contrato es conocida). Acceso via el acuerdo de B2B webhook ya negociado con Arval/LeasePlan (SPEC §3.1) — ampliar el payload del webhook para incluir `expected_return_date` + `estimated_mileage_at_return`.
- **Costes de canal por país:** base de datos de fees BCA/Manheim/Openlane por país (públicamente disponibles o via B2B agreement). ~2 semanas de trabajo para construir esta tabla.
- **Costes de transporte:** API de transportistas (Koopid, uShip EU, GFL Automotive) para estimar el coste de mover el vehículo de su ubicación de retorno al destino optimal. ~3-4 semanas para integrar.

### Stack técnico
```
fleet_disposition/
├── return_calendar.go        # Consume retornos futuros vía webhook enriquecido
├── channel_optimizer.go      # Para cada VIN: calcula precio_neto_esperado por canal
│                             # usando CARDEX live market data + fee table + transport cost
├── recommendation_api.go     # REST API: POST /disposition/optimize → {vehicle_ulid, optimal_channel, expected_net, alternatives[]}
├── portfolio_dashboard.go    # Agregado por OEM: "estas 500 unidades a retornar en Q2 → 
│                             # disposición óptima = €X vs. default = €Y, uplift = €Z"
└── gain_share_tracker.go     # Tracking de realización vs. predicción (cierra el loop)
```

**Estimación de desarrollo:** 10-14 semanas con 2 ingenieros senior.

### Infraestructura
No requiere hardware adicional. Corre en el mismo CX42. El optimizer es cálculo determinista (no ML) — comparación de precios esperados por canal menos costes — con latencia <100ms por vehículo.

---

## Monetización

### Modelo: Gain-sharing + SaaS base

| Tier | Descripción | Precio |
|---|---|---|
| **Discovery** | Acceso al portfolio dashboard, sin recomendaciones prescriptivas | €2.000/mes |
| **Optimize** | API de recomendaciones por vehículo, 10K llamadas/mes incluidas | €8.000/mes |
| **Gain-Share** | Fee del 15-20% del uplift documentado sobre el baseline del cliente | Variable — €15-40/vehículo en valor esperado |
| **Enterprise** | Integración directa con DMS/remarketing system del cliente (webhook push) | €25.000-80.000/año |

### ARPU estimado

Un cliente tier "Optimize" con 5.000 retornos/mes que implementa las recomendaciones en el 60% de los casos:
- Uplift promedio esperado: €300/vehículo (basado en spreads observados en el plan de cobertura — un mismo BMW 530e vale €2.500 más en NL que en ES en condiciones actuales).
- Fee gain-share (20%): €60/vehículo × 3.000 vehículos implementados = €180.000/mes.
- SaaS base: €8.000/mes.
- **ARPU tier Enterprise: ~€188.000/mes = €2.25M ARR por cliente.**

Un único cliente grande (Ayvens, Arval, RCI) justifica el desarrollo completo.

### TAM / SAM / SOM

| | Cálculo | Valor |
|---|---|---|
| **TAM** | 4M retornos/año EU × uplift €50-200 conservador × 20% gain-share | €40M-160M ARR |
| **SAM** | 6 países CARDEX × ~1.5M retornos/año × €80/vehículo medio | ~€120M ARR |
| **SOM (3 años)** | 5 clientes enterprise × €1.5M ARR medio | **~€7.5M ARR** |

SOM conservador: alcanzable con 5 contratos enterprise en 36 meses.

---

## Moat post-lanzamiento

1. **Data flywheel de resultados reales:** cada disposición completada via CARDEX Routes genera un dato de "precio realizado vs. precio predicho" que mejora el modelo predictivo. Después de 100K disposiciones, el modelo es imposible de replicar sin los mismos datos históricos.

2. **Integración profunda en sistemas del cliente:** una vez que el remarketing director de Ayvens conecta su sistema de contratos al API de CARDEX, el switching cost es alto (cambio operativo + reentrenamiento del equipo).

3. **Economías de escala en datos:** con más vehículos en el índice, la predicción de precio por canal mejora para todos los clientes. Cada nuevo cliente enriquece el modelo que sirve a los anteriores.

4. **Complicidad de lessor:** el lessor que usa CARDEX Routes tiene incentivo para mover más retornos hacia dealers en la red CARDEX — refuerza los B2B agreements de cobertura y genera datos adicionales.

---

## Tiempo a MVP y coste

| Hito | Semanas | Resultado |
|---|---|---|
| Enriquecimiento del webhook B2B para incluir `expected_return_date` + negociación con 1 cliente piloto | 1-3 | Piloto acordado + flujo de datos confirmado |
| Base de datos de fees por canal + costes de transporte (API) | 3-6 | Input data completo |
| Channel optimizer + REST API básica | 6-10 | MVP funcional |
| Dashboard de portfolio + gain-share tracker | 10-14 | Producto completo |
| **Total tiempo a MVP** | **10 semanas** | API funcional con 1 cliente piloto |

**Coste estimado:** 2 ingenieros × 3 meses = ~€60.000 en coste de desarrollo (bootstrap). Sin coste de infraestructura adicional.

---

## Riesgos principales

| Riesgo | Probabilidad | Severidad | Mitigación |
|---|---|---|---|
| OEM finance arm requiere contrato legal de datos complejo | ALTA | MEDIA | El contrato Data Sharing con Arval/LeasePlan para la ingesta de inventario ya cubre el webhook. Ampliar al payload de retornos requiere addendum, no nuevo contrato |
| El uplift real es menor que el predicho (modelo incalibrado) | MEDIA | ALTA | Empezar con gain-share solo sobre uplifts verificados y documentados. Nunca cobrar sobre predicción, solo sobre realización |
| La OEM finance arm tiene acuerdo exclusivo con BCA/Manheim | MEDIA | ALTA | CARDEX no compite con BCA — recomienda el canal (incluido BCA si es el óptimo). No es un canal de subasta, es un optimizador de canales existentes |
| Construir el modelo antes de tener suficientes datos para calibrarlo | MEDIA | MEDIA | El modelo funciona con datos de mercado públicos desde el día 1 (precios CARDEX + fees de canal). Los datos de "resultado real" son bonus que mejoran la precisión con el tiempo |

**Kill criteria:**
- Ningún OEM finance arm acepta un piloto en 6 meses tras lanzamiento: pivotar hacia lessors de flota corporativa (Arval Corporate, sin la complejidad OEM)
- El uplift promedio documentado en el piloto es <€150/vehículo: revisar modelo antes de escalar
