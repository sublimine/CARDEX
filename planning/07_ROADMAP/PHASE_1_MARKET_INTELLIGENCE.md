# PHASE_1 — Market Intelligence

## Identificador
- ID: P1, Nombre: Market Intelligence — Inteligencia de mercado y competidores
- Estado: PENDING
- Dependencias de fases previas: ninguna (paralelo con P0)
- Fecha de documentación: 2026-04-14

## Propósito y rationale

Antes de construir la infraestructura de extracción, CARDEX necesita una comprensión cuantitativa del mercado que va a indexar. Sin este conocimiento, el sistema opera sin denominadores: no sabe cuántos dealers existen en total en cada país, no puede calcular su cobertura real, y no puede calibrar si sus criterios de quality pipeline son adecuados para el mercado real.

P1 produce los denominadores y el contexto competitivo que todos los criterios cuantitativos de las fases siguientes necesitan para ser significativos. Es trabajo de documentación e investigación, no de código — puede ejecutarse en paralelo con P0.

## Objetivos concretos

1. Documentar la demografía del mercado de vehículos de ocasión B2B en los 6 países objetivo (DE/FR/ES/BE/NL/CH) con fuentes oficiales
2. Obtener el denominador de dealers por país (número total estimado de dealers profesionales activos)
3. Documentar el panorama competitivo: ≥20 competidores directos e indirectos con análisis de modelo, cobertura y debilidades
4. Benchmarkear las herramientas open-source disponibles por capa funcional del stack
5. Identificar las plataformas de anuncios dominantes por país y sus características técnicas de acceso
6. Documentar la estructura regulatoria (robots.txt, terms of service, litigios relevantes) de los principales targets de extracción

## Entregables

Los 3 archivos del directorio `planning/02_MARKET_INTELLIGENCE/` (ver Task 12):

| Entregable | Archivo | Contenido mínimo |
|---|---|---|
| Censo demográfico | `MARKET_CENSUS.md` | Denominadores por país con fuentes oficiales, segmentación por tipo de dealer, volumen de transacciones B2B |
| Competidores | `COMPETITIVE_LANDSCAPE.md` | ≥20 competidores con modelo de negocio, cobertura geográfica, fortalezas/debilidades |
| Benchmark herramientas | `TOOLING_BENCHMARK.md` | ≥3 herramientas por capa funcional con métricas comparativas cuantitativas |

## Criterios cuantitativos de salida

### CS-1-1: Denominadores por país documentados con fuentes oficiales

```bash
# Verificación manual (no hay query SQL hasta que el sistema esté running)
# El criterio es: MARKET_CENSUS.md contiene para CADA uno de los 6 países:
# - Número de dealers profesionales registrados (fuente oficial nombrada)
# - Volumen de transacciones B2B/año (fuente: ACEA, KBA, ANTS, DGT, RDW, DIV, ASTRA)
# - Segmentación: dealer independiente, dealer OEM autorizado, importador

grep -c "^| DE |" planning/02_MARKET_INTELLIGENCE/MARKET_CENSUS.md   # debe ser ≥1
grep -c "^| FR |" planning/02_MARKET_INTELLIGENCE/MARKET_CENSUS.md   # debe ser ≥1
grep -c "^| ES |" planning/02_MARKET_INTELLIGENCE/MARKET_CENSUS.md   # debe ser ≥1
grep -c "^| BE |" planning/02_MARKET_INTELLIGENCE/MARKET_CENSUS.md   # debe ser ≥1
grep -c "^| NL |" planning/02_MARKET_INTELLIGENCE/MARKET_CENSUS.md   # debe ser ≥1
grep -c "^| CH |" planning/02_MARKET_INTELLIGENCE/MARKET_CENSUS.md   # debe ser ≥1
```

### CS-1-2: ≥20 competidores documentados

```bash
# COMPETITIVE_LANDSCAPE.md debe contener entrada estructurada para ≥20 competidores
grep -c "^## " planning/02_MARKET_INTELLIGENCE/COMPETITIVE_LANDSCAPE.md
# Resultado esperado: ≥20
```

### CS-1-3: ≥3 herramientas benchmarkeadas por capa funcional

```bash
# TOOLING_BENCHMARK.md debe cubrir todas las capas del stack
# Verificación: secciones existentes
grep -c "^## " planning/02_MARKET_INTELLIGENCE/TOOLING_BENCHMARK.md
# Resultado esperado: ≥6 capas con ≥3 herramientas cada una
```

### CS-1-4: Fuentes primarias citadas y accesibles

```bash
# Toda fuente en MARKET_CENSUS.md debe tener URL o referencia bibliográfica verificable
# Verificación manual: revisión de todas las fuentes listadas
# Criterio binario: 0 fuentes sin URL o referencia
grep -c "^\[^source\]" planning/02_MARKET_INTELLIGENCE/MARKET_CENSUS.md  # adaptable
```

### CS-1-5: Denominadores integrados en KG schema

```sql
-- Una vez el sistema esté running: los denominadores de P1 deben estar en la tabla
-- market_denominators del knowledge graph para que los coverage scores sean calculables
SELECT COUNT(*) FROM market_denominator
WHERE country_code IN ('DE','FR','ES','BE','NL','CH')
AND denominator_dealers IS NOT NULL
AND source_url IS NOT NULL;
-- Resultado esperado: 6
```

## Métricas de progreso intra-fase

| Métrica | Descripción | Objetivo |
|---|---|---|
| `countries_with_denominator` | Países con denominador oficial documentado | 6/6 |
| `competitors_documented` | Competidores con ficha completa en COMPETITIVE_LANDSCAPE.md | ≥20 |
| `tool_layers_benchmarked` | Capas funcionales con ≥3 herramientas comparadas | ≥6 |
| `sources_verified` | Fuentes con URL verificable | 100% de fuentes citadas |

## Actividades principales

1. **Fuentes primarias por país** — recopilar datos de:
   - DE: Kraftfahrt-Bundesamt (KBA), ZDK (Zentralverband Deutsches Kraftfahrzeuggewerbe)
   - FR: CCFA, ANTS (Agence Nationale des Titres Sécurisés), CNPA
   - ES: ANFAC, DGT, GANVAM
   - BE: FEBIAC, DIV (Direction pour l'Immatriculation des Véhicules)
   - NL: RDW (Rijksdienst voor het Wegverkeer) — fuente más granular (VIN-level)
   - CH: ASTRA (Bundesamt für Strassen), auto-schweiz
2. **Inventario de plataformas** — por país: cuáles son dominantes, qué robots.txt tienen, qué volumen de listings
3. **Análisis competitivo** — documentar AutoScout24, mobile.de, leboncoin, Autovid, CARFAX EU, BCA, Manheim, CarNext, Autorola, Openlane, BilBanebi, EurotaxGlass's, Eurotax, DAT, DaltonMotor, CarGurus EU, Autohero, Heycar, Cazoo EU y otros con modelo de acceso B2B
4. **Benchmark tooling** — evaluar alternativas a cada componente del stack CARDEX para validar las decisiones de `06_STACK_DECISIONS.md` con datos adicionales
5. **Síntesis en MARKET_CENSUS.md** — tabla por país + interpretación estratégica para discovery

## Dependencias externas

- Acceso web para consulta de fuentes estadísticas oficiales
- No requiere código ni infraestructura
- Puede realizarse completamente antes de que haya un servidor running

## Riesgos específicos de la fase

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Denominadores oficiales no disponibles públicamente para todos los países | MEDIA | MEDIA | Usar denominadores proxy (VAT registrations + NACE codes para sector 45.1x/45.2x) cuando datos directos no estén disponibles |
| Competidor no documentado que resulta relevante en fases posteriores | BAJA | BAJA | Actualización del COMPETITIVE_LANDSCAPE.md es posible post-P1; no es un criterio de cierre exhaustivo |
| Tooling benchmark desactualizado en el momento de implementación | MEDIA | BAJA | El benchmark documenta el estado a fecha; las decisiones de stack ya están tomadas en 06_STACK_DECISIONS.md |

## Retrospectiva esperada

Al cerrar P1, evaluar:
- ¿Los denominadores encontrados son coherentes con las hipótesis iniciales del TAM?
- ¿Hay competidores con cobertura o modelo técnico que obligue a revisar el diseño de CARDEX?
- ¿Alguna herramienta del benchmark supera significativamente las decisiones ya tomadas en 06_STACK_DECISIONS.md?
- ¿Los datos de RDW (NL) confirman que NL es el mejor país piloto para P6?
