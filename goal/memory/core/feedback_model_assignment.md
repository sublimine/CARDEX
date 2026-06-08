---
name: feedback_model_assignment
description: "Asignación de modelos por tarea — orquestador en Opus, subagentes en el modelo justo y necesario; no preocuparse por tokens"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 020fe92e-3d59-49f4-9abe-f0ad36acb37d
---

Salman delega en el orquestador la **asignación de modelo por agente**. Reglas:

- El **orquestador soy yo = Opus 4.8** (el cargo máximo), siempre que se pueda.
- A cada subagente, el modelo **justo y necesario + un pelín por encima** de la dificultad de su tarea, para que tenga margen pero sin desperdiciar. No poner Opus a todo.
- Microtareas simples → modelos baratos. Salman mencionó Llama para tareas triviales. **Matiz honesto:** los subagentes nativos de este harness son Claude (opus/sonnet/haiku); Llama no es un tipo de subagente nativo, pero sí puede invocarse vía API/local dentro de scripts que el agente ejecute. Usar haiku/sonnet para lo barato dentro del harness.
- **No optimizar por tokens.** Hay bono de doble recompensa de uso de Claude **hasta el 5 de julio de 2026** que conviene aprovechar. Si se agotan tokens/bono, Salman lo resuelve; que no sea un freno.

**Why:** eficiencia de coste sin sacrificar capacidad; el cuello de botella es la calidad, no los tokens.
**How to apply:** al lanzar cada Agent, elegir modelo por dificultad real de la microtarea. Ver [[project_cardex_architecture]].
