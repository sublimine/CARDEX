---
name: project-cardex-infra-strategy
description: "Local PC is for testing only — validate indexing pipeline works, then purge listings to avoid saturating disk. VPS purchase pending for production."
metadata: 
  node_type: memory
  type: project
  originSessionId: f40b2fe4-7b98-4b15-bea1-af705c3e870f
---

Estrategia de infraestructura confirmada por Salman (2026-06-05):

1. **PC local = entorno de pruebas SOLAMENTE**. Validar que el pipeline completo funciona (discovery → extraction → indexing → MeiliSearch sync). Tanto T0 como T1, todos los tiers.
2. **Después de validar, borrar los listings permanentemente** para no saturar el disco del PC.
3. **Cuando todo esté ready, Salman compra un VPS** y se migra toda la infra ahí.
4. La integración en VPS es responsabilidad mía — configurar Docker, desplegar, arrancar producción.

**Why:** El PC de Salman tiene espacio limitado (67.33 GB usados de 1 TB según Docker). No tiene sentido acumular millones de listings en local. El objetivo local es demostrar que el pipeline end-to-end funciona.

**How to apply:** Al arrancar scrapers/discovery en local, configurar limits conservadores (batch size pequeño, max listings por portal). Una vez validado E2E, purgar datos y preparar deploy script para VPS. Cuando Salman confirme VPS, desplegar todo con docker compose en producción.

5. **Configuración de scraping = exportable e impecable.** Toda la config (domain_map, tier classification, rate limits, identity pools, circuit breaker thresholds, portal specs) debe estar organizada de forma que al migrar al VPS solo sea plug & play. Cero configuración manual.

**How to apply:** Asegurar que toda config de scraping viva en archivos versionados (no hardcoded, no en DB), documentada, y que `docker compose up -d` en el VPS arranque todo sin tocar nada.

Related: [[goal_cardex_total_coverage]], [[project_cardex_state]]
