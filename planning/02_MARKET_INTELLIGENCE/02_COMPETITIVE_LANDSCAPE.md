# 02 — Competitive Landscape

## Identificador
- Fecha: 2026-04-14, Estado: DOCUMENTADO
- Cobertura: ≥24 competidores en 4 categorías

## Categoría A — Data Providers B2B (datasets sectoriales)

### A1 — Indicata Analytics (S&P Global Mobility)
- **Modelo de negocio:** datos de mercado B2B, análisis de stock y demanda, benchmarking de precios; suscripción enterprise mensual/anual
- **Cobertura geográfica:** EU amplio (~20 países), incluye DE/FR/ES/BE/NL (sin confirmación CH)
- **Fuentes de datos:** aggregators públicos (mobile.de, AutoScout24) + OEM data sharing programs + OBD fleet data
- **Pricing / monetización:** [PV: €€€ — enterprise SaaS, ~€1.000-5.000/mes por módulo según cobertura]
- **Target:** dealers OEM, importadores, financieras, aseguradoras
- **Cobertura estimada del mercado:** Alta en segmento premium; long-tail débil (no indexa micro-dealers sin presencia en aggregators)
- **Debilidades estructurales:**
  - Refresh ~24-48h para precios; no near-realtime
  - Long-tail casi ausente — solo dealers con presencia en aggregators indexados
  - Foco en "market analysis" no en "dealer discovery" — no es un índice navegable por buyer
  - Precio prohibitivo para buyers B2B pequeños/medianos
- **Amenaza competitiva para CARDEX:** MEDIA — sirve a un segmento diferente (grandes grupos, OEM analytics); CARDEX apunta a compradores B2B que necesitan inventario cross-source, no análisis de mercado
- **Diferenciación CARDEX:** índice navegable por vehículo con dedup cross-source; acceso a long-tail; precio de acceso <€€€

### A2 — JATO Dynamics
- **Modelo de negocio:** datos de especificaciones técnicas, pricing de nuevos, opciones OEM; B2B enterprise
- **Cobertura:** global, >50 países, EU completa
- **Fuentes:** OEM directo, registros de homologación, dealer pricelists
- **Target:** OEM, financieras, aseguradoras, dealers grandes
- **Debilidades:** no tiene inventario de vehículos de ocasión; foco en especificaciones de nuevos y residual values
- **Amenaza para CARDEX:** BAJA — mercados distintos; JATO no compite en el espacio de inventario de ocasión
- **Diferenciación:** CARDEX indexa inventario live de ocasión, no specs de nuevos

### A3 — AutoVista Group (Autovista Analytics)
- **Modelo de negocio:** valuaciones de vehículos de ocasión + stock visibility analytics; B2B enterprise
- **Cobertura:** EU amplio; fuerte en FR (herencia Argus) y DACH; débil en ES/BE
- **Fuentes:** datos de matrícula, Argus valuaciones FR, modelos estadísticos
- **Debilidades:** no es un índice de inventario live — es un modelo de valoración; la cobertura fuera de FR/DE es limitada
- **Amenaza para CARDEX:** BAJA-MEDIA — un buyer que necesita valuaciones usa AutoVista; un buyer que necesita encontrar stock usa CARDEX
- **Diferenciación:** CARDEX sirve para encontrar vehículos, no para valorarlos

### A4 — EurotaxGlass's (parte de Autovista Group)
- **Modelo de negocio:** valuaciones y códigos de equipamiento estándar; DACH dominante
- **Cobertura:** DACH, expansión EU limitada
- **Target:** dealers, aseguradoras, financieras — principalmente para valoraciones de tasación
- **Debilidades:** no inventario live; foco en DACH; precio alto para acceso completo
- **Amenaza para CARDEX:** BAJA

### A5 — DAT (Deutsche Automobil Treuhand GmbH)
- **Modelo de negocio:** valuaciones, DAT-Codes (estándar DE para opciones/equipamiento), e-DAT platform
- **Cobertura:** DE dominante; algunos mercados vecinos DE-influenciados (AT, CH)
- **Fuentes:** KBA data + DAT database propietaria
- **Target:** dealers DE, talleres, aseguradoras, financieras
- **Relevancia para CARDEX:** los DAT-Codes son el vocabulario estándar de equipamiento en DE — V18 (equipment normalization) puede mapear a DAT-Codes
- **Amenaza para CARDEX:** BAJA (complementario más que competidor)

### A6 — AAA Data (grupo AAA en FR)
- **Modelo de negocio:** datos de registro de flota, historial de vehículos, B2B analytics
- **Cobertura:** FR principalmente; acceso a datos SIV/ANTS
- **Target:** aseguradoras, financieras, dealers FR
- **Debilidades:** FR-centric; no pan-europeo; enfocado en historial más que en inventario live
- **Amenaza para CARDEX:** BAJA

---

## Categoría B — Marketplaces B2C/B2B con componente profesional

### B7 — mobile.de (Scout24 AG)
- **Modelo de negocio:** marketplace de anuncios de vehículos; revenue: listings de pago para dealers, premium placements, leads B2B, API para dealers (partners)
- **Cobertura:** DE dominante, algunos listings AT/CH, listings internacionales limitados
- **Usuarios:** 70%+ B2C + dealers profesionales (Händlersuche)
- **Fuentes de datos:** listings directos de dealers (alta calidad); plataforma propia
- **API B2B:** mobile.de ofrece API de partner para dealers grandes (carga de inventario, no consulta de inventario de competidores)
- **Cobertura DE:** ~1,5-2 millones de listings activos en picos; ~37.000 dealers registrados (own claim [PV])
- **Debilidades para compradores B2B:**
  - Solo DE — no sirve para buscar en FR/ES/NL
  - No cross-source dedup — el mismo vehículo puede aparecer en mobile.de Y AutoScout24
  - Sin NLG propio — las descripciones son las del dealer (calidad variable)
  - Acceso a datos no es open — buyers B2B no pueden descargar el índice
- **Amenaza para CARDEX:** ALTA en DE (es la fuente dominante y podría lanzar producto B2B cross-source), pero su modelo de negocio es marketplace, no índice exportable
- **Diferenciación CARDEX:** multi-país, cross-source dedup, long-tail, API de consulta

### B8 — AutoScout24 (Scout24 AG, mismo grupo que mobile.de)
- **Modelo de negocio:** igual que mobile.de, foco pan-europeo
- **Cobertura:** multi-TLD (DE, IT, FR, BE, NL, AT, CH, ES), aunque la profundidad varía mucho por país
- **Debilidades:**
  - Mismas debilidades que mobile.de + fragmentación por TLD nacional
  - Sin cross-country dedup entre sus propios TLDs
  - Listings en IT/ES más débiles que en DE
- **Amenaza para CARDEX:** ALTA (es el competidor más parecido en cobertura geográfica), pero mismo modelo marketplace sin índice exportable
- **Diferenciación CARDEX:** cobertura long-tail, cross-source dedup, API de datos

### B9 — La Centrale (Argus Group, FR)
- **Modelo de negocio:** marketplace B2C + sección "Pro" para dealers FR
- **Cobertura:** FR dominante
- **Target:** B2C mayoría; dealers FR en sección Pro
- **Debilidades:** FR-only; sin cross-source; sin API pública
- **Amenaza para CARDEX:** MEDIA en FR

### B10 — Coches.net / Autocasion (Adevinta)
- **Modelo de negocio:** marketplaces ES
- **Cobertura:** ES dominante (Coches.net #1, Autocasion #2)
- **Target:** B2C + dealers
- **Amenaza para CARDEX:** MEDIA en ES; sin alcance internacional

### B11 — 2dehands.be / Marktplaats.nl (eBay Classifieds, renombrado Adevinta)
- **Modelo de negocio:** clasificados generales con sección de coches
- **Cobertura:** BE y NL respectivamente
- **Debilidades:** clasificados generalistas — calidad de datos de vehículos inferior a portales especializados
- **Amenaza para CARDEX:** BAJA — segmento diferente (B2C generalista)

### B12 — AutoTrack.nl
- **Modelo de negocio:** comparador de coches NL (B2C)
- **Cobertura:** NL
- **Debilidades:** NL-only; comparador B2C, no índice B2B
- **Amenaza para CARDEX:** BAJA

### B13 — Autoline-EU
- **Modelo de negocio:** marketplace pan-europeo de vehículos comerciales (camiones, furgonetas)
- **Cobertura:** pan-EU (~30 países)
- **Target:** transportistas, dealers de vehículos comerciales
- **Relevancia para CARDEX:** vehículos comerciales están fuera del scope inicial de CARDEX; potencial expansión futura
- **Amenaza para CARDEX:** MUY BAJA (scope diferente)

---

## Categoría C — Auction Houses + B2B Platforms

### C14 — BCA Europe (BCA Group / Constellation Automotive)
- **Modelo de negocio:** subastas B2B físicas y online de vehículos de ocasión; revenue por comisión de subasta + servicios de preparación
- **Cobertura:** EU amplio (UK, DE, FR, ES, BE, NL, IT, SE, etc.) — uno de los mayores en Europa
- **Target:** dealers profesionales comprando/vendiendo stock en bloque; financieras con desinversiones de flota
- **Diferencia fundamental:** BCA es un canal de **transacción** (compra/venta en subasta); CARDEX es un canal de **descubrimiento** (índice de quién tiene qué)
- **Debilidades para CARDEX scope:**
  - Solo stock que pasa por sus subastas — no incluye stock en lote del dealer
  - Acceso restringido a compradores registrados (no índice abierto)
  - No indexa el long-tail de dealers pequeños
- **Amenaza para CARDEX:** BAJA (canal complementario, no sustituto)
- **Diferenciación CARDEX:** CARDEX muestra el stock que el dealer tiene en su lote/web, no el que va a subasta

### C15 — CarOnSale (DE, online B2B auction)
- **Modelo de negocio:** subasta online B2B, enfocado en dealers DE y AT
- **Cobertura:** DE/AT principalmente
- **Target:** dealers comprando/vendiendo stock entre sí (B2B dealer-to-dealer)
- **Amenaza para CARDEX:** BAJA-MEDIA — complementario en modelo de transacción

### C16 — Manheim Express / Manheim (Cox Automotive)
- **Modelo de negocio:** subastas B2B, marketplace digital; fuerte en UK/US, presencia EU
- **Target:** dealers, financieras, fabricantes con desinversiones de flota
- **Amenaza para CARDEX:** BAJA (mismo argumento que BCA)

### C17 — ADESA Europe / Openlane (KAR Global)
- **Modelo de negocio:** subastas B2B online + marketplace
- **Cobertura:** EU (BE base europea)
- **Target:** igual que BCA/Manheim
- **Amenaza para CARDEX:** BAJA

---

## Categoría D — Aggregators / Meta-searches con spillover B2B

### D18 — AutoUncle
- **Modelo de negocio:** comparador de precios de coches de ocasión; B2C price transparency + dealer leads
- **Cobertura:** pan-EU (~15 países); agrega datos de mobile.de, AutoScout24, etc.
- **Target:** compradores B2C que quieren comparar precios
- **Relevancia para CARDEX:** AutoUncle hace algo parecido al discovery de CARDEX pero solo para mostrar precios B2C, sin dedup, sin API exportable, sin NLG propio
- **Debilidades:** B2C-only; no API para compradores B2B; sin long-tail
- **Amenaza para CARDEX:** MEDIA (el más parecido en modelo técnico, pero orientado a B2C)
- **Diferenciación CARDEX:** B2B, API, cross-source dedup, long-tail, NLG propio

### D19 — Carvago (Mall Group, CZ)
- **Modelo de negocio:** compra online de coches de ocasión (B2C ecommerce) con entrega cross-border
- **Cobertura:** CZ, SK, DE, AT, HU y expansión EU
- **Target:** B2C
- **Amenaza para CARDEX:** BAJA (B2C seller, no índice B2B)

### D20 — Heycar (Volkswagen Group)
- **Modelo de negocio:** marketplace de coches certificados (OEM-certified used cars); financiado por VW Group
- **Cobertura:** DE, FR, ES (expansión)
- **Debilidades:** solo coches "certified" (garantizados por dealer OEM) — excluye long-tail por diseño
- **Amenaza para CARDEX:** BAJA (segmento premium OEM-certified, no cross-source)

### D21 — CarGurus (US, expansión EU)
- **Modelo de negocio:** marketplace B2C con Deal Rating; revenue: leads para dealers
- **Cobertura:** UK fuerte, DE/FR en expansión
- **Target:** B2C + dealers
- **Amenaza para CARDEX:** MEDIA a largo plazo si CarGurus expande agresivamente en EU y lanza componente B2B
- **Diferenciación CARDEX:** EU Data Act, long-tail, cross-source dedup, sin dependencia de revenue de dealers para publicar

### D22 — Autohero (Auto1 Group)
- **Modelo de negocio:** compra online B2C de coches de ocasión (Auto1 es el vehículo comprador del dealer, Autohero es el canal de venta al consumidor)
- **Cobertura:** DE, FR, ES, NL, BE y otros
- **Target:** B2C consumidores finales
- **Amenaza para CARDEX:** BAJA — son el dealer, no un índice

### D23 — Cazoo (UK, en restructuring)
- **Modelo de negocio:** similar a Autohero — B2C online car retailer
- **Cobertura:** UK principalmente; expansión EU pausada por dificultades financieras (~2023-2024)
- **Amenaza para CARDEX:** MUY BAJA

### D24 — CarSpring / Wirkaufendeinauto (Autobid, DE)
- **Modelo de negocio:** compra directa de coches al consumidor; wholesale B2B (vende a dealers)
- **Target:** consumidores vendiendo + dealers comprando
- **Amenaza para CARDEX:** BAJA

---

## Matrix resumen competidores × dimensiones clave

| Competidor | Tipo | Cobertura geo | Long-tail | Cross-source dedup | API B2B | NLG propio | Acceso libre | Amenaza |
|---|---|---|---|---|---|---|---|---|
| Indicata (S&P) | Data B2B | EU multi | ✗ | Parcial | ✓ (pago) | ✗ | ✗ | MEDIA |
| JATO | Data B2B | Global | ✗ | ✗ | ✓ (pago) | ✗ | ✗ | BAJA |
| AutoVista / Argus | Data B2B | EU | ✗ | ✗ | ✓ (pago) | ✗ | ✗ | BAJA |
| DAT | Data B2B | DACH | ✗ | ✗ | ✓ (pago) | ✗ | ✗ | BAJA |
| mobile.de | Marketplace | DE | Parcial | ✗ | Partner only | ✗ | ✗ | ALTA |
| AutoScout24 | Marketplace | EU multi | Parcial | ✗ | Partner only | ✗ | ✗ | ALTA |
| La Centrale | Marketplace | FR | Parcial | ✗ | ✗ | ✗ | ✗ | MEDIA-FR |
| Coches.net | Marketplace | ES | Parcial | ✗ | ✗ | ✗ | ✗ | MEDIA-ES |
| BCA/Manheim | Auction B2B | EU | ✗ | ✗ | ✓ (pago) | ✗ | ✗ | BAJA |
| CarOnSale | Auction B2B | DE/AT | ✗ | ✗ | ✓ | ✗ | ✗ | BAJA |
| AutoUncle | Aggregator | EU multi | ✗ | Parcial | ✗ | ✗ | ✓ | MEDIA |
| CarGurus EU | Marketplace | UK/DE | Parcial | ✗ | ✗ | ✗ | ✗ | MEDIA |
| Heycar | Marketplace | DE/FR/ES | ✗ | ✗ | ✗ | ✗ | ✗ | BAJA |
| **CARDEX** | **Índice B2B** | **6 países EU** | **✓✓** | **✓✓** | **✓ open** | **✓** | **✓** | — |

---

## Posicionamiento único de CARDEX

CARDEX ocupa un nicho que actualmente no tiene ocupante:

1. **Cobertura long-tail:** los ~40.000-50.000 micro-dealers (<10 vehículos en stock) son invisibles para los grandes data providers y sub-representados en los marketplaces. CARDEX, gracias a las 15 familias de discovery, los captura.

2. **Cross-source dedup:** el mismo vehículo puede aparecer en mobile.de, AutoScout24, y el sitio propio del dealer. CARDEX deduplica por VIN y presenta un único registro con múltiples fuentes — mayor confianza.

3. **NLG propio:** las descripciones de CARDEX son originales (no copias del dealer). Esto elimina el riesgo de derechos de autor y produce descripciones neutras y profesionales para el comprador B2B.

4. **EU Data Act Edge Client:** el mecanismo legal E11 permite a dealers que no publican en ningún aggregator dar acceso directo a su inventario — un canal que ningún competidor tiene.

5. **API exportable sin barrera:** los buyers B2B pueden integrar CARDEX en sus sistemas propios (ERP, DMS) via API, algo que mobile.de y AutoScout24 no ofrecen en abierto.

6. **€0 OPEX en licencias:** esto se traduce en pricing de acceso competitivo para los compradores B2B — mientras Indicata cobra €€€ enterprise, CARDEX puede permitirse tiers accesibles.
