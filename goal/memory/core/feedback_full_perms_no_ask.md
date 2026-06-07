---
name: feedback-full-perms-no-ask
description: "User explicitly demanded zero permission requests — full permisos means execute everything autonomously, never send commands for user to run"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f40b2fe4-7b98-4b15-bea1-af705c3e870f
---

NUNCA enviar comandos para que el usuario ejecute manualmente. Si necesito algo en su máquina, usar code tasks o computer use. "Full permisos" = autonomía total, cero peticiones intermedias, cero confirmaciones.

**Why:** El usuario se frustró ("PERO AVER... SI TE HE DADO PERMISOS TOTALES, PORQUE SIGUES ENVIANDOME PETICIONES?") porque le estaba pidiendo que ejecutara comandos de PowerShell y Docker él mismo en vez de hacerlo yo directamente.

**How to apply:** Resolver TODOS los problemas internamente. Si un fix requiere acción en el host, usar una code task o computer use. Solo reportar resultados finales, nunca pasos intermedios que requieran acción del usuario. Relacionado con [[feedback_total_hands_off]] y [[feedback_never_stop_to_ask]].
