---
name: Investigar a fondo ANTES de implementar
description: NUNCA implementar sin investigación previa exhaustiva. Research-first obligatorio para todo.
type: feedback
originSessionId: f40b2fe4-7b98-4b15-bea1-af705c3e870f
---
NUNCA proceder a implementar nada sin antes haber investigado a fondo. Investigación exhaustiva primero, implementación después. Sin excepciones.

**Why:** El usuario recibió múltiples iteraciones de resultados mediocres porque se implementó sobre suposiciones en lugar de datos reales. Ejemplo concreto: los plate resolvers se implementaron asumiendo cómo funcionaban los portales gubernamentales, resultando en scrapers rotos y datos mínimos. La investigación previa habría revelado los endpoints reales, los campos disponibles, y las limitaciones antes de escribir una sola línea de código.

**How to apply:** Para cualquier feature nueva o integración:
1. Lanzar agentes de investigación dedicados (preferiblemente Opus)
2. Probar con curl/HTTP real contra los endpoints antes de escribir código
3. Documentar hallazgos en un archivo .md
4. Solo entonces implementar sobre datos verificados
5. Nunca asumir que un endpoint funciona — probarlo primero
