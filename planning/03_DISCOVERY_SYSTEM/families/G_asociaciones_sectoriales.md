# Familia G — Asociaciones sectoriales

## Identificador
- ID: G, Nombre: Asociaciones sectoriales, Categoría: Trade-association
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
Las asociaciones profesionales publican directorios de miembros, frecuentemente con dirección, website y certificaciones. Aportan validación cualitativa (miembro activo de asociación profesional) y cobertura de dealers establecidos que invierten en afiliación sectorial.

## Asociaciones por país

### G.DE — Alemania
- **ZDK** (Zentralverband Deutsches Kraftfahrzeuggewerbe) — https://www.kfzgewerbe.de — ~38.000 miembros
- **BVfK** (Bundesverband freier Kfz-Händler) — https://www.bvfk.de — independientes/multi-marca
- **VDIK** (Verband der Internationalen Kraftfahrzeughersteller) — import dealers
- **16 Landesverbände regionales** — uno por Bundesland, cada uno con directorio propio (ZDK Baden-Württemberg, Bayern, Berlin-Brandenburg, etc.)

### G.FR — Francia
- **CNPA** (Conseil National des Professions de l'Automobile) — https://www.cnpa.fr — ~5.500 miembros → integrado en **Mobilians**
- **Mobilians** — https://mobilians.fr — umbrella sectorial post-2021
- **FNAA** (Fédération Nationale de l'Artisanat Automobile) — https://www.fna.fr
- **GSCAF** — Groupement Syndical des Concessionnaires Automobiles

### G.ES — España
- **FACONAUTO** (Federación Española de Concesionarios de Automoción) — https://faconauto.com — ~3.200 concesionarios oficiales
- **GANVAM** (Asociación Nacional de Vendedores de Vehículos) — https://ganvam.es — venta vehículos + maquinaria
- **ASETRA** y otras asociaciones regionales por CCAA

### G.NL — Países Bajos
- **BOVAG** (Nederlandse Bond voor de Automobielbranche) — https://www.bovag.nl — ~6.000 miembros
- **RAI Vereniging** (Branchevereniging Rijwiel- en Automobielindustrie) — manufacturers + importers

### G.BE — Bélgica
- **FEBIAC** (Fédération Belge de l'Industrie de l'Automobile et du Cycle) — https://www.febiac.be — importers
- **TRAXIO** — https://www.traxio.be — ~6.500 miembros — sector distribución y reparación
- **FEDA** — retail automoción specific

### G.CH — Suiza
- **AGVS** (Auto Gewerbe Verband Schweiz) / **UPSA** (Union Professionnelle Suisse de l'Automobile) — https://www.agvs-upsa.ch — ~4.000 garages/dealers
- **auto-schweiz** / **auto-suisse** — importers association
- **Swiss Automotive Network**

## Sub-técnicas

### G.M1 — Member directory scraping respetuoso
Cada asociación expone un "member finder" público con paginación por región/categoría. Strategy: acceso transparente con UA CardexBot, rate limits conservadores.

### G.M2 — Newsletter/press releases
Muchas publican newsletters con menciones de nuevos miembros, awards, aperturas → input para detection de cambios (altas/bajas en la base).

### G.M3 — Regional chapter directories
Las asociaciones federales (ZDK, CNPA) tienen capítulos regionales con directorios específicos más detallados que el federal.

## Base legal
Member directories publicados intencionalmente como servicio público de búsqueda. Consentimiento implícito de los miembros al unirse (ToS de la asociación incluye publicación en directorio). Acceso transparente.

## Métricas
- `members_per_association(país)` — cardinalidad real
- `cross_validation_with_A(país)` — % miembros que matchean registro mercantil (debería ser ~100%, confirma consistencia)
- `discovery_quality_score(asociación)` — completitud de datos aportados (dirección, website, teléfono)

## Implementación
- Módulo Go: `discovery/family_g/`
- Parser específico por asociación (estructuras HTML/API distintas)
- Cron: sync trimestral
- Coste: bajo

## Cross-validation

| Familia | Overlap | Único de G |
|---|---|---|
| A | ~100% (miembros siempre registrados) | G aporta certificación + categoría profesional |
| H | ~50% (solapamiento con OEM dealers) | G captura independientes no-OEM |
| F | ~60% (muchos miembros también en aggregators) | G valida calidad + incluye no listados |

## Riesgos y mitigaciones
- R-G1: directorios con JS-rendered. Mitigación: Playwright transparente si necesario, sin stealth.
- R-G2: asociaciones emergentes no listadas. Mitigación: monitoreo press sectorial (Familia O) para detectar nuevas.
- R-G3: miembros históricos dados de baja pero aún en directorio obsoleto. Mitigación: validación cruzada con A (estado activo).

## Iteración futura
- Asociaciones de nicho (classic cars, electric specialty, commercial fleet management)
- Cámaras de comercio bilaterales (DE-FR, FR-ES) con sección automoción
