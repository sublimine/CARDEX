# CARDEX — Competitive Deep Dive Report — June 2026

**Fecha:** 2026-06-05
**Autor:** Strategic Research (AI-assisted)
**Clasificación:** Interno — Fundador
**Versión:** 1.0
**Complementa:** MARKET_OPPORTUNITIES_2026-06.md, INNOVATION_OPPORTUNITIES_2026-06.md

---

## Executive Summary

Este informe cubre cinco áreas críticas que los informes anteriores no auditaron:

1. **6 competidores directos de datos vehiculares** (TecAlliance, Autovista/Eurotax, DAT Group, Schwacke, Glass's, CAP HPI) — con pricing, gaps explotables, y puntos de entrada para CARDEX.
2. **6 marketplaces B2B de subastas online** (BCA, Manheim, ADESA/OpenLane, CarOnSale, AUTOonline, Autorola) — APIs, datos expuestos, y viabilidad de CARDEX como data provider.
3. **4 vectores regulatorios 2026-2027** con fechas exactas que crean demanda estructural nueva.
4. **Mapa de pricing de APIs de datos automotive** — lo que cobran los incumbentes por consulta/mes/volumen.
5. **12+ startups B2B automotive** que levantaron funding en 2025-2026, con montos, modelos de negocio, y señales de mercado.

**Hallazgo principal:** El mercado mid-market de datos vehiculares en Europa continental (entre el enterprise de Autovista a EUR 50K+/año y las APIs basura a EUR 20/mes) está estructuralmente vacío. CARDEX puede ocuparlo con pricing de EUR 99-999/mes sin competencia directa en datos de listings cross-border de 6 mercados.

---

## 1. COMPETIDORES DIRECTOS NO AUDITADOS

---

### 1.1 TecAlliance (TecDoc)

**Perfil:** Proveedor dominante de datos del aftermarket automotriz (recambios). Sede: Ismaning, Alemania. Propiedad de los principales fabricantes de recambios (VDA shareholders). Ranking #1 entre 91 competidores en su segmento.

**Qué venden:**
- **TecDoc Catalogue:** Base de datos de 1.150+ marcas de recambios, 254K+ tipos de vehículos, 636M+ linkages vehículo-pieza, 11,9M artículos.
- **Web Service API:** Integración de datos de recambios en aplicaciones third-party.
- **IDP Data Receiver API (2026):** API de actualización en tiempo real para proveedores de datos. Expansión a NTypes, ejes, cabinas, transmisión prevista para mediados de 2026.

**Pricing:**
- Suscripción modular. No publican precios fijos.
- Cotización individual basada en formato de datos y alcance.
- TecDoc Catalogue Garage Data y Garage Data Pro disponibles en su tienda online (precio no listado públicamente).
- Coste de membresía como data supplier: "muy alto, inasequible para pequeños fabricantes y distribuidores." Fuente: FactoryData.

**Gaps explotables:**
- **Solo aftermarket (recambios), NO datos de mercado de vehículos usados.** TecAlliance no indexa listings, no ofrece valuaciones, no tiene datos de pricing de vehículos usados.
- No puede analizar datos de marcas fuera de su ecosistema.
- Limitado a publicar lo que sus proveedores le envían — sin capacidad de enriquecimiento independiente.
- Descrito como "transatlántico con giros lentos y difíciles" — poca agilidad.
- Monopolio de facto crea frustración entre stakeholders pequeños.

**Entrada CARDEX:** Cero solapamiento. TecAlliance es recambios; CARDEX es vehículos usados. **Oportunidad de partnership**: CARDEX podría enriquecer datos TecDoc con contexto de mercado (qué vehículos están realmente en circulación y a qué precios) para talleres que necesitan ambas dimensiones. Alternativamente, los clientes de TecAlliance (talleres, distribuidores) son un canal de distribución natural para alertas de vehículos usados.

**Fuentes:**
- [TecAlliance — Automotive Data Solutions](https://www.tecalliance.net/)
- [TecAlliance Limitations — FactoryData](https://www.factorydata.com/en/tecalliance-limitations-of-the-most-used-technology-in-the-market/)
- [TecAlliance Company Profile — Tracxn](https://tracxn.com/d/companies/tecalliance/__V9QaGBnK6Tb3cxz0M-YA493Ehrjz8uI05FRC5Ac3kGY)

---

### 1.2 Autovista Group (Eurotax)

**Perfil:** Propiedad de J.D. Power (adquirida Sep 2023). Revenue estimado: USD 178,8M/año. ~445 empleados en 3 continentes. Sede: Londres. Opera Autovista (internacional), Glass's (UK), Eurotax (Europa continental).

**Qué venden:**
- **Autovista API:** Specs, valuaciones, SMR, forecasts. Integración directa en sistemas de terceros.
- **Eurotax Applications:** Datasets de valuación para 22+ mercados europeos. Integración con sistemas de negocio de dealers.
- **Eurotax Data:** Datos de pricing y specs para integración en plataformas.
- **Residual Value Intelligence (REFORECAST):** Predicción de residuales a 120 meses. Enterprise-only.
- **Indicata (via Autorola Group, pero con datos Autovista):** BI de vehículos usados en 14 países. Monitoreo en tiempo real de clasificados, OEM websites, dealer websites.

**Pricing:**
- "Unlimited use, one subscription, no hidden fees" — pero el precio base es enterprise.
- Estimaciones de mercado: EUR 5.000-50.000+/año dependiendo del alcance. Fuente: informes anteriores CARDEX y referencias de la industria.
- Indicata/Autorola: USD 3.800-5.800/año para dealers (fuente: INNOVATION_OPPORTUNITIES report).
- No publican tarifas en su web. Cotización obligatoria.

**Gaps explotables:**
- **Pricing enterprise inaccesible para dealers SME.** Un dealer independiente con 50-100 vehículos no puede pagar EUR 5K+/año por datos de mercado.
- **Foco en valuación, no en arbitraje cross-border.** Autovista dice cuánto vale un vehículo, pero no dónde comprarlo más barato.
- **Sin datos de dealer websites individuales.** Autovista agrega datos de marketplaces centrales (AutoScout24, mobile.de, LaCentrale), no de sitios web de dealers directos. CARDEX indexa dealer websites, un dataset diferente y complementario.
- **Sin alertas push.** Indicata es dashboard/reporting, no notificaciones proactivas.
- Actividad de mercado descrita como "very low" en algunos análisis. Fuente: Owler.

**Entrada CARDEX:**
- **Precio:** CARDEX puede ofrecer un subconjunto de datos competitivo a EUR 99-299/mes vs. EUR 5K+/año de Autovista.
- **Nicho:** Arbitraje cross-border dealer-level es un producto que Autovista no tiene.
- **Datos complementarios:** Datos de dealer websites directos vs. datos de marketplaces centrales.
- **Riesgo:** J.D. Power tiene recursos para bajar precios si ve amenaza. Pero su modelo enterprise no se adapta fácilmente al mid-market sin canibalizar.

**Fuentes:**
- [Autovista API](https://autovista.com/product/autovista-api/)
- [Autovista Group Revenue — Growjo](https://growjo.com/company/Autovista_Group)
- [Autovista Group — Owler](https://www.owler.com/company/autovistagroup)
- [Eurotax Applications](https://www.autovistagroup.com/index.php/products-and-services/eurotax-applications)

---

### 1.3 DAT Group (SilverDAT)

**Perfil:** Deutsche Automobil Treuhand. Fundada en 1931. Intermediario neutral entre VDA (fabricantes), VDIK (importadores), y ZDK (comercio automotriz). Sede: Ostfildern, Alemania. Estándar de facto para valuaciones en Alemania.

**Qué venden:**
- **SilverDAT 3:** Plataforma integrada de valuación de vehículos, cálculo de costes de reparación, identificación por VIN, gestión de daños, remarketing.
- **SilverDAT Connect:** API para integración en aplicaciones de terceros.
- **Módulos:** Valuación usados, EV-specific, repair cost, damage management, remarketing a marketplaces online.

**Pricing (estimado, basado en datos de 2020 + inflación):**
- SilverDAT Beginner: EUR 274/mes (1er año, 1 usuario).
- SilverDAT Basis: EUR 365/mes 1er año, EUR 247/mes desde 2º año (2 usuarios).
- SilverDAT Flat Rate: EUR 427/mes 1er año, EUR 309/mes desde 2º año (2 usuarios).
- Suscripción de 12 meses obligatoria.
- Precios probablemente superiores en 2026 dado inflación + expansión de funcionalidades.

**Gaps explotables:**
- **Alemania-céntrico.** DAT es el estándar en DE pero su presencia en FR, ES, NL, BE, CH es marginal comparada con Autovista/Eurotax.
- **Foco en valuación + reparación, no en market intelligence de listings live.** DAT dice "tu coche vale X" basado en modelos estadísticos, no "hay 47 coches como este en 6 países a estos precios ahora mismo."
- **Sin datos de inventario live.** No scrapean listings. No pueden decir qué hay realmente en venta.
- **Pricing mínimo EUR 274/mes** — caro para un solo módulo de valuación básico para un dealer pequeño.

**Entrada CARDEX:**
- **Complemento, no competencia directa.** Un dealer en DE puede tener SilverDAT para valuación y CARDEX para market intelligence cross-border.
- **Precio inferior para datos de mercado live.** CARDEX a EUR 99-149/mes vs. SilverDAT a EUR 274+/mes.
- **Cross-border como diferenciador.** DAT es fuerte en DE. CARDEX es fuerte en DE+FR+ES+NL+BE+CH simultáneamente.

**Fuentes:**
- [DAT Group — International](https://www.datgroup.com/)
- [SilverDAT 3](https://www.datgroup.com/products/silverdat-3/)
- [SilverDAT Pricing — Pixelconcept](https://www.pixelconcept.de/en/dat-software/)
- [DAT Group — CBInsights](https://www.cbinsights.com/company/dat-group)

---

### 1.4 Schwacke

**Perfil:** Proveedor histórico de valuación de vehículos en Alemania. La "Schwacke List" es referencia para dealers, aseguradoras y bancos en el mercado alemán. Opera como parte del ecosistema de datos automotrices alemán.

**Qué venden:**
- **Schwacke List (Schwacke-Liste):** Valuación estandarizada de vehículos usados basada en marca, modelo, año, kilometraje y equipamiento.
- Datos estadísticos de millones de puntos de datos del mercado alemán.
- Aceptado por aseguradoras, bancos y empresas para valuaciones comerciales.

**Pricing:**
- EUR 7-10 por valuación individual (consumer).
- Acceso via informes pagados o partners online autorizados.
- Dealers y concesionarios acceden a través de paquetes profesionales (precios no públicos).

**Gaps explotables:**
- **Solo Alemania.** Sin cobertura pan-europea.
- **Basado en promedios estadísticos, no en datos live.** La Schwacke List es un modelo estadístico, no una visión en tiempo real del mercado.
- **Consumer-oriented.** El producto principal es la valuación unitaria, no analytics de mercado.
- **Sin API moderna pública.** No hay documentación de API REST accesible para developers.

**Entrada CARDEX:**
- **CARDEX como complemento cross-border.** Schwacke valúa un vehículo en Alemania; CARDEX muestra que ese mismo vehículo vale más/menos en otros 5 países.
- **Datos live vs. estadísticos.** CARDEX muestra precios reales de listings actuales; Schwacke muestra promedios históricos.

**Fuentes:**
- [Schwacke List — CashForCars](https://www.cashforcars.de/en/blog-schwacke-list-calculate-car-value)
- [Online Car Valuation — Schwacke](https://mirkaafenaerenauto.lu/en/ratgeber/auto-bewertung-online-kostenlos)

---

### 1.5 Glass's Guide

**Perfil:** Proveedor líder de valuación vehicular en UK. Ahora parte de Autovista Group (J.D. Power). Proporciona valuaciones, live retail pricing, datos de specs y forecasts.

**Qué venden:**
- **Glass's Guide Valuations:** Trade, retail, private values con ajuste por mileage.
- **Market Value Assessor:** Herramienta de valuación basada en datos de mercado en vivo.
- **Data Feeds & APIs:** Feeds de datos y APIs para integración enterprise.
- **VRM Valuation API:** API de valuación por matrícula con datos de mercado en tiempo real. Actualización importante en Dec 2025: solo QualifiedModelCode (NatCode) y valuaciones Standard Trade/Retail.
- **Live Retail Prices:** Datos de retail pricing local.

**Pricing:**
- No público. Cotización enterprise obligatoria.
- Estimaciones de la industria: GBP 2.000-10.000+/año dependiendo de módulos.
- Es el estándar en UK, por tanto tiene pricing power significativo.

**Gaps explotables:**
- **Solo UK.** Cobertura europea continental mínima (la gestiona Autovista/Eurotax del mismo grupo).
- **NatCode como identificador único.** Transición forzada desde Glass Code a QualifiedModelCode puede causar fricción con integradores legacy.
- **No datos de inventario live cross-border.** No pueden decir qué hay a la venta en FR, ES, NL, etc.
- **Dependencia de Autovista Group para Europa continental** — que a su vez tiene los gaps mencionados en §1.2.

**Entrada CARDEX:**
- **UK no es mercado CARDEX actual** (6 países: DE, FR, ES, NL, BE, CH). No hay competencia directa.
- **Si CARDEX expande a UK:** Glass's es el incumbent a batir. Pero como parte de J.D. Power/Autovista, su pricing será enterprise. CARDEX puede entrar al mid-market UK.
- **Datos cross-border como valor añadido para importadores UK.** Post-Brexit, importar vehículos de EU a UK requiere inteligencia de pricing que Glass's no proporciona.

**Fuentes:**
- [Glass's Guide — Vehicle Valuations](https://glass.co.uk/)
- [VRM Valuation API CVM Transition](https://glass.co.uk/vrm-valuation-api-cvm-transition/)
- [Glass's Data Feeds & APIs](https://glass.co.uk/product/data-solutions/)
- [Glass's — VendorMotive](https://www.vendormotive.com/vendors/glass-s)

---

### 1.6 CAP HPI

**Perfil:** Parte de Solera Holdings. Proveedor líder de valuaciones vehiculares, datos de historial y specs en UK. Fusión de CAP (valuaciones) y HPI (historial de vehículos).

**Qué venden:**
- **CAP Valuation Data:** Valuaciones trade, retail, private con ajuste por condición y mileage. 460K+ opciones y list prices de 55 fabricantes.
- **HPI Vehicle Data API:** Historial, valuación, specs, MOT, DVLA data.
- **Valuation Anywhere / Valuation Anywhere Live:** Valuaciones en tiempo real via web, texto o email.
- **Red Book:** Guía de valuación de referencia.
- **CAP API:** Acceso via HTTP services con subscriber ID.

**Pricing:**
- No público. Cotización personalizada obligatoria.
- Estimaciones de la industria: GBP 3.000-20.000+/año para dealers medianos-grandes.
- Un tender gubernamental UK (2025) para "Provision of CAP Vehicle Data Subscription" sugiere que incluso entidades públicas pagan suscripciones significativas.

**Gaps explotables:**
- **Solo UK (+ datos internacionales limitados via Solera).** Sin cobertura específica de EU-6 continental.
- **Orientado a valuación + historial, no a market intelligence cross-border.**
- **Parte de Solera** — mismo conglomerado que AUTOonline. Posibilidad de sinergias internas que excluyen a third-party providers.
- **Sin datos de listings live pan-europeos.**

**Entrada CARDEX:**
- Similar a Glass's: **UK no es mercado CARDEX actual.** Sin competencia directa.
- **Si CARDEX expande a UK:** CAP HPI + Glass's forman un duopolio. CARDEX puede diferenciarse con datos cross-border EU-UK y pricing mid-market.

**Fuentes:**
- [CAP HPI — Home](https://www.cap-hpi.com/)
- [HPI Vehicle Data API](https://www.hpi.co.uk/vehicle-data-api.html)
- [CAP HPI Access & Pricing — Oreate AI](https://www.oreateai.com/blog/unpacking-cap-hpi-api-what-you-need-to-know-about-access-and-pricing/056ee701e74c4b3f7150a8081f78039e)
- [CAP Vehicle Data Tender — Find a Tender](https://www.find-tender.service.gov.uk/Notice/010019-2025)

---

### Matriz Competitiva — Competidores Directos vs. CARDEX

| Dimensión | TecAlliance | Autovista | DAT/SilverDAT | Schwacke | Glass's | CAP HPI | **CARDEX** |
|---|---|---|---|---|---|---|---|
| **Tipo de datos** | Recambios | Valuación + specs | Valuación + repair | Valuación | Valuación + retail | Valuación + historial | **Listings live** |
| **Cobertura geográfica** | Global | 30+ países | DE-centric | Solo DE | Solo UK | Solo UK | **DE+FR+ES+NL+BE+CH** |
| **Datos de inventario live** | No | Parcial (via Indicata) | No | No | Parcial (retail) | No | **Sí — 1,55M vehículos** |
| **Arbitraje cross-border** | No | No | No | No | No | No | **Sí** |
| **Datos dealer websites directos** | No | No | No | No | No | No | **Sí — 71+ portales** |
| **Pricing min** | Custom (alto) | EUR 5K+/año | EUR 274/mes | EUR 7/query | Custom (alto) | Custom (alto) | **EUR 49-149/mes** |
| **Target** | Aftermarket | Enterprise | DE enterprise | DE consumer | UK enterprise | UK enterprise | **SME dealers EU** |
| **Alertas push** | No | No | No | No | No | No | **Sí (roadmap)** |
| **Price forecasting** | No | Sí (120 meses) | No | No | Sí | No | **Sí (Chronos-2)** |

**Conclusión §1:** Ningún competidor directo ofrece simultáneamente: datos de listings live + cobertura de 6 mercados EU + pricing mid-market + arbitraje cross-border. CARDEX ocupa un nicho estructuralmente vacío.

---

## 2. MARKETPLACES B2B DE SUBASTAS ONLINE

---

### 2.1 BCA (British Car Auctions)

**Perfil:** La mayor empresa de remarketing vehicular de Europa. Vende 1M+ vehículos anuales. Opera ~50 centros en 10 países: UK, FR, PT, ES, DE, NL, CH, DK, IT, SE.

**Modelo de negocio:** Subastas B2B para OEMs, leasing companies, fleet managers y dealer groups. En mayo 2026, BCA adquirió Aston Barclay (aprobado por regulador UK). Deal con Grosvenor Leasing (3 años exclusivo) y Santander Consumer UK.

**APIs y datos expuestos:**
- **No hay API pública documentada.** BCA opera como plataforma cerrada para compradores registrados.
- Los datos de transacciones son propietarios y no se exponen a terceros.
- La digitalización del proceso de subasta ha sido su inversión principal.

**Integración CARDEX como data provider:**
- **Viabilidad: MEDIA.** BCA podría beneficiarse de datos de pricing cross-border para informar a sus vendedores del valor óptimo de reserve price. Sin embargo, su escala y su propiedad de datos transaccionales propios les hace autosuficientes en pricing.
- **Ángulo más viable:** CARDEX como fuente de datos de mercado retail para complementar los datos transaccionales wholesale de BCA. Un vendedor en BCA podría usar CARDEX para saber a cuánto se está vendiendo el vehículo al retail en 6 países antes de fijar reserve.

**Fuentes:**
- [BCA Group](https://www.bca.com/)
- [BCA UK](https://www.bca.co.uk/)
- [BCA Aston Barclay Acquisition — Motor Trader](https://www.motortrader.com/tag/bca)

---

### 2.2 Manheim (Cox Automotive)

**Perfil:** Parte de Cox Automotive. Plataforma global de remarketing vehicular. Foco principal en US con operaciones en Europa.

**APIs y datos expuestos:**
- **API pública documentada:** [developer.manheim.com](https://developer.manheim.com/). Suite de Hypermedia APIs (REST).
- **Capacidades API:**
  - Enviar inventario nuevo a Manheim.
  - Crear órdenes de movimiento de inventario.
  - Crear consignaciones en ubicaciones físicas.
  - Obtener precios wholesale via Manheim Market Report.
  - Datos de transacciones en JSON (customer ID, auction code, VIN, sale key).
- **Acceso:** Via representante Cox Automotive o DataSyndication@coxautoinc.com.
- **Actualización 2026:** Mejoras en Vehicle Details Page con herramientas de bidding y checkout (abril 2026).

**Integración CARDEX como data provider:**
- **Viabilidad: MEDIA-ALTA.** Manheim ya tiene API documentada y abierta a partners. CARDEX podría integrarse como fuente de datos de mercado retail europeo para enriquecer el Manheim Market Report en Europa.
- **Gap de Manheim:** La documentación API es primariamente US-focused. La cobertura europea de Manheim es limitada comparada con BCA.
- **Acción:** Contactar DataSyndication@coxautoinc.com para explorar data partnership.

**Fuentes:**
- [Manheim API Developer Portal](https://developer.manheim.com/)
- [Manheim Marketplace API](https://developer.manheim.com/apis/marketplace/index.html)
- [Manheim API Access](https://developer.manheim.com/pages/accessAndEnvironments.html)

---

### 2.3 ADESA / OpenLane Europe

**Perfil:** Rebrandeado de ADESA Europe a OPENLANE Europe. Parte de KAR Global/OPENLANE Inc. Plataforma consolidada pan-europea + UK (openlane.eu y openlane.co.uk). Integra inspecciones, subastas y delivery.

**APIs y datos expuestos:**
- **Plataforma digital consolidada** pero sin API pública documentada para terceros encontrada.
- La integración entre ADESA y TradeRev fue un hito de integración digital interna.

**Integración CARDEX como data provider:**
- **Viabilidad: MEDIA.** OpenLane está consolidando plataformas internamente. Su foco es eficiencia operativa, no apertura de datos.
- **Ángulo:** CARDEX podría ofrecer benchmarking de precios de mercado retail para informar las expectativas de vendedores en la plataforma.

**Fuentes:**
- [ADESA Rebrands to OPENLANE Europe](https://www.vehicleremarket.com/10211626/adesa-rebrands-to-openlane-in-europe)
- [OPENLANE Corporate](https://corporate.openlane.com/)
- [OPENLANE Europe](https://www.openlane.eu/en/cms/about-adesa)

---

### 2.4 CarOnSale

**Perfil:** B2B auction marketplace. Fundada 2018, Berlin. EUR 70M Series C (julio 2025, liderada por Northzone). 18.000+ dealers registrados. Foco: subastas cross-border de vehículos usados en Europa.

**APIs y datos expuestos:**
- **No hay API pública para third-party data providers.** La API interna usa Fivetran + Snowflake para su propio pipeline de datos.
- "Harvesting and analysing data around car auctions is the big differentiator" — Fivetran case study.
- Ofrece "intelligent pricing based on real sales data" con precio garantizado para recolección.
- Servicio completo: grabación, subasta, transporte, reclamaciones.

**Integración CARDEX como data provider:**
- **Viabilidad: ALTA.** CarOnSale necesita datos de mercado retail para calibrar su pricing. Si CARDEX proporciona datos de lo que cuestan los vehículos al retail en 6 países, CarOnSale puede mejorar la precisión de sus precios garantizados.
- **Modelo:** CARDEX como data feed white-label → CarOnSale enriquece su "intelligent pricing" con datos de mercado retail CARDEX.
- **Acción:** Contactar a CarOnSale para proponer data partnership. El timing es bueno post-Series C (capital para inversión en infraestructura de datos).

**Fuentes:**
- [CarOnSale](https://www.caronsale.com/en)
- [CarOnSale + Fivetran Case Study](https://www.fivetran.com/case-studies/fivetran-accelerates-online-auto-trading-for-caronsale)
- [CarOnSale Series C — Tech.eu](https://tech.eu/2025/07/07/caronsale-secures-70m-in-series-c-for-cross-border-used-car-trading/)

---

### 2.5 AUTOonline (Solera)

**Perfil:** La mayor plataforma de intercambio de salvage online de Europa. Parte de Solera Holdings (mismo grupo que CAP HPI). Opera en DE, PL, TR, FR, ES, GR, MX.

**Escala operativa:**
- 3.700+ vehículos de salvage listados por día.
- 4.100+ compradores activos (reconstructores, desguaces, dealers).
- Aseguradoras líderes como vendedores principales.
- Servicios adicionales: verificación de valor, remarketing de flotas.

**APIs y datos expuestos:**
- **Sin API pública documentada para data providers.** La plataforma conecta aseguradoras con compradores profesionales en un ecosistema cerrado.
- La web [autoonline.com](https://www.autoonline.com/) describe el flujo: vendedor lista → compradores pujan → transacción.

**Integración CARDEX como data provider:**
- **Viabilidad: BAJA-MEDIA.** AUTOonline es salvage (vehículos dañados), no vehículos usados en buen estado. El solapamiento con los datos de CARDEX (listings retail) es limitado.
- **Ángulo potencial:** CARDEX podría informar a compradores de AUTOonline del valor post-reparación de un vehículo dañado comparándolo con listings de vehículos similares en buen estado en 6 mercados.
- **Riesgo:** Solera es dueño tanto de AUTOonline como de CAP HPI. Podrían integrar datos internamente.

**Fuentes:**
- [AUTOonline — Solera Solutions](https://www.solera.com/solutions/vehicle-claims/autoonline/)
- [AUTOonline Salvage Exchange](https://www.autoonline.com/salvage-exchange.html)

---

### 2.6 Autorola (Autorola Group / Indicata)

**Perfil:** Online remarketing + BI para automotive. Sede: Dinamarca. 70.000+ compradores activos. 200.000+ vehículos disponibles anualmente. Opera Autorola (subastas) + Indicata (BI) + Autorola Solutions (servicios).

**APIs y datos expuestos:**
- **API documentada:** Swagger en [SwaggerHub — Autorola FM_Integration_API](https://app.swaggerhub.com/apis/Autorola/FM_Integration_API/).
- Integración con CarCollect: subastas iniciadas en CarCollect se retransmiten a Autorola con bidding en tiempo real.
- Autorola Solutions ofrece integraciones personalizadas para fleet management.
- Datos de Indicata integrados: valuaciones live enriquecen la plataforma de subastas.
- 21% de ventas de Autorola son cross-border (dato propio Autorola Group).

**Integración CARDEX como data provider:**
- **Viabilidad: ALTA.** Autorola ya tiene API documentada y mentalidad de integración. Indicata consume datos de clasificados y dealer websites — exactamente lo que CARDEX produce.
- **Modelo 1:** CARDEX como fuente de datos adicional para Indicata (datos de dealer websites directos que Indicata no scrapea).
- **Modelo 2:** CARDEX enriquece la plataforma Autorola con datos de pricing de mercados donde Autorola tiene menos cobertura.
- **Riesgo:** Autorola/Indicata ya hace scraping propio de clasificados. Pero CARDEX tiene datos de dealer websites directos que Indicata no cubre.

**Fuentes:**
- [Autorola Group](https://www.autorolagroup.com/)
- [Indicata](https://indicata.com/)
- [Autorola FM Integration API — SwaggerHub](https://app.swaggerhub.com/apis/Autorola/FM_Integration_API/)
- [Autorola + CarCollect Integration](https://www.carcollect.com/integrations/autorola)

---

### 2.7 CarDataHub / CarGenius (Agregador)

**Perfil:** Plataforma que integra 50+ auction houses y proporciona datos de subasta via REST API. 2M+ vehículos vendidos via su tecnología. Opera desde 2004. Clientes: flotas, OEMs, dealers independientes.

**APIs y datos expuestos:**
- **REST API pública:** Datos de subasta en formato máquina. Single API key para acceso.
- Streaming de listings live, pujas programáticas, monitoreo de actividad.
- 99,95% API uptime en últimos 12 meses.
- Hosting en datacenter ISO 27001 en EU. Sin datos personales procesados.

**Integración CARDEX como data provider:**
- **Viabilidad: MEDIA-ALTA.** CarDataHub agrega datos de subastas; CARDEX aporta datos de retail. Combinación complementaria.
- **Modelo:** CARDEX feed → CarDataHub lo distribuye a sus clientes de auction houses como "retail market context."

**Fuentes:**
- [CarDataHub — Auction Data API](https://www.cardatahub.com/)
- [CarGenius — White-Label Solutions](https://www.cargenius.info/)

---

### Resumen Marketplaces B2B — Prioridad de Integración CARDEX

| Plataforma | Viabilidad Integración | Tipo | API Pública | Acción |
|---|---|---|---|---|
| **CarOnSale** | ALTA | B2B auction | No (interna) | Proponer data partnership post-Series C |
| **Autorola/Indicata** | ALTA | Remarketing + BI | Sí (Swagger) | Proponer feed de dealer websites directos |
| **CarDataHub** | MEDIA-ALTA | Agregador 50+ auctions | Sí (REST) | Explorar como canal de distribución |
| **Manheim** | MEDIA-ALTA | Remarketing US+EU | Sí (REST) | Contactar DataSyndication |
| **BCA** | MEDIA | Remarketing EU | No | Proponer benchmarking retail |
| **OpenLane** | MEDIA | Remarketing EU | No | Monitorizar apertura de plataforma |
| **AUTOonline** | BAJA-MEDIA | Salvage | No | Solo ángulo post-repair valuation |

---

## 3. REGULACIÓN 2026-2027 QUE CREA DEMANDA NUEVA

---

### 3.1 Euro 7 — Timeline Exacto

**Regulación:** Regulation (EU) 2024/1257. Implementing Acts: EU 2025/1706 y EU 2025/1707.

**Fechas exactas:**

| Fecha | Hito |
|---|---|
| **29 noviembre 2026** | Euro 7 aplica a nuevas type approvals de vehículos ligeros (M1/N1). Los nuevos modelos no obtienen type approval sin cumplir Euro 7. |
| **29 noviembre 2027** | Euro 7 obligatorio para TODOS los vehículos ligeros nuevos vendidos/registrados en la EU. |
| **29 mayo 2028** | Euro 7 aplica a nuevas type approvals de vehículos pesados (M2/M3/N2/N3/O3/O4). |
| **29 mayo 2029** | Euro 7 obligatorio para todos los vehículos pesados nuevos. |

**Innovación regulatoria clave:**
- **Environmental Vehicle Passport (EVP):** Documento digital por VIN con niveles de contaminantes, CO2, consumo, rango eléctrico, datos OBM. Accesible via QR + VIN, sin registro. **Esto es nuevo y no cubierto en informes anteriores.**
- 320+ Low Emission Zones (LEZ) activas en Europa, cada una con criterios propios por Euro-norm.
- Mercado compliant Euro 7: 13,6M unidades en 2026, creciendo a 14,1M en 2035.

**Demanda que crea para CARDEX:**
- Dealers necesitan saber qué vehículos de su stock perderán valor aceleradamente por restricciones LEZ.
- Vehículos pre-Euro 7 fluirán de Europa Occidental a Oriental — CARDEX puede trackear estos flujos.
- El EVP como dato adicional por VIN enriquece el dataset CARDEX.

**Fuentes:**
- [Euro 7 Timeline — Geotab](https://www.geotab.com/ie/blog/euro-7-emission-standard-timeline-eu/)
- [Euro 7 — Webfleet](https://www.webfleet.com/en_gb/webfleet/blog/euro-7-emission-standards/)
- [Euro 7 — RAC Drive](https://www.rac.co.uk/drive/advice/emissions/what-is-euro-7-and-when-does-it-start/)
- [Euro 7 Implementing Acts — Xeeniq/Medium](https://medium.com/@xeeniq/euro-7-implementing-acts-2025-1706-2025-1707)
- [Euro 7 Technical Requirements — EUR-Lex](https://eur-lex.europa.eu/EN/legal-content/summary/vehicle-emissions-and-battery-durability-euro-7-technical-requirements-and-certification-rules.html)

---

### 3.2 EU Battery Passport — Timeline Exacto

**Regulación:** Regulation EU 2023/1542 (Battery Regulation).

**Fechas exactas:**

| Fecha | Hito |
|---|---|
| Febrero 2026 | Metodologías finalizadas de carbon footprint para baterías. |
| **18 febrero 2026** | Carbon footprint declaration obligatoria para baterías industriales >2 kWh. |
| **Julio 2026** | Comisión publica guía oficial de due diligence para cadena de suministro de baterías. |
| **19 julio 2026** | **EU Central DPP Registry operativo.** Datos de Battery Passport accesibles. |
| Agosto 2026 | Nuevos estándares de etiquetado obligatorio para baterías. |
| **18 febrero 2027** | **OBLIGATORIO: Todas las baterías EV e industriales >2 kWh deben tener Battery Passport digital, accesible via QR code.** |
| **18 agosto 2027** | Due diligence de cadena de suministro obligatoria (postponed desde agosto 2025). |
| 18 agosto 2031 | Umbrales mínimos de contenido reciclado obligatorios (cobalto, plomo, litio, níquel). |

**Demanda que crea para CARDEX:**
- **19 julio 2026 es la fecha clave:** El registry central será accesible. CARDEX puede ser first-mover en integrar datos de Battery Passport en listings de EVs usados.
- ~329K EVs de leasing retornan al mercado en 2026. Cada uno necesitará Battery Passport verificable.
- SoH (State of Health) se convierte en campo obligatorio de facto para transacciones de EVs usados.

**Fuentes:**
- [EU Battery Passport Requirements — Circularise](https://www.circularise.com/blogs/eu-battery-passport-regulation-requirements)
- [Battery Regulation — EUR-Lex](https://eur-lex.europa.eu/EN/legal-content/summary/sustainability-rules-for-batteries-and-waste-batteries.html)
- [Battery Passport Deadlines — Digiprodpass](https://digiprodpass.com/blogs/battery-passport-deadlines-2027)
- [DPP Timeline 2026-2030 — PassportCraft](https://passportcraft.com/insights/dpp-timeline-2026-2030-every-deadline)
- [EU Battery Passport 2026 — BASE Project](https://base-batterypassport.com/blog/regulations-4/eu-battery-passport-regulation-57)

---

### 3.3 Right to Repair — Automotive Data Access

**Dos regulaciones convergentes:**

**3.3.1 EU Right to Repair Directive (2024/1799)**

| Fecha | Hito |
|---|---|
| **31 julio 2026** | Transposición obligatoria a leyes nacionales. Aplica a productos vendidos antes y después de esta fecha. |

- Cobertura actual: electrodomésticos, displays, móviles/tablets, servidores. **Vehículos NO están en el scope directo de la Directive de julio 2026.**
- Sin embargo, el framework SERMI (Secure Repair and Maintenance Information) ya obliga a OEMs automotrices a proporcionar acceso a información de reparación y mantenimiento a talleres independientes autorizados.

**3.3.2 EU Data Act (automotive vehicle data)**

| Fecha | Hito |
|---|---|
| **12 septiembre 2025** | EU Data Act en vigor. OEMs obligados a transparencia de datos vehiculares y acceso bajo términos FRAND. |
| **Septiembre 2026** | Design obligations: OEMs deben diseñar vehículos para facilitar acceso a datos por terceros autorizados. |

- OEMs deben proporcionar acceso a datos raw y preprocesados de vehículos conectados a terceros (talleres, aseguradoras, plataformas digitales).
- Acceso gratuito para usuarios del vehículo; tarifas FRAND para data recipients comerciales.
- **LKQ Europe** confirma que esto abre "a new era of vehicle data access" para el aftermarket independiente.

**Demanda que crea para CARDEX:**
- Septiembre 2026: datos de OEMs disponibles via FRAND. CARDEX puede actuar como intermediario autorizado (Data Act Art. 5) para combinar datos OEM con datos de mercado propios.
- El mercado de intermediación de datos vehiculares nace formalmente en 2026. CARDEX está posicionado para capturarlo.

**Fuentes:**
- [EU Right to Repair — Fieldfisher](https://www.fieldfisher.com/en/insights/incoming-eu-right-to-repair-requirements-the-key-t)
- [Right to Repair EU — Regulatory Decoded](https://regulatorydecoded.com/eu-right-to-repair-manufacturers-directive-2024-1799/)
- [EU Data Act Vehicle Data — TransConnect](https://transconnect.com/en/blog/vehicle-data-under-control-what-the-eu-data-act-means-for-dealers-and-fleet-owners)
- [EU Data Act — LKQ Europe](https://lkqeurope.com/article/public-affairs/eu-data-act-new-era-vehicle-data-access-begins)
- [Vehicle Data Governance FAQ — Taylor Wessing](https://www.taylorwessing.com/en/insights-and-events/insights/2026/01/faq-access-to-vehicle-data-and-data-governance)
- [Germany Right to Repair — Hogan Lovells](https://www.hoganlovells.com/en/publications/germanys-new-repair-law-implementing-the-eu-right-to-repair-directive)

---

### 3.4 GDPR Enforcement Trends en Automotive

**Números actualizados (marzo 2026):**
- Total acumulado de multas GDPR: EUR 6.110M+ (2.685 multas registradas).
- Solo en 2025: EUR 1.200M en multas — incremento del 22% YoY en notificaciones de breach.
- Entre enero 2023 y marzo 2026: más multas que en los 5 años anteriores combinados.
- **Foco 2026 del EDPB:** Coordinated Enforcement Framework centrado en transparencia y obligaciones de información.

**Automotive-específico:**
- **Volkswagen:** EUR 1,1M multa (julio 2022) por cámaras en vehículos de test-drive sin señalización (GDPR Art. 13).
- **General Motors:** USD 12,75M multa CCPA (California) por venta de datos de connected cars sin consentimiento.
- Vehículos conectados generan datos de perfiles de conductor, telemática, localización → escrutinio creciente de DPAs.
- EU Data Act + NIS2 + ePrivacy reconfiguran cómo las empresas automotrices recopilan, usan y comparten datos personales.
- **Nelson Mullins** prevé que "privacy regulation of auto industry will accelerate in 2026."

**Implicaciones para CARDEX:**
- CARDEX scrapea datos B2B públicos de dealers (no datos personales de consumidores). Riesgo GDPR bajo.
- Sin embargo, la tendencia regulatoria creciente crea demanda de herramientas de compliance. CARDEX podría ofrecer "GDPR-compliant data sourcing" como diferenciador vs. proveedores que scrapean datos personales.
- Clientes de CARDEX (dealers, leasing companies) necesitan proveedores de datos con base legal demostrable. Art. 6(1)(f) interés legítimo para datos B2B públicos.

**Fuentes:**
- [GDPR Enforcement Tracker Report 2025/2026 — CMS Law](https://cms.law/en/int/publication/GDPR-Enforcement-Tracker-Report/numbers-and-figures)
- [GDPR Fines EUR 7.1B — Kiteworks](https://www.kiteworks.com/gdpr-compliance/gdpr-fines-data-privacy-enforcement-2026/)
- [GDPR Automotive Connected Cars — Infosecurity Magazine](https://www.infosecurity-magazine.com/opinions/driving-compliance-data-protection/)
- [Privacy Regulation Auto Industry 2026 — Nelson Mullins](https://www.nelsonmullins.com/insights/blogs/driving-forward-developments-in-transportation-law-and-innovation/all/privacy-regulation-of-auto-industry-to-accelerate-in-2026-part-2)

---

### Calendario Regulatorio Consolidado 2026-2027

```
2026
 Jul 19 — EU DPP Registry operativo (Battery Passport data accesible)
 Jul 31 — EU Right to Repair Directive: transposición nacional
 Aug 02 — EU AI Act: Annex III high-risk plenamente aplicable
 Sep    — EU Data Act: design obligations para OEMs
 Nov 29 — Euro 7: type approval obligatorio para nuevos modelos M1/N1

2027
 Feb 18 — Battery Passport OBLIGATORIO para todas las baterías EV >2 kWh
 Aug 18 — Due diligence cadena de suministro de baterías
 Nov 29 — Euro 7: TODOS los vehículos ligeros nuevos deben cumplir
```

---

## 4. MODELOS DE PRICING DE APIS DE DATOS AUTOMOTIVE

---

### 4.1 Mapa Comparativo de Pricing

| Proveedor | Modelo | Precio Público | Tipo de Datos | Cobertura |
|---|---|---|---|---|
| **Autovista API** | Suscripción enterprise | EUR 5.000-50.000+/año (estimado) | Valuación, specs, forecasts | 30+ países EU |
| **DAT/SilverDAT** | Suscripción mensual | EUR 274-427/mes (estimado 2020 base) | Valuación, repair cost, VIN | Alemania-centric |
| **TecAlliance/TecDoc** | Custom enterprise | No público (alto) | Aftermarket parts data | Global |
| **Schwacke** | Pay-per-query | EUR 7-10/valuación | Valuación vehículos | Solo Alemania |
| **Glass's** | Enterprise suscripción | GBP 2.000-10.000+/año (est.) | Valuación, retail pricing | Solo UK |
| **CAP HPI** | Enterprise suscripción | GBP 3.000-20.000+/año (est.) | Valuación, historial, specs | Solo UK |
| **carVertical** | Pay-per-report + B2B | EUR 24,99/report (consumer) | Historial vehicular | 45+ países |
| **AutoDNA** | Pay-per-report | Desde EUR 19,99/report | Historial vehicular | 26+ países EU |
| **CARFAX Europe** | Enterprise custom | No público | Historial vehicular | 20 países EU + US/CA |
| **MarketCheck** | Tiered (desde USD 8) | Custom enterprise | Listings, market data | US/UK/CA |
| **autobiz API** | Enterprise custom | No público | Valuaciones B2B/B2C | 22 mercados EU |
| **CarAPI** | Tiered anual | USD 199-299/año | Specs, VIN decode | US-centric |
| **Zyla API Hub** | Tiered mensual | USD 20-200/mes | Precios EU básicos | EU (baja calidad) |
| **Dataforce** | Dataset purchase | EUR 500-12.500/año | Datos de registro | 40 países |
| **JATO Dynamics** | Enterprise only | EUR 5.000+/mes (est.) | Transaccional + specs | 50+ mercados |

### 4.2 Análisis de Bandas de Precio

**Banda Enterprise (EUR 5K-50K+/año):** Autovista, JATO, Glass's, CAP HPI, TecAlliance. Requieren contratos anuales, negociación de ventas, y SLAs. Inaccesibles para dealers SME y startups.

**Banda Mid-Market (EUR 100-500/mes):** **VACÍA.** No existe ningún proveedor que ofrezca datos de listings live de múltiples mercados EU a este precio. Esta es la oportunidad de CARDEX.

**Banda Low-End (EUR 8-25/consulta o USD 20-200/mes):** MarketCheck (desde USD 8, pero US/UK foco), CarAPI (USD 199-299/año, US-centric), Schwacke (EUR 7-10/query, solo DE), carVertical/AutoDNA (EUR 20-25/report, historial no market data), Zyla (EUR 20-200/mes, calidad dudosa).

**Banda Consumer (EUR 0-10/report):** Schwacke consumer, HPI check individual, carVertical consumer reports.

### 4.3 Pricing Recomendado para CARDEX

Basado en el análisis competitivo, CARDEX debe posicionarse en la **banda mid-market vacía**:

| Tier CARDEX | Precio/mes | Posicionamiento vs. Competencia |
|---|---|---|
| Starter (EUR 49) | 10x más barato que Autovista mínimo | Comparable a 2-3 reportes carVertical/mes |
| Professional (EUR 149) | 40x más barato que JATO | Comparable a SilverDAT Beginner pero con 6 países |
| Enterprise (EUR 499) | 10-100x más barato que Autovista enterprise | Datos de 6 mercados live |

**Fuentes:**
- [MarketCheck Pricing](https://www.marketcheck.com/apis/pricing/)
- [CarAPI Pricing](https://carapi.app/pricing)
- [carVertical Pricing](https://www.carvertical.com/en/pricing)
- [Dataforce Market Data](https://www.dataforce.de/en/market-data/)
- [SilverDAT Pricing — Pixelconcept](https://www.pixelconcept.de/en/dat-software/)

---

## 5. STARTUPS AUTOMOTIVE B2B CON FUNDING 2025-2026

---

### 5.1 Tabla de Startups con Funding Reciente

| Startup | País | Funding (2025-2026) | Total Raised | Qué Hacen | Modelo de Negocio |
|---|---|---|---|---|---|
| **CarOnSale** | DE (Berlín) | EUR 70M Series C (Jul 2025) | ~EUR 100M+ | B2B auction cross-border EU | Comisión por transacción + pricing garantizado |
| **AutoGrab** | AU → UK/EU | AUD 80M Series B (Ene 2026) | AUD 130M+ | AI vehicle valuations, sourcing, analytics | SaaS + API para dealers, insurers, fleet |
| **FINN** | DE (Múnich) | EUR 1B ABS financing (Feb 2025) | EUR 250M equity + EUR 1B+ debt | Car subscription B2B fleet | Suscripción mensual por vehículo |
| **MotorK** | IT (Milán) | EUR 3M growth (Ene 2026) | ~EUR 100M+ (Euronext listed) | SaaS para retail automotive EMEA | SaaS suscripción para OEMs/dealers |
| **Kavak** | MX → EU | USD 300M equity (Feb 2026) | USD 3B+ total | Used car marketplace (C2B2C) | Compra/venta + financiación (Kuna Capital) |
| **Omnetic** | NL (Amsterdam) | USD 107M PE (Feb 2024) | USD 107M | Business management para dealerships | SaaS suscripción + services |
| **Brego** | UK | ~USD 2M total | USD 2M | AI vehicle valuations UK | API SaaS (valuaciones) |
| **Ravin AI** | IL | USD 30M total (Series B May 2023) | USD 30M | AI damage assessment | SaaS + API para insurers/remarketing |
| **Fixico** | IL | USD 23M total (Series A 2021) | USD 23M | Digital car repair management | Platform marketplace |
| **JP.cars** | NL (Amsterdam) | No public funding | — | Used car data intelligence (NL/BE/DE) | SaaS para dealers/leasing |
| **eCarsTrade** | BE (Bruselas) | No funding (bootstrapped) | EUR 0 | B2B auction EU (leasing vehicles) | Comisión por transacción |
| **KnowTrex** | DE | No public funding | — | Market intelligence automotive AI | SaaS para pricing/sales |

### 5.2 Análisis de Señales de Mercado

**Señal 1 — AI Valuations es el segmento caliente:**
AutoGrab (AUD 80M Series B, valuación AUD 230M) demuestra que hay apetito inversor significativo para plataformas de valuación vehicular AI-powered. Brego (UK) tiene tracción con 2,2B+ data points. CARDEX tiene Chronos-2 ya implementado — es un competidor viable en este espacio.

**Señal 2 — Cross-border B2B es where the money is:**
CarOnSale (EUR 70M) y FINN (EUR 1B ABS) dominan porque resuelven problemas cross-border. 21% de ventas Autorola son cross-border. El comercio intra-EU de vehículos usados es el segmento de mayor crecimiento. CARDEX nació para este segmento.

**Señal 3 — Consolidación y verticales SaaS automotive:**
MotorK (EUR 3M, Euronext), Omnetic (USD 107M PE) y la adquisición de Autovista por J.D. Power muestran consolidación. Los compradores pagan primas por datos automotive verticales integrados. CARDEX como dataset propietario tiene valor de adquisición.

**Señal 4 — Bootstrapping funciona en B2B automotive EU:**
eCarsTrade (bootstrapped, 10K+ empresas, EUR 13,2Cr revenue) y JP.cars (bootstrapped, top-20 dealers NL como clientes) demuestran que se puede crecer sin funding significativo si el producto resuelve un problema real. CARDEX opera con EUR 22/mes de infraestructura — es ultra-lean.

**Señal 5 — Australia mira a Europa:**
AutoGrab (AU) levantó USD 80M específicamente para expandirse a UK y Europa. Co-fundador reubicado en Londres. Esto valida el mercado europeo de datos vehiculares AI-powered y señala competencia entrante en 12-18 meses.

### 5.3 Fondos de Inversión Activos en Automotive B2B Europa (2025-2026)

| Fondo | Tamaño | Foco | Etapa |
|---|---|---|---|
| **BMW i Ventures** | USD 300M (Fund III, abril 2026) | AI automotriz, manufacturing, supply chain | Seed → Series B |
| **UVC Partners** | EUR 400M | B2B tech EU: deeptech, climate, mobility, AI | Seed → Series B |
| **Planet First Partners** | — | Sustainability, mobility | Series C |
| **Northzone** | — | Marketplaces, B2B SaaS | Growth |
| **Octopus Ventures** (UK) | — | AI, climate, health | Seed → Series B |

**Fuentes:**
- [CarOnSale Series C — Tech.eu](https://tech.eu/2025/07/07/caronsale-secures-70m)
- [AutoGrab Series B — Startup Daily](https://www.startupdaily.net/topic/funding/ai-based-car-valuation-platform-hits-top-get-with-80-million-series-b/)
- [FINN ABS II — EU-Startups](https://www.eu-startups.com/2025/02/car-subscription-service-finn-closes-abs-of-e1-billion-euros-for-financing-its-fleet-growth/)
- [MotorK EUR 3M — EU-Startups](https://www.eu-startups.com/2026/01/milano-based-automotive-saas-provider-motork-secures-e3-million-to-bolster-its-financial-position/)
- [Kavak USD 300M — Silicon Valley InvestClub](https://siliconvalleyinvestclub.com/2026/02/23/kavak-raises-300-million-in-funding/)
- [BMW i Ventures Fund III — BMW Press](https://www.press.bmwgroup.com/global/article/detail/T0457479EN/bmw-i-ventures-announces-300-million-fund-to-back-ai-startups-reshaping-the-automotive-ecosystem)
- [Omnetic — Tracxn](https://tracxn.com/d/companies/omnetic/__PbPFzJWOZDq20wzTA8GfD7oI8uCjKwrvULEa5TNBm4E)
- [Brego AI](https://brego.io/)
- [JP.cars](https://jp.cars/)
- [eCarsTrade — Tracxn](https://tracxn.com/d/companies/ecarstrade/__CO6BbpS7bjC_ejqcrKuHeENZi0AtCSev7gadW-T2Nf8)

---

## 6. IMPLICACIONES ESTRATÉGICAS PARA CARDEX

---

### 6.1 Dónde Puede Entrar CARDEX — Resumen de Gaps

| Gap Identificado | Fuente del Gap | Producto CARDEX |
|---|---|---|
| No existe API mid-market de listings EU cross-border | §4.2 — Banda mid-market vacía | Cross-Border Price Intelligence API |
| Autovista/JATO inaccesibles para dealers SME | §1.2, §4.1 | Tiers EUR 49-499/mes |
| Ningún competidor ofrece alertas push de arbitraje | §1 Matriz — columna "Alertas push" | Dealer Inventory Alert Service |
| Marketplaces B2B necesitan datos retail para pricing | §2.4, §2.6 — CarOnSale, Autorola | White-label data feed |
| Battery Passport + datos de mercado = producto nuevo | §3.2 — Registry operativo julio 2026 | EV Battery Passport Data Relay |
| Euro 7 EVP + datos de mercado = producto nuevo | §3.1 — EVP por VIN | Emission Zone Depreciation Scoring |
| Datos dealer websites directos no disponibles en ningún competidor | §1 Matriz — "Datos dealer websites" | Data feed propietario |
| AI valuations con datos propietarios dealer-level | §5.2 Señal 1 — AutoGrab a EUR 80M | Price Forecasting API (Chronos-2) |

### 6.2 Partners Prioritarios para Contactar (Q3 2026)

| Partner | Tipo | Producto CARDEX | Prioridad |
|---|---|---|---|
| CarOnSale | Data feed client | Market retail pricing | P0 |
| Autorola/Indicata | Data feed client | Dealer website listings | P0 |
| CarDataHub/CarGenius | Canal de distribución | Auction data enrichment | P1 |
| BMW i Ventures | Inversor potencial | Equity funding Seed | P1 |
| Manheim/Cox Automotive | Data partnership | EU market data | P2 |
| autobiz | Partnership técnico | Cross-border valuations | P2 |

### 6.3 Competidores a Monitorizar

| Competidor | Amenaza | Timeline | Acción |
|---|---|---|---|
| **AutoGrab** | AI valuations, expandiendo a EU | 12-18 meses | Acelerar Chronos-2 productización |
| **Carapis** | Scraping 25+ mercados, si añaden dealer discovery cierran gap | 6-12 meses | Defender moat de dealer websites directos |
| **JP.cars** | Market intelligence NL/BE/DE, expandiendo | 6-12 meses | Co-opetition posible; ellos cubren NL, CARDEX es más amplio |
| **KnowTrex** | AI pricing intelligence EU | 6-12 meses | Competir en data uniqueness |
| **Indicata** (Autovista) | Si bajan precios al mid-market | 12+ meses | Velocidad de ejecución; ocupar nicho antes |

---

## 7. FUENTES COMPLETAS

### Competidores Directos
- [TecAlliance — Automotive Data Solutions](https://www.tecalliance.net/)
- [TecAlliance Limitations — FactoryData](https://www.factorydata.com/en/tecalliance-limitations-of-the-most-used-technology-in-the-market/)
- [Autovista API](https://autovista.com/product/autovista-api/)
- [Autovista Group Revenue — Growjo](https://growjo.com/company/Autovista_Group)
- [DAT Group International](https://www.datgroup.com/)
- [SilverDAT 3](https://www.datgroup.com/products/silverdat-3/)
- [SilverDAT Pricing — Pixelconcept](https://www.pixelconcept.de/en/dat-software/)
- [Schwacke List — CashForCars](https://www.cashforcars.de/en/blog-schwacke-list-calculate-car-value)
- [Glass's Guide](https://glass.co.uk/)
- [Glass's VRM API Transition](https://glass.co.uk/vrm-valuation-api-cvm-transition/)
- [CAP HPI](https://www.cap-hpi.com/)
- [HPI Vehicle Data API](https://www.hpi.co.uk/vehicle-data-api.html)

### Marketplaces B2B
- [BCA Group](https://www.bca.com/)
- [Manheim API Developer Portal](https://developer.manheim.com/)
- [OPENLANE Corporate](https://corporate.openlane.com/)
- [CarOnSale](https://www.caronsale.com/en)
- [CarOnSale + Fivetran](https://www.fivetran.com/case-studies/fivetran-accelerates-online-auto-trading-for-caronsale)
- [AUTOonline — Solera](https://www.solera.com/solutions/vehicle-claims/autoonline/)
- [Autorola Group](https://www.autorolagroup.com/)
- [Autorola FM Integration API — SwaggerHub](https://app.swaggerhub.com/apis/Autorola/FM_Integration_API/)
- [CarDataHub](https://www.cardatahub.com/)

### Regulación
- [Euro 7 Timeline — Geotab](https://www.geotab.com/ie/blog/euro-7-emission-standard-timeline-eu/)
- [Euro 7 — Webfleet](https://www.webfleet.com/en_gb/webfleet/blog/euro-7-emission-standards/)
- [Euro 7 Implementing Acts — Xeeniq](https://medium.com/@xeeniq/euro-7-implementing-acts-2025-1706-2025-1707)
- [EU Battery Passport — Circularise](https://www.circularise.com/blogs/eu-battery-passport-regulation-requirements)
- [Battery Regulation — EUR-Lex](https://eur-lex.europa.eu/EN/legal-content/summary/sustainability-rules-for-batteries-and-waste-batteries.html)
- [DPP Timeline — PassportCraft](https://passportcraft.com/insights/dpp-timeline-2026-2030-every-deadline)
- [Right to Repair — Fieldfisher](https://www.fieldfisher.com/en/insights/incoming-eu-right-to-repair-requirements-the-key-t)
- [Right to Repair — Regulatory Decoded](https://regulatorydecoded.com/eu-right-to-repair-manufacturers-directive-2024-1799/)
- [EU Data Act Vehicle — TransConnect](https://transconnect.com/en/blog/vehicle-data-under-control-what-the-eu-data-act-means-for-dealers-and-fleet-owners)
- [EU Data Act — LKQ Europe](https://lkqeurope.com/article/public-affairs/eu-data-act-new-era-vehicle-data-access-begins)
- [GDPR Enforcement Report — CMS Law](https://cms.law/en/int/publication/GDPR-Enforcement-Tracker-Report/numbers-and-figures)
- [GDPR Fines 2026 — Kiteworks](https://www.kiteworks.com/gdpr-compliance/gdpr-fines-data-privacy-enforcement-2026/)
- [GDPR Automotive — Infosecurity](https://www.infosecurity-magazine.com/opinions/driving-compliance-data-protection/)
- [Privacy Auto 2026 — Nelson Mullins](https://www.nelsonmullins.com/insights/blogs/driving-forward-developments-in-transportation-law-and-innovation/all/privacy-regulation-of-auto-industry-to-accelerate-in-2026-part-2)

### Pricing APIs
- [MarketCheck Pricing](https://www.marketcheck.com/apis/pricing/)
- [CarAPI Pricing](https://carapi.app/pricing)
- [carVertical Pricing](https://www.carvertical.com/en/pricing)
- [autobiz API](https://corporate.autobiz.com/en/our-products/autobizapi/)
- [Dataforce Market Data](https://www.dataforce.de/en/market-data/)
- [Best Car Value APIs 2026 — VehicleDatabases](https://vehicledatabases.com/articles/best-car-value-api-providers)

### Startups & Funding
- [CarOnSale Series C — Tech.eu](https://tech.eu/2025/07/07/caronsale-secures-70m)
- [AutoGrab Series B — Startup Daily](https://www.startupdaily.net/topic/funding/ai-based-car-valuation-platform-hits-top-get-with-80-million-series-b/)
- [AutoGrab AUD 80M — AutoGrab](https://autograb.com.au/automotive-data-intelligence-provider-autograb-completes-80m-capital-raise-funding-to-support-expansion-into-uk-and-europe-while-accelerating-growth-in-australia/)
- [FINN ABS EUR 1B — EU-Startups](https://www.eu-startups.com/2025/02/car-subscription-service-finn-closes-abs-of-e1-billion-euros-for-financing-its-fleet-growth/)
- [FINN Series C EUR 100M — Tech.eu](https://tech.eu/2024/01/11/finn-secures-100m-in-series-c-round/)
- [MotorK EUR 3M — EU-Startups](https://www.eu-startups.com/2026/01/milano-based-automotive-saas-provider-motork-secures-e3-million-to-bolster-its-financial-position/)
- [Kavak USD 300M — Silicon Valley InvestClub](https://siliconvalleyinvestclub.com/2026/02/23/kavak-raises-300-million-in-funding/)
- [BMW i Ventures Fund III](https://www.press.bmwgroup.com/global/article/detail/T0457479EN/bmw-i-ventures-announces-300-million-fund-to-back-ai-startups-reshaping-the-automotive-ecosystem)
- [Omnetic — Tracxn](https://tracxn.com/d/companies/omnetic/__PbPFzJWOZDq20wzTA8GfD7oI8uCjKwrvULEa5TNBm4E)
- [Brego AI](https://brego.io/)
- [JP.cars](https://jp.cars/)
- [eCarsTrade — Tracxn](https://tracxn.com/d/companies/ecarstrade/__CO6BbpS7bjC_ejqcrKuHeENZi0AtCSev7gadW-T2Nf8)
- [KnowTrex](https://www.knowtrex.com/)
- [Ravin AI — Tracxn](https://tracxn.com/d/companies/ravin/__X3CtGuFQEzi1S1xiKKqtaR-EZV0DFrKydFMsmcBdfcQ)
- [Fixico — Tracxn](https://tracxn.com/d/companies/fixico/__xGyEvJHWf3On769-2s6w43fEFULpbpLpCnbRzQNE8L4)
