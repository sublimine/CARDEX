# Familia O — Press digital, archivos históricos y prensa sectorial

## Identificador
- ID: O, Nombre: Prensa e históricos, Categoría: Press-historical
- Fecha: 2026-04-14, Estado: DOCUMENTADO

## Propósito y rationale
La prensa sectorial automotriz y los archivos de prensa publican noticias sobre aperturas de dealers, fusiones, cambios de marca, aniversarios, premios, declaraciones de cese. Procesar esta fuente textual aporta (1) discovery de dealers no capturados por otras familias, (2) validación temporal de actividad, (3) detección temprana de eventos críticos (cierres, quiebras).

## Fuentes

### O.1 — Prensa sectorial automotriz por país

#### O.1.1 — Alemania
- **Autohaus.de** — https://www.autohaus.de (publicación industria #1 DE)
- **Automobilwoche** — https://www.automobilwoche.de
- **kfz-betrieb** — https://www.kfz-betrieb.vogel.de
- **AUTO BILD Professional** — https://www.autobild.de/professional
- **Handelsblatt Auto** — sección auto del Handelsblatt
- **Automobil-Produktion** — https://www.automobil-produktion.de

#### O.1.2 — Francia
- **L'argus.fr (Pro section)** — https://pro.largus.fr
- **Autoactu** — https://www.autoactu.com
- **Journal de l'Automobile** — https://www.journalauto.com
- **Décision Auto** — https://www.decision-auto.com
- **Auto Infos** — https://www.autoinfos.fr

#### O.1.3 — España
- **Asesor Vehículos** — publicación sectorial
- **Automóvil Pro** — https://www.automovilpro.com
- **Autorevista** — https://autorevista.com
- **Motor16** (con sección profesional)
- **Dirigentes Digital Auto** — sección auto

#### O.1.4 — Países Bajos
- **Automotive Management Nederland** — https://www.automotivemanagement.nl
- **Auto-Aktueel** — https://www.auto-aktueel.nl

#### O.1.5 — Bélgica
- **Fleet.be** — https://www.fleet.be
- **Link2Fleet** — https://www.link2fleet.com

#### O.1.6 — Suiza
- **AutoWoche CH** — https://www.autowoche.ch
- **AGVS news** — publicaciones de AGVS (cross-Familia G.CH)

### O.2 — Common Crawl News subset
- URL: https://commoncrawl.org/news-crawl/
- Dataset exclusivo de sites news crawleados más frecuentemente
- Alcance global, filtrable por TLD
- Procesamiento local vía DuckDB + WARC parser

### O.3 — Wayback Machine archives (cross-Familia C.2)
- Snapshots históricos de las publicaciones sectoriales arriba
- Permite reconstruir events históricos (aperturas, cierres) de dealers

### O.4 — GDELT Project
- URL: https://www.gdeltproject.org
- Dataset global de noticias monitorizadas en tiempo real
- Free, sin límites efectivos
- Filtrable por entidad + evento + geo
- Útil para detección temporal en tiempo real

### O.5 — Google News (cross-Familia K via SearXNG)
- Búsquedas en Google News sobre empresas del knowledge graph
- Señal de actividad prensa

### O.6 — Prensa general con sección motor (discovery secundario)
- Die Welt, FAZ, Süddeutsche (DE)
- Le Monde, Le Figaro (FR)
- El País, El Mundo, ABC (ES)
- De Volkskrant, NRC (NL)
- De Standaard, Le Soir (BE)
- NZZ, Tages-Anzeiger (CH)

Cobertura limitada vs prensa sectorial, pero captura eventos de gran escala.

### O.7 — Boletines oficiales y gacetas locales
- Cross-Familia J (BOPs) — menciones de altas, cambios, ceses de dealers

## Sub-técnicas

### O.M1 — Crawl respetuoso de prensa sectorial
Cada publicación tiene sitemap.xml + RSS. Strategy: respeto robots.txt, rate limit conservador, sync mensual.

### O.M2 — NER (Named Entity Recognition) sobre texto
Pipeline spaCy + modelos fine-tuned sobre dataset sectorial automoción para identificar:
- Empresa (dealer name)
- Ubicación
- Event type (apertura, fusión, cierre, premio, cambio de marca)
- Persona clave (CEO, administrador)
- Fecha del evento

### O.M3 — Entity linking con knowledge graph
Cada entidad NER extraída se intenta linkar con el knowledge graph existente (familias A-N). Match confirmado → enriquecimiento con event info. Match no encontrado → posible nuevo dealer, candidato a validación cruzada.

### O.M4 — Event classification
Classifier sobre tipo de event. Critical events:
- `opening` → nuevo dealer, iniciar ingesta
- `closure` → marcar dealer inactive en knowledge graph
- `merger` → fusionar entidades en knowledge graph
- `rebranding` → actualizar razón social
- `leadership_change` → actualizar metadata

### O.M5 — Temporal analysis
Histórico de menciones por dealer → serie temporal. Permite detectar picos (news-worthy events) y silencio prolongado (posible inactividad).

### O.M6 — Cross-language monitoring
NER + entity linking funciona en los 6 idiomas objetivo. Un dealer BE con website en FR puede aparecer en prensa NL o FR indistintamente.

## Base legal
- Prensa sectorial: acceso respetando robots.txt y ToS. Extracción NER es uso transformativo (no copia substantial).
- Snippets <11 palabras → Infopaq exception
- Common Crawl News + GDELT: bajo licencias CC que permiten data mining
- Wayback Machine: acceso permitido bajo misión de archivado

## Métricas
- `news_mentions_per_dealer` — frecuencia de menciones
- `event_detection_latency` — tiempo entre publicación y detección
- `unique_discovery_via_O` — dealers descubiertos via prensa
- `entity_linking_precision` — % NER matches correctamente enlazados

## Implementación
- Módulo Go: `discovery/family_o/`
- NER pipeline: Python subprocess (spaCy + custom models) → ONNX para inferencia CPU eficiente
- Persistencia: tabla `press_events` con FK a dealer-ID + full-text search index (SQLite FTS5)
- Cron: daily ingest GDELT + weekly crawl prensa sectorial
- Coste: medio (NER CPU-intensivo pero batch nocturno)

## Cross-validation

| Familia | Overlap | Único de O |
|---|---|---|
| A | ~60% | O captura dealers en prensa antes que en registros (aperturas pre-registro formal) |
| G | ~30% | O captura dealers independientes no en asociación |
| M | alto (signals activity) | O aporta signal cualitativo, M aporta signal estructural |

O es especialmente valiosa para detección temporal (state changes) más que para discovery primario.

## Riesgos y mitigaciones
- R-O1: prensa sectorial con paywall creciente. Mitigación: priorizar free sections + GDELT + Common Crawl como fallback.
- R-O2: NER con precisión imperfecta en nombres dealer (ambigüedades con nombres comunes). Mitigación: training continuo con corpus propio + threshold alto para autolink, baja para manual review.
- R-O3: prensa sensacionalista falsa (rumores de cierre no confirmados). Mitigación: corroboration mínimo 2 fuentes independientes antes de actuar sobre event.

## Iteración futura
- LLM local (Llama 3) para relation extraction más fine-grained que NER clásico
- Sentiment analysis por dealer (correlación con indicadores B2B satisfaction)
- Integración con podcasts/video news sectorial automoción (transcripción + análisis)
- Modelado predictivo de eventos (dealer X con patrón prensa Y → probability of event Z in T)
