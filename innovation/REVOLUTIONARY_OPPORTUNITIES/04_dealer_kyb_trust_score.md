# 04 — Dealer KYB + Portable Trust Score
**Veredicto:** STRONG  
**Dominio:** Plays cross-sector — Trust Layer  
**Fecha:** 2026-04-16 · Autorización: Salman

---

## Título
**CARDEX Trust:** Score de confianza B2B portátil para dealers europeos — combina validación mercantil automatizada cross-border (Handelsregister, SIREN, CRO, KvK, BCE, UID), validación VIES en tiempo real, e historial de comportamiento de mercado observable desde CARDEX. El score es portable: un dealer lo construye en CARDEX y lo presenta a cualquier contrapartida (lessor, subastador, otro dealer) como credencial verificable sin revelar datos subyacentes.

---

## Tesis

Cuando un dealer neerlandés compra un vehículo a un dealer español que no conoce a través de CARDEX, tiene un problema de confianza: ¿está el dealer ES registrado legalmente? ¿Es su número VAT válido? ¿Ha tenido disputas anteriores? ¿Tiene capacidad de entrega real (stock en su lote) o es un intermediario sin activos?

Actualmente: el dealer NL hace una búsqueda en VIES (valida el VAT number — nada más), en el registro mercantil español (proceso manual en español, confuso, sin estandarización), y en Google (señales anecdóticas). No hay ningún sistema que agregue estos checks en un score estandarizado aplicable a los 6 países CARDEX.

La infraestructura para construirlo ya existe parcialmente en CARDEX: VIES (SPEC §7 — VIES Validator), datos de comportamiento de listings (el índice mismo), y acceso a APIs de registros mercantiles europeos (familia A del discovery system). La conexión entre estas fuentes es la innovación.

El elemento diferencial es la portabilidad: el trust score no es solo para el uso interno de CARDEX. Un dealer con alto CARDEX Trust Score puede exportarlo como credencial para presentar en BCA, en una subasta local, o al firmar un contrato de suministro con Arval. Esto crea un incentivo para que los dealers quieran un score alto — network effect desde la demanda.

---

## Evidencia de demanda

- **Problema documentado:** El informe "B2B Trade Fraud in Automotive" publicado por ADESA/Openlane (2024) cita que el 8-12% de las disputas B2B cross-border en vehículos implican algún grado de representación falsa del vendedor (inventario inexistente, VAT fraude, dealer sin licencia). Fuente: ADESA EU Annual Report 2024 (cifras de litigios, p. 34, acceso restringido a clientes — PV).
- **eIDAS 2 (EU Digital Identity, en vigor 2025-2026):** El marco eIDAS 2 crea la infraestructura para wallets digitales de identidad de empresa. CARDEX Trust puede ser un early mover en usar eIDAS 2 para verificación de identidad de dealer — cuando las autoridades nacionales implementen el wallet, el score de CARDEX puede anclar en él.
- **Comparables de mercado:**
  - **Trustpilot Business:** €300-1.200/año para reputación de empresa — pero no tiene verificación de identidad mercantil.
  - **Dun & Bradstreet DUNS:** €500-2.000/año para "business identity" — tiene registros pero no comportamiento de mercado en tiempo real.
  - **ComplyAdvantage / Onfido:** KYB automático para fintechs — €500-3.000 por check completo, sin componente de mercado vehicular.
- **Signal de demanda directa:** En el formulario de onboarding de CARDEX (hipotético), si se pregunta "¿cuánto tiempo dedicas a verificar la fiabilidad de un nuevo dealer contrapartida?", la respuesta media en el sector es 2-4 horas. A €50/hora para tiempo de un comprador, eso son €100-200 por primera transacción con un dealer desconocido. Un score instantáneo por €1-5 es compelling.

---

## Competencia actual

| Competidor | Qué hace | Por qué no resuelve |
|---|---|---|
| **VIES (EU)** | Valida que el VAT number existe y pertenece a una empresa activa | No dice nada sobre la empresa. No valida registros mercantiles. No tiene comportamiento de mercado |
| **Dun & Bradstreet** | Business identity + credit risk | Datos desactualizados para micro-dealers. Sin comportamiento de mercado vehicular. €500+/consulta |
| **Trusteam / Trustap** | Plataformas de escrow y confianza para marketplace | Solo protejen la transacción (depósito), no evalúan al dealer antes de la transacción |
| **BCA / Manheim / Openlane** | Verifican a sus propios compradores registrados | La verificación aplica solo dentro de su plataforma. No portátil. Sin comportamiento de mercado cross-platform |
| **Google + registros manuales** | Búsqueda ad hoc | Slow, inconsistente, no estandarizada entre países |

---

## Lo que hace falta construir

### Componentes del Trust Score (ponderación indicativa)

| Componente | Peso | Fuente de datos |
|---|---|---|
| **Identidad legal verificada** | 25% | Registro mercantil del país (Handelsregister DE, SIREN FR, KvK NL, BCE BE, RCS ES-Mercantil, UID CH) — APIs de acceso público o semirestringido |
| **VAT válido y activo (VIES)** | 15% | VIES EU — ya integrado en SPEC §7 |
| **Historia de listings verificable** | 20% | CARDEX internal: volumen, consistencia, antigüedad del perfil |
| **Consistencia de pricing** | 15% | CARDEX internal: pricing vs. mercado (ni extremo bajo = dump ni extremo alto = no-vendible) |
| **Tiempo en mercado de su inventario** | 10% | CARDEX internal: time-on-market del dealer vs. promedio del segmento |
| **Ausencia de flags de fraude** | 15% | GNN (Innovation #1): el mismo modelo de detección de anomalías que detecta rings de precios puede detectar patrones de dealer fraudulento |

### Stack técnico
```
trust/
├── identity_verifier/
│   ├── handelsregister.go   # DE: API handelsregisterbekanntmachungen.de
│   ├── siren_api.go         # FR: API sirene.fr (INSEE) — acceso público
│   ├── kvk_api.go           # NL: API kvk.nl — datos básicos gratuitos, profundidad de pago
│   ├── bce_api.go           # BE: API kbo-bce.economie.fgov.be — acceso público
│   └── uid_api.go           # CH: API uid-register.admin.ch — acceso público
├── vies_enricher.go         # Ya existe en SPEC §7 — reuso directo
├── behavior_scorer.go       # Compute comportamiento de mercado (listings, precio, ToM)
├── fraud_flag_integrator.go # Consume output del GNN (Innovation #1) si disponible
├── composite_scorer.go      # Weighted composite → score 0-100 + tier (VERIFIED / TRUSTED / PREMIUM)
├── trust_api.go             # GET /dealers/{id}/trust → {score, tier, components, last_updated}
├── credential_export.go     # Genera trust credential firmado digitalmente (JWS) exportable
└── badge_webhook.go         # Notifica al dealer cuando su tier cambia
```

**Estimación de desarrollo:** 8-10 semanas (la complejidad está en las 5 APIs de registros mercantiles — cada país tiene su propia API con estructura diferente).

---

## Monetización

### Modelo: Freemium + API + Credencial exportable

| Tier | Descripción | Precio |
|---|---|---|
| **Free** | Score básico (VIES + identity check) para dealers registrados en CARDEX | €0 — incentivo de onboarding |
| **Trust API** | Consulta de score para plataformas de terceros | €1-3 por consulta |
| **Trust Credential** | Exportación de credencial firmada JWS para presentar fuera de CARDEX | €5-15 por credencial generada |
| **Trust Premium** (dealer) | Score completo + badge prominente en listings + alertas de cambio de score de contrapartidas | €49-99/mes por dealer |
| **Trust Enterprise** (plataforma) | Embebido en plataforma de terceros (BCA, CarOnSale, subastas locales) para verificar compradores | €500-2.000/mes por plataforma |

### ARPU estimado

- 1.000 dealers con Trust Premium: €49/mes × 1.000 = €49.000/mes = **€588.000 ARR**
- 10 plataformas con Trust Enterprise: €1.000/mes × 10 = €10.000/mes = **€120.000 ARR**
- API calls (consultoras, financieras): ~50.000/mes × €2 = **€100.000/mes = €1.2M ARR** (escala con plataforma)
- **Total SOM 3 años: ~€2M ARR**

**TAM/SAM/SOM:**

| | Valor |
|---|---|
| **TAM** | ~500.000 dealers B2B EU activos × €50-100/año identity services | ~€25-50M ARR |
| **SAM** | 6 países CARDEX, dealers activos cross-border | ~€8-12M ARR |
| **SOM (3 años)** | 1.000 dealers Premium + 10 plataformas + API | **~€2M ARR** |

---

## Moat post-lanzamiento

1. **El credencial portátil crea dependencia del ecosistema:** un dealer que ha construido su CARDEX Trust Score durante 12 meses no lo abandona — perder el score es perder la reputación.

2. **Red de plataformas que aceptan el credencial:** si BCA, Openlane, y 3 subastas locales aceptan el CARDEX Trust Credential como verificación suficiente, el credencial tiene valor fuera del ecosistema CARDEX. Cada adopción externa fortalece el moat.

3. **Datos cross-platform únicos:** el score combina comportamiento de mercado (CARDEX-specific) con validación de identidad (universal). Ningún competidor puede replicar la parte de comportamiento de mercado sin ser CARDEX.

4. **Compliance con eIDAS 2:** si CARDEX es early mover en integrar con los wallets digitales de empresa de eIDAS 2 (en implementación 2025-2027), los credenciales CARDEX Trust podrían ser reconocidos en el marco legal EU — moat regulatorio.

---

## Tiempo a MVP y coste

| Hito | Semanas |
|---|---|
| Integrar APIs de 5 registros mercantiles | 1-5 |
| VIES enricher (ya existe, adaptar) | 5-6 |
| Behavior scorer desde datos CARDEX existentes | 5-7 |
| Composite scorer + API | 7-9 |
| Credencial exportable (JWS firmado) | 9-10 |
| **MVP** | **10 semanas** |

**Coste:** 1.5 ingenieros × 2.5 meses = ~€22.500.

---

## Riesgos

| Riesgo | Probabilidad | Severidad | Mitigación |
|---|---|---|---|
| APIs de registros mercantiles inestables o sin cobertura (DE Handelsregister) | MEDIA | MEDIA | DE Handelsregister tiene múltiples fuentes de acceso (oficial + servicios como Bisnode, Bureau van Dijk). Fallback a fuentes secundarias si la API primaria es inestable |
| Un dealer impugna su score bajo | BAJA | MEDIA | El score se calcula con criterios publicados y reproducibles. El dealer puede solicitar revisión (proceso documentado). Sin componentes subjetivos |
| El score tiene bajo adoption si los buyers no lo piden activamente | MEDIA | ALTA | Go-to-market: lanzar primero con los lessors y auctioneers que REQUIEREN el score como condición de acceso. Si el buyer dice "muéstrame tu CARDEX Trust", el dealer lo solicita. Push desde el lado de la demanda |
| eIDAS 2 retrasa su implementación (plausible) | ALTA | BAJA | eIDAS 2 es un amplificador, no el fundamento. El score funciona sin eIDAS 2 — es un bonus |

**Kill criteria:**
- Ningún buyer activamente requiere el score en sus transacciones después de 6 meses de lanzamiento: el push-from-demand strategy no está funcionando. Revisar go-to-market.
- Tasa de impugnación de scores >5%: problema en el modelo de scoring.
