# Familia F — Aggregator dealer directories públicos

## Identificador
- ID: F, Nombre: Aggregator dealer directories, Categoría: Marketplace-derived
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Cada marketplace B2B/B2C de vehículos expone páginas SEO-optimizadas con el directorio completo de sus concesionarios registrados. Estas páginas están diseñadas para ser indexadas por buscadores, lo que las convierte en fuente legalmente limpia de discovery (hay consentimiento implícito a la indexación por su propósito SEO). Cada dealer-entry aporta: razón social, dirección, teléfono, website propio (crítico), perfil de valoraciones.

## Fuentes por marketplace

### F.1 — mobile.de Händlersuche
- URL: https://www.mobile.de/händler
- Cobertura: DE, AT, NL, BE, FR, ES (multi-país desde Scout24 Group)
- Paginación: por PLZ/código postal + categoría
- Datos extraíbles: Händler-ID, nombre, dirección, teléfono, website, logo, calificación media
- Volumen: ~40.000 dealers DE + ~8.000 AT + menor en otros países

### F.2 — AutoScout24 dealer directory (multi-país)
- URL base: https://www.autoscout24.{de|fr|es|be|nl|ch|at|it|pl}
- Cada TLD expone `/haendler/` o equivalente
- Datos similares a mobile.de (mismo grupo Scout24)
- Volumen: 25-40k dealers por país

### F.3 — La Centrale Pro dealers (FR)
- URL: https://www.lacentrale.fr/concessionnaires
- Argus Group ownership
- Datos: dealer profile + stock summary + website

### F.4 — Coches.net dealer directory (ES, Adevinta)
- URL: https://www.coches.net/concesionarios
- Paginación: por provincia + tipo de dealer (oficial/multi-marca/ocasión)

### F.5 — Autocasion dealer directory (ES)
- URL: https://www.autocasion.com/concesionarios

### F.6 — 2dehands.be dealer profiles (BE, eBay Group)
- URL: https://www.2dehands.be/auto-s-zakelijk/handelaars
- Cobertura BE específica

### F.7 — tweedehands.nl (NL, 2dehands.be sibling)
- URL: https://www.marktplaats.nl/z/auto-s/auto-s.html?categoryId=91&attributes=S%2C10882
- Marktplaats (eBay) ownership

### F.8 — autotrack.nl dealer directory (NL)
- URL: https://www.autotrack.nl/dealers
- Integración con AutoTrack white-label hosted (cross-Familia E)

### F.9 — autoline-eu.com (multi-país)
- URL: https://autoline-eu.{es|de|fr|it|pl}
- Dealer directory B2B paneuropeo, especializado en commercial vehicles

### F.10 — truck1.eu
- URL: https://www.truck1.eu/trucks/sellers
- Commercial vehicles B2B

### F.11 — commercialfleet.com EU dealer directory
- Vehicles comerciales B2B con componente EU

### F.12 — mascus.com B2B
- URL: https://www.mascus.com/dealers/
- Especializado en maquinaria + commercial vehicles

### F.13 — CarOnSale dealer directory (DE, subastas B2B)
- URL: https://caronsale.de/dealers (acceso público limitado)

### F.14 — mobile.ch (CH específico, parte del grupo)
- URL: https://www.mobile.ch/händler

### F.15 — AutoRicerca (IT ecosystem spillover)
- IT no es target pero dealers fronterizos FR/CH pueden aparecer

## Sub-técnicas

### F.M1 — Crawling respetuoso del directorio
Cada aggregator expone un directorio SEO-friendly, paginado. Estrategia:
- Respeto absoluto a `robots.txt`
- Rate limit conservador (1 req / 3s por site)
- UA identificable CardexBot
- Cache agresivo (re-crawl mensual, no más frecuente)
- Parser específico por site para extraer estructura dealer-entry

### F.M2 — Sitemap.xml de directorio
La mayoría exponen `sitemap.xml` con las URLs de perfiles dealer listadas. Acceso directo al índice sin paginación HTML.

### F.M3 — API pública cuando existe
- AutoScout24 Partner API: requiere sign-up pero es gratuita para indexing partners
- mobile.de RSS feeds: algunos segmentos los exponen
- Otros: estrategia HTML como fallback

## Base legal
- Directorios SEO-optimizados: consentimiento implícito a indexación (si no, usarían `noindex`)
- `robots.txt` respetado estrictamente: si `Disallow`, no se crawlea
- Sindicación intencional vía Schema.org markup presente en la mayoría
- Ryanair v. PR Aviation (C-30/14): respeto ToS → verificación manual trimestral de cada ToS para confirmar que no prohibían indexing por terceros

## Métricas

- `dealers_per_aggregator(país)` — discovery rate por fuente
- `unique_discovery_rate(aggregator)` — cuántos dealers solo esta fuente captura
- `website_resolution_rate(aggregator)` — % dealers con website extraído (input crítico para C/D)
- `cross_validation_with_A(país)` — matching con registro mercantil

## Implementación

- Módulo Go: `discovery/family_f/`
- Sub-módulos por aggregator
- Persistencia: SQLite tabla `aggregator_profiles`
- Cron: full-sync mensual por aggregator
- Coste: medio (muchos HTML pages, pero paginación manejable)

## Cross-validation con otras familias

| Familia | Overlap | Único de F |
|---|---|---|
| A | ~30% | F captura dealers sin registro fácilmente localizable |
| B | ~50% | F confirma geo + aporta teléfono/website |
| C | ~70% (indirecto) | F es seed adicional para C vía websites extraídos |
| H | ~40% con oficiales | F captura multi-marca no listados en networks OEM |

## Riesgos y mitigaciones
- R-F1: anti-bot en algunos aggregators. Mitigación: rate limits ultra-conservadores, si persiste → marcar aggregator como "no extraíble", buscar alternativas.
- R-F2: cambio de estructura HTML. Mitigación: tests de regresión + detección de cambios.
- R-F3: ToS prohibitivo en algún aggregator. Mitigación: documentar + excluir esa fuente específica, complementar con familias A/C.

## Iteración futura
- Marketplaces emergentes (nuevos actores que aparezcan)
- Aggregators verticales especializados (camping-car, motorcycle, classic cars)
