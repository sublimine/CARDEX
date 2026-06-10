# Familia audi_partner — frente de API (E-DMS), NO receta de sitemap

> Hallazgo verificado en vivo 2026-06-10 (curl_cffi chrome131). Esto documenta la
> superficie REAL; la receta de cosecha está PENDIENTE de ingeniería de API. No se
> ha fabricado ninguna receta a medias.

## Qué es
Plataforma de sitios-dealer del OEM Audi (`one.audi` / PSS). Cientos de dealers
Audi alemanes y EU sobre una SPA byte-idéntica. Detectada como cluster dominante de
DE-T3 en el barrido (subdominios `*.audi`, páginas de 400KB idénticas).

## Superficie verificada (bhg-buehl.audi, wolkenhauer-westerstede.audi)
- `robots.txt` → `Sitemap: /sitemap.xml` → `sitemapindex` → `/sitemap-de.xml`.
- **El sitemap NO lista stock**: solo páginas de servicio
  (`/de/service-im-autohaus/...`, `/de/geschaeftskunden/`). El cage genérico por
  sitemap rinde 0 vehículos aquí (por eso caen a T3 sin inventario aparente).
- El stock se carga por **API GraphQL de PSS**, keyed por un **dealer id** presente
  en el HTML de la home: `graphql.pss.audi.com/api/v1/dealers/<DEALER_ID>/...`
  (ej. `DEUA26159`). El endpoint `/vcard` responde **200** (datos del dealer).
- Hosts de plataforma comunes: `assets.one.audi`, `env-config.one.audi`,
  `web-api.audi.com`, `audiondemand.audi.de`.

## Lo que falta (el frente de API)
- Los endpoints REST de stock probados (`/stock`, `/vehicles`, `/stockcars`,
  `/used-cars`, `/inventory`, `/vtp`, `?dealer=`) devuelven **403**: el stock NO es
  un GET REST; es una **query GraphQL POST** (capturar la operación exacta que envía
  la SPA: nombre de operación, variables, headers/Origin, posible token efímero).
- Trabajo pendiente: (1) capturar la query real (DevTools/HAR o Playwright XHR
  intercept sobre la página de "Gebrauchtwagen"); (2) parametrizarla por dealer id;
  (3) paginar; (4) mapear el JSON a campos (vin/modelName/price/year/mileage);
  (5) conector E-DMS en el harvester (no el path de sitemap).
- Extracción del dealer id: regex sobre el HTML home
  (`graphql\.pss\.audi\.com/api/v1/dealers/([A-Z0-9]+)/`).

## Estado en el sistema
- `cms_fingerprint` clasifica `audi_partner` (firma: `graphql.pss.audi.com` +
  `assets.one.audi`/`env-config.one.audi`). Esto AGRUPA el cluster ya — la cosecha
  llega cuando el conector de API esté construido.
- Naturaleza taxonómica destinada: `E-DMS` (1 conector cierra N dealers), no
  `E-FAMILY` (que es el multiplicador de sitemap).

## Por qué no se forzó una receta
Doctrina anti-atajo: una receta de sitemap aquí mentiría (el sitemap no tiene
stock) y un conector de API sin la query real capturada sería un stub. El valor
honesto entregado hoy es la CLASIFICACIÓN del cluster + este mapa de superficie
para que el conector se construya sobre hechos, no suposiciones.
