# Core memory — índice

Contexto duradero de CARDEX: el GOAL, los estándares de trabajo (feedback), la
arquitectura objetivo, la estrategia de infraestructura y las referencias.
Procedencia: set de memoria del agente (`agent/memory/`). Las entradas de otro
proyecto (Habana Legacy) se han excluido a propósito — ver `../../README.md`.

## El objetivo
- [**GOAL #1 — 100% territorio + 900K+ dealers con web**](goal_cardex_total_coverage.md) — prioridad absoluta; métrica = dealers CON dominio web resuelto, no filas brutas.
- [Goal: scraping production indexing](project_cardex_scraping_goal.md) — cada portal indexa 100% del inventario live por país; ciclo deploy→monitor→diagnose→fix.

## Estado del proyecto
- [Estado CARDEX junio 2026](project_cardex_state.md) — main consolidado (los 8 frentes); métrica dealers-con-web ≈48,7K [verificado 2026-06-08; antes 45.864] en discovery_candidates.domain (tabla dealers vacía); cuello = browser/proxy + conversión a escala.
- [Supervisor 24/7 + 73 portales tier-1](project_cardex_supervisor_73.md) — daemon en el terminal del usuario; goal activo = 73 portales con config guardada por portal.
- [Plan 7 entregables P1](project_deliverables_action.md) — D1-D7 en `docs/deliverables/`.

## Arquitectura y resiliencia
- [Arquitectura objetivo](project_cardex_architecture.md) — microagentes por microtarea, paralelización horizontal por país, dashboard de control total.
- [Resiliencia anti-ruptura](project_cardex_resilience.md) — config-driven por web + detección de drift + alertas trazables + auto-remediación.
- [Guardian — auditoría continua anti-fugas](project_cardex_guardian_audit.md) — QA lógico post-tarea; razona gaps de cobertura (no solo wiring).
- [Discovery geo-sweep H3](project_cardex_geosweep_h3.md) — mallado hexagonal + diccionario multilingüe para el long-tail (capa futura).
- [Infra strategy](project_cardex_infra_strategy.md) — local=test (validar-y-purgar), VPS/terminal 24/7 = prod; config plug & play.

## Estándares de trabajo (feedback — cómo opero)
- [Cero atajos, cero invenciones](feedback_no_shortcuts.md)
- [Autorización amplia, ejecutar hasta cerrar](feedback_full_authorization.md)
- [Respuestas densas y técnicas](feedback_response_style.md)
- [NUNCA defaultear a "no se puede"](feedback_never_default_cant.md)
- [Investigar a fondo ANTES de implementar](feedback_research_before_implement.md)
- [NUNCA parar para preguntar](feedback_never_stop_to_ask.md)
- [Orquestación activa obligatoria](feedback_orchestration_active.md)
- [Hands off total — cero paradas](feedback_total_hands_off.md)
- [Full permisos — jamás pedir ejecución manual](feedback_full_perms_no_ask.md)
- [Limpiar worktrees siempre](feedback_worktree_cleanup.md)
- [Presupuesto cero — aparcar lo de pago](feedback_budget_zero_park_paid.md)
- [Cero excusas, responsabilidad total](feedback_zero_excuses_ownership.md)
- [Asignación de modelos por tarea](feedback_model_assignment.md)
- [Política de stealth](feedback_stealth_policy.md)
- [Dispatch — espera activa](feedback_dispatch_active_wait.md)

## Referencias
- [Repo CARDEX — path y convenciones](reference_repo_path.md)
- [Heartbeat de supervisión](reference_cardex_heartbeat.md)
- [APIs externas — estado de credenciales (redactado)](reference_api_credentials.md)
- [Perfil del operador / atribución](user_salman_cardex.md)
