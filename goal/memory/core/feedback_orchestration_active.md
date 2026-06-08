---
name: Feedback — orquestación activa obligatoria
description: Dispatch debe supervisar activamente, tomar decisiones, resolver bloqueos, no dejar sesiones paradas. Cero CHAPUZAS, todo robusto e impecable (el stealth temporal por presupuesto SÍ se permite, ver feedback_stealth_policy).
type: feedback
originSessionId: f40b2fe4-7b98-4b15-bea1-af705c3e870f
---
Dispatch NO es un lanzador pasivo de sesiones. Es un orquestador activo que:

1. Monitorea cada sesión constantemente — no lanzar y olvidar
2. Si una sesión se bloquea, interviene inmediatamente (send_message o relanzar)
3. Toma decisiones técnicas cuando las sesiones no saben cómo seguir
4. Gestiona conflictos entre sesiones (git, archivos compartidos)
5. Verifica que el output es robusto, no chapuzas

**Why:** El usuario perdió 2 meses porque las sesiones se quedaban paradas sin supervisión. El patrón "lanzo y espero" es el anti-patrón principal.

**How to apply:** Después de lanzar sesiones, hacer polling activo cada 1-2 minutos. Si una sesión lleva >5 min sin avanzar turns, investigar y desbloquear. Si una sesión termina con errores, relanzar inmediatamente. No reportar al usuario hasta que haya resultados concretos verificados.

Reforzado 2026-06-05: "No quiero nada parado, supervisando cada cosa activamente, cada error lo arreglas, cada cosa lo auditas. No se te pasa ni un rasguño, todo siempre a la máxima calidad institucional." Esto aplica a TODAS las sesiones, perpetuamente.
