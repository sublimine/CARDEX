# Familia L — Plataformas sociales / business profiles públicos

## Identificador
- ID: L, Nombre: Plataformas sociales, Categoría: Social
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Los dealers mantienen presencia en plataformas sociales con perfiles business públicos que frecuentemente contienen dirección, teléfono, website, horario, fotos del establecimiento y reseñas. Captura dealers que no tienen web propia pero sí perfil social + validación complementaria de los que sí.

## Fuentes

### L.1 — Google Maps Business profiles
- Categoría "Car dealer" (GCID `car_dealer`) + categorías relacionadas (`used_car_dealer`, `truck_dealer`, `motorcycle_dealer`)
- Places API free tier limitado (no usable a escala para €0)
- **Alternativa gratuita**: scraping de SERP Google Maps via HTML — legal si respeta ToS y rate limits
- Datos: nombre, dirección, teléfono, website (critical), horario, fotos, reseñas agregadas
- Volumen estimado: ~50-80k dealers con perfil Google Maps cross 6 países

### L.2 — Facebook Pages
- Categoría "Car Dealership" y relacionadas
- Graph API requiere token (limited free)
- Acceso HTML público limitado (Facebook restringe crawl)
- Útil solo cuando otras familias aportan el link de FB y se usa API para validación/enrichment

### L.3 — Instagram business profiles
- Muchos dealers usan IG como storefront
- Acceso limitado (Meta restricts)
- Útil solo para validación cruzada cuando se tiene el handle

### L.4 — LinkedIn company directory
- Filtros: Industry "Automotive" + Country + Size
- Datos: employees, sede, website, founded year
- Scraping respetuoso del directorio público (respeta ToS)
- Particularmente útil para grupos dealer con estructura corporativa

### L.5 — YouTube dealer channels
- Algunos dealers mantienen canal con videos de inventario
- Búsqueda por keywords + location → descubrimiento
- API YouTube Data v3 free tier suficiente (10.000 units/día)

### L.6 — X (Twitter) business accounts
- Limitado en EU B2B auto, pero algunos dealers premium activos
- Accessible via web scraping básico

### L.7 — TikTok business profiles
- Emergente pero presencia relevante en dealers jóvenes
- Difícil acceso programático

### L.8 — Xing (DE/AT/CH specific)
- LinkedIn equivalente en DACH
- Cobertura dealers DE/CH
- URL: https://www.xing.com

### L.9 — Viadeo (FR específico, aunque declinante)
- Legado profesional FR

## Sub-técnicas

### L.M1 — Geo-grid search en Google Maps
Sistemático: para cada ciudad top-100 por país, query "car dealer near [ciudad]" + paginación + dedup por Place-ID. Respeto a rate limit.

### L.M2 — Cross-platform profile unification
Un mismo dealer puede tener perfiles en Google, Facebook, Instagram, LinkedIn. Matching por website común o por teléfono común → entidad unificada con N perfiles.

### L.M3 — Review signal harvesting
Reseñas agregadas (Google Maps rating, Facebook rating, etc.) aportan señal de credibilidad + actividad real. Dealer con rating fresco = activo.

### L.M4 — Outreach potential identification
Dealers con perfil social pero sin website → candidatos prioritarios para Edge onboarding (Fase 11): ofrecerles terminal CARDEX como vitrina web gratuita.

## Base legal
- Google Maps: acceso público, ToS respetado, no scraping agresivo
- Facebook/Instagram/LinkedIn: acceso muy limitado por ToS — solo consumo del dato cuando la plataforma lo entrega públicamente y sin bypass
- YouTube Data API: free tier legal
- Xing: access dentro del ToS

## Métricas
- `dealers_with_social_presence(país)` — % dealers del knowledge graph con al menos 1 perfil social
- `unique_discovery_via_L` — dealers solo esta familia captura
- `platform_coverage_matrix` — distribución por plataforma

## Implementación
- Módulo Go: `discovery/family_l/`
- Sub-módulos: `google_maps/`, `facebook/`, `linkedin/`, `youtube/`, `xing/`
- Persistencia: tabla `social_profiles` con FK a dealer-ID
- Cron: sync trimestral
- Coste: medio (Google Maps sweep consume tiempo por rate limits)

## Cross-validation

| Familia | Overlap | Único de L |
|---|---|---|
| A | ~70% | L captura dealers sin registro fácilmente localizable |
| B | ~80% (geo coincide) | L aporta teléfono + reseñas + fotos (enriquecimiento) |
| C | ~60% | L aporta website que C pudiera no haber resuelto |
| G | ~40% | L captura no-miembros de asociación con presencia online |

## Riesgos y mitigaciones
- R-L1: Google Maps anti-scraping agresivo. Mitigación: rate limits muy conservadores, si escalada continua abandonar y priorizar Places API free tier.
- R-L2: Facebook/LinkedIn cerrando acceso crecientemente. Mitigación: NO depender de ellos como fuente primaria, solo como enriquecimiento cuando el perfil es público.
- R-L3: perfiles abandonados/inactivos. Mitigación: flag con fecha de último update + cross-validation de actividad real.

## Iteración futura
- Análisis de señales de cierre/transición mediante cambios de perfil social
- Crowdsourced validation: sistema de reportes de usuarios buyers sobre dealers "fantasma"
- Integración con otros ecosistemas regionales (Nextdoor, Glovo business, etc.)
