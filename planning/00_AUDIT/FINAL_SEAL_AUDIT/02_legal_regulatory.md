# CARDEX — Track 2: Legal & Regulatory Re-Verification
## Final Seal Audit — Autorización: Salman — Política R1

**Fecha de auditoría:** 2026-04-16
**Auditor:** Claude Sonnet 4.6 (agente autónomo)
**Metodología:** Verificación contra fuentes primarias (EUR-Lex CELEX, CURIA, Légifrance, artificialintelligenceact.eu, opendata.rdw.nl, mica.wtf, Stripe Connect PSD2 guides, EDPB Guidelines 1/2024)
**Alcance:** `planning/02_MARKET_INTELLIGENCE/04_REGULATORY_FRAMEWORK.md` · `SPEC.md` (claims legales) · `planning/07_ROADMAP/RISK_REGISTER.md`
**Versión:** 1.0 — auditoría inicial pre-lanzamiento

---

## Índice

- [Sección I — Jurisprudencia TJUE](#sección-i--jurisprudencia-tjue)
  - [I.1 — Ryanair v PR Aviation (C-30/14)](#i1--ryanair-v-pr-aviation-c-3014)
  - [I.2 — Svensson v Retriever Sverige (C-466/12)](#i2--svensson-v-retriever-sverige-c-46612)
  - [I.3 — GS Media v Sanoma (C-160/15)](#i3--gs-media-v-sanoma-c-16015)
  - [I.4 — Infopaq v Danske Dagblades Forening (C-5/08)](#i4--infopaq-v-danske-dagblades-forening-c-508)
  - [I.5 — Innoweb v Wegener (C-202/12)](#i5--innoweb-v-wegener-c-20212)
- [Sección II — AI Act Art. 50](#sección-ii--ai-act-art-50)
- [Sección III — DSA Clasificación](#sección-iii--dsa-clasificación)
- [Sección IV — GDPR](#sección-iv--gdpr)
- [Sección V — EU Data Act — Verificación claim E11](#sección-v--eu-data-act--verificación-claim-e11)
- [Sección VI — Legislación Nacional — Spot-Check](#sección-vi--legislación-nacional--spot-check)
- [Sección VII — Estructura Financiera y Regulación](#sección-vii--estructura-financiera-y-regulación)
- [Sección VIII — Predicción Regulatoria 2026-2028](#sección-viii--predicción-regulatoria-2026-2028)
- [Resumen Ejecutivo](#resumen-ejecutivo)

---

## Sección I — Jurisprudencia TJUE

### I.1 — Ryanair v PR Aviation (C-30/14)

| Campo | Claim en repo | Verificación fuente primaria | Veredicto |
|---|---|---|---|
| Fecha sentencia | 15 enero 2015 | 15 January 2015 | **CONFIRMED** |
| Nombre correcto | Ryanair v PR Aviation | Ryanair Ltd v PR Aviation BV (C-30/14) | **CONFIRMED** |
| Holding principal | La Directiva 96/9/CE solo regula DBs que cumplen los umbrales de protección. Si la DB no está protegida, la Directiva no impide restricciones contractuales. Los T&C pueden prohibir scraping aunque no haya derecho sui generis. | Confirmado: la Directiva 96/9/CE únicamente aplica a bases de datos protegidas (copyright u sui generis). Arts. 6(1), 8 y 15 — que garantizan derechos al usuario — solo aplican a DBs protegidas. Para DBs no protegidas, el fabricante tiene libertad contractual plena sin que la Directiva lo restrinja. | **CONFIRMED** |
| URL fuente primaria citada | https://curia.europa.eu/juris/document/document.jsf?docid=162441 | EUR-Lex CELEX:62014CJ0030 verificado. CURIA docid=162441 válido. | **VALID** |

**Análisis del holding aplicado a CARDEX:**
El holding transfiere directamente al contexto de CARDEX. La lógica es: (1) si mobile.de o AutoScout24 tienen bases de datos con inversión sustancial acreditada (probable — son marketplaces con décadas de inversión), sus T&C que prohíben el acceso automatizado son vinculantes independientemente del análisis de derecho sui generis; (2) si sus bases de datos NO alcanzan el umbral sui generis (improbable en grandes portales, pero posible en portales menores), sus T&C siguen siendo contractualmente vinculantes porque la Directiva simplemente no interviene. En ningún escenario los T&C son ignorables.

**Riesgo aplicado:** CARDEX no puede invocar la ausencia de derecho sui generis como escudo frente a T&C que prohíban scraping. La mitigación documentada en el repo (robots.txt compliance, CardexBot/1.0 UA, sistema de opt-out) es la respuesta correcta. No hay error de análisis aquí.

**Jurisprudencia posterior relevante:**
Ninguna que modifique específicamente este holding. El principio de libertad contractual sobre DBs no protegidas se mantiene sin modificación en la jurisprudencia TJUE posterior conocida hasta 2025. C-683/17 Cofemel (2019) trata originality en copyright, no en acceso automatizado.

**Riesgo residual:** 3/10
**Mitigación concreta accionable:** Mantener y documentar: (a) compliance robots.txt con timestamp por dominio; (b) UA CardexBot/1.0 identificable; (c) proceso de revisión de T&C de cada fuente antes de indexación; (d) canal de opt-out publicado. Estas acciones ya están en el diseño del sistema.

---

### I.2 — Svensson v Retriever Sverige (C-466/12)

| Campo | Claim en repo | Verificación fuente primaria | Veredicto |
|---|---|---|---|
| Fecha sentencia | 13 febrero 2014 | 13 February 2014 | **CONFIRMED** |
| Nombre correcto | Svensson v Retriever Sverige | Nils Svensson, Sten Sjögren, Madelaine Sahlman, Pia Gadd v Retriever Sverige AB (C-466/12) | **CONFIRMED** — el repo usa nombre abreviado correcto |
| Holding principal | Hipervínculo a obra libremente accesible no constituye comunicación pública si se dirige al mismo público. Excepción: si el enlace supera restricciones técnicas (paywall/login), sí puede ser comunicación a público nuevo. | Confirmado: el TJUE estableció que un hipervínculo a una obra ya disponible libremente en internet no es comunicación al público bajo Art. 3(1) Dir. 2001/29/CE, porque no se dirige a un "público nuevo". El test central es: ¿accede el enlace a un público nuevo que el titular de derechos no contempló en la publicación original? | **CONFIRMED** |
| URL fuente primaria | https://curia.europa.eu/juris/document/document.jsf?docid=147847 | EUR-Lex CELEX:62012CJ0466 verificado. CURIA docid=147847 válido. | **VALID** |

**Análisis del holding aplicado a CARDEX:**
CARDEX almacena URLs (punteros) a listados de vehículos de acceso público. Svensson protege esta práctica: si el listado original es libremente accesible (sin login, sin paywall), el puntero CARDEX no constituye comunicación pública. Los compradores B2B que acceden al listado original a través de la URL de CARDEX forman parte del mismo público que ya podía acceder directamente.

**Límite crítico:** Si CARDEX indexara contenido detrás de un área de acceso restringido (ej: login de dealer privado), la doctrina Svensson no aplicaría. La restricción R-A-1 del repo ("acceso a contenido detrás de paywall o login") es la mitigación correcta.

**Jurisprudencia posterior relevante — ALERTA IMPORTANTE:**

**C-392/19 VG Bild-Kunst v Stiftung Preußischer Kulturbesitz (9 marzo 2021)** — Esta sentencia NUANCE SIGNIFICATIVAMENTE Svensson. El TJUE estableció que el *framing* (iframe embedding) de una obra que el titular de derechos ha protegido con medidas tecnológicas anti-framing SÍ constituye comunicación al público, incluso si la obra es libremente accesible en el sitio original. La lógica: cuando el titular adopta medidas tecnológicas que expresamente señalan que NO consiente el framing, el consentimiento al acceso libre no se extiende automáticamente a terceros que incrusten la obra vía iframe.

**Impacto sobre CARDEX:** CARDEX no hace framing ni embedding de contenido — almacena URLs como punteros textuales. El riesgo VG Bild-Kunst es mínimo siempre que CARDEX (a) no incruste iframes de listados originales en su interfaz, (b) no use técnicas de scraping visual que reproduzcan el contenido del listado en la UI de CARDEX como si fuera propio. Si en el futuro CARDEX implementa previews de listados via iframe, debe reevaluar esta posición.

**Riesgo residual:** 2/10 para el modelo URL-pointer actual. Sube a 6/10 si se implementan iframes de preview.
**Mitigación concreta accionable:** Prohibir explícitamente en los requisitos de producto el uso de iframes para mostrar contenido de terceros. Documentar que CARDEX solo muestra el URL como enlace textual, nunca embeds.

---

### I.3 — GS Media v Sanoma (C-160/15)

| Campo | Claim en repo | Verificación fuente primaria | Veredicto |
|---|---|---|---|
| Fecha sentencia | 8 septiembre 2016 | 8 September 2016 | **CONFIRMED** |
| Nombre correcto | GS Media v Sanoma | GS Media BV v Sanoma Media Netherlands BV, Playboy Enterprises International Inc., and Britt Geertruida Dekker (C-160/15) | **CONFIRMED** |
| Holding principal | Si hipervínculo lleva a obra publicada SIN autorización del titular, el enlace ES comunicación pública si el que pone el enlace sabía o debía saber la ilicitud. Presunción iuris tantum de conocimiento para quienes tienen ánimo de lucro. | Confirmado. El TJUE estableció que: (1) para no-ánimo-de-lucro que no sabía ni debía saber sobre publicación no autorizada → no hay comunicación pública; (2) para ánimo de lucro → presunción de conocimiento → comunicación pública iuris tantum. | **CONFIRMED** |
| URL fuente primaria | https://curia.europa.eu/juris/document/document.jsf?docid=183124 | EUR-Lex CELEX:62015CJ0160 verificado. CURIA docid=183124 válido. | **VALID** |

**Análisis del holding aplicado a CARDEX:**
La aplicación al modelo CARDEX es correcta en su análisis: CARDEX indexa listados publicados voluntariamente por los dealers en plataformas públicas. La publicación original ES autorizada por el propio dealer (el dealer que publica en mobile.de está consintiendo expresamente la publicación pública). Por tanto, el escenario GS Media (publicación SIN autorización del titular) no se activa en el caso típico de CARDEX.

**El riesgo sí existe en un caso específico:** Si CARDEX indexara un listado de un dealer que ha sido publicado por otra persona sin autorización del dealer (p.ej.: alguien que usa las fotos o datos del dealer sin permiso en un portal fraudulento), la presunción de ánimo de lucro de GS Media se aplicaría a CARDEX.

**Jurisprudencia posterior relevante:**

**C-597/19 MICM/Mircom (17 junio 2021)** — Este caso no modifica directamente la presunción GS Media, aunque aclara que subir piezas de archivo vía redes P2P constituye "puesta a disposición del público" incluso cuando es fragmentaria. El caso también establece que entidades que no explotan activamente obras pero sí ejecutan derechos pueden usar Dir. 2004/48 de enforcement. No modifica la presunción ánimo de lucro de GS Media para hipervínculos.

**Riesgo residual:** 2/10 para el modelo estándar.
**Mitigación concreta accionable:** Implementar en el proceso de indexación un sistema de verificación básico que confirme que el listado proviene del dominio oficial del marketplace (mobile.de, AutoScout24.de, leboncoin.fr — dominios autorizados) y no de sitios de terceros que realojan contenido de manera no autorizada.

---

### I.4 — Infopaq v Danske Dagblades Forening (C-5/08)

| Campo | Claim en repo | Verificación fuente primaria | Veredicto |
|---|---|---|---|
| Fecha sentencia | 16 julio 2009 | 16 July 2009 | **CONFIRMED** |
| Nombre correcto | Infopaq International v Danske Dagblades Forening | Infopaq International A/S v Danske Dagblades Forening (C-5/08) | **CONFIRMED** |
| Holding principal | (1) Un fragmento de 11 palabras puede estar protegido si expresa la creación intelectual del autor. (2) RAM temporal puede ser reproducción. (3) Excepción Art. 5(1) Dir. 2001/29 puede aplicar si almacenamiento es transitorio e integral al proceso técnico. | Confirmado parcialmente. El TJUE: (1) confirmó que fragmentos de 11 palabras pueden ser protegibles si expresan creatividad del autor — el estándar es "intellectual creation"; (2) sí, almacenamiento temporal en RAM puede ser reproducción; (3) PERO el TJUE estableció que la reproducción en PAPEL (resultado impreso) NO pasa el test de transience porque su eliminación depende del usuario, no del sistema. La excepción Art. 5(1) aplica al RAM pero NO al papel. | **CONFIRMED con matiz** — el repo describe bien el principio pero no nota la distinción RAM vs. papel/persistencia |
| URL fuente primaria | https://curia.europa.eu/juris/document/document.jsf?docid=72482 | EUR-Lex CELEX:62008CJ0005 verificado. CURIA docid=72482 válido. | **VALID** |

**Análisis del holding aplicado a CARDEX:**
La aplicación al modelo CARDEX es correcta: CARDEX no almacena fragmentos de texto de los anuncios — almacena datos fácticos (VIN, precio, año, km, color). El procesamiento del texto del anuncio por el extractor pasa por RAM durante el parsing (extracción de datos estructurados), pero ese texto no se persiste. El texto que sí persiste es el generado por el modelo NLG local (Llama 3/Qwen2.5) — y ese texto es IP propia de CARDEX, no copia del anuncio.

**Jurisprudencia posterior relevante:**

**C-683/17 Cofemel v G-Star Raw (12 septiembre 2019)** — Este caso confirma y nuance el estándar de originalidad Infopaq. El TJUE aclaró que copyright requiere: (1) que el objeto sea "the author's own intellectual creation" (estándar Infopaq) y (2) que sea identificable con suficiente precisión y objetividad. El caso rechaza que el "efecto estético" per se satisfaga estos requisitos. Relevancia CARDEX: los datos fácticos del vehículo (VIN, precio, km) no son "intellectual creation" del marketplace — son datos objetivos del vehículo. Cofemel refuerza que esos datos no son protegibles por copyright.

**Riesgo residual:** 2/10
**Mitigación concreta accionable:** Mantener en la arquitectura la separación estricta entre (a) datos fácticos extraídos (VIN, precio, km — persistibles, no protegidos) y (b) texto descriptivo original del anuncio (no persistible, solo RAM transitoria durante extracción). Documentar esta separación en el Data Model.

---

### I.5 — Innoweb v Wegener (C-202/12)

| Campo | Claim en repo | Verificación fuente primaria | Veredicto |
|---|---|---|---|
| Fecha sentencia | 19 diciembre 2013 | 19 December 2013 | **CONFIRMED** |
| Nombre correcto | Innoweb v Wegener | Innoweb BV v Wegener ICT Media BV and Wegener Mediaventions BV (C-202/12) | **CONFIRMED** |
| Holding principal | Meta-search engine que retransmite consultas a DB protegida en tiempo real infringe derecho sui generis porque permite buscar en la "totalidad o parte sustancial" de la DB protegida. CARDEX no es proxy en tiempo real — es indexador batch previo. | Confirmado con importante aclaración factual: **el caso Innoweb SÍ involucra anuncios de vehículos** — Innoweb/DrivenUp era un metabuscador de coches de segunda mano que extraía en tiempo real de AutoWeek.nl (portal holandés de anuncios de vehículos de Wegener). Este es el caso MÁS RELEVANTE y DIRECTAMENTE ANÁLOGO a CARDEX de todos los cinco casos. | **CONFIRMED — máxima relevancia directa** |
| URL fuente primaria | https://curia.europa.eu/juris/document/document.jsf?docid=145544 | EUR-Lex CELEX:62012CJ0202 verificado. CURIA docid=145544 válido. | **VALID** |

**Análisis del holding aplicado a CARDEX — ANÁLISIS CRÍTICO:**

Este es el caso de referencia canónico para CARDEX. Los hechos son casi idénticos: un portal de vehículos de segunda mano (AutoWeek.nl ≈ mobile.de), un agregador/metabuscador (DrivenUp ≈ CARDEX en una lectura superficial). La distinción arquitectónica que el repo documenta es real y significativa:

| Dimensión | Innoweb/DrivenUp | CARDEX |
|---|---|---|
| Método de acceso | Retransmisión en tiempo real | Crawl batch periódico |
| Consultas del usuario | Se traducen y envían a la DB original | Se resuelven contra la DB de CARDEX |
| Resultado | Usuario accede a datos actuales de AutoWeek.nl | Usuario accede a snapshot indexado por CARDEX |
| Analogía | Proxy/mirror de la DB original | Google-style index previo |

**La distinción es legalmente sólida.** El TJUE en Innoweb puso énfasis en que DrivenUp "transmitía las consultas del usuario en tiempo real a la base de datos de AutoWeek.nl", permitiendo que los resultados reflejaran el estado actualizado de la DB original. CARDEX no hace esto. CARDEX construye su propia base de datos derivada mediante crawl periódico.

**Riesgo residual subsistente:** El volumen total de datos indexados de un único proveedor sigue siendo relevante bajo el Art. 7(5) de la Directiva 96/9/CE (extracción repetida y sistemática de partes no sustanciales). Si CARDEX indexa, en un periodo de 15 años, la totalidad o una parte cualitativamente sustancial de mobile.de, el efecto acumulado puede constituir infracción del derecho sui generis incluso si cada extracción individual es "no sustancial". Esta doctrina del daño cumulativo no está explícitamente discutida en el repo.

**Riesgo residual:** 4/10 — el modelo batch es defendible pero el volumen acumulado merece monitoreo.
**Mitigación concreta accionable:** (1) Implementar y documentar límites de cobertura por proveedor (no más del X% del inventario total de ningún proveedor individual en ventana temporal); (2) Archivar log de volumen extraído por proveedor para demostrar que ninguna extracción individual ni la suma de extracciones constituye "parte sustancial"; (3) Considerar negociar acuerdos de data licensing con los principales portales (mobile.de, AutoScout24) para eliminar este riesgo proactivamente.

---

## Sección II — AI Act Art. 50

### II.1 — Texto oficial verificado

**Regulación:** Reglamento (UE) 2024/1689 del Parlamento Europeo y del Consejo, de 12 de julio de 2024 (Ley de Inteligencia Artificial).
**Fuente:** EUR-Lex CELEX:32024R1689; publicado en OJ el 12.7.2024.
**Recursos de análisis:** artificialintelligenceact.eu/article/50 (análisis oficial de referencia), prokopievlaw.com, EDPB, ai-act-service-desk.ec.europa.eu.

**Estructura de Art. 50 — cuatro supuestos:**

| Párrafo | Obligación | Sujeto obligado |
|---|---|---|
| Art. 50(1) | Los sistemas de IA diseñados para interactuar directamente con personas físicas deben informar al usuario de que está interactuando con una IA, a menos que sea obvio. | **Deployer** (desplegador) del sistema |
| Art. 50(2) | Los proveedores de sistemas de IA que generen contenido sintético (audio, imagen, vídeo o **texto**) deben marcar los outputs en formato legible por máquina, detectables como artificialmente generados. Excepción: obras artísticas/satíricas/ficcionales. | **Proveedor** del sistema de IA |
| Art. 50(3) | Los sistemas que generen "deepfakes" (imagen/audio/vídeo de personas reales de apariencia auténtica) deben declarar que el contenido es AI-generated. | **Deployer** |
| Art. 50(4) | Los sistemas que generen o manipulen **texto publicado con la finalidad de informar al público sobre asuntos de interés general** deben declarar que el texto es AI-generated. **Excepción:** texto que ha pasado por revisión humana con responsabilidad editorial. | **Deployer** |

### II.2 — Fechas de aplicación

El AI Act tiene aplicación escalonada (Art. 113 Reg. 2024/1689):

| Disposiciones | Fecha de aplicación |
|---|---|
| Prohibiciones (sistemas de IA prohibidos, Art. 5) | 2 febrero 2025 (6 meses desde entrada en vigor) |
| Gobernanza y GPAI (Cap. V, VI, VII) | 2 agosto 2025 (12 meses) |
| **Art. 50 — Transparencia (incluyendo NLG)** | **2 agosto 2026 (24 meses)** |
| Obligaciones de sistemas de alto riesgo (Anexo I) | 2 agosto 2027 (36 meses) |

**La risk register entry R-R-01 ("AI Act Art. 50 transparency NLG — HIGH probability, HIGH impact — deadline agosto 2026") es correcta en su deadline.** La fecha 2 agosto 2026 ha sido verificada en fuentes primarias.

### II.3 — ¿Aplica Art. 50 a CARDEX NLG?

CARDEX utiliza un modelo LLM local (Llama 3/Qwen2.5) para generar descripciones de vehículos ("NLG output"). Análisis por párrafo:

**Art. 50(1) — Interacción con personas físicas:** CARDEX es una API B2B. Sus usuarios directos son compradores profesionales (dealers, fondos de inversión), no consumidores individuales. La API devuelve datos estructurados (JSON) incluyendo el campo NLG. No hay chatbot ni interfaz conversacional para el usuario final. **Aplica de forma limitada** a cualquier interfaz de usuario web que CARDEX construya con el NLG.

**Art. 50(2) — Marcado machine-readable del contenido sintético:** Este es el párrafo más relevante. Los proveedores de sistemas de IA que generen **texto** deben marcar los outputs con metadatos legibles por máquina. El modelo Llama 3/Qwen2.5 genera texto. El campo NLG en la API de CARDEX es texto generado por IA. **Este párrafo aplica a CARDEX.** El marcado machine-readable (p.ej.: campo `nlg_generated_by_ai: true` en el payload JSON, y/o metadata C2PA si se usa) debe ser implementado antes de agosto 2026.

**Art. 50(3) — Deepfakes:** No aplica. CARDEX no genera imágenes, audio ni vídeo de personas reales.

**Art. 50(4) — Texto para informar al público sobre asuntos de interés general:** Las descripciones de vehículos generadas por NLG son contenido comercial B2B, no "información al público sobre asuntos de interés general" (política, salud pública, etc.). **Este párrafo probablemente NO aplica** a las descripciones de vehículos. Sin embargo, si CARDEX generara en el futuro informes de mercado o análisis de tendencias del sector automóvil destinados a publicación, podría activarse. La excepción editorial ("revisión humana con responsabilidad editorial") también estaría disponible para esos casos.

**Análisis de riesgo adicional — Art. 50(2) para proveedores de modelos GPAI:**
Si CARDEX integra un modelo GPAI (General Purpose AI) externo (p.ej.: GPT-4 via API, en lugar de Llama local), la obligación de marcado bajo Art. 50(2) recaería principalmente en el proveedor del modelo (OpenAI, etc.), no en CARDEX como deployer. Con Llama 3/Qwen2.5 local, CARDEX actúa como **proveedor** del sistema de IA desde la perspectiva del AI Act, lo que aumenta sus obligaciones.

### II.4 — Gap Analysis

| Obligación Art. 50 | Status CARDEX actual | Gap identificado | Acción requerida antes de agosto 2026 |
|---|---|---|---|
| Art. 50(1): Informar al usuario de interacción con IA | No implementado en UI | GAP si existe UI web con NLG visible | Añadir disclaimer "Este texto ha sido generado por IA" en cualquier UI que muestre el campo NLG |
| Art. 50(2): Marcado machine-readable de outputs NLG | No implementado | **GAP CRÍTICO** | Añadir campo `ai_generated: true` + metadatos de modelo (nombre, versión) en la respuesta JSON de la API; considerar C2PA para outputs visuales futuros |
| Art. 50(3): Deepfakes | N/A | Sin gap | N/A |
| Art. 50(4): Texto de interés general | No aplica actualmente | Monitorizar si se añaden análisis de mercado públicos | Implementar revisión editorial si se publican informes públicos |

**Nota sobre el Code of Practice en desarrollo:** La Comisión Europea publicó el primer borrador del Code of Practice on Marking and Labelling of AI-generated Content en enero 2026, con segundo borrador esperado en marzo 2026 y versión final en junio 2026. Este Code of Practice detallará los estándares técnicos específicos de marcado bajo Art. 50(2). CARDEX debe monitorizar su evolución para implementar el estándar correcto.

**Riesgo residual:** 7/10 si no se actúa — deadline agosto 2026 es en 3.5 meses desde la fecha de esta auditoría. La consecuencia de incumplimiento es multa y/o reputacional.

---

## Sección III — DSA Clasificación

### III.1 — Clasificación correcta

El repo afirma que CARDEX es un "motor de búsqueda" bajo Art. 45 DSA (Reg. EU 2022/2065).

**Verificación de definiciones DSA:**

| Categoría DSA | Definición Art. 2 DSA | ¿Aplica a CARDEX? | Veredicto |
|---|---|---|---|
| Servicio intermediario | Servicios de mera transmisión, caché, o alojamiento | CARDEX aloja un índice derivado — no es mera transmisión ni cache puro | PARCIALMENTE |
| Servicio de alojamiento (hosting) | Almacena información a petición del destinatario del servicio | CARDEX no aloja contenido de terceros a su petición — genera su propio índice | **NO APLICA** como categoría primaria |
| Motor de búsqueda en línea | Servicio que permite a los usuarios buscar en "todos los sitios web" o en sitios web de determinado idioma, basándose en consultas | CARDEX permite búsquedas en su índice de vehículos — es un motor de búsqueda **especializado/vertical**, no de "todos los sitios web" | **APLICA con matiz** |
| Plataforma en línea | Servicio de alojamiento que almacena y difunde al público información a petición del destinatario | CARDEX no difunde información a petición de sus usuarios — CARDEX genera y sirve su propia información | **NO APLICA** |
| VLOP/VLOSE | >45M usuarios activos mensuales UE | CARDEX << 45M usuarios | **N/A** |

**Sobre Art. 45 DSA:** La consulta EUR-Lex confirma que Art. 45 DSA (en la versión en vigor) trata de **códigos de conducta para riesgos sistémicos** relacionados con VLOPs/VLOSEs, NO de las obligaciones básicas de los motores de búsqueda. El repo comete un error de referencia de artículo: las obligaciones específicas de **todos** los motores de búsqueda (no solo VLOSE) se encuentran principalmente en:
- **Art. 27 DSA** — Transparencia en sistemas de recomendación y parámetros de ranking
- **Art. 9 DSA** — Punto de contacto para autoridades (aplicable a todos los servicios intermediarios)
- **Art. 11 DSA** — Punto de contacto para usuarios (servicios establecidos o dirigidos a UE)

Art. 45 específicamente trata de códigos de conducta voluntarios para VLOPs/VLOSEs para abordar riesgos sistémicos y publicidad. **Es una disposición de soft-law para grandes plataformas, no la base de las obligaciones básicas de un motor de búsqueda B2B.**

### III.2 — Obligaciones aplicables a CARDEX bajo DSA

Para un motor de búsqueda/plataforma intermediaria de tamaño pequeño (<45M MAU), las obligaciones DSA aplicables son:

| Artículo DSA | Contenido | Acción CARDEX |
|---|---|---|
| Art. 9 | Punto de contacto para autoridades | Email legal@cardex.io (o similar) publicado y operativo |
| Art. 11 | Punto de contacto para usuarios | Formulario de contacto público en la web |
| Art. 12 | Informe anual de transparencia | Aplicable pero muy simplificado para servicios pequeños — publicar número de avisos recibidos |
| Art. 14 | Mecanismo de notificación y acción (Notice & Action) | Canal para que terceros notifiquen contenido ilícito |
| Art. 27 | Transparencia sobre parámetros de ranking | Documentar públicamente qué factores determinan el ranking de resultados (confidence score, precio, etc.) |

**Veredicto sobre clasificación DSA:** La clasificación de CARDEX como "motor de búsqueda" es aproximadamente correcta pero el artículo de referencia (Art. 45) es erróneo. Las obligaciones correctas están en Arts. 9, 11, 12, 14 y 27. El error no cambia el nivel de riesgo (sigue siendo BAJO) pero puede crear confusión si alguien revisa el documento regulatorio.

**Riesgo residual:** 2/10 — bajo, pero corregir el error de referencia de artículo para no crear confusión.

---

## Sección IV — GDPR

### IV.1 — Test de interés legítimo (Art. 6(1)(f)) — tres pasos

El EDPB publicó Guidelines 1/2024 on Art. 6(1)(f) GDPR (8 octubre 2024), estableciendo el marco de tres pasos para el test de interés legítimo. Aplicación a CARDEX:

| Paso | Análisis | Veredicto |
|---|---|---|
| **1. Finalidad legítima** | CARDEX procesa datos de contacto de dealers autónomos (nombre, teléfono, email, dirección) para permitir a compradores B2B identificar y contactar a vendedores de vehículos. El interés comercial de compradores profesionales de encontrar vendedores es un interés legítimo claro y reconocible. Las Guidelines EDPB 1/2024 confirman que intereses comerciales pueden ser legítimos. La finalidad está precisamente articulada (indexación de dealers activos en el mercado B2B de vehículos de segunda mano). | **PASS** |
| **2. Necesidad** | El procesamiento de nombre, teléfono, email y dirección del dealer es necesario para la finalidad: sin esos datos, el comprador no puede contactar al vendedor. No existe una alternativa menos intrusiva que sea igualmente efectiva (p.ej.: solo publicar el nombre de la empresa no permitiría el contacto si el dealer es autónomo). El VIN y datos del vehículo no son datos personales en sí mismos y no presentan issue. | **PASS** |
| **3. Ponderación (balance test)** | Los dealers autónomos publican sus datos de contacto voluntariamente en portales públicos con la intención explícita de ser contactados por compradores. La expectativa razonable del dealer al publicar en mobile.de es precisamente que los compradores encontrarán sus datos. El tratamiento no causa daño grave (no hay datos sensibles, no hay perfilado, no hay uso desviado de la finalidad). Sin embargo, la Guidelines EDPB 1/2024 ponen énfasis en la "conexión con las actividades del responsable" — CARDEX como nuevo agregador puede no ser una fuente que el dealer haya explícitamente contemplado. | **PASS condicional** — el balance se inclina hacia el responsable, pero el dealer debe tener derecho de oposición efectivo |

**Obligaciones derivadas:**
- Privacy notice accesible (responsable del tratamiento, finalidad, base legal, derechos ARCO, plazo de conservación).
- Derecho de oposición operativo: el dealer que se oponga debe ser suprimido del índice en <72h.
- Sin transferencias fuera UE en S0/S1 (Hetzner DE).

### IV.2 — DPIA (Art. 35) — ¿Obligatoria?

El Art. 35 GDPR requiere DPIA cuando el tratamiento "es probable que entrañe un alto riesgo para los derechos y libertades de las personas físicas", especialmente en casos de: evaluación sistemática de personas, tratamiento a gran escala de categorías especiales, monitoreo sistemático de zonas accesibles al público.

**Análisis para CARDEX:**
- CARDEX procesa datos de dealers profesionales (no categorías especiales).
- El volumen de datos es potencialmente grande (miles de dealers en 5+ países), lo que puede calificar como "tratamiento a gran escala".
- El índice de dealers podría considerarse "monitoreo sistemático" de actividad profesional.
- El "G-01 DPIA needed before go-live with PII of sellers" está correctamente identificado como bloqueante en el repo.

**Veredicto:** La DPIA ES obligatoria o al menos altamente recomendable antes de go-live. Las Guidelines EDPB/WP29 lista de tratamientos que requieren DPIA incluye "tratamiento a gran escala de datos personales" — CARDEX al escalar a varios países y miles de dealers entra en este rango.

### IV.3 — Derechos ARCO — Implementation gaps

| Derecho | Requisito GDPR | Status CARDEX | Gap |
|---|---|---|---|
| Acceso (Art. 15) | El dealer puede solicitar qué datos tiene CARDEX sobre él | No documentado | Crear endpoint /api/dealer/gdpr/access |
| Rectificación (Art. 16) | El dealer puede corregir datos incorrectos | No documentado | Endpoint de corrección o canal de contacto claro |
| Supresión (Art. 17) | El dealer puede solicitar borrado | R-A-10 menciona opt-out — pero no hay SLA documentado | Implementar supresión en <30 días con confirmación |
| Oposición (Art. 21) | El dealer puede oponerse al tratamiento basado en LI | No documentado como flujo técnico | Formulario de oposición + proceso de revisión |

**Riesgo residual GDPR:** 5/10 — el análisis de base legal es sólido, pero los flujos técnicos de ejercicio de derechos no están implementados. DPIA pendiente es el bloqueante real. El riesgo sube si se escala a >1000 dealers sin estos mecanismos.

---

## Sección V — EU Data Act — Verificación claim E11

### V.1 — Verificación Art. 4/5 Data Act — ANÁLISIS CRÍTICO

**Claim del repo:** El EU Data Act Art. 4 da al dealer (usuario) el derecho a acceder a los datos que genera al usar una plataforma como mobile.de, y el Art. 5 le permite designar a CARDEX como tercero receptor de esos datos via el Edge Client E11.

**Fecha de aplicación del Data Act:** El Reglamento 2023/2854 fue publicado el 22 diciembre 2023 y **aplica desde el 12 de septiembre de 2025** (Art. 3(1) aplica a productos conectados después del 12 septiembre 2026).

**Análisis de "connected product" en el Data Act:**

| Claim | Texto oficial Art. 4 / Definición | Veredicto | Impacto si incorrecto |
|---|---|---|---|
| El dealer que publica en mobile.de "genera datos" bajo el Data Act | El Data Act define "connected product" como un producto que "obtiene, genera o recopila datos relativos a su uso o entorno, que se comunica mediante un servicio de comunicaciones electrónicas" — **es decir, un dispositivo IoT/hardware** (vehículo conectado, dispositivo doméstico, maquinaria industrial). mobile.de es una PLATAFORMA DE SOFTWARE, no un "connected product" hardware. | **INCORRECTO** para el caso mobile.de | Si el claim es incorrecto, E11 pierde su base legal bajo Data Act |
| El dealer puede designar a CARDEX como tercero vía Art. 5 para recibir datos de mobile.de | Art. 5 permite al usuario del "producto conectado" designar un tercero. El "producto conectado" es el hardware IoT. Los datos generados al interactuar con una plataforma web (mobile.de) NO son "datos generados por un producto conectado" bajo el Data Act. | **INCORRECTO** | Mismo impacto |
| El DMS del dealer (sistema de gestión de inventario) podría ser "connected product" | Si el DMS es un dispositivo/software que se conecta a internet y genera datos de uso (lo cual es plausible para un DMS como software instalado), podría entrar en el scope del Data Act según interpretaciones expansivas. Pero esto es controvertido: el Data Act estaba pensado para IoT hardware, no para software B2B. | **INCIERTO — alta incertidumbre legal** | Riesgo de que la estrategia E11 sea cuestionada |

**Conclusión sobre el claim E11:** El argumento del repo de que el Data Act Art. 4/5 aplica a "datos generados por el dealer al usar mobile.de" es **probablemente incorrecto**. El Data Act fue diseñado para el ecosistema IoT (vehículos conectados, dispositivos inteligentes, maquinaria), no para datos generados al usar plataformas web de terceros. Los recitals del Data Act (Recital 14) confirman que el scope se refiere a "productos conectados a internet que generan datos sobre su desempeño, uso o entorno" — describiendo claramente hardware IoT.

**Riesgo residual:** 7/10 — si la base legal E11 es cuestionada por un regulador o en litigio, E11 perde su fundamento bajo Data Act.

**Mitigación si el claim es incorrecto:**
El repo ya identifica correctamente que la estrategia E11 puede operar bajo consentimiento contractual explícito del dealer, sin necesidad de invocar el Data Act. El Edge Client E11 instalado voluntariamente por el dealer en su DMS, con consentimiento informado, tiene una base legal perfectamente válida bajo GDPR Art. 6(1)(a) (consentimiento) o Art. 6(1)(b) (ejecución de contrato con el dealer). El Data Act no es la única ni siquiera la principal base legal para E11 — el consentimiento contractual es más sólido y más claro.

**Acción requerida:** Redactar el contrato de dealer (Terms of Service) para E11 de manera que el fundamento jurídico sea el consentimiento GDPR + acuerdo contractual, no el Data Act. El Data Act puede mencionarse como contexto normativo favorable, pero no como base legal primaria.

---

## Sección VI — Legislación Nacional — Spot-Check

### VI.1 — FR: Code PI L342-1 vs L341-343

**Análisis:** El repo cita en la tabla de fuentes "Arts. L341-1 a L343-7 CPI" como la sección, y dentro del análisis menciona "Art. L342-1 CPI" como el artículo específico de la prohibición de extracción. La verificación en Légifrance confirma:

- **L341-1 CPI** — Definición del productor de base de datos y condición de protección (inversión sustancial)
- **L342-1 CPI** — Derechos del productor: prohibición de extracción o reutilización de la totalidad o parte sustancial del contenido
- **L342-3 CPI** — Derechos del usuario legítimo: puede extraer partes no sustanciales
- **L342-4 à L342-6** — Excepciones y plazos de protección

**Veredicto:** La cita del repo es **CONFIRMED y CORRECTA** en substancia. L342-1 es el artículo que establece los derechos del productor (equivalente al Art. 7 de la Directiva 96/9/CE). Las citas cruzadas "L341-343" son la sección completa y "L342-1" es el artículo específico — no hay contradicción.

**Cadremploi v. Keljob (CA Paris, 23 mars 2004):** La cita del repo es correcta. Este es el precedente francés canónico sobre indexación de anuncios (empleo). La CA Paris estableció que la indexación sistemática de anuncios constituyó extracción de parte sustancial. CARDEX se diferencia en que indexa metadatos (VIN, precio) y no las descripciones completas — posición defensible.

**Riesgo residual VI.1:** 3/10 — el análisis del repo es correcto.

---

### VI.2 — DE: UrhG § 87b aplicación a CARDEX

**§ 87b(1) UrhG** establece el derecho exclusivo del fabricante de una base de datos a prohibir la "extracción o reutilización repetida y sistemática de partes no sustanciales cuyo resultado sea contrario a la explotación normal de la base de datos".

**Aplicación a CARDEX:** Este párrafo (§ 87b, equivalente al Art. 7(5) Dir. 96/9/CE) es el más relevante para el modelo batch de CARDEX. Si CARDEX realiza crawls periódicos de mobile.de y en cada ciclo extrae "partes no sustanciales" pero el efecto acumulado es el acceso a la totalidad del inventario, § 87b puede ser invocado por mobile.de.

**Veredicto:** **CONFIRMED — el riesgo § 87b es real** y el repo lo documenta correctamente como riesgo MEDIO. La mitigación (rate limiting, metadatos mínimos, no-copy del texto completo) es la respuesta apropiada. Sin embargo, ninguna mitigación técnica elimina completamente el riesgo acumulativo si se indexa el 100% del inventario de un único proveedor.

**Adicionalmente — § 87a UrhG:** Define "fabricante de base de datos" como el que realiza inversión sustancial en su creación. mobile.de y AutoScout24.de son operadores alemanes con inversión sustancial acreditada. Sus bases de datos TIENEN protección sui generis bajo § 87a-87e UrhG. El análisis del repo sobre esto es correcto.

**UWG § 4 Nr. 4 (Schmarotzen):** La doctrina del "parasitismo económico" en competencia desleal aplicaría si CARDEX fuera un competidor directo de mobile.de. CARDEX es B2B puro, mobile.de es B2C + B2B mixto — hay overlap parcial en el segmento B2B. El riesgo UWG no es cero pero es reducido dado el diferente posicionamiento.

**Riesgo residual VI.2:** 4/10.

---

### VI.3 — NL: RDW CC0 — verificación de licencia

**Verificación:** opendata.rdw.nl es el portal oficial del Rijksdienst voor het Wegverkeer (RDW). El dataset "Open Data RDW: Gekentekende_voertuigen" (vehículos matriculados) está publicado bajo licencia de **Dominio Público** ("Public Domain license"), lo que equivale a CC0 en términos prácticos. La verificación directa del portal y de fuentes secundarias (Socrata/Data Overheid) confirma que el dataset es de acceso libre sin restricciones, sin necesidad de API key, descargable libremente.

**Veredicto:** **CONFIRMED** — el claim del repo de que "RDW Open Data está publicado bajo licencia CC0 (dominio público)" es correcto. Nota terminológica: la licencia exacta es "Public Domain" en el portal de RDW, no estrictamente "CC0" como etiqueta formal, pero el efecto jurídico es equivalente — renuncia de derechos de propiedad intelectual y libre uso sin restricciones.

**Implicación para CARDEX:** Los datos del RDW (VIN, matrícula, marca, modelo, año, color, fecha de primera matriculación) pueden ser usados libremente por CARDEX sin restricción de Databankenwet NL. Esto hace de NL el territorio jurídicamente más limpio para el pipeline de VIN-lookup.

**Riesgo residual VI.3:** 1/10 — prácticamente sin riesgo. Solo monitorizar si RDW cambia los términos de licencia en futuras iteraciones del portal.

---

## Sección VII — Estructura Financiera y Regulación

### VII.1 — MiCA (Reg. EU 2023/1114) — Compute Credits

**Claim del repo/SPEC.md:** Los "Compute Credits" (TTL 90 días, no reembolsables, no transferibles entre usuarios, no convertibles a fiat) no constituyen "instrumento de dinero electrónico" ni "token de utilidad" bajo MiCA, por tanto no requieren licencia o autorización bajo MiCA.

**Verificación:**

MiCA Art. 3(1)(9) define **utility token** como: "un tipo de criptoactivo que solo se destina a dar acceso a un bien o servicio prestado por su emisor". Los Compute Credits son exactamente esto: acceso a la capacidad de computación de la API de CARDEX.

La clave legal está en Art. 2(4) MiCA y en los criterios de exclusión. MiCA define "criptoactivos" como "una representación digital de valor o de un derecho que puede transferirse y almacenarse electrónicamente, utilizando la tecnología de registro distribuido o una tecnología similar". La característica de **transferibilidad** mediante "distributed ledger technology or similar technology" es el criterio diferenciador clave.

Los Compute Credits de CARDEX:
- **No usan blockchain/DLT** — son saldos en una base de datos centralizada SQL (tabla `compute_credits` en PostgreSQL según el schema de SPEC.md)
- Son no-transferibles entre usuarios
- Tienen TTL de 90 días (no son reserva de valor persistente)
- No son convertibles a fiat

**Veredicto:** El claim de "evasión MiCA" mediante Compute Credits es **LARGELY CONFIRMED** con matiz importante:

Los Compute Credits tal como están diseñados (sin DLT, no-transferibles, TTL, no-convertibles) probablemente caen fuera del scope de MiCA porque no son "criptoactivos" en el sentido de MiCA (que requiere transferencia mediante DLT). Son más análogos a **créditos prepagos** o "vouchers" de acceso — que históricamente han quedado fuera de la regulación de dinero electrónico bajo PSD2/EMD2 cuando son de uso limitado y no-transferibles.

**Riesgo residual:** La oferta y venta de utility tokens en volumen significativo sí requiere whitepaper y notificación bajo MiCA Title II, aunque en muchos casos para tokens "que ya existen o están operativos" hay excepciones (Art. 4(3)(c) MiCA — exención para utility tokens que ya dan acceso a servicios existentes). Dado que los créditos no son DLT-based, MiCA probablemente no aplica en absoluto.

**Riesgo residual VII.1:** 3/10 — el riesgo es BAJO si se mantiene la arquitectura SQL centralizada sin DLT. Si en el futuro CARDEX emite créditos en blockchain, MiCA aplica completamente y el análisis cambia.
**Acción requerida:** Mantener documentación explícita de que los créditos son saldos centralizados SQL, no criptoactivos. Obtener opinión legal escrita de un abogado fintech antes de lanzamiento a escala.

---

### VII.2 — PSD2 (Dir. 2015/2366) — Zero-Custody

**Claim del repo/SPEC.md:** CARDEX usa Stripe Connect para split payments (comprador → vendedor directo). CARDEX nunca custodia fondos de terceros. Por tanto, CARDEX no requiere licencia de entidad de pago (PSP) o dinero electrónico (EMI) bajo PSD2.

**Verificación:**

Stripe.com guías de PSD2 para plataformas (verificado mediante WebSearch) confirman:
- Stripe Connect permite que los fondos fluyan directamente del comprador a las cuentas conectadas de los vendedores.
- Las plataformas que usan Stripe Connect **no reciben los pagos debidos por compradores a vendedores** — son Stripe (entidad regulada PSP) quien gestiona el flujo.
- El enfoque correcto bajo PSD2 es que la plataforma actúa como **agente comercial** de los vendedores (no intermediario de fondos) — la excepción de agente comercial (Art. 3(b) PSD2) aplica cuando la plataforma actúa en nombre de **solo el pagador o solo el receptor**, no de ambos.

**Matiz crítico de PSD2:** PSD2 Art. 3(b) estrechó el alcance de la excepción de "agente comercial" respecto a PSD1. Bajo PSD2, la excepción solo aplica cuando se actúa en nombre de **únicamente** el pagador o únicamente el receptor, no de ambos simultáneamente. Si CARDEX actúa en nombre tanto del comprador (asistencia en la búsqueda) como del vendedor (indexación de su inventario), la excepción puede no aplicar.

**Sin embargo**, la solución Stripe Connect no depende de la excepción de agente comercial — depende del hecho de que **Stripe** (PSP licenciado) es quien procesa el pago, y CARDEX no "recibe, transmite o retiene fondos" en ningún momento. Esta es la condición definitiva: sin custodia de fondos → sin obligación de licencia PSD2, independientemente de la figura jurídica que use CARDEX en la relación comercial.

**Veredicto:** El claim de "Zero-Custody" es **CONFIRMED** como estrategia válida, siempre que la implementación técnica de Stripe Connect sea correcta y CARDEX realmente nunca acceda ni custodie fondos de terceros. La condición es técnica, no solo contractual.

**Riesgo residual VII.2:** 3/10 — BAJO si la implementación Stripe Connect se hace correctamente. Sube a 7/10 si en algún punto CARDEX toca fondos (p.ej.: recibe y redistribuye comisiones de manera que implica custodia temporal).
**Acción requerida:** Revisar la implementación técnica con un abogado fintech antes del lanzamiento del módulo de transacciones. Documentar el flujo de fondos con diagramas que demuestren zero-custody. Conservar confirmación escrita de Stripe de que el modelo elegido es el que evita obligaciones PSD2.

---

## Sección VIII — Predicción Regulatoria 2026-2028

| Evento regulatorio | Probabilidad | Impacto en CARDEX | Acción preventiva |
|---|---|---|---|
| **AI Act Art. 50 plena aplicación (2 agosto 2026)** | ALTA — certeza legal | ALTO: obligación de marcado AI en NLG outputs + disclosure en UI | Implementar marcado machine-readable en campo NLG antes de agosto 2026; monitorizar Code of Practice final (junio 2026) |
| **Data Act plena aplicación para connected products nuevos (12 sept 2026)** | ALTA — certeza legal | MEDIO: impacto en estrategia E11 si se invoca como base legal; clarifica que mobile.de no es "connected product" | Rediseñar base legal E11 hacia consentimiento contractual puro; no depender del Data Act para justificar E11 |
| **Revisión Directiva de Bases de Datos 96/9/CE** | MEDIA — Comisión Europea tiene en agenda la revisión | ALTO: posible ampliación o restricción del derecho sui generis; revisión puede introducir excepciones de text/data mining más amplias | Monitorizar EUR-Lex + consultas públicas; si se amplían las excepciones TDM, CARDEX se beneficia |
| **Excepción de TDM (text and data mining) Art. 4 Dir. 2019/790** | ALTA — ya está en vigor | MEDIO-POSITIVO: la excepción de TDM para "organisaciones de investigación" no aplica a CARDEX (es comercial), pero la tendencia legislativa es ampliar TDM para uso comercial | Monitorizar si la revisión de la Directiva 96/9 incorpora excepciones TDM más amplias |
| **ePrivacy Regulation (si se aprueba)** | MEDIA — en negociación desde 2017 | BAJO: CARDEX no usa cookies de tracking, no envía comunicaciones. Sin impacto sustancial | Sin acción inmediata; monitorizar |
| **DMA gatekeeper designation automotriz (mobile.de/AutoScout24)** | BAJA — umbrales DMA son altos | ALTO-POSITIVO si ocurre: CARDEX podría invocar Art. 6 DMA para acceso a datos en condiciones razonables | Monitorizar designaciones DMA en sector automotive; preparar argumento de acceso si se designa a Scout24 |
| **Lex specialis automotive data (regulación sectorial)** | MEDIA-BAJA — en discusión en la UE en contexto de vehículos conectados | ALTO: una regulación de datos de vehículos podría crear obligaciones de acceso a datos de fabricantes (OEMs) que beneficien o perjudiquen a CARDEX | Participar en consultas públicas; monitorizar propuestas del European Automotive Data Space |
| **Battery Passport Reg. / ESG vehicle data (Reg. EU 2023/1542)** | ALTA — ya aprobada, aplicación escalonada | MEDIO: el Battery Passport digital requiere datos estructurados de baterías que CARDEX puede indexar; nueva fuente de datos abiertos | Integrar fuentes Battery Passport cuando estén disponibles; oportunidad de datos estandarizados |
| **Cease & desist masivo de portales (R-L-01)** | MEDIA | ALTO: pérdida de fuentes de datos | Ver mitigaciones documentadas en Risk Register; priorizar negociación de acuerdos de data licensing |
| **ESMA guidance sobre tokens prepagos SaaS** | BAJA | ALTO si clarifica que Compute Credits son utility tokens bajo MiCA | Obtener opinión legal fintech antes de lanzamiento a escala; mantener arquitectura SQL no-DLT |

---

## Resumen Ejecutivo

### Claims verificados y correctos: 10
### Claims a corregir: 2
### Claims que necesitan matiz o acción: 5

### Claims a corregir (INCORRECT):

1. **DSA Art. 45** — La referencia al artículo es incorrecta. Art. 45 DSA trata de códigos de conducta para VLOPs/VLOSEs, no de las obligaciones básicas de motores de búsqueda. Las obligaciones de CARDEX como motor de búsqueda están en Arts. 9, 11, 14 y 27 DSA. **Corrección: actualizar 04_REGULATORY_FRAMEWORK.md.**

2. **EU Data Act base legal para E11** — El claim de que el Data Act Art. 4/5 aplica a "datos generados por el dealer al usar mobile.de" es probablemente incorrecto. El Data Act cubre productos conectados IoT/hardware, no plataformas web de terceros. La base legal de E11 debe ser consentimiento contractual (GDPR Art. 6(1)(a)/(b)), no el Data Act. **Corrección: rediseñar Terms of Service de E11; actualizar 04_REGULATORY_FRAMEWORK.md.**

### Claims que necesitan matiz o acción inmediata:

3. **AI Act Art. 50** — La entry R-R-01 es correcta en riesgo e impacto. Falta: implementar marcado machine-readable de outputs NLG antes del 2 agosto 2026. **Acción: sprint técnico para añadir campo `ai_generated: true` y metadatos del modelo en la API; disclaimer en UI.**

4. **Innoweb — riesgo cumulativo § 87b/Art. 7(5)** — El análisis de la distinción batch vs. real-time es correcto, pero no aborda el riesgo de extracción cumulativa. **Acción: implementar límites de cobertura por proveedor y logging de volúmenes.**

5. **VG Bild-Kunst (C-392/19)** — Esta sentencia post-Svensson no está en el repo y añade un riesgo si en el futuro CARDEX implementa previews/iframes. **Acción: prohibir iframes de contenido de terceros en requisitos de producto; actualizar sección jurisprudencia.**

### Top 3 Riesgos Predichos 2026-2028

1. **AI Act Art. 50 incumplimiento** — Probabilidad: ALTA — Impacto: ALTO — Horizonte: 2 agosto 2026 — 3.5 meses desde esta auditoría. Sin implementación de marcado NLG, CARDEX estará en incumplimiento el día del lanzamiento si el MVP llega a agosto 2026.

2. **Cuestionamiento base legal E11 por regulador / litigan con portal** — Probabilidad: MEDIA — Impacto: ALTO — Horizonte: 2026-2027. Si un portal grande (mobile.de, AutoScout24) cuestiona E11 invocando que CARDEX no tiene base legal para extraer su data vía DMS del dealer, y la base Data Act cae, E11 puede ser bloqueado legalmente. Mitigación: rediseñar base legal hacia consentimiento contractual puro ahora.

3. **Litigio sui generis / cease & desist de portal grande** — Probabilidad: MEDIA — Impacto: ALTO — Horizonte: 2026-2027. Innoweb es el precedente directo; aunque CARDEX tiene la distinción batch, el riesgo de una demanda preventiva de un portal (especialmente en DE bajo UrhG § 87b) es real. Mitigación: acuerdos de data licensing proactivos con los 2-3 portales principales.

### Matriz de riesgo residual consolidada

| Sección | Claim principal | Veredicto | Riesgo (1-10) | Acción requerida |
|---|---|---|---|---|
| I.1 — Ryanair C-30/14 | T&C vinculantes aunque no haya sui generis | CONFIRMED | 3 | Mantener robots.txt compliance y proceso revisión T&C |
| I.2 — Svensson C-466/12 | URL pointers a contenido público son legales | CONFIRMED con matiz VG Bild-Kunst | 2 | Prohibir iframes de contenido de terceros |
| I.3 — GS Media C-160/15 | No riesgo si solo se indexa contenido autorizado | CONFIRMED | 2 | Verificar que fuentes indexadas son dominios oficiales |
| I.4 — Infopaq C-5/08 | Riesgo bajo — no se almacena texto protegido | CONFIRMED | 2 | Mantener separación datos fácticos / texto descriptivo |
| I.5 — Innoweb C-202/12 | Distinción batch vs. real-time es válida | CONFIRMED — riesgo cumulativo no discutido | 4 | Implementar límites de cobertura por proveedor |
| II — AI Act Art. 50 | R-R-01 deadline agosto 2026 es correcto | CONFIRMED — falta implementación técnica | 7 | Sprint técnico: marcado NLG antes de agosto 2026 |
| III — DSA | Motor de búsqueda, obligaciones Arts. 9/11/14/27 | INCORRECTO en referencia Art. 45 | 2 | Corregir referencia en documentación |
| IV — GDPR | Art. 6(1)(f) LI para datos de dealers | CONFIRMED — DPIA pendiente | 5 | Completar DPIA (G-01) antes de go-live |
| V — Data Act E11 | Art. 4/5 aplica a datos de mobile.de | PROBABLEMENTE INCORRECTO | 7 | Rediseñar base legal E11 hacia consentimiento contractual |
| VI.1 — FR L342-1 | Cita correcta, riesgo mitigado | CONFIRMED | 3 | Sin acción adicional |
| VI.2 — DE § 87b | Riesgo cumulativo sistemático | CONFIRMED — riesgo real | 4 | Límites de volumen por proveedor |
| VI.3 — NL RDW CC0 | Dominio público confirmado | CONFIRMED | 1 | Monitorizar cambios de licencia |
| VII.1 — MiCA Compute Credits | No aplica MiCA si arquitectura SQL no-DLT | LARGELY CONFIRMED | 3 | Opinión legal fintech escrita antes de escala |
| VII.2 — PSD2 Zero-Custody | Stripe Connect evita obligación PSD2 | CONFIRMED condicionalmente | 3 | Revisión técnica + legal antes de módulo transacciones |

---

## Fuentes primarias consultadas

- EUR-Lex CELEX:62014CJ0030 (Ryanair v PR Aviation)
- EUR-Lex CELEX:62012CJ0466 (Svensson v Retriever Sverige)
- EUR-Lex CELEX:62015CJ0160 (GS Media v Sanoma)
- EUR-Lex CELEX:62008CJ0005 (Infopaq v Danske Dagblades)
- EUR-Lex CELEX:62012CJ0202 (Innoweb v Wegener)
- EUR-Lex CELEX:62019CJ0392 (VG Bild-Kunst v SPK)
- EUR-Lex CELEX:62019CJ0597 (MICM/Mircom v Telenet)
- EUR-Lex CELEX:62017CJ0683 (Cofemel v G-Star Raw)
- EUR-Lex CELEX:32024R1689 (AI Act / Reg. EU 2024/1689)
- artificialintelligenceact.eu/article/50 — análisis Art. 50
- ai-act-service-desk.ec.europa.eu — texto oficial Art. 50
- EUR-Lex CELEX:32022R2065 (DSA)
- EUR-Lex CELEX:32023R2854 (Data Act)
- EUR-Lex CELEX:32023R1114 (MiCA)
- mica.wtf — texto Art. 3 MiCA
- Légifrance — Art. L342-1 Code PI
- opendata.rdw.nl — licencia CC0 / Public Domain
- EDPB Guidelines 1/2024 on Art. 6(1)(f) GDPR (8 octubre 2024)
- Stripe — PSD2 Marketplace Guides
- Plesner.com — Data Act application dates
