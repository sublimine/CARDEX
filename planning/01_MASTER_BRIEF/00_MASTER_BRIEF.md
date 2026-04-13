# CARDEX — Brief institucional

## Identificador
- Documento: 00_MASTER_BRIEF
- Versión: 1.0
- Fecha: 2026-04-14
- Estado: AUTORITATIVO

Este documento es la fuente de verdad del proyecto CARDEX bajo el régimen institucional. Cualquier decisión técnica, comercial o legal posterior debe ser consistente con lo aquí establecido o documentar explícitamente la divergencia.

## Misión

Construir el primer índice europeo unificado y verificable del 100% del inventario B2B de vehículos publicado en internet en seis países (Alemania, Francia, España, Bélgica, Países Bajos, Suiza), bajo un modelo arquitectónico de índice-puntero (sin almacenamiento de fotos ni descripciones), con calidad institucional zero-error y operación 100% legal.

## Modelo arquitectónico — índice-puntero

CARDEX no es un host de contenido. Es un índice. La unidad atómica de su registro contiene:

- VIN canónico como clave de mundo real
- Hash SHA256 de la URL del CDN del proveedor donde reside la imagen original
- URL de la fuente para acceso directo del cliente
- Metadatos derivados (precio, geoposición, timestamps, fingerprint del payload)

Las imágenes, descripciones libres y fichas completas jamás residen en infraestructura CARDEX. Cuando el comprador abre un registro en el terminal, su navegador hace fetch directo al CDN del proveedor original. CARDEX es la guía, no la copia.

Topológicamente, CARDEX es un buscador vertical especializado, no un data broker. Esta distinción tiene consecuencias legales, fiscales y arquitectónicas profundas que vertebran toda la implementación.

## Cobertura objetivo

100% del inventario B2B de vehículos publicado en internet pública en los seis países objetivo, descubierto y mantenido mediante el sistema de discovery por 15 familias documentado en `03_DISCOVERY_SYSTEM/`. Esto incluye explícitamente al concesionario long-tail con 5 vehículos en una web minimal — si está expuesto en internet, está indexable. Solo queda fuera el inventario verdaderamente off-line (stock no digitalizado, off-market estructural OEM), que es físicamente inaccesible para cualquier sistema y se aborda en fases posteriores mediante onboarding voluntario vía Edge dealer client bajo EU Data Act.

## Geografía objetivo

Seis países, tratados con paridad de calidad pero ritmo diferenciado de activación:

| Código | País | Particularidad operativa |
|---|---|---|
| DE | Alemania | Mayor TAM, KBA estadístico no VIN-level, mobile.de dominante |
| FR | Francia | Argus Group ecosystem, INSEE Sirene API completa abierta |
| ES | España | IDEAUTO referencia, BORME open data, AEAT IAE 615.x |
| BE | Bélgica | BCE/KBO open data download completo, mercado transit-export |
| NL | Países Bajos | RDW Open Data API VIN-level, único país con cobertura matemáticamente verificable |
| CH | Suiza | Fuera de UE, nDSG en lugar de GDPR, Edge delegación EU Data Act NO aplica |

## Producto final

Para el comprador B2B, CARDEX presenta cada vehículo como un anuncio completo (foto + título + descripción + precio + especificaciones), pero ese anuncio se construye así:

- **Foto:** puntero al CDN del proveedor original
- **Título:** factual y corto, generado desde VIN-decode + variante (ej. "BMW Serie 3 320d Touring 2020")
- **Descripción:** generada por NLG multilingüe (ES/FR/DE/NL/EN/IT) desde structured facts validados, propiedad intelectual de CARDEX
- **Precio:** indexado como hecho, normalizado a B2B net + EUR
- **Especificaciones:** equipment list normalizada a vocabulario controlado DAT/ABV codes

El resultado: anuncio impecable, sin un solo byte de copyright ajeno almacenado, mejor calidad y consistencia que la fuente original gracias al pipeline de validación V01-V20.

## Restricciones absolutas

### R1 — Legalidad estricta
Cero técnicas de evasión: ningún WAF bypass, ninguna TLS impersonation, ningún UA spoofing, ningún proxy residencial evasivo, ningún anti-fingerprinting. Todo acceso es transparente (UA identificable como CardexBot), respeta robots.txt y rate limits declarados, y opera bajo bases legales explícitas (open data, sitemap como licencia implícita, EU Data Act delegado por dealer, Schema.org como sindicación intencional).

### R2 — Presupuesto €0 OPEX
Single VPS objetivo. Stack 100% open-source, datasets públicos, procesamiento local. Ninguna API de pago. La arquitectura se diseña para una máquina, lo que impone disciplina de eficiencia. Camino de escalado horizontal previsto para cuando el negocio valide.

### R3 — Calidad institucional zero-error
Ningún registro publicado sin pasar las 20 validaciones V01-V20. Lo que no llega a estándar entra en cola de revisión humana, no se publica. Mejor 100k vehículos impecables que 500k con errores.

### R4 — Sin techos mentales
No hay objetivo numérico cerrado en discovery. El proceso es iterativo hasta exhaustividad verificable: tres ciclos consecutivos de las N familias activas sin un solo dealer nuevo descubierto durante T tiempo de búsqueda activa documentado. Cada nuevo vector descubierto se integra como sub-técnica adicional.

### R5 — Multi-redundancia 360°
Ningún registro indexado por una sola fuente. Mínimo tres vectores independientes para confianza alta. Lo que no llega a multi-redundancia entra en cola de revisión, no en índice live.

## Modelo competitivo

CARDEX no compite directamente con marketplaces (mobile.de, AutoScout24, La Centrale) — los indexa. Tampoco compite con los proveedores de datos B2B existentes (Indicata/S&P, JATO, AutoVista, EurotaxGlass, DAT, AAA Data) — los supera en cobertura long-tail y en accesibilidad (terminal en tiempo real para buyer B2B, no dataset corporativo).

Compite estructuralmente con:
1. La fragmentación actual del mercado (un buyer tiene que consultar 15 fuentes para mapear oferta paneuropea)
2. La opacidad del long-tail (~30% del inventario invisible para los aggregators dominantes)
3. La asimetría de información que sostiene los márgenes intermediarios actuales

Su ventaja defensible es el knowledge graph dealer construido por el sistema de discovery 15-familias, que ningún competidor europeo tiene mapeado y cuya replicación requiere años de trabajo legalmente disciplinado.

## Camino al mercado

El plan no fija fechas de lanzamiento. Fija criterios cuantitativos de salida por fase (documentados en `07_ROADMAP/`). Cada fase termina cuando el criterio se cumple, no cuando expira un calendario. Esta disciplina es no negociable bajo el régimen institucional.

Hito mínimo viable de demostración pública: cobertura ≥95% del knowledge graph dealer en al menos un país (recomendación NL por verificabilidad RDW VIN-level), con error rate <0.5% sobre vehículos publicados, freshness SLA cumplido durante 30 días consecutivos, y 10 buyers piloto activos con feedback positivo sostenido.

Hito de cobertura plena: los seis países activos al estándar institucional con métricas cuantitativas auditables contra denominadores oficiales (RDW, KBA, IDEAUTO, BCE, BORME, ASTRA).

## Documentos referenciados

- `01_PRINCIPLES.md` — los cinco principios (R1-R5) desarrollados con implicaciones operacionales
- `02_SUCCESS_CRITERIA.md` — criterios cuantitativos de éxito por fase
- `02_MARKET_INTELLIGENCE/` — censo de mercado, análisis de competidores, benchmarks de tooling
- `03_DISCOVERY_SYSTEM/` — las 15 familias de discovery dealer
- `04_EXTRACTION_PIPELINE/` — estrategias E1-E12 de extracción de catálogo
- `05_QUALITY_PIPELINE/` — validadores V01-V20 zero-error
- `06_ARCHITECTURE/` — arquitectura técnica + spec VPS
- `07_ROADMAP/` — plan de ejecución por fases con criterios cuantitativos
