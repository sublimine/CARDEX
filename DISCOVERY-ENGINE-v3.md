# CARDEX — ESQUEMA MAESTRO v3
# Motor de Censo Automotriz Pan-Europeo
# DE · ES · FR · NL · BE · CH

---

## RUPTURA FUNDAMENTAL CON v2

v2 piensa como scraper: "recolectar listados, deduplicar, estimar gaps."
v3 piensa como oficina de censo: **la población total es conocida. Cada vehículo registrado existe en un registro estatal. El problema no es estimar cuántos hay — es rastrear cuáles están en venta, a qué precio, y predecir cuáles lo estarán mañana.**

Capture-recapture estima. El censo cuenta. CARDEX cuenta.

---

## 1. TENSOR DE ESTADO VEHICULAR

Cada vehículo existe en la intersección de 5 dimensiones. No es una fila en una tabla — es un punto en un espacio 5-dimensional cuya posición predice su comportamiento.

```
V(t) = f(Físico, Geográfico, Económico, Regulatorio, Temporal)
```

| Dimensión | Componentes | Fuente (coste 0€) |
|-----------|-------------|-------------------|
| Física | make/model/year/fuel/kW/mileage/color/VIN | Listados + registros |
| Geográfica | país/región/código postal/zona urbana-rural | Registro + listado |
| Económica | precio_listado/TCO/depreciación/spread_transfronterizo | Calculado |
| Regulatoria | clase emisiones/impuesto_circulación/zona_ambiental/ITV-TÜV_expiry | Legislación + datos abiertos |
| Temporal | días_en_mercado/estacionalidad/distancia_a_evento_regulatorio | Derivado |

La potencia no está en cada dimensión aislada — está en las **intersecciones**:

- Físico × Regulatorio = qué vehículos quedarán prohibidos en zonas LEZ y cuándo (caída de valor predecible)
- Geográfico × Económico = superficie de arbitraje transfronterizo (mismo vehículo, distinto precio por fiscalidad)
- Temporal × Físico = olas de oferta predecibles (lease returns a 3 años, primera reventa privada a 5-7 años)
- Regulatorio × Temporal = deadlines que fuerzan ventas (implementación de ZFE en Lyon 2025, Madrid 360, etc.)

---

## 2. CAPA DE VERDAD: ESTADÍSTICAS DE MATRICULACIÓN

### El ground truth que nadie usa

Cada país publica estadísticas de matriculación que revelan la composición EXACTA del parque. No son estimaciones — son censos completos.

| País | Fuente | Granularidad | Acceso | Coste |
|------|--------|-------------|--------|-------|
| DE | KBA (Kraftfahrt-Bundesamt) | make/model/fuel/year/Kreis | flensburg-statistik.de, destatis.de | 0€ |
| ES | DGT (Dirección General de Tráfico) | make/model/fuel/year/provincia | datos.gob.es, dgt.es/estadisticas | 0€ |
| FR | SDES (Ministère Écologie) | make/model/fuel/year/département | data.gouv.fr, RSVERO dataset | 0€ |
| NL | RDW | VIN-level (!), make/model/fuel/year/apk_expiry | opendata.rdw.nl (SODA API) | 0€ |
| BE | DIV/SPF Mobilité | make/model/fuel/year/province | statbel.fgov.be | 0€ |
| CH | ASTRA/BFS | make/model/fuel/canton | bfs.admin.ch, opendata.swiss | 0€ |

**Holanda es el caso extremo: RDW publica 15M+ registros a nivel VIN con fecha de APK (ITV), primera matriculación, masa, combustible, emisiones CO2, estado del seguro. Gratis. API pública.**

### Qué se extrae

Para cada celda `(país, región, make, model, fuel, year)`:

```
fleet_count[DE][Bayern][BMW][3 Series][Diesel][2019] = 14,283
```

Esto es la POBLACIÓN TOTAL. No una estimación — el número real de vehículos registrados.

### De población a flujo

Los registros también publican **transacciones anuales** (cambios de titularidad):

| País | Transacciones/año | Fuente |
|------|-------------------|--------|
| DE | 6.2M | KBA Besitzumschreibungen |
| FR | 5.6M | AAAA/SDES |
| ES | 2.1M | DGT |
| NL | 2.0M | RDW |
| BE | 0.8M | FEBIAC/DIV |
| CH | 0.7M | ASTRA |
| **Total** | **17.4M** | |

Ratio de rotación = transacciones / parque. Esto da la **velocidad del mercado** por segmento:

```
turnover_rate[DE][SUV][2020] = 0.14  →  14% del stock de SUVs 2020 cambia de manos/año
turnover_rate[NL][EV][2022] = 0.22  →  EVs recientes rotan más rápido (lease returns)
```

Con el parque total y la tasa de rotación, puedes calcular el **stock esperado de vehículos en venta** en cualquier momento:

```
expected_for_sale = fleet_count × turnover_rate × avg_days_on_market / 365
```

Si el mercado dice 14,283 BMW 3 Series Diesel 2019 en Bayern, con rotación del 12% y 45 días promedio en mercado:

```
expected_for_sale = 14,283 × 0.12 × 45/365 ≈ 211
```

Si CARDEX tiene 185 listados activos para esa celda → **cobertura del 87.7%**, y faltan ~26 vehículos. No estimado estadísticamente — derivado de ground truth.

---

## 3. ECOSISTEMA INDIRECTO: LAS DIMENSIONES INVISIBLES

### 3.1 Ciclo de Vida de Recambios → Depreciación Predictiva

**Fuente: TecDoc (Tecalliance)**

TecDoc es la base de datos estándar de la industria europea de recambios. Mapea cada vehículo (por KBA/TSN en DE, tipo-mina en FR, etc.) a todas las piezas compatibles, fabricantes y referencias cruzadas. 

Acceso relevante a coste cero:
- TecDoc Catalog (TecCom) tiene API con tier gratuito para desarrolladores
- Las tiendas online de recambios (Autodoc, Oscaro, Mister-Auto) publican precios indexables

**Señal extraíble:**

```
parts_cost_index[make][model][year] = Σ(precio_pieza × frecuencia_reemplazo) / baseline_segmento
```

Un vehículo cuyo índice de coste de recambios es 1.8× el segmento tiene un TCO más alto → se deprecia más rápido → su precio de reventa convergerá más rápido al equilibrio.

Esto predice precio de venta con más precisión que cualquier comparación de listados, porque captura un **fundamental** del activo, no el sentimiento del vendedor.

**Señales de discontinuación:**
- Pieza con 0 proveedores aftermarket = solo OEM = precio 3-5x → coste de propiedad se dispara
- Modelo con piezas en fin de producción = desplome de valor inminente
- Detectable monitoreando catálogos TecDoc periódicamente

### 3.2 Siniestralidad → Valor Ajustado por Riesgo

**Fuentes:**

| Dato | Fuente | Acceso |
|------|--------|--------|
| Siniestralidad por modelo/año | CESVIMAP (ES), Allianz Zentrum (DE), SRA (FR) | Publicaciones públicas parciales |
| Euro NCAP ratings | euroncap.com | Abierto, estructurado |
| Costes medios de reparación por modelo | Audatex/DAT public reports | Informes anuales gratuitos |
| ITV/TÜV failure rates por modelo/año | RDW (NL: APK data, granular), TÜV Report (DE: anual, público) | 0€ |

**El TÜV Report es oro puro:** publica tasas de fallo por modelo y edad. Un Dacia Sandero de 5 años tiene 15% de fallos graves vs 4% de un Toyota Yaris del mismo año. Esto correlaciona directamente con:
- Probabilidad de que el vehículo pase a estado "en venta" (dueño no quiere reparar)
- Descuento esperado en precio (comprador informado penaliza)
- Velocidad de rotación (vehículo fiable se vende más rápido)

**Modelo:**

```
risk_adjusted_value = market_price × (1 - risk_discount)
risk_discount = f(ncap_score, tuv_failure_rate, parts_cost_index, avg_repair_cost)
```

Ningún portal tiene esto. Ni AutoScout24, ni mobile.de, ni ningún agregador. Es una capa de inteligencia exclusiva de CARDEX.

### 3.3 Arbitraje Transfronterizo → Flywheel de Datos

**La fiscalidad crea distorsiones de precio masivas:**

| Impuesto | País | Efecto |
|----------|------|--------|
| BPM (Belasting van Personenauto's) | NL | +€2,000-15,000 sobre precio base. EVs exentos hasta 2025. |
| Malus écologique | FR | Hasta €60,000 para emisiones >193 g/km (2024). |
| IEDMT (Impuesto Matriculación) | ES | 0-14.75% según emisiones y comunidad autónoma. |
| NoVA (Normverbrauchsabgabe) | AT* | Referencia para flujos CH. |
| Kfz-Steuer | DE | Anual, basado en CO2. Relativamente bajo → DE es exportador neto de vehículos usados. |
| BPM + MRB | NL | Combinados hacen que NL sea el mercado más caro de Europa para combustión. |

*AT no es target pero afecta flujos hacia CH.

**Superficie de arbitraje calculable:**

```
arbitrage_spread[vehicle] = price[country_A] - price[country_B] - transport_cost - re_registration_cost - tax_delta
```

Donde:
- `price[country]` = precio medio observado en listados CARDEX para esa celda
- `transport_cost` = distancia × €0.50/km (transporte en camión, tarifas públicas)
- `re_registration_cost` = COC + homologación + trámites (fijo por país, dato público)
- `tax_delta` = diferencia fiscal neta al importar

**Un Golf GTI 2020 con 50K km:**
- ES: ~€21,000 (IEDMT 4.75% ya incluido, precio bajo)
- NL: ~€28,500 (precio inflado por BPM histórico)
- Spread bruto: €7,500
- Costes (transporte Madrid→Rotterdam + COC + RDW + BPM recálculo): ~€2,800
- **Arbitraje neto: ~€4,700**

Esto no es un análisis teórico — es un **producto**. Dealers que importan/exportan pagarán por esta señal.

**Flywheel:** Cada transacción de arbitraje que se ejecuta usando datos CARDEX genera:
1. Confirmación de precio real de transacción (no listado, sino venta efectiva)
2. Datos de coste de re-registro reales (validan el modelo)
3. El usuario vuelve porque el dato fue correcto → más usuarios → más datos → mejor modelo

### 3.4 Zonas Ambientales como Acelerador de Depreciación

**LEZ/ZFE activas y en implementación:**

| Zona | País | Restricción | Deadline |
|------|------|------------|----------|
| Umweltzone (>80 ciudades) | DE | Solo Plakette 4 (Euro 4+) | Activo |
| ZFE-m (Paris, Lyon, Marseille, +10) | FR | Crit'Air ≤2 para centro (Euro 5+ gasolina, Euro 6+ diesel) | Escalamiento 2024-2028 |
| Madrid 360, Barcelona ZBE | ES | Sin etiqueta = prohibido centro | Activo |
| Milieuzone (14 ciudades) | NL | Diesel <Euro 6 prohibido en centro Amsterdam desde 2025 | Activo/escalando |
| LEZ Brussels, Antwerp, Ghent | BE | Euro 5 diesel ban desde 2025 | Activo/escalando |
| Varias ciudades | CH | Caso por caso, menos estricto | Variable |

**Señal:**

```
lez_exposure[vehicle] = {
  zones_banned_now: ["Paris", "Madrid"],
  zones_banned_2026: ["Paris", "Madrid", "Lyon", "Barcelona", "Amsterdam"],
  zones_banned_2028: ["Paris", "Madrid", "Lyon", "Barcelona", "Amsterdam", "Marseille", "Brussels", ...],
  depreciation_acceleration: 0.15  // 15% de depreciación adicional por restricción
}
```

Un diesel Euro 5 que hoy se vende a €12,000 en París. En 2026, no puede circular por Lyon, Marseille, Toulouse. Su pool de compradores urbanos se reduce drásticamente → precio converge a €8,000-9,000 independientemente de condición mecánica.

**CARDEX puede calcular esto para CADA vehículo en el parque.** Es la única plataforma que cruza la clase de emisiones (del registro) con el mapa de zonas (legislación) con el precio de mercado (listados) para producir una **curva de depreciación regulatoria** específica por vehículo.

### 3.5 ITV/APK/TÜV como Predictor de Oferta

**El dato más infrautilizado del mercado.**

En Holanda, RDW publica la fecha de expiración del APK (ITV) de cada vehículo. En Alemania, el TÜV caduca cada 2 años. En España, la ITV tiene calendarios fijos por antigüedad.

**Patrón observado:** Cuando un vehículo de >8 años tiene ITV próxima a caducar, hay 3 escenarios:
1. Pasa ITV → sigue circulando (no genera listado)
2. Falla ITV → reparación cara → dueño decide vender (genera listado en 2-6 semanas)
3. Falla ITV → desguace

La probabilidad de cada escenario depende de:
- Coste esperado de reparación (de TÜV Report / datos de taller)
- Valor residual del vehículo (de listados CARDEX)
- Si coste_reparación > 30% × valor_residual → alta probabilidad de venta o desguace

**Para NL (donde tenemos datos VIN-level):**

```
vehicles_with_apk_expiring_next_30d = query RDW API
for each vehicle:
  estimated_repair_cost = f(model, age, last_apk_defects)
  estimated_value = cardex_price_model(make, model, year, mileage_estimate)
  if repair_cost / value > 0.30:
    probability_of_listing = 0.65
    expected_listing_date = apk_expiry + 14-42 days
```

Esto permite a CARDEX **predecir qué vehículos aparecerán en venta antes de que se listen.** Valor enorme para dealers que quieren comprar stock.

---

## 4. ARQUITECTURA DE INGESTA ZERO-COST

### Jerarquía de fuentes por coste y fiabilidad

```
┌─────────────────────────────────────────────────────────────┐
│ TIER 0: VERDAD ABSOLUTA (0€, bulk, gobierno)                │
│ Registros: KBA, DGT, SDES, RDW, DIV, ASTRA                │
│ → Parque total, transacciones, composición por segmento     │
├─────────────────────────────────────────────────────────────┤
│ TIER 1: DATOS ABIERTOS ESTRUCTURADOS (0€, API/bulk)         │
│ RDW opendata (NL, VIN-level), data.gouv.fr, datos.gob.es   │
│ TÜV Report, Euro NCAP, OpenStreetMap, Overpass API          │
│ → Historial técnico, ratings, geolocalización               │
├─────────────────────────────────────────────────────────────┤
│ TIER 2: SEMI-ESTRUCTURADOS GRATUITOS (0€, scraping ligero)  │
│ Asociaciones: ZDK, BOVAG, TRAXIO, AGVS, GANVAM, CNPA       │
│ OEM locators, CPO listings, Yellow Pages                    │
│ → Directorio de dealers, afiliaciones de marca              │
├─────────────────────────────────────────────────────────────┤
│ TIER 3: PORTALES (0€, scraping adaptativo)                  │
│ mobile.de, AutoScout24, LeBonCoin, Wallapop, Marktplaats..  │
│ → Listados activos, precios, fotos, descripción             │
├─────────────────────────────────────────────────────────────┤
│ TIER 4: FEEDS PUSH (0€, partnership)                        │
│ DMS: Keyloop, Nextlane, MotorK (CARDEX como canal gratis)   │
│ → Inventario en tiempo real, datos limpios, cero scraping   │
├─────────────────────────────────────────────────────────────┤
│ TIER 5: DERIVADOS (0€, calculado internamente)              │
│ Arbitraje, depreciación regulatoria, predicción de oferta   │
│ TCO, risk-adjusted value, curvas de precio                  │
│ → Inteligencia exclusiva, no replicable sin el stack        │
└─────────────────────────────────────────────────────────────┘
```

**Inversión del paradigma:** v2 empezaba por Tier 3 (portales) y construía hacia arriba. v3 empieza por Tier 0 (ground truth) y baja hacia los listados. Los portales son la ÚLTIMA fuente, no la primera. El parque total se conoce ANTES de scrapear un solo listado.

### Pipeline de cruce

```
TIER 0 (censo)          TIER 3 (listados)
     │                        │
     ▼                        ▼
 fleet_matrix            listings_matrix
 [país×región×           [país×región×
  make×model×             make×model×
  year×fuel]              year×fuel]
     │                        │
     └──────────┬─────────────┘
                ▼
         COVERAGE MATRIX
         coverage[cell] = listings[cell] / expected_for_sale[cell]
                │
                ▼
         GAP MATRIX
         gap[cell] = expected_for_sale[cell] - listings[cell]
                │
                ▼
         PRIORITY QUEUE
         Cells con mayor gap absoluto × valor económico
         → dirige el esfuerzo de scraping
```

El scraping no es exhaustivo — es **quirúrgico**. Solo se intensifica en celdas donde el gap matrix indica alta oportunidad. En celdas con cobertura >90%, se reduce a mantenimiento.

---

## 5. LEGALIDAD COMO ARMA COMPETITIVA

### Diseño por capas de cumplimiento

| Capa | Principio | Implementación |
|------|-----------|----------------|
| Datos de vehículos | No son datos personales (GDPR no aplica) | Vehículos como objetos, no vinculados a personas |
| Datos de dealers (B2B) | Interés legítimo (Art. 6.1.f GDPR) | Información comercial pública de entidades jurídicas |
| Datos de vendedores privados | Minimización radical | Solo: precio, ubicación (ciudad), make/model/year. NUNCA nombre, teléfono, email |
| Scraping | Art. 4 Directiva Copyright (DSM) | TDM permitido salvo opt-out explícito. Respetar robots.txt = safe harbor |
| Almacenamiento | Privacy by Design (Art. 25 GDPR) | Pseudonimización por defecto. TTL en datos de particulares. |
| Transferencia cross-border | Todos datos en EU | Hetzner DE/FI. Sin transferencia a terceros países |

### Por qué esto es un moat

Un competidor que scrapea sin este framework tiene 3 vulnerabilidades:

1. **GDPR complaint de un particular** → multa + orden de borrado + precedente público
2. **Cease & desist de un portal** → sin defensa legal clara → pérdida de fuente
3. **Demanda de competidor** (ej: AutoScout24 demandó a varios agregadores) → litigio costoso

CARDEX opera exclusivamente sobre datos de vehículos (objetos, no personas) + datos B2B de dealers (entidades jurídicas) + datos derivados (calculados internamente). El único punto de riesgo son los listados de particulares → se aplica minimización extrema.

El framework legal no es un coste — es una **barrera de entrada** para competidores menos rigurosos.

### Compliance como feature

```
Cada vehículo en CARDEX lleva un provenance record:

VehicleProvenance {
  source_type: GOVERNMENT_REGISTRY | OPEN_DATA | PORTAL_PUBLIC | DMS_FEED | DERIVED
  legal_basis: LEGITIMATE_INTEREST | TDM_EXCEPTION | CONTRACT | PUBLIC_TASK
  data_minimization_applied: true
  retention_policy: INDEFINITE (objects) | 90_DAYS (private seller metadata)
  right_to_erasure_applicable: false (vehicle data) | true (private seller data only)
}
```

Esto es auditable, explicable ante cualquier DPA, y constituye documentación defensiva ante litigios.

---

## 6. EFECTO RED: MONOPOLIO IRREVERSIBLE

### Dinámica de lock-in por capas

```
Tiempo →
────────────────────────────────────────────────────────

Mes 1-3: DATOS (unidireccional)
  Registros + OSM + directorios + primeros portales
  → Primer coverage matrix con ground truth
  → Nadie más tiene esto porque nadie cruza registros con listados

Mes 3-6: INTELIGENCIA (retroalimentación)
  Coverage matrix → gap-directed scraping → más datos → mejor matrix
  Datos indirectos (TÜV, recambios, zonas LEZ) → capa analítica exclusiva
  → El gap entre CARDEX y cualquier competidor se AMPLÍA con cada ciclo

Mes 6-12: NETWORK EFFECTS (exponencial)
  DMS feeds activos → dealers reciben tráfico gratuito → más dealers se integran
  Datos de arbitraje → traders ejecutan transacciones → datos de transacción reales
  Predicciones de oferta → dealers compran anticipándose → validan el modelo
  → Cada usuario genera datos que hacen el sistema más valioso para el siguiente

Mes 12+: MOAT IRREVERSIBLE
  Historical price data (nadie más tiene 12+ meses de cobertura cross-border)
  Modelo de depreciación calibrado con transacciones reales
  Red de DMS integrados (switching cost alto)
  Legal compliance auditable (competidores vulnerables)
  → Replicar CARDEX requiere empezar 12 meses atrás. Imposible.
```

### El dato que nadie puede copiar

Los portales tienen listados. CARDEX tiene el **delta entre lo que existe y lo que se ve.** Ese delta es calculado, no scrapeado — depende de la acumulación de todas las capas. Un competidor puede scrapear los mismos portales, pero no puede replicar:

1. El cruce con registros gubernamentales (requiere el pipeline de procesamiento)
2. El modelo de depreciación regulatoria (requiere mapa LEZ + clasificación de emisiones por VIN)
3. Las predicciones de oferta por ITV/APK (requiere datos históricos de correlación)
4. Los datos de transacción real de arbitraje (requiere los usuarios B2B que CARDEX atrae)

Cada dimensión refuerza las demás. No es un producto — es un **sistema termodinámico** que se aleja del equilibrio con cada ciclo.

---

## 7. IMPLEMENTACIÓN: PRIMERA SEMANA

No roadmap de 6 meses. Qué se ejecuta AHORA, con el stack Docker existente:

### Día 1-2: Ingestión de Tier 0

```
1. RDW OpenData (NL): Descarga bulk de 15M+ registros via SODA API
   → Tabla: vehicles_rdw (kenteken, make, model, fuel, year, apk_expiry, co2, mass)
   → Es el dataset más completo del mundo a coste 0

2. INSEE SIRENE (FR): Bulk CSV 12GB desde data.gouv.fr
   → Filtro: NAF 45.11Z, 45.19Z → ~40,000 dealers con dirección exacta
   
3. KBO/BCE (BE): Monthly CSV desde kbopub.economie.fgov.be
   → Filtro: NACE 45.110 → ~30,000 entidades
```

### Día 3-4: Coverage Matrix Prototipo

```
4. KBA Statistik (DE): Tablas de parque por make/model/year/Kreis
   → fleet_matrix para Alemania (mayor mercado)

5. Cruzar fleet_matrix con listados existentes (5000 seed)
   → Primera coverage matrix real: "tenemos X de Y esperados"
   → Visualizar en Grafana (ya desplegado)
```

### Día 5-7: Gap-Directed Scraping

```
6. Identificar las 10 celdas con mayor gap absoluto × valor
7. Scraping quirúrgico: solo esas celdas, no exhaustivo
8. Re-calcular coverage matrix
9. Medir: ¿la cobertura mejoró más eficientemente que scraping ciego?
```

Esto valida el núcleo de v3 en una semana: **ground truth → coverage → scraping dirigido.** Si funciona (y tiene que funcionar, porque la matemática es determinista), el resto del sistema se construye sobre esta base.

---

## 8. MODELO DE DATOS NUCLEAR

### PostgreSQL (entidades y relaciones)

```sql
-- Parque vehicular por celda (de registros gubernamentales)
CREATE TABLE fleet_census (
    country     CHAR(2),
    region      TEXT,           -- NUTS-3 o equivalente
    make        TEXT,
    model       TEXT,
    fuel_type   TEXT,           -- petrol/diesel/electric/hybrid/lpg
    year        SMALLINT,
    registered_count  INT,      -- vehículos registrados en esta celda
    annual_transactions INT,    -- cambios de titularidad/año
    turnover_rate     NUMERIC(5,4),  -- transactions/registered
    source_date DATE,
    PRIMARY KEY (country, region, make, model, fuel_type, year)
);

-- Vehículo unificado (de listados)
CREATE TABLE vehicles (
    vehicle_ulid    TEXT PRIMARY KEY,
    vin             TEXT,
    make            TEXT NOT NULL,
    model           TEXT NOT NULL,
    variant         TEXT,
    year            SMALLINT NOT NULL,
    fuel_type       TEXT,
    mileage_km      INT,
    power_kw        SMALLINT,
    color           TEXT,
    emission_class  TEXT,        -- euro6d, euro5, etc
    co2_gkm         SMALLINT,
    country         CHAR(2) NOT NULL,
    region          TEXT,
    postal_code     TEXT,
    dealer_ulid     TEXT REFERENCES dealers(dealer_ulid),
    is_private_seller BOOLEAN DEFAULT FALSE,
    listing_status  TEXT DEFAULT 'ACTIVE',  -- ACTIVE/SOLD/STALE
    first_seen      TIMESTAMPTZ NOT NULL,
    last_seen       TIMESTAMPTZ NOT NULL,
    days_on_market  INT GENERATED ALWAYS AS (EXTRACT(DAY FROM last_seen - first_seen)) STORED,
    best_price_eur  NUMERIC(10,2),
    provenance      JSONB NOT NULL  -- {source_type, legal_basis, minimization}
);

-- Precios por fuente (multilistado)
CREATE TABLE vehicle_sources (
    vehicle_ulid    TEXT REFERENCES vehicles(vehicle_ulid),
    source_portal   TEXT NOT NULL,
    source_url      TEXT,
    price_eur       NUMERIC(10,2),
    currency        CHAR(3) DEFAULT 'EUR',
    scraped_at      TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (vehicle_ulid, source_portal)
);

-- Coverage matrix (materializada, recalculada hourly)
CREATE MATERIALIZED VIEW coverage_matrix AS
SELECT
    fc.country, fc.region, fc.make, fc.model, fc.fuel_type, fc.year,
    fc.registered_count,
    fc.turnover_rate,
    ROUND(fc.registered_count * fc.turnover_rate * 45.0 / 365) AS expected_for_sale,
    COUNT(v.vehicle_ulid) AS listed_count,
    ROUND(COUNT(v.vehicle_ulid)::NUMERIC /
        NULLIF(ROUND(fc.registered_count * fc.turnover_rate * 45.0 / 365), 0), 4
    ) AS coverage_ratio,
    ROUND(fc.registered_count * fc.turnover_rate * 45.0 / 365) - COUNT(v.vehicle_ulid) AS gap
FROM fleet_census fc
LEFT JOIN vehicles v ON
    v.country = fc.country
    AND v.region = fc.region
    AND v.make = fc.make
    AND v.model = fc.model
    AND v.fuel_type = fc.fuel_type
    AND v.year = fc.year
    AND v.listing_status = 'ACTIVE'
GROUP BY fc.country, fc.region, fc.make, fc.model, fc.fuel_type, fc.year,
         fc.registered_count, fc.turnover_rate;

-- Dealer unificado
CREATE TABLE dealers (
    dealer_ulid     TEXT PRIMARY KEY,
    canonical_name  TEXT NOT NULL,
    country         CHAR(2) NOT NULL,
    region          TEXT,
    postal_code     TEXT,
    lat             NUMERIC(9,6),
    lon             NUMERIC(9,6),
    brands          TEXT[],
    dms_provider    TEXT,
    estimated_stock SMALLINT,
    confidence      NUMERIC(3,2),
    registry_id     TEXT,          -- SIREN, KBO, HRB, etc
    last_verified   TIMESTAMPTZ
);

-- Dealer identities across sources
CREATE TABLE dealer_identities (
    dealer_ulid     TEXT REFERENCES dealers(dealer_ulid),
    source          TEXT NOT NULL,
    source_dealer_id TEXT,
    source_name     TEXT,
    source_url      TEXT,
    PRIMARY KEY (dealer_ulid, source)
);

-- Índice de coste de recambios por modelo
CREATE TABLE parts_cost_index (
    make        TEXT,
    model       TEXT,
    year        SMALLINT,
    cost_index  NUMERIC(4,2),   -- 1.0 = media del segmento
    segment_avg_eur NUMERIC(8,2),
    discontinued_parts_count SMALLINT DEFAULT 0,
    source      TEXT,           -- tecdoc, autodoc, oscaro
    updated_at  DATE,
    PRIMARY KEY (make, model, year)
);

-- Zonas ambientales y su impacto
CREATE TABLE lez_zones (
    zone_id     TEXT PRIMARY KEY,
    city        TEXT NOT NULL,
    country     CHAR(2) NOT NULL,
    min_emission_class TEXT NOT NULL,  -- euro6d, euro5, etc
    effective_date DATE NOT NULL,
    planned_escalation JSONB  -- [{date, new_min_class}]
);

-- Tabla de impuestos por país para cálculo de arbitraje
CREATE TABLE tax_structures (
    country     CHAR(2) PRIMARY KEY,
    registration_tax JSONB,    -- fórmula parametrizada
    annual_tax      JSONB,     -- fórmula parametrizada
    import_costs    JSONB,     -- COC, homologación, trámites
    updated_at      DATE
);
```

### ClickHouse (series temporales y analytics)

```sql
-- Historial de precios (append-only, compresión extrema)
CREATE TABLE price_history (
    vehicle_ulid    String,
    source_portal   String,
    price_eur       Float32,
    observed_at     DateTime
) ENGINE = MergeTree()
ORDER BY (vehicle_ulid, source_portal, observed_at)
TTL observed_at + INTERVAL 3 YEAR;

-- Market signals agregados
CREATE TABLE market_signals (
    country     FixedString(2),
    region      String,
    make        String,
    model       String,
    fuel_type   String,
    year        UInt16,
    date        Date,
    avg_price   Float32,
    median_price Float32,
    listing_count UInt32,
    avg_dom     Float32,       -- days on market
    turnover_velocity Float32, -- sold/listed ratio
    price_change_7d Float32,   -- % change vs 7 days ago
    arbitrage_spread_max Float32  -- max cross-border spread
) ENGINE = MergeTree()
ORDER BY (country, make, model, date)
PARTITION BY toYYYYMM(date);
```

---

## 9. MÉTRICAS DE VERDAD

| Métrica | Qué mide | Por qué importa |
|---------|----------|-----------------|
| Coverage ratio por celda | listed / expected_for_sale | **North star.** Si no sube, nada más importa |
| Gap absoluto ponderado | Σ(gap × valor_medio_celda) | Prioriza esfuerzo donde hay más valor |
| Precisión de predicción de oferta | % vehículos predichos que efectivamente se listan | Valida el modelo ITV/APK |
| Error de precio vs transacción real | |predicted - actual| / actual | Calibración del modelo de valoración |
| Coste por vehículo indexado | infraestructura_mensual / vehículos_activos | Debe tender a 0 con escala |
| Tiempo de detección de nuevo listado | Δt entre publicación y entrada en CARDEX | Frescura competitiva |

No métricas de vanidad. No "uptime 99.9%". No "requests per second". Solo las que determinan si el sistema está cumpliendo su función.
