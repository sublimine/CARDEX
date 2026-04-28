# ADR-0002 — Qwen2.5-Coder-7B Q5_K_M como clasificador fiscal local

**Fecha**: 2026-04-27 (redacción retroactiva de decisión vigente)
**Estado**: Vigente
**Owner**: Salman Karrouch

---

## Contexto

CARDEX requiere clasificación fiscal automatizada de listings (IVA deducible vs REBU) para 6 países UE. Los requisitos:
- Clasificación trazable: cada output debe poder rastrearse al prompt exacto y al modelo que la produjo.
- Operación local sin dependencia de API externa (privacidad de prompts y coste predecible).
- Latencia inferior a 2 segundos por clasificación en hardware de desarrollo.
- Capacidad de tuning de prompts iterativa sin coste por iteración.
- Hardware disponible: GPU consumer-grade, no datacenter.

## Opciones evaluadas

**Claude Sonnet vía API Anthropic**:
- Pros: precisión superior, sin gestión de modelo local.
- Contras: coste por clasificación a escala (millones de listings), dependencia de API externa, exposición de prompts a tercero.

**Llama 3.1 8B Q4_K_M**:
- Pros: modelo abierto, bien soportado.
- Contras: menor capacidad de razonamiento sobre regulación fiscal compleja en pruebas internas.

**Mixtral 8x7B Q4**:
- Pros: capacidad superior en tareas de razonamiento.
- Contras: requisitos de VRAM superiores al hardware disponible.

**Qwen2.5-Coder-7B Q5_K_M**:
- Pros: capacidad de razonamiento estructurado superior a Llama 8B en pruebas internas, encaje en VRAM disponible, latencia aceptable, soporte estable en llama.cpp.
- Contras: modelo orientado a código (Coder), aplicación a clasificación fiscal requiere prompt engineering específico.

## Decisión

Adoptar **Qwen2.5-Coder-7B Q5_K_M** servido vía llama.cpp en `localhost:8081` como clasificador fiscal de producción.

## Consecuencias aceptadas

- Toda `FiscalClassification` almacenada en PG incluye trazabilidad obligatoria al prompt exacto y al hash del modelo (invariante declarada en CLAUDE.md §17).
- Cambio de modelo o de cuantización requiere ADR nuevo y procedimiento de rotación documentado en RUNBOOKS RB-004.
- Pruebas de regresión clasificatoria obligatorias antes de promover cualquier cambio de prompt o modelo.
- LLM fuera del critical path en tiempo real: clasificación es asíncrona, listings se encolan si llama.cpp degrada.

## Fecha de revisión

2026-07-27 o cuando se publique un modelo abierto con superioridad demostrable en el banco de pruebas interno.
