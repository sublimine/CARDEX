---
name: Policy R1 — cero atajos, cero superficialidad, cero invenciones
description: Hard rule against shortcuts, fabrication, and superficial work across all CARDEX tasks
type: feedback
---

Regla R1 (inviolable): en todo el proyecto CARDEX está prohibido atajar, inventar datos/fuentes/sentencias, o producir trabajo superficial. Salman lo califica explícitamente como "pecar".

**Why:** Expectativa de calidad institucional. Cualquier atajo contamina el repo, introduce riesgo legal (citas inventadas de TJUE, por ejemplo), y erosiona la confianza en todo lo demás. Inventar una dependencia, un endpoint, o una obligación regulatoria es peor que admitir desconocimiento.

**How to apply:**
- Si no existe fuente autoritativa, decirlo y parar — no rellenar.
- Si un fixture o endpoint no puede verificarse, marcarlo como TODO explícito, nunca stubbear en silencio.
- Si una tarea exige mínimos cuantitativos (ej: "mínimo 20 predicciones"), cumplirlos o declarar la razón de no alcanzarlos.
- Sin mocks donde pueda usarse fixture real; sin tests skipeados silenciosamente; sin features declaradas en docs pero no implementadas.
- Verificación final obligatoria (go test -race, lint, govulncheck) antes de marcar done.
- También aplica a la postura legal: cero WAF evasion, cero stealth, UA CardexBot identificable, respeto a robots.txt en todos los fetchers incluidos fixtures.
