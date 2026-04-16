# 04 — Marco Regulatorio

## Identificador
- Fecha: 2026-04-14, Estado: DOCUMENTADO
- Alcance: legislación UE + 6 países aplicable a CARDEX (indexación B2B, datos públicos, NLG, privacy)

## Nota metodológica

Este documento recoge el marco legal vigente hasta la fecha de corte de conocimiento del autor (agosto 2025). Las referencias a jurisprudencia TJUE son de resoluciones publicadas y firmes. La legislación nacional derivada de directivas UE puede variar en la transposición específica por país — se indica la norma base y la fecha de transposición conocida. Para actualizaciones posteriores a agosto 2025, consultar CURIA (https://curia.europa.eu) y Eur-Lex (https://eur-lex.europa.eu).

**Principio rector de este documento:** CARDEX opera como un sistema de indexación de datos públicos con punteros a fuentes originales. No almacena copias de contenido protegido. Este modelo de operación (index-pointer) es la base sobre la que se construye la posición legal.

---

## I. Legislación UE Base

### I.1 — Directiva de Bases de Datos 96/9/CE

**Referencia:** Directiva 96/9/CE del Parlamento Europeo y del Consejo, de 11 de marzo de 1996, sobre la protección jurídica de las bases de datos.

**Objeto:** Crea el derecho sui generis del fabricante de una base de datos — protección independiente del copyright para bases de datos cuya obtención, verificación o presentación haya supuesto una inversión sustancial.

**Artículos relevantes:**
- **Art. 1:** Alcance — bases de datos en cualquier forma.
- **Art. 7:** Derecho sui generis del fabricante — prohibición de extracción y/o reutilización de partes sustanciales del contenido.
- **Art. 8:** Derechos del usuario legítimo — el usuario de una base de datos puesta a disposición del público puede extraer partes no sustanciales para cualquier fin.
- **Art. 9:** Excepciones — extracción para uso privado de contenidos no electrónicos, enseñanza e investigación.
- **Art. 15:** Carácter imperativo — cualquier cláusula contractual que restrinja los derechos del usuario legítimo conforme a Art. 8 es nula de pleno derecho.

**Aplicación a CARDEX:**
- CARDEX no extrae partes sustanciales de ninguna base de datos de un competidor.
- CARDEX indexa listados individuales (VIN + URL + metadata pública) — cada listado es una unidad de contenido público, no una extracción sistemática de la base de datos del editor.
- La doctrina Innoweb (ver §III.3) confirma que la indexación de metadatos en sitios de anuncios es "extracción" del derecho sui generis si es sistemática y sustancial. CARDEX mitiga esto mediante rate-limiting, robots.txt compliance, y no almacenamiento de contenido textual completo.

**Riesgo:** MEDIO — La doctrina sui generis está en evolución. Los grandes marketplaces (mobile.de, AutoScout24) tienen bases de datos con inversión sustancial acreditada.

**Mitigación arquitectónica:**
1. CARDEX almacena únicamente VIN (dato fáctico, no protegido), SHA256, URL fuente (puntero), y metadatos mínimos (precio, año, matrícula — datos fácticos).
2. Las descripciones NLG son generadas por CARDEX con modelo local — no son copias de las descripciones del anunciante.
3. El volumen de extracción por sesión está limitado para evitar "parte sustancial" de ningún dataset de un único proveedor.

---

### I.2 — GDPR (Reglamento UE 2016/679)

**Referencia:** Reglamento (UE) 2016/679 del Parlamento Europeo y del Consejo, de 27 de abril de 2016, relativo a la protección de las personas físicas en lo que respecta al tratamiento de datos personales.

**Aplicación a CARDEX:**

CARDEX es un sistema de datos B2B — los sujetos de datos son empresas (dealers), no personas físicas. Sin embargo, los dealers individuales (persona física que ejerce el comercio de vehículos) son personas físicas y sus datos son datos personales bajo GDPR.

**Datos que CARDEX procesa con dimensión GDPR:**
| Dato | Categoría GDPR | Base legal |
|---|---|---|
| Nombre del dealer (persona jurídica) | No es dato personal — es dato de empresa | N/A |
| Nombre del dealer (persona física) | Dato personal — nombre del autónomo | Art. 6(1)(f) interés legítimo |
| Dirección del concesionario | Dato personal si es autónomo | Art. 6(1)(f) interés legítimo |
| Teléfono de contacto del concesionario | Dato personal si es autónomo | Art. 6(1)(f) interés legítimo |
| Email de contacto | Dato personal si es autónomo | Art. 6(1)(f) interés legítimo |
| VIN del vehículo | No es dato personal per se — no identifica al propietario | N/A |

**Posición de CARDEX:**
- Base legal Art. 6(1)(f): interés legítimo — el comprador B2B tiene un interés legítimo en conocer qué dealers tienen determinados vehículos. Este interés no prevalece sobre el interés del dealer individual en proteger sus datos.
- Obligaciones de CARDEX: privacy notice en la API (quién es el responsable del tratamiento, qué datos se procesan, derecho de supresión), derecho de oposición efectivo para dealers individuales.
- **Dato personal sensible:** ninguno — CARDEX no procesa categorías especiales (Art. 9).
- **Transferencias internacionales:** No aplica en S0/S1 — VPS en Hetzner DE (UE). CH tiene nDSG equivalente (ver §II.6).

**Riesgo GDPR:** BAJO — el modelo B2B sobre datos de dealers profesionales tiene precedente como interés legítimo. Ver ICO guidance on legitimate interests for B2B data.

---

### I.3 — Directiva ePrivacy 2002/58/CE (y propuesta de Reglamento)

**Referencia:** Directiva 2002/58/CE relativa al tratamiento de datos personales y a la protección de la intimidad en el sector de las comunicaciones electrónicas.

**Aplicación a CARDEX:**
- CARDEX no usa cookies de terceros, no hace tracking de usuarios individuales, no envía comunicaciones electrónicas no solicitadas.
- El acceso del crawler a sitios web públicos no está regulado por ePrivacy (aplica a comunicaciones, no a acceso a contenidos públicos).
- La propuesta de Reglamento ePrivacy (2017, aún en negociación en agosto 2025) no cambia la posición de CARDEX — CARDEX no tiene actividad de comunicaciones electrónicas.

**Riesgo ePrivacy:** MUY BAJO — no aplica sustancialmente al modelo de negocio de CARDEX.

---

### I.4 — Digital Services Act (DSA) — Reglamento UE 2022/2065

**Referencia:** Reglamento (UE) 2022/2065 del Parlamento Europeo y del Consejo, de 19 de octubre de 2022, relativo a un mercado único de servicios digitales.

**Clasificación de CARDEX bajo DSA:**
- DSA aplica a "servicios intermediarios" — proveedores de servicios de la sociedad de la información que incluyen servicios de mera transmisión, caché, alojamiento, motores de búsqueda en línea y plataformas en línea.
- CARDEX califica como **motor de búsqueda en línea** (Art. 2(g) DSA: servicio que permite a los usuarios buscar en sitios web basándose en consultas, mediante un índice construido previamente), no como plataforma de alojamiento de contenidos de terceros.
- **Corrección de referencia:** Art. 45 DSA regula los códigos de conducta voluntarios para VLOPs/VLOSEs a fin de mitigar riesgos sistémicos — NO es la base de las obligaciones básicas de motores de búsqueda. Las obligaciones aplicables a CARDEX derivan de los artículos siguientes.

**Tier DSA de CARDEX:** Motor de búsqueda en línea de tamaño reducido, B2B, muy por debajo del umbral VLOSE (45 M usuarios activos mensuales en la UE). No aplican las obligaciones adicionales de VLOPs/VLOSEs.

**Obligaciones aplicables a CARDEX (Art. 2(g) + Arts. 9, 11, 14, 27):**

| Artículo DSA | Contenido | Acción CARDEX |
|---|---|---|
| Art. 9 | Órdenes de las autoridades de actuación contra contenidos ilícitos: CARDEX debe tener canal para recibir órdenes de autoridades competentes | Mantener email legal@cardex.io (o equivalente) publicado y operativo en <48h |
| Art. 11 | Punto de contacto único para autoridades de los Estados miembros, la Comisión y el Comité | Publicar punto de contacto oficial en la API y en el website |
| Art. 14 | T&Cs claras y accesibles: qué restricciones se aplican al contenido, cómo se toman decisiones | Publicar Terms of Service con restricciones de uso, política de indexación y canal de opt-out |
| Art. 27 | Transparencia sobre sistemas de recomendación: parámetros principales de ranking y cómo los usuarios pueden modificarlos | Documentar públicamente los factores del ranking (confidence_score, freshness, price) en la API docs |

**Obligaciones que no aplican a CARDEX en fase MVP:**
- Art. 16 (Notice & Action para contenidos ilegales): aplica a hosting providers, no a motores de búsqueda en la misma medida.
- Art. 24-36 (Obligaciones específicas de VLOPs/VLOSEs): CARDEX << 45M MAU.
- Art. 42 (Informes de transparencia anuales para VLOPs): no aplica hasta alcanzar el umbral VLOSE.
- Art. 45 (Códigos de conducta para riesgos sistémicos): solo para VLOPs/VLOSEs designados.

**Riesgo DSA:** BAJO — CARDEX no es plataforma de alojamiento de contenidos de terceros; es un índice B2B especializado con obligaciones básicas limitadas (Arts. 9, 11, 14, 27).

---

### I.5 — Digital Markets Act (DMA) — Reglamento UE 2022/1925

**Referencia:** Reglamento (UE) 2022/1925 sobre mercados contestables y equitativos en el sector digital (Ley de Mercados Digitales).

**Aplicación a CARDEX:**
- DMA aplica a "gatekeepers" — plataformas con más de 45M usuarios activos mensuales en la UE y más de 10.000 usuarios empresariales activos. CARDEX está muy lejos de estos umbrales en fase MVP.
- Sin embargo, DMA **beneficia a CARDEX** indirectamente: obliga a los gatekeepers (Scout24/mobile.de, Adevinta/Coches.net, eBay/2dehands.be) a facilitar la interoperabilidad y el acceso a datos a terceros en condiciones no discriminatorias.
- Si Scout24 es designado gatekeeper, CARDEX podría invocar Art. 6 DMA para acceso a datos de dealers en condiciones razonables.

**Riesgo DMA:** N/A para CARDEX como sujeto obligado. Oportunidad potencial si gatekeepers son designados.

---

### I.6 — Data Act (Reglamento UE 2023/2854)

**Referencia:** Reglamento (UE) 2023/2854 del Parlamento Europeo y del Consejo, de 13 de diciembre de 2023, relativo a normas armonizadas sobre acceso equitativo a los datos y su utilización.

**Scope del Data Act (corrección Wave 2 — 2026-04-14):**

El Data Act (en aplicación desde 12 septiembre 2025) se orienta principalmente a productos conectados IoT/hardware (Recital 14: dispositivos que se conectan a internet y generan datos sobre su desempeño o entorno). El alcance incluye:
- **Vehículos conectados** — los datos telemáticos que el vehículo genera son cobertura directa del Art. 4.
- **Dispositivos IoT** — sensores, maquinaria, electrodomésticos conectados.
- **Sistemas DMS como software instalado** — posible cobertura expansiva, bajo debate jurídico.

**Alcance que NO cubre el Data Act:**
- Datos generados por el dealer al interactuar con una plataforma web de terceros (mobile.de, AutoScout24): los listings publicados en plataformas web no son "datos generados por un producto conectado" en el sentido del Art. 2(5) Data Act.

**Artículo relevante — vehículos conectados (Art. 4/5):**
- **Art. 4:** El fabricante del vehículo conectado debe garantizar que los datos telemáticos generados por el vehículo sean accesibles al usuario (dealer/propietario).
- **Art. 5:** El usuario puede designar a un tercero (potencialmente CARDEX en el futuro) para recibir esos datos de telemetría vehicular.

**Estrategia E11 — base legal correcta:**
E11 (Edge Client) se apoya en consentimiento contractual explícito del dealer (GDPR Art. 6(1)(a)/(b)), no en el Data Act. Ver §IV.5 para el análisis completo de la base legal de E11.

**El Data Act como contexto favorable, no como base legal primaria:**
El Data Act crea un marco normativo que refuerza el principio de portabilidad de datos, lo que apoya política y filosóficamente la existencia de servicios como CARDEX. Sin embargo, su aplicación directa como base legal de E11 para datos de inventario de plataformas web es insegura jurídicamente.

**Aplicación territorial:** Data Act aplica en la UE. CH queda fuera (ver §II.6 — nDSG).

**Riesgo Data Act:** BAJO como riesgo directo — no es la base legal de E11 (que usa GDPR Art. 6(1)(a)/(b)). Oportunidad futura si datos telemáticos vehiculares se integran en el pipeline.

---

## II. Legislación Nacional por País

### II.1 — DE — Alemania

**Ley de Derecho de Autor (UrhG) — Derechos sui generis de bases de datos:**
- **§ 87a-87e UrhG:** Transpone la Directiva 96/9/CE. El fabricante de una base de datos tiene derecho exclusivo a la extracción y reutilización de la totalidad o de una parte sustancial.
- **§ 87b UrhG:** Prohibición de extracción y reutilización repetida y sistemática de partes no sustanciales cuando esto sea contrario a la explotación normal de la base de datos.
- **Relevancia CARDEX:** La indexación de mobile.de o AutoScout24.de en Alemania está sujeta a § 87b si el patrón de acceso es sistemático. CARDEX mitiga con rate limiting, robots.txt compliance, y no-copy del contenido textual completo.

**Ley contra la Competencia Desleal (UWG):**
- La obtención sistemática de datos de un competidor puede constituir acto de competencia desleal bajo § 4 Nr. 4 UWG (explotación del esfuerzo ajeno — "Schmarotzen").
- CARDEX no es competidor directo de mobile.de (CARDEX es B2B, mobile.de es mixto B2C+B2B) — el riesgo UWG es reducido pero presente.

**Fuente:** https://www.gesetze-im-internet.de/urhg/ (UrhG), https://www.gesetze-im-internet.de/uwg_2004/ (UWG)

---

### II.2 — FR — Francia

**Code de la Propriété Intellectuelle (CPI) — Droit sui generis:**
- **Arts. L341-1 a L343-7 CPI:** Transpone la Directiva 96/9/CE. Derecho del productor de bases de datos durante 15 años (renovable si hay inversión sustancial).
- **Art. L342-1 CPI:** Prohibición de extracción o reutilización de la totalidad o de una parte sustancial del contenido de la base de datos.
- **Art. L342-3 CPI:** El usuario legítimo de una base de datos puesta a disposición del público puede extraer o reutilizar partes no sustanciales.

**Particularidad francesa — Tribunal de Commerce:**
- Los grandes casos de web scraping en FR son tratados como litigios mercantiles (tribunal de commerce), no civil. Los precedentes relevantes incluyen el caso **Cadremploi v. Keljob** (CA Paris, 23 mars 2004) — primer caso sui generis sobre indexación de anuncios.
- En ese caso, la CA Paris consideró que Keljob (buscador de ofertas de empleo) realizaba una extracción de partes sustanciales al indexar todos los anuncios de Cadremploi.
- CARDEX se diferencia: no indexa todos los anuncios de ningún proveedor individual — indexa VINs (datos fácticos) y punteros, no las descripciones completas de los anuncios.

**Fuente:** https://www.legifrance.gouv.fr/codes/section_lc/LEGITEXT000006069414/LEGISCTA000006161653/

---

### II.3 — ES — España

**Ley de Propiedad Intelectual (LPI) — Derechos sui generis:**
- **Arts. 133-137 LPI (Texto Refundido RDL 1/1996):** Transpone la Directiva 96/9/CE. Protección del fabricante de bases de datos por 15 años desde la puesta a disposición.
- **Art. 133 LPI:** Define "fabricante de una base de datos" — quien realiza inversiones sustanciales en la obtención, verificación o presentación del contenido.
- **Art. 134 LPI:** Derechos del fabricante — extracción y reutilización de la totalidad o parte sustancial.
- **Art. 135 LPI:** Derechos del usuario legítimo — puede extraer partes no sustanciales.

**Ley de Servicios de la Sociedad de la Información (LSSI-CE):**
- LSSI transpone la Directiva 2000/31/CE (comercio electrónico). CARDEX tiene obligaciones de identificación (razón social, CIF, domicilio, email) en su website y API pública.
- Art. 17 LSSI: limitación de responsabilidad para proveedores de enlaces (análogo al safe harbor) — CARDEX como proveedor de punteros/links tiene protección similar si no tiene conocimiento de actividad ilícita en el contenido enlazado.

**Fuente:** https://www.boe.es/buscar/act.php?id=BOE-A-1996-8930 (LPI), https://www.boe.es/buscar/act.php?id=BOE-A-2002-13758 (LSSI)

---

### II.4 — BE — Bélgica

**Loi sur les bases de données / Databankenwet (Ley de 31 agosto 1998):**
- Transpone la Directiva 96/9/CE en BE. Protección de 15 años para el fabricante de bases de datos.
- La ley belga es notable por su **Art. 7** que permite extracciones para "información, ilustración de enseñanza o investigación científica" — más amplia que la media EU.
- Bilingüismo jurídico FR/NL: la ley existe en ambas versiones con igual fuerza legal.

**Code de Droit Économique (CDE):**
- **Art. IV.95-96 CDE:** Prácticas del mercado — prohibición de actos contrarios a usos comerciales honestos (equivalente al UWG alemán).
- El parasitismo económico (profiter de l'effort d'autrui) es una doctrina BE que podría aplicarse a la extracción masiva de datos de bases de datos competidoras.

**Fuente:** https://www.ejustice.just.fgov.be/cgi_loi/loi_a1.pl?language=fr&la=F&cn=1998083140 (Databankenwet)

---

### II.5 — NL — Países Bajos

**Databankenwet (Wet van 8 juli 1999):**
- Transpone la Directiva 96/9/CE en NL. Derecho sui generis de 15 años.
- **Art. 2 Databankenwet:** El fabricante de una base de datos tiene el derecho exclusivo a autorizar la extracción o reutilización de partes sustanciales del contenido.
- **Art. 5 Databankenwet:** El usuario legítimo puede usar partes no sustanciales sin autorización.
- **Art. 8 Databankenwet:** Prohibición de extracción repetida y sistemática de partes no sustanciales.

**Significancia NL para CARDEX:**
- RDW Open Data (opendata.rdw.nl) está publicado bajo licencia CC0 (dominio público). CARDEX puede usar libremente estos datos sin restricción de la Databankenwet — el titular (Rijksoverheid) ha renunciado a los derechos. Esto hace de NL el país piloto ideal también desde la perspectiva legal.
- KvK (Kamer van Koophandel) API: los datos del registro de empresas son datos públicos bajo el Handelsregisterwet 2007, Art. 22 — acceso libre aunque con rate limits técnicos.

**Fuente:** https://wetten.overheid.nl/BWBR0010591/2021-07-01 (Databankenwet NL), https://www.rdw.nl/over-rdw/organisatie/open-data (RDW Open Data license)

---

### II.6 — CH — Suiza

**nDSG — Nuevo reglamento suizo de protección de datos (en vigor desde 1 septiembre 2023):**
- Suiza no es UE — el GDPR no aplica directamente. El nDSG (Bundesgesetz über den Datenschutz, revisado 2020) es la norma aplicable.
- El nDSG está alineado con GDPR en principios pero tiene diferencias importantes:
  - No hay DPA (Delegado de Protección de Datos) obligatorio para empresas de tamaño medio.
  - El EDÖB (Eidgenössischer Datenschutz- und Öffentlichkeitsbeauftragter — equivalente a la AEPD/CNIL) tiene poderes de supervisión pero no de multa directa hasta 2025.
  - Las transferencias de datos desde CH hacia la UE son legales (CH tiene decisión de adecuación UE).
  - El Privacy Shield no aplica; las transferencias CH→US requieren cláusulas contractuales.

**URG (Urheberrechtsgesetz) — Ley suiza de Propiedad Intelectual:**
- Art. 28-28b URG: Protección de bases de datos en CH (equivalente al derecho sui generis EU pero más restringido — CH no ha adoptado plenamente el derecho sui generis como derecho independiente).
- En la práctica, las bases de datos en CH están protegidas principalmente por el derecho de autor ordinario (si hay originalidad en la selección) más la UWG suiza.

**UWG suiza (Bundesgesetz gegen den unlauteren Wettbewerb):**
- Art. 2 UWG CH: Cláusula general — todo comportamiento engañoso o contrario a la buena fe en la competencia es desleal.
- Art. 5 UWG CH: Explotación del resultado del trabajo ajeno (Leistungsübernahme) — equivalente al parasitismo económico BE/UWG alemán.

**EU Data Act:** No aplica en CH — CH está fuera de la UE. La estrategia E11 en CH requiere una base legal diferente (consentimiento contractual del dealer, no Art. 5 Data Act).

**Fuente:** https://www.fedlex.admin.ch/eli/cc/2022/491/de (nDSG), https://www.fedlex.admin.ch/eli/cc/1993/1798_1798_1798/de (URG), https://www.fedlex.admin.ch/eli/cc/1988/223_223_223/de (UWG CH)

---

## III. Jurisprudencia TJUE Relevante

### III.1 — Ryanair v PR Aviation (C-30/14)

**STJUE de 15 enero 2015.**

**Hechos:** PR Aviation tenía un sitio web de comparación de precios de vuelos. Ryanair prohibía contractualmente en sus Términos y Condiciones el uso automatizado de su sitio. PR Aviation extraía precios de Ryanair para mostrárselos a sus usuarios.

**Cuestión prejudicial:** ¿Puede el fabricante de una base de datos que no cae bajo la protección del derecho de autor ni del derecho sui generis (porque no cumple los umbrales de inversión sustancial) prohibir contractualmente el acceso automatizado?

**Ratio decidendi:** El TJUE respondió que **sí** — la Directiva 96/9/CE sólo regula la protección de bases de datos que cumplen los requisitos de protección (originalidad para copyright, inversión sustancial para sui generis). Si la base de datos no está protegida, el Derecho de la Unión no se opone a que el fabricante establezca restricciones contractuales de acceso. Es decir, los términos y condiciones contractuales pueden prohibir el scraping aunque no haya derecho sui generis.

**Aplicación a CARDEX:**
- CARDEX debe leer y respetar los Términos y Condiciones de cada fuente.
- Si un marketplace prohíbe el acceso automatizado en sus T&C, CARDEX no puede invocar la ausencia de derecho sui generis como defensa.
- **Mitigación:** robots.txt compliance, CardexBot/1.0 UA identificable, sistema de opt-out para dealers que no deseen indexación, contacto legal disponible para fuentes que quieran ser eliminadas del índice.

---

### III.2 — Svensson v Retriever Sverige (C-466/12)

**STJUE de 13 febrero 2014.**

**Hechos:** Svensson (periodista) publicó artículos en un sitio de acceso libre. Retriever Sweden (aggregador) creó hipervínculos a esos artículos. Los periodistas alegaron infracción de derecho de autor por comunicación pública.

**Ratio decidendi:** El TJUE estableció que:
1. Un hipervínculo a una obra ya publicada en internet con autorización del autor **no constituye comunicación pública** si se dirige al mismo público (usuarios de internet que ya podían acceder a la obra).
2. Si el enlace supera restricciones técnicas (paywall, login) — sí puede constituir comunicación al público.

**Doctrina de la "comunicación a un público nuevo":** No hay comunicación pública si la obra ya estaba disponible libremente al mismo público.

**Aplicación a CARDEX:**
- CARDEX almacena URLs (punteros) a listados de vehículos públicos. Esta práctica está protegida por la doctrina Svensson: los punteros a obras ya públicas no son comunicación pública.
- Los compradores B2B que acceden a la URL original a través de CARDEX están en el mismo público que ya podía acceder al listado directamente.
- **Límite:** si CARDEX indexara contenido detrás de un paywall o área de acceso restringido, la doctrina Svensson no aplicaría.

**Jurisprudencia posterior — VG Bild-Kunst v Stiftung Preußischer Kulturbesitz (C-392/19, 9 marzo 2021):**
El TJUE matizó Svensson: el *framing* (incrustación via iframe) de una obra que el titular ha protegido con medidas tecnológicas anti-framing SÍ constituye comunicación al público. Cuando el titular adopta medidas técnicas para impedir el framing, el consentimiento al acceso libre no se extiende automáticamente a terceros que incrusten la obra vía iframe.

**Impacto CARDEX:** CARDEX solo almacena URLs como punteros textuales — no usa iframes ni embeds de contenido de terceros. Riesgo nulo para el modelo actual. **Restricción permanente de producto:** cualquier futura funcionalidad de "preview" o "visor" de listados originales vía iframe está prohibida.

---

### III.3 — Innoweb v Wegener (C-202/12)

**STJUE de 19 diciembre 2013.**

**Hechos:** Innoweb operaba un metabuscador de vehículos de segunda mano (DrivenUp). Wegener operaba AutoWeek.nl, un sitio de anuncios de vehículos. DrivenUp extraía en tiempo real de AutoWeek.nl mediante consultas a su base de datos.

**Ratio decidendi:** El TJUE resolvió que el metabuscador infringía el derecho sui generis de Wegener porque:
1. Permitía al usuario de DrivenUp "buscar simultáneamente en la totalidad o en una parte sustancial" de la base de datos protegida de Wegener.
2. El metabuscador que retransmite consultas a la base de datos original es equivalente a la "puesta a disposición de un instrumento para la consulta" de la base de datos — constituyendo reutilización.
3. La extracción es "en tiempo real" — el usuario accede a los datos actualizados de la base de datos original, no a una copia almacenada.

**Distinción crítica con CARDEX:**
- DrivenUp retransmitía las consultas del usuario a AutoWeek.nl en tiempo real, actuando como un proxy de la base de datos.
- CARDEX **no retransmite consultas** a las fuentes originales en tiempo real. CARDEX indexa los datos previamente (crawler batch) y almacena únicamente el puntero. El usuario de CARDEX hace una consulta a la base de datos **de CARDEX**, no a la del marketplace original.
- Esto es una diferencia arquitectónica fundamental. CARDEX es más parecido a Google (que indexa previamente) que a Innoweb/DrivenUp (que retransmite en tiempo real).

**Aplicación a CARDEX:**
- La arquitectura index-pointer (no proxy en tiempo real) está específicamente diseñada para diferenciarse de Innoweb y situarse en la zona de menor riesgo.
- **Riesgo residual:** si el volumen total de datos indexados de un proveedor individual (p.ej. mobile.de) representa una "parte sustancial" de su base de datos, podría argumentarse que el proceso de indexación batch periódico es equivalente. CARDEX mitiga esto con rate limiting y almacenando solo metadatos mínimos (no el contenido textual completo del anuncio).

---

### III.4 — GS Media v Sanoma (C-160/15)

**STJUE de 8 septiembre 2016.**

**Hechos:** GS Media publicó hipervínculos a fotografías de Playboy filtradas ilegalmente, sin autorización del titular de derechos. Sanoma (Playboy EU) demandó por comunicación pública.

**Ratio decidendi:** El TJUE amplió la doctrina Svensson:
1. Si el hipervínculo lleva a una obra publicada **sin autorización del titular**, el enlace es comunicación pública si el que pone el enlace sabe o debería saber la ilicitud de la publicación original.
2. Se presume que quien pone el enlace con **ánimo de lucro** conoce la ilicitud — presunción iuris tantum.

**Aplicación a CARDEX:**
- CARDEX indexa únicamente listados públicos de dealers que los publican voluntariamente en plataformas públicas. La publicación original está autorizada por el propio dealer.
- No hay riesgo GS Media mientras CARDEX no indexe contenido publicado sin autorización del titular de derechos.
- La presunción de "ánimo de lucro" del TJUE es relevante: CARDEX tiene ánimo de lucro potencial (modelo de negocio B2B). Esto refuerza la necesidad de procedimientos de verificación de legalidad de cada fuente indexada.

---

### III.5 — Infopaq International v Danske Dagblades Forening (C-5/08)

**STJUE de 16 julio 2009.**

**Hechos:** Infopaq capturaba artículos de prensa y los almacenaba temporalmente en RAM para generar extractos de 11 palabras alrededor de un término de búsqueda. La prensa danesa alegó infracción de copyright.

**Ratio decidendi:**
1. Un fragmento de 11 palabras puede ser suficientemente original para estar protegido por el derecho de autor si expresa la "creación intelectual propia" del autor.
2. El acto de almacenamiento temporal en RAM puede constituir una reproducción sujeta al derecho exclusivo del autor.
3. Sin embargo, la excepción de reproducción transitoria del Art. 5(1) de la Directiva 2001/29/CE puede aplicar si el almacenamiento es transitorio, integral al proceso técnico, y no tiene significación económica independiente.

**Aplicación a CARDEX:**
- CARDEX no almacena fragmentos de texto de los anuncios — almacena únicamente datos fácticos (VIN, precio, año, km, color — datos no protegidos por copyright) y el URL como puntero.
- El procesamiento de texto del anuncio por el extractor (para extraer datos estructurados) implica una carga temporal en RAM del contenido — aplica la excepción Art. 5(1) si el proceso es transitorio y no tiene significación económica independiente.
- La generación NLG de CARDEX produce **texto propio** (no es copia del anuncio original) — este es el contenido que CARDEX almacena y sirve como IP propia.
- **Riesgo Infopaq:** BAJO — la arquitectura evita específicamente el almacenamiento de texto extraído del anuncio original.

---

## IV. Doctrinas Aplicables al Modelo de CARDEX

### IV.1 — Doctrina del Hipervínculo (Svensson/GS Media)

**Regla aplicable a CARDEX:**
- Los punteros URL a listados públicos de dealers son legales en virtud de la doctrina del hipervínculo, siempre que:
  1. La publicación original estuviera autorizada por el dealer.
  2. El listado sea de acceso público (sin paywall ni login requerido).
  3. CARDEX no tenga conocimiento de que la publicación original es ilícita.

**Implementación:** V02_source_url_validation verifica que cada URL indexada es de acceso público antes de la indexación permanente.

---

### IV.2 — Doctrina de la Licencia Implícita por robots.txt

**Regla:**
- Un sitio web que no prohíbe el acceso de robots en su robots.txt otorga implícitamente licencia para el acceso automatizado. Esta es una doctrina ampliamente aceptada en la práctica, aunque no consolidada jurisprudencialmente en el TJUE.
- Si robots.txt **prohíbe** el acceso de un agente (o de todos los agentes), no existe licencia implícita.
- Si robots.txt **permite** el acceso pero los T&C prohíben el scraping, prevalecen los T&C contractuales (doctrina Ryanair, C-30/14).

**Implementación CARDEX:**
- El Discovery Service lee robots.txt de cada dominio antes de cada ciclo de crawl.
- `cardex_discovery_robots_blocked_total{domain}` — métrica Prometheus para dominios bloqueados.
- Dominio en robots.txt bloqueado → familia de descubrimiento A-O no accede a ese dominio.

---

### IV.3 — Doctrina del Schema.org Structured Data como Invitación a la Indexación

**Regla:**
- Cuando un webmaster añade marcado Schema.org (schema.org/Car, schema.org/AutoDealer) a sus páginas, está implícitamente invitando a los motores de búsqueda y agregadores a interpretar y procesar esos datos estructurados.
- Esta doctrina no está consolidada jurisprudencialmente pero es ampliamente aceptada en la práctica (Google, Bing, DuckDuckGo la invocan implícitamente).

**Implementación CARDEX:**
- Familia A (Schema.org Parser) prioriza páginas con marcado Schema.org/AutoDealer.
- La presencia de Schema.org es un factor positivo en el confidence score del dealer (V09_schema_org_validation da +0.15 de score).
- Si un dealer ha marcado explícitamente sus páginas con Schema.org, la invitación a la indexación es más clara.

---

### IV.4 — Datos Fácticos No Protegidos (Feist v Rural Telephone)

**Regla:**
- En el Derecho europeo (a diferencia del US Feist v Rural Telephone), los datos fácticos (hechos, datos de registro, números) no están protegidos por el derecho de autor ordinario porque carecen de originalidad.
- Sin embargo, una **base de datos** de datos fácticos puede estar protegida por el derecho sui generis si ha requerido inversión sustancial.
- Los datos fácticos individuales (VIN, año, km, precio de lista, dirección, CIF/VAT) no están protegidos ni por copyright ni por el derecho sui generis en sí mismos — es la **colección** la que puede estar protegida.

**Aplicación a CARDEX:**
- CARDEX extrae datos fácticos individuales (VIN, precio, km, año, color, combustible) de listados públicos.
- No extrae la "colección completa" de ningún proveedor — indexa unidades individuales (un listado = un vehículo) en el contexto del descubrimiento de dealers.
- El VIN es un identificador técnico del vehículo (asignado por el fabricante del vehículo, no por el marketplace) — no está protegido por ningún derecho.

---

### IV.5 — Base Legal E11 — Consentimiento Contractual (GDPR Art. 6(1)(a) y (b))

**Corrección de base legal (Wave 2 Fix — 2026-04-14):**

El EU Data Act (Reg. 2023/2854) fue diseñado para productos conectados IoT/hardware (Art. 2(5): "producto conectado" = producto que obtiene, genera o recopila datos y se comunica mediante red de comunicaciones electrónicas — Recital 14 confirma: IoT devices, maquinaria, vehículos conectados). El Data Act **no aplica** a datos generados por el dealer al interactuar con plataformas web de terceros (mobile.de, AutoScout24). Por tanto, los Arts. 4 y 5 del Data Act no constituyen base legal para que E11 justifique la transmisión del inventario del dealer desde su DMS hacia CARDEX en el contexto de plataformas web.

**Base legal correcta de E11 — doble ancla GDPR:**

| Base legal | Artículo | Condición | Cobertura territorial |
|---|---|---|---|
| **Consentimiento explícito** | GDPR Art. 6(1)(a) | El dealer acepta los Terms of Service de CARDEX y el Data Sharing Agreement (DSA) antes de instalar el Edge Client | UE (DE/FR/ES/BE/NL) + CH (nDSG Art. 6(6)) |
| **Ejecución contractual** | GDPR Art. 6(1)(b) | La transmisión de inventario es necesaria para ejecutar el contrato de servicio entre CARDEX y el dealer (sin datos de inventario, el servicio de indexación contratado no se puede prestar) | UE + CH |

**Flujo de consent capture (obligatorio pre-instalación E11):**

1. **Presentación del DSA:** Antes de la instalación del Edge Client, se muestra al dealer el Data Sharing Agreement completo en el idioma del dealer (DE/FR/ES/NL).
2. **Checkbox de consentimiento explícito:** El dealer marca activamente: *"Acepto compartir mi inventario de vehículos con CARDEX según los términos del DSA."*
3. **Timestamping + IP logging:** El sistema registra timestamp ISO-8601 + IP del dealer + versión del DSA aceptada en la tabla `dealer_consent_log`.
4. **Especificación del scope:** El DSA enumera exactamente qué campos se comparten (inventario de vehículos: VIN, precio, km, año, fotos — **sin** datos de clientes, sin datos financieros del dealer).
5. **Derecho de revocación:** El Edge Client incluye botón "Pausar indexación" y "Dar de baja de CARDEX" — ambos con efecto inmediato (TTL de vehículos expirados en ≤24h post-revocación).
6. **Evidencia durable:** La `dealer_consent_log` se archiva durante el período de relación comercial + 3 años (Art. 17 GDPR plazo de supresión diferida).

**Implementación E11:**
- El Edge Client (Tauri/Rust) se instala en el entorno del dealer tras completar el flujo de consent capture descrito arriba.
- El Edge Client exporta datos del DMS (inventario, especificaciones) directamente a CARDEX API de ingesta via HTTPS firmado con la clave privada del dealer.
- El dealer mantiene control total: puede revocar en cualquier momento (UI de revocación en el Edge Client + endpoint API `/api/v1/dealer/{id}/revoke`).

**Referencia al Data Act como contexto favorble (sin ser base legal primaria):**
El Data Act (desde septiembre 2025) crea un marco normativo favorable que reconoce la portabilidad de datos de usuarios como principio de política pública de la UE. Esto apoya el argumento de que el dealer tiene interés legítimo en compartir sus propios datos de inventario, pero **no** es la base legal directa de E11 — el consentimiento GDPR y el contrato son suficientes y más sólidos.

**Cobertura territorial de E11:**
- **UE (DE/FR/ES/BE/NL):** GDPR Art. 6(1)(a)/(b). El Data Act puede citarse como contexto, no como base.
- **CH (Suiza):** nDSG Art. 6(6) — consentimiento válido bajo nDSG, estructura análoga a GDPR. **Sin invocación del Data Act** (CH fuera de la UE).

---

## V. Restricciones Absolutas

Las siguientes prácticas están **absolutamente prohibidas** en CARDEX independientemente de contexto o posible ventaja competitiva:

| # | Práctica Prohibida | Base Legal / Razón |
|---|---|---|
| R-A-1 | Acceso a contenido detrás de paywall o login sin autorización | Doctrina Svensson — no es contenido público |
| R-A-2 | Bypass de mecanismos anti-bot (curl_cffi, playwright-stealth, JA3/JA4) | Viola robots.txt implícito, T&C, potencialmente CFAA-equivalente UE |
| R-A-3 | Extracción sistemática de la **totalidad** del inventario de un proveedor sin licencia | Directiva 96/9/CE Art. 7 — parte sustancial |
| R-A-4 | Almacenamiento de descripciones textuales completas de anuncios de terceros | Copyright del redactor del anuncio — Infopaq |
| R-A-5 | Uso de proxies residenciales o rotación de IPs para eludir bloqueos | Práctica de evasión — viola T&C, incompatible con CardexBot UA |
| R-A-6 | Envío de comunicaciones comerciales no solicitadas a contactos extraídos | ePrivacy + anti-spam nacionales |
| R-A-7 | Almacenamiento de datos de propietarios individuales de vehículos (personas físicas) | GDPR Art. 9 categorías especiales; no alineado con finalidad B2B |
| R-A-8 | Acceso a MOFIS (CH) sin acuerdo formal con ASTRA | MOFIS no es open data — acceso no autorizado |
| R-A-9 | Retransmisión en tiempo real de consultas a bases de datos de terceros | Doctrina Innoweb C-202/12 |
| R-A-10 | Uso de datos del RDW para perfilado individual de propietarios de vehículos | RDW CC0 limita uso a datos de vehículo, no de personas |

---

## VI. Tabla Resumen por País

| País | Norma sui generis DB | Equivalente UWG | GDPR / Equiv. | Open Data VIN | E11 base legal |
|---|---|---|---|---|---|
| DE | § 87a-87e UrhG | UWG § 4 Nr. 4 | GDPR (DSGVO) | No | GDPR Art. 6(1)(a)/(b) |
| FR | Arts. L341-L343 CPI | Code Commerce | GDPR | No | GDPR Art. 6(1)(a)/(b) |
| ES | Arts. 133-137 LPI | LCD | GDPR (LOPD-GDD) | No | GDPR Art. 6(1)(a)/(b) |
| BE | Databankenwet 1998 / Loi DB | CDE Art. IV.95 | GDPR | No | GDPR Art. 6(1)(a)/(b) |
| NL | Databankenwet 1999 | Oneerlijke Handel | GDPR | **Sí (RDW CC0)** | GDPR Art. 6(1)(a)/(b) |
| CH | URG + UWG CH | UWG CH Art. 2/5 | nDSG (no GDPR) | No | **nDSG Art. 6(6) consentimiento** |

*Nota: La columna "E11 base legal" refleja la corrección Wave 2 (2026-04-14). La base legal de E11 es el consentimiento contractual GDPR/nDSG, no el Data Act (Reg. 2023/2854), cuyo scope se limita a productos conectados IoT/hardware y no cubre datos de plataformas web de terceros.*

---

## VII. Fuentes Normativas Primarias

| Norma | Referencia | URL |
|---|---|---|
| Directiva 96/9/CE | OJ L 77, 27.3.1996, p. 20 | https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX:31996L0009 |
| GDPR | OJ L 119, 4.5.2016, p. 1 | https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX:32016R0679 |
| Directiva ePrivacy | OJ L 201, 31.7.2002, p. 37 | https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX:32002L0058 |
| DSA | OJ L 277, 27.10.2022, p. 1 | https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX:32022R2065 |
| Data Act | OJ L, 22.12.2023 | https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX:32023R2854 |
| UrhG DE § 87a-87e | BJNR012730965 | https://www.gesetze-im-internet.de/urhg/ |
| CPI FR L341-343 | | https://www.legifrance.gouv.fr/codes/section_lc/LEGITEXT000006069414/LEGISCTA000006161653/ |
| LPI ES Arts. 133-137 | RDL 1/1996 | https://www.boe.es/buscar/act.php?id=BOE-A-1996-8930 |
| Databankenwet BE | 31.8.1998 | https://www.ejustice.just.fgov.be/cgi_loi/loi_a1.pl?language=fr&la=F&cn=1998083140 |
| Databankenwet NL | 8.7.1999 | https://wetten.overheid.nl/BWBR0010591/2021-07-01 |
| nDSG CH | SR 235.1 | https://www.fedlex.admin.ch/eli/cc/2022/491/de |
| STJUE C-30/14 | Ryanair v PR Aviation | https://curia.europa.eu/juris/document/document.jsf?docid=162441 |
| STJUE C-466/12 | Svensson | https://curia.europa.eu/juris/document/document.jsf?docid=147847 |
| STJUE C-202/12 | Innoweb v Wegener | https://curia.europa.eu/juris/document/document.jsf?docid=145544 |
| STJUE C-160/15 | GS Media v Sanoma | https://curia.europa.eu/juris/document/document.jsf?docid=183124 |
| STJUE C-5/08 | Infopaq | https://curia.europa.eu/juris/document/document.jsf?docid=72482 |
