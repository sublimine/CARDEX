# Huecos confesados — con plan y fecha

> Nada se esconde. Cada hueco con su plan y su responsable. Verdad cruda > mentira cómoda.

## H1 — Descubrimiento muy por debajo del universo (CRÍTICO, el cuello real)
- **Qué:** 114.620 descubiertos vs universo estimado por el owner (NL sola ~200k).
  De los descubiertos, decenas de miles SIN web resuelta (NL: 26.856 RDW + 6.019
  AS24 sin dominio).
- **Plan:** W1 a escala — (a) correr `domain_resolution.worker` con LLM local sobre
  toda la cola `name sin domain` de los 6 países; (b) ampliar el censo con registros
  mercantiles completos + directorios + OSM exhaustivo + CommonCrawl/CT-logs.
- **Fecha objetivo:** piloto ES en marcha (Task #9); abanico 6 países a continuación.

## H2 — audi_partner: stock por API GraphQL, sin conector
- **Qué:** cientos de dealers Audi DE/EU sobre `one.audi`/PSS. Stock NO en sitemap;
  vive tras `graphql.pss.audi.com` (POST GraphQL, 403 a REST). Clasificado por
  fingerprint pero sin cosecha.
- **Plan:** capturar la query GraphQL real (Playwright XHR intercept sobre la página
  de stock), parametrizar por dealer_id, conector E-DMS. Dossier:
  `recipes/RESEARCH_audi_partner.md`.
- **Fecha objetivo:** tras cerrar el piloto E2E (frente Tier-ish, no bloquea la línea).

## H3 — Recetas de familia sin construir (firma sí, cosecha no)
- **Qué:** `drupal` (16 dealers NL), `autosociaal` (7, SaaS NL), `gerente_tidi`,
  `joomla`, `craftcms` — clasificadas por `cms_fingerprint` pero sin receta de cosecha.
- **Plan:** investigar superficie de stock de cada una (sitemap/API) → receta de
  familia + verificación V2 (≥2 corridas). Cada una multiplica N dealers.
- **Fecha objetivo:** continua, por orden de tamaño de cluster.

## H4 — DE/CH top-ups pendientes (cosecha somera)
- **Qué:** DE sirve solo 42 E2E pese a estar clasificado; los dealers cageados
  inline están topados a 200 punteros (cap inline), no a fondo.
- **Plan:** `run_t2_batch --country DE --tiers T2,T3,T1 --cap 2000` (y CH), serializado.
- **Fecha objetivo:** inmediato tras el esqueleto.

## H5 — Tier-1 plataformas gigantes con WAF (no atacadas con matriz completa)
- **Qué:** mobile.de, AS24 a fondo, coches.net, etc. — defensas duras
  (DataDome/Akamai). Hay arsenal (Camoufox, curl_cffi, E07) pero sin la matriz
  navegador×proxy×cadencia cazada por plataforma.
- **Plan:** W2 Tier-1 — reconocer defensa → matriz → investigación GitHub/foros/Reddit
  registrada en `recipes/RESEARCH_{portal}.md`. Gate de gasto (proxies) = decisión owner.
- **Fecha objetivo:** tras consolidar el long-tail (mayor ROI inmediato en discovery).

## H6 — El stock cageado por sitemap incluye coches VENDIDOS (CRÍTICO, cazado por la Inquisición)
- **Qué:** el sitemap de un dealer lista PDPs de coches vendidos/reservados cuya
  página sigue dando 200. Contar por sitemap **sobrecuenta el stock disponible**.
  Caso probado: dificar.com → sitemap 235, disponible real 123 (total declarado +
  listado paginado coinciden); 4/4 PDPs solo-en-sitemap muestreados = "vendido".
  **Implicación:** los ~66.594 punteros "servidos" hoy (cageados por sitemap)
  incluyen una fracción de vendidos — el inventario DISPONIBLE real es menor.
- **Detección:** ya enforced — `pipeline` V3 exige que sitemap y listado concuerden;
  divergencia → W3 NO PASA. La Inquisición refuta el número (verdict REFUTED).
- **Plan de fix (W3 availability filter):** cosechar desde el LISTADO paginado (set
  vivo) en vez del sitemap cuando divergen; o marcar GONE los PDPs "vendido/
  reservado". Re-cosechar el inventario ya cageado con el filtro → corregir el conteo
  servido a sólo-disponible. Re-derivar `state/COVERAGE.md` tras el barrido de fix.
- **Fecha objetivo:** inmediato — es el siguiente bloque de código (precede a escalar
  el ejército, para no multiplicar inventario inflado).

## Método — fallo reconocido del Director (2026-06-10)
Se trabajó como operario secuencial en vez de desplegar el ejército de agentes, y
se priorizó cosechar lo descubierto sobre AMPLIAR el descubrimiento (el cuello real).
Corrección: esta arquitectura de workflows + discovery masivo como frente principal.
