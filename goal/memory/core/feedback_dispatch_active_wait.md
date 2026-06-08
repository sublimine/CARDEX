---
name: feedback_dispatch_active_wait
description: Regla operativa Dispatch — no puedo auto-enviar entre turnos; debo hacer ESPERA ACTIVA con polling del transcript dentro del mismo turno
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 020fe92e-3d59-49f4-9abe-f0ad36acb37d
---

**Límite real del modo Dispatch (señalado por Salman el 2026-06-06):** si cierro el turno tras lanzar una task, NO proceso hasta que el usuario me escriba. Por tanto, si termino el turno, Salman NUNCA recibirá el resultado de la task sin escribirme primero.

**Regla:** cuando lanzo una task cuyo resultado Salman espera, me quedo en **espera activa dentro del mismo turno**: hago polling con `read_transcript` (que bloquea hasta max_wait_seconds) en bucle hasta que la task termine, y entonces le reporto yo. Si la espera se alarga, le doy updates de progreso periódicos, pero NO cierro el turno dejándolo sin respuesta.

**Why:** es la materialización concreta del "estar en primera línea" y de "cero excusas": la supervisión activa solo existe si me quedo procesando; cerrar el turno = abandono de facto. Ver [[feedback_zero_excuses_ownership]] y [[feedback_orchestration_active]].
**How to apply:** tras start_task/start_code_task relevante → read_transcript en bucle (max_wait alto), reportar al terminar o dar update si tarda; nunca cerrar turno esperando que el usuario pregunte.
