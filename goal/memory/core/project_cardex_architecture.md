---
name: project_cardex_architecture
description: "Arquitectura CARDEX deseada — microagentes especializados, paralelización por país, dashboard de control total"
metadata: 
  node_type: memory
  type: project
  originSessionId: 020fe92e-3d59-49f4-9abe-f0ad36acb37d
---

Visión de arquitectura que Salman quiere para CARDEX (montar poco a poco, pero robusto e impecable desde la base):

**Microagentes, no monolitos.** Descomponer en microtareas con un agente fresco por función, p.ej.: (1) descubridor que encuentra y lanza enlaces; (2) localizador del catálogo/marketplace real de cada portal; (3) extractor de HTML; (4) parser+scraper que estructura y guarda; etc. Un agente por microtarea rinde mejor y no cuesta más tokens que un monolito que lo hace todo.

**Paralelización horizontal por país.** En vez de un agente recorriendo 6 países en serie (lento), un equipo/agente por país (DE, FR, ES, BE, NL, CH) scrapeando simultáneamente. Matiz del orquestador acordado: **primero clavar y validar el patrón en un portal/país, luego abanicar a los 6** — paralelizar antes de tener el patrón replica el caos x6.

**Criterio fino de paralelización (lección 2026-06-07, runtime compartido):** paralelizar SOLO lo aislado en datos (discovery por país escribe a su propio scope `country=XX`, fuentes/endpoints distintos → seguro; research). SERIALIZAR lo que toca estado global mutable: migraciones de esquema, reinicios de Docker, tablas compartidas — ahí 2 sesiones colisionan (visto con la sesión duplicada). El bootstrap de discovery puede ir en serie (rápido); el **barrido/poblado masivo por país** es donde la paralelización real (equipos por país con aislamiento) gana días — ese es el momento de desplegar horizontal.

**Dashboard de control total.** Salman debe poder supervisar todo desde un panel: estado de tiers, sistema de crawling, sistema de portales, descubrimiento de dealers, y las demás vías. Múltiples vías corren en paralelo horizontalmente; la organización y el control deben ser totales.

**Infra:** de momento todo corre en el terminal de Salman (local = test). Cuando se encuentre la fórmula para scrapear el 100%, paga la VPS y se arranca a público. Ver [[project_cardex_infra_strategy]] y [[goal_cardex_total_coverage]].
