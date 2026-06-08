---
name: project_cardex_resilience
description: "Subsistema de resiliencia anti-ruptura de CARDEX — config por web, detección de drift, alertas trazables, equipo de auto-remediación"
metadata: 
  node_type: memory
  type: project
  originSessionId: 020fe92e-3d59-49f4-9abe-f0ad36acb37d
---

Directiva de Salman (2026-06-06): CARDEX debe ser inmune a que los portales cambien su HTML/estructura. "Nunca perdemos un portal por un cambio." Integrado en [[project_cardex_guardian_audit]] (doc `GUARDIAN_AUDIT_SYSTEM.md`).

**Componentes exigidos:**
1. **Scraper config-driven por web.** Cada portal y cada dealer con su configuración de extracción ADAPTADA y GUARDADA (selectores/estrategia/endpoints/paginación/normalización) en un store versionado. Lógica genérica + particularidad en config → reparar = tocar la config de esa web.
2. **Detección de drift.** Cada corrida compara contra baseline (volumen en rango, campos presentes, esquema estable, ratios sanos). Desviación → marca DRIFT en esa web.
3. **Alertas trazables por origen.** Cada drift dispara alerta identificada: qué portal, qué cambió, desde cuándo, severidad, último estado bueno. Si 10 portales cambian, 10 alertas localizadas, no un genérico.
4. **Equipo de auto-remediación.** Ante alerta, se despliega equipo de agentes: investiga el cambio, audita la nueva estructura, regenera la config, valida con muestra (límite-y-purga), devuelve a producción. Trazado punta a punta; al dueño "detectado → reparado" o escalado si requiere decisión.

**Nota de contexto:** Salman notó ratios raros en el dashboard (p.ej. ~6-10% de candidatos con web, candidatos sin scrapear). NO es bug del dashboard: es la foto REAL del estado roto actual (discovery descableado, 84% FR de una fuente, candidatos en `pending`). P0 + vertical NL lo corrigen. Ver [[goal_cardex_total_coverage]] y [[project_cardex_state]].

**Estado (2026-06-07):** IMPLEMENTADO en gran parte. Drift-gate cableado al coordinator vivo (P1). Sistema de scraping a medida por dealer (`feature/dealer-scraping-system`, mergeado): config versionada por dealer + `remediation.py` REAL (re-detect→regenerate→revalidate). **P2 PENDIENTE (cazado por Guardian):** el TRIGGER de auto-remediación NO está cableado — el harvester calcula `drift_ok` pero nunca llama `remediate()`; capacidad real pero dormida. Cablear `if not drift.ok: remediate(...)`. También P2: `playwright_xhr` para SPAs con datos en XHR, conector feed DMS para inventario embebido.
