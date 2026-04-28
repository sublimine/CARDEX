# ADR-0008 — Misión técnica: cobertura del 100% del territorio en los 6 países objetivo

**Fecha**: 2026-04-27
**Estado**: Vigente
**Owner**: Salman Karrouch

---

## Contexto

CARDEX vende inteligencia fiscal sobre arbitraje transfronterizo de vehículos usados en la UE. El valor del producto para el ICP (traders profesionales) es estrictamente proporcional a la completitud del inventario indexado: un dataset parcial deja oportunidades de arbitraje fuera del análisis y degrada la confianza del cliente en la herramienta.

Decisiones de producto, de ingeniería y de pricing dependen de un compromiso explícito sobre el alcance del scraping.

## Opciones evaluadas

**Cobertura best-effort por país**:
- Pros: arranque rápido, decisiones flexibles por dominio.
- Contras: ambigüedad sobre qué se considera "suficiente", proliferación de excepciones, valor del producto difuso para el cliente.

**Cobertura tier-based (top dominios primero, long tail descartado)**:
- Pros: ROI inicial alto.
- Contras: deja fuera oportunidades de arbitraje en dominios de menor volumen pero de alto margen, reduce diferenciación competitiva.

**Cobertura del 100% del territorio en 6 países**:
- Pros: producto definido por completitud, diferenciación clara frente a alternativas best-effort, alineación entre pricing y cobertura, criterio operativo inequívoco para priorización.
- Contras: requiere disciplina de paginación exhaustiva, requiere fallbacks ante dominios difíciles, requiere infraestructura de monitorización de cobertura efectiva.

## Decisión

Adoptar **misión de cobertura del 100% del territorio** como compromiso técnico vinculante:
- 6 países UE objetivo (lista específica gestionada por owner, fuera del alcance de este ADR).
- "Territorio" = todos los listings públicos accesibles vía sitemap o paginación de listados públicos.
- Excluido del alcance: listings de plataformas privadas con autenticación obligatoria.

## Consecuencias aceptadas

- **Paginación exhaustiva** declarada como invariante en CLAUDE.md §27: nunca abandonar un dominio antes de agotar su inventario completo. Es anti-patrón flaggeable.
- **Sin techos mentales** (CLAUDE.md §3): cuando una ruta directa no alcanza, combinar approaches (sitemap + paginación + browser stealth como excepción documentada).
- **Métrica de cobertura efectiva** debe instrumentarse: comparar listings indexados contra estimación de inventario total por dominio.
- **Pricing** se construye sobre la garantía de cobertura: el modelo monetario por país de cobertura activado (CLAUDE.md §16) refleja directamente este compromiso.
- **Excepciones**: dominios donde la cobertura del 100% es técnicamente imposible o económicamente irracional se documentan como ADR específico de exclusión, no como degradación silenciosa.

## Fecha de revisión

Trimestral. La cobertura efectiva se audita contra el objetivo y los gaps se registran como deuda priorizada en STATUS.md.
