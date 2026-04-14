# Familia I — Redes de inspección y certificación

## Identificador
- ID: I, Nombre: Redes de inspección y certificación, Categoría: Inspection-network
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Las redes de inspección técnica obligatoria y certificación de vehículos publican directorios de estaciones + talleres partners. Estos directorios capturan el universo de actividad técnica ligada al vehículo, parte del cual es dealer-adjacent (muchos dealers tienen taller + inspección) o dealer-directo (estaciones de inspección que también venden).

Además, algunas redes de certificación (Bosch Car Service, Q-Service) federan workshops con sello de calidad que frecuentemente venden vehículos de ocasión.

## Redes por país

### I.DE — Alemania
- **TÜV** (Süd, Nord, Rheinland, Thüringen, Hessen, etc.) — múltiples entidades federales — https://www.tuev-sued.de, etc.
- **DEKRA** — https://www.dekra.de/stationen — red paneuropea
- **GTÜ** (Gesellschaft für Technische Überwachung) — https://www.gtue.de
- **KÜS** (Kraftfahrzeug-Überwachungsorganisation freiberuflicher Sachverständiger) — https://www.kues.de

### I.FR — Francia
- **UTAC** y su red de **centres de contrôle technique** — https://www.utac.fr
- **Dekra France** — red de CT
- **SGS France** — red CT
- **Bureau Veritas** — red CT

### I.ES — España
- **ITV stations** (Inspección Técnica de Vehículos) — cada CCAA con concesionarias regionales
  - Applus+ IDIADA (multi-CCAA)
  - SGS, Dekra, Bureau Veritas ES
  - GRUPO ITEVELESA, ATISAE, etc.
- Directorios regionales por CCAA (Madrid, Cataluña, Andalucía tienen portales propios)

### I.NL — Países Bajos
- **RDW** mantiene el registro completo de estaciones **APK**
- **APK Inspection Stations** vía RDW Open Data API (cross-Familia A.NL)

### I.BE — Bélgica
- **Contrôle Technique (CT)** — operadas por entidades regionales
  - GOCA (Groupement des entreprises agréées de Contrôle Automobile)
  - AIBV, Autosécurité, SBAT, etc.

### I.CH — Suiza
- **MFK stations** (Motorfahrzeugkontrolle) — cada cantón con su MFK oficial
- 26 entidades cantonales con directorios propios

### I.Multi-país — Redes de certificación
- **Bosch Car Service** — https://www.boschcarservice.com — ~16.000 workshops en EU, directorio público
- **Q-Service** — red multi-brand
- **AutoFit** — red franquicia EU
- **ATU** (Auto-Teile-Unger) — red DE/AT/NL
- **Euromaster** (Michelin) — red EU con servicios vehicle
- **Norauto** — FR/ES/IT/BE con servicios + usados

## Sub-técnicas

### I.M1 — Station directory scraping
Cada red expone estaciones/stations con paginación por región. UA transparente, rate limits conservadores.

### I.M2 — Partner network directories
Las redes de certificación (Bosch Car Service, Q-Service) publican directorio de talleres certificados, muchos dealers-adjacent.

### I.M3 — Cross-reference con A/B
Una estación de inspección no es necesariamente dealer. Flag `is_dealer_candidate` requiere cross-validation con A (NACE 45.11 presente) o B (POI con tag shop=car).

## Base legal
Directorios públicos diseñados para consumidor final. Consentimiento implícito. ODbL para red Bosch.

## Métricas
- `stations_per_network(país)` — cardinalidad
- `dealer_adjacent_rate` — % estaciones que son también dealers (cross-A/B)
- `coverage_uniqueness` — % dealers que SOLO esta familia captura

## Implementación
- Módulo Go: `discovery/family_i/`
- Parser por red
- Persistencia: tabla `inspection_stations` con flag dealer-candidate
- Cron: sync semestral

## Cross-validation

> Hipótesis de diseño — porcentajes de overlap a validar empíricamente en primera ejecución de discovery completo.

| Familia | Overlap hipotético | Único de I |
|---|---|---|
| A | ~40% (estaciones puras no son dealers) | I captura talleres con venta ocasional no en registro dealer formal |
| B | ~60% | I aporta certificación técnica como signal de seriedad |
| G | ~30% | algunos workshops están en ambos |

## Riesgos y mitigaciones
- R-I1: mezcla talleres puros vs dealers. Mitigación: clasificador cross-Familia.
- R-I2: estaciones regionales cambian de operador. Mitigación: re-sync periódico.

## Iteración futura
- Redes de salvamento/siniestros (algunas venden también)
- Redes de reparación carrocería con venta de ocasión
- Inspection networks en countries fronterizos (spillover dealer)
