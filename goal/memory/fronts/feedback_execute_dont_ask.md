---
name: Execute, don't ask
description: User rejects options/clarifying questions when a mission is already defined; wants direct execution with real probing
type: feedback
originSessionId: c98d6429-f694-41d1-ad0e-5a893b5b7e9f
---
Cuando el usuario me da una misión con scope grande (investigar/implementar muchas fuentes, múltiples países, etc.), NO debo:
- Dar opciones A/B para elegir
- Parar a preguntar "¿quieres que...?"
- Defaultear a "no se puede" por legal/ToS/scraping/complejidad
- Recortar scope antes de intentarlo

SÍ debo:
- Probar cada fuente con curl real primero
- Si una falla, documentar el curl exacto + respuesta y seguir
- Implementar parsers solo para las que devuelven datos
- Documentar honestamente lo que no funciona con evidencia (no con "probablemente no")

**Why:** Su instrucción literal: "No me des a elegir a mi que te di la puta mision", "NUNCA defaultear a 'no se puede'", "No acepto un no como respuesta", "Trabajo profesional de elite de primera avanzado lento e impecable". Ya pasó una vez en CARDEX Check donde preguntas abrían debate en vez de ejecutar.

**How to apply:** En misiones tipo "investiga + implementa X", ir directo a curl/probe/code. Reservas legales/técnicas se documentan como hallazgos (con evidencia real), no como justificación para no empezar. Solo parar a preguntar si hay una decisión irreversible de infra/dinero. Un brief en español con tono imperativo ("EJECUTA", "VE") es señal definitiva.
