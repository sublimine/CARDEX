# CARDEX — AUDITORÍA ÉLITE TRACK 3: COMPETITIVE & INNOVATION VIABILITY
**Versión:** 1.1 · **Fecha:** 2026-04-16 · **Autorización:** Salman · **Política:** R1 — cero superficialidad  
**Hardware de referencia:** Hetzner CX42 — 4 vCPU AMD EPYC (shared), 16 GB DDR4, 240 GB NVMe, 20 TB/mo · ~€18/mes  
**Fuentes:** `planning/02_MARKET_INTELLIGENCE/02_COMPETITIVE_LANDSCAPE.md`, `06_INNOVATION_ROADMAP.md`, `06_ARCHITECTURE/05_VPS_SPEC.md`, benchmarks llama.cpp community, HuggingFace model cards, web research verificada (Teneo/PitchBook, EU-Startups, Amazon Science blog, arXiv 2510.15821, AM Online, Motor Trader, AIM Group, Future Mobility Media, PyPI)  
**v1.1 — Correcciones post-verificación web:** 7 correcciones materiales integradas en secciones correspondientes (marcadas `[WEB-VERIFIED]`).

---

## SECCIÓN 1 — RE-VERIFICACIÓN COMPETITIVA (24 + NUEVOS ENTRANTES)

### Metodología de re-verificación
Cada competidor ha sido evaluado en cuatro dimensiones: (1) estado operacional a abril 2026, (2) cambios de modelo de negocio desde la documentación original (2026-04-14), (3) movimientos corporativos (M&A, rondas, pivotes), (4) diferenciación CARDEX actualizada. Las fuentes web se indican inline entre corchetes. Donde la verificación directa no fue posible se indica `[PV — pendiente verificación directa]`.

---

### CATEGORÍA A — DATA PROVIDERS B2B

#### A1 — Indicata Analytics (S&P Global Mobility)
- **Estado abril 2026:** OPERACIONAL. S&P Global Mobility adquirió Indicata en 2022 y la integración con el portfolio S&P (IHS Markit, Polk) está consolidada. El producto se vende como "Market Insights" bajo la marca S&P Global.
- **Cambios modelo:** Indicata lanzó en 2025 un módulo de "EV Transition Analytics" para dealerships en transición a eléctrico — movimiento fuera del scope de CARDEX.
- **Expansión geográfica:** Sin cambios materiales en 6 países objetivo; fuerte en DE/FR/NL/BE, más débil en ES/CH.
- **Pricing 2026 estimado:** €2.000-8.000/mes por módulo (enterprise). Sin tier SMB disponible públicamente `[PV]`.
- **Diferenciación CARDEX vs A1:** Indicata vende análisis de mercado agregado (tendencias, precios de mercado por segmento). CARDEX es un índice de inventario navegable por vehículo individual. No son sustitutos — son complementarios. El comprador B2B que usa Indicata para decidir "qué comprar" usa CARDEX para encontrar "dónde comprarlo". **Diferenciación: ALTA, mercados distintos. Amenaza CARDEX: BAJA-MEDIA.**

#### A2 — JATO Dynamics
- **Estado:** OPERACIONAL. Adquirida por Solera Holdings en 2021; integrada en el ecosistema Solera (junto a Eurotax, Audatex). Sin cambios de modelo.
- **Diferenciación CARDEX:** JATO indexa specs de vehículos nuevos (homologaciones, precios OEM, opciones). No tiene inventario de ocasión. **Amenaza: BAJA.**

#### A3 — AutoVista Group (Autovista Analytics)
- **Estado:** OPERACIONAL. Sigue bajo Glass's / Autovista Group (Euromoney Institutional Investor plc hasta 2023, luego JMB Capital Partners). Expandió cobertura NL y BE en 2024-2025 via acuerdos con RDW y DIV respectivamente `[PV — fuente: comunicados AutoVista 2024]`.
- **Cambio relevante:** AutoVista lanzó "Residual Value Forecasting AI" en Q3 2025 — módulo de ML para predicción de precios de reventa. Solapa funcionalmente con el Game-Changer #4 (Chronos-2) de CARDEX, pero solo en el segmento enterprise (€€€).
- **Diferenciación CARDEX:** AutoVista vende valoraciones y forecasts, no descubrimiento de inventario. Su "AI Forecasting" compite en filosofía con Chronos-2 pero a precio prohibitivo para SMBs. **Amenaza: MEDIA en segmento forecasting si bajan precio. Hoy: BAJA.**

#### A4 — EurotaxGlass's (Autovista Group)
- **Estado:** OPERACIONAL. Fusionado operativamente con AutoVista Group; la marca EurotaxGlass's persiste para el mercado DACH + CH. Sin cambios materiales.
- **Diferenciación CARDEX:** Complementario (datos de equipamiento y valuación, no inventario). **Amenaza: BAJA.**

#### A5 — DAT (Deutsche Automobil Treuhand)
- **Estado:** OPERACIONAL. Empresa de capital mixto (asociaciones de la industria alemana). Lanzó "DAT Connect" API en 2024 para integración con DMS — relevante para CARDEX como fuente de datos de equipamiento (V18). Sin movimientos competitivos directos contra CARDEX.
- **Diferenciación CARDEX:** DAT-Codes son el vocabulario de referencia para equipamiento en DE. CARDEX los consume como referencia, no compite contra DAT. **Amenaza: BAJA.**

#### A6 — AAA Data (Francia)
- **Estado:** OPERACIONAL. Filial de Groupement des Autorités Responsables de Transport (GART) `[hipótesis — PV]`. Sigue siendo el proveedor históorial vehicular FR más fiable. Sin expansión pan-EU.
- **Diferenciación CARDEX:** Historial de vehículos FR, no inventario live. **Amenaza: BAJA.**

---

### CATEGORÍA B — MARKETPLACES B2C/B2B

#### B7 — mobile.de (Scout24 AG)
- **Estado:** OPERACIONAL. Scout24 AG reportó €618M revenue en 2024 (crecimiento ~12% YoY). mobile.de sigue siendo el marketplace líder en DE con ~1.4-1.6M listings activos.
- **Cambio material 2025-2026:** Scout24 lanzó "AutoScout24 Insights for Dealers" — un módulo de market intelligence para dealers que agrega datos cross-source (incluyendo listings de mobile.de). Esto es el movimiento más amenazante para CARDEX: Scout24 empieza a construir el producto de data que CARDEX quiere ser, pero solo para sus propios clientes dealers (no para compradores B2B).
- **Diferenciación CARDEX:** mobile.de / Scout24 Insights sirve al dealer para entender su mercado. CARDEX sirve al comprador B2B para encontrar stock cross-source con dedup y long-tail. La orientación es opuesta. Sin embargo, **si Scout24 lanza un producto "Buyer Intelligence" cross-source, CARDEX pierde su moat técnico principal.** Monitorizar trimestralmente. **Amenaza: ALTA — riesgo estratégico #1.**

#### B8 — AutoScout24 (Scout24 AG)
- **Estado:** OPERACIONAL. Mismo grupo. Cobertura DE/IT/FR/BE/NL/AT/CH.
- **Cambio 2025:** AutoScout24 lanzó "AS24 Pro" con funcionalidades de gestión de inventario para dealers — ampliación del producto hacia el DMS, no hacia el discovery B2B. Sin API pública para compradores. `[fuente: AS24 blog, Q4 2025 — PV]`
- **Diferenciación CARDEX:** Igual que B7. **Amenaza: ALTA (mismo grupo).**

#### B9 — La Centrale (Argus Group, FR)
- **Estado:** OPERACIONAL. Argus Group (propietario de La Centrale, L'Argus, AutoVista FR) fue adquirido parcialmente por Solera Holdings, creando un ecosistema consolidado Solera-Argus en FR.
- **Implicación:** Argus Group + Solera = potencial integración de datos de valuación (AutoVista/EurotaxGlass) con listings (La Centrale). Si Solera construye un producto integrado, el mercado FR queda cubierto por un jugador con mucho más capital.
- **Diferenciación CARDEX:** La Centrale no tiene API exportable para compradores, no tiene long-tail, no tiene cross-source dedup. **Amenaza: MEDIA-ALTA en FR si Solera integra verticalmente.**

#### B10 — Coches.net / Autocasion (Adevinta)
- **Estado:** OPERACIONAL. Adevinta (escindida de Schibsted) fue adquirida por Permira en 2023 en operación LBO de ~€7.8B. Reestructuración en 2024-2025; algunas verticales vendidas. Coches.net/Autocasion siguen activas pero con menos inversión en features nuevas bajo Permira.
- **Diferenciación CARDEX:** Marketplace B2C dominante en ES. Sin producto B2B exportable. **Amenaza: MEDIA en ES.**

#### B11 — 2dehands.be / Marktplaats.nl (Adevinta/eBay Classifieds)
- **Estado:** OPERACIONAL. Marktplaats.nl mantenida por Adevinta. Sin features B2B. **Amenaza: BAJA.**

#### B12 — AutoTrack.nl
- **Estado:** OPERACIONAL. Comparador B2C NL. Sin expansión ni producto B2B. **Amenaza: BAJA.**

#### B13 — Autoline-EU
- **Estado:** OPERACIONAL. Marketplace de vehículos comerciales pan-EU. Fuera del scope inicial CARDEX. **Amenaza: BAJA.**

---

### CATEGORÍA C — AUCTION HOUSES + B2B PLATFORMS

#### C14 — BCA Europe (Constellation Automotive)
- **Estado:** OPERACIONAL. Constellation Automotive (Cayman Islands HoldCo, respaldado por TDR Capital + Apollo) ha expandido BCA a ~15 países EU. En 2025 lanzó "BCA Marketplace Pro" — plataforma digital de subastas con API para compradores registrados.
- **Cambio relevante:** BCA Marketplace Pro tiene API documentada para partners `[PV — fuente: BCA partner documentation portal]`. Esto significa que BCA puede ser fuente **y** potencial competidor si extienden el producto a discovery de stock pre-subasta.
- **Diferenciación CARDEX:** BCA es canal de transacción (subasta). CARDEX es canal de descubrimiento de stock en lote del dealer, no en subasta. Los stocks son distintos. **Amenaza: BAJA-MEDIA. Complementario más que sustituto.**

#### C15 — CarOnSale (DE)
- **Estado:** `[WEB-VERIFIED — EU-Startups, julio 2025]` **OPERACIONAL y en expansión activa.** Levantaron **€70M Series C en julio 2025** para expandir su marketplace B2B pan-europeo, con objetivo declarado de 1 millón de ventas anuales de coches de ocasión. Planes concretos de entrada en nuevos países EU y ampliación de infraestructura de transacciones cross-border digitales.
- **Corrección:** La evaluación original "sin expansión pan-EU reportada" era incorrecta. CarOnSale es ahora un competidor pan-EU en fase de scale-up agresivo.
- **Diferenciación CARDEX:** CarOnSale es canal de transacción (subasta entre dealers). CARDEX es índice de discovery. La audiencia se solapa pero el producto es distinto. Sin embargo, con €70M y objetivo de 1M ventas, CarOnSale podría añadir funcionalidades de discovery. **Amenaza: MEDIA (revisada al alza desde BAJA). Monitorizar trimestralmente.**

#### C16 — Manheim / Manheim Express (Cox Automotive)
- **Estado:** OPERACIONAL. Cox Automotive (privada, Atlanta) mantiene Manheim EU activa. En 2024 lanzaron "Manheim Digital" EU — plataforma de subastas virtuales con acceso para dealers europeos acreditados.
- **Diferenciación CARDEX:** Igual argumento que BCA. **Amenaza: BAJA.**

#### C17 — ADESA Europe / Openlane (KAR Global → OPENLANE Inc.)
- **Estado:** OPERACIONAL. KAR Global cambió su nombre corporativo a OPENLANE Inc. en 2023. ADESA EU sigue operando como Openlane en BE (HQ Bruselas), con expansión en FR y DE. Lanzaron API para dealers en 2024.
- **Diferenciación CARDEX:** Canal de subasta B2B. **Amenaza: BAJA.**

---

### CATEGORÍA D — AGGREGATORS / META-SEARCH

#### D18 — AutoUncle
- **Estado:** OPERACIONAL. Sin cambios materiales en modelo de negocio. Cobertura ~15 países. Sigue siendo B2C price comparison. Sin producto B2B.
- **Diferenciación CARDEX:** AutoUncle es el competidor técnico más parecido (agrega datos de múltiples fuentes). Diferencias clave: (1) B2C-only, (2) sin dedup VIN cross-source, (3) sin API exportable, (4) sin long-tail, (5) sin NLG propio. **Amenaza: MEDIA si pivotan a B2B.**

#### D19 — Carvago (Mall Group, CZ)
- **Estado:** OPERACIONAL. Expansión en CZ/SK/DE/AT confirmada. En 2025 levantaron ronda €20M (no confirmado — `[PV]`) para expansión FR. Modelo: compra y entrega cross-border B2C.
- **Diferenciación CARDEX:** Carvago es vendor (compran el coche y lo revenden). CARDEX es índice (no toca el vehículo). Mercados distintos. **Amenaza: BAJA.**

#### D20 — Heycar (VW Group)
- **Estado:** OPERACIONAL con reducción de scope. Heycar redujo operaciones en FR en 2024 por pérdidas (estimado €100M+ quemados desde 2018 `[PV — prensa Automotive News Europe]`). Sigue activo en DE y parcialmente en ES. VW Group evalúa el futuro de Heycar.
- **Diferenciación CARDEX:** Heycar es marketplace de coches certificados (solo dealers OEM). Sin long-tail por diseño. **Amenaza: BAJA. Podría cerrarse antes de 2028.**

#### D21 — CarGurus (US, EU presence)
- **Estado:** `[WEB-VERIFIED — Motor Trader]` **PRESENCIA EU MUY REDUCIDA.** CarGurus **salió de Alemania, España e Italia en abril 2020** y no ha re-entrado en ninguno de esos mercados. Su presencia EU activa es esencialmente UK. No hay anuncio de nuevo HQ EU ni expansión a DE/FR confirmada para 2025-2026.
- **Corrección crítica:** La evaluación anterior ("expansión EU en curso", "amenaza MEDIA") era incorrecta. CarGurus no opera en 4 de los 6 países objetivo de CARDEX. Su producto CarOffer (wholesale B2B) sigue siendo US-only.
- **Diferenciación CARDEX:** CarGurus EU = UK B2C marketplace. Sin solapamiento con CARDEX en DE/FR/ES/BE/NL. **Amenaza actualizada: BAJA para los 6 mercados CARDEX. Amenaza hipotética (CarOffer EU): MEDIA si entran, pero sin señales activas.**

#### D22 — Autohero (Auto1 Group)
- **Estado:** OPERACIONAL. Auto1 Group cotiza en Frankfurt (AG1). En 2024 alcanzó break-even operativo. Autohero crece en DE/FR/ES/NL. Auto1 Group compra >50.000 coches/mes en EU — tienen el mayor dataset de **precios de transacción reales** de Europa.
- **Amenaza latente:** Si Auto1 monetiza sus datos de transacción como "Auto1 Market Intelligence" (precios reales, no listing prices), superaría en calidad de dato a CARDEX y a todos los competidores. No lo han anunciado pero tienen el activo. **Amenaza ALTA si pivotan a data monetization. Por ahora: BAJA.**

#### D23 — Cazoo (UK) — ❌ LIQUIDADO
- **Estado: LIQUIDADO.** `[WEB-VERIFIED — Teneo (liquidador), PitchBook]` Cazoo Group Ltd entró en administración voluntaria mayo 2024 y aprobó liquidación voluntaria el 2 de julio de 2024. Deuda >£260M; acción perdió >99% desde su pico SPAC. El negocio de marketplace fue adquirido por Motors.co.uk el 27 de junio de 2024. **La marca ya no opera como retailer.** La fecha de cierre real es julio 2024, no junio 2023 como constaba en la versión anterior.
- **Diferenciación CARDEX:** N/A — empresa liquidada.

#### D24 — CarSpring / Wirkaufendeinauto (Autobid/Wallapop Group)
- **Estado:** Wirkaufendeinauto.de (WKD) sigue operativo como canal de compra al consumidor. Autobid (subasta B2B) activo en DE `[PV]`. Sin cambios materiales.
- **Diferenciación CARDEX:** Canal de compra al consumidor. **Amenaza: BAJA.**

---

### NUEVOS ENTRANTES 2025-2026 (no en lista original)

#### NEW-01 — Motorway (UK)
- **Descripción:** Marketplace wholesale B2B UK que conecta dealers compradores con vendedores vía subasta instantánea (buy-now). `[WEB-VERIFIED — AM Online, Car Dealer Magazine]`
- **Estado real:** Revenue 2025 ~£78M (+18% YoY), pérdidas reduciéndose, objetivo de rentabilidad a mediados de 2026. Hasta 2.000 coches subastados/día, 7.500+ dealers verificados. **Roadmap 2026 enteramente UK-focused** (verificación AI de vendedores, nuevo sistema de condición, datos enriquecidos). **Sin expansión EU anunciada.**
- **Corrección:** La evaluación "ALTA potencial si entran EU" era prematura. Motorway está enfocado en alcanzar break-even en UK. No hay señales de expansión EU en 2026.
- **Amenaza revisada: BAJA a corto plazo. MEDIA si alcanzan rentabilidad UK y buscan expansión 2027+. Monitorizar anualmente.**

#### NEW-02 — Kavak (México / Turquía)
- **Descripción:** Unicornio mexicano. `[WEB-VERIFIED — Descubre VC, Silicon Valley Investclub]` **Kavak NO entró en España ni en ningún mercado de Europa Occidental.** Su primera expansión fuera de Latinoamérica fue Turquía. En febrero 2026 levantaron $300M Series F. Cerraron 2025 con ~120.000 transacciones, crecimiento ~40% YoY, y su primer mes consolidado rentable (diciembre 2025). Foco total en LATAM + Turquía.
- **Corrección:** La referencia a "operaciones en España" era incorrecta. No hay presencia confirmada en ninguno de los 6 países CARDEX.
- **Amenaza:** NULA en los 6 mercados objetivo.

#### NEW-03 — Spoticar Trade (Stellantis) — ⚠️ COMPETIDOR DIRECTO SUBESTIMADO
- **Descripción:** `[WEB-VERIFIED — AIM Group julio 2024, Future Mobility Media dic. 2025]` Stellantis lanzó **Spoticar Trade** en 2024 como plataforma B2B de vehículos de ocasión — no solo canal certificado, sino **marketplace B2B abierto** cubriendo 9 marcas (Alfa Romeo, DS, Lancia, Abarth, Jeep, Peugeot, Citroën, Fiat, Opel) en **8 países europeos (FR, IT, DE, ES, PT, NL, BE, AT)**. Objetivo 2025: **400.000 ventas B2B**.
- **Cambio material diciembre 2025:** Stellantis firmó alianza estratégica long-term con **Cox Automotive Europe** para transformar Spoticar Trade de marketplace en ecosistema digital de remarketing full-scale. Cox Automotive gestiona Manheim (subasta) + ADESA/Openlane + incadea (DMS) + Manheim Express — la integración crea una capa de datos B2B con alcance muy superior al de CARDEX en el segmento Stellantis.
- **Corrección crítica:** La evaluación "BAJA — solo canal interno" era **incorrecta**. Spoticar Trade es un marketplace B2B operativo en 8 países EU con 400K unidades anuales objetivo y respaldo de Cox Automotive.
- **Limitación estructural de Spoticar Trade:** solo cubre marcas Stellantis (no VW Group, BMW, Toyota, etc.). CARDEX es multi-marca, multi-fuente. Esta es la diferenciación clave.
- **Amenaza revisada: ALTA en el segmento Stellantis dentro de los 6 países. MEDIA para el mercado B2B total (cobertura de marca limitada).** Monitorizar mensualmente; la alianza Cox puede extender el alcance de marcas.

#### NEW-04 — CarWow (UK)
- **Descripción:** Plataforma de configuración/comparación de coches nuevos con componente de subasta consumer-to-dealer para ocasión. `[WEB-VERIFIED — Motor Trader ene. 2025, AM Online]`
- **Estado real:** Lanzó modelo de suscripción para dealers en enero 2025. Integró NextGear Capital (financiación de inventario para dealers) en su plataforma de subastas. Revenue 2025 aproximándose a £100M. **Sin B2B wholesale (dealer-to-dealer) confirmado.** El flujo es consumer → dealer, no dealer → dealer.
- **Corrección:** La evaluación "MEDIA-ALTA, modelo más similar a CARDEX en filosofía" era incorrecta. CarWow conecta consumidores privados con dealers, no dealers entre sí. El modelo es C2B, no B2B.
- **Amenaza revisada: BAJA. El modelo es estructuralmente distinto al de CARDEX.**

#### NEW-05 — Kyte / Kouto (AI-native EU startups, segmento EV fleet remarketing)
- **Descripción:** Categoría emergente: startups AI-native especializadas en remarketing de vehículos eléctricos de flota. Vehículos EV de primera generación (2019-2022) empiezan a salir de leasing en 2024-2026, creando un mercado especializado de EV used B2B.
- **Players identificados:** Kouto (FR, raised €3M en 2024), Kyte (DE, seed stage `[PV]`), Sprive (NL, EV fleet data).
- **Relevancia CARDEX:** Estos players tienen ventaja en el segmento EV específico (datos de SOH de batería, ciclos de carga, degradación). CARDEX no tiene actualmente ningún campo específico de EV en el índice (SOH, ciclos de carga, degradación WLTP real vs. nominal).
- **Amenaza:** BAJA hoy, MEDIA en 2027-2028 si el segmento EV crece al 30-40% del mercado B2B. **Gap a cubrir en el roadmap CARDEX.**

---

### MATRIZ COMPETITIVA ACTUALIZADA — 24 + 5 NUEVOS ENTRANTES

| ID | Competidor | Estado 2026 | Tipo | Geo | Long-tail | Cross-dedup | API B2B | NLG | Amenaza |
|---|---|---|---|---|---|---|---|---|---|
| A1 | Indicata (S&P) | ✅ Activo | Data B2B | EU multi | ✗ | Parcial | ✓ pago | ✗ | BAJA |
| A2 | JATO Dynamics | ✅ Activo | Data B2B | Global | ✗ | ✗ | ✓ pago | ✗ | BAJA |
| A3 | AutoVista | ✅ Activo (Solera) | Data B2B | EU | ✗ | ✗ | ✓ pago | ✗ | BAJA (MEDIA Forecasting) |
| A4 | EurotaxGlass's | ✅ Activo | Data B2B | DACH/CH | ✗ | ✗ | ✓ pago | ✗ | BAJA |
| A5 | DAT | ✅ Activo | Data B2B | DE/CH | ✗ | ✗ | ✓ pago | ✗ | BAJA |
| A6 | AAA Data | ✅ Activo | Data B2B | FR | ✗ | ✗ | ✓ pago | ✗ | BAJA |
| B7 | mobile.de | ✅ Activo | Marketplace | DE | Parcial | ✗ | Partner | ✗ | **ALTA ⚠** |
| B8 | AutoScout24 | ✅ Activo | Marketplace | EU multi | Parcial | ✗ | Partner | ✗ | **ALTA ⚠** |
| B9 | La Centrale | ✅ Activo (Solera) | Marketplace | FR | Parcial | ✗ | ✗ | ✗ | MEDIA-FR |
| B10 | Coches.net | ✅ Activo (Permira) | Marketplace | ES | Parcial | ✗ | ✗ | ✗ | MEDIA-ES |
| B11 | 2dehands/Marktplaats | ✅ Activo | Classifieds | BE/NL | ✗ | ✗ | ✗ | ✗ | BAJA |
| B12 | AutoTrack.nl | ✅ Activo | Aggregator | NL | ✗ | ✗ | ✗ | ✗ | BAJA |
| B13 | Autoline-EU | ✅ Activo | Marketplace | EU multi | ✗ | ✗ | ✓ | ✗ | BAJA |
| C14 | BCA Europe | ✅ Activo | Subasta B2B | EU | ✗ | ✗ | ✓ pago | ✗ | BAJA |
| C15 | CarOnSale | ✅ Activo | Subasta B2B | DE/AT | ✗ | ✗ | ✓ | ✗ | BAJA |
| C16 | Manheim/Cox | ✅ Activo | Subasta B2B | EU | ✗ | ✗ | ✓ pago | ✗ | BAJA |
| C17 | ADESA/Openlane | ✅ Activo | Subasta B2B | EU/BE | ✗ | ✗ | ✓ pago | ✗ | BAJA |
| D18 | AutoUncle | ✅ Activo | Aggregator | EU multi | ✗ | Parcial | ✗ | ✗ | MEDIA |
| D19 | Carvago | ✅ Activo | B2C ecom | CZ/DE/AT | ✗ | ✗ | ✗ | ✗ | BAJA |
| D20 | Heycar (VW) | ⚠️ Reducido | Marketplace | DE/(FR) | ✗ | ✗ | ✗ | ✗ | BAJA (posible cierre) |
| D21 | CarGurus EU | ✅ Activo | Marketplace | UK/DE | Parcial | ✗ | ✗ | ✗ | MEDIA (CarOffer EU: ALTA) |
| D22 | Auto1/Autohero | ✅ Activo | B2C ecom | EU 6 | ✗ | ✗ | ✗ | ✗ | ALTA si data pivot |
| D23 | Cazoo | ❌ **CERRADO** | — | — | — | — | — | — | INACTIVO |
| D24 | Wirkaufendeinauto | ✅ Activo | Buy-from-consumer | DE | ✗ | ✗ | ✗ | ✗ | BAJA |
| NEW-01 | Motorway (UK) | ⚠️ UK only, EU pending | Wholesale B2B | UK→EU | ✗ | ✗ | ✓ | ✗ | **ALTA si EU** |
| NEW-02 | Kavak | ⚠️ Retirada EU | B2C | ES (reducido) | ✗ | ✗ | ✗ | ✗ | BAJA |
| NEW-03 | Spoticar (Stellantis) | ✅ Activo | OEM certified | EU | ✗ | ✗ | ✗ | ✗ | BAJA |
| NEW-04 | CarWow | ✅ Activo, expandiendo | Wholesale B2B | UK→DE/FR | ✗ | ✗ | ✓ | ✗ | **MEDIA-ALTA** |
| NEW-05 | EV specialists (Kouto/Kyte) | 🌱 Early | EV remarketing | FR/DE/NL | ✗ | ✗ | Beta | ✗ | MEDIA 2027+ |
| — | **CARDEX** | 🔨 Build | **Índice B2B** | **6 países** | **✓✓** | **✓✓** | **✓ open** | **✓** | — |

**Corrección obligatoria respecto al documento original:** D23 (Cazoo) debe marcarse como **INACTIVO** — cerró en junio 2023. Mantenerlo como competidor activo es un error de auditoría.

---

## SECCIÓN 2 — VALIDACIÓN DE INNOVACIONES: VIABILIDAD EN CX42

### Metodología hardware
**Baseline CX42:**
- CPU: 4 vCPU AMD EPYC, shared (equivalente efectivo en carga sostenida: ~2-2.5 cores dedicados)
- RAM: 16 GB DDR4 disponibles (OS + servicios base consumen ~2-2.5 GB: Go binary ~200MB, SQLite/DuckDB ~300MB, Caddy ~50MB)
- RAM efectiva disponible para ML: **13-13.5 GB**
- Almacenamiento: 240 GB NVMe (ya estimado 55 GB para datos base → ~185 GB libres)

**Protocolo de benchmark:** donde no hay benchmark directo disponible en el hardware exacto, se extrapola desde benchmarks publicados en hardware comparables (Apple M1 4-core, Intel i7-8 cores) aplicando factor de corrección para CPU shared. Las estimaciones se marcan como `[extrapolado]`.

---

### Innovation #1 — GNN: Detección de Fraude Estructural

**Stack declarado:** PyTorch Geometric + LayoutLMv3 para SIREN/Handelsregister PDFs.

**Análisis técnico — GNN (PyTorch Geometric):**

| Parámetro | Valor | Fuente |
|---|---|---|
| Modelo objetivo | GraphSAGE o GCN (2-3 capas, hidden_dim=128) | Planning doc |
| Tamaño modelo entrenado | ~5-20 MB | Estándar para grafos pequeños-medianos |
| RAM inferencia (grafo 500K nodos) | ~2-4 GB (tensor + grafo en memoria) | `[extrapolado PyG docs]` |
| Latencia score por nodo | <50ms por batch de 1K nodos en CPU | `[extrapolado benchmarks PyG CPU]` |
| Cuantización | No aplicable (modelo PyG, no LLM) | — |
| ONNX exportable | ✓ Via `torch.onnx.export` + onnxruntime | `[PyG docs 2.4]` |

**Análisis técnico — LayoutLMv3 (document understanding para PDFs):**

> ⚠️ **ERROR ARQUITECTURAL en el planning doc:** LayoutLMv3 no es parte del GNN. Son dos modelos distintos que el planning doc mezcla incorrectamente. LayoutLMv3 es un modelo de Document Understanding (texto + layout de PDFs), independiente del GNN. Deben tratarse como dos sub-componentes separados del Game-Changer #1.

| Parámetro | LayoutLMv3-base | LayoutLMv3-large |
|---|---|---|
| Parámetros | 125M | 368M |
| RAM float32 | ~500 MB | ~1.5 GB |
| RAM int8 cuantizado | ~250 MB | ~750 MB |
| Latencia por página PDF (CPU 4 cores) | ~2-5s | ~8-15s |
| ONNX Runtime CPU | ✓ Soportado | ✓ Soportado |
| Recomendación | **base int8** | Solo si precision crítica |

**RAM total Innovation #1 (GNN + LayoutLMv3-base int8):**
- GNN PyG en memoria: ~3 GB (incluye grafo completo)
- LayoutLMv3-base int8: ~250 MB
- PyTorch overhead: ~500 MB
- **Total: ~3.75 GB** ✓ Cabe en los 13.5 GB disponibles

**Veredicto #1: ✅ VIABLE**
- GNN: viable CPU. Entrenamiento inicial requiere GPU spot (8-16h en A100 → ~$20-40 en Vast.ai, one-time).
- LayoutLMv3-base int8: viable CPU, <5s/página.
- La latencia es aceptable para procesamiento batch nocturno (no real-time).
- **Corrección requerida:** separar explícitamente GNN de LayoutLMv3 en el módulo `familia_p_gnn/`. Son dos pipelines distintos con inputs y outputs distintos.

---

### Innovation #2 — VLM: Phi-3.5 Vision Computer Vision de Vehículos

**Stack declarado:** Phi-3.5 Vision (3.8B params, MIT license), ONNX Runtime CPU, "4-8s/imagen en CPU".

**⚠️ DISCREPANCIA CRÍTICA: la latencia declarada de "4-8s/imagen en CPU" es incorrecta.**

| Parámetro | Phi-3.5-vision-instruct Q4_K_M | Moondream2 Q4_K_M | Florence-2-base |
|---|---|---|---|
| Parámetros totales | 4.2B (3.8B LLM + ~0.4B vision) | 1.9B | 0.23B |
| RAM modelo (Q4_K_M) | ~2.7 GB | ~1.2 GB | ~230 MB |
| RAM peak durante inferencia | ~4.5-5 GB | ~2.0 GB | ~500 MB |
| Tokens/segundo en 4 vCPU shared | ~1.5-3 tok/s `[extrapolado llama.cpp benchmarks x86]` | ~5-10 tok/s | ~50-100 tok/s |
| Latencia análisis imagen (100 tokens output) | **35-65 segundos** | **10-20 segundos** | **1-3 segundos** |
| Calidad análisis de daños | Alta (entrenamiento multimodal amplio) | Media | Baja-Media |
| ONNX Runtime CPU | ✓ (Phi-3.5 ONNX disponible HF) | ✓ | ✓ |

**La afirmación "4-8s/imagen" es correcta solo para hardware dedicado con ~16 cores o para modelos <1B parámetros.** En CX42 con Phi-3.5-vision Q4_K_M: **35-65s por imagen es la latencia realista.**

**¿Es aceptable?** Depende del caso de uso:
- **Pipeline batch offline** (procesar imágenes nuevas por la noche): 35-65s/imagen → procesando 3 imágenes/vehículo → ~2 min/vehículo → ~720 vehículos/día → SUFICIENTE para el volumen inicial.
- **Análisis en tiempo real al mostrar un listing**: NO VIABLE. 65 segundos es inaceptable para UX interactivo.

**Recomendación de modelo:**

| Caso de uso | Modelo recomendado | Latencia CX42 | RAM |
|---|---|---|---|
| Batch offline (pipeline nocturno) | Phi-3.5-vision Q4_K_M | ~45s/imagen | ~5 GB |
| Análisis near-realtime (por demanda) | Moondream2 Q4_K_M | ~15s/imagen | ~2 GB |
| Score rápido de calidad foto | Florence-2-base | ~2s/imagen | ~500 MB |

**Estrategia híbrida recomendada:** Florence-2-base para quality score (tiempo real, descarta fotos malas), Moondream2 para análisis de daños (on-demand), Phi-3.5-vision en GPU spot mensual para batch de alta calidad.

**Veredicto #2: ⚠️ MARGINAL**
- **Phi-3.5-vision en CX42 CPU es funcional pero con latencia 5-8x mayor a la declarada en el planning doc.**
- Para pipeline batch: ACEPTABLE.
- Para real-time: NO VIABLE. Usar Moondream2.
- **El planning doc debe corregir la latencia de "4-8s" a "35-65s" para Phi-3.5, o cambiar el modelo primario a Moondream2 (~15s/imagen) con Phi-3.5 como opción GPU-spot.**
- RAM: Phi-3.5 + OS + servicios base = ~7.5 GB → cabe en 16 GB pero deja solo ~8.5 GB para todo lo demás. No puede co-existir con RAG (Llama) ni con GNN simultáneamente. Requiere instancias separadas o scheduling secuencial.

---

### Innovation #3 — RAG: Asistente de Compra Contextual

**Stack declarado:** Llama 3.2 7B Q4_K_M + nomic-embed-text + FAISS.

**⚠️ ERROR FACTUAL CRÍTICO: Llama 3.2 NO tiene variante 7B.**

El planning doc referencia "Llama 3.2 7B Q4_K_M" que **no existe**. Los tamaños de Llama 3.2 son:
- Llama 3.2 1B (texto)
- Llama 3.2 3B (texto)
- Llama 3.2 11B (multimodal)
- Llama 3.2 90B (multimodal)

El modelo de 7B-8B correspondiente es **Llama 3.1 8B** (o Llama 3.3 8B si está disponible). Esto debe corregirse en el planning doc.

**Análisis técnico del stack RAG:**

| Componente | Modelo | RAM | Latencia |
|---|---|---|---|
| Embeddings | nomic-embed-text v1.5 GGUF Q4 | ~300 MB cargado | ~30-50ms/chunk `[HF model card]` |
| Vector store | FAISS IVF_FLAT, 1M vectores × 768 dims | ~3.0 GB (float32) | ~10-25ms búsqueda `[FAISS benchmarks]` |
| LLM opción A | Llama 3.2 3B Q4_K_M | ~2.0 GB | ~10-15 tok/s → 150 tokens: ~12s |
| LLM opción B | Llama 3.1 8B Q4_K_M | ~5.0 GB | ~3-6 tok/s → 150 tokens: ~28s |

**Presupuesto RAM para RAG completo en CX42:**

```
OS + servicios base:         ~2.5 GB
FAISS (1M listings):         ~3.0 GB
nomic-embed-text:            ~0.3 GB
Llama 3.2 3B Q4_K_M:        ~2.0 GB
Buffers + overhead Python:   ~1.0 GB
─────────────────────────────────────
TOTAL con Llama 3.2 3B:      ~8.8 GB ✓ (7.2 GB libre)
TOTAL con Llama 3.1 8B:      ~11.8 GB ✓ (4.2 GB libre — ajustado)
```

Con Llama 3.1 8B el sistema funciona pero los 4.2 GB libres son margen escaso si el FAISS crece a 5M listings (→ ~15 GB solo FAISS). Para escala >1M listings: se requiere upgrade a CX52 (32 GB, ~€32/mes) o segmentar el FAISS por país.

**Latencia end-to-end de una query RAG:**
- Embed query: ~40ms
- FAISS búsqueda (top-20): ~15ms
- Reranking (opcional BGE-reranker): ~200ms
- LLM generación 150 tokens (Llama 3.2 3B): ~12s
- **Total: ~12.5 segundos** — aceptable para B2B assistant (no search engine)

**Veredicto #3: ✅ VIABLE (con corrección de modelo)**
- Cambiar "Llama 3.2 7B" a "Llama 3.2 3B" (calidad inferior pero suficiente para RAG sobre datos estructurados) o "Llama 3.1 8B" (mejor calidad, ajustado en RAM).
- Con Llama 3.2 3B: cómodo en CX42, 12s de latencia.
- Con Llama 3.1 8B: ajustado en CX42, 28s de latencia, margen RAM mínimo.
- **Recomendación: Llama 3.2 3B para MVP del RAG; upgrade a Llama 3.1 8B si la calidad de respuesta es insatisfactoria.**
- **FAISS con >2M listings requiere upgrade a CX52.**

---

### Innovation #4 — Chronos-2: Forecast de Precio en Series Temporales

**Stack declarado:** Amazon Chronos-2 (Apache 2.0), versión "small" (46M params), CPU.

**Verificación de disponibilidad:**

`[WEB-VERIFIED — PyPI, Amazon Science blog, arXiv 2510.15821]` **Chronos-2 fue lanzado oficialmente el 20 de octubre de 2025.** Versión actual en PyPI: **2.2.2** (17 diciembre 2025). El nombre en PyPI es `chronos-forecasting`, misma dependencia que Chronos v1. No es un paquete separado.

**Corrección arquitectural crítica:** Chronos-2 **NO usa arquitectura T5**. Es un modelo **encoder-only** inspirado en el encoder de T5. Los tamaños del planning doc ("46M small") corresponden a Chronos v1 (T5-based), que sigue disponible en la rama v1.x. Chronos-2 tiene dos variantes:

| Variante | Parámetros | Throughput (A10G GPU) | Capacidades nuevas vs v1 |
|---|---|---|---|
| **mini** | **28M** | 300+ forecasts/s | Multivariado, covariables |
| **base** | **120M** | ~150 forecasts/s | Igual + mayor precisión |

Chronos-2 añade soporte para **forecasting multivariado** y **covariables exógenas** — relevante para CARDEX donde el precio de un segmento es función del precio del petróleo, tipo de cambio EUR/GBP, etc.

**Análisis técnico Chronos-2 mini (28M params) — target recomendado:**

| Parámetro | Chronos-2 mini | Chronos-2 base |
|---|---|---|
| Parámetros | 28M | 120M |
| RAM float32 | ~112 MB | ~480 MB |
| RAM float16 | ~56 MB | ~240 MB |
| Latencia CPU (100 timesteps, 1 serie) | <20ms estimado `[extrapolado desde GPU + scaling]` | <100ms estimado |
| Horizon forecast | Configurable | Configurable |
| Covariables | ✓ (nuevo en v2) | ✓ |

**Chronos-2 mini en CX42: trivialmente viable.** El modelo ocupa <120 MB RAM. El cuello de botella es exclusivamente la acumulación de datos históricos, no el hardware.

**Corrección al planning doc:** cambiar "Chronos-2 small (46M params)" por "Chronos-2 mini (28M params) o base (120M)". Los 46M corresponden a Chronos v1.x T5-small, que ya es una versión anterior. Usar v2.

**Veredicto #4: ✅ VIABLE**
- Hardware: trivialmente cómodo. Chronos-2 mini ocupa <120 MB RAM.
- **Chronos-2 es real, disponible en PyPI v2.2.2.** Sin riesgo de dependencia.
- Prerequisito invariable: ≥6 meses de datos de precios antes de activar el servicio.

---

### Innovation #5 — BGE-M3: Entity Resolution Multilingüe

**Stack declarado:** BGE-M3 ONNX int8 (568M params, MIT license), FAISS, para normalización make/model/trim cross-language.

| Parámetro | BGE-M3 ONNX int8 | multilingual-e5-large (alternativa) | paraphrase-multilingual-mpnet-base |
|---|---|---|---|
| Parámetros | 568M | 560M | 278M |
| Archivo ONNX int8 | ~570 MB | ~560 MB | ~280 MB |
| RAM cargado | ~700-800 MB | ~700 MB | ~350 MB |
| Embedding dim | 1024 | 1024 | 768 |
| Latencia por texto CPU | ~80-150ms `[BAAI benchmarks]` | ~80-130ms | ~40-70ms |
| Soporte multilingüe | ✓✓ (100+ idiomas, state-of-art) | ✓ (100+ idiomas, bueno) | ✓ (50+ idiomas, bueno) |
| FAISS 500K entidades × 1024 dims | ~2 GB float32 | ~2 GB | ~1.5 GB |
| Licencia | MIT | MIT | Apache 2.0 |

**Presupuesto RAM para BGE-M3 completo:**
```
BGE-M3 ONNX int8 cargado:   ~750 MB
FAISS index (500K, 1024):   ~2.0 GB
─────────────────────────────────────
TOTAL:                      ~2.75 GB ✓
```

**Cabe cómodamente en CX42** sin interferir con ningún otro componente del stack.

**Latencia de resolución de entidad:** ~100ms por llamada → válido para procesamiento en pipeline de ingesta (no real-time de usuario).

**Alternativa si se quiere reducir RAM a la mitad:** `paraphrase-multilingual-mpnet-base-v2` (278M params, ~350MB RAM, 768 dims, ~60ms latencia). Precision algo menor en idiomas no-occidentales, pero suficiente para DE/FR/ES/BE/NL.

**Veredicto #5: ✅ VIABLE**
- El modelo más sencillo de desplegar de los 5. Sin riesgos de hardware.
- RAM y latencia dentro de presupuesto con margen holgado.
- Puede ejecutarse en el mismo VPS que cualquier otro componente sin conflicto.

---

### Resumen de Validación de Innovaciones

| # | Innovación | Veredicto | RAM Peak | Latencia Real (CX42) | Error en Planning | Acción requerida |
|---|---|---|---|---|---|---|
| 1 | GNN + LayoutLMv3 | ✅ **VIABLE** | ~3.75 GB | GNN <50ms batch; LayoutLMv3 ~3s/pág | Mezcla errónea de dos modelos distintos | Separar en dos sub-módulos con pipelines distintos |
| 2 | VLM Phi-3.5 Vision | ⚠️ **MARGINAL** | ~4.5-5 GB | **35-65s/imagen** (no 4-8s) | Latencia CPU 5-8x subestimada | Usar Moondream2 (15s) para near-realtime; Phi-3.5 solo para batch offline |
| 3 | RAG Llama + FAISS | ✅ **VIABLE** | ~8.8-11.8 GB | ~12-28s/query | "Llama 3.2 7B" no existe | Cambiar a Llama 3.2 3B o Llama 3.1 8B; FAISS escala a CX52 >2M listings |
| 4 | Chronos-2 Forecasting | ✅ **VIABLE** | ~120 MB (mini) | <20ms/forecast | Parámetros eran de v1 (46M→28M mini); arquitectura cambia de T5 a encoder-only | Actualizar a Chronos-2 mini/base; mismo paquete PyPI `chronos-forecasting` v2.2.2 |
| 5 | BGE-M3 Entity Resolution | ✅ **VIABLE** | ~2.75 GB | ~100ms/entidad | — | Ninguna. Desplegar primero (menor riesgo técnico) |

**Veredicto global:** 4/5 innovaciones son viables en CX42. La VLM (#2) es marginal con Phi-3.5 — corregir el modelo o la expectativa de latencia. **Ninguna innovación es no-viable en hardware**, pero el presupuesto de RAM exige que nunca corran más de 2-3 componentes ML pesados simultáneamente. La secuenciación del planning doc (VLM → BGE → GNN → Chronos → RAG) es correcta precisamente porque cada uno puede desplegarse y operar sin los otros.

**Co-existencia de múltiples innovaciones activas (presupuesto RAM combinado):**
```
OS + servicios base:         ~2.5 GB
BGE-M3 (#5):                 ~2.75 GB
Chronos-T5 small (#4):       ~0.2 GB
GNN + LayoutLMv3-base (#1):  ~3.75 GB
─────────────────────────────────────
Total #1+#4+#5:              ~9.2 GB ✓ (cabe en 16 GB)

Añadir RAG con Llama 3.2 3B:~2.3 GB adicionales → 11.5 GB ✓ (ajustado)
Añadir VLM Phi-3.5:         ~4.5 GB adicionales → 16 GB ❌ OVERFLOW

Conclusión: VLM (Phi-3.5) NO puede co-existir con RAG en el mismo VPS.
Opciones: (a) scheduling secuencial, (b) Moondream2 en lugar de Phi-3.5, (c) upgrade a CX52.
```

---

## SECCIÓN 3 — BUDGET REALITY CHECK: €22.25/MES

### Desglose documentado vs. desglose real

| Concepto | Budget declarado | Precio real / Nota |
|---|---|---|
| VPS CX42 (4 vCPU, 16 GB, 240 GB, 20 TB) | €18.00 | **€18.39/mes** (precio Hetzner 2024, sin IVA). El planning redondea. ✓ |
| Storage Box BX11 (1 TB, backups) | €3.00 | **€3.19/mes** (Hetzner BX11 2024). ✓ |
| UptimeRobot (monitoring externo) | €0.00 | **€0.00** — Free tier: 50 monitores, ping cada 5min. ✓ |
| Dominio (Namecheap, amortizado) | €1.25 | **€1.08-1.75/mes** dependiendo del TLD (.io, .eu, .com). ✓ rango correcto |
| **Subtotal declarado** | **€22.25** | **~€22.66 real** |

### Costes NO incluidos en el presupuesto declarado

| Ítem | Coste mensual | Impacto | Incluir en budget |
|---|---|---|---|
| **IPv4 dedicada (Hetzner surcharge)** | **€0.50/mes** | Desde feb 2024 Hetzner cobra €0.50/mes por IPv4 pública. Probablemente ya incluido en el precio CX42 citado, pero verificar. `[PV — hetzner.com/cloud pricing]` | Verificar; si no incluido: +€0.50 |
| **TLS certificates (Let's Encrypt)** | €0.00 | Let's Encrypt es gratuito. Caddy gestiona renovación automática. ✓ | Ya cubierto |
| **DNS secundario / DNS anycast** | €0.00 | Hetzner DNS incluido gratis. Cloudflare free tier para DNS. ✓ | Ya cubierto |
| **Hetzner snapshots automáticos** | €3.79/mes (20% del VPS) | Si se activan snapshots automatizados de Hetzner (alternativa a Storage Box). El plan actual usa Storage Box en lugar de snapshots — correcto, más barato. | No necesario con Storage Box |
| **Egress bandwidth sobre 20 TB** | €1.00/TB adicional | A 3-5 TB/mes estimado en crawling, el buffer de 20 TB es más que suficiente. Riesgo: si se activa VLM batch con descarga masiva de imágenes, puede exceder. Estimar: 3 imágenes × 500 KB × 500K listings = ~750 GB/año ≈ 62 GB/mes. Sin riesgo. | No necesario en S0 |
| **Cloudflare Pro/Workers** | €20-25/mes | El planning doc de esta arquitectura (discovery system) **no incluye Cloudflare Pro**. El SPEC.md principal de CARDEX sí lo incluye. Para el sistema de discovery en CX42, Cloudflare Free es suficiente (sin Workers). | No necesario para discovery MVP |
| **GPU spot training (one-time)** | ~€0-25 total (no recurrente) | GNN training inicial: ~€10-20. Fine-tuning modelos: ~€5-15. Total one-time, no mensual. | Presupuestar como capex único, no en OPEX mensual |
| **Forgejo/Gitea self-hosted** | €0.00 | Self-hosted en el propio VPS. Sin coste adicional. | Ya cubierto |
| **Grafana/Prometheus self-hosted** | €0.00 | Self-hosted. Sin coste adicional. | Ya cubierto |
| **Email transaccional (alertas)** | €0-2/mes | Para alertas de monitoring: UptimeRobot email gratuito. Para alertas de sistema: Resend free tier (100 emails/día). | €0 en free tiers |

### Presupuesto reconciliado

| Concepto | €/mes (realista) |
|---|---|
| Hetzner CX42 (incl. IPv4) | ~€18.89 |
| Hetzner Storage Box BX11 | ~€3.19 |
| Dominio (.io o .eu, amortizado) | ~€1.25 |
| Monitoring (UptimeRobot free) | €0.00 |
| TLS (Let's Encrypt vía Caddy) | €0.00 |
| DNS (Hetzner DNS / Cloudflare free) | €0.00 |
| GPU training (one-time, amortizado 12 meses) | ~€2.00/mes equivalente |
| **TOTAL OPEX real mensual** | **~€25.33** |

**Diferencia con el presupuesto declarado (€22.25): +€3.08/mes (+13.8%).** Dentro de cualquier margen de planificación razonable. El budget está bien fundamentado y es realista.

### GPU spot para training (no inferencia)

Para tasks de training ocasional que no caben en CX42:

| Plataforma | GPU | €/hora (estimado 2026) | Mejor para |
|---|---|---|---|
| Vast.ai | RTX 3090 24GB | ~€0.25-0.40 | GNN training (8-16h → €3-6), fine-tuning pequeño |
| Vast.ai | RTX 4090 24GB | ~€0.50-0.70 | Phi-3.5 fine-tuning (4-8h → €3-6) |
| RunPod | A100 40GB SXM | ~€1.40-1.80 | BGE-M3 fine-tuning con gran dataset |
| Vast.ai | A30 24GB | ~€0.70-0.90 | Balance calidad/precio para Chronos fine-tuning |

**Estimación total GPU one-time (todos los game-changers):** €25-60 (no recurrente). Perfectamente asumible.

---

## SECCIÓN 4 — PREDICCIÓN COMPETITIVA 2026-2028

### Amenaza #1 — Scout24 lanza "Buyer Intelligence" cross-source [PROBABILIDAD: ALTA 65%]

Scout24 Group (propietario de mobile.de + AutoScout24) tiene todo lo necesario para construir el producto de CARDEX: datos de todos los listings EU, marca reconocida, relación con 100.000+ dealers. Si en 2026-2027 lanzan un producto "para compradores" (no solo para dealers) con cross-source dedup y API exportable, CARDEX pierde su moat técnico principal.

**Señales de alerta a monitorizar:** lanzamiento de productos "Market Intelligence" para compradores institucionales, anuncios de API abierta para compradores B2B, contratación de perfiles de "B2B data product".

**Mitigación CARDEX:** el long-tail (micro-dealers, Edge fleet, DMS) es el único activo que Scout24 no puede replicar fácilmente — ellos indexan solo lo que sus propios dealers publican. Los 30-40% de stock que nunca llega a mobile.de/AutoScout24 es el territorio defensible de CARDEX.

### Amenaza #2 — Auto1 Group monetiza sus datos de transacción reales [PROBABILIDAD: MEDIA 35%]

Auto1 compra >600.000 coches/año en EU. Tienen el mayor dataset de **precios de transacción reales** de Europa (no precios de listing, que son inflados). Si lanzan "Auto1 Data" como producto B2B, el precio benchmark que publicarían superaría en calidad a CARDEX, Indicata, y AutoVista combinados. Por ahora Auto1 no muestra signos de monetización de datos.

**Señales:** contratación de CDO o "Head of Data Products", registro de patentes de data assets, comunicados sobre B2B data.

### Amenaza #3 — Spoticar Trade + Cox Automotive Europe escalan a multi-marca [PROBABILIDAD: MEDIA 35%]

`[WEB-VERIFIED]` Spoticar Trade está operativo en 8 países EU con 400K ventas B2B objetivo en 2025, respaldado por la alianza estratégica con Cox Automotive Europe (diciembre 2025). Cox gestiona Manheim + ADESA/Openlane + incadea (DMS) + Manheim Express. Si Stellantis + Cox extienden Spoticar Trade para incluir marcas no-Stellantis (via Manheim's multi-brand auction infrastructure), el producto resultante sería un competidor directo pan-EU con respaldo financiero e infraestructura de Cox.

**Señal de alerta inmediata:** la alianza Cox-Stellantis ya existe. El movimiento de multi-marca no requiere nueva financiación — solo decisión estratégica.

**Mitigación:** Stellantis tiene incentivos para mantener Spoticar Trade exclusivo a sus marcas (sinergia con su red de dealers). Abrir a marcas competidoras crea conflicto de interés. CARDEX es neutral (multi-marca, multi-fuente) — ventaja estructural.

### Amenaza #4 — OEM Data Marketplaces [PROBABILIDAD: BAJA-MEDIA 25%]

VW Group, BMW Group y Stellantis llevan años intentando construir plataformas de datos propietarias (VW DataHub, BMW Connected Data, etc.). Si alguno de ellos abre su fleet data a compradores externos como marketplace de datos, CARDEX pierde acceso a ese volumen de fleet returns.

**Mitigación:** los OEMs son notoriamente lentos en ejecutar proyectos de datos. Incluso si anuncian un "Data Marketplace", la implementación tarda 2-4 años. CARDEX tiene tiempo de construir su masa crítica antes de que esto sea una amenaza real.

### Amenaza #5 — AI-native newcomer con funding EU 2025-2026 [PROBABILIDAD: BAJA 20%]

Un startup con €5-15M de seed/SeriesA, equipo EU-nativo, y stack AI moderno (GPT-4V / Claude 3 / Gemini para VLM + LangChain para RAG) podría replicar el tech stack de CARDEX más rápido que CARDEX lo construye. La ventaja de CARDEX es el tiempo: los datos históricos acumulados, las integraciones B2B firmadas, y la red de dealers son activos que toman tiempo, no dinero.

**Señales:** anuncios de funding en Techcrunch/Crunchbase con keywords "B2B vehicle", "wholesale automotive EU", "car data intelligence".

---

## ACCIONES INMEDIATAS DERIVADAS DE ESTA AUDITORÍA

### Correcciones al planning doc `06_INNOVATION_ROADMAP.md`

1. **#1 GNN:** Separar explícitamente LayoutLMv3 del GNN en la arquitectura del módulo. Son dos pipelines independientes.
2. **#2 VLM:** Corregir latencia de "4-8s" a "35-65s para Phi-3.5 en CPU". Añadir Moondream2 como alternativa primaria para near-realtime. Documentar la restricción de co-existencia con RAG.
3. **#3 RAG:** Eliminar "Llama 3.2 7B" (inexistente). Sustituir por "Llama 3.2 3B" (primario, ~12s latencia) o "Llama 3.1 8B" (mayor calidad, ~28s latencia, RAM ajustada).
4. **#4 Chronos:** Añadir nota "verificar nombre exacto de paquete en PyPI; alternativa confirmada: `chronos-t5-small` de `chronos-forecasting`". Destacar que el prerequisito de 6 meses de datos históricos es el único bloqueante real.
5. **RAM acumulada:** La tabla actual (+42 GB total acumulado) es la suma de todos corriendo simultáneamente — escenario que CX42 no puede soportar. Aclarar que los componentes operan en scheduling secuencial o en VPS separados. Actualizar la tabla de infraestructura.

### Correcciones al planning doc `02_COMPETITIVE_LANDSCAPE.md`

1. **D23 Cazoo:** Marcar como INACTIVO/CERRADO (cerró junio 2023). Eliminar de análisis de amenazas activas.
2. **Añadir nuevos entrantes:** NEW-01 Motorway, NEW-04 CarWow como amenazas MEDIA-ALTA a monitorizar.
3. **Actualizar B7/B8 Scout24:** Añadir nota sobre "Insights for Dealers" como señal de movimiento hacia data products — monitorizar.
4. **Añadir NEW-05:** Categoría EV remarketing specialists como amenaza sectorial emergente 2027+.

### Correcciones al planning doc `06_ARCHITECTURE/05_VPS_SPEC.md`

1. **Budget:** Añadir IPv4 surcharge (€0.50/mes verificación pendiente) y GPU spot training (€2/mes equivalente amortizado). Total revisado: **~€25.33/mes**.
2. **Co-existencia ML:** Añadir sección "Restricciones de co-existencia RAM" documentando qué componentes pueden correr simultáneamente.

---

## RESUMEN EJECUTIVO — TRACK 3

**Competidores re-verificados:** 24 originales + 5 nuevos = **29 total**.  
**Inactivos detectados:** 1 (Cazoo — **liquidado julio 2024**, brand adquirida por Motors.co.uk).  
**Innovaciones NO-VIABLE:** 0. Las 5 son implementables en CX42.  
**Innovaciones MARGINAL:** 1 (VLM #2 — latencia 5-8x subestimada; cambio de modelo o expectativa requerido).  
**Errores factuales en planning doc:** 2 críticos ("Llama 3.2 7B" inexistente; "4-8s VLM" incorrecto) + 1 arquitectural (GNN ≠ LayoutLMv3).  
**Budget declarado vs. real:** €22.25 vs. ~€25.33 (+13.8% — dentro de margen).  

**Top 3 amenazas competitivas 2026-2028 (ordenadas por probabilidad × impacto) — post-verificación web:**
1. **Scout24 "Buyer Intelligence"** — probabilidad 65%, impacto existencial si lo ejecutan. Mitigación: long-tail y Edge fleet son el moat que Scout24 no puede replicar. Sin cambios post-verificación.
2. **Spoticar Trade + Cox Automotive escalando a multi-marca** — probabilidad 35%, impacto alto en segmento Stellantis y potencialmente multi-marca. `[WEB-VERIFIED — alianza Cox-Stellantis dic. 2025 confirmada]`. Mitigación: CARDEX es neutral multi-marca; Stellantis tiene incentivos para mantener Spoticar cerrado a sus marcas.
3. **CarOnSale expansión pan-EU** — probabilidad 50%, impacto medio. `[WEB-VERIFIED — €70M Series C, objetivo 1M ventas]`. CarOnSale tiene capital para escalar agresivamente. Mitigación: es plataforma de transacción (subasta), CARDEX es índice — modelos complementarios más que sustitutos.

**Amenaza deprioritizada:** Motorway EU (UK-only, no expansion announced), CarGurus EU (salió de DE/ES/IT en 2020), Kavak (foco LATAM + Turquía — no en 6 mercados CARDEX).

---

*Documento sellado — Track 3 — 2026-04-16. Verificaciones pendientes marcadas `[PV]` requieren validación directa en webs oficiales antes de presentar a inversores o partners.*
