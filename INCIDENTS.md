# CARDEX — INCIDENTS

<!-- Registro de incidentes con post-mortem. Cronológico inverso (más reciente arriba). -->
<!-- Cada entrada: fecha, severidad, detección, causa raíz, resolución, lecciones, acciones derivadas. -->

---

## Formato canónico de entrada

```
## YYYY-MM-DD — [Severidad] Título corto

**Detección**: cómo y cuándo se detectó.
**Componentes afectados**: lista de servicios o módulos.
**Duración**: tiempo desde detección hasta resolución.
**Impacto**: qué se perdió, qué se degradó, cuántos listings/vehículos afectados.

**Causa raíz**: análisis de qué condición precipitó el fallo. No "qué pasó" sino "por qué pasó".

**Resolución**: pasos exactos ejecutados para restaurar el servicio.

**Lecciones**: qué hemos aprendido que cambia cómo operamos.

**Acciones derivadas**:
- [ ] Acción concreta con owner y fecha
- [ ] ADR si aplica
- [ ] Cambio en CLAUDE.md si modifica invariante
- [ ] Runbook nuevo o actualizado si aplica
```

---

## Severidades

- **SEV-1**: pérdida de datos, indisponibilidad del pipeline > 1h, o exposición de credenciales.
- **SEV-2**: degradación significativa del throughput, fallos parciales, o consumer trabado.
- **SEV-3**: bug funcional sin pérdida de datos ni indisponibilidad.

---

## Historial

Sin incidentes registrados a fecha 2026-04-27. La primera entrada se redacta al primer incidente real.
