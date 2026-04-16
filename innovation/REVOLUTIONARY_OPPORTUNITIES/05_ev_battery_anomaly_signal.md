# 05 — EV Battery Anomaly Signal (SoH Proxy desde comportamiento de mercado)
**Veredicto:** STRONG  
**Dominio:** Necesidades desatendidas B2B automotriz EU  
**Fecha:** 2026-04-16 · Autorización: Salman

---

## Título
**CARDEX EV Watch:** Sistema de detección de anomalías de precio en vehículos eléctricos que actúa como proxy estadístico de degradación de batería — sin medir el SoH físicamente, identifica EVs cuyo precio de mercado se desvía anormalmente de su cohort (mismo modelo/año/km) y los señala como candidatos a inspección de batería antes de la compra.

---

## Tesis

La ola de EVs matriculados en EU entre 2019-2022 está retornando masivamente de leasing en 2024-2026. Un dealer B2B que compra 30 EVs/semana en subasta enfrenta un riesgo nuevo sin precedente en vehículos ICE: dos Renault Zoe 50kWh 2021 con 65.000 km pueden valer €8.000-12.000 dependiendo del State of Health (SoH) de la batería. La batería con 75% SoH (degradada) puede costar €3.000-5.000 en reemplazo. El dealer no lo sabe antes de comprar. No hay test de SoH en la subasta.

Lo que CARDEX puede hacer sin medir nada físicamente: detectar la anomalía de precio. Un EV que se vende a €4.000 por debajo de la mediana de su cohort tiene una razón — y en un 60-70% de los casos esa razón es la batería (el vendedor lo sabe o lo intuye). Esta señal estadística, presentada al comprador en el momento de decisión, es información de alto valor.

No es diagnóstico. Es detección de anomalía + señal de riesgo. La diferencia es legal y es correcta: CARDEX dice "este vehículo está en el percentil 15 de precio de su cohort — investiga el motivo". No dice "la batería está mala". El comprador que recibe esa señal puede hacer una inspección de batería (Aviloo, DEKRA EV Check, o el propio OBD) antes de pujar. Sin la señal, no sabe qué vehículos inspeccionar entre los 200 que ve esa semana.

El timing es perfecto: 2025-2027 es el pico de retornos de EVs de primera generación. Los dealers B2B están en el momento de mayor exposición a este riesgo. Nadie les da esta información hoy.

---

## Evidencia de demanda

- **Volumen de retornos EV EU 2025-2027:** Según la ACEA, las matriculaciones de vehículos 100% eléctricos en EU alcanzaron 535.000 en 2020 y 875.000 en 2021. Con una media de contratos de leasing de 3-4 años, los retornos masivos de estos vehículos ocurren en 2023-2025. Las estimaciones de la industria apuntan a ~1.5-2M EVs retornando de leasing en EU solo en 2025-2026. Fuente: ACEA Statistical Pocketbook 2024; Dataforce Fleet Report EU 2024.
- **Valor en riesgo por batería degradada:** Aviloo (empresa austriaca de diagnóstico de baterías EV, 450K tests completados a finales 2024) publicó que el 23% de las baterías de vehículos EV de ocasión presentan degradación >20% respecto al nominal. A un coste de reemplazo de batería de €4.000-8.000, el riesgo no identificado por vehículo es de €800-1.850 en valor esperado. Fuente: Aviloo Battery Report 2024.
- **Demanda de información antes de compra:** En una encuesta de Charging Interface Initiative (CharIN) 2024, el 78% de dealers B2B europeos que empezaban a comprar EVs citaba "incertidumbre sobre la batería" como su principal barrera. La demanda de información está documentada.
- **Análogo de mercado — Recurrent Auto (US):** Recurrent construyó un negocio en EE.UU. de reporting de salud de batería EV para compradores. Su base de datos procesa 200K+ vehículos y carga €19-29 por informe B2C. Sin embargo, no tienen presencia EU y no tienen el componente de anomalía estadística cross-market que CARDEX puede generar.

---

## Competencia actual

| Competidor | Qué hace | Por qué no es lo mismo |
|---|---|---|
| **Aviloo** | Diagnóstico físico de batería EV via OBD | Requiere hardware físico, no es scalable en subasta. Solo diagnóstica, no detecta estadísticamente |
| **DEKRA EV Battery Check** | Inspección física manual | Cara (€150-300/vehículo), manual, no integrada en plataforma de compra |
| **Recurrent Auto (US)** | SoH reporting B2C en US | No está en EU. No tiene datos de mercado EU. Foco B2C |
| **AutoDNA / CARFAX EU** | Historial de vehículo (accidentes, ITV) | No tiene información de batería en ningún caso |
| **OEM telematics (Renault, VW, etc.)** | SoH real via OEM conectado | Dato bloqueado, no accesible al comprador B2B sin acuerdo bilateral con cada OEM |

**Nadie proporciona señal estadística de anomalía de precio EV en tiempo real, pan-EU, embebida en una plataforma de discovery.** El gap es real y la ventana temporal es 2025-2028.

---

## Lo que hace falta construir

### Modelo de detección de anomalía por cohort

**Definición de cohort:** `{make} + {model} + {fuel_type=EV} + {year} ± 1 + {km_bucket}` donde km_bucket = {<30K, 30-60K, 60-90K, 90-120K, >120K}.

**Detección de anomalía:**
```
cohort_median_price = percentile_50(listings_in_cohort)
cohort_iqr = percentile_75 - percentile_25

anomaly_threshold = cohort_median_price - 1.5 × cohort_iqr
battery_risk_flag = (listing_price < anomaly_threshold) AND (fuel_type == EV)
battery_risk_score = (cohort_median_price - listing_price) / cohort_median_price × 100
```

Un Renault Zoe 50kWh 2021 50-70K km cuya mediana de cohort es €14.500 y que se lista a €10.800 obtiene un `battery_risk_score = 25.5%` — un desvío de 25.5% por debajo de la mediana del cohort.

### Stack técnico
```
ev_watch/
├── cohort_builder.go         # Construye y actualiza cohorts EV semanalmente
├── anomaly_detector.go       # IQR-based anomaly detection por cohort
├── risk_scorer.go            # Score [0-100]: 0=precio normal, 100=anomalía extrema
├── ev_classifier.go          # Identifica EV vs. PHEV vs. ICE en el índice
├── watch_api.go              # GET /vehicles/{vin}/ev-risk → {score, cohort_median, 
│                             # deviation_pct, recommendation, inspection_providers}
├── inspection_directory.go   # Directorio de servicios de inspección EV por país/región
│                             # (Aviloo, DEKRA EV, BCA EV Check) con click-to-book
└── alert_webhook.go          # Notifica al buyer cuando vehículo en watchlist entra en 
│                             # zona de anomalía
```

**Estimación de desarrollo:** 5-7 semanas. La estadística es sencilla (IQR). El trabajo está en la clasificación EV del índice y en el directorio de proveedores de inspección.

**Prerequisito de datos:** El cohort de detección requiere mínimo 20-30 listings comparables por cohort para ser estadísticamente robusto. Para modelos populares (Renault Zoe, Volkswagen ID.3, Peugeot e-208) esto se alcanza rápidamente. Para modelos de nicho, el flag puede ser "cohort insuficiente — sin datos".

---

## Monetización

### Modelo: Feature de valor en terminal + B2B data partnerships

| Tier | Descripción | Precio |
|---|---|---|
| **Terminal Pro** | EV Watch incluido en tier Pro — cada listing EV muestra el score de anomalía | Sin coste adicional — aumenta valor tier Pro |
| **EV Watch API** | Para plataformas de terceros (subastas, DMS) que quieren embeber el score | €0.20-0.50 por consulta EV |
| **Fleet Batch Scoring** | Lessors que quieren puntuar portfolio de EVs retornados antes de disposición | €0.10-0.30 por vehículo en batch |
| **Inspection Referral** | Comisión de referral por cada inspección física reservada a través del directorio integrado | €10-30 por referral a Aviloo/DEKRA |
| **Data Partnership** | Feed de anomalías anonimizadas a second-life battery companies (Northvolt, VW PowerCo) para identificar fuentes de baterías degradadas | €500-2.000/mes por empresa |

### ARPU estimado (2027, cuando la ola EV está en pico)

- 5 lessors que puntúan 50.000 EVs/trimestre en batch: €0.20/vehículo × 200K/año = €40.000 ARR
- 3 subastas con EV Watch API embebida, 100K consultas/mes: €0.30 × 1.2M/año = €360.000 ARR
- 3 second-life battery companies con data feed: €1.000/mes × 3 × 12 = €36.000 ARR
- Referrals a inspección: 2.000 referrals/año × €20 = €40.000 ARR
- **Total estimado SOM 2027: ~€476.000 ARR**

No es un producto de €10M standalone, pero:
1. Es defensible (datos propietarios)
2. Posiciona a CARDEX como la referencia en EV B2B intelligence
3. Abre la puerta a partenariados con second-life battery economy (mercado de €4B en EU para 2030)
4. El referral a proveedores de inspección crea un marketplace de servicios ancillary

**TAM/SAM/SOM:**

| | Valor |
|---|---|
| **TAM** | ~2M EVs B2B retornando EU/año × €1-2 valor de scoring | ~€2-4M ARR directo + upside de partenariados second-life |
| **SAM** | 6 países CARDEX, dealers/lessors activos en EV | ~€800K ARR |
| **SOM (3 años)** | Subastas + lessors + second-life data | **~€500K ARR** |

---

## Moat post-lanzamiento

1. **Cohort data exclusiva:** los cohorts se construyen desde el índice CARDEX que incluye long-tail. Un competidor que solo tiene datos de AutoScout24 tiene cohorts más pequeños y menos precisos — el IQR es menos representativo.

2. **Historial temporal:** después de 12 meses de datos, CARDEX tiene la curva de depreciación EV más granular de EU por modelo/año/km. Esto es imposible de replicar retroactivamente.

3. **Integración con directorio de inspección:** si Aviloo y DEKRA EV integran el botón "book inspection" en el CARDEX listing, el loop de acción está cerrado — el competidor que solo da el score (sin el directorio de acción) tiene menos valor.

4. **Second-life battery intelligence:** las empresas de baterías de segunda vida pagan por saber dónde están las baterías degradadas. CARDEX, una vez que identifica los vehículos anomalía en EU, puede literalmente ayudar a Northvolt o VW PowerCo a encontrar su materia prima. Nadie más tiene esta capacidad agregada.

---

## Tiempo a MVP y coste

| Hito | Semanas |
|---|---|
| EV classifier (identificar EVs en el índice) | 1-2 |
| Cohort builder + IQR anomaly detector | 2-4 |
| Risk scorer + API | 4-5 |
| Directorio de inspección (5-7 proveedores, 6 países) | 5-6 |
| UI en terminal (badge EV Risk en listings) | 6-7 |
| **MVP** | **7 semanas** |

**Coste:** 1 ingeniero × 2 meses = ~€12.000.

---

## Riesgos

| Riesgo | Probabilidad | Severidad | Mitigación |
|---|---|---|---|
| El modelo genera falsos positivos (vehículos en buen estado con precio bajo por otras razones) | ALTA | MEDIA | El score nunca dice "batería mala" — dice "precio anómalo en este cohort". La razón puede ser otras (equipamiento, color, historial). Esto es correcto. El flag es para "investiga", no para "no compres". |
| Cohorts insuficientes para modelos de nicho (Tesla, Porsche EV, etc.) | ALTA | BAJA | "Datos insuficientes" es una respuesta válida. No silenciar — devolver el flag con el denominador del cohort. |
| Dealer acusa a CARDEX de haberle costado una venta al señalar su vehículo | BAJA | MEDIA | El score es información al comprador, no publicado en el listing del vendedor. El vendedor no ve el score que ve el comprador. Framing: feature del buyer, no feature del seller. |
| El mercado EV se contrae (nuevas matriculaciones bajan) y la ola de retornos es menor de lo esperado | MEDIA | MEDIA | La ola de retornos 2020-2022 ya está en curso independientemente de la demanda de nuevos EVs. El TAM existe para 2025-2028. Revisitar en 2028. |
| Aviloo / DEKRA se niegan a integrarse en el directorio por conflicto de interés | BAJA | BAJA | El directorio puede ser unilateral (CARDEX lista sus servicios sin acuerdo bilateral). El referral con comisión requiere acuerdo; sin él, el directorio sigue siendo útil. |

**Kill criteria:**
- Tasa de falsos positivos >50% en backtest (vehículos con precio anómalo que NO tienen problemas de batería): modelo sin valor discriminatorio. Revisitar features.
- Ningún lessor o subasta adopta el API después de 6 meses: revisar si el EV volume en el índice es suficiente para hacer los cohorts estadísticamente útiles.
